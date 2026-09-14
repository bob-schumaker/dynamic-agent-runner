"""Fake-only source-preparation tests for the closed RoBERTa embedding ABI."""

from __future__ import annotations

import json
import math
import struct

import pytest

from dynamic_agent_runner.workflow_host.execution_descriptors import (
    parse_execution_descriptor,
)
from dynamic_agent_runner.workflow_host.mlx_roberta_embedding_abi import (
    ROBERTA_ENCODER_MLX_V1_ABI,
    _roberta_tensor_shapes,
)
from dynamic_agent_runner.workflow_host.mlx_roberta_weight_preparation import (
    MLX_ROBERTA_V1_WEIGHT_PREPARATION_CONTRACT,
    MLX_ROBERTA_V1_WEIGHT_PREPARATION_CONTRACT_DIGEST,
    mlx_roberta_v1_weight_preparation_provider,
)
from dynamic_agent_runner.workflow_host.model_materials import (
    MaterialOutput,
    PreparationOperation,
    transformation_digest,
)


def _descriptor():
    return parse_execution_descriptor(
        {
            "format_version": 1,
            "architecture_abi": ROBERTA_ENCODER_MLX_V1_ABI.to_mapping(),
            "material_roles": ["merges", "vocab", "weights"],
            "abi_fields": {
                "tokenizer": {
                    "vocab_role": "vocab",
                    "merges_role": "merges",
                    "format": "roberta-byte-level-bpe-v1",
                    "pre_tokenizer": "gpt2-byte-level-v1",
                    "add_prefix_space": False,
                    "special_token_ids": {
                        "bos": 0,
                        "eos": 2,
                        "pad": 1,
                        "unk": 3,
                        "mask": 4,
                    },
                    "truncation": "longest-first",
                },
                "encoder": {
                    "weights_role": "weights",
                    "tensor_layout": "roberta-encoder-safetensors-v1",
                    "dtype": "float32",
                    "vocab_size": 14,
                    "hidden_size": 2,
                    "layers": 1,
                    "attention_heads": 1,
                    "intermediate_size": 2,
                    "max_positions": 6,
                    "type_vocab_size": 1,
                    "position_ids": "roberta-padding-index-v1",
                    "layer_norm_epsilon": 1e-5,
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


def _operation() -> PreparationOperation:
    value: dict[str, object] = {
        "capability_id": MLX_ROBERTA_V1_WEIGHT_PREPARATION_CONTRACT.contract_id,
        "contract_version": MLX_ROBERTA_V1_WEIGHT_PREPARATION_CONTRACT.version,
        "contract_digest": MLX_ROBERTA_V1_WEIGHT_PREPARATION_CONTRACT_DIGEST,
        "inputs": ["source_weights"],
        "output": {
            "role": "weights",
            "group": "weights",
            "filename": "model.safetensors",
            "sha256": "b" * 64,
        },
    }
    return PreparationOperation(
        capability_id=value["capability_id"],
        contract_version=value["contract_version"],
        contract_digest=value["contract_digest"],
        inputs=tuple(value["inputs"]),
        output=MaterialOutput(**value["output"]),
        transformation_digest=transformation_digest(value),
    )


def _source_weights(
    *, ancillary: bool = False, pooler: bool = False, mutate=None
) -> bytes:
    descriptor = _descriptor()
    header: dict[str, object] = {"__metadata__": {"format": "pt"}}
    body = bytearray()
    for name, shape in sorted(_roberta_tensor_shapes(descriptor).items()):
        start = len(body)
        body.extend(struct.pack(f"<{math.prod(shape)}f", *([1.0] * math.prod(shape))))
        header[name] = {
            "dtype": "F32",
            "shape": list(shape),
            "data_offsets": [start, len(body)],
        }
    if ancillary:
        start = len(body)
        body.extend(struct.pack("<6q", *range(6)))
        header["embeddings.position_ids"] = {
            "dtype": "I64",
            "shape": [1, 6],
            "data_offsets": [start, len(body)],
        }
        for name, shape in {
            "lm_head.dense.weight": (2, 2),
            "lm_head.dense.bias": (2,),
            "lm_head.layer_norm.weight": (2,),
            "lm_head.layer_norm.bias": (2,),
            "lm_head.decoder.weight": (14, 2),
            "lm_head.decoder.bias": (14,),
        }.items():
            start = len(body)
            body.extend(
                struct.pack(f"<{math.prod(shape)}f", *([2.0] * math.prod(shape)))
            )
            header[name] = {
                "dtype": "F32",
                "shape": list(shape),
                "data_offsets": [start, len(body)],
            }
    if pooler:
        for name, shape in {
            "pooler.dense.weight": (2, 2),
            "pooler.dense.bias": (2,),
        }.items():
            start = len(body)
            body.extend(
                struct.pack(f"<{math.prod(shape)}f", *([3.0] * math.prod(shape)))
            )
            header[name] = {
                "dtype": "F32",
                "shape": list(shape),
                "data_offsets": [start, len(body)],
            }
    if mutate is not None:
        mutate(header)
    header_bytes = json.dumps(header, sort_keys=True, separators=(",", ":")).encode()
    return len(header_bytes).to_bytes(8, "little") + header_bytes + bytes(body)


def _header(content: bytes) -> dict[str, object]:
    size = int.from_bytes(content[:8], "little")
    return json.loads(content[8 : 8 + size])


def test_provider_removes_only_complete_descriptor_derived_ancillary_groups() -> None:
    descriptor = _descriptor()
    prepared = mlx_roberta_v1_weight_preparation_provider(descriptor).prepare(
        _operation(), {"source_weights": _source_weights(ancillary=True, pooler=True)}
    )

    assert set(_header(prepared)) == {
        "__metadata__",
        *_roberta_tensor_shapes(descriptor),
    }


@pytest.mark.parametrize(
    "mutate",
    (
        lambda header: header.pop("lm_head.decoder.bias"),
        lambda header: header["embeddings.position_ids"].update(dtype="I32"),
        lambda header: header["embeddings.position_ids"].update(shape=[1, 5]),
        lambda header: header["lm_head.decoder.bias"].update(data_offsets=[1, 2]),
        lambda header: header.update(
            extra={"dtype": "F32", "shape": [], "data_offsets": [0, 0]}
        ),
    ),
)
def test_provider_rejects_changed_or_partial_source_only_groups(mutate) -> None:
    provider = mlx_roberta_v1_weight_preparation_provider(_descriptor())

    with pytest.raises(ValueError, match="unavailable"):
        provider.prepare(
            _operation(),
            {"source_weights": _source_weights(ancillary=True, mutate=mutate)},
        )


@pytest.mark.parametrize(
    "mutate",
    (
        lambda header: header.pop("pooler.dense.bias"),
        lambda header: header["pooler.dense.weight"].update(shape=[3, 2]),
        lambda header: header["pooler.dense.bias"].update(data_offsets=[1, 2]),
    ),
)
def test_provider_rejects_changed_or_partial_pooler_group(mutate) -> None:
    provider = mlx_roberta_v1_weight_preparation_provider(_descriptor())

    with pytest.raises(ValueError, match="unavailable"):
        provider.prepare(
            _operation(),
            {"source_weights": _source_weights(pooler=True, mutate=mutate)},
        )
