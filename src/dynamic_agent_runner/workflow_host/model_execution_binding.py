"""Sealed generic model-execution binding and exact runner lookup."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Sequence

from dynamic_agent_runner.workflow_host.capabilities import (
    CapabilityContract,
    CapabilityRequirements,
)
from dynamic_agent_runner.workflow_host.model_materials import ModelDependencyLock


class ModelExecutionBindingError(ValueError):
    """Raised with a redacted model-execution admission classification."""


@dataclass(frozen=True)
class ModelExecutionBinding:
    logical_model_id: str
    runner_contract_id: str
    runner_contract_version: str
    loader_profile_contract_id: str
    loader_profile_contract_version: str
    material_lock_digest: str
    capability_requirements_digest: str
    runner_capability_id: str
    runner_capability_version: str
    runner_capability_digest: str
    converter_capability_id: str | None = None

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(self.__dict__, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


@dataclass(frozen=True)
class ModelRunnerProvider:
    provider_id: str
    contract: CapabilityContract
    supported_profiles: tuple[tuple[str, str, str, str], ...]


def derive_model_execution_binding(
    *,
    lock: ModelDependencyLock,
    requirements: CapabilityRequirements,
    converter_capability_id: str | None = None,
) -> ModelExecutionBinding:
    """Derive one package-independent binding from sealed contracts only."""
    runner_id = requirements.bindings.get("runner")
    if not isinstance(runner_id, str):
        raise ModelExecutionBindingError("runner_unavailable")
    runner_requirement = next(
        (
            item
            for item in requirements.required_capabilities
            if item.capability_id == runner_id
        ),
        None,
    )
    if runner_requirement is None:
        raise ModelExecutionBindingError("runner_unavailable")
    if (
        converter_capability_id is not None
        and requirements.bindings.get("converter") != converter_capability_id
    ):
        raise ModelExecutionBindingError("converter_unavailable")
    return ModelExecutionBinding(
        lock.logical_model_id,
        lock.runner_contract.contract_id,
        lock.runner_contract.version,
        lock.loader_profile_contract.contract_id,
        lock.loader_profile_contract.version,
        lock.digest,
        requirements.digest,
        runner_id,
        runner_requirement.contract_version,
        runner_requirement.contract_digest,
        converter_capability_id,
    )


class ModelRunnerRegistry:
    """Receiver-owned exact runner resolution with no fallback."""

    def __init__(self, providers: Sequence[ModelRunnerProvider]) -> None:
        self._providers = tuple(providers)

    def resolve(self, binding: ModelExecutionBinding) -> ModelRunnerProvider:
        profile = (
            binding.runner_contract_id,
            binding.runner_contract_version,
            binding.loader_profile_contract_id,
            binding.loader_profile_contract_version,
        )
        for provider in self._providers:
            if (
                provider.contract.capability_id == binding.runner_capability_id
                and provider.contract.contract_version
                == binding.runner_capability_version
                and provider.contract.contract_digest
                == binding.runner_capability_digest
                and profile in provider.supported_profiles
            ):
                return provider
        raise ModelExecutionBindingError("runner_unavailable")
