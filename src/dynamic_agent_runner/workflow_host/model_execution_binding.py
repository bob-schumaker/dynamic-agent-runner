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
from dynamic_agent_runner.workflow_host.execution_descriptors import (
    ExecutionDescriptor,
    ExecutionDescriptorError,
    ExecutionDescriptorValidatorRegistry,
)
from dynamic_agent_runner.workflow_host.model_materials import ModelDependencyLock


class ModelExecutionBindingError(ValueError):
    """Raised with a redacted model-execution admission classification."""


@dataclass(frozen=True)
class ModelExecutionBinding:
    logical_model_id: str
    runner_contract_id: str
    runner_contract_version: str
    loader_profile_contract_id: str | None
    loader_profile_contract_version: str | None
    material_lock_digest: str
    capability_requirements_digest: str
    runner_capability_id: str
    runner_capability_version: str
    runner_capability_digest: str
    converter_capability_id: str | None = None
    execution_descriptor_digest: str | None = None
    execution_abi_id: str | None = None
    execution_abi_version: str | None = None
    execution_abi_contract_digest: str | None = None

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
    supported_execution_abis: tuple[tuple[str, str, str], ...] = ()


def derive_model_execution_binding(
    *,
    lock: ModelDependencyLock,
    requirements: CapabilityRequirements,
    converter_capability_id: str | None = None,
    execution_descriptor: ExecutionDescriptor | None = None,
    descriptor_validators: ExecutionDescriptorValidatorRegistry | None = None,
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
    descriptor_identity = _validate_execution_descriptor(
        lock, execution_descriptor, descriptor_validators
    )
    loader_profile = lock.loader_profile_contract
    return ModelExecutionBinding(
        lock.logical_model_id,
        lock.runner_contract.contract_id,
        lock.runner_contract.version,
        loader_profile.contract_id if loader_profile is not None else None,
        loader_profile.version if loader_profile is not None else None,
        lock.digest,
        requirements.digest,
        runner_id,
        runner_requirement.contract_version,
        runner_requirement.contract_digest,
        converter_capability_id,
        *descriptor_identity,
    )


class ModelRunnerRegistry:
    """Receiver-owned exact runner resolution with no fallback."""

    def __init__(self, providers: Sequence[ModelRunnerProvider]) -> None:
        self._providers = tuple(providers)

    def resolve(self, binding: ModelExecutionBinding) -> ModelRunnerProvider:
        if binding.execution_abi_id is not None:
            return self._resolve_execution_abi(binding)
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

    def _resolve_execution_abi(
        self, binding: ModelExecutionBinding
    ) -> ModelRunnerProvider:
        abi = (
            binding.execution_abi_id,
            binding.execution_abi_version,
            binding.execution_abi_contract_digest,
        )
        for provider in self._providers:
            if (
                provider.contract.capability_id == binding.runner_capability_id
                and provider.contract.contract_version
                == binding.runner_capability_version
                and provider.contract.contract_digest
                == binding.runner_capability_digest
                and abi in provider.supported_execution_abis
            ):
                return provider
        raise ModelExecutionBindingError("runner_unavailable")


def _validate_execution_descriptor(
    lock: ModelDependencyLock,
    descriptor: ExecutionDescriptor | None,
    validators: ExecutionDescriptorValidatorRegistry | None,
) -> tuple[str | None, str | None, str | None, str | None]:
    if lock.format_version == 1:
        if descriptor is not None or validators is not None:
            raise ModelExecutionBindingError("runner_unavailable")
        return None, None, None, None
    if descriptor is None or validators is None or lock.execution_descriptor is None:
        raise ModelExecutionBindingError("runner_unavailable")
    if lock.execution_descriptor.sha256 != descriptor.digest:
        raise ModelExecutionBindingError("runner_unavailable")
    if any(
        role not in {source.role for source in lock.sources}
        for role in descriptor.material_roles
    ):
        raise ModelExecutionBindingError("runner_unavailable")
    try:
        validators.validate(descriptor)
    except ExecutionDescriptorError as error:
        raise ModelExecutionBindingError("runner_unavailable") from error
    return (
        descriptor.digest,
        descriptor.architecture_abi.abi_id,
        descriptor.architecture_abi.version,
        descriptor.architecture_abi.contract_digest,
    )
