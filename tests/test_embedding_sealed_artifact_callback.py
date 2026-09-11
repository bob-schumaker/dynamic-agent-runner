"""Tests for the receiver-owned sealed embedding callback bridge."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from dynamic_agent_runner.workflow_host.embedding_execution import (
    EmbeddingBatchLimits,
    EmbeddingExecutionBinding,
    EmbeddingLimitProjectorBinding,
    EmbeddingLimitProjectorRegistry,
    EmbeddingTextItem,
    EmbeddingVector,
)
from dynamic_agent_runner.workflow_host.embedding_sealed_artifact_callback import (
    EmbeddingSealedArtifactCallbackError,
    EmbeddingSealedArtifactCallbackProvider,
    EmbeddingSealedArtifactCallbackResolver,
)
from dynamic_agent_runner.workflow_host.execution_descriptors import (
    ExecutionDescriptorAbi,
    parse_execution_descriptor,
)
from dynamic_agent_runner.workflow_host.model_execution_binding import (
    ModelExecutionBinding,
)
from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactCallback,
    SealedArtifactRunnerDescriptor,
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


def test_embedding_resolver_rejects_a_policy_without_the_exact_callback() -> None:
    class Execution:
        def execute(self, **_kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("execution must not be reached")

    identity = ExecutionDescriptorAbi("example-encoder-v1", "1", "d" * 64)
    resolver = EmbeddingSealedArtifactCallbackResolver(
        execution=Execution(),
        limit_projectors=EmbeddingLimitProjectorRegistry(
            (
                EmbeddingLimitProjectorBinding(
                    identity, lambda _descriptor: EmbeddingBatchLimits(1, 1, 1, 1, 1)
                ),
            )
        ),
    )
    descriptor = SealedArtifactRunnerDescriptor(
        "a" * 64,
        "asset.py",
        "b" * 64,
        "c" * 64,
        "d" * 64,
        (),
        (),
        SimpleNamespace(),
        (),
        (),
        (),
        (),
    )
    policy = SimpleNamespace(
        embedding_execution_binding=None,
        execution_descriptor=parse_execution_descriptor(
            {
                "format_version": 1,
                "architecture_abi": identity.to_mapping(),
                "material_roles": ["weights"],
                "abi_fields": {},
            }
        ),
        capability_requirements=None,
        selected_capability_provider_ids=(),
    )

    with pytest.raises(EmbeddingSealedArtifactCallbackError, match="unavailable"):
        resolver.resolve(descriptor, policy, object())
