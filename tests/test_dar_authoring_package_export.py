"""Tests for deterministic portable DAR authoring package ZIP export."""

from __future__ import annotations

import shutil
import zipfile
import json
import hashlib
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
from dynamic_agent_runner.workflow_host.execution_descriptors import (  # noqa: E402
    parse_execution_descriptor,
)
from dynamic_agent_runner.workflow_host.material_sets import (  # noqa: E402
    parse_model_material_sets,
)
from dynamic_agent_runner.workflow_host.package_sources import (
    PackageSourceSelectionPolicy,
)  # noqa: E402
from dynamic_agent_runner.workflow_host.staging import (  # noqa: E402
    PackageStagingError,
    PrivatePackageStager,
)
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


def _execution_descriptor() -> dict[str, object]:
    return {
        "format_version": 1,
        "architecture_abi": {
            "id": "example-encoder-v1",
            "version": "1",
            "contract_digest": "d" * 64,
        },
        "material_roles": ["tokenizer", "weights"],
        "abi_fields": {},
    }


def _v2_model_materials() -> dict[str, object]:
    descriptor = parse_execution_descriptor(_execution_descriptor())
    return {
        "format_version": 2,
        "logical_model_id": "example-embedding",
        "runner_contract": {"id": "example-embedding-v1", "version": "1"},
        "execution_descriptor": {
            "filename": "execution-descriptor.json",
            "sha256": descriptor.digest,
        },
        "sources": [
            {
                "role": "tokenizer",
                "group": "base",
                "source_type": "huggingface_file",
                "repository": "example/embedding",
                "revision": "a" * 40,
                "filename": "tokenizer.json",
                "sha256": "b" * 64,
            },
            {
                "role": "weights",
                "group": "base",
                "source_type": "huggingface_file",
                "repository": "example/embedding",
                "revision": "a" * 40,
                "filename": "weights.safetensors",
                "sha256": "c" * 64,
            },
        ],
        "preparation": [],
    }


def _sealed_artifact_descriptor() -> bytes:
    value: dict[str, object] = {
        "asset": {
            "abi_version": 1,
            "entrypoint": "run",
            "path": "assets/runner.py",
            "sha256": hashlib.sha256(
                b"def run(context):\n    return None\n"
            ).hexdigest(),
        },
        "callbacks": [],
        "capability_requirements_digest": CapabilityRequirements().digest,
        "child_contract_digests": [],
        "format_version": 1,
        "inputs": [],
        "limits": {
            "max_concurrency": 1,
            "max_cpu_milliseconds": 1,
            "max_io_bytes": 1,
            "max_memory_bytes": 1,
            "max_runtime_milliseconds": 1,
        },
        "outputs": [
            {
                "max_bytes": 1,
                "media_type": "application/octet-stream",
                "role": "result",
                "schema_digest": None,
            }
        ],
        "profile_digest": "b" * 64,
        "schemas": [],
    }
    value["artifact_runner_digest"] = hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _stage(
    tmp_path: Path,
    *,
    with_capability_requirements: bool = False,
    with_model_materials: bool = False,
    model_materials: dict[str, object] | None = None,
    execution_descriptor: dict[str, object] | None = None,
    with_model_material_sets: bool = False,
    with_sealed_artifact_runner: bool = False,
    sealed_asset_body: str = "def run(context):\n    return None\n",
    sealed_artifact_descriptor: bytes | None = None,
    sealed_artifact_files: dict[str, bytes] | None = None,
):
    source = tmp_path / "packages" / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
    if with_capability_requirements or with_sealed_artifact_runner:
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
            json.dumps(
                model_materials or _model_materials(),
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
    if execution_descriptor is not None:
        (source / "execution-descriptor.json").write_text(
            json.dumps(execution_descriptor, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
    if with_model_material_sets:
        (source / "model-material-sets.json").write_text(
            json.dumps(
                {
                    "format_version": 1,
                    "material_sets": [
                        {"role": "suggest", "model_materials": _model_materials()}
                    ],
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
    if with_sealed_artifact_runner:
        (source / "assets").mkdir()
        (source / "assets" / "runner.py").write_text(
            sealed_asset_body, encoding="utf-8"
        )
        (source / "sealed-artifact-runner.json").write_bytes(
            sealed_artifact_descriptor or _sealed_artifact_descriptor()
        )
        for path, content in (sealed_artifact_files or {}).items():
            destination = source / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
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


def test_v2_execution_descriptor_round_trips_through_zip_import(
    tmp_path: Path,
) -> None:
    execution_descriptor = _execution_descriptor()
    model_materials = _v2_model_materials()
    staged, store = _stage(
        tmp_path,
        with_model_materials=True,
        model_materials=model_materials,
        execution_descriptor=execution_descriptor,
    )
    archive = tmp_path / "exports" / "v2.zip"

    export_staged_package(staged=staged, destination=archive)
    handle = PackageSourceSelectionPolicy(
        allowed_root=archive.parent, store=store
    ).select_zip(archive, now=NOW)
    imported = PrivatePackageStager(
        store=store, private_root=tmp_path / "imports"
    ).stage(handle, now=NOW)

    descriptor = parse_execution_descriptor(execution_descriptor)
    lock = parse_model_dependency_lock(model_materials)
    with zipfile.ZipFile(archive) as exported:
        assert exported.read("execution-descriptor.json") == descriptor.canonical_bytes
    assert (imported.root / "execution-descriptor.json").read_bytes() == (
        descriptor.canonical_bytes
    )
    assert imported.digest == staged.digest
    assert lock.execution_descriptor is not None
    assert lock.execution_descriptor.sha256 == descriptor.digest


def test_zip_import_rejects_duplicate_execution_descriptor_assets(
    tmp_path: Path,
) -> None:
    staged, store = _stage(
        tmp_path,
        with_model_materials=True,
        model_materials=_v2_model_materials(),
        execution_descriptor=_execution_descriptor(),
    )
    archive = tmp_path / "exports" / "v2.zip"
    export_staged_package(staged=staged, destination=archive)

    with zipfile.ZipFile(archive, "a") as exported:
        with pytest.warns(UserWarning, match="Duplicate name"):
            exported.writestr("execution-descriptor.json", b"{}")

    handle = PackageSourceSelectionPolicy(
        allowed_root=archive.parent, store=store
    ).select_zip(archive, now=NOW)
    with pytest.raises(PackageStagingError, match="duplicate"):
        PrivatePackageStager(store=store, private_root=tmp_path / "imports").stage(
            handle, now=NOW
        )


def test_export_rejects_tampered_v2_execution_descriptor(tmp_path: Path) -> None:
    staged, _ = _stage(
        tmp_path,
        with_model_materials=True,
        model_materials=_v2_model_materials(),
        execution_descriptor=_execution_descriptor(),
    )
    staged.root.chmod(0o700)
    descriptor = staged.root / "execution-descriptor.json"
    descriptor.chmod(0o600)
    descriptor.write_text('{"format_version":1}', encoding="utf-8")

    with pytest.raises(PackageExportError, match="model-material lock"):
        export_staged_package(staged=staged, destination=tmp_path / "v2.zip")


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


def test_export_and_import_bind_sealed_artifact_runner_digest(tmp_path: Path) -> None:
    staged, store = _stage(tmp_path, with_sealed_artifact_runner=True)
    archive = tmp_path / "exports" / "sealed-artifact.zip"

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

    expected = json.loads(_sealed_artifact_descriptor())["artifact_runner_digest"]
    assert staged_manifest["sealed_artifact_runner_digest"] == expected
    assert exported_manifest["sealed_artifact_runner_digest"] == expected
    assert imported.digest == staged.digest


def test_staging_rejects_a_sealed_runner_with_tampered_asset(tmp_path: Path) -> None:
    with pytest.raises(PackageStagingError, match="sealed artifact runner"):
        _stage(
            tmp_path,
            with_sealed_artifact_runner=True,
            sealed_asset_body="def run(context):\n    raise RuntimeError()\n",
        )


def test_staging_rejects_callback_without_declared_capability(tmp_path: Path) -> None:
    child = json.dumps(
        {
            "body": {},
            "callback_name": "generate",
            "capability_requirement": "model.generate.v1",
            "format_version": 1,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    child_digest = hashlib.sha256(child).hexdigest()
    descriptor = json.loads(_sealed_artifact_descriptor())
    descriptor["child_contract_digests"] = [child_digest]
    descriptor["callbacks"] = [
        {
            "child_contract_digest": child_digest,
            "max_calls": 1,
            "max_concurrency": 1,
            "max_request_bytes": 1,
            "max_response_bytes": 1,
            "max_total_request_bytes": 1,
            "max_total_response_bytes": 1,
            "name": "generate",
            "requirement": "model.generate.v1",
            "timeout_milliseconds": 1,
        }
    ]
    del descriptor["artifact_runner_digest"]
    descriptor["artifact_runner_digest"] = hashlib.sha256(
        json.dumps(descriptor, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    with pytest.raises(PackageStagingError, match="sealed artifact runner"):
        _stage(
            tmp_path,
            with_sealed_artifact_runner=True,
            sealed_artifact_descriptor=json.dumps(
                descriptor, sort_keys=True, separators=(",", ":")
            ).encode("utf-8"),
            sealed_artifact_files={"contracts/generate.json": child},
        )


def test_export_rejects_runner_capability_digest_mismatch(tmp_path: Path) -> None:
    staged, _ = _stage(tmp_path, with_sealed_artifact_runner=True)
    staged.root.chmod(0o700)
    runner_path = staged.root / "sealed-artifact-runner.json"
    runner_path.chmod(0o600)
    descriptor = json.loads(runner_path.read_text(encoding="utf-8"))
    descriptor["capability_requirements_digest"] = "0" * 64
    del descriptor["artifact_runner_digest"]
    descriptor["artifact_runner_digest"] = hashlib.sha256(
        json.dumps(descriptor, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    runner_path.write_text(
        json.dumps(descriptor, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )

    with pytest.raises(
        PackageExportError, match=r"^sealed artifact runner is invalid$"
    ):
        export_staged_package(staged=staged, destination=tmp_path / "export.zip")


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


def test_export_and_import_bind_declared_material_sets_digest(tmp_path: Path) -> None:
    staged, store = _stage(tmp_path, with_model_material_sets=True)
    archive = tmp_path / "exports" / "model-material-sets.zip"

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

    expected = parse_model_material_sets(
        {
            "format_version": 1,
            "material_sets": [
                {"role": "suggest", "model_materials": _model_materials()}
            ],
        }
    ).digest
    assert staged_manifest["model_material_sets_digest"] == expected
    assert exported_manifest["model_material_sets_digest"] == expected
    assert imported.digest == staged.digest


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
