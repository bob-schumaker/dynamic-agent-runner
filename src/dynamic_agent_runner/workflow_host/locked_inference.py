"""Strict descriptor contract for bounded locked inference callbacks."""

from __future__ import annotations

import hashlib
import json
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dynamic_agent_runner.workflow_host.capabilities import CapabilityRequirements
from dynamic_agent_runner.workflow_host.locked_inference_execution import (
    LockedInferenceExecutionError,
    validate_locked_inference_schema,
)
from dynamic_agent_runner.workflow_host.material_sets import ModelMaterialSets
from dynamic_agent_runner.workflow_host.model_execution_binding import (
    ModelExecutionBinding,
    ModelExecutionBindingError,
    derive_model_execution_binding,
)


_ROLE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_GENERATE_CAPABILITY = "model.generate.v1"


class LockedInferenceError(ValueError):
    """Raised with a redacted locked-inference contract classification."""


@dataclass(frozen=True)
class SealedAsset:
    """One package-relative asset whose exact bytes are policy-bound."""

    path: str
    sha256: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.path, str)
            or not self.path
            or self.path.startswith("/")
            or any(segment in {"", ".", ".."} for segment in self.path.split("/"))
            or not _DIGEST.fullmatch(self.sha256)
        ):
            raise LockedInferenceError("sealed inference asset is invalid")

    def to_mapping(self) -> dict[str, str]:
        return {"path": self.path, "sha256": self.sha256}


@dataclass(frozen=True)
class InferenceLimits:
    """Finite package-declared ceilings for one inference role."""

    max_calls: int
    max_input_bytes: int
    max_output_bytes: int
    timeout_milliseconds: int
    max_concurrency: int

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
            for value in self.__dict__.values()
        ):
            raise LockedInferenceError("inference limits are invalid")

    def to_mapping(self) -> dict[str, int]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class InferenceRole:
    """One exact material, capability, schema, and asset authorization relation."""

    role: str
    material_role: str
    capability_id: str
    instruction_asset: SealedAsset
    request_schema_asset: SealedAsset
    response_schema_asset: SealedAsset
    authorized_asset_digests: tuple[str, ...]
    limits: InferenceLimits

    def __post_init__(self) -> None:
        if not _ROLE.fullmatch(self.role) or not _ROLE.fullmatch(self.material_role):
            raise LockedInferenceError("inference role is invalid")
        if self.capability_id != _GENERATE_CAPABILITY:
            raise LockedInferenceError("inference capability is invalid")
        if (
            not self.authorized_asset_digests
            or tuple(self.authorized_asset_digests)
            != tuple(sorted(self.authorized_asset_digests))
            or len(set(self.authorized_asset_digests))
            != len(self.authorized_asset_digests)
            or any(
                not _DIGEST.fullmatch(value) for value in self.authorized_asset_digests
            )
        ):
            raise LockedInferenceError("authorized inference assets are invalid")
        object.__setattr__(
            self, "authorized_asset_digests", tuple(self.authorized_asset_digests)
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "authorized_asset_digests": list(self.authorized_asset_digests),
            "capability_id": self.capability_id,
            "instruction_asset": self.instruction_asset.to_mapping(),
            "limits": self.limits.to_mapping(),
            "material_role": self.material_role,
            "request_schema_asset": self.request_schema_asset.to_mapping(),
            "response_schema_asset": self.response_schema_asset.to_mapping(),
            "role": self.role,
        }


@dataclass(frozen=True)
class InferenceRoles:
    """Canonical v1 ordered collection of sealed inference roles."""

    roles: tuple[InferenceRole, ...]
    format_version: int = 1

    def __post_init__(self) -> None:
        identifiers = tuple(item.role for item in self.roles)
        materials = tuple(item.material_role for item in self.roles)
        if (
            self.format_version != 1
            or not identifiers
            or identifiers != tuple(sorted(identifiers))
            or len(set(identifiers)) != len(identifiers)
            or len(set(materials)) != len(materials)
        ):
            raise LockedInferenceError("inference roles are invalid")
        object.__setattr__(self, "roles", tuple(self.roles))

    @property
    def canonical_bytes(self) -> bytes:
        return _canonical_json(
            {
                "format_version": self.format_version,
                "roles": [role.to_mapping() for role in self.roles],
            }
        )

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()

    def for_role(self, role: str) -> InferenceRole:
        for item in self.roles:
            if item.role == role:
                return item
        raise LockedInferenceError("inference role is unavailable")


@dataclass(frozen=True)
class LockedInferenceBinding:
    """One host-private exact role-to-material-to-capability identity."""

    role: str
    material_role: str
    model_binding: ModelExecutionBinding
    capability_contract_version: str
    capability_contract_digest: str

    @property
    def material_lock_digest(self) -> str:
        return self.model_binding.material_lock_digest

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            (
                self.role
                + self.material_role
                + self.model_binding.digest
                + _GENERATE_CAPABILITY
                + self.capability_contract_version
                + self.capability_contract_digest
            ).encode("utf-8")
        ).hexdigest()


def parse_inference_roles(value: object) -> InferenceRoles:
    """Parse strict canonical role data and verify an optional declared digest."""

    if (
        not isinstance(value, Mapping)
        or set(value) - {"format_version", "roles", "inference_roles_digest"}
        or not {"format_version", "roles"} <= set(value)
    ):
        raise LockedInferenceError("inference role fields are invalid")
    raw_roles = value["roles"]
    if not isinstance(raw_roles, list):
        raise LockedInferenceError("inference roles must be a list")
    result = InferenceRoles(
        tuple(_role(item) for item in raw_roles), value["format_version"]
    )
    declared = value.get("inference_roles_digest")
    if declared is not None and (
        not _DIGEST.fullmatch(declared) or declared != result.digest
    ):
        raise LockedInferenceError("inference role digest does not match")
    return result


def validate_inference_material_roles(
    roles: InferenceRoles, material_sets: ModelMaterialSets
) -> None:
    """Fail closed unless every role names one declared distinct material set."""

    try:
        for role in roles.roles:
            material_sets.for_role(role.material_role)
    except Exception as error:
        raise LockedInferenceError("inference material role is unavailable") from error


def verify_inference_role_assets(*, root: Path, roles: InferenceRoles) -> None:
    """Verify declared instruction and schema assets before provider admission."""

    if not isinstance(root, Path):
        raise LockedInferenceError("inference asset is invalid")
    try:
        for role in roles.roles:
            _verified_asset_bytes(root, role.instruction_asset).decode("utf-8")
            for schema in (role.request_schema_asset, role.response_schema_asset):
                validate_locked_inference_schema(_verified_asset_bytes(root, schema))
    except (OSError, UnicodeError, LockedInferenceExecutionError) as error:
        raise LockedInferenceError("inference asset is invalid") from error


def derive_locked_inference_bindings(
    *,
    roles: InferenceRoles,
    material_sets: ModelMaterialSets,
    requirements: CapabilityRequirements,
) -> tuple[LockedInferenceBinding, ...]:
    """Derive per-role host identities without exposing provider selection."""

    validate_inference_material_roles(roles, material_sets)
    requirements_by_id = {
        item.capability_id: item for item in requirements.required_capabilities
    }
    generation = requirements_by_id.get(_GENERATE_CAPABILITY)
    if generation is None or "structured" not in generation.required_features:
        raise LockedInferenceError("inference capability is unavailable")
    bindings = []
    for role in roles.roles:
        try:
            model_binding = derive_model_execution_binding(
                lock=material_sets.for_role(role.material_role),
                requirements=requirements,
            )
        except ModelExecutionBindingError as error:
            raise LockedInferenceError(
                "inference material binding is unavailable"
            ) from error
        bindings.append(
            LockedInferenceBinding(
                role=role.role,
                material_role=role.material_role,
                model_binding=model_binding,
                capability_contract_version=generation.contract_version,
                capability_contract_digest=generation.contract_digest,
            )
        )
    return tuple(bindings)


def _role(value: object) -> InferenceRole:
    fields = {
        "role",
        "material_role",
        "capability_id",
        "instruction_asset",
        "request_schema_asset",
        "response_schema_asset",
        "authorized_asset_digests",
        "limits",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise LockedInferenceError("inference role is invalid")
    digests = value["authorized_asset_digests"]
    limits = value["limits"]
    if (
        not isinstance(digests, list)
        or not isinstance(limits, Mapping)
        or set(limits)
        != {
            "max_calls",
            "max_input_bytes",
            "max_output_bytes",
            "timeout_milliseconds",
            "max_concurrency",
        }
    ):
        raise LockedInferenceError("inference role is invalid")
    return InferenceRole(
        role=value["role"],
        material_role=value["material_role"],
        capability_id=value["capability_id"],
        instruction_asset=_asset(value["instruction_asset"]),
        request_schema_asset=_asset(value["request_schema_asset"]),
        response_schema_asset=_asset(value["response_schema_asset"]),
        authorized_asset_digests=tuple(digests),
        limits=InferenceLimits(**limits),
    )


def _asset(value: object) -> SealedAsset:
    if not isinstance(value, Mapping) or set(value) != {"path", "sha256"}:
        raise LockedInferenceError("sealed inference asset is invalid")
    return SealedAsset(value["path"], value["sha256"])


def _verified_asset_bytes(root: Path, asset: SealedAsset) -> bytes:
    path = root / asset.path
    try:
        if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
            raise OSError("asset is not a regular file")
        value = path.read_bytes()
    except OSError as error:
        raise LockedInferenceError("inference asset is invalid") from error
    if hashlib.sha256(value).hexdigest() != asset.sha256:
        raise LockedInferenceError("inference asset is invalid")
    return value


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
