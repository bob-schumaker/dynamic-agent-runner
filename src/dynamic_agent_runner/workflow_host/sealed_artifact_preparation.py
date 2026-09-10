"""Registered-package input preparation for sealed artifact workflows."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Protocol

from dynamic_agent_runner.workflow_host.profiles import InstallationIdentityProvider
from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactHandle,
    SealedArtifactHandleError,
    SealedArtifactHandleService,
    verify_sealed_artifact_runner_files,
)


class _Registration(Protocol):
    package_id: str
    revision_digest: str
    profile_digest: str


class _Registrations(Protocol):
    def resolve(self, workflow_id: str) -> _Registration: ...


class _Revision(Protocol):
    package_root: Path


class _Catalog(Protocol):
    def revision(self, package_id: str, revision_digest: str) -> _Revision: ...


class _Identity(Protocol):
    @property
    def principal(self) -> str: ...


class SealedArtifactInputPreparationService:
    """Seal input only after it is bound to one registered local package revision."""

    def __init__(
        self,
        *,
        registrations: _Registrations,
        catalog: _Catalog,
        handles: SealedArtifactHandleService,
        identity: _Identity | None = None,
    ) -> None:
        principal = (identity or InstallationIdentityProvider()).principal
        if (
            not isinstance(handles, SealedArtifactHandleService)
            or handles.owner != principal
        ):
            raise SealedArtifactHandleError(
                "artifact handle preparation is unavailable"
            )
        self._registrations = registrations
        self._catalog = catalog
        self._handles = handles
        self._principal = principal

    def prepare(
        self,
        *,
        workflow_id: str,
        receiver_id: str,
        invocation_id: str,
        role: str,
        media_type: str,
        schema_digest: str | None,
        content: bytes,
        expires_at: datetime,
        now: datetime,
    ) -> SealedArtifactHandle:
        """Verify package provenance and authorization before copying caller bytes."""

        try:
            registration = self._registrations.resolve(workflow_id)
            revision = self._catalog.revision(
                registration.package_id, registration.revision_digest
            )
            root = revision.package_root
            descriptor = verify_sealed_artifact_runner_files(
                root, (root / "sealed-artifact-runner.json").read_bytes()
            )
            if (
                receiver_id != self._principal
                or descriptor.profile_digest != registration.profile_digest
            ):
                raise SealedArtifactHandleError("artifact handle is invalid")
        except SealedArtifactHandleError:
            raise
        except Exception as error:
            raise SealedArtifactHandleError("artifact handle is unavailable") from error
        return self._handles.prepare(
            descriptor=descriptor,
            receiver_id=receiver_id,
            revision_digest=registration.revision_digest,
            invocation_id=invocation_id,
            role=role,
            media_type=media_type,
            schema_digest=schema_digest,
            content=content,
            expires_at=expires_at,
            now=now,
        )
