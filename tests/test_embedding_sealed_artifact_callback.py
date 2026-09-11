"""Tests for the receiver-owned sealed embedding callback bridge."""

from __future__ import annotations

import json

from dynamic_agent_runner.workflow_host.embedding_execution import (
    EmbeddingBatchLimits,
    EmbeddingExecutionBinding,
    EmbeddingTextItem,
    EmbeddingVector,
)
from dynamic_agent_runner.workflow_host.embedding_sealed_artifact_callback import (
    EmbeddingSealedArtifactCallbackProvider,
)
from dynamic_agent_runner.workflow_host.model_execution_binding import (
    ModelExecutionBinding,
)
from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactCallback,
)


def test_sealed_embedding_callback_translates_only_canonical_bounded_json() -> None:
    calls: list[object] = []

    class Execution:
        def execute(self, **kwargs):  # type: ignore[no-untyped-def]
            calls.append(kwargs)
            return (EmbeddingVector("chunk-1", (0.25, 0.75)),)

    callback = SealedArtifactCallback(
        "embed", "embedding.execute.v1", "a" * 64, 1, 1, 256, 256, 256, 256, 1
    )
    binding = EmbeddingExecutionBinding(
        ModelExecutionBinding(
            "locked",
            "runner",
            "1",
            None,
            None,
            "b" * 64,
            "c" * 64,
            "runner.capability",
            "1",
            "d" * 64,
        ),
        "embedding.execute.v1",
        "1",
        "e" * 64,
    )
    provider = EmbeddingSealedArtifactCallbackProvider(
        callback=callback,
        execution=Execution(),
        binding=binding,
        selected_provider_ids=("receiver-private",),
        limits=EmbeddingBatchLimits(1, 16, 16, 2, 1),
    )

    response = provider.invoke("embed", b'{"items":[{"id":"chunk-1","text":"note"}]}')

    assert json.loads(response) == {
        "items": [{"id": "chunk-1", "vector": [0.25, 0.75]}]
    }
    assert calls[0]["items"] == (EmbeddingTextItem("chunk-1", "note"),)
