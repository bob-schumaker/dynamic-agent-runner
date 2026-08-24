"""Deterministic validation for a controlled external authoring package output."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from dynamic_agent_runner import load_agent_package_workflow
from dynamic_agent_runner.validation import validate_agent_workflow
from dynamic_agent_runner.workflow_host.authoring_materials import (
    AuthoringMaterialSetProjection,
)
from dynamic_agent_runner.workflow_host.descriptor import WorkflowDescriptor


class AuthoringOutputError(ValueError):
    """Raised when an external authoring result is not a safe DAR package."""


@dataclass(frozen=True)
class AuthoredPackageValidation:
    """Redacted deterministic identity for a validated authoring result."""

    package_id: str
    package_digest: str
    descriptor_digest: str
    file_count: int


def build_authored_package_manifest(package_root: Path) -> bytes:
    """Build canonical package-manifest bytes for controlled authoring output."""

    files = _package_files(package_root)
    workflow, descriptor_bytes, descriptor_value = _load_package_contract(package_root)
    runtime_manifest = workflow.runtime_manifest
    package_id = runtime_manifest.package_id
    dar_runtime = descriptor_value.get("dar_runtime")
    if (
        not isinstance(package_id, str)
        or not package_id
        or not isinstance(dar_runtime, dict)
        or set(dar_runtime) != {"distribution", "required_version"}
        or not all(isinstance(value, str) and value for value in dar_runtime.values())
    ):
        raise AuthoringOutputError("authoring package structure is invalid")
    payload = {
        "content_digest": _package_digest(files),
        "dar_runtime": dar_runtime,
        "descriptor_format_version": descriptor_value["format_version"],
        "files": [
            {
                "byte_count": len(body),
                "path": path,
                "sha256": hashlib.sha256(body).hexdigest(),
            }
            for path, body in files
        ],
        "format_version": 2,
        "package_id": package_id,
        "runtime_format_version": runtime_manifest.format_version,
    }
    if not isinstance(descriptor_bytes, bytes):  # Defensive invariant for typing.
        raise AuthoringOutputError("authoring package structure is invalid")
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def write_authored_package_manifest(package_root: Path) -> bytes:
    """Atomically write the canonical manifest after controlled package generation."""

    manifest = build_authored_package_manifest(package_root)
    destination = package_root / "package-manifest.json"
    temporary = package_root / f".package-manifest-{secrets.token_hex(16)}.tmp"
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            _write_all(descriptor, manifest)
        finally:
            os.close(descriptor)
        os.replace(temporary, destination)
    except OSError as error:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise AuthoringOutputError(
            "authoring package manifest is unavailable"
        ) from error
    return manifest


def validate_authored_package(
    *, package_root: Path, materials: AuthoringMaterialSetProjection
) -> AuthoredPackageValidation:
    """Validate a controlled generated directory before release evidence records it.

    This is not a package-import boundary: callers must stage an untrusted
    directory through the host's no-follow package-selection path first. It
    validates the external harness's controlled output and returns no paths or
    raw material content.
    """

    if not isinstance(package_root, Path) or not isinstance(
        materials, AuthoringMaterialSetProjection
    ):
        raise AuthoringOutputError("authoring output is invalid")
    files = _package_files(package_root)
    _reject_reference_only_material(files, materials)
    workflow, descriptor_bytes, _ = _load_package_contract(package_root)
    try:
        manifest = (package_root / "package-manifest.json").read_bytes()
    except OSError as error:
        raise AuthoringOutputError("authoring package manifest is invalid") from error
    expected_manifest = build_authored_package_manifest(package_root)
    if manifest != expected_manifest:
        raise AuthoringOutputError("authoring package manifest is invalid")
    return AuthoredPackageValidation(
        package_id=workflow.runtime_manifest.package_id,
        package_digest=_package_digest(files),
        descriptor_digest=hashlib.sha256(descriptor_bytes).hexdigest(),
        file_count=len(files),
    )


def _package_files(package_root: Path) -> tuple[tuple[str, bytes], ...]:
    try:
        if package_root.is_symlink() or not package_root.is_dir():
            raise ValueError
        entries = tuple(package_root.rglob("*"))
        if any(path.is_symlink() for path in entries):
            raise ValueError
        files = tuple(
            sorted(
                path
                for path in entries
                if path.is_file()
                and path.name not in {"package-manifest.json", "package-signature.json"}
            )
        )
        if not files:
            raise ValueError
        result = tuple(
            (path.relative_to(package_root).as_posix(), path.read_bytes())
            for path in files
        )
    except (OSError, ValueError) as error:
        raise AuthoringOutputError("authoring package structure is invalid") from error
    return result


def _load_package_contract(package_root: Path) -> tuple[Any, bytes, dict[str, object]]:
    try:
        workflow = load_agent_package_workflow(str(package_root))
        validate_agent_workflow(workflow)
        descriptor_bytes = (package_root / "workflow-descriptor.yaml").read_bytes()
        descriptor_value = yaml.safe_load(descriptor_bytes)
        if not isinstance(descriptor_value, dict):
            raise ValueError
        descriptor = WorkflowDescriptor.from_mapping(descriptor_value)
        if descriptor.package_id != workflow.runtime_manifest.package_id:
            raise ValueError
    except Exception as error:  # DAR/YAML parser errors are deliberately redacted.
        raise AuthoringOutputError("authoring package structure is invalid") from error
    return workflow, descriptor_bytes, descriptor_value


def _reject_reference_only_material(
    files: tuple[tuple[str, bytes], ...], materials: AuthoringMaterialSetProjection
) -> None:
    protected = tuple(
        member.content.encode("utf-8")
        for member in materials.members
        if member.disposition == "reference_only"
    )
    if any(content in body for _, body in files for content in protected):
        raise AuthoringOutputError(
            "reference-only authoring material appears in generated package"
        )


def _package_digest(files: tuple[tuple[str, bytes], ...]) -> str:
    digest = hashlib.sha256()
    for relative_path, body in files:
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(body).hexdigest().encode("ascii"))
        digest.update(b"\0")
        digest.update(str(len(body)).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _write_all(descriptor: int, value: bytes) -> None:
    offset = 0
    while offset < len(value):
        offset += os.write(descriptor, value[offset:])
