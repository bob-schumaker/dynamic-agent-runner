"""Private descriptor-relative staging for DAR package directories."""

from __future__ import annotations

import errno
import hashlib
import os
import secrets
import shutil
import stat
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dynamic_agent_runner import load_agent_package_workflow

from dar_workflow_server.profiles import InstallationIdentityProvider
from dar_workflow_server.state import OpaqueRecordError, PrivateStateStore


MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_PACKAGE_BYTES = 64 * 1024 * 1024
MAX_PACKAGE_FILES = 256
_READ_SIZE = 64 * 1024


class PackageStagingError(ValueError):
    """Raised when a selected package cannot be safely staged."""


@dataclass(frozen=True)
class StagedPackage:
    """An immutable private DAR-compatible package copy."""

    root: Path
    digest: str
    file_count: int
    byte_count: int


class PrivatePackageStager:
    """Copy a selected source directory through no-follow descriptors only."""

    def __init__(self, *, store: PrivateStateStore, private_root: Path) -> None:
        self._store = store
        self._private_root = private_root
        self._identity = InstallationIdentityProvider()

    def stage(self, source_handle: str, *, now: datetime) -> StagedPackage:
        """Stage, validate, and seal one directory selected by the local control plane."""

        source_root, source_path = self._source_paths(source_handle, now)
        private_root = _private_directory(self._private_root)
        temporary_root = private_root / f".stage-{secrets.token_hex(16)}"
        temporary_root.mkdir(mode=0o700)
        source_fd = -1
        try:
            source_fd = _open_directory_below(source_root, source_path)
            entries: list[tuple[str, str, int]] = []
            _copy_directory(
                source_fd,
                temporary_root,
                relative_path="",
                entries=entries,
            )
            digest, file_count, byte_count = _package_digest(entries)
            try:
                load_agent_package_workflow(str(temporary_root))
            except Exception as error:
                raise PackageStagingError(
                    "DAR validation failed for staged package"
                ) from error
            final_root = private_root / f"package-{digest}"
            if final_root.exists():
                shutil.rmtree(temporary_root)
            else:
                os.replace(temporary_root, final_root)
                _seal_tree(final_root)
            return StagedPackage(final_root, digest, file_count, byte_count)
        finally:
            if source_fd >= 0:
                os.close(source_fd)
            if temporary_root.exists():
                shutil.rmtree(temporary_root)

    def _source_paths(self, source_handle: str, now: datetime) -> tuple[Path, Path]:
        try:
            record = self._store.load(
                source_handle,
                expected_kind="package_source",
                owner=self._identity.principal,
                now=now,
            )
        except OpaqueRecordError as error:
            raise PackageStagingError(str(error)) from error
        payload = record.payload
        if payload.get("source_type") != "directory":
            raise PackageStagingError("package source is not a directory")
        root = _absolute_path(payload.get("source_root"), "package source root")
        path = _absolute_path(payload.get("source_path"), "package source path")
        try:
            path.relative_to(root)
        except ValueError as error:
            raise PackageStagingError(
                "package source path is outside its root"
            ) from error
        return root, path


def _private_directory(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    mode = os.lstat(path).st_mode
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise PackageStagingError("private staging root is not a directory")
    os.chmod(path, 0o700)
    return path


def _absolute_path(value: object, name: str) -> Path:
    if not isinstance(value, str):
        raise PackageStagingError(f"{name} is invalid")
    path = Path(value)
    if not path.is_absolute() or "." in path.parts or ".." in path.parts:
        raise PackageStagingError(f"{name} is invalid")
    return path


def _open_directory_below(root: Path, path: Path) -> int:
    try:
        relative_parts = path.relative_to(root).parts
    except ValueError as error:  # Defensive: callers already validate this binding.
        raise PackageStagingError("package source path is outside its root") from error
    descriptor = _open_absolute_directory(root)
    try:
        for part in relative_parts:
            child = _open_directory_at(descriptor, part)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _open_absolute_directory(path: Path) -> int:
    descriptor = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = _open_directory_at(descriptor, part)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _open_directory_at(parent_fd: int, name: str) -> int:
    try:
        return os.open(
            name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=parent_fd,
        )
    except OSError as error:
        if error.errno == errno.ELOOP or _is_symlink_at(parent_fd, name):
            raise PackageStagingError("package source contains a symlink") from error
        raise PackageStagingError("package source directory is unavailable") from error


def _is_symlink_at(parent_fd: int, name: str) -> bool:
    try:
        return stat.S_ISLNK(
            os.stat(name, dir_fd=parent_fd, follow_symlinks=False).st_mode
        )
    except OSError:
        return False


def _copy_directory(
    source_fd: int,
    destination: Path,
    *,
    relative_path: str,
    entries: list[tuple[str, str, int]],
) -> None:
    for name in sorted(os.listdir(source_fd)):
        try:
            source_stat = os.lstat(name, dir_fd=source_fd)
        except FileNotFoundError as error:
            raise PackageStagingError(
                "package source changed during staging"
            ) from error
        if stat.S_ISLNK(source_stat.st_mode):
            raise PackageStagingError("package source contains a symlink")
        child_relative_path = f"{relative_path}/{name}" if relative_path else name
        child_destination = destination / name
        if stat.S_ISDIR(source_stat.st_mode):
            child_destination.mkdir(mode=0o700)
            child_fd = _open_directory_at(source_fd, name)
            try:
                _copy_directory(
                    child_fd,
                    child_destination,
                    relative_path=child_relative_path,
                    entries=entries,
                )
            finally:
                os.close(child_fd)
        elif stat.S_ISREG(source_stat.st_mode):
            _copy_file(source_fd, name, child_destination, child_relative_path, entries)
        else:
            raise PackageStagingError("package source contains a non-regular entry")


def _copy_file(
    source_parent_fd: int,
    name: str,
    destination: Path,
    relative_path: str,
    entries: list[tuple[str, str, int]],
) -> None:
    try:
        source_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=source_parent_fd)
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise PackageStagingError("package source contains a symlink") from error
        raise PackageStagingError("package source changed during staging") from error
    try:
        source_stat = os.fstat(source_fd)
        if not stat.S_ISREG(source_stat.st_mode):
            raise PackageStagingError("package source contains a non-regular entry")
        if source_stat.st_size > MAX_FILE_BYTES:
            raise PackageStagingError("package source file exceeds size limit")
        destination_fd = os.open(
            destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        try:
            digest = hashlib.sha256()
            byte_count = 0
            while chunk := os.read(source_fd, _READ_SIZE):
                byte_count += len(chunk)
                if byte_count > MAX_FILE_BYTES:
                    raise PackageStagingError("package source file exceeds size limit")
                if sum(entry[2] for entry in entries) + byte_count > MAX_PACKAGE_BYTES:
                    raise PackageStagingError("package source exceeds size limit")
                digest.update(chunk)
                _write_all(destination_fd, chunk)
            entries.append((relative_path, digest.hexdigest(), byte_count))
            if len(entries) > MAX_PACKAGE_FILES:
                raise PackageStagingError("package source exceeds file limit")
        finally:
            os.close(destination_fd)
    finally:
        os.close(source_fd)


def _write_all(descriptor: int, value: bytes) -> None:
    offset = 0
    while offset < len(value):
        offset += os.write(descriptor, value[offset:])


def _package_digest(entries: list[tuple[str, str, int]]) -> tuple[str, int, int]:
    digest = hashlib.sha256()
    byte_count = 0
    for path, file_digest, size in entries:
        digest.update(f"{path}\0{file_digest}\0{size}\n".encode("utf-8"))
        byte_count += size
    return digest.hexdigest(), len(entries), byte_count


def _seal_tree(root: Path) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        os.chmod(path, 0o500 if path.is_dir() else 0o400)
    os.chmod(root, 0o500)
