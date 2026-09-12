"""Parent-only construction of typed generation-worker launch descriptors."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
from collections.abc import Mapping

from dynamic_agent_runner.local_model_preparation import PreparedArtifactSet
from dynamic_agent_runner.workflow_host.descriptor import DeclaredInputConverter
from dynamic_agent_runner.workflow_host.generation_resource_budgets import (
    GenerationResourceBudget,
    GenerationRunnerCapability,
)
from dynamic_agent_runner.workflow_host.generation_worker import (
    GenerationWorkerLaunchDescriptor,
    GenerationWorkerProtocolError,
)
from dynamic_agent_runner.workflow_host.generation_worker_assets import (
    GenerationWorkerAssetHandleError,
    GenerationWorkerAssetHandleService,
)


class GenerationWorkerCoLocatedFactory:
    """Bind typed host-private converter and material assets to one descriptor."""

    def __init__(
        self,
        *,
        capability: GenerationRunnerCapability,
        asset_handles: GenerationWorkerAssetHandleService,
        invocation_digest: str,
        fragment_index: int,
        converter: DeclaredInputConverter,
        package_root: Path,
        prepared_set: PreparedArtifactSet,
        messages: tuple[Mapping[str, object], ...],
        sealed_payload: bytes,
        sealed_payload_digest: str,
        material_lock_digest: str,
        execution_descriptor_digest: str,
        execution_device: str,
        budget: GenerationResourceBudget,
        expires_at: datetime,
        now: datetime,
    ) -> None:
        if (
            not isinstance(capability, GenerationRunnerCapability)
            or capability.worker_protocol != "generation-worker-v1"
            or not isinstance(asset_handles, GenerationWorkerAssetHandleService)
            or execution_device not in capability.supported_execution_devices
            or not isinstance(converter, DeclaredInputConverter)
            or not isinstance(package_root, Path)
            or not isinstance(prepared_set, PreparedArtifactSet)
            or not isinstance(sealed_payload, bytes)
            or not isinstance(budget, GenerationResourceBudget)
        ):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        try:
            provisional = GenerationWorkerLaunchDescriptor(
                protocol_version="generation-worker-v1",
                invocation_digest=invocation_digest,
                fragment_index=fragment_index,
                runner_id=capability.runner_id,
                capability_contract_digest=capability.contract_digest,
                converter_id=converter.converter_id,
                converter_asset_digest=converter.asset_digest,
                material_lock_digest=material_lock_digest,
                execution_descriptor_digest=execution_descriptor_digest,
                execution_device=execution_device,
                budget=budget,
                asset_handles=("pending-co-located-handle",),
            )
            handle = asset_handles.issue_co_located(
                descriptor=provisional,
                package_root=package_root,
                converter=converter,
                prepared_set=prepared_set,
                messages=messages,
                sealed_payload=sealed_payload,
                sealed_payload_digest=sealed_payload_digest,
                expires_at=expires_at,
                now=now,
            )
            self._descriptor = replace(provisional, asset_handles=(handle,))
        except (
            GenerationWorkerAssetHandleError,
            GenerationWorkerProtocolError,
            TypeError,
            ValueError,
        ) as error:
            raise GenerationWorkerProtocolError(
                "generation worker protocol invalid"
            ) from error
        self.runner_id = capability.runner_id
        self.capability = capability

    def create_launch_descriptor(self) -> GenerationWorkerLaunchDescriptor:
        """Return the sole typed child-facing artifact from this factory."""

        return self._descriptor


class GenerationWorkerCoLocatedFactoryBuilder:
    """Receiver-installed parent factory for one exact worker invocation."""

    def __init__(
        self,
        *,
        capability: GenerationRunnerCapability,
        asset_handles: GenerationWorkerAssetHandleService,
    ) -> None:
        if (
            not isinstance(capability, GenerationRunnerCapability)
            or capability.worker_protocol != "generation-worker-v1"
            or not isinstance(asset_handles, GenerationWorkerAssetHandleService)
        ):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        self.runner_id = capability.runner_id
        self.capability = capability
        self._asset_handles = asset_handles

    def create_for_invocation(
        self, **kwargs: object
    ) -> GenerationWorkerCoLocatedFactory:
        """Return an immutable factory with only this invocation's opaque assets."""

        try:
            return GenerationWorkerCoLocatedFactory(
                capability=self.capability,
                asset_handles=self._asset_handles,
                **kwargs,
            )
        except (GenerationWorkerProtocolError, TypeError) as error:
            raise GenerationWorkerProtocolError(
                "generation worker protocol invalid"
            ) from error
