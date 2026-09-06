"""Sealed local-principal workflow inputs for registered no-tool workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Mapping, Protocol, Sequence, runtime_checkable

from dynamic_agent_runner.workflow_host.catalog import (
    PackageCatalog,
    PackageCatalogError,
)
from dynamic_agent_runner.workflow_host.policy import (
    PolicyCompilationError,
    compile_workflow_policy,
)
from dynamic_agent_runner.workflow_host.profiles import InstallationIdentityProvider
from dynamic_agent_runner.workflow_host.registration import (
    WorkflowRegistration,
    WorkflowRegistrationError,
    WorkflowRegistrationService,
)
from dynamic_agent_runner.workflow_host.state import (
    OpaqueRecordError,
    PrivateStateStore,
)
from dynamic_agent_runner.workflow_host.workspace_ingress import (
    MaterializedWorkspaceBinaryArtifact,
    MaterializedWorkspaceImageArtifact,
    MaterializedWorkspaceInputArtifact,
)


class PreparedWorkflowInputError(ValueError):
    """Raised when a workflow input is not sealed for its exact registration."""


class WorkspaceArtifactVerifier(Protocol):
    """Private control-plane verifier for one opaque workspace artifact."""

    def load(
        self,
        artifact_id: str,
        *,
        workflow_id: str,
        registration_digest: str,
        now: datetime,
    ) -> object: ...


@runtime_checkable
class WorkspaceArtifactMaterializer(WorkspaceArtifactVerifier, Protocol):
    """Private verifier that can provide hash-checked text only to a handler."""

    def materialize(
        self,
        artifact_id: str,
        *,
        workflow_id: str,
        registration_digest: str,
        now: datetime,
    ) -> MaterializedWorkspaceInputArtifact: ...


@runtime_checkable
class WorkspaceArtifactImageMaterializer(WorkspaceArtifactVerifier, Protocol):
    """Private verifier that exposes sealed image bytes only to a vision adapter."""

    def materialize_image(
        self,
        artifact_id: str,
        *,
        workflow_id: str,
        registration_digest: str,
        now: datetime,
    ) -> MaterializedWorkspaceImageArtifact: ...


@runtime_checkable
class WorkspaceArtifactBinaryMaterializer(WorkspaceArtifactVerifier, Protocol):
    """Private verifier that exposes sealed bytes only to a host-local tool."""

    def materialize_binary(
        self,
        artifact_id: str,
        *,
        workflow_id: str,
        registration_digest: str,
        now: datetime,
    ) -> MaterializedWorkspaceBinaryArtifact: ...


@dataclass(frozen=True)
class PreparedWorkflowInput:
    """Public opaque input reference returned by trusted local preparation."""

    prepared_input_id: str
    workflow_id: str
    registration_digest: str
    expires_at: datetime


@dataclass(frozen=True)
class SealedWorkflowInput:
    """Private input material available only after registration-bound verification."""

    prompt: str
    structured_input: dict[str, str]
    additional_context: str
    workspace_artifact_ids: tuple[str, ...]


class WorkflowInvocationPreparationService:
    """The sole issuer and verifier of no-tool prepared workflow inputs."""

    def __init__(
        self,
        *,
        registrations: WorkflowRegistrationService,
        catalog: PackageCatalog,
        store: PrivateStateStore,
        artifact_verifier: WorkspaceArtifactVerifier | None = None,
    ) -> None:
        self._registrations = registrations
        self._catalog = catalog
        self._store = store
        self._artifact_verifier = artifact_verifier
        self._identity = InstallationIdentityProvider()

    def prepare(
        self,
        *,
        workflow_id: str,
        prompt: str,
        additional_context: str = "",
        structured_input: Mapping[str, str] | None = None,
        workspace_artifact_ids: Sequence[str] = (),
        now: datetime,
    ) -> PreparedWorkflowInput:
        """Seal valid prompt/context input for one already registered workflow."""

        if not isinstance(prompt, str) or not prompt:
            raise PreparedWorkflowInputError("prompt must be a non-empty string")
        if not isinstance(additional_context, str):
            raise PreparedWorkflowInputError("additional_context must be a string")
        if structured_input:
            raise PreparedWorkflowInputError(
                "structured input is unavailable for this no-tool workflow"
            )
        registration, policy = self._registration_policy(workflow_id)
        artifact_ids = _artifact_ids(workspace_artifact_ids)
        self._verify_artifacts(artifact_ids, registration=registration, now=now)
        if (
            len(additional_context.encode("utf-8"))
            > policy.input_contract.additional_context_max_bytes
        ):
            raise PreparedWorkflowInputError(
                "additional_context exceeds its declared limit"
            )
        expires_at = now.astimezone(UTC) + timedelta(minutes=5)
        try:
            prepared_input_id = self._store.issue(
                kind="prepared_workflow_input",
                owner=self._identity.principal,
                payload={
                    "workflow_id": registration.workflow_id,
                    "registration_digest": registration.registration_digest,
                    "prompt": prompt,
                    "structured_input": {},
                    "additional_context": additional_context,
                    "workspace_artifact_ids": list(artifact_ids),
                },
                expires_at=expires_at,
                now=now,
            )
        except OpaqueRecordError as error:
            raise PreparedWorkflowInputError(
                "prepared input could not be sealed"
            ) from error
        return PreparedWorkflowInput(
            prepared_input_id,
            registration.workflow_id,
            registration.registration_digest,
            expires_at,
        )

    def load(
        self,
        prepared_input_id: str,
        *,
        registration: WorkflowRegistration,
        now: datetime,
    ) -> SealedWorkflowInput:
        """Resolve sealed input only for its exact registered workflow binding."""

        try:
            record = self._store.load(
                prepared_input_id,
                expected_kind="prepared_workflow_input",
                owner=self._identity.principal,
                now=now,
            )
        except OpaqueRecordError as error:
            if "expired" in str(error):
                raise PreparedWorkflowInputError(
                    "prepared input has expired"
                ) from error
            raise PreparedWorkflowInputError("prepared input is invalid") from error
        payload = record.payload
        if (
            payload.get("workflow_id") != registration.workflow_id
            or payload.get("registration_digest") != registration.registration_digest
        ):
            raise PreparedWorkflowInputError(
                "prepared input does not match registration"
            )
        return _sealed_input(payload)

    def consume(
        self,
        prepared_input_id: str,
        *,
        registration: WorkflowRegistration,
        now: datetime,
    ) -> SealedWorkflowInput:
        """Atomically spend a verified default single-use input before a run."""

        sealed = self.load(prepared_input_id, registration=registration, now=now)
        try:
            self._store.consume(
                prepared_input_id,
                expected_kind="prepared_workflow_input",
                owner=self._identity.principal,
                now=now,
            )
        except OpaqueRecordError as error:
            raise PreparedWorkflowInputError("prepared input is unavailable") from error
        return sealed

    def materialize_workspace_artifacts(
        self,
        sealed: SealedWorkflowInput,
        *,
        registration: WorkflowRegistration,
        now: datetime,
    ) -> tuple[MaterializedWorkspaceInputArtifact, ...]:
        """Resolve sealed artifacts into private hash-verified handler values."""

        if not sealed.workspace_artifact_ids:
            return ()
        materializer = self._artifact_verifier
        if not isinstance(materializer, WorkspaceArtifactMaterializer):
            raise PreparedWorkflowInputError(
                "workspace artifact materialization is unavailable"
            )
        try:
            artifacts = tuple(
                materializer.materialize(
                    artifact_id,
                    workflow_id=registration.workflow_id,
                    registration_digest=registration.registration_digest,
                    now=now,
                )
                for artifact_id in sealed.workspace_artifact_ids
            )
        except Exception as error:
            raise PreparedWorkflowInputError(
                "workspace artifact materialization is unavailable"
            ) from error
        if len({artifact.role for artifact in artifacts}) != len(artifacts):
            raise PreparedWorkflowInputError("workspace artifact roles are ambiguous")
        return artifacts

    def materialize_workspace_images(
        self,
        sealed: SealedWorkflowInput,
        *,
        registration: WorkflowRegistration,
        now: datetime,
    ) -> tuple[MaterializedWorkspaceImageArtifact, ...]:
        """Resolve sealed image artifacts for the selected vision adapter only."""

        if not sealed.workspace_artifact_ids:
            return ()
        materializer = self._artifact_verifier
        if not isinstance(materializer, WorkspaceArtifactImageMaterializer):
            raise PreparedWorkflowInputError(
                "workspace image materialization is unavailable"
            )
        try:
            images = tuple(
                materializer.materialize_image(
                    artifact_id,
                    workflow_id=registration.workflow_id,
                    registration_digest=registration.registration_digest,
                    now=now,
                )
                for artifact_id in sealed.workspace_artifact_ids
            )
        except Exception as error:
            raise PreparedWorkflowInputError(
                "workspace image materialization is unavailable"
            ) from error
        if len({image.role for image in images}) != len(images):
            raise PreparedWorkflowInputError("workspace artifact roles are ambiguous")
        return images

    def materialize_workspace_binaries(
        self,
        sealed: SealedWorkflowInput,
        *,
        registration: WorkflowRegistration,
        now: datetime,
    ) -> tuple[MaterializedWorkspaceBinaryArtifact, ...]:
        """Resolve sealed binary artifacts only for host-local tool bindings."""

        if not sealed.workspace_artifact_ids:
            return ()
        materializer = self._artifact_verifier
        if not isinstance(materializer, WorkspaceArtifactBinaryMaterializer):
            raise PreparedWorkflowInputError(
                "workspace binary materialization is unavailable"
            )
        try:
            binaries = tuple(
                materializer.materialize_binary(
                    artifact_id,
                    workflow_id=registration.workflow_id,
                    registration_digest=registration.registration_digest,
                    now=now,
                )
                for artifact_id in sealed.workspace_artifact_ids
            )
        except Exception as error:
            raise PreparedWorkflowInputError(
                "workspace binary materialization is unavailable"
            ) from error
        if len({binary.role for binary in binaries}) != len(binaries):
            raise PreparedWorkflowInputError("workspace artifact roles are ambiguous")
        return binaries

    def _registration_policy(self, workflow_id: str):
        try:
            registration = self._registrations.resolve(workflow_id)
            revision = self._catalog.revision(
                registration.package_id, registration.revision_digest
            )
            policy = compile_workflow_policy(revision)
        except (
            WorkflowRegistrationError,
            PackageCatalogError,
            PolicyCompilationError,
        ) as error:
            raise PreparedWorkflowInputError(
                "workflow registration is unavailable"
            ) from error
        if policy.policy_digest != registration.policy_digest:
            raise PreparedWorkflowInputError(
                "workflow registration policy does not match"
            )
        return registration, policy

    def _verify_artifacts(
        self,
        artifact_ids: tuple[str, ...],
        *,
        registration: WorkflowRegistration,
        now: datetime,
    ) -> None:
        if not artifact_ids:
            return
        if self._artifact_verifier is None:
            raise PreparedWorkflowInputError(
                "workspace artifact verification is unavailable"
            )
        try:
            for artifact_id in artifact_ids:
                self._artifact_verifier.load(
                    artifact_id,
                    workflow_id=registration.workflow_id,
                    registration_digest=registration.registration_digest,
                    now=now,
                )
        except Exception as error:
            raise PreparedWorkflowInputError(
                "workspace artifact is unavailable"
            ) from error


def _sealed_input(payload: Mapping[str, object]) -> SealedWorkflowInput:
    prompt = payload.get("prompt")
    additional_context = payload.get("additional_context")
    structured_input = payload.get("structured_input")
    workspace_artifact_ids = payload.get("workspace_artifact_ids")
    if (
        not isinstance(prompt, str)
        or not isinstance(additional_context, str)
        or not isinstance(structured_input, dict)
        or structured_input
        or not isinstance(workspace_artifact_ids, list)
        or _artifact_ids(workspace_artifact_ids) != tuple(workspace_artifact_ids)
    ):
        raise PreparedWorkflowInputError("prepared input is invalid")
    return SealedWorkflowInput(
        prompt, {}, additional_context, tuple(workspace_artifact_ids)
    )


def _artifact_ids(value: Sequence[object]) -> tuple[str, ...]:
    if isinstance(value, str) or len(value) > 16:
        raise PreparedWorkflowInputError("workspace artifact identifiers are invalid")
    artifact_ids = tuple(value)
    if any(
        not isinstance(artifact_id, str) or not artifact_id
        for artifact_id in artifact_ids
    ) or len(set(artifact_ids)) != len(artifact_ids):
        raise PreparedWorkflowInputError("workspace artifact identifiers are invalid")
    return artifact_ids
