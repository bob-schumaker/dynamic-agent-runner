"""Tests for deterministic portable DAR authoring package ZIP export."""

from __future__ import annotations

import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


from dynamic_agent_runner.workflow_host.package_export import (  # noqa: E402
    PackageExportError,
    export_signed_staged_package,
    export_staged_package,
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


def _stage(tmp_path: Path):
    source = tmp_path / "packages" / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
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
