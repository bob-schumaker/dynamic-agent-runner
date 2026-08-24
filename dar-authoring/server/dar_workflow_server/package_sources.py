"""Human-selected local package sources for the DAR authoring control plane."""

from __future__ import annotations

import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

from dar_workflow_server.profiles import InstallationIdentityProvider
from dar_workflow_server.state import OpaqueRecordError, PrivateStateStore


class PackageSourceSelectionError(ValueError):
    """Raised when a selected package directory is outside the trusted boundary."""


class PackageSourceSelectionPolicy:
    """Issue a source handle only for a human-selected no-follow directory."""

    def __init__(self, *, allowed_root: Path | None, store: PrivateStateStore) -> None:
        self._allowed_root = allowed_root
        self._store = store
        self._identity = InstallationIdentityProvider()

    def select_directory(self, path: Path, *, now: datetime) -> str:
        """Validate a configured directory selection and return only an opaque ID."""

        root = self._validated_allowed_root()
        candidate = _canonical_path(path, "package directory")
        try:
            candidate.relative_to(root)
        except ValueError as error:
            raise PackageSourceSelectionError(
                "package directory is outside the allowed root"
            ) from error
        _validate_no_follow_directory(candidate, "package directory")
        try:
            return self._store.issue(
                kind="package_source",
                owner=self._identity.principal,
                payload={"source_type": "directory", "source_path": str(candidate)},
                expires_at=now.astimezone(UTC) + timedelta(minutes=5),
                now=now,
            )
        except OpaqueRecordError as error:
            raise PackageSourceSelectionError(str(error)) from error

    def _validated_allowed_root(self) -> Path:
        if self._allowed_root is None:
            raise PackageSourceSelectionError("package allowed root is not configured")
        root = _canonical_path(self._allowed_root, "package allowed root")
        _validate_no_follow_directory(root, "package allowed root")
        return root


def _canonical_path(path: Path, name: str) -> Path:
    if not path.is_absolute() or "." in path.parts or ".." in path.parts:
        raise PackageSourceSelectionError(f"{name} must be an absolute canonical path")
    return path


def _validate_no_follow_directory(path: Path, name: str) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError as error:
            raise PackageSourceSelectionError(f"{name} does not exist") from error
        if stat.S_ISLNK(mode):
            raise PackageSourceSelectionError(f"{name} contains a symlink")
        if not stat.S_ISDIR(mode):
            raise PackageSourceSelectionError(f"{name} is not a directory")
