"""Host-owned, opaque package-output directories for DAR authoring."""

from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath

from dynamic_agent_runner.workflow_host.state import (
    OpaqueRecordError,
    PrivateStateStore,
)


class AuthoringOutputError(ValueError):
    """Raised when an authoring output operation cannot stay contained."""


@dataclass(frozen=True)
class AuthoringOutputReceipt:
    """Content-free identity for one host-owned package output directory."""

    output_id: str
    package_name: str
    expires_at: datetime


@dataclass(frozen=True)
class AuthoredFileReceipt:
    """Redacted record of one atomically written authored package file."""

    relative_path: str
    content_hash: str
    byte_count: int


class AuthoringOutputService:
    """Create and write only opaque, configured-root package outputs."""

    def __init__(
        self,
        *,
        store: PrivateStateStore,
        owner: str,
        output_root: Path,
        max_file_bytes: int,
        output_ttl: timedelta,
    ) -> None:
        if not isinstance(owner, str) or not owner:
            raise AuthoringOutputError("authoring output owner is invalid")
        if (
            not isinstance(max_file_bytes, int)
            or isinstance(max_file_bytes, bool)
            or max_file_bytes <= 0
        ):
            raise AuthoringOutputError("authoring output byte limit is invalid")
        if output_ttl <= timedelta():
            raise AuthoringOutputError("authoring output lifetime is invalid")
        _validate_absolute_path(output_root, "authoring output root")
        self._store = store
        self._owner = owner
        self._output_root = output_root
        self._max_file_bytes = max_file_bytes
        self._output_ttl = output_ttl

    def create(self, *, package_name: str, now: datetime) -> AuthoringOutputReceipt:
        """Create one empty package directory and return its opaque identity."""

        _validate_package_name(package_name)
        issued_at = _as_utc(now)
        root_descriptor = _open_directory(self._output_root)
        try:
            try:
                os.mkdir(package_name, mode=0o700, dir_fd=root_descriptor)
            except FileExistsError as error:
                raise AuthoringOutputError(
                    "authoring package already exists"
                ) from error
        finally:
            os.close(root_descriptor)
        expires_at = issued_at + self._output_ttl
        try:
            output_id = self._store.issue(
                kind="authoring_output",
                owner=self._owner,
                payload={"format_version": 1, "package_name": package_name},
                expires_at=expires_at,
                now=issued_at,
            )
        except OpaqueRecordError as error:
            try:
                (self._output_root / package_name).rmdir()
            except OSError:
                pass
            raise AuthoringOutputError("authoring output is unavailable") from error
        return AuthoringOutputReceipt(output_id, package_name, expires_at)

    def write_file(
        self,
        *,
        output_id: str,
        relative_path: str,
        content: str,
        now: datetime,
    ) -> AuthoredFileReceipt:
        """Atomically replace one contained UTF-8 package file."""

        package_name = self._package_name(output_id, now=now)
        path = _relative_file_path(relative_path)
        if not isinstance(content, str):
            raise AuthoringOutputError("authoring output content is invalid")
        body = content.encode("utf-8")
        if len(body) > self._max_file_bytes:
            raise AuthoringOutputError("authoring output exceeds the byte limit")
        descriptor = _open_output_directory(self._output_root, package_name)
        try:
            _write_relative_file(descriptor, path, body)
        except OSError as error:
            raise AuthoringOutputError("authoring output is unavailable") from error
        finally:
            os.close(descriptor)
        return AuthoredFileReceipt(
            relative_path=path.as_posix(),
            content_hash=hashlib.sha256(body).hexdigest(),
            byte_count=len(body),
        )

    def package_path(self, output_id: str, *, now: datetime) -> Path:
        """Return the validated output path for host finalization only."""

        package_name = self._package_name(output_id, now=now)
        descriptor = _open_output_directory(self._output_root, package_name)
        os.close(descriptor)
        return self._output_root / package_name

    def _package_name(self, output_id: str, *, now: datetime) -> str:
        try:
            record = self._store.load(
                output_id,
                expected_kind="authoring_output",
                owner=self._owner,
                now=_as_utc(now),
            )
            package_name = record.payload.get("package_name")
        except OpaqueRecordError as error:
            raise AuthoringOutputError("authoring output is unavailable") from error
        try:
            _validate_package_name(package_name)
        except AuthoringOutputError as error:
            raise AuthoringOutputError("authoring output is unavailable") from error
        assert isinstance(package_name, str)
        return package_name


def _validate_package_name(value: object) -> None:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 64
        or value.startswith(".")
        or any(
            character
            not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            for character in value
        )
    ):
        raise AuthoringOutputError("authoring package name is invalid")


def _relative_file_path(value: object) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise AuthoringOutputError("authoring output path is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or any(
        part in {"", ".", ".."} or part.startswith(".") for part in path.parts
    ):
        raise AuthoringOutputError("authoring output path is invalid")
    return path


def _validate_absolute_path(path: Path, name: str) -> None:
    if not path.is_absolute() or "." in path.parts or ".." in path.parts:
        raise AuthoringOutputError(f"{name} is invalid")


def _open_directory(path: Path) -> int:
    _validate_absolute_path(path, "authoring output root")
    descriptor = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            next_descriptor = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
    except OSError as error:
        os.close(descriptor)
        raise AuthoringOutputError("authoring output is unavailable") from error
    return descriptor


def _open_output_directory(output_root: Path, package_name: str) -> int:
    root_descriptor = _open_directory(output_root)
    try:
        return os.open(
            package_name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=root_descriptor,
        )
    except OSError as error:
        raise AuthoringOutputError("authoring output is unavailable") from error
    finally:
        os.close(root_descriptor)


def _write_relative_file(
    root_descriptor: int, relative_path: PurePosixPath, body: bytes
) -> None:
    descriptor = os.dup(root_descriptor)
    try:
        for part in relative_path.parts[:-1]:
            try:
                os.mkdir(part, mode=0o700, dir_fd=descriptor)
            except FileExistsError:
                pass
            next_descriptor = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
        filename = relative_path.name
        temporary = f".{filename}.{secrets.token_hex(16)}.tmp"
        temporary_descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=descriptor,
        )
        try:
            _write_all(temporary_descriptor, body)
            os.fsync(temporary_descriptor)
        finally:
            os.close(temporary_descriptor)
        os.replace(temporary, filename, src_dir_fd=descriptor, dst_dir_fd=descriptor)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_all(descriptor: int, body: bytes) -> None:
    offset = 0
    while offset < len(body):
        offset += os.write(descriptor, body[offset:])


def _as_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise AuthoringOutputError("authoring output time is invalid")
    return value.astimezone(UTC)
