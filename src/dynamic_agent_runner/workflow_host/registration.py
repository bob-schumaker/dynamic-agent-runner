"""Immutable host execution-profile workflow registrations and alias mappings."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from dynamic_agent_runner.workflow_host.policy import (
    CapabilityResolution,
    WorkflowPolicy,
)
from dynamic_agent_runner.workflow_host.mcp_binding import (
    MCPWorkflowCapabilityBindingControlPlane,
    MCPWorkflowCapabilityBindingError,
)
from dynamic_agent_runner.workflow_host.mcp_surfaces import (
    MCPSurfaceSnapshotControlPlane,
    MCPSurfaceSnapshotError,
)
from dynamic_agent_runner.workflow_host.mcp_tools import MCPReadOnlyToolClient
from dynamic_agent_runner.workflow_host.profiles import (
    InstallationIdentityProvider,
    LocalModelProfile,
    LocalModelProfileControlPlane,
    LocalModelProfileError,
)


class WorkflowRegistrationError(ValueError):
    """Raised when a policy cannot receive an immutable execution registration."""


@dataclass(frozen=True)
class WorkflowRegistration:
    """A catalog-local alias bound to one policy and execution profile."""

    workflow_id: str
    registration_digest: str
    package_id: str
    revision_digest: str
    policy_digest: str
    profile_id: str
    profile_digest: str
    model_id: str
    capability_requirements_digest: str | None = None
    model_materials_digest: str | None = None
    model_material_sets_digest: str | None = None
    model_execution_binding_digest: str | None = None
    selected_capability_provider_ids: tuple[str, ...] = ()
    mcp_binding_id: str | None = None
    model_recipe_digest: str | None = None
    owner: str | None = None


class WorkflowRegistrationService:
    """Bind eligible policies only to the human-configured execution profile."""

    def __init__(
        self,
        *,
        profiles: LocalModelProfileControlPlane,
        configured_profile_id: str,
        root: Path,
        mcp_bindings: MCPWorkflowCapabilityBindingControlPlane | None = None,
        mcp_client: MCPReadOnlyToolClient | None = None,
        mcp_surfaces: MCPSurfaceSnapshotControlPlane | None = None,
        model_recipe_digest_provider: Callable[[LocalModelProfile], str] | None = None,
        owner: str | None = None,
    ) -> None:
        self._profiles = profiles
        self._configured_profile_id = configured_profile_id
        self._root = root
        self._path = root / "registrations.json"
        self._mcp_bindings = mcp_bindings
        self._mcp_client = mcp_client
        self._mcp_surfaces = mcp_surfaces
        self._model_recipe_digest_provider = model_recipe_digest_provider
        self._owner = (
            InstallationIdentityProvider().principal if owner is None else owner
        )
        _nonempty(self._owner, "owner")
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
        """Create or retrieve a local alias for an eligible profile-bound policy."""

        _nonempty(workflow_id, "workflow_id")
        if capability_resolution.status != "eligible":
            raise WorkflowRegistrationError(
                "policy capability resolution is unavailable"
            )
        profile = self._configured_profile()
        self._validate_profile(policy, profile)
        bound_mcp_id = self._validate_mcp_binding(policy, mcp_binding_id)
        model_recipe_digest = self._model_recipe_digest(policy, profile)
        registration = _registration_from(
            policy,
            profile,
            workflow_id,
            selected_capability_provider_ids=policy.selected_capability_provider_ids,
            mcp_binding_id=bound_mcp_id,
            model_recipe_digest=model_recipe_digest,
            owner=self._owner,
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

    def refresh(
        self,
        *,
        workflow_id: str,
        policy: WorkflowPolicy,
        capability_resolution: CapabilityResolution,
        mcp_binding_id: str | None = None,
    ) -> WorkflowRegistration:
        """Refresh one registered policy without changing its package revision."""

        existing = self.resolve(workflow_id)
        if existing.owner != self._owner:
            raise WorkflowRegistrationError(
                "workflow refresh owner does not match registration"
            )
        if (
            existing.package_id != policy.package_id
            or existing.revision_digest != policy.revision_digest
        ):
            raise WorkflowRegistrationError(
                "workflow refresh immutable identity mismatch"
            )
        if capability_resolution.status != "eligible":
            raise WorkflowRegistrationError(
                "policy capability resolution is unavailable"
            )
        profile = self._configured_profile()
        self._validate_profile(policy, profile)
        bound_mcp_id = self._validate_mcp_binding(policy, mcp_binding_id)
        registration = _registration_from(
            policy,
            profile,
            workflow_id,
            selected_capability_provider_ids=policy.selected_capability_provider_ids,
            mcp_binding_id=bound_mcp_id,
            model_recipe_digest=self._model_recipe_digest(policy, profile),
            owner=self._owner,
        )
        records = self._read()
        records[workflow_id] = _to_mapping(registration)
        self._write(records)
        return registration

    def configured_profile(self) -> LocalModelProfile:
        """Return the validated profile that is authoritative for registration."""

        return self._configured_profile()

    def _configured_profile(self) -> LocalModelProfile:
        try:
            return self._profiles.load(self._configured_profile_id)
        except LocalModelProfileError as error:
            raise WorkflowRegistrationError(
                "configured profile is unavailable"
            ) from error

    def _validate_profile(
        self, policy: WorkflowPolicy, profile: LocalModelProfile
    ) -> None:
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

    def _model_recipe_digest(
        self, policy: WorkflowPolicy, profile: LocalModelProfile
    ) -> str | None:
        if policy.input_converter is None:
            return None
        if self._model_recipe_digest_provider is None:
            raise WorkflowRegistrationError("model recipe is unavailable")
        try:
            digest = self._model_recipe_digest_provider(profile)
        except Exception as error:  # noqa: BLE001 - provider boundaries vary.
            raise WorkflowRegistrationError("model recipe is unavailable") from error
        if not _is_digest(digest):
            raise WorkflowRegistrationError("model recipe is unavailable")
        return digest

    def _read(self) -> dict[str, dict[str, object]]:
        try:
            value = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        if not isinstance(value, dict) or not isinstance(
            value.get("registrations"), dict
        ):
            raise WorkflowRegistrationError("registration catalog is invalid")
        return value["registrations"]

    def _write(self, records: Mapping[str, Mapping[str, object]]) -> None:
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
    selected_capability_provider_ids: tuple[str, ...],
    mcp_binding_id: str | None,
    model_recipe_digest: str | None,
    owner: str,
) -> WorkflowRegistration:
    digest_input = {
        "format_version": 1,
        "workflow_id": workflow_id,
        "package_id": policy.package_id,
        "revision_digest": policy.revision_digest,
        "policy_digest": policy.policy_digest,
        "capability_requirements_digest": policy.capability_requirements_digest,
        "model_materials_digest": policy.model_materials_digest,
        "model_material_sets_digest": policy.model_material_sets_digest,
        "model_execution_binding_digest": policy.model_execution_binding_digest,
        "selected_capability_provider_ids": selected_capability_provider_ids,
        "profile_id": profile.profile_id,
        "profile_digest": profile.profile_digest,
        "model_id": profile.model_id,
        "owner": owner,
    }
    if mcp_binding_id is not None:
        digest_input["mcp_binding_id"] = mcp_binding_id
    if model_recipe_digest is not None:
        digest_input["model_recipe_digest"] = model_recipe_digest
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
        profile_digest=profile.profile_digest,
        model_id=profile.model_id,
        capability_requirements_digest=policy.capability_requirements_digest,
        model_materials_digest=policy.model_materials_digest,
        model_material_sets_digest=policy.model_material_sets_digest,
        model_execution_binding_digest=policy.model_execution_binding_digest,
        selected_capability_provider_ids=selected_capability_provider_ids,
        mcp_binding_id=mcp_binding_id,
        model_recipe_digest=model_recipe_digest,
        owner=owner,
    )


def _to_mapping(registration: WorkflowRegistration) -> dict[str, object]:
    result = {
        "workflow_id": registration.workflow_id,
        "registration_digest": registration.registration_digest,
        "package_id": registration.package_id,
        "revision_digest": registration.revision_digest,
        "policy_digest": registration.policy_digest,
        "profile_id": registration.profile_id,
        "profile_digest": registration.profile_digest,
        "model_id": registration.model_id,
    }
    if registration.mcp_binding_id is not None:
        result["mcp_binding_id"] = registration.mcp_binding_id
    if registration.capability_requirements_digest is not None:
        result["capability_requirements_digest"] = (
            registration.capability_requirements_digest
        )
    if registration.model_materials_digest is not None:
        result["model_materials_digest"] = registration.model_materials_digest
    if registration.model_material_sets_digest is not None:
        result["model_material_sets_digest"] = registration.model_material_sets_digest
    if registration.model_execution_binding_digest is not None:
        result["model_execution_binding_digest"] = (
            registration.model_execution_binding_digest
        )
    if registration.selected_capability_provider_ids:
        result["selected_capability_provider_ids"] = list(
            registration.selected_capability_provider_ids
        )
    if registration.model_recipe_digest is not None:
        result["model_recipe_digest"] = registration.model_recipe_digest
    if registration.owner is not None:
        result["owner"] = registration.owner
    return result


def _from_mapping(value: object) -> WorkflowRegistration:  # noqa: C901
    if not isinstance(value, Mapping):
        raise WorkflowRegistrationError("registration catalog is invalid")
    try:
        values = {key: value[key] for key in _RECORD_FIELDS}
    except KeyError as error:
        raise WorkflowRegistrationError("registration catalog is invalid") from error
    allowed_fields = _RECORD_FIELDS | {
        "capability_requirements_digest",
        "model_materials_digest",
        "model_material_sets_digest",
        "model_execution_binding_digest",
        "selected_capability_provider_ids",
        "mcp_binding_id",
        "model_recipe_digest",
        "owner",
    }
    if not set(value).issubset(allowed_fields) or any(
        not isinstance(item, str) or not item for item in values.values()
    ):
        raise WorkflowRegistrationError("registration catalog is invalid")
    mcp_binding_id = value.get("mcp_binding_id")
    if mcp_binding_id is not None and (
        not isinstance(mcp_binding_id, str) or not mcp_binding_id
    ):
        raise WorkflowRegistrationError("registration catalog is invalid")
    model_recipe_digest = value.get("model_recipe_digest")
    if model_recipe_digest is not None and not _is_digest(model_recipe_digest):
        raise WorkflowRegistrationError("registration catalog is invalid")
    owner = value.get("owner")
    if owner is not None and (not isinstance(owner, str) or not owner):
        raise WorkflowRegistrationError("registration catalog is invalid")
    capability_requirements_digest = value.get("capability_requirements_digest")
    if capability_requirements_digest is not None and not _is_digest(
        capability_requirements_digest
    ):
        raise WorkflowRegistrationError("registration catalog is invalid")
    model_materials_digest = value.get("model_materials_digest")
    if model_materials_digest is not None and not _is_digest(model_materials_digest):
        raise WorkflowRegistrationError("registration catalog is invalid")
    model_material_sets_digest = value.get("model_material_sets_digest")
    if model_material_sets_digest is not None and not _is_digest(
        model_material_sets_digest
    ):
        raise WorkflowRegistrationError("registration catalog is invalid")
    model_execution_binding_digest = value.get("model_execution_binding_digest")
    if model_execution_binding_digest is not None and not _is_digest(
        model_execution_binding_digest
    ):
        raise WorkflowRegistrationError("registration catalog is invalid")
    provider_ids = value.get("selected_capability_provider_ids", [])
    if (
        not isinstance(provider_ids, list)
        or not provider_ids
        and "selected_capability_provider_ids" in value
        or any(
            not isinstance(provider_id, str) or not provider_id
            for provider_id in provider_ids
        )
    ):
        raise WorkflowRegistrationError("registration catalog is invalid")
    return WorkflowRegistration(  # type: ignore[arg-type]
        **values,
        capability_requirements_digest=capability_requirements_digest,
        model_materials_digest=model_materials_digest,
        model_material_sets_digest=model_material_sets_digest,
        model_execution_binding_digest=model_execution_binding_digest,
        selected_capability_provider_ids=tuple(provider_ids),
        mcp_binding_id=mcp_binding_id,
        model_recipe_digest=model_recipe_digest,
        owner=owner,
    )


_RECORD_FIELDS = {
    "workflow_id",
    "registration_digest",
    "package_id",
    "revision_digest",
    "policy_digest",
    "profile_id",
    "profile_digest",
    "model_id",
}


def _nonempty(value: object, name: str) -> None:
    if not isinstance(value, str) or not value:
        raise WorkflowRegistrationError(f"{name} must be a non-empty string")


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
