"""Human-controlled ingestion of local files into sealed workspace artifacts."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from dynamic_agent_runner.sandbox_workspace import (
    SandboxWorkspaceError,
    copy_regular_file_no_follow,
    create_private_workspace,
)

from dar_workflow_server.state import OpaqueRecordError, PrivateStateStore


class WorkspaceIngressError(ValueError):
    """Raised when a caller-selected file cannot become a workspace artifact."""


@dataclass(frozen=True)
class WorkspaceIngressPolicy:
    """Trusted workflow registration constraints for one file artifact."""

    workflow_id: str
    registration_digest: str
    accepted_roles: tuple[str, ...]
    accepted_media_types: tuple[str, ...]


@dataclass(frozen=True)
class WorkspaceInputArtifact:
    """Public opaque receipt for a copied workspace input."""

    artifact_id: str
    content_hash: str
    byte_count: int
    expires_at: datetime


@dataclass(frozen=True)
class StoredWorkspaceInputArtifact:
    """Private artifact binding available only after registration verification."""

    artifact_id: str
    content_path: Path
    content_hash: str
    byte_count: int
    role: str
    media_type: str


class WorkspaceIngressService:
    """Copy trusted caller files into fresh, registration-bound private workspaces."""

    def __init__(
        self,
        *,
        input_root: Path,
        private_workspace_parent: Path,
        store: PrivateStateStore,
        owner: str,
        max_file_bytes: int,
        artifact_ttl: timedelta,
    ) -> None:
        _require_absolute_directory(input_root, label="input root")
        _require_absolute_directory(
            private_workspace_parent, label="private workspace parent"
        )
        if not isinstance(owner, str) or not owner:
            raise WorkspaceIngressError("artifact owner is invalid")
        if (
            not isinstance(max_file_bytes, int)
            or isinstance(max_file_bytes, bool)
            or max_file_bytes <= 0
        ):
            raise WorkspaceIngressError("maximum file bytes is invalid")
        if artifact_ttl <= timedelta():
            raise WorkspaceIngressError("artifact lifetime is invalid")
        self._input_root = input_root
        self._private_workspace_parent = private_workspace_parent
        self._store = store
        self._owner = owner
        self._max_file_bytes = max_file_bytes
        self._artifact_ttl = artifact_ttl

    def ingress(
        self,
        *,
        source_path: Path,
        role: str,
        media_type: str,
        policy: WorkspaceIngressPolicy,
        now: datetime,
    ) -> WorkspaceInputArtifact:
        """Create an opaque artifact after every trusted-boundary check passes."""

        _validate_policy(policy)
        if role not in policy.accepted_roles:
            raise WorkspaceIngressError("artifact role is not accepted")
        if media_type not in policy.accepted_media_types:
            raise WorkspaceIngressError("artifact media type is not accepted")
        source_relative_path = _source_relative_path(source_path, self._input_root)
        try:
            workspace = create_private_workspace(self._private_workspace_parent)
            copied = copy_regular_file_no_follow(
                source_root=self._input_root,
                source_relative_path=source_relative_path,
                workspace_root=workspace.root,
                destination_name="content",
                max_bytes=self._max_file_bytes,
            )
            expires_at = now.astimezone(UTC) + self._artifact_ttl
            artifact_id = self._store.issue(
                kind="workspace_input_artifact",
                owner=self._owner,
                payload={
                    "workflow_id": policy.workflow_id,
                    "registration_digest": policy.registration_digest,
                    "workspace_relative_path": workspace.relative_path,
                    "content_relative_path": copied.relative_path,
                    "content_hash": copied.content_hash,
                    "byte_count": copied.byte_count,
                    "role": role,
                    "media_type": media_type,
                },
                expires_at=expires_at,
                now=now,
            )
        except (SandboxWorkspaceError, OpaqueRecordError) as error:
            raise WorkspaceIngressError(
                "workspace input artifact is unavailable"
            ) from error
        return WorkspaceInputArtifact(
            artifact_id=artifact_id,
            content_hash=copied.content_hash,
            byte_count=copied.byte_count,
            expires_at=expires_at,
        )

    def load(
        self,
        artifact_id: str,
        *,
        workflow_id: str,
        registration_digest: str,
        now: datetime,
    ) -> StoredWorkspaceInputArtifact:
        """Resolve a private artifact only for its exact registered workflow."""

        try:
            record = self._store.load(
                artifact_id,
                expected_kind="workspace_input_artifact",
                owner=self._owner,
                now=now,
            )
        except OpaqueRecordError as error:
            raise WorkspaceIngressError(
                "workspace input artifact is unavailable"
            ) from error
        payload = record.payload
        if (
            payload.get("workflow_id") != workflow_id
            or payload.get("registration_digest") != registration_digest
        ):
            raise WorkspaceIngressError(
                "workspace input artifact does not match registration"
            )
        return _stored_artifact(
            artifact_id,
            payload,
            private_workspace_parent=self._private_workspace_parent,
        )


def _require_absolute_directory(path: Path, *, label: str) -> None:
    if not path.is_absolute() or "." in path.parts or ".." in path.parts:
        raise WorkspaceIngressError(f"{label} must be an absolute canonical path")
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError as error:
        raise WorkspaceIngressError(f"{label} is unavailable") from error
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise WorkspaceIngressError(f"{label} is unavailable")


def _source_relative_path(source_path: Path, input_root: Path) -> str:
    if (
        not source_path.is_absolute()
        or "." in source_path.parts
        or ".." in source_path.parts
    ):
        raise WorkspaceIngressError("source path is outside the configured input root")
    try:
        relative = source_path.relative_to(input_root)
    except ValueError as error:
        raise WorkspaceIngressError(
            "source path is outside the configured input root"
        ) from error
    if not relative.parts:
        raise WorkspaceIngressError("source path is outside the configured input root")
    return relative.as_posix()


def _validate_policy(policy: WorkspaceIngressPolicy) -> None:
    if (
        not isinstance(policy.workflow_id, str)
        or not policy.workflow_id
        or not _is_digest(policy.registration_digest)
        or not policy.accepted_roles
        or not policy.accepted_media_types
        or any(
            not isinstance(value, str) or not value for value in policy.accepted_roles
        )
        or any(
            not isinstance(value, str) or not value
            for value in policy.accepted_media_types
        )
    ):
        raise WorkspaceIngressError("workspace ingress policy is invalid")


def _stored_artifact(
    artifact_id: str,
    payload: dict[str, object],
    *,
    private_workspace_parent: Path,
) -> StoredWorkspaceInputArtifact:
    required = {
        "workflow_id",
        "registration_digest",
        "workspace_relative_path",
        "content_relative_path",
        "content_hash",
        "byte_count",
        "role",
        "media_type",
    }
    if set(payload) != required:
        raise WorkspaceIngressError("workspace input artifact is invalid")
    workspace_relative_path = payload["workspace_relative_path"]
    content_relative_path = payload["content_relative_path"]
    content_hash = payload["content_hash"]
    byte_count = payload["byte_count"]
    role = payload["role"]
    media_type = payload["media_type"]
    if (
        not isinstance(workspace_relative_path, str)
        or not isinstance(content_relative_path, str)
        or not isinstance(content_hash, str)
        or not isinstance(byte_count, int)
        or isinstance(byte_count, bool)
        or byte_count < 0
        or not isinstance(role, str)
        or not isinstance(media_type, str)
        or not workspace_relative_path.startswith("workspace-")
        or content_relative_path != "content"
        or not content_hash.startswith("sha256:")
    ):
        raise WorkspaceIngressError("workspace input artifact is invalid")
    content_path = (
        private_workspace_parent / workspace_relative_path / content_relative_path
    )
    return StoredWorkspaceInputArtifact(
        artifact_id=artifact_id,
        content_path=content_path,
        content_hash=content_hash,
        byte_count=byte_count,
        role=role,
        media_type=media_type,
    )


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
