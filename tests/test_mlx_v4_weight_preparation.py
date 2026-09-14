"""Tests for the sealed v4 MLX embedding weight preparation provider."""

from __future__ import annotations

import json
import math
import struct
from hashlib import sha256

import pytest

from dynamic_agent_runner.workflow_host.execution_descriptors import (
    parse_execution_descriptor,
)
from dynamic_agent_runner.workflow_host.capabilities import (
    CapabilityRequirement,
    CapabilityRequirements,
)
from dynamic_agent_runner.workflow_host.mlx_embedding_abi import (
    BERT_ENCODER_MLX_V3_ABI,
    BERT_ENCODER_MLX_V4_ABI,
    _bert_dtype_details,
    _bert_tensor_shapes,
)
from dynamic_agent_runner.workflow_host.mlx_v4_weight_preparation import (
    MLX_V4_WEIGHT_PREPARATION_CONTRACT,
    MLX_V4_WEIGHT_PREPARATION_CONTRACT_DIGEST,
    MLX_V4_WEIGHT_PREPARATION_PROVIDER_ID,
    mlx_v4_weight_preparation_provider,
)
from dynamic_agent_runner.workflow_host.model_materials import (
    MaterialOutput,
    PreparationOperation,
    parse_model_dependency_lock,
    transformation_digest,
)
from dynamic_agent_runner.workflow_host.model_material_admission import (
    HostMaterialPolicy,
    ModelMaterialAdmission,
    ModelMaterialAdmissionError,
)


def _descriptor(*, abi=BERT_ENCODER_MLX_V4_ABI):
    return parse_execution_descriptor(
        {
            "format_version": 1,
            "architecture_abi": abi.to_mapping(),
            "material_roles": ["tokenizer", "weights"],
            "abi_fields": {
                "tokenizer": {
                    "role": "tokenizer",
                    "format": "sentencepiece-unigram-model-v1",
                    "normalization": "nmt-nfkc",
                    "pre_tokenizer": "sentencepiece-unigram-v1",
                    "id_offset": 1,
                    "special_token_ids": {"cls": 0, "sep": 2, "pad": 1, "unk": 3},
                    "truncation": "longest-first",
                },
                "encoder": {
                    "weights_role": "weights",
                    "tensor_layout": "bert-encoder-safetensors-v1",
                    "dtype": "float16",
                    "layer_norm_dtype": "float32",
                    "vocab_size": 8,
                    "hidden_size": 4,
                    "layers": 1,
                    "attention_heads": 2,
                    "intermediate_size": 8,
                    "max_positions": 4,
                    "type_vocab_size": 2,
                },
                "pooling": "masked_mean",
                "normalization": "l2",
                "limits": {
                    "max_items": 1,
                    "max_item_bytes": 16,
                    "max_aggregate_bytes": 16,
                    "max_tokens": 4,
                    "max_vectors": 1,
                    "max_memory_bytes": 1_000_000,
                    "max_tokenizer_bytes": 1_000,
                    "max_weights_bytes": 1_000_000,
                    "max_safetensors_header_bytes": 1_000_000,
                    "max_conformance_fixture_bytes": 1_000,
                },
                "conformance": {
                    "fixture_filename": "conformance-fixture.json",
                    "fixture_sha256": "a" * 64,
                    "precision": "float32",
                    "metric": "max_abs",
                    "max_error": 0.0,
                },
            },
        }
    )


def _operation(*, source_role: str = "source_weights") -> PreparationOperation:
    value: dict[str, object] = {
        "capability_id": MLX_V4_WEIGHT_PREPARATION_CONTRACT.contract_id,
        "contract_version": MLX_V4_WEIGHT_PREPARATION_CONTRACT.version,
        "contract_digest": MLX_V4_WEIGHT_PREPARATION_CONTRACT_DIGEST,
        "inputs": [source_role],
        "output": {
            "role": "weights",
            "group": "weights",
            "filename": "model.safetensors",
            "sha256": "b" * 64,
        },
    }
    return PreparationOperation(
        capability_id=value["capability_id"],  # type: ignore[arg-type]
        contract_version=value["contract_version"],  # type: ignore[arg-type]
        contract_digest=value["contract_digest"],  # type: ignore[arg-type]
        inputs=tuple(value["inputs"]),  # type: ignore[arg-type]
        output=MaterialOutput(**value["output"]),  # type: ignore[arg-type]
        transformation_digest=transformation_digest(value),
    )


def _source_weights(
    descriptor, *, include_position_ids: bool = False, mutate=None
) -> bytes:
    shapes = _bert_tensor_shapes(descriptor)
    header: dict[str, object] = {"__metadata__": {"format": "pt"}}
    body = bytearray()
    for index, (name, shape) in enumerate(sorted(shapes.items())):
        start = len(body)
        count = math.prod(shape)
        body.extend(struct.pack(f"<{count}f", *([index + 0.25] * count)))
        header[name] = {
            "dtype": "F32",
            "shape": list(shape),
            "data_offsets": [start, len(body)],
        }
    if include_position_ids:
        positions = descriptor.abi_fields["encoder"]["max_positions"]
        assert isinstance(positions, int)
        start = len(body)
        body.extend(struct.pack(f"<{positions}q", *range(positions)))
        header["embeddings.position_ids"] = {
            "dtype": "I64",
            "shape": [1, positions],
            "data_offsets": [start, len(body)],
        }
    if mutate is not None:
        mutate(header)
    header_bytes = json.dumps(
        header, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return len(header_bytes).to_bytes(8, "little") + header_bytes + bytes(body)


def _header(content: bytes) -> dict[str, object]:
    size = int.from_bytes(content[:8], "little")
    return json.loads(content[8 : 8 + size])


def test_provider_is_fixed_to_the_v4_descriptor_and_exact_contract() -> None:
    descriptor = _descriptor()
    provider = mlx_v4_weight_preparation_provider(descriptor)

    assert provider.provider_id == MLX_V4_WEIGHT_PREPARATION_PROVIDER_ID
    assert provider.contract == MLX_V4_WEIGHT_PREPARATION_CONTRACT
    assert provider.contract_digest == MLX_V4_WEIGHT_PREPARATION_CONTRACT_DIGEST

    with pytest.raises(ValueError, match="unavailable"):
        mlx_v4_weight_preparation_provider(_descriptor(abi=BERT_ENCODER_MLX_V3_ABI))


def test_provider_converts_only_declared_non_layer_norm_tensors_deterministically() -> (
    None
):
    descriptor = _descriptor()
    provider = mlx_v4_weight_preparation_provider(descriptor)
    source = _source_weights(descriptor)

    first = provider.prepare(_operation(), {"source_weights": source})
    second = provider.prepare(_operation(), {"source_weights": source})
    header = _header(first)
    source_header = _header(source)
    shapes = _bert_tensor_shapes(descriptor)

    assert first == second
    assert set(header) == {"__metadata__", *shapes}
    assert header["__metadata__"] == {"format": "pt"}
    for name, shape in shapes.items():
        metadata = header[name]
        assert metadata["shape"] == list(shape)
        assert metadata["dtype"] == _bert_dtype_details(descriptor, name)[0]
    first_tensor = next(name for name in sorted(shapes) if ".LayerNorm." not in name)
    offset = header[first_tensor]["data_offsets"]
    body_start = 8 + int.from_bytes(first[:8], "little")
    expected = sorted(shapes).index(first_tensor) + 0.25
    assert struct.unpack(
        "<e", first[body_start + offset[0] : body_start + offset[0] + 2]
    )[0] == pytest.approx(expected)
    layer_norm_name = next(name for name in sorted(shapes) if ".LayerNorm." in name)
    source_body_start = 8 + int.from_bytes(source[:8], "little")
    source_offset = source_header[layer_norm_name]["data_offsets"]
    output_offset = header[layer_norm_name]["data_offsets"]
    assert (
        source[
            source_body_start + source_offset[0] : source_body_start + source_offset[1]
        ]
        == first[body_start + output_offset[0] : body_start + output_offset[1]]
    )


@pytest.mark.parametrize(
    "mutate",
    (
        lambda header: header.pop("embeddings.word_embeddings.weight"),
        lambda header: header["embeddings.word_embeddings.weight"].update(dtype="F16"),
        lambda header: header["embeddings.word_embeddings.weight"].update(
            data_offsets=[1, 2]
        ),
        lambda header: header.update(
            extra={"dtype": "F32", "shape": [], "data_offsets": [0, 0]}
        ),
    ),
)
def test_provider_rejects_changed_source_header_before_conversion(mutate) -> None:
    descriptor = _descriptor()
    provider = mlx_v4_weight_preparation_provider(descriptor)

    with pytest.raises(ValueError, match="unavailable"):
        provider.prepare(
            _operation(), {"source_weights": _source_weights(descriptor, mutate=mutate)}
        )


def test_provider_rejects_changed_operation_or_source_role_before_conversion() -> None:
    descriptor = _descriptor()
    provider = mlx_v4_weight_preparation_provider(descriptor)
    source = _source_weights(descriptor)

    with pytest.raises(ValueError, match="unavailable"):
        provider.prepare(_operation(source_role="weights"), {"weights": source})


def test_provider_discards_only_the_standard_position_ids_buffer() -> None:
    descriptor = _descriptor()
    provider = mlx_v4_weight_preparation_provider(descriptor)

    prepared = provider.prepare(
        _operation(),
        {"source_weights": _source_weights(descriptor, include_position_ids=True)},
    )

    assert "embeddings.position_ids" not in _header(prepared)


@pytest.mark.parametrize(
    "mutate",
    (
        lambda header: header["embeddings.position_ids"].update(dtype="I32"),
        lambda header: header["embeddings.position_ids"].update(shape=[1, 3]),
        lambda header: header["embeddings.position_ids"].update(data_offsets=[1, 2]),
        lambda header: header.update(
            extra_ids={"dtype": "I64", "shape": [1, 4], "data_offsets": [0, 32]}
        ),
    ),
)
def test_provider_rejects_changed_or_extra_ancillary_source_tensors(mutate) -> None:
    descriptor = _descriptor()
    provider = mlx_v4_weight_preparation_provider(descriptor)

    with pytest.raises(ValueError, match="unavailable"):
        provider.prepare(
            _operation(),
            {
                "source_weights": _source_weights(
                    descriptor, include_position_ids=True, mutate=mutate
                )
            },
        )


def test_admission_selects_only_the_descriptor_bound_preparation_provider() -> None:
    descriptor = _descriptor()
    provider = mlx_v4_weight_preparation_provider(descriptor)
    source = _source_weights(descriptor)
    output = provider.prepare(_operation(), {"source_weights": source})
    operation = {
        "capability_id": MLX_V4_WEIGHT_PREPARATION_CONTRACT.contract_id,
        "contract_version": MLX_V4_WEIGHT_PREPARATION_CONTRACT.version,
        "contract_digest": MLX_V4_WEIGHT_PREPARATION_CONTRACT_DIGEST,
        "inputs": ["source_weights"],
        "output": {
            "role": "weights",
            "group": "weights",
            "filename": "model.safetensors",
            "sha256": sha256(output).hexdigest(),
        },
    }
    operation["transformation_digest"] = transformation_digest(operation)
    lock = parse_model_dependency_lock(
        {
            "format_version": 2,
            "logical_model_id": "sealed-test-package",
            "runner_contract": {"id": "embedding.execute.v1", "version": "1"},
            "execution_descriptor": {
                "filename": "execution-descriptor.json",
                "sha256": "a" * 64,
            },
            "sources": [
                {
                    "role": "source_weights",
                    "group": "weights",
                    "source_type": "huggingface_file",
                    "repository": "example-org/example-model",
                    "revision": "a" * 40,
                    "filename": "model.safetensors",
                    "sha256": sha256(source).hexdigest(),
                }
            ],
            "preparation": [operation],
        }
    )
    requirements = CapabilityRequirements(
        (
            CapabilityRequirement("embedding.execute.v1", "1", "d" * 64, ()),
            CapabilityRequirement(
                MLX_V4_WEIGHT_PREPARATION_CONTRACT.contract_id,
                MLX_V4_WEIGHT_PREPARATION_CONTRACT.version,
                MLX_V4_WEIGHT_PREPARATION_CONTRACT_DIGEST,
                (),
            ),
        ),
        {"runner": "embedding.execute.v1"},
    )

    class Cache:
        def __init__(self) -> None:
            self.values: dict[tuple[str, str, str | None], bytes] = {}

        def load(self, **kwargs):
            return self.values.get(
                (kwargs["lock_digest"], kwargs["role"], kwargs["transformation_digest"])
            )

        def promote(self, **kwargs) -> None:
            self.values[
                (kwargs["lock_digest"], kwargs["role"], kwargs["transformation_digest"])
            ] = kwargs["content"]

    class Transport:
        def __init__(self) -> None:
            self.calls = 0

        def fetch(self, _source: object) -> bytes:
            self.calls += 1
            return source

    transport = Transport()
    admission = ModelMaterialAdmission(
        cache=Cache(),
        transport=transport,
        providers=(provider,),
        selected_provider_ids=("a-different-provider",),
        revalidate_selected=lambda _ids: True,
        policy=HostMaterialPolicy(allow_download=True, allow_preparation=True),
    )
    with pytest.raises(ModelMaterialAdmissionError, match="material_unavailable"):
        admission.materialize(lock=lock, requirements=requirements)
    assert transport.calls == 0

    materials = ModelMaterialAdmission(
        cache=Cache(),
        transport=transport,
        providers=(provider,),
        selected_provider_ids=(MLX_V4_WEIGHT_PREPARATION_PROVIDER_ID,),
        revalidate_selected=lambda _ids: True,
        policy=HostMaterialPolicy(allow_download=True, allow_preparation=True),
    ).materialize(lock=lock, requirements=requirements)
    assert materials.artifacts == {"source_weights": source, "weights": output}
