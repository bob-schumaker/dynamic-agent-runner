"""Tests for deterministic portable DAR authoring package ZIP export."""

from __future__ import annotations

import shutil
import zipfile
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


from dynamic_agent_runner.workflow_host.package_export import (  # noqa: E402
    PackageExportError,
    export_signed_staged_package,
    export_staged_package,
)
from dynamic_agent_runner.workflow_host.capabilities import (  # noqa: E402
    CapabilityRequirements,
)
from dynamic_agent_runner.workflow_host.model_materials import (  # noqa: E402
    parse_model_dependency_lock,
)
from dynamic_agent_runner.workflow_host.package_sources import (
    PackageSourceSelectionPolicy,
)  # noqa: E402
from dynamic_agent_runner.workflow_host.staging import PrivatePackageStager  # noqa: E402
from dynamic_agent_runner.workflow_host.state import PrivateStateStore  # noqa: E402


NOW = datetime(2026, 8, 23, tzinfo=UTC)
TEMPLATE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "specs"
    / "agent-engineering-plugin-migration"
    / "legacy-dar-authoring"
    / "templates"
)


def _model_materials() -> dict[str, object]:
    return {
        "format_version": 1,
        "logical_model_id": "local-model",
        "runner_contract": {"id": "llama-cpp-v1", "version": "v1"},
        "loader_profile_contract": {"id": "llama-cpp-text-v1", "version": "v1"},
        "sources": [
            {
                "role": "base_model",
                "group": "base",
                "source_type": "huggingface_file",
                "repository": "example/model",
                "revision": "a" * 40,
                "filename": "model.gguf",
                "sha256": "b" * 64,
            }
        ],
        "preparation": [],
    }


def _stage(
    tmp_path: Path,
    *,
    with_capability_requirements: bool = False,
    with_model_materials: bool = False,
):
    source = tmp_path / "packages" / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
    if with_capability_requirements:
        descriptor = source / "workflow-descriptor.yaml"
        value = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
        requirements = CapabilityRequirements()
        value["dar_runtime"]["required_version"] = "0.1.17"
        value["capability_requirements"] = {
            "format_version": 1,
            "required_capabilities": [],
            "capability_requirements_digest": requirements.digest,
            "bindings": {},
        }
        descriptor.write_text(yaml.safe_dump(value), encoding="utf-8")
    if with_model_materials:
        (source / "model-materials.json").write_text(
            json.dumps(_model_materials(), sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
    store = PrivateStateStore(tmp_path / "state")
    handle = PackageSourceSelectionPolicy(
        allowed_root=source.parent, store=store
    ).select_directory(source, now=NOW)
    return (
        PrivatePackageStager(store=store, private_root=tmp_path / "private").stage(
            handle, now=NOW
        ),
        store,
    )


def test_export_is_deterministic_and_round_trips_through_zip_import(
    tmp_path: Path,
) -> None:
    staged, store = _stage(tmp_path)
    first = tmp_path / "exports" / "first.zip"
    second = tmp_path / "exports" / "second.zip"

    first_receipt = export_staged_package(staged=staged, destination=first)
    second_receipt = export_staged_package(staged=staged, destination=second)
    handle = PackageSourceSelectionPolicy(
        allowed_root=second.parent, store=store
    ).select_zip(second, now=NOW)
    imported = PrivatePackageStager(
        store=store, private_root=tmp_path / "imports"
    ).stage(handle, now=NOW)

    assert first.read_bytes() == second.read_bytes()
    assert first_receipt.content_digest == staged.digest
    assert second_receipt.byte_count == second.stat().st_size
    assert imported.digest == staged.digest


def test_export_and_import_bind_declared_capability_requirements_digest(
    tmp_path: Path,
) -> None:
    staged, store = _stage(tmp_path, with_capability_requirements=True)
    archive = tmp_path / "exports" / "capabilities.zip"

    export_staged_package(staged=staged, destination=archive)
    staged_manifest = json.loads((staged.root / "package-manifest.json").read_text())
    with zipfile.ZipFile(archive) as exported:
        exported_manifest = json.loads(exported.read("package-manifest.json"))
    handle = PackageSourceSelectionPolicy(
        allowed_root=archive.parent, store=store
    ).select_zip(archive, now=NOW)
    imported = PrivatePackageStager(
        store=store, private_root=tmp_path / "imports"
    ).stage(handle, now=NOW)

    expected = CapabilityRequirements().digest
    assert staged_manifest["capability_requirements_digest"] == expected
    assert exported_manifest["capability_requirements_digest"] == expected
    assert imported.digest == staged.digest


def test_export_and_import_bind_declared_model_materials_digest(
    tmp_path: Path,
) -> None:
    staged, store = _stage(tmp_path, with_model_materials=True)
    archive = tmp_path / "exports" / "model-materials.zip"

    export_staged_package(staged=staged, destination=archive)
    staged_manifest = json.loads((staged.root / "package-manifest.json").read_text())
    with zipfile.ZipFile(archive) as exported:
        exported_manifest = json.loads(exported.read("package-manifest.json"))
    handle = PackageSourceSelectionPolicy(
        allowed_root=archive.parent, store=store
    ).select_zip(archive, now=NOW)
    imported = PrivatePackageStager(
        store=store, private_root=tmp_path / "imports"
    ).stage(handle, now=NOW)

    expected = parse_model_dependency_lock(_model_materials()).digest
    assert staged_manifest["model_materials_digest"] == expected
    assert exported_manifest["model_materials_digest"] == expected
    assert imported.digest == staged.digest


def test_export_rejects_a_tampered_model_materials_digest(tmp_path: Path) -> None:
    staged, _ = _stage(tmp_path, with_model_materials=True)
    staged.root.chmod(0o700)
    manifest_path = staged.root / "package-manifest.json"
    manifest_path.chmod(0o600)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["model_materials_digest"] = "0" * 64
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )

    with pytest.raises(PackageExportError, match="model-material"):
        export_staged_package(staged=staged, destination=tmp_path / "export.zip")


def test_export_rejects_a_tampered_private_payload(tmp_path: Path) -> None:
    staged, _ = _stage(tmp_path)
    staged.root.chmod(0o700)
    payload = staged.root / "agent-design.md"
    payload.chmod(0o600)
    payload.write_text("changed", encoding="utf-8")

    with pytest.raises(PackageExportError, match="does not match"):
        export_staged_package(staged=staged, destination=tmp_path / "export.zip")


def test_signed_export_round_trips_through_trusted_publisher_import(
    tmp_path: Path,
) -> None:
    staged, store = _stage(tmp_path)
    key_id = "publisher.example.v1"
    private_key = Ed25519PrivateKey.generate()
    archive = tmp_path / "exports" / "signed.zip"

    receipt = export_signed_staged_package(
        staged=staged,
        destination=archive,
        key_id=key_id,
        private_key=private_key.private_bytes_raw(),
    )
    handle = PackageSourceSelectionPolicy(
        allowed_root=archive.parent, store=store
    ).select_publisher_zip(archive, now=NOW)
    imported = PrivatePackageStager(
        store=store,
        private_root=tmp_path / "imports",
        trusted_keys=lambda: {key_id: private_key.public_key().public_bytes_raw()},
    ).stage(handle, now=NOW)

    with zipfile.ZipFile(archive) as exported:
        assert "package-signature.json" in exported.namelist()
    assert receipt.content_digest == staged.digest
    assert receipt.publisher_key_id == key_id
    assert imported.digest == staged.digest
    assert imported.publisher_key_id == key_id
