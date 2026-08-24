"""Deterministic ZIP export for an already-private staged workflow package."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from dar_workflow_server.package_signatures import PackageSignatureError, sign_manifest
from dar_workflow_server.staging import StagedPackage


_MANIFEST_NAME = "package-manifest.json"
_SIGNATURE_NAME = "package-signature.json"
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


class PackageExportError(ValueError):
    """Raised when a staged package cannot be exported safely."""


@dataclass(frozen=True)
class ExportedPackage:
    """Receipt for one deterministic local ZIP export."""

    content_digest: str
    byte_count: int
    publisher_key_id: str | None = None


def export_staged_package(
    *, staged: StagedPackage, destination: Path
) -> ExportedPackage:
    """Write a deterministic ZIP only after verifying the private content manifest."""

    payload = _verified_payload(staged)
    return _write_exported_package(
        payload=payload, destination=destination, content_digest=staged.digest
    )


def export_signed_staged_package(
    *, staged: StagedPackage, destination: Path, key_id: str, private_key: bytes
) -> ExportedPackage:
    """Write a deterministic publisher-signed ZIP from an already-private package."""

    payload = _verified_payload(staged)
    try:
        signature = sign_manifest(
            manifest=payload[_MANIFEST_NAME], key_id=key_id, private_key=private_key
        )
    except PackageSignatureError as error:
        raise PackageExportError("package signing material is invalid") from error
    payload[_SIGNATURE_NAME] = json.dumps(
        signature, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return _write_exported_package(
        payload=payload,
        destination=destination,
        content_digest=staged.digest,
        publisher_key_id=key_id,
    )


def _write_exported_package(
    *,
    payload: dict[str, bytes],
    destination: Path,
    content_digest: str,
    publisher_key_id: str | None = None,
) -> ExportedPackage:
    """Write one canonical ZIP payload without retaining a private signing key."""

    _validate_destination(destination)
    temporary = destination.parent / f".{destination.name}.{secrets.token_hex(16)}.tmp"
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
            for relative_path in sorted(payload):
                info = zipfile.ZipInfo(relative_path, date_time=_ZIP_TIMESTAMP)
                info.create_system = 3
                info.external_attr = 0o100600 << 16
                info.compress_type = zipfile.ZIP_STORED
                archive.writestr(info, payload[relative_path])
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return ExportedPackage(content_digest, destination.stat().st_size, publisher_key_id)


def _verified_payload(staged: StagedPackage) -> dict[str, bytes]:
    root = Path(staged.root)
    manifest = _read_regular_file(root, _MANIFEST_NAME)
    try:
        value = json.loads(manifest)
    except (TypeError, json.JSONDecodeError) as error:
        raise PackageExportError("staged package manifest is invalid") from error
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if manifest != canonical or not isinstance(value, dict):
        raise PackageExportError("staged package manifest is invalid")
    files = value.get("files")
    if (
        value.get("format_version") != 2
        or value.get("content_digest") != staged.digest
        or not isinstance(value.get("package_id"), str)
        or not value["package_id"]
        or not isinstance(files, list)
        or not isinstance(value.get("runtime_format_version"), int)
        or isinstance(value["runtime_format_version"], bool)
        or not isinstance(value.get("descriptor_format_version"), int)
        or isinstance(value["descriptor_format_version"], bool)
        or not _valid_dar_runtime(value.get("dar_runtime"))
    ):
        raise PackageExportError("staged package manifest is invalid")
    payload: dict[str, bytes] = {_MANIFEST_NAME: manifest}
    entries: list[tuple[str, str, int]] = []
    for entry in files:
        if not isinstance(entry, dict) or set(entry) != {
            "byte_count",
            "path",
            "sha256",
        }:
            raise PackageExportError("staged package manifest is invalid")
        relative_path = _relative_path(entry["path"])
        if relative_path in payload:
            raise PackageExportError("staged package manifest is invalid")
        body = _read_regular_file(root, relative_path)
        digest = hashlib.sha256(body).hexdigest()
        if entry["byte_count"] != len(body) or entry["sha256"] != digest:
            raise PackageExportError("staged package manifest does not match payload")
        payload[relative_path] = body
        entries.append((relative_path, digest, len(body)))
    if _content_digest(entries) != staged.digest:
        raise PackageExportError("staged package manifest does not match payload")
    return payload


def _valid_dar_runtime(value: object) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"distribution", "required_version"}
        and isinstance(value["distribution"], str)
        and bool(value["distribution"])
        and isinstance(value["required_version"], str)
        and bool(value["required_version"])
    )


def _validate_destination(destination: Path) -> None:
    if not destination.is_absolute() or destination.suffix.lower() != ".zip":
        raise PackageExportError(
            "package export destination must be an absolute ZIP path"
        )
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    mode = os.lstat(destination.parent).st_mode
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise PackageExportError("package export destination parent is unavailable")


def _relative_path(value: object) -> str:
    if not isinstance(value, str):
        raise PackageExportError("staged package manifest is invalid")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise PackageExportError("staged package manifest is invalid")
    return str(path)


def _read_regular_file(root: Path, relative_path: str) -> bytes:
    path = root.joinpath(*PurePosixPath(relative_path).parts)
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError as error:
        raise PackageExportError("staged package payload is unavailable") from error
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise PackageExportError("staged package payload is unavailable")
    return path.read_bytes()


def _content_digest(entries: list[tuple[str, str, int]]) -> str:
    digest = hashlib.sha256()
    for path, file_digest, size in sorted(entries):
        digest.update(f"{path}\0{file_digest}\0{size}\n".encode("utf-8"))
    return digest.hexdigest()
