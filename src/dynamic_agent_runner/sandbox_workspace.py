"""Descriptor-relative, no-follow file ingress for private workspaces."""

from __future__ import annotations

import hashlib
import errno
import os
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Final


_READ_CHUNK_BYTES: Final = 65_536
_TEMPORARY_PREFIX: Final = ".dar-ingress-"


class SandboxWorkspaceError(ValueError):
    """Raised when a workspace ingress operation cannot safely proceed."""


@dataclass(frozen=True)
class NoFollowCopyResult:
    """Redaction-safe metadata for one private workspace copy."""

    relative_path: str
    content_hash: str
    byte_count: int


def copy_regular_file_no_follow(
    *,
    source_root: str | Path,
    source_relative_path: str,
    workspace_root: str | Path,
    destination_name: str,
    max_bytes: int,
) -> NoFollowCopyResult:
    """Copy one regular file through descriptor-relative no-follow handles.

    Both roots are trusted host inputs. The source is selected only by a
    canonical relative path, and the destination must be an absent single file
    name in a fresh private workspace.
    """

    _require_posix_no_follow_support()
    source_parts = _relative_path_parts(source_relative_path, label="source path")
    destination_parts = _relative_path_parts(destination_name, label="destination name")
    if len(destination_parts) != 1:
        raise SandboxWorkspaceError(
            "destination name must be one relative path segment"
        )
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 0:
        raise SandboxWorkspaceError("maximum byte count must be a nonnegative integer")

    source_root_fd = _open_absolute_directory(source_root, label="source root")
    workspace_root_fd = _open_absolute_directory(workspace_root, label="workspace root")
    source_fd: int | None = None
    temporary_name: str | None = None
    temporary_fd: int | None = None
    try:
        source_fd = _open_regular_file(
            source_root_fd, source_parts, label="source path"
        )
        _reject_existing_entry(workspace_root_fd, destination_parts[0])
        temporary_name, temporary_fd = _create_temporary_file(workspace_root_fd)
        content_hash, byte_count = _copy_open_file(
            source_fd, temporary_fd, max_bytes=max_bytes
        )
        os.fsync(temporary_fd)
        os.close(temporary_fd)
        temporary_fd = None
        os.replace(
            temporary_name,
            destination_parts[0],
            src_dir_fd=workspace_root_fd,
            dst_dir_fd=workspace_root_fd,
        )
        temporary_name = None
        os.fsync(workspace_root_fd)
        return NoFollowCopyResult(
            relative_path=destination_parts[0],
            content_hash=f"sha256:{content_hash}",
            byte_count=byte_count,
        )
    except OSError as exc:
        raise SandboxWorkspaceError(
            "workspace ingress filesystem operation failed"
        ) from exc
    finally:
        if temporary_fd is not None:
            os.close(temporary_fd)
        if temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=workspace_root_fd)
            except FileNotFoundError:
                pass
        if source_fd is not None:
            os.close(source_fd)
        os.close(workspace_root_fd)
        os.close(source_root_fd)


def _require_posix_no_follow_support() -> None:
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        raise SandboxWorkspaceError(
            "descriptor-relative no-follow support is unavailable"
        )


def _relative_path_parts(value: str, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, str) or not value:
        raise SandboxWorkspaceError(f"{label} must be a nonempty relative path")
    if "\\" in value or "\x00" in value:
        raise SandboxWorkspaceError(f"{label} must be a canonical relative path")
    parts = tuple(value.split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        raise SandboxWorkspaceError(f"{label} must be a canonical relative path")
    if value.startswith("/"):
        raise SandboxWorkspaceError(f"{label} must be a canonical relative path")
    return parts


def _open_absolute_directory(root: str | Path, *, label: str) -> int:
    path = Path(root)
    if not path.is_absolute():
        raise SandboxWorkspaceError(f"{label} must be absolute")
    root_fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    current_fd = root_fd
    try:
        for part in path.parts[1:]:
            _reject_symlink(current_fd, part, label=label)
            next_fd = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=current_fd,
            )
            if current_fd != root_fd:
                os.close(current_fd)
            current_fd = next_fd
        _require_directory(current_fd, label=label)
        if current_fd == root_fd:
            return current_fd
        os.close(root_fd)
        return current_fd
    except OSError as exc:
        if current_fd != root_fd:
            os.close(current_fd)
        os.close(root_fd)
        if exc.errno == errno.ELOOP:
            raise SandboxWorkspaceError(f"{label} contains a symlink") from exc
        raise SandboxWorkspaceError(f"{label} cannot be opened") from exc


def _require_directory(file_descriptor: int, *, label: str) -> None:
    if not stat.S_ISDIR(os.fstat(file_descriptor).st_mode):
        raise SandboxWorkspaceError(f"{label} is not a directory")


def _open_regular_file(root_fd: int, parts: tuple[str, ...], *, label: str) -> int:
    parent_fd = root_fd
    opened_parents: list[int] = []
    try:
        for part in parts[:-1]:
            _reject_symlink(parent_fd, part, label=label)
            child_fd = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=parent_fd,
            )
            opened_parents.append(child_fd)
            parent_fd = child_fd
        _reject_symlink(parent_fd, parts[-1], label=label)
        file_descriptor = os.open(
            parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd
        )
        mode = os.fstat(file_descriptor).st_mode
        if not stat.S_ISREG(mode):
            os.close(file_descriptor)
            raise SandboxWorkspaceError(f"{label} is not a regular file")
        return file_descriptor
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise SandboxWorkspaceError(f"{label} contains a symlink") from exc
        raise SandboxWorkspaceError(f"{label} cannot be opened") from exc
    finally:
        for descriptor in reversed(opened_parents):
            os.close(descriptor)


def _reject_existing_entry(root_fd: int, name: str) -> None:
    try:
        os.stat(name, dir_fd=root_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise SandboxWorkspaceError("workspace destination already exists")


def _reject_symlink(parent_fd: int, name: str, *, label: str) -> None:
    try:
        mode = os.stat(name, dir_fd=parent_fd, follow_symlinks=False).st_mode
    except FileNotFoundError:
        return
    if stat.S_ISLNK(mode):
        raise SandboxWorkspaceError(f"{label} contains a symlink")


def _create_temporary_file(root_fd: int) -> tuple[str, int]:
    for _ in range(16):
        name = f"{_TEMPORARY_PREFIX}{secrets.token_urlsafe(18)}"
        try:
            return name, os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=root_fd,
            )
        except FileExistsError:
            continue
    raise SandboxWorkspaceError("workspace temporary name allocation failed")


def _copy_open_file(
    source_fd: int, destination_fd: int, *, max_bytes: int
) -> tuple[str, int]:
    digest = hashlib.sha256()
    byte_count = 0
    while chunk := os.read(source_fd, _READ_CHUNK_BYTES):
        byte_count += len(chunk)
        if byte_count > max_bytes:
            raise SandboxWorkspaceError("source file exceeds maximum byte count")
        digest.update(chunk)
        _write_all(destination_fd, chunk)
    return digest.hexdigest(), byte_count


def _write_all(file_descriptor: int, content: bytes) -> None:
    remaining = memoryview(content)
    while remaining:
        written = os.write(file_descriptor, remaining)
        if written <= 0:
            raise SandboxWorkspaceError("workspace temporary write failed")
        remaining = remaining[written:]
