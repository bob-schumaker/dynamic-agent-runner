"""Bounded dispatch for reviewed deterministic workflow-local tool assets."""

from __future__ import annotations

import os
import json
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


class LocalToolSandboxError(ValueError):
    """Raised when a local tool escapes its declared sealed boundary."""


LocalToolExecutor = Callable[[tuple[str, ...], bytes, int], bytes]


def macos_sandbox_profile(
    *, asset_path: Path, input_path: Path, output_path: Path
) -> str:
    """Return a deny-by-default macOS Sandbox profile for one local tool run."""

    paths = (asset_path, input_path, output_path)
    if any(not path.is_absolute() for path in paths):
        raise LocalToolSandboxError("local tool sandbox paths must be absolute")
    escaped = tuple(_sandbox_literal(path) for path in paths)
    return "\n".join(
        (
            "(version 1)",
            "(deny default)",
            "(deny network*)",
            f"(allow file-read-data (literal {escaped[0]}))",
            f"(allow file-read-data (literal {escaped[1]}))",
            f"(allow file-write* (literal {escaped[2]}))",
            f"(allow process-exec (literal {escaped[0]}))",
        )
    )


@dataclass(frozen=True)
class LocalToolDefinition:
    """One package-reviewed deterministic executable and its finite limits."""

    tool_id: str
    asset_path: Path
    accepted_artifact_role: str
    max_input_bytes: int
    max_output_bytes: int
    timeout_seconds: int

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or not value
            for value in (self.tool_id, self.accepted_artifact_role)
        ):
            raise LocalToolSandboxError("local tool definition is invalid")
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
            for value in (
                self.max_input_bytes,
                self.max_output_bytes,
                self.timeout_seconds,
            )
        ):
            raise LocalToolSandboxError("local tool limits are invalid")


class LocalToolSandbox:
    """Dispatch only package-owned assets through a host-supplied sealed executor."""

    def __init__(self, *, package_root: Path, execute: LocalToolExecutor) -> None:
        if not callable(execute):
            raise LocalToolSandboxError("local tool executor is unavailable")
        self._package_root = _directory(package_root)
        self._execute = execute

    def run(
        self,
        definition: LocalToolDefinition,
        *,
        artifact_role: str,
        artifact_bytes: bytes,
    ) -> dict[str, object]:
        """Run one declared package asset with one sealed bounded artifact."""

        if artifact_role != definition.accepted_artifact_role:
            raise LocalToolSandboxError("local tool artifact role is not accepted")
        if (
            not isinstance(artifact_bytes, bytes)
            or len(artifact_bytes) > definition.max_input_bytes
        ):
            raise LocalToolSandboxError("local tool input exceeds the declared limit")
        asset = _asset_path(definition.asset_path, package_root=self._package_root)
        try:
            output = self._execute(
                (str(asset),), artifact_bytes, definition.timeout_seconds
            )
        except Exception as error:
            raise LocalToolSandboxError("local tool execution failed") from error
        if not isinstance(output, bytes) or len(output) > definition.max_output_bytes:
            raise LocalToolSandboxError("local tool output exceeds the declared limit")
        try:
            evidence = json.loads(output.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise LocalToolSandboxError("local tool evidence is invalid") from error
        if not isinstance(evidence, dict):
            raise LocalToolSandboxError("local tool evidence is invalid")
        return evidence


def _directory(path: Path) -> Path:
    try:
        metadata = os.lstat(path)
    except OSError as error:
        raise LocalToolSandboxError("local tool package is unavailable") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise LocalToolSandboxError("local tool package is unavailable")
    return path.resolve()


def _asset_path(asset_path: Path, *, package_root: Path) -> Path:
    candidate = asset_path if asset_path.is_absolute() else package_root / asset_path
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(package_root)
        metadata = os.lstat(resolved)
    except (OSError, ValueError) as error:
        raise LocalToolSandboxError("local tool asset is unavailable") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise LocalToolSandboxError("local tool asset is unavailable")
    return resolved


def _sandbox_literal(path: Path) -> str:
    value = str(path)
    if '"' in value or "\n" in value:
        raise LocalToolSandboxError("local tool sandbox path is invalid")
    return f'"{value}"'
