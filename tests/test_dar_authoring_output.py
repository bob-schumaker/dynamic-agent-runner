"""Tests for deterministic validation of external authoring package output."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dynamic_agent_runner.workflow_host.authoring_materials import (  # noqa: E402
    AuthoringMaterialProjectionMember,
    AuthoringMaterialSetProjection,
)
from dynamic_agent_runner.workflow_host.authoring_output import (  # noqa: E402
    AuthoringOutputError,
    build_authored_package_manifest,
    validate_authored_package,
    write_authored_package_manifest,
)


NOW = datetime(2026, 8, 24, tzinfo=UTC)
TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "templates"


def _projection(
    *members: AuthoringMaterialProjectionMember,
) -> AuthoringMaterialSetProjection:
    return AuthoringMaterialSetProjection(
        material_set_id="v1.material-set.authoring",
        members=members,
        expires_at=NOW,
    )


def _member(*, content: str, disposition: str) -> AuthoringMaterialProjectionMember:
    return AuthoringMaterialProjectionMember(
        artifact_id="v1.material.example",
        digest="a" * 64,
        role="example",
        disposition=disposition,
        content=content,
    )


def test_validates_a_dar_package_without_exposing_paths_or_material_content(
    tmp_path: Path,
) -> None:
    package = tmp_path / "generated-package"
    shutil.copytree(TEMPLATE_ROOT, package)
    write_authored_package_manifest(package)

    result = validate_authored_package(
        package_root=package,
        materials=_projection(
            _member(content="private design brief", disposition="reference_only")
        ),
    )

    assert result.package_id == "dar-authoring-no-tool-template"
    assert len(result.package_digest) == 64
    assert len(result.descriptor_digest) == 64
    assert result.file_count == 4
    assert str(package) not in repr(result)
    assert "private design brief" not in repr(result)


def test_rejects_reference_only_authoring_material_in_generated_package(
    tmp_path: Path,
) -> None:
    package = tmp_path / "generated-package"
    shutil.copytree(TEMPLATE_ROOT, package)
    design = package / "agent-design.md"
    design.write_text(
        design.read_text(encoding="utf-8") + "\nsecret design brief\n",
        encoding="utf-8",
    )

    with pytest.raises(AuthoringOutputError, match="reference-only"):
        validate_authored_package(
            package_root=package,
            materials=_projection(
                _member(content="secret design brief", disposition="reference_only")
            ),
        )


def test_rejects_a_generated_package_without_its_canonical_manifest(
    tmp_path: Path,
) -> None:
    package = tmp_path / "generated-package"
    shutil.copytree(TEMPLATE_ROOT, package)

    with pytest.raises(AuthoringOutputError, match="manifest"):
        validate_authored_package(package_root=package, materials=_projection())


def test_authoring_manifest_writer_matches_the_deterministic_package_manifest(
    tmp_path: Path,
) -> None:
    package = tmp_path / "generated-package"
    shutil.copytree(TEMPLATE_ROOT, package)

    assert write_authored_package_manifest(package) == (
        build_authored_package_manifest(package)
    )
    assert (package / "package-manifest.json").read_bytes() == (
        build_authored_package_manifest(package)
    )


def test_rejects_symlinked_or_invalid_generated_package_files(tmp_path: Path) -> None:
    package = tmp_path / "generated-package"
    shutil.copytree(TEMPLATE_ROOT, package)
    (package / "agent-design.md").unlink()
    (package / "agent-design.md").symlink_to("agent-runtime.yaml")

    with pytest.raises(AuthoringOutputError, match="package structure"):
        validate_authored_package(package_root=package, materials=_projection())
