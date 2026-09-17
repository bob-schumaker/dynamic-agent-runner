"""Generic sealed-job transport for reviewed host capabilities."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol


class ReviewedCapabilityJobError(ValueError):
    """Raised when a sealed reviewed-capability job is unavailable or changed."""


@dataclass(frozen=True)
class SealedReviewedCapabilityJob:
    """The private immutable envelope resolved by a host extension."""

    job_handle: str
    issuer_id: str
    opaque_id: str
    revision: str
    digest: str
    principal: str
    expires_at: datetime
    template_capability_id: str
    template_contract_version: str
    template_digest: str
    extension_binding: str
    dependency_capability_id: str
    dependency_binding_digest: str
    member_binding_digest: str


class ReviewedCapabilityJobResolver(Protocol):
    """Host-owned sealed-job resolver; it never exposes members to packages."""

    def resolve(
        self, *, job_handle: str, principal: str, now: datetime
    ) -> SealedReviewedCapabilityJob: ...

    def revalidate(
        self, *, job: SealedReviewedCapabilityJob, now: datetime
    ) -> SealedReviewedCapabilityJob: ...


def revalidate_sealed_reviewed_capability_job(
    *,
    job: SealedReviewedCapabilityJob,
    resolver: ReviewedCapabilityJobResolver,
    dependency_binding_digest: str,
    now: datetime,
) -> SealedReviewedCapabilityJob:
    """Require the host's current sealed-job binding before dispatch."""

    _validate_job(job)
    current = _utc(now)
    _digest(dependency_binding_digest)
    try:
        revalidated = resolver.revalidate(job=job, now=current)
    except Exception as error:  # noqa: BLE001 - host resolver boundaries vary.
        raise ReviewedCapabilityJobError("sealed job is unavailable") from error
    _validate_job(revalidated)
    if (
        revalidated != job
        or revalidated.dependency_binding_digest != dependency_binding_digest
    ):
        raise ReviewedCapabilityJobError("sealed job is unavailable")
    return revalidated


def resolve_sealed_reviewed_capability_job(
    *,
    arguments: Mapping[str, object],
    resolver: ReviewedCapabilityJobResolver,
    principal: str,
    template_capability_id: str,
    template_contract_version: str,
    template_digest: str,
    extension_binding: str,
    dependency_binding_digest: str,
    now: datetime,
) -> SealedReviewedCapabilityJob:
    """Resolve only the exact sealed job required by a reviewed declaration."""

    job_handle = _job_handle(arguments)
    _text(principal)
    _text(template_capability_id)
    _text(template_contract_version)
    _digest(template_digest)
    _text(extension_binding)
    _digest(dependency_binding_digest)
    current = _utc(now)
    try:
        job = resolver.resolve(job_handle=job_handle, principal=principal, now=current)
    except Exception as error:  # noqa: BLE001 - host resolver boundaries vary.
        raise ReviewedCapabilityJobError("sealed job is unavailable") from error
    _validate_job(job)
    if (
        job.job_handle != job_handle
        or job.principal != principal
        or job.expires_at <= current
        or job.template_capability_id != template_capability_id
        or job.template_contract_version != template_contract_version
        or job.template_digest != template_digest
        or job.extension_binding != extension_binding
        or job.dependency_capability_id != "embedding.execute.v1"
        or job.dependency_binding_digest != dependency_binding_digest
    ):
        raise ReviewedCapabilityJobError("sealed job is unavailable")
    return job


def _job_handle(arguments: Mapping[str, object]) -> str:
    if not isinstance(arguments, Mapping) or set(arguments) != {"job_handle"}:
        raise ReviewedCapabilityJobError("sealed job is invalid")
    value = arguments["job_handle"]
    if (
        not isinstance(value, str)
        or not value.startswith("sealed:vector-index-job:")
        or not value.removeprefix("sealed:vector-index-job:")
    ):
        raise ReviewedCapabilityJobError("sealed job is invalid")
    return value


def _validate_job(job: object) -> None:
    if not isinstance(job, SealedReviewedCapabilityJob):
        raise ReviewedCapabilityJobError("sealed job is unavailable")
    if (
        not job.job_handle.startswith("sealed:vector-index-job:")
        or job.job_handle.removeprefix("sealed:vector-index-job:") != job.opaque_id
        or not all(
            isinstance(value, str) and value
            for value in (
                job.issuer_id,
                job.opaque_id,
                job.revision,
                job.principal,
                job.template_capability_id,
                job.template_contract_version,
                job.extension_binding,
                job.dependency_capability_id,
            )
        )
    ):
        raise ReviewedCapabilityJobError("sealed job is unavailable")
    try:
        _digest(job.digest)
        _digest(job.template_digest)
        _digest(job.dependency_binding_digest)
        _digest(job.member_binding_digest)
        _utc(job.expires_at)
    except ReviewedCapabilityJobError:
        raise ReviewedCapabilityJobError("sealed job is unavailable") from None


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ReviewedCapabilityJobError("sealed job is invalid")
    return value


def _digest(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ReviewedCapabilityJobError("sealed job is invalid")
    return value


def _utc(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ReviewedCapabilityJobError("sealed job is invalid")
    return value.astimezone(UTC)
