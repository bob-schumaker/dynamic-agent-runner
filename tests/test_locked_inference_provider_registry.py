from __future__ import annotations

import pytest

from dynamic_agent_runner.workflow_host.locked_inference_provider_registry import (
    LockedInferenceProviderRegistry,
    LockedInferenceProviderRegistryError,
)


def test_registry_does_not_fallback_when_selected_provider_is_missing() -> None:
    registry = LockedInferenceProviderRegistry({"selected": object()})  # type: ignore[arg-type]
    with pytest.raises(LockedInferenceProviderRegistryError):
        registry.resolve(binding=object(), selected_provider_id="missing")  # type: ignore[arg-type]
