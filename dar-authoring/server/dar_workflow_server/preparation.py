"""Sealed local-principal workflow inputs for registered no-tool workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Mapping

from dar_workflow_server.catalog import PackageCatalog, PackageCatalogError
from dar_workflow_server.policy import PolicyCompilationError, compile_workflow_policy
from dar_workflow_server.profiles import InstallationIdentityProvider
from dar_workflow_server.registration import (
    WorkflowRegistration,
    WorkflowRegistrationError,
    WorkflowRegistrationService,
)
from dar_workflow_server.state import OpaqueRecordError, PrivateStateStore


class PreparedWorkflowInputError(ValueError):
    """Raised when a workflow input is not sealed for its exact registration."""


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


class WorkflowInvocationPreparationService:
    """The sole issuer and verifier of no-tool prepared workflow inputs."""

    def __init__(
        self,
        *,
        registrations: WorkflowRegistrationService,
        catalog: PackageCatalog,
        store: PrivateStateStore,
    ) -> None:
        self._registrations = registrations
        self._catalog = catalog
        self._store = store
        self._identity = InstallationIdentityProvider()

    def prepare(
        self,
        *,
        workflow_id: str,
        prompt: str,
        additional_context: str = "",
        structured_input: Mapping[str, str] | None = None,
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


def _sealed_input(payload: Mapping[str, object]) -> SealedWorkflowInput:
    prompt = payload.get("prompt")
    additional_context = payload.get("additional_context")
    structured_input = payload.get("structured_input")
    if (
        not isinstance(prompt, str)
        or not isinstance(additional_context, str)
        or not isinstance(structured_input, dict)
        or structured_input
    ):
        raise PreparedWorkflowInputError("prepared input is invalid")
    return SealedWorkflowInput(prompt, {}, additional_context)
