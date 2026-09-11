"""Fake-only contract for the generic MLX BERT embedding interpreter."""

from __future__ import annotations

import json
from collections.abc import Callable
from types import SimpleNamespace

import pytest

from dynamic_agent_runner.errors import EmbeddingExecutionError
from dynamic_agent_runner.local_models import EmbeddingInputItem
from dynamic_agent_runner.workflow_host.execution_descriptors import (
    parse_execution_descriptor,
)
from dynamic_agent_runner.workflow_host.mlx_embedding_abi import (
    BertEncoderMlxV1EmbeddingBackend,
    _bert_tensor_shapes,
)


def _materials() -> SimpleNamespace:
    return SimpleNamespace(
        execution_descriptor=parse_execution_descriptor(
            {
                "format_version": 1,
                "architecture_abi": {
                    "id": "bert-encoder-mlx-v1",
                    "version": "1",
                    "contract_digest": "2179662461bf786c7f55d88d9e3454a3d4dc59f5e818a96e248847abc62e4420",
                },
                "material_roles": ["tokenizer", "weights"],
                "abi_fields": {
                    "tokenizer": {
                        "role": "tokenizer",
                        "format": "wordpiece-json-v1",
                        "normalization": "nfc",
                        "pre_tokenizer": "bert-basic-v1",
                        "special_token_ids": {
                            "cls": 101,
                            "sep": 102,
                            "pad": 0,
                            "unk": 100,
                        },
                        "truncation": "longest-first",
                    },
                    "encoder": {
                        "weights_role": "weights",
                        "tensor_layout": "bert-encoder-safetensors-v1",
                        "dtype": "float32",
                        "vocab_size": 200,
                        "hidden_size": 2,
                        "layers": 1,
                        "attention_heads": 1,
                        "intermediate_size": 2,
                        "max_positions": 2,
                        "type_vocab_size": 1,
                    },
                    "pooling": "cls",
                    "normalization": "none",
                    "limits": {
                        "max_items": 1,
                        "max_item_bytes": 1,
                        "max_aggregate_bytes": 1,
                        "max_tokens": 1,
                        "max_vectors": 1,
                        "max_memory_bytes": 1,
                        "max_tokenizer_bytes": 1,
                        "max_weights_bytes": 1,
                        "max_safetensors_header_bytes": 1,
                        "max_conformance_fixture_bytes": 1,
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


TensorHeader = dict[str, dict[str, object]]
HeaderMutation = Callable[[TensorHeader], None]


def _weights_header(*, mutate: HeaderMutation | None = None) -> bytes:
    descriptor = _materials().execution_descriptor
    header = {
        name: {"dtype": "F32", "shape": list(shape)}
        for name, shape in _bert_tensor_shapes(descriptor).items()
    }
    if mutate is not None:
        mutate(header)
    return json.dumps(header).encode()


def test_backend_rejects_malformed_artifacts_before_tokenizer_or_model_work() -> None:
    calls: list[str] = []
    backend = BertEncoderMlxV1EmbeddingBackend(
        artifact_reader=lambda _role: calls.append("artifact") or b"malformed",
        tokenizer=lambda _items: calls.append("tokenizer") or (),
        encoder=lambda _tokens: calls.append("encoder") or (),
    )

    with pytest.raises(EmbeddingExecutionError, match="material"):
        backend.embed((EmbeddingInputItem("entry", "text"),), _materials())

    assert calls == ["artifact"]


def test_backend_rejects_malformed_weights_before_tokenizer_or_model_work() -> None:
    calls: list[str] = []

    def artifact_reader(role: str) -> bytes:
        calls.append(role)
        return b"{}" if role == "tokenizer" else b"malformed"

    backend = BertEncoderMlxV1EmbeddingBackend(
        artifact_reader=artifact_reader,
        tokenizer=lambda _items: calls.append("tokenizer-call") or (),
        encoder=lambda _tokens: calls.append("encoder-call") or (),
    )

    with pytest.raises(EmbeddingExecutionError, match="material"):
        backend.embed((EmbeddingInputItem("entry", "text"),), _materials())

    assert calls == ["tokenizer", "weights"]


def test_backend_rejects_unknown_tensor_before_tokenizer_or_model_work() -> None:
    calls: list[str] = []
    header = json.dumps({"unexpected": {}}).encode()

    def artifact_reader(role: str) -> bytes:
        calls.append(role)
        return (
            b"{}" if role == "tokenizer" else len(header).to_bytes(8, "little") + header
        )

    backend = BertEncoderMlxV1EmbeddingBackend(
        artifact_reader=artifact_reader,
        tokenizer=lambda _items: calls.append("tokenizer-call") or (),
        encoder=lambda _tokens: calls.append("encoder-call") or (),
    )

    with pytest.raises(EmbeddingExecutionError, match="material"):
        backend.embed((EmbeddingInputItem("entry", "text"),), _materials())

    assert calls == ["tokenizer", "weights"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda header: header["embeddings.word_embeddings.weight"].update(
            shape=[199, 2]
        ),
        lambda header: header["embeddings.word_embeddings.weight"].update(dtype="F16"),
    ],
)
def test_backend_rejects_wrong_tensor_metadata_before_tokenizer_or_model_work(
    mutate: HeaderMutation,
) -> None:
    calls: list[str] = []
    header = _weights_header(mutate=mutate)

    def artifact_reader(role: str) -> bytes:
        calls.append(role)
        return (
            b"{}" if role == "tokenizer" else len(header).to_bytes(8, "little") + header
        )

    backend = BertEncoderMlxV1EmbeddingBackend(
        artifact_reader=artifact_reader,
        tokenizer=lambda _items: calls.append("tokenizer-call") or (),
        encoder=lambda _tokens: calls.append("encoder-call") or (),
    )

    with pytest.raises(EmbeddingExecutionError, match="material"):
        backend.embed((EmbeddingInputItem("entry", "text"),), _materials())

    assert calls == ["tokenizer", "weights"]
