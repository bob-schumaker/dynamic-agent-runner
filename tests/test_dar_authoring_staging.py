"""Tests for private no-follow staging of selected DAR packages."""

from __future__ import annotations

import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest


PLUGIN_SERVER_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "server"
sys.path.insert(0, str(PLUGIN_SERVER_ROOT))

from dar_workflow_server.package_sources import PackageSourceSelectionPolicy  # noqa: E402
from dar_workflow_server.staging import (  # noqa: E402
    PackageStagingError,
    PrivatePackageStager,
)
from dar_workflow_server.state import PrivateStateStore  # noqa: E402


NOW = datetime(2026, 8, 23, tzinfo=UTC)
TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "templates"


def _selection(tmp_path: Path, source: Path) -> tuple[str, PrivateStateStore]:
    store = PrivateStateStore(tmp_path / "state")
    handle = PackageSourceSelectionPolicy(
        allowed_root=source.parent, store=store
    ).select_directory(source, now=NOW)
    return handle, store


def _source_package(tmp_path: Path) -> Path:
    source = tmp_path / "packages" / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
    return source


def test_staging_copies_selected_package_and_validates_dar(tmp_path: Path) -> None:
    source = _source_package(tmp_path)
    handle, store = _selection(tmp_path, source)

    staged = PrivatePackageStager(store=store, private_root=tmp_path / "private").stage(
        handle, now=NOW
    )

    assert staged.root.is_dir()
    assert staged.root != source
    assert staged.file_count == 3
    assert staged.byte_count > 0
    assert len(staged.digest) == 64
    assert (staged.root / "agent-runtime.yaml").read_text(encoding="utf-8") == (
        source / "agent-runtime.yaml"
    ).read_text(encoding="utf-8")


def test_staging_does_not_follow_nested_symlinks(tmp_path: Path) -> None:
    source = _source_package(tmp_path)
    os.symlink(tmp_path / "outside", source / "unexpected-link")
    handle, store = _selection(tmp_path, source)

    with pytest.raises(PackageStagingError, match="symlink"):
        PrivatePackageStager(store=store, private_root=tmp_path / "private").stage(
            handle, now=NOW
        )


def test_staging_rejects_non_regular_entries(tmp_path: Path) -> None:
    source = _source_package(tmp_path)
    os.mkfifo(source / "unexpected-fifo")
    handle, store = _selection(tmp_path, source)

    with pytest.raises(PackageStagingError, match="non-regular"):
        PrivatePackageStager(store=store, private_root=tmp_path / "private").stage(
            handle, now=NOW
        )


def test_staged_copy_does_not_change_when_source_changes_after_staging(
    tmp_path: Path,
) -> None:
    source = _source_package(tmp_path)
    original = (source / "agent-design.md").read_text(encoding="utf-8")
    handle, store = _selection(tmp_path, source)
    staged = PrivatePackageStager(store=store, private_root=tmp_path / "private").stage(
        handle, now=NOW
    )

    (source / "agent-design.md").write_text("changed", encoding="utf-8")

    assert (staged.root / "agent-design.md").read_text(encoding="utf-8") == original


def test_staging_rejects_a_parent_path_swapped_for_a_symlink(tmp_path: Path) -> None:
    source = _source_package(tmp_path)
    handle, store = _selection(tmp_path, source)
    original_parent = source.parent
    moved_parent = tmp_path / "moved-packages"
    original_parent.rename(moved_parent)
    os.symlink(tmp_path / "outside", original_parent)

    with pytest.raises(PackageStagingError, match="symlink"):
        PrivatePackageStager(store=store, private_root=tmp_path / "private").stage(
            handle, now=NOW
        )


def test_invalid_dar_package_is_not_published_to_private_staging(
    tmp_path: Path,
) -> None:
    source = tmp_path / "packages" / "invalid"
    source.mkdir(parents=True)
    (source / "agent-runtime.yaml").write_text("not: valid", encoding="utf-8")
    handle, store = _selection(tmp_path, source)
    private_root = tmp_path / "private"

    with pytest.raises(PackageStagingError, match="DAR validation"):
        PrivatePackageStager(store=store, private_root=private_root).stage(
            handle, now=NOW
        )

    assert not list(private_root.glob("package-*"))
