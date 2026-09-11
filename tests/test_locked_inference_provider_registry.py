from __future__ import annotations

import pytest
from types import SimpleNamespace

from dynamic_agent_runner.workflow_host.capabilities import CapabilityContract
from dynamic_agent_runner.workflow_host.locked_inference_provider_registry import (
    LockedInferenceProviderBinding,
    LockedInferenceProviderRegistry,
    LockedInferenceProviderRegistryError,
)


def test_registry_does_not_fallback_when_selected_provider_is_missing() -> None:
    registry = LockedInferenceProviderRegistry(
        (
            LockedInferenceProviderBinding(
                "selected",
                CapabilityContract("model.generate.v1", "1", "a" * 64, ()),
                object(),  # type: ignore[arg-type]
            ),
        )
    )
    with pytest.raises(LockedInferenceProviderRegistryError):
        registry.resolve(binding=object(), selected_provider_id="missing")  # type: ignore[arg-type]


def test_registry_rejects_a_selected_provider_with_the_wrong_contract() -> None:
    registry = LockedInferenceProviderRegistry(
        (
            LockedInferenceProviderBinding(
                "selected",
                CapabilityContract("model.generate.v1", "1", "a" * 64, ()),
                object(),  # type: ignore[arg-type]
            ),
        )
    )

    with pytest.raises(LockedInferenceProviderRegistryError, match="unavailable"):
        registry.resolve(
            binding=SimpleNamespace(
                capability_contract_version="1", capability_contract_digest="b" * 64
            ),
            selected_provider_id="selected",
        )
