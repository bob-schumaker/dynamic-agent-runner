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


class WorkflowRegistrationService:
    """Bind eligible policies only to the human-configured strict local profile."""

    def __init__(
        self,
        *,
        profiles: LocalModelProfileControlPlane,
        configured_profile_id: str,
        root: Path,
    ) -> None:
        self._profiles = profiles
        self._configured_profile_id = configured_profile_id
        self._root = root
        self._path = root / "registrations.json"
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
    ) -> WorkflowRegistration:
        """Create or retrieve a local alias for an eligible strict-local policy."""

        _nonempty(workflow_id, "workflow_id")
        if capability_resolution.status != "eligible":
            raise WorkflowRegistrationError(
                "policy capability resolution is unavailable"
            )
        profile = self._configured_profile()
        self._validate_profile(policy, profile)
        registration = _registration_from(policy, profile, workflow_id)
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
    policy: WorkflowPolicy, profile: LocalModelProfile, workflow_id: str
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
    )


def _to_mapping(registration: WorkflowRegistration) -> dict[str, str]:
    return {
        "workflow_id": registration.workflow_id,
        "registration_digest": registration.registration_digest,
        "package_id": registration.package_id,
        "revision_digest": registration.revision_digest,
        "policy_digest": registration.policy_digest,
        "profile_id": registration.profile_id,
        "model_id": registration.model_id,
    }


def _from_mapping(value: object) -> WorkflowRegistration:
    if not isinstance(value, Mapping):
        raise WorkflowRegistrationError("registration catalog is invalid")
    try:
        values = {key: value[key] for key in _RECORD_FIELDS}
    except KeyError as error:
        raise WorkflowRegistrationError("registration catalog is invalid") from error
    if set(value) != _RECORD_FIELDS or any(
        not isinstance(item, str) or not item for item in values.values()
    ):
        raise WorkflowRegistrationError("registration catalog is invalid")
    return WorkflowRegistration(**values)  # type: ignore[arg-type]


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
