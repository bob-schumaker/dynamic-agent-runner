"""Immutable strict-local workflow registrations and alias mappings."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dar_workflow_server.policy import CapabilityResolution, WorkflowPolicy
from dar_workflow_server.mcp_binding import (
    MCPWorkflowCapabilityBindingControlPlane,
    MCPWorkflowCapabilityBindingError,
)
from dar_workflow_server.mcp_surfaces import (
    MCPSurfaceSnapshotControlPlane,
    MCPSurfaceSnapshotError,
)
from dar_workflow_server.mcp_tools import MCPReadOnlyToolClient
from dar_workflow_server.profiles import (
    LocalModelProfile,
    LocalModelProfileControlPlane,
    LocalModelProfileError,
)


class WorkflowRegistrationError(ValueError):
    """Raised when a policy cannot receive an immutable local registration."""


@dataclass(frozen=True)
class WorkflowRegistration:
    """A catalog-local alias bound to one policy and strict-local model profile."""

    workflow_id: str
    registration_digest: str
    package_id: str
    revision_digest: str
    policy_digest: str
    profile_id: str
    model_id: str
    mcp_binding_id: str | None = None


class WorkflowRegistrationService:
    """Bind eligible policies only to the human-configured strict local profile."""

    def __init__(
        self,
        *,
        profiles: LocalModelProfileControlPlane,
        configured_profile_id: str,
        root: Path,
        mcp_bindings: MCPWorkflowCapabilityBindingControlPlane | None = None,
        mcp_client: MCPReadOnlyToolClient | None = None,
        mcp_surfaces: MCPSurfaceSnapshotControlPlane | None = None,
    ) -> None:
        self._profiles = profiles
        self._configured_profile_id = configured_profile_id
        self._root = root
        self._path = root / "registrations.json"
        self._mcp_bindings = mcp_bindings
        self._mcp_client = mcp_client
        self._mcp_surfaces = mcp_surfaces
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        mode = os.lstat(root).st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise WorkflowRegistrationError("registration root is not a directory")

    def register(
        self,
        *,
        workflow_id: str,
        policy: WorkflowPolicy,
        capability_resolution: CapabilityResolution,
        mcp_binding_id: str | None = None,
    ) -> WorkflowRegistration:
        """Create or retrieve a local alias for an eligible strict-local policy."""

        _nonempty(workflow_id, "workflow_id")
        if capability_resolution.status != "eligible":
            raise WorkflowRegistrationError(
                "policy capability resolution is unavailable"
            )
        profile = self._configured_profile()
        self._validate_profile(policy, profile)
        bound_mcp_id = self._validate_mcp_binding(policy, mcp_binding_id)
        registration = _registration_from(
            policy, profile, workflow_id, mcp_binding_id=bound_mcp_id
        )
        records = self._read()
        existing = records.get(workflow_id)
        if existing is not None:
            existing_registration = _from_mapping(existing)
            if (
                existing_registration.registration_digest
                == registration.registration_digest
            ):
                return existing_registration
            raise WorkflowRegistrationError("workflow alias collision")
        records[workflow_id] = _to_mapping(registration)
        self._write(records)
        return registration

    def resolve(self, workflow_id: str) -> WorkflowRegistration:
        """Resolve one immutable local alias without rebinding it."""

        _nonempty(workflow_id, "workflow_id")
        value = self._read().get(workflow_id)
        if value is None:
            raise WorkflowRegistrationError("workflow alias is not registered")
        return _from_mapping(value)

    def _configured_profile(self) -> LocalModelProfile:
        try:
            return self._profiles.load(self._configured_profile_id)
        except LocalModelProfileError as error:
            raise WorkflowRegistrationError(
                "configured local profile is unavailable"
            ) from error

    def _validate_profile(
        self, policy: WorkflowPolicy, profile: LocalModelProfile
    ) -> None:
        if profile.adapter_id != "strict-local-adapter-v1":
            raise WorkflowRegistrationError("configured adapter is not strict local")
        if profile.profile_requirement != policy.model_profile_requirement:
            raise WorkflowRegistrationError(
                "configured profile requirement does not match policy"
            )
        if "text_generation" not in profile.capabilities:
            raise WorkflowRegistrationError("configured profile lacks text_generation")

    def _validate_mcp_binding(
        self, policy: WorkflowPolicy, mcp_binding_id: str | None
    ) -> str | None:
        if not policy.declared_tools:
            if mcp_binding_id is not None:
                raise WorkflowRegistrationError(
                    "no-tool policy cannot receive an MCP capability binding"
                )
            return None
        if (
            not isinstance(mcp_binding_id, str)
            or not mcp_binding_id
            or self._mcp_bindings is None
            or self._mcp_client is None
            or self._mcp_surfaces is None
        ):
            raise WorkflowRegistrationError("MCP capability binding is unavailable")
        try:
            binding = self._mcp_bindings.load(mcp_binding_id)
            expected = {
                tool.tool_id: tool.remote_tool_name for tool in policy.declared_tools
            }
            if (
                binding.policy_digest != policy.policy_digest
                or dict(binding.tool_id_to_remote_name) != expected
            ):
                raise WorkflowRegistrationError(
                    "MCP capability binding does not match policy"
                )
            self._mcp_surfaces.verify_current_client(
                binding.snapshot_id, self._mcp_client
            )
        except (MCPWorkflowCapabilityBindingError, MCPSurfaceSnapshotError) as error:
            raise WorkflowRegistrationError(
                "MCP capability binding is unavailable"
            ) from error
        return mcp_binding_id

    def _read(self) -> dict[str, dict[str, str]]:
        try:
            value = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        if not isinstance(value, dict) or not isinstance(
            value.get("registrations"), dict
        ):
            raise WorkflowRegistrationError("registration catalog is invalid")
        return value["registrations"]

    def _write(self, records: Mapping[str, Mapping[str, str]]) -> None:
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {"registrations": records}, sort_keys=True, separators=(",", ":")
            ),
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        os.replace(temporary, self._path)


def _registration_from(
    policy: WorkflowPolicy,
    profile: LocalModelProfile,
    workflow_id: str,
    *,
    mcp_binding_id: str | None,
) -> WorkflowRegistration:
    digest_input = {
        "format_version": 1,
        "workflow_id": workflow_id,
        "package_id": policy.package_id,
        "revision_digest": policy.revision_digest,
        "policy_digest": policy.policy_digest,
        "profile_id": profile.profile_id,
        "model_id": profile.model_id,
    }
    if mcp_binding_id is not None:
        digest_input["mcp_binding_id"] = mcp_binding_id
    registration_digest = hashlib.sha256(
        json.dumps(digest_input, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return WorkflowRegistration(
        workflow_id=workflow_id,
        registration_digest=registration_digest,
        package_id=policy.package_id,
        revision_digest=policy.revision_digest,
        policy_digest=policy.policy_digest,
        profile_id=profile.profile_id,
        model_id=profile.model_id,
        mcp_binding_id=mcp_binding_id,
    )


def _to_mapping(registration: WorkflowRegistration) -> dict[str, str]:
    result = {
        "workflow_id": registration.workflow_id,
        "registration_digest": registration.registration_digest,
        "package_id": registration.package_id,
        "revision_digest": registration.revision_digest,
        "policy_digest": registration.policy_digest,
        "profile_id": registration.profile_id,
        "model_id": registration.model_id,
    }
    if registration.mcp_binding_id is not None:
        result["mcp_binding_id"] = registration.mcp_binding_id
    return result


def _from_mapping(value: object) -> WorkflowRegistration:
    if not isinstance(value, Mapping):
        raise WorkflowRegistrationError("registration catalog is invalid")
    try:
        values = {key: value[key] for key in _RECORD_FIELDS}
    except KeyError as error:
        raise WorkflowRegistrationError("registration catalog is invalid") from error
    if set(value) not in (_RECORD_FIELDS, _RECORD_FIELDS | {"mcp_binding_id"}) or any(
        not isinstance(item, str) or not item for item in values.values()
    ):
        raise WorkflowRegistrationError("registration catalog is invalid")
    mcp_binding_id = value.get("mcp_binding_id")
    if mcp_binding_id is not None and (
        not isinstance(mcp_binding_id, str) or not mcp_binding_id
    ):
        raise WorkflowRegistrationError("registration catalog is invalid")
    return WorkflowRegistration(  # type: ignore[arg-type]
        **values, mcp_binding_id=mcp_binding_id
    )


_RECORD_FIELDS = {
    "workflow_id",
    "registration_digest",
    "package_id",
    "revision_digest",
    "policy_digest",
    "profile_id",
    "model_id",
}


def _nonempty(value: object, name: str) -> None:
    if not isinstance(value, str) or not value:
        raise WorkflowRegistrationError(f"{name} must be a non-empty string")
