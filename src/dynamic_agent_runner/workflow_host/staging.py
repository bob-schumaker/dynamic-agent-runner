"""Private descriptor-relative staging for DAR package directories."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import secrets
import shutil
import stat
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from pathlib import PurePosixPath

import yaml

from dynamic_agent_runner import load_agent_package_workflow

from dynamic_agent_runner.workflow_host.profiles import InstallationIdentityProvider
from dynamic_agent_runner.workflow_host.package_signatures import (
    PackageSignatureError,
    verify_manifest,
)
from dynamic_agent_runner.workflow_host.state import (
    OpaqueRecordError,
    PrivateStateStore,
)


MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_PACKAGE_BYTES = 64 * 1024 * 1024
MAX_PACKAGE_FILES = 256
MAX_ZIP_COMPRESSION_RATIO = 100
_READ_SIZE = 64 * 1024
_PACKAGE_MANIFEST_NAME = "package-manifest.json"
_PACKAGE_SIGNATURE_NAME = "package-signature.json"
_HUMAN_SELECTED_LOCAL = "human_selected_local"
_PUBLISHER_SIGNATURE = "publisher_signature"


class PackageStagingError(ValueError):
    """Raised when a selected package cannot be safely staged."""


@dataclass(frozen=True)
class StagedPackage:
    """An immutable private DAR-compatible package copy."""

    root: Path
    digest: str
    file_count: int
    byte_count: int
    trust: str
    publisher_key_id: str | None = None


class PrivatePackageStager:
    """Stage a selected directory or safely extracted ZIP through one copy path."""

    def __init__(
        self,
        *,
        store: PrivateStateStore,
        private_root: Path,
        trusted_keys: Callable[[], Mapping[str, bytes]] | None = None,
    ) -> None:
        self._store = store
        self._private_root = private_root
        self._identity = InstallationIdentityProvider()
        self._trusted_keys = trusted_keys or (lambda: {})

    def stage(self, source_handle: str, *, now: datetime) -> StagedPackage:
        """Stage, validate, and seal one local-control-plane package source."""

        source_type, source_root, source_path, trust = self._source_paths(
            source_handle, now
        )
        private_root = _private_directory(self._private_root)
        temporary_root = private_root / f".stage-{secrets.token_hex(16)}"
        temporary_root.mkdir(mode=0o700)
        extraction_root: Path | None = None
        source_fd = -1
        try:
            if source_type == "directory":
                source_fd = _open_directory_below(source_root, source_path)
            else:
                extraction_root = private_root / f".extract-{secrets.token_hex(16)}"
                extraction_root.mkdir(mode=0o700)
                _extract_zip(source_root, source_path, extraction_root)
                source_fd = _open_absolute_directory(extraction_root)
            entries: list[tuple[str, str, int]] = []
            source_manifest, source_signature = _copy_directory(
                source_fd,
                temporary_root,
                relative_path="",
                entries=entries,
            )
            digest, file_count, byte_count = _package_digest(entries)
            try:
                workflow = load_agent_package_workflow(str(temporary_root))
            except Exception as error:
                raise PackageStagingError(
                    "DAR validation failed for staged package"
                ) from error
            _mark_declared_local_tool_assets_executable(temporary_root)
            expected_manifest = _content_manifest_bytes(
                package_id=workflow.runtime_manifest.package_id,
                content_digest=digest,
                entries=entries,
                compatibility=_package_compatibility(temporary_root, workflow),
            )
            if source_type == "zip" and source_manifest is None:
                raise PackageStagingError("portable ZIP source manifest is missing")
            if source_manifest is not None and not secrets.compare_digest(
                source_manifest, expected_manifest
            ):
                raise PackageStagingError(
                    "package source manifest does not match payload"
                )
            publisher_key_id = self._verify_publisher_signature(
                trust=trust,
                manifest=expected_manifest,
                source_manifest=source_manifest,
                source_signature=source_signature,
            )
            _write_content_manifest(temporary_root, expected_manifest)
            final_root = private_root / f"package-{digest}"
            if final_root.exists():
                shutil.rmtree(temporary_root)
            else:
                os.replace(temporary_root, final_root)
                _seal_tree(final_root)
            return StagedPackage(
                final_root,
                digest,
                file_count,
                byte_count,
                trust,
                publisher_key_id,
            )
        finally:
            if source_fd >= 0:
                os.close(source_fd)
            if extraction_root is not None and extraction_root.exists():
                shutil.rmtree(extraction_root)
            if temporary_root.exists():
                shutil.rmtree(temporary_root)

    def _source_paths(
        self, source_handle: str, now: datetime
    ) -> tuple[str, Path, Path, str]:
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
        source_type = payload.get("source_type")
        if source_type not in {"directory", "zip"}:
            raise PackageStagingError("package source type is invalid")
        trust = payload.get("trust")
        if trust not in {_HUMAN_SELECTED_LOCAL, _PUBLISHER_SIGNATURE}:
            raise PackageStagingError("package source trust is invalid")
        root = _absolute_path(payload.get("source_root"), "package source root")
        path = _absolute_path(payload.get("source_path"), "package source path")
        try:
            path.relative_to(root)
        except ValueError as error:
            raise PackageStagingError(
                "package source path is outside its root"
            ) from error
        return source_type, root, path, trust

    def _verify_publisher_signature(
        self,
        *,
        trust: str,
        manifest: bytes,
        source_manifest: bytes | None,
        source_signature: bytes | None,
    ) -> str | None:
        if trust == _HUMAN_SELECTED_LOCAL:
            return None
        if source_manifest is None or source_signature is None:
            raise PackageStagingError("publisher-signed package metadata is missing")
        try:
            signature = json.loads(source_signature)
            if not isinstance(signature, Mapping):
                raise PackageSignatureError("package signature is invalid")
            return verify_manifest(
                manifest=manifest,
                signature=signature,
                trusted_keys=self._trusted_keys(),
            )
        except (PackageSignatureError, TypeError, ValueError) as error:
            raise PackageStagingError(
                "package publisher signature is invalid"
            ) from error


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


def _open_file_below(root: Path, path: Path) -> int:
    try:
        relative_parts = path.relative_to(root).parts
    except ValueError as error:  # Defensive: callers already validate this binding.
        raise PackageStagingError("package source path is outside its root") from error
    if not relative_parts:
        raise PackageStagingError("package source archive is unavailable")
    descriptor = _open_absolute_directory(root)
    try:
        for part in relative_parts[:-1]:
            child = _open_directory_at(descriptor, part)
            os.close(descriptor)
            descriptor = child
        try:
            archive_fd = os.open(
                relative_parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=descriptor
            )
        except OSError as error:
            if error.errno == errno.ELOOP or _is_symlink_at(
                descriptor, relative_parts[-1]
            ):
                raise PackageStagingError(
                    "package source archive contains a symlink"
                ) from error
            raise PackageStagingError(
                "package source archive is unavailable"
            ) from error
        archive_stat = os.fstat(archive_fd)
        if not stat.S_ISREG(archive_stat.st_mode):
            os.close(archive_fd)
            raise PackageStagingError("package source archive is not a regular file")
        return archive_fd
    finally:
        os.close(descriptor)


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
) -> tuple[bytes | None, bytes | None]:
    source_manifest: bytes | None = None
    source_signature: bytes | None = None
    for name in sorted(os.listdir(source_fd)):
        if not relative_path and name == _PACKAGE_MANIFEST_NAME:
            source_manifest = _read_source_metadata(source_fd, name)
            continue
        if not relative_path and name == _PACKAGE_SIGNATURE_NAME:
            source_signature = _read_source_metadata(source_fd, name)
            continue
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
    return source_manifest, source_signature


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


def _content_manifest_bytes(
    *,
    package_id: str | None,
    content_digest: str,
    entries: list[tuple[str, str, int]],
    compatibility: Mapping[str, object],
) -> bytes:
    if not package_id:
        raise PackageStagingError("staged package has no package_id")
    payload = {
        "content_digest": content_digest,
        "dar_runtime": compatibility["dar_runtime"],
        "descriptor_format_version": compatibility["descriptor_format_version"],
        "files": [
            {"byte_count": size, "path": path, "sha256": file_digest}
            for path, file_digest, size in sorted(entries)
        ],
        "format_version": 2,
        "package_id": package_id,
        "runtime_format_version": compatibility["runtime_format_version"],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _package_compatibility(root: Path, workflow: object) -> dict[str, object]:
    descriptor_path = root / "workflow-descriptor.yaml"
    try:
        descriptor = yaml.safe_load(descriptor_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise PackageStagingError("package descriptor is invalid") from error
    runtime_manifest = getattr(workflow, "runtime_manifest", None)
    runtime_format_version = getattr(runtime_manifest, "format_version", None)
    package_id = getattr(runtime_manifest, "package_id", None)
    if (
        not isinstance(descriptor, Mapping)
        or descriptor.get("package_id") != package_id
        or not _positive_int(runtime_format_version)
        or not _positive_int(descriptor.get("format_version"))
    ):
        raise PackageStagingError("package descriptor is incompatible")
    dar_runtime = descriptor.get("dar_runtime")
    if (
        not isinstance(dar_runtime, Mapping)
        or set(dar_runtime) != {"distribution", "required_version"}
        or not _nonempty_string(dar_runtime.get("distribution"))
        or not _nonempty_string(dar_runtime.get("required_version"))
    ):
        raise PackageStagingError("package descriptor is incompatible")
    return {
        "dar_runtime": {
            "distribution": dar_runtime["distribution"],
            "required_version": dar_runtime["required_version"],
        },
        "descriptor_format_version": descriptor["format_version"],
        "runtime_format_version": runtime_format_version,
    }


def _mark_declared_local_tool_assets_executable(root: Path) -> None:
    """Grant execute permission only to descriptor-declared package-local assets."""

    try:
        descriptor = yaml.safe_load(
            (root / "workflow-descriptor.yaml").read_text(encoding="utf-8")
        )
    except (OSError, yaml.YAMLError) as error:
        raise PackageStagingError("package descriptor is invalid") from error
    if not isinstance(descriptor, Mapping):
        raise PackageStagingError("package descriptor is invalid")
    tools = descriptor.get("tools")
    assets: list[object] = []
    if isinstance(tools, list):
        assets.extend(
            tool.get("asset_path")
            for tool in tools
            if isinstance(tool, Mapping) and tool.get("kind") == "local"
        )
    assets.extend(_terminal_output_assets(descriptor.get("output")))
    for asset_path in assets:
        if not isinstance(asset_path, str) or not asset_path:
            continue
        asset = root / asset_path
        try:
            resolved = asset.resolve(strict=True)
            resolved.relative_to(root)
            metadata = os.lstat(resolved)
        except (OSError, ValueError) as error:
            raise PackageStagingError("local tool asset is unavailable") from error
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise PackageStagingError("local tool asset is unavailable")
        os.chmod(resolved, 0o700)


def _terminal_output_assets(output: object) -> list[object]:
    """Return validator and processor assets declared at the output boundary."""

    assets: list[object] = []
    if isinstance(output, Mapping):
        if isinstance(output.get("validator"), Mapping):
            assets.append(output["validator"].get("asset_path"))
        processors = output.get("processors")
        if isinstance(processors, list):
            assets.extend(
                processor.get("asset_path")
                for processor in processors
                if isinstance(processor, Mapping)
            )
    return assets


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _write_content_manifest(root: Path, encoded: bytes) -> None:
    destination = root / _PACKAGE_MANIFEST_NAME
    temporary = root / f".manifest-{secrets.token_hex(16)}.tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        _write_all(descriptor, encoded)
    finally:
        os.close(descriptor)
    os.replace(temporary, destination)


def _read_source_metadata(source_parent_fd: int, name: str) -> bytes:
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
        body = bytearray()
        while chunk := os.read(source_fd, _READ_SIZE):
            body.extend(chunk)
            if len(body) > MAX_FILE_BYTES:
                raise PackageStagingError("package source file exceeds size limit")
        return bytes(body)
    finally:
        os.close(source_fd)


def _seal_tree(root: Path) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_dir():
            os.chmod(path, 0o500)
        else:
            mode = os.lstat(path).st_mode
            os.chmod(path, 0o500 if mode & stat.S_IXUSR else 0o400)
    os.chmod(root, 0o500)


def _extract_zip(root: Path, archive_path: Path, destination: Path) -> None:
    archive_fd = _open_file_below(root, archive_path)
    try:
        with os.fdopen(archive_fd, "rb") as stream, zipfile.ZipFile(stream) as archive:
            members = _validated_zip_members(archive)
            for relative_path, member in members:
                target = destination.joinpath(*relative_path.parts)
                if member.is_dir():
                    target.mkdir(mode=0o700)
                else:
                    _extract_zip_file(archive, member, target)
    except zipfile.BadZipFile as error:
        raise PackageStagingError(
            "package source archive is not a valid ZIP"
        ) from error


def _validated_zip_members(
    archive: zipfile.ZipFile,
) -> list[tuple[PurePosixPath, zipfile.ZipInfo]]:
    members: list[tuple[PurePosixPath, zipfile.ZipInfo]] = []
    seen: set[PurePosixPath] = set()
    total_bytes = 0
    total_compressed_bytes = 0
    for member in archive.infolist():
        relative_path = _zip_member_path(member)
        if relative_path in seen:
            raise PackageStagingError(
                "package source archive contains duplicate members"
            )
        seen.add(relative_path)
        _validate_zip_member_type(member)
        total_bytes = _zip_member_total_bytes(member, total_bytes)
        total_compressed_bytes = _zip_member_compressed_bytes(
            member, total_compressed_bytes
        )
        _validate_zip_compression_ratio(total_bytes, total_compressed_bytes)
        if len(seen) > MAX_PACKAGE_FILES:
            raise PackageStagingError("package source exceeds file limit")
        members.append((relative_path, member))
    _reject_zip_parent_conflicts(members)
    return sorted(members, key=lambda item: (len(item[0].parts), str(item[0])))


def _zip_member_total_bytes(member: zipfile.ZipInfo, total_bytes: int) -> int:
    if member.is_dir():
        return total_bytes
    if member.file_size > MAX_FILE_BYTES:
        raise PackageStagingError("package source file exceeds size limit")
    total_bytes += member.file_size
    if total_bytes > MAX_PACKAGE_BYTES:
        raise PackageStagingError("package source exceeds size limit")
    return total_bytes


def _zip_member_compressed_bytes(member: zipfile.ZipInfo, total_bytes: int) -> int:
    if member.is_dir():
        return total_bytes
    if member.file_size and not member.compress_size:
        raise PackageStagingError("package source archive exceeds compression ratio")
    return total_bytes + member.compress_size


def _validate_zip_compression_ratio(
    uncompressed_bytes: int, compressed_bytes: int
) -> None:
    if uncompressed_bytes and (
        not compressed_bytes
        or uncompressed_bytes > compressed_bytes * MAX_ZIP_COMPRESSION_RATIO
    ):
        raise PackageStagingError("package source archive exceeds compression ratio")


def _reject_zip_parent_conflicts(
    members: list[tuple[PurePosixPath, zipfile.ZipInfo]],
) -> None:
    file_paths = {path for path, member in members if not member.is_dir()}
    for relative_path, _ in members:
        if any(parent in file_paths for parent in relative_path.parents):
            raise PackageStagingError("package source archive has conflicting members")


def _zip_member_path(member: zipfile.ZipInfo) -> PurePosixPath:
    if "\\" in member.filename:
        raise PackageStagingError(
            "package source archive contains unsafe archive member"
        )
    relative_path = PurePosixPath(member.filename)
    if (
        relative_path.is_absolute()
        or not relative_path.parts
        or any(part in {"", ".", ".."} for part in relative_path.parts)
    ):
        raise PackageStagingError(
            "package source archive contains unsafe archive member"
        )
    return relative_path


def _validate_zip_member_type(member: zipfile.ZipInfo) -> None:
    mode = member.external_attr >> 16
    file_type = stat.S_IFMT(mode)
    if stat.S_ISLNK(mode):
        raise PackageStagingError("package source archive contains a symlink")
    if member.is_dir():
        if file_type not in {0, stat.S_IFDIR}:
            raise PackageStagingError(
                "package source archive contains a non-regular entry"
            )
    elif file_type not in {0, stat.S_IFREG}:
        raise PackageStagingError("package source archive contains a non-regular entry")


def _extract_zip_file(
    archive: zipfile.ZipFile, member: zipfile.ZipInfo, destination: Path
) -> None:
    byte_count = 0
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination_fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with archive.open(member) as source:
            while chunk := source.read(_READ_SIZE):
                byte_count += len(chunk)
                if byte_count > MAX_FILE_BYTES:
                    raise PackageStagingError("package source file exceeds size limit")
                _write_all(destination_fd, chunk)
        if byte_count != member.file_size:
            raise PackageStagingError(
                "package source archive changed during extraction"
            )
    finally:
        os.close(destination_fd)
