"""Fake-only contract for the generic MLX BERT embedding interpreter."""

from __future__ import annotations

import pytest

from dynamic_agent_runner.errors import EmbeddingExecutionError
from dynamic_agent_runner.local_models import EmbeddingInputItem
from dynamic_agent_runner.workflow_host.mlx_embedding_abi import (
    BertEncoderMlxV1EmbeddingBackend,
)


def test_backend_rejects_malformed_artifacts_before_tokenizer_or_model_work() -> None:
    calls: list[str] = []
    backend = BertEncoderMlxV1EmbeddingBackend(
        artifact_reader=lambda _role: calls.append("artifact") or b"malformed",
        tokenizer=lambda _items: calls.append("tokenizer") or (),
        encoder=lambda _tokens: calls.append("encoder") or (),
    )

    with pytest.raises(EmbeddingExecutionError, match="material"):
        backend.embed((EmbeddingInputItem("entry", "text"),), object())

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
        backend.embed((EmbeddingInputItem("entry", "text"),), object())

    assert calls == ["tokenizer", "weights"]
