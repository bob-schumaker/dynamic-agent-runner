"""Receiver-owned exact provider lookup for locked inference bindings."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from dynamic_agent_runner.workflow_host.capabilities import CapabilityContract
from dynamic_agent_runner.workflow_host.locked_inference import LockedInferenceBinding
from dynamic_agent_runner.workflow_host.locked_inference_execution import (
    LockedInferenceProvider,
)


class LockedInferenceProviderRegistryError(ValueError):
    """Raised when the preselected receiver provider is unavailable."""


@dataclass(frozen=True)
class LockedInferenceProviderBinding:
    """One receiver executable implementing one exact generation contract."""

    provider_id: str
    contract: CapabilityContract
    provider: LockedInferenceProvider


class LockedInferenceProviderRegistry:
    """Resolve only an earlier-selected private provider; never fall back."""

    def __init__(self, providers: Sequence[LockedInferenceProviderBinding]) -> None:
        bindings = tuple(providers)
        if (
            not bindings
            or any(
                not isinstance(item, LockedInferenceProviderBinding)
                for item in bindings
            )
            or len({item.provider_id for item in bindings}) != len(bindings)
        ):
            raise LockedInferenceProviderRegistryError(
                "inference provider is unavailable"
            )
        self._providers = {item.provider_id: item for item in bindings}

    def resolve(
        self, *, binding: LockedInferenceBinding, selected_provider_id: str
    ) -> LockedInferenceProvider:
        if not isinstance(selected_provider_id, str) or not selected_provider_id:
            raise LockedInferenceProviderRegistryError(
                "inference provider is unavailable"
            )
        provider = self._providers.get(selected_provider_id)
        if (
            provider is None
            or provider.contract.capability_id != "model.generate.v1"
            or provider.contract.contract_version
            != getattr(binding, "capability_contract_version", None)
            or provider.contract.contract_digest
            != getattr(binding, "capability_contract_digest", None)
        ):
            raise LockedInferenceProviderRegistryError(
                "inference provider is unavailable"
            )
        return provider.provider
