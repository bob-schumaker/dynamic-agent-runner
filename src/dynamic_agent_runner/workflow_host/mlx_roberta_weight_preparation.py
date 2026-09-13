"""Receiver-owned source preparation for sealed RoBERTa embedding weights."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping

from dynamic_agent_runner.workflow_host.execution_descriptors import ExecutionDescriptor
from dynamic_agent_runner.workflow_host.mlx_roberta_embedding_abi import (
    ROBERTA_ENCODER_MLX_V1_ABI,
    RobertaEncoderMlxV1DescriptorValidator,
    _roberta_tensor_shapes,
)
from dynamic_agent_runner.workflow_host.model_material_admission import (
    ModelPreparationProvider,
)
from dynamic_agent_runner.workflow_host.model_materials import (
    MaterialContract,
    PreparationOperation,
    transformation_digest,
)


MLX_ROBERTA_V1_WEIGHT_PREPARATION_PROVIDER_ID = "receiver-mlx-roberta-v1-preparer"
MLX_ROBERTA_V1_WEIGHT_PREPARATION_CONTRACT = MaterialContract(
    "mlx.embedding.roberta.weights.prepare.v1", "1"
)
MLX_ROBERTA_V1_WEIGHT_PREPARATION_CONTRACT_DIGEST = hashlib.sha256(
    b"dar.mlx.embedding.roberta.weights.prepare.v1:source_weights:execution-weights"
).hexdigest()

_SOURCE_ROLE = "source_weights"
_OUTPUT_ROLE = "weights"
_OUTPUT_GROUP = "weights"
_OUTPUT_FILENAME = "model.safetensors"
_POSITION_IDS = "embeddings.position_ids"


def mlx_roberta_v1_weight_preparation_provider(
    descriptor: ExecutionDescriptor,
) -> ModelPreparationProvider:
    """Bind one finite source-only removal contract to the RoBERTa ABI."""

    try:
        RobertaEncoderMlxV1DescriptorValidator().validate(descriptor)
        if descriptor.architecture_abi != ROBERTA_ENCODER_MLX_V1_ABI:
            raise ValueError
        expected = _roberta_tensor_shapes(descriptor)
        limits = descriptor.abi_fields["limits"]
        if not isinstance(limits, Mapping):
            raise ValueError
        header_limit = limits["max_safetensors_header_bytes"]
        weight_limit = limits["max_weights_bytes"]
        if not isinstance(header_limit, int) or not isinstance(weight_limit, int):
            raise ValueError
    except Exception as error:  # noqa: BLE001 - sealed descriptor boundary.
        raise ValueError("MLX RoBERTa weight preparation is unavailable") from error

    def prepare(operation: PreparationOperation, inputs: Mapping[str, bytes]) -> bytes:
        try:
            if (
                operation.capability_id
                != MLX_ROBERTA_V1_WEIGHT_PREPARATION_CONTRACT.contract_id
                or operation.contract_version
                != MLX_ROBERTA_V1_WEIGHT_PREPARATION_CONTRACT.version
                or operation.contract_digest
                != MLX_ROBERTA_V1_WEIGHT_PREPARATION_CONTRACT_DIGEST
                or operation.inputs != (_SOURCE_ROLE,)
                or operation.output.role != _OUTPUT_ROLE
                or operation.output.group != _OUTPUT_GROUP
                or operation.output.filename != _OUTPUT_FILENAME
                or operation.transformation_digest
                != transformation_digest(operation.to_mapping())
                or set(inputs) != {_SOURCE_ROLE}
                or not isinstance(inputs[_SOURCE_ROLE], bytes)
            ):
                raise ValueError
            return _prepare(inputs[_SOURCE_ROLE], expected, header_limit, weight_limit)
        except Exception as error:  # noqa: BLE001 - sealed material boundary.
            raise ValueError("MLX RoBERTa weight preparation is unavailable") from error

    return ModelPreparationProvider(
        provider_id=MLX_ROBERTA_V1_WEIGHT_PREPARATION_PROVIDER_ID,
        contract=MLX_ROBERTA_V1_WEIGHT_PREPARATION_CONTRACT,
        contract_digest=MLX_ROBERTA_V1_WEIGHT_PREPARATION_CONTRACT_DIGEST,
        prepare=prepare,
    )


def _prepare(
    source: bytes,
    expected: Mapping[str, tuple[int, ...]],
    header_limit: int,
    weight_limit: int,
) -> bytes:
    if len(source) < 8 or len(source) > weight_limit:
        raise ValueError
    header_size = int.from_bytes(source[:8], "little")
    if header_size > header_limit or len(source) < 8 + header_size:
        raise ValueError
    header = _header(source[8 : 8 + header_size])
    body = source[8 + header_size :]
    offsets, metadata = _source_tensors(header, expected, len(body))
    output_header: dict[str, object] = {}
    if metadata is not None:
        output_header["__metadata__"] = metadata
    output_body = bytearray()
    for name in sorted(offsets):
        start, end = offsets[name]
        output_start = len(output_body)
        output_body.extend(body[start:end])
        output_header[name] = {
            "dtype": "F32",
            "shape": list(expected[name]),
            "data_offsets": [output_start, len(output_body)],
        }
    encoded = json.dumps(
        output_header, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    if len(encoded) > header_limit:
        raise ValueError
    return len(encoded).to_bytes(8, "little") + encoded + bytes(output_body)


def _header(value: bytes) -> Mapping[str, object]:
    try:
        parsed = json.loads(value.decode("utf-8"), object_pairs_hook=_unique)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError from error
    if not isinstance(parsed, Mapping) or any(
        not isinstance(key, str) for key in parsed
    ):
        raise ValueError
    return parsed


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _source_tensors(
    header: Mapping[str, object],
    expected: Mapping[str, tuple[int, ...]],
    data_size: int,
) -> tuple[dict[str, tuple[int, int]], Mapping[str, str] | None]:
    tensors = dict(header)
    metadata = tensors.pop("__metadata__", None)
    if metadata is not None and (
        not isinstance(metadata, Mapping)
        or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in metadata.items()
        )
    ):
        raise ValueError
    ancillary = {
        _POSITION_IDS: (
            "I64",
            (1, expected["embeddings.position_embeddings.weight"][0]),
        )
    }
    hidden = expected["embeddings.LayerNorm.weight"][0]
    vocab = expected["embeddings.word_embeddings.weight"][0]
    lm_head = {
        "lm_head.dense.weight": ("F32", (hidden, hidden)),
        "lm_head.dense.bias": ("F32", (hidden,)),
        "lm_head.layer_norm.weight": ("F32", (hidden,)),
        "lm_head.layer_norm.bias": ("F32", (hidden,)),
        "lm_head.decoder.weight": ("F32", (vocab, hidden)),
        "lm_head.decoder.bias": ("F32", (vocab,)),
    }
    names = set(tensors)
    extras = names - set(expected)
    if not set(expected) <= names or extras not in (
        set(),
        set(ancillary),
        set(lm_head),
        set(ancillary) | set(lm_head),
    ):
        raise ValueError
    offsets = {
        name: _span(tensors[name], "F32", shape, data_size)
        for name, shape in expected.items()
    }
    spans = list(offsets.values())
    for name in extras:
        dtype, shape = (ancillary | lm_head)[name]
        spans.append(_span(tensors[name], dtype, shape, data_size))
    previous = 0
    for start, end in sorted(spans):
        if start != previous:
            raise ValueError
        previous = end
    if previous != data_size:
        raise ValueError
    return offsets, metadata


def _span(
    value: object, dtype: str, shape: tuple[int, ...], data_size: int
) -> tuple[int, int]:
    if (
        not isinstance(value, Mapping)
        or value.get("dtype") != dtype
        or value.get("shape") != list(shape)
    ):
        raise ValueError
    offsets = value.get("data_offsets")
    if (
        not isinstance(offsets, list)
        or len(offsets) != 2
        or any(not isinstance(item, int) or isinstance(item, bool) for item in offsets)
    ):
        raise ValueError
    start, end = offsets
    bytes_per_item = 8 if dtype == "I64" else 4
    if (
        start < 0
        or end < start
        or end > data_size
        or end - start != math.prod(shape) * bytes_per_item
    ):
        raise ValueError
    return start, end
