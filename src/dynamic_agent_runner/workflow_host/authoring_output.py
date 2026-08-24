"""Deterministic validation for a controlled external authoring package output."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

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
    try:
        workflow = load_agent_package_workflow(str(package_root))
        validate_agent_workflow(workflow)
        descriptor_bytes = (package_root / "workflow-descriptor.yaml").read_bytes()
        descriptor = WorkflowDescriptor.from_mapping(yaml.safe_load(descriptor_bytes))
    except Exception as error:  # DAR/YAML parser errors are deliberately redacted.
        raise AuthoringOutputError("authoring package structure is invalid") from error
    if descriptor.package_id != workflow.runtime_manifest.package_id:
        raise AuthoringOutputError("authoring package structure is invalid")
    return AuthoredPackageValidation(
        package_id=descriptor.package_id,
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
        files = tuple(sorted(path for path in entries if path.is_file()))
        if not files:
            raise ValueError
        result = tuple(
            (path.relative_to(package_root).as_posix(), path.read_bytes())
            for path in files
        )
    except (OSError, ValueError) as error:
        raise AuthoringOutputError("authoring package structure is invalid") from error
    return result


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
