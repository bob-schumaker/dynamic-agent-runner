"""Fake-only contract tests for the closed MLX RoBERTa embedding interpreter."""

from __future__ import annotations

import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from dynamic_agent_runner.errors import EmbeddingExecutionError
from dynamic_agent_runner.local_models import EmbeddingInputItem
from dynamic_agent_runner.workflow_host.execution_descriptors import (
    parse_execution_descriptor,
)
from dynamic_agent_runner.workflow_host.mlx_roberta_embedding_abi import (
    ROBERTA_ENCODER_MLX_V1_ABI,
    RobertaEncoderMlxV1EmbeddingBackend,
    roberta_encoder_mlx_v1_embedding_batch_limits,
    _roberta_tensor_shapes,
)


def _materials(
    *, pooling: str = "masked_mean", normalization: str = "l2"
) -> SimpleNamespace:
    return SimpleNamespace(
        execution_descriptor=parse_execution_descriptor(
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
                    "pooling": pooling,
                    "normalization": normalization,
                    "limits": {
                        "max_items": 1,
                        "max_item_bytes": 1_024,
                        "max_aggregate_bytes": 1_024,
                        "max_tokens": 4,
                        "max_vectors": 1,
                        "max_memory_bytes": 1_000_000,
                        "max_tokenizer_bytes": 1_024,
                        "max_weights_bytes": 1_000_000,
                        "max_safetensors_header_bytes": 1_000_000,
                        "max_conformance_fixture_bytes": 1_000_000,
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
    )


def _tokenizer_assets() -> tuple[bytes, bytes]:
    return (
        json.dumps(
            {
                "<s>": 0,
                "<pad>": 1,
                "</s>": 2,
                "<unk>": 3,
                "<mask>": 4,
                "h": 5,
                "i": 6,
                "Ġ": 7,
                "Ġh": 8,
                "Ġhi": 9,
                "!": 10,
                "Ã": 11,
                "©": 12,
                "Ã©": 13,
            },
            sort_keys=True,
        ).encode(),
        b"#version: 0.2\n\xc4\xa0 h\n\xc4\xa0h i\n\xc3\x83 \xc2\xa9\n",
    )


def _weights_blob(*, mutate=None) -> bytes:
    descriptor = _materials().execution_descriptor
    cursor = 0
    header = {
        name: {
            "data_offsets": [cursor, cursor := cursor + 4 * math.prod(shape)],
            "dtype": "F32",
            "shape": list(shape),
        }
        for name, shape in _roberta_tensor_shapes(descriptor).items()
    }
    if mutate is not None:
        mutate(header)
    payload = bytearray(cursor)
    return (
        len(json.dumps(header).encode()).to_bytes(8, "little")
        + json.dumps(header).encode()
        + payload
    )


class _NumpyMlx:
    int32 = np.int32

    @staticmethod
    def array(value: object, dtype: object | None = None) -> np.ndarray:
        return np.array(value, dtype=dtype)

    @staticmethod
    def zeros(shape: tuple[int, ...], dtype: object | None = None) -> np.ndarray:
        return np.zeros(shape, dtype=dtype)

    @staticmethod
    def mean(value: np.ndarray, *, axis: int, keepdims: bool) -> np.ndarray:
        return np.mean(value, axis=axis, keepdims=keepdims)

    @staticmethod
    def sqrt(value: np.ndarray | float) -> np.ndarray | float:
        return np.sqrt(value)

    @staticmethod
    def sum(value: np.ndarray, *, axis: int, keepdims: bool = False) -> np.ndarray:
        return np.sum(value, axis=axis, keepdims=keepdims)

    @staticmethod
    def softmax(value: np.ndarray, *, axis: int) -> np.ndarray:
        shifted = value - np.max(value, axis=axis, keepdims=True)
        exponentials = np.exp(shifted)
        return exponentials / np.sum(exponentials, axis=axis, keepdims=True)

    @staticmethod
    def erf(value: np.ndarray) -> np.ndarray:
        return np.vectorize(math.erf)(value)

    @staticmethod
    def eval(*_values: object) -> None:
        return None

    @staticmethod
    def load(source: str) -> dict[str, np.ndarray]:
        payload = Path(source).read_bytes()
        header_size = int.from_bytes(payload[:8], "little")
        header = json.loads(payload[8 : 8 + header_size])
        data = payload[8 + header_size :]
        return {
            name: np.frombuffer(
                data,
                dtype=np.float32,
                count=math.prod(metadata["shape"]),
                offset=metadata["data_offsets"][0],
            ).reshape(metadata["shape"])
            for name, metadata in header.items()
        }


class _RecordingNumpyMlx(_NumpyMlx):
    sqrt_inputs: list[np.ndarray | float] = []

    @classmethod
    def sqrt(cls, value: np.ndarray | float) -> np.ndarray | float:
        cls.sqrt_inputs.append(value)
        return super().sqrt(value)


def test_backend_executes_the_closed_roberta_encoder_with_fake_mlx() -> None:
    vocab, merges = _tokenizer_assets()
    weights = _weights_blob()
    backend = RobertaEncoderMlxV1EmbeddingBackend(
        artifact_reader=lambda role: {
            "vocab": vocab,
            "merges": merges,
            "weights": weights,
        }[role],
        mlx_loader=_NumpyMlx,
    )

    materials = _materials(normalization="none")
    result = backend.embed((EmbeddingInputItem("entry", " hi"),), materials)

    assert result.model == materials.execution_descriptor.digest
    assert result.items[0].id == "entry"
    assert result.items[0].vector == (0.0, 0.0)


def test_backend_rejects_changed_tensor_header_before_mlx_load() -> None:
    vocab, merges = _tokenizer_assets()
    weights = _weights_blob(
        mutate=lambda header: header["embeddings.position_embeddings.weight"].update(
            shape=[5, 2]
        )
    )
    backend = RobertaEncoderMlxV1EmbeddingBackend(
        artifact_reader=lambda role: {
            "vocab": vocab,
            "merges": merges,
            "weights": weights,
        }[role],
        mlx_loader=lambda: pytest.fail("MLX must not load"),
    )

    with pytest.raises(EmbeddingExecutionError, match="material is unavailable"):
        backend.embed((EmbeddingInputItem("entry", " hi"),), _materials())


def test_roberta_abi_projects_descriptor_limits_without_material_reads() -> None:
    limits = roberta_encoder_mlx_v1_embedding_batch_limits(
        _materials().execution_descriptor
    )

    assert limits.max_items == 1
    assert limits.max_item_utf8_bytes == 1_024
    assert limits.max_total_utf8_bytes == 1_024
    assert limits.max_vector_dimension == 2
    assert limits.max_total_vectors == 1


def test_backend_uses_roberta_epsilon_at_all_layer_norm_sites() -> None:
    vocab, merges = _tokenizer_assets()
    weights = _weights_blob()
    _RecordingNumpyMlx.sqrt_inputs.clear()
    backend = RobertaEncoderMlxV1EmbeddingBackend(
        artifact_reader=lambda role: {
            "vocab": vocab,
            "merges": merges,
            "weights": weights,
        }[role],
        mlx_loader=_RecordingNumpyMlx,
    )

    backend.embed(
        (EmbeddingInputItem("entry", " hi"),), _materials(normalization="none")
    )

    epsilon_inputs = [
        value
        for value in _RecordingNumpyMlx.sqrt_inputs
        if isinstance(value, np.ndarray) and value.shape == (1, 4, 1)
    ]
    assert len(epsilon_inputs) == 3
    assert all(np.all(value == 1e-5) for value in epsilon_inputs)
