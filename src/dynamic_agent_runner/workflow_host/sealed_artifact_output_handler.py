"""Host-owned orchestration for sealed artifact output publication."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactHandleError,
    SealedArtifactOutput,
    SealedArtifactOutputHandle,
    SealedArtifactOutputHandleService,
    SealedArtifactPrivateOutputSet,
)


_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class SealedArtifactOutputHandlerError(ValueError):
    """Stable, redacted error exposed by the output handler."""

    def __init__(self, classification: str) -> None:
        self.classification = classification
        super().__init__(classification)


class DeclarationResolver(Protocol):
    def __call__(
        self, workflow_id: str, package_id: str, descriptor_digest: str
    ) -> tuple[SealedArtifactOutput, ...] | None: ...


@dataclass(frozen=True)
class SealedArtifactOutputStageRequest:
    """Immutable, host-admitted candidates awaiting private staging."""

    receiver_id: str
    workflow_id: str
    package_id: str
    revision_digest: str
    invocation_id: str
    descriptor_digest: str
    outputs: tuple[tuple[str, str, bytes], ...]
    expires_at: datetime

    def __post_init__(self) -> None:
        for field_name in (
            "receiver_id",
            "workflow_id",
            "package_id",
            "invocation_id",
        ):
            _require_identifier(getattr(self, field_name))
        for field_name in ("revision_digest", "descriptor_digest"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
                raise SealedArtifactOutputHandlerError("output_invalid")
        if not isinstance(self.outputs, tuple) or not self.outputs:
            raise SealedArtifactOutputHandlerError("output_invalid")
        for candidate in self.outputs:
            if (
                not isinstance(candidate, tuple)
                or len(candidate) != 3
                or not isinstance(candidate[0], str)
                or not candidate[0]
                or not isinstance(candidate[1], str)
                or not candidate[1]
                or not isinstance(candidate[2], bytes)
            ):
                raise SealedArtifactOutputHandlerError("output_invalid")
        if (
            not isinstance(self.expires_at, datetime)
            or self.expires_at.tzinfo is None
            or self.expires_at.utcoffset() is None
        ):
            raise SealedArtifactOutputHandlerError("output_invalid")


@dataclass(frozen=True)
class SealedArtifactOutputReadBinding:
    """Immutable receiver binding required to read a public output handle."""

    receiver_id: str
    revision_digest: str
    invocation_id: str

    def __post_init__(self) -> None:
        _require_identifier(self.receiver_id)
        _require_identifier(self.invocation_id)
        if (
            not isinstance(self.revision_digest, str)
            or _DIGEST.fullmatch(self.revision_digest) is None
        ):
            raise SealedArtifactOutputHandlerError("output_invalid")


class SealedArtifactOutputHandler:
    """Coordinate deferred output publication over the existing service."""

    def __init__(
        self,
        *,
        service: SealedArtifactOutputHandleService,
        declaration_resolver: DeclarationResolver,
    ) -> None:
        if not isinstance(service, SealedArtifactOutputHandleService):
            raise SealedArtifactOutputHandlerError("output_unavailable")
        if not callable(declaration_resolver):
            raise SealedArtifactOutputHandlerError("output_invalid")
        self._service = service
        self._declaration_resolver = declaration_resolver

    @staticmethod
    def read_binding(
        receiver_id: str, revision_digest: str, invocation_id: str
    ) -> SealedArtifactOutputReadBinding:
        return SealedArtifactOutputReadBinding(
            receiver_id=receiver_id,
            revision_digest=revision_digest,
            invocation_id=invocation_id,
        )

    def stage_declared(
        self,
        request: SealedArtifactOutputStageRequest,
        *,
        now: datetime,
    ) -> SealedArtifactPrivateOutputSet:
        if not isinstance(request, SealedArtifactOutputStageRequest):
            raise SealedArtifactOutputHandlerError("output_invalid")
        try:
            declaration = self._declaration_resolver(
                request.workflow_id, request.package_id, request.descriptor_digest
            )
            if declaration is None:
                raise SealedArtifactOutputHandlerError("output_unavailable")
            return self._service.stage_declared(
                declaration_digest=request.descriptor_digest,
                outputs=declaration,
                receiver_id=request.receiver_id,
                revision_digest=request.revision_digest,
                invocation_id=request.invocation_id,
                sealed=request.outputs,
                expires_at=request.expires_at,
                now=now,
            )
        except SealedArtifactOutputHandlerError:
            raise
        except Exception as error:  # noqa: BLE001 - map at package boundary.
            raise _map_service_error(error) from error

    def promote(
        self,
        private: SealedArtifactPrivateOutputSet,
        *,
        now: datetime,
    ) -> tuple[SealedArtifactOutputHandle, ...]:
        if not isinstance(private, SealedArtifactPrivateOutputSet):
            raise SealedArtifactOutputHandlerError("output_invalid")
        _require_aware(now)
        if now >= private.expires_at:
            raise SealedArtifactOutputHandlerError("output_expired")
        try:
            transition = self._service.transition_private_output(
                private, operation="promote", now=now
            )
            if transition.status == "conflict":
                raise SealedArtifactOutputHandlerError("output_conflict")
            if transition.status == "missing":
                raise SealedArtifactOutputHandlerError("output_unavailable")
            return transition.handles
        except Exception as error:  # noqa: BLE001 - map at package boundary.
            raise _map_service_error(error) from error

    def discard(
        self,
        private: SealedArtifactPrivateOutputSet,
        *,
        now: datetime,
    ) -> None:
        if not isinstance(private, SealedArtifactPrivateOutputSet):
            raise SealedArtifactOutputHandlerError("output_invalid")
        _require_aware(now)
        if now >= private.expires_at:
            return
        try:
            transition = self._service.transition_private_output(
                private, operation="discard", now=now
            )
            if transition.status == "missing":
                raise SealedArtifactOutputHandlerError("output_unavailable")
            if transition.status == "conflict":
                raise SealedArtifactOutputHandlerError("output_conflict")
        except Exception as error:  # noqa: BLE001 - map at package boundary.
            raise _map_service_error(error) from error

    def read(
        self,
        handle: SealedArtifactOutputHandle,
        *,
        binding: SealedArtifactOutputReadBinding,
        now: datetime,
    ) -> bytes:
        if not isinstance(handle, SealedArtifactOutputHandle):
            raise SealedArtifactOutputHandlerError("output_invalid")
        if not isinstance(binding, SealedArtifactOutputReadBinding):
            raise SealedArtifactOutputHandlerError("output_invalid")
        _require_aware(now)
        if now >= handle.expires_at:
            raise SealedArtifactOutputHandlerError("output_expired")
        try:
            return self._service.read(
                handle,
                receiver_id=binding.receiver_id,
                revision_digest=binding.revision_digest,
                invocation_id=binding.invocation_id,
                now=now,
            )
        except Exception as error:  # noqa: BLE001 - map at package boundary.
            raise _map_service_error(error) from error


def _require_identifier(value: object) -> None:
    if not isinstance(value, str) or not value:
        raise SealedArtifactOutputHandlerError("output_invalid")


def _require_aware(value: object) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise SealedArtifactOutputHandlerError("output_invalid")


def _map_service_error(error: Exception) -> SealedArtifactOutputHandlerError:
    if isinstance(error, SealedArtifactOutputHandlerError):
        return error
    if not isinstance(error, SealedArtifactHandleError):
        return SealedArtifactOutputHandlerError("output_storage_failed")
    message = str(error)
    if "invalid" in message:
        return SealedArtifactOutputHandlerError("output_invalid")
    if "expired" in message:
        return SealedArtifactOutputHandlerError("output_expired")
    return SealedArtifactOutputHandlerError("output_unavailable")
