"""Receiver-owned JSON bridge for one sealed embedding callback."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Protocol

from dynamic_agent_runner.workflow_host.embedding_execution import (
    EmbeddingBatchLimits,
    EmbeddingExecutionBinding,
    EmbeddingTextItem,
    EmbeddingLimitProjectorRegistry,
)
from dynamic_agent_runner.workflow_host.capabilities import (
    selected_provider_id_for_requirement,
)
from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactCallback,
    SealedArtifactRunnerDescriptor,
)


class EmbeddingSealedArtifactCallbackError(ValueError):
    """Raised without exposing embedding requests, vectors, or provider detail."""


class _EmbeddingExecution(Protocol):
    def execute(
        self,
        *,
        binding: EmbeddingExecutionBinding,
        selected_provider_ids: Sequence[str],
        package_limits: EmbeddingBatchLimits,
        items: Sequence[EmbeddingTextItem],
    ) -> tuple[object, ...]: ...


class EmbeddingSealedArtifactCallbackProvider:
    """Translate one fixed sealed JSON callback to host-owned embedding execution."""

    def __init__(
        self,
        *,
        callback: SealedArtifactCallback,
        execution: _EmbeddingExecution,
        binding: EmbeddingExecutionBinding,
        selected_provider_ids: Sequence[str],
        limits: EmbeddingBatchLimits,
    ) -> None:
        if (
            callback.requirement != "embedding.execute.v1"
            or not callable(getattr(execution, "execute", None))
            or not selected_provider_ids
        ):
            raise EmbeddingSealedArtifactCallbackError(
                "embedding callback is unavailable"
            )
        self._callback = callback
        self._execution = execution
        self._binding = binding
        self._selected_provider_ids = tuple(selected_provider_ids)
        self._limits = limits

    def revalidate(self, callback: SealedArtifactCallback) -> None:
        if callback != self._callback:
            raise EmbeddingSealedArtifactCallbackError(
                "embedding callback is unavailable"
            )

    def invoke(self, name: str, request: bytes) -> bytes:
        if name != self._callback.name:
            raise EmbeddingSealedArtifactCallbackError(
                "embedding callback is unavailable"
            )
        try:
            value = json.loads(request.decode("utf-8"), object_pairs_hook=_unique)
            if not isinstance(value, Mapping) or set(value) != {"items"}:
                raise ValueError
            if (
                json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
                != request
            ):
                raise ValueError
            items = tuple(
                EmbeddingTextItem(item["id"], item["text"])
                for item in value["items"]
                if isinstance(item, Mapping) and set(item) == {"id", "text"}
            )
            if len(items) != len(value["items"]):
                raise ValueError
            vectors = self._execution.execute(
                binding=self._binding,
                selected_provider_ids=self._selected_provider_ids,
                package_limits=self._limits,
                items=items,
            )
            response = {
                "items": [
                    {"id": item.item_id, "vector": list(item.values)}
                    for item in vectors
                ]
            }
            return json.dumps(response, separators=(",", ":"), sort_keys=True).encode()
        except Exception as error:  # noqa: BLE001 - redacted callback boundary.
            raise EmbeddingSealedArtifactCallbackError(
                "embedding callback is unavailable"
            ) from error


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value = dict(pairs)
    if len(value) != len(pairs):
        raise ValueError
    return value


class EmbeddingSealedArtifactCallbackResolver:
    """Resolve only the exact embedding callback already admitted by policy."""

    def __init__(
        self,
        *,
        execution: _EmbeddingExecution,
        limit_projectors: EmbeddingLimitProjectorRegistry,
    ) -> None:
        self._execution = execution
        self._limit_projectors = limit_projectors

    def resolve(
        self,
        descriptor: SealedArtifactRunnerDescriptor,
        policy: object,
        _revision: object,
    ) -> EmbeddingSealedArtifactCallbackProvider:
        try:
            binding = policy.embedding_execution_binding
            execution_descriptor = policy.execution_descriptor
            requirements = policy.capability_requirements
            selected = tuple(policy.selected_capability_provider_ids)
            callbacks = [
                callback
                for callback in descriptor.callbacks
                if callback.requirement == "embedding.execute.v1"
            ]
            if (
                not isinstance(binding, EmbeddingExecutionBinding)
                or len(callbacks) != 1
            ):
                raise ValueError
            selected_provider_id_for_requirement(
                requirements=requirements,
                selected_provider_ids=selected,
                capability_id="embedding.execute.v1",
            )
            limits = self._limit_projectors.project(execution_descriptor)
            return EmbeddingSealedArtifactCallbackProvider(
                callback=callbacks[0],
                execution=self._execution,
                binding=binding,
                selected_provider_ids=selected,
                limits=limits,
            )
        except Exception as error:  # noqa: BLE001 - redacted receiver boundary.
            raise EmbeddingSealedArtifactCallbackError(
                "embedding callback is unavailable"
            ) from error
