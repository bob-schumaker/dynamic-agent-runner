"""Pure, declarative workflow support classification."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType


class WorkflowSupportMatrixError(ValueError):
    """Raised when a support-matrix value is malformed."""


class WorkflowSupportStatus(StrEnum):
    """One terminal pure-classification result."""

    SUPPORTED = "supported"
    NOT_APPLICABLE = "not_applicable"
    BLOCKED = "blocked"
    DEFERRED = "deferred"


_REASONS_BY_STATUS = {
    WorkflowSupportStatus.DEFERRED: frozenset({"profile_unimplemented"}),
    WorkflowSupportStatus.NOT_APPLICABLE: frozenset({"adapter_capability_missing"}),
    WorkflowSupportStatus.BLOCKED: frozenset(
        {
            "authorization_missing",
            "material_identity_mismatch",
            "required_abi_unavailable",
            "required_host_capability_missing",
            "required_material_missing",
            "required_provider_unavailable",
        }
    ),
    WorkflowSupportStatus.SUPPORTED: frozenset(),
}


@dataclass(frozen=True)
class MaterialIdentity:
    """Immutable package and material facts for one candidate or profile."""

    package_id: str
    material_lock_digest: str
    material_roles: tuple[str, ...]
    artifact_digests: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _text(self.package_id, "package_id")
        _digest(self.material_lock_digest, "material_lock_digest")
        object.__setattr__(
            self,
            "material_roles",
            _canonical_strings(self.material_roles, "material_roles"),
        )
        artifacts = dict(self.artifact_digests)
        if any(not isinstance(key, str) for key in artifacts):
            raise WorkflowSupportMatrixError("artifact_digests are invalid")
        for key, digest in artifacts.items():
            _text(key, "artifact digest name")
            _digest(digest, "artifact digest")
        object.__setattr__(self, "artifact_digests", MappingProxyType(artifacts))

    def to_mapping(self) -> dict[str, object]:
        """Return the profile/candidate material identity as canonical data."""

        return {
            "package_id": self.package_id,
            "material_lock_digest": self.material_lock_digest,
            "material_roles": list(self.material_roles),
            "artifact_digests": dict(sorted(self.artifact_digests.items())),
        }


@dataclass(frozen=True)
class WorkflowSupportProfile:
    """One immutable declarative workflow-support requirement set."""

    profile_id: str
    workflow_family: str
    required_adapter_capabilities: tuple[str, ...]
    required_abi_capabilities: tuple[str, ...]
    required_provider_capabilities: tuple[str, ...]
    required_host_capabilities: tuple[str, ...]
    material_identity: MaterialIdentity | None
    execution_mode: str
    authorization_required: bool
    implemented: bool

    def __post_init__(self) -> None:
        _text(self.profile_id, "profile_id")
        _text(self.workflow_family, "workflow_family")
        for name in (
            "required_adapter_capabilities",
            "required_abi_capabilities",
            "required_provider_capabilities",
            "required_host_capabilities",
        ):
            object.__setattr__(
                self, name, _canonical_strings(getattr(self, name), name)
            )
        if self.material_identity is not None and not isinstance(
            self.material_identity, MaterialIdentity
        ):
            raise WorkflowSupportMatrixError("material_identity is invalid")
        if self.execution_mode not in {"synthetic", "live"}:
            raise WorkflowSupportMatrixError("execution_mode is invalid")
        if not isinstance(self.authorization_required, bool) or not isinstance(
            self.implemented, bool
        ):
            raise WorkflowSupportMatrixError("profile flags are invalid")

    def to_mapping(self) -> dict[str, object]:
        """Return the canonical profile information used for its digest."""

        return {
            "profile_id": self.profile_id,
            "workflow_family": self.workflow_family,
            "required_adapter_capabilities": list(self.required_adapter_capabilities),
            "required_abi_capabilities": list(self.required_abi_capabilities),
            "required_provider_capabilities": list(self.required_provider_capabilities),
            "required_host_capabilities": list(self.required_host_capabilities),
            "material_identity": (
                self.material_identity.to_mapping()
                if self.material_identity is not None
                else None
            ),
            "execution_mode": self.execution_mode,
            "authorization_required": self.authorization_required,
            "implemented": self.implemented,
        }

    @property
    def digest(self) -> str:
        """Return the SHA-256 digest of canonical profile bytes."""

        return hashlib.sha256(_canonical_json(self.to_mapping())).hexdigest()


@dataclass(frozen=True)
class WorkflowSupportCandidate:
    """Immutable adapter, host, provider, and material facts for one cell."""

    adapter_id: str
    adapter_capabilities: frozenset[str]
    available_abi_capabilities: frozenset[str]
    provider_capabilities: frozenset[str]
    host_capabilities: frozenset[str]
    material_identity: MaterialIdentity | None
    authorization_granted: bool

    def __post_init__(self) -> None:
        _text(self.adapter_id, "adapter_id")
        for name in (
            "adapter_capabilities",
            "available_abi_capabilities",
            "provider_capabilities",
            "host_capabilities",
        ):
            values = getattr(self, name)
            if not isinstance(values, frozenset) or any(
                not isinstance(value, str) or not value for value in values
            ):
                raise WorkflowSupportMatrixError(f"{name} are invalid")
        if self.material_identity is not None and not isinstance(
            self.material_identity, MaterialIdentity
        ):
            raise WorkflowSupportMatrixError("material_identity is invalid")
        if not isinstance(self.authorization_granted, bool):
            raise WorkflowSupportMatrixError("authorization_granted is invalid")


@dataclass(frozen=True)
class WorkflowSupportCell:
    """A pure terminal classification bound to profile and candidate identity."""

    profile_digest: str
    adapter_id: str
    material_identity: MaterialIdentity | None
    status: WorkflowSupportStatus
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        _digest(self.profile_digest, "profile_digest")
        _text(self.adapter_id, "adapter_id")
        if self.material_identity is not None and not isinstance(
            self.material_identity, MaterialIdentity
        ):
            raise WorkflowSupportMatrixError("material_identity is invalid")
        status = WorkflowSupportStatus(self.status)
        reasons = tuple(self.reason_codes)
        if reasons != tuple(sorted(reasons)) or not set(reasons).issubset(
            _REASONS_BY_STATUS[status]
        ):
            raise WorkflowSupportMatrixError("support cell reasons are invalid")
        if (status is WorkflowSupportStatus.SUPPORTED) != (not reasons):
            raise WorkflowSupportMatrixError("support cell reasons are invalid")
        if status is not WorkflowSupportStatus.SUPPORTED and not reasons:
            raise WorkflowSupportMatrixError("support cell reasons are invalid")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "reason_codes", reasons)


@dataclass(frozen=True)
class WorkflowSupportReceipt:
    """Pure receipt data bound to one exact support cell."""

    profile_digest: str
    adapter_id: str
    material_identity: MaterialIdentity | None
    test_mode: str
    status: WorkflowSupportStatus
    reason_codes: tuple[str, ...]
    dispatch_count: int

    def __post_init__(self) -> None:
        _digest(self.profile_digest, "profile_digest")
        _text(self.adapter_id, "adapter_id")
        if self.material_identity is not None and not isinstance(
            self.material_identity, MaterialIdentity
        ):
            raise WorkflowSupportMatrixError("material_identity is invalid")
        if self.test_mode not in {"synthetic", "live"}:
            raise WorkflowSupportMatrixError("test_mode is invalid")
        status = WorkflowSupportStatus(self.status)
        reasons = tuple(self.reason_codes)
        if reasons != tuple(sorted(reasons)) or not set(reasons).issubset(
            _REASONS_BY_STATUS[status]
        ):
            raise WorkflowSupportMatrixError("receipt reasons are invalid")
        if (status is WorkflowSupportStatus.SUPPORTED) != (not reasons):
            raise WorkflowSupportMatrixError("receipt reasons are invalid")
        if status is not WorkflowSupportStatus.SUPPORTED and not reasons:
            raise WorkflowSupportMatrixError("receipt reasons are invalid")
        if type(self.dispatch_count) is not int or self.dispatch_count < 0:
            raise WorkflowSupportMatrixError("dispatch_count is invalid")
        if status is not WorkflowSupportStatus.SUPPORTED and self.dispatch_count:
            raise WorkflowSupportMatrixError("dispatch_count is invalid")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "reason_codes", reasons)


def classify_workflow_support(
    profile: WorkflowSupportProfile, candidate: WorkflowSupportCandidate
) -> WorkflowSupportCell:
    """Classify immutable facts without resolving any runtime collaborator."""

    if not isinstance(profile, WorkflowSupportProfile) or not isinstance(
        candidate, WorkflowSupportCandidate
    ):
        raise WorkflowSupportMatrixError("support classification inputs are invalid")
    if not profile.implemented:
        return _cell(
            profile,
            candidate,
            WorkflowSupportStatus.DEFERRED,
            ("profile_unimplemented",),
        )
    if not set(profile.required_adapter_capabilities).issubset(
        candidate.adapter_capabilities
    ):
        return _cell(
            profile,
            candidate,
            WorkflowSupportStatus.NOT_APPLICABLE,
            ("adapter_capability_missing",),
        )

    reasons = _blocked_reasons(profile, candidate)
    if reasons:
        return _cell(
            profile,
            candidate,
            WorkflowSupportStatus.BLOCKED,
            tuple(sorted(reasons)),
        )
    return _cell(profile, candidate, WorkflowSupportStatus.SUPPORTED, ())


def _blocked_reasons(
    profile: WorkflowSupportProfile, candidate: WorkflowSupportCandidate
) -> list[str]:
    reasons: list[str] = []
    if profile.material_identity is not None:
        if candidate.material_identity is None or not set(
            profile.material_identity.material_roles
        ).issubset(candidate.material_identity.material_roles):
            reasons.append("required_material_missing")
        elif (
            candidate.material_identity.to_mapping()
            != profile.material_identity.to_mapping()
        ):
            reasons.append("material_identity_mismatch")
    if not set(profile.required_abi_capabilities).issubset(
        candidate.available_abi_capabilities
    ):
        reasons.append("required_abi_unavailable")
    if not set(profile.required_provider_capabilities).issubset(
        candidate.provider_capabilities
    ):
        reasons.append("required_provider_unavailable")
    if not set(profile.required_host_capabilities).issubset(
        candidate.host_capabilities
    ):
        reasons.append("required_host_capability_missing")
    if profile.authorization_required and not candidate.authorization_granted:
        reasons.append("authorization_missing")
    return reasons


def _cell(
    profile: WorkflowSupportProfile,
    candidate: WorkflowSupportCandidate,
    status: WorkflowSupportStatus,
    reasons: tuple[str, ...],
) -> WorkflowSupportCell:
    return WorkflowSupportCell(
        profile.digest,
        candidate.adapter_id,
        candidate.material_identity,
        status,
        reasons,
    )


def validate_workflow_support_receipt(
    profile: WorkflowSupportProfile,
    candidate: WorkflowSupportCandidate,
    cell: WorkflowSupportCell,
    receipt: WorkflowSupportReceipt,
) -> None:
    """Reject receipt data that is not bound to the exact evaluated cell."""

    if not isinstance(cell, WorkflowSupportCell) or not isinstance(
        receipt, WorkflowSupportReceipt
    ):
        raise WorkflowSupportMatrixError("support receipt is invalid")
    expected = classify_workflow_support(profile, candidate)
    if cell != expected or (
        receipt.profile_digest,
        receipt.adapter_id,
        receipt.material_identity,
        receipt.test_mode,
        receipt.status,
        receipt.reason_codes,
    ) != (
        expected.profile_digest,
        expected.adapter_id,
        expected.material_identity,
        profile.execution_mode,
        expected.status,
        expected.reason_codes,
    ):
        raise WorkflowSupportMatrixError("receipt does not match support cell")


def _canonical_strings(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise WorkflowSupportMatrixError(f"{name} are invalid")
    if value != tuple(sorted(value)) or len(set(value)) != len(value):
        raise WorkflowSupportMatrixError(f"{name} are invalid")
    return value


def _text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value:
        raise WorkflowSupportMatrixError(f"{name} is invalid")


def _digest(value: object, name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise WorkflowSupportMatrixError(f"{name} is invalid")


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        _normalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _normalize(value: object) -> object:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, Mapping):
        return {
            unicodedata.normalize("NFC", key): _normalize(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return [_normalize(item) for item in value]
    return value
