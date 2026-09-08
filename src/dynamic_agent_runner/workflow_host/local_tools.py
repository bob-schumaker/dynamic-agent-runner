"""Bounded dispatch for reviewed deterministic workflow-local tool assets."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from dynamic_agent_runner import HostToolBinding


class LocalToolSandboxError(ValueError):
    """Raised when a local tool escapes its declared sealed boundary."""


LocalToolExecutor = Callable[[tuple[str, ...], bytes, int], bytes]


def execute_macos_sandbox_exec(
    command: tuple[str, ...], artifact_bytes: bytes, timeout_seconds: int
) -> bytes:
    """Run a reviewed test fixture through macOS ``sandbox-exec`` as-is.

    The permissive profile proves the platform execution handoff only. It is not
    the untrusted-tool isolation backend specified by local-tool hardening.
    """

    if not command or not all(isinstance(item, str) and item for item in command):
        raise LocalToolSandboxError("local tool command is invalid")
    try:
        result = subprocess.run(
            (
                "sandbox-exec",
                "-p",
                "(version 1) (allow default)",
                *command,
            ),
            check=True,
            input=artifact_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise LocalToolSandboxError("local tool execution failed") from error
    return result.stdout


@dataclass(frozen=True)
class DockerSandboxConfiguration:
    """Host-owned fixed limits for one digest-pinned Docker worker image."""

    image: str
    docker_executable: Path
    docker_host: str
    memory_bytes: int
    max_processes: int
    scratch_bytes: int
    max_output_bytes: int

    def __post_init__(self) -> None:
        repository, separator, digest = self.image.partition("@sha256:")
        if (
            not repository
            or not separator
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise LocalToolSandboxError("docker sandbox image is invalid")
        if (
            not isinstance(self.docker_executable, Path)
            or not self.docker_executable.is_absolute()
            or ".." in self.docker_executable.parts
        ):
            raise LocalToolSandboxError("docker sandbox executable is invalid")
        if (
            not self.docker_host.startswith("unix:///")
            or "\n" in self.docker_host
            or "\x00" in self.docker_host
        ):
            raise LocalToolSandboxError("docker sandbox endpoint is invalid")
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
            for value in (
                self.memory_bytes,
                self.max_processes,
                self.scratch_bytes,
                self.max_output_bytes,
            )
        ):
            raise LocalToolSandboxError("docker sandbox limits are invalid")


class DockerSandboxExecutor:
    """Execute one declared asset in a capability-reduced Docker worker."""

    def __init__(
        self,
        configuration: DockerSandboxConfiguration,
        *,
        execute: Callable[..., object] = subprocess.run,
    ) -> None:
        if not isinstance(configuration, DockerSandboxConfiguration) or not callable(
            execute
        ):
            raise LocalToolSandboxError("docker sandbox executor is unavailable")
        self._configuration = configuration
        self._execute = execute

    def __call__(
        self, command: tuple[str, ...], artifact_bytes: bytes, timeout_seconds: int
    ) -> bytes:
        if (
            len(command) != 1
            or not isinstance(command[0], str)
            or not command[0]
            or not isinstance(artifact_bytes, bytes)
            or not isinstance(timeout_seconds, int)
            or isinstance(timeout_seconds, bool)
            or timeout_seconds <= 0
        ):
            raise LocalToolSandboxError("docker sandbox request is invalid")
        asset = Path(command[0])
        if not asset.is_absolute():
            raise LocalToolSandboxError("docker sandbox request is invalid")
        docker_command = (
            str(self._configuration.docker_executable),
            "run",
            "--rm",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            f"--pids-limit={self._configuration.max_processes}",
            f"--memory={self._configuration.memory_bytes}",
            "--tmpfs="
            f"/dar/scratch:rw,noexec,nosuid,size={self._configuration.scratch_bytes},mode=1777",
            "--user=65534:65534",
            "--workdir=/dar/scratch",
            f"--mount=type=bind,src={asset},dst=/dar/asset,readonly",
            "--entrypoint=/dar/asset",
            self._configuration.image,
        )
        try:
            result = self._execute(
                docker_command,
                check=True,
                input=artifact_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=timeout_seconds,
                env={
                    "DOCKER_HOST": self._configuration.docker_host,
                    "HOME": "/nonexistent",
                    "PATH": "/usr/bin:/bin",
                },
            )
            output = result.stdout  # type: ignore[attr-defined]
        except (AttributeError, OSError, subprocess.SubprocessError) as error:
            raise LocalToolSandboxError("docker sandbox execution failed") from error
        if (
            not isinstance(output, bytes)
            or len(output) > self._configuration.max_output_bytes
        ):
            raise LocalToolSandboxError(
                "docker sandbox output exceeds the declared limit"
            )
        return output


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


def create_local_tool_binding(
    *,
    sandbox: LocalToolSandbox,
    definition: LocalToolDefinition,
    artifact_role: str,
    artifact_bytes: bytes,
) -> HostToolBinding:
    """Bind one sealed artifact to its declared local tool for this run only."""

    def handler(arguments: object) -> dict[str, object]:
        if arguments != {}:
            raise LocalToolSandboxError("local tool arguments are invalid")
        return sandbox.run(
            definition, artifact_role=artifact_role, artifact_bytes=artifact_bytes
        )

    return HostToolBinding(
        canonical_id=f"local:{definition.tool_id}",
        model_id=definition.tool_id,
        handler=handler,
        label=definition.tool_id,
        description="Run the workflow's declared deterministic local tool.",
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        side_effect="read",
        approval_required="no",
    )


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
        relative = candidate.relative_to(package_root)
        current = package_root
        for part in relative.parts:
            current /= part
            if stat.S_ISLNK(os.lstat(current).st_mode):
                raise LocalToolSandboxError("local tool asset is unavailable")
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(package_root)
        metadata = os.lstat(resolved)
    except (OSError, ValueError, LocalToolSandboxError) as error:
        raise LocalToolSandboxError("local tool asset is unavailable") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise LocalToolSandboxError("local tool asset is unavailable")
    return resolved


def _sandbox_literal(path: Path) -> str:
    value = str(path)
    if '"' in value or "\n" in value:
        raise LocalToolSandboxError("local tool sandbox path is invalid")
    return f'"{value}"'
