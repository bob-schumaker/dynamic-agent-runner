"""Receiver-owned exact provider lookup for locked inference bindings."""

from __future__ import annotations

from collections.abc import Mapping

from dynamic_agent_runner.workflow_host.locked_inference import LockedInferenceBinding
from dynamic_agent_runner.workflow_host.locked_inference_execution import (
    LockedInferenceProvider,
)


class LockedInferenceProviderRegistryError(ValueError):
    """Raised when the preselected receiver provider is unavailable."""


class LockedInferenceProviderRegistry:
    """Resolve only an earlier-selected private provider; never fall back."""

    def __init__(self, providers: Mapping[str, LockedInferenceProvider]) -> None:
        self._providers = dict(providers)

    def resolve(
        self, *, binding: LockedInferenceBinding, selected_provider_id: str
    ) -> LockedInferenceProvider:
        if not isinstance(selected_provider_id, str) or not selected_provider_id:
            raise LockedInferenceProviderRegistryError(
                "inference provider is unavailable"
            )
        provider = self._providers.get(selected_provider_id)
        if provider is None:
            raise LockedInferenceProviderRegistryError(
                "inference provider is unavailable"
            )
        return provider
