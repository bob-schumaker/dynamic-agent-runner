"""Tests for deterministic portable DAR authoring package ZIP export."""

from __future__ import annotations

import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

PLUGIN_SERVER_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "server"
sys.path.insert(0, str(PLUGIN_SERVER_ROOT))

from dar_workflow_server.package_export import (  # noqa: E402
    PackageExportError,
    export_staged_package,
)
from dar_workflow_server.package_sources import PackageSourceSelectionPolicy  # noqa: E402
from dar_workflow_server.staging import PrivatePackageStager  # noqa: E402
from dar_workflow_server.state import PrivateStateStore  # noqa: E402


NOW = datetime(2026, 8, 23, tzinfo=UTC)
TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "templates"


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
