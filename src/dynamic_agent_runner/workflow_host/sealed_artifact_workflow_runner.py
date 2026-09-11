"""Concrete host composition for sealed-artifact workflow invocations."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

from dynamic_agent_runner.workflow_host.capabilities import CapabilityCatalog
from dynamic_agent_runner.workflow_host.catalog import PackageCatalog
from dynamic_agent_runner.workflow_host.policy import compile_workflow_policy
from dynamic_agent_runner.workflow_host.profiles import InstallationIdentityProvider
from dynamic_agent_runner.workflow_host.registration import WorkflowRegistrationService
from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactAssetRuntime,
    SealedArtifactCallbackProvider,
    SealedArtifactExecutionContext,
    SealedArtifactHandleError,
    SealedArtifactHandleService,
    SealedArtifactOutputCollector,
    SealedArtifactOutputHandle,
    SealedArtifactOutputHandleService,
    SealedArtifactRunnerAdmissionError,
    SealedArtifactRunnerDescriptor,
    validate_sealed_artifact_runner_capabilities,
    verify_sealed_artifact_runner_files,
)


class SealedArtifactCallbackResolver(Protocol):
    """Resolve the already selected private callback provider for one policy."""

    def resolve(
        self,
        descriptor: SealedArtifactRunnerDescriptor,
        policy: object,
        revision: object,
    ) -> SealedArtifactCallbackProvider: ...


class _Identity(Protocol):
    @property
    def principal(self) -> str: ...


@dataclass(frozen=True)
class SealedArtifactInvocation:
    """Opaque handles and stable identities supplied to one receiver run."""

    workflow_id: str
    invocation_id: str
    input_handles: Mapping[str, str]


@dataclass(frozen=True)
class SealedArtifactInvocationResult:
    """Only opaque output handles and a redacted execution receipt leave DAR."""

    outputs: tuple[SealedArtifactOutputHandle, ...]
    receipt: Mapping[str, int | str]


class SealedArtifactWorkflowRunner:
    """Compose registered package, handle, callback, runtime, and egress services."""

    def __init__(
        self,
        *,
        registrations: WorkflowRegistrationService,
        catalog: PackageCatalog,
        handles: SealedArtifactHandleService,
        outputs: SealedArtifactOutputHandleService,
        callback_resolver: SealedArtifactCallbackResolver,
        capability_catalog: CapabilityCatalog | None = None,
        identity: _Identity | None = None,
        output_ttl: timedelta,
    ) -> None:
        principal = (identity or InstallationIdentityProvider()).principal
        if (
            not isinstance(handles, SealedArtifactHandleService)
            or handles.owner != principal
            or not isinstance(outputs, SealedArtifactOutputHandleService)
            or outputs.owner != principal
            or output_ttl <= timedelta()
            or not callable(getattr(callback_resolver, "resolve", None))
        ):
            raise SealedArtifactRunnerAdmissionError(
                "sealed artifact runner is unavailable"
            )
        self._registrations = registrations
        self._catalog = catalog
        self._handles = handles
        self._outputs = outputs
        self._callback_resolver = callback_resolver
        self._capability_catalog = capability_catalog
        self._principal = principal
        self._output_ttl = output_ttl

    def run(
        self, invocation: SealedArtifactInvocation, *, now: datetime
    ) -> SealedArtifactInvocationResult:
        """Run only one registered local package through the fixed receiver order."""

        reserved: list[str] = []
        consumed: set[str] = set()
        try:
            (
                registration,
                revision,
                descriptor,
                callback_provider,
                declared,
                supplied,
            ) = self._admit(invocation)
            for role, item in declared.items():
                handle_id = supplied.get(role)
                if handle_id is None:
                    continue
                self._handles.reserve(
                    handle_id,
                    receiver_id=self._principal,
                    revision_digest=registration.revision_digest,
                    invocation_id=invocation.invocation_id,
                    role=role,
                    media_type=item.media_type,
                    schema_digest=item.schema_digest,
                    now=now,
                )
                reserved.append(handle_id)
            collector = SealedArtifactOutputCollector(descriptor=descriptor)

            def read_input(role: str) -> bytes:
                item = declared.get(role)
                handle_id = supplied.get(role)
                if item is None or handle_id is None:
                    raise SealedArtifactHandleError("artifact handle is unavailable")
                content = self._handles.consume(
                    handle_id,
                    receiver_id=self._principal,
                    revision_digest=registration.revision_digest,
                    invocation_id=invocation.invocation_id,
                    role=role,
                    media_type=item.media_type,
                    schema_digest=item.schema_digest,
                    now=now,
                )
                consumed.add(handle_id)
                return content

            asset = _asset_bytes(revision.package_root, descriptor)
            runtime = SealedArtifactAssetRuntime()
            sealed = runtime.execute(
                asset=asset,
                context=SealedArtifactExecutionContext(
                    descriptor=descriptor,
                    read_input=read_input,
                    callback_provider=callback_provider,
                    collector=collector,
                ),
            )
            outputs = self._outputs.publish(
                descriptor=descriptor,
                receiver_id=self._principal,
                revision_digest=registration.revision_digest,
                invocation_id=invocation.invocation_id,
                sealed=sealed,
                expires_at=now + self._output_ttl,
                now=now,
            )
            return SealedArtifactInvocationResult(outputs, runtime.receipts()[-1])
        except Exception as error:
            raise SealedArtifactRunnerAdmissionError(
                "sealed artifact runner is unavailable"
            ) from error
        finally:
            for handle_id in reserved:
                if handle_id in consumed:
                    continue
                try:
                    self._handles.revoke(handle_id, now=now)
                except SealedArtifactHandleError:
                    pass

    def _admit(self, invocation: SealedArtifactInvocation):
        registration = self._registrations.resolve(invocation.workflow_id)
        if getattr(registration, "owner", None) != self._principal:
            raise SealedArtifactRunnerAdmissionError(
                "sealed artifact runner is unavailable"
            )
        revision = self._catalog.revision(
            registration.package_id, registration.revision_digest
        )
        policy = compile_workflow_policy(
            revision, capability_catalog=self._capability_catalog
        )
        if policy.policy_digest != registration.policy_digest or tuple(
            getattr(registration, "selected_capability_provider_ids", ())
        ) != tuple(getattr(policy, "selected_capability_provider_ids", ())):
            raise SealedArtifactRunnerAdmissionError(
                "sealed artifact runner is unavailable"
            )
        descriptor = verify_sealed_artifact_runner_files(
            revision.package_root,
            (revision.package_root / "sealed-artifact-runner.json").read_bytes(),
        )
        validate_sealed_artifact_runner_capabilities(
            descriptor, policy.capability_requirements
        )
        if (
            revision.trust != "human_selected_local"
            or descriptor.profile_digest != registration.profile_digest
        ):
            raise SealedArtifactRunnerAdmissionError(
                "sealed artifact runner is unavailable"
            )
        callback_provider = self._callback_resolver.resolve(
            descriptor, policy, revision
        )
        declared = {item.role: item for item in descriptor.inputs}
        supplied = dict(invocation.input_handles)
        if (
            not isinstance(invocation.workflow_id, str)
            or not invocation.workflow_id
            or not isinstance(invocation.invocation_id, str)
            or not invocation.invocation_id
            or not set(supplied) <= set(declared)
            or any(
                not isinstance(handle, str) or not handle
                for handle in supplied.values()
            )
            or any(
                item.required and item.role not in supplied
                for item in declared.values()
            )
        ):
            raise SealedArtifactRunnerAdmissionError(
                "sealed artifact runner is unavailable"
            )
        return registration, revision, descriptor, callback_provider, declared, supplied


def _asset_bytes(root: Path, descriptor: SealedArtifactRunnerDescriptor) -> bytes:
    try:
        content = (root / descriptor.asset_path).read_bytes()
    except OSError as error:
        raise SealedArtifactRunnerAdmissionError(
            "sealed artifact runner is unavailable"
        ) from error
    if hashlib.sha256(content).hexdigest() != descriptor.asset_digest:
        raise SealedArtifactRunnerAdmissionError(
            "sealed artifact runner is unavailable"
        )
    return content
