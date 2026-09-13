"""Receiver-owned preparation for sealed MLX BERT v4 embedding weights."""

from __future__ import annotations

import hashlib
import json
import math
import struct
from collections.abc import Mapping

from dynamic_agent_runner.workflow_host.execution_descriptors import (
    ExecutionDescriptor,
)
from dynamic_agent_runner.workflow_host.mlx_embedding_abi import (
    BERT_ENCODER_MLX_V4_ABI,
    BertEncoderMlxV4DescriptorValidator,
    _bert_dtype_details,
    _bert_optional_pooler_shapes,
    _bert_tensor_shapes,
)
from dynamic_agent_runner.workflow_host.model_material_admission import (
    ModelPreparationProvider,
)
from dynamic_agent_runner.workflow_host.model_materials import (
    MaterialContract,
    PreparationOperation,
    transformation_digest,
)


MLX_V4_WEIGHT_PREPARATION_PROVIDER_ID = "receiver-mlx-v4-weight-preparer"
MLX_V4_WEIGHT_PREPARATION_CONTRACT = MaterialContract(
    "mlx.embedding.weights.prepare.v1", "1"
)
MLX_V4_WEIGHT_PREPARATION_CONTRACT_DIGEST = hashlib.sha256(
    b"dar.mlx.embedding.weights.prepare.v1:source_weights:f32:weights:mixed-f16-f32"
).hexdigest()

_SOURCE_ROLE = "source_weights"
_OUTPUT_ROLE = "weights"
_OUTPUT_GROUP = "weights"
_OUTPUT_FILENAME = "model.safetensors"
_CONVERSION_CHUNK_FLOATS = 65_536


def mlx_v4_weight_preparation_provider(
    descriptor: ExecutionDescriptor,
) -> ModelPreparationProvider:
    """Return one v4-descriptor-bound, receiver-local preparation provider."""

    try:
        BertEncoderMlxV4DescriptorValidator().validate(descriptor)
        if descriptor.architecture_abi != BERT_ENCODER_MLX_V4_ABI:
            raise ValueError
        expected = _expected_tensors(descriptor)
        maximum_header_bytes = _limit(descriptor, "max_safetensors_header_bytes")
        maximum_weight_bytes = _limit(descriptor, "max_weights_bytes")
    except Exception as error:  # noqa: BLE001 - sealed descriptor boundary.
        raise ValueError("MLX v4 weight preparation is unavailable") from error

    def prepare(operation: PreparationOperation, inputs: Mapping[str, bytes]) -> bytes:
        try:
            _validate_operation(operation)
            if set(inputs) != {_SOURCE_ROLE} or not isinstance(
                inputs[_SOURCE_ROLE], bytes
            ):
                raise ValueError
            return _convert_source_weights(
                inputs[_SOURCE_ROLE],
                expected=expected,
                maximum_header_bytes=maximum_header_bytes,
                maximum_weight_bytes=maximum_weight_bytes,
            )
        except Exception as error:  # noqa: BLE001 - sealed material boundary.
            raise ValueError("MLX v4 weight preparation is unavailable") from error

    return ModelPreparationProvider(
        provider_id=MLX_V4_WEIGHT_PREPARATION_PROVIDER_ID,
        contract=MLX_V4_WEIGHT_PREPARATION_CONTRACT,
        contract_digest=MLX_V4_WEIGHT_PREPARATION_CONTRACT_DIGEST,
        prepare=prepare,
    )


def _expected_tensors(
    descriptor: ExecutionDescriptor,
) -> dict[str, tuple[tuple[int, ...], str]]:
    shapes = _bert_tensor_shapes(descriptor)
    optional_shapes = _bert_optional_pooler_shapes(descriptor)
    return {
        name: (shape, _bert_dtype_details(descriptor, name)[0])
        for name, shape in {**shapes, **optional_shapes}.items()
    }


def _limit(descriptor: ExecutionDescriptor, name: str) -> int:
    limits = descriptor.abi_fields["limits"]
    if not isinstance(limits, Mapping) or not isinstance(limits[name], int):
        raise ValueError
    return limits[name]


def _validate_operation(operation: PreparationOperation) -> None:
    if (
        operation.capability_id != MLX_V4_WEIGHT_PREPARATION_CONTRACT.contract_id
        or operation.contract_version != MLX_V4_WEIGHT_PREPARATION_CONTRACT.version
        or operation.contract_digest != MLX_V4_WEIGHT_PREPARATION_CONTRACT_DIGEST
        or operation.inputs != (_SOURCE_ROLE,)
        or operation.output.role != _OUTPUT_ROLE
        or operation.output.group != _OUTPUT_GROUP
        or operation.output.filename != _OUTPUT_FILENAME
        or operation.transformation_digest
        != transformation_digest(operation.to_mapping())
    ):
        raise ValueError


def _convert_source_weights(
    source: bytes,
    *,
    expected: Mapping[str, tuple[tuple[int, ...], str]],
    maximum_header_bytes: int,
    maximum_weight_bytes: int,
) -> bytes:
    if len(source) < 8 or len(source) > maximum_weight_bytes:
        raise ValueError
    header_size = int.from_bytes(source[:8], "little")
    if header_size > maximum_header_bytes or len(source) < 8 + header_size:
        raise ValueError
    header = _header(source[8 : 8 + header_size])
    source_body = source[8 + header_size :]
    source_tensors, metadata = _source_tensor_header(
        header, expected=expected, data_size=len(source_body)
    )
    output_header: dict[str, object] = {}
    if metadata is not None:
        output_header["__metadata__"] = metadata
    output_body = bytearray()
    for name in sorted(source_tensors):
        shape, output_dtype = expected[name]
        start, end = source_tensors[name]
        data = source_body[start:end]
        output_start = len(output_body)
        if output_dtype == "F16":
            output_body.extend(_f32_to_f16(data))
        else:
            output_body.extend(data)
        output_header[name] = {
            "data_offsets": [output_start, len(output_body)],
            "dtype": output_dtype,
            "shape": list(shape),
        }
    header_bytes = json.dumps(
        output_header, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    if len(header_bytes) > maximum_header_bytes:
        raise ValueError
    return len(header_bytes).to_bytes(8, "little") + header_bytes + bytes(output_body)


def _header(value: bytes) -> Mapping[str, object]:
    try:
        decoded = value.decode("utf-8")
        parsed = json.loads(decoded, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError from error
    if not isinstance(parsed, Mapping) or any(
        not isinstance(key, str) for key in parsed
    ):
        raise ValueError
    return parsed


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _source_tensor_header(
    header: Mapping[str, object],
    *,
    expected: Mapping[str, tuple[tuple[int, ...], str]],
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
    known_names = set(expected)
    optional_names = {"pooler.dense.bias", "pooler.dense.weight"}
    tensor_names = set(tensors)
    if (
        not set(expected) - optional_names <= tensor_names
        or tensor_names - known_names
        or (tensor_names & optional_names and not optional_names <= tensor_names)
    ):
        raise ValueError
    offsets: dict[str, tuple[int, int]] = {}
    spans: list[tuple[int, int]] = []
    for name in sorted(tensor_names):
        specification = tensors[name]
        shape, _output_dtype = expected[name]
        if not isinstance(specification, Mapping):
            raise ValueError
        source_shape = specification.get("shape")
        data_offsets = specification.get("data_offsets")
        if (
            specification.get("dtype") != "F32"
            or not isinstance(source_shape, list)
            or tuple(source_shape) != shape
            or any(
                not isinstance(value, int) or isinstance(value, bool)
                for value in source_shape
            )
            or not isinstance(data_offsets, list)
            or len(data_offsets) != 2
            or any(
                not isinstance(value, int) or isinstance(value, bool)
                for value in data_offsets
            )
        ):
            raise ValueError
        start, end = data_offsets
        if (
            start < 0
            or end < start
            or end > data_size
            or end - start != math.prod(shape) * 4
        ):
            raise ValueError
        offsets[name] = (start, end)
        spans.append((start, end))
    previous_end = 0
    for start, end in sorted(spans):
        if start != previous_end:
            raise ValueError
        previous_end = end
    if previous_end != data_size:
        raise ValueError
    return offsets, metadata


def _f32_to_f16(source: bytes) -> bytes:
    if len(source) % 4:
        raise ValueError
    converted = bytearray()
    for offset in range(0, len(source), _CONVERSION_CHUNK_FLOATS * 4):
        chunk = source[offset : offset + _CONVERSION_CHUNK_FLOATS * 4]
        count = len(chunk) // 4
        converted.extend(struct.pack(f"<{count}e", *struct.unpack(f"<{count}f", chunk)))
    return bytes(converted)
