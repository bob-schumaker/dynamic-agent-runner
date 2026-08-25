"""Fail-closed macOS isolation for M4.4 clean authoring actors."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
from typing import Mapping


class M44IsolationError(ValueError):
    """Raised when an M4.4 clean actor cannot be isolated safely."""


_ALLOWED_ENVIRONMENT_KEYS = frozenset(
    {
        "DAR_AUTHORING_MCP_MODE",
        "DAR_AUTHORING_MATERIAL_SET_ID",
        "DAR_AUTHORING_OUTPUT_ID",
        "DAR_AUTHORING_PACKAGE_NAME",
        "LANG",
        "LC_CTYPE",
        "PATH",
        "TZ",
    }
)
_RUNTIME_READ_ROOTS = (Path("/System"), Path("/usr"), Path("/bin"))


@dataclass(frozen=True)
class M44IsolationRequest:
    """One hermetic child process with explicit read and write capabilities."""

    command: tuple[str, ...]
    read_only_roots: tuple[Path, ...]
    writable_root: Path
    working_directory: Path
    environment: Mapping[str, str]

    def __post_init__(self) -> None:
        _validate_command(self.command)
        _validate_directory(self.writable_root, "writable root")
        _validate_directory(self.working_directory, "working directory")
        if not _contained(self.working_directory, self.writable_root):
            raise M44IsolationError("working directory is outside writable root")
        if not self.read_only_roots:
            raise M44IsolationError("read-only roots are invalid")
        for root in self.read_only_roots:
            _validate_directory(root, "read-only root")
            if _overlaps(root, self.writable_root):
                raise M44IsolationError("read-only and writable roots overlap")
        if len(set(self.read_only_roots)) != len(self.read_only_roots):
            raise M44IsolationError("read-only roots are invalid")
        _validate_environment(self.environment)


class MacOSSeatbeltIsolation:
    """Use Seatbelt only after a live probe proves it can enforce policy."""

    def available(self) -> bool:
        """Return whether Seatbelt is available and accepts a restrictive profile."""

        if platform.system() != "Darwin":
            return False
        executable = shutil.which("sandbox-exec")
        if executable is None:
            return False
        try:
            result = subprocess.run(
                [
                    executable,
                    "-p",
                    "(version 1) (deny default) (allow process-exec)",
                    "/usr/bin/true",
                ],
                capture_output=True,
                check=False,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0

    def profile(self, request: M44IsolationRequest) -> str:
        """Render the deny-by-default Seatbelt profile for one child process."""

        _validate_request(request)
        read_roots = (*_RUNTIME_READ_ROOTS, *request.read_only_roots)
        read_rules = " ".join(_subpath(root) for root in read_roots)
        return "\n".join(
            (
                "(version 1)",
                "(deny default)",
                "(allow process-exec)",
                "(allow process-fork)",
                f"(allow file-read* {read_rules})",
                f"(allow file-write* {_subpath(request.writable_root)})",
            )
        )

    def run(
        self, request: M44IsolationRequest, *, timeout: float = 300
    ) -> subprocess.CompletedProcess[str]:
        """Run one child only when the OS has accepted the isolation backend."""

        _validate_request(request)
        if timeout <= 0:
            raise M44IsolationError("timeout is invalid")
        if not self.available():
            raise M44IsolationError("macOS Seatbelt isolation is unavailable")
        executable = shutil.which("sandbox-exec")
        if executable is None:  # Defensive: availability is intentionally rechecked.
            raise M44IsolationError("macOS Seatbelt isolation is unavailable")
        try:
            return subprocess.run(
                [executable, "-p", self.profile(request), *request.command],
                capture_output=True,
                check=False,
                cwd=request.working_directory,
                env=dict(request.environment),
                text=True,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise M44IsolationError("isolated child could not be run") from error


def _validate_request(request: object) -> None:
    if not isinstance(request, M44IsolationRequest):
        raise M44IsolationError("isolation request is invalid")


def _validate_command(command: object) -> None:
    if (
        not isinstance(command, tuple)
        or not command
        or any(not isinstance(item, str) or not item for item in command)
    ):
        raise M44IsolationError("command is invalid")
    executable = Path(command[0])
    if not executable.is_absolute() or executable.is_symlink():
        raise M44IsolationError("command is invalid")
    try:
        mode = os.lstat(executable).st_mode
    except OSError as error:
        raise M44IsolationError("command is unavailable") from error
    if not stat.S_ISREG(mode) or not os.access(executable, os.X_OK):
        raise M44IsolationError("command is unavailable")


def _validate_directory(path: object, label: str) -> None:
    if not isinstance(path, Path) or not path.is_absolute():
        raise M44IsolationError(f"{label} is invalid")
    if path.is_symlink():
        raise M44IsolationError(f"{label} is a symlink")
    try:
        mode = os.lstat(path).st_mode
    except OSError as error:
        raise M44IsolationError(f"{label} is unavailable") from error
    if not stat.S_ISDIR(mode):
        raise M44IsolationError(f"{label} is unavailable")


def _validate_environment(environment: object) -> None:
    if not isinstance(environment, Mapping) or not environment:
        raise M44IsolationError("environment is invalid")
    for key, value in environment.items():
        if (
            not isinstance(key, str)
            or key not in _ALLOWED_ENVIRONMENT_KEYS
            or not isinstance(value, str)
        ):
            raise M44IsolationError("environment is invalid")


def _contained(path: Path, root: Path) -> bool:
    return path == root or path.is_relative_to(root)


def _overlaps(first: Path, second: Path) -> bool:
    return _contained(first, second) or _contained(second, first)


def _subpath(path: Path) -> str:
    escaped = str(path).replace("\\", "\\\\").replace('"', '\\"')
    return f'(subpath "{escaped}")'
