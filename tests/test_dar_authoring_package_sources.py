"""Tests for human-only DAR authoring package-source selection."""

from __future__ import annotations

import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest


from dynamic_agent_runner.workflow_host.package_sources import (  # noqa: E402
    PackageSourceSelectionError,
    PackageSourceSelectionPolicy,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore  # noqa: E402


NOW = datetime(2026, 8, 23, tzinfo=UTC)


def _policy(tmp_path: Path, allowed_root: Path | None) -> PackageSourceSelectionPolicy:
    return PackageSourceSelectionPolicy(
        allowed_root=allowed_root,
        store=PrivateStateStore(tmp_path / "state"),
    )


def test_human_selected_directory_becomes_an_opaque_source_handle(
    tmp_path: Path,
) -> None:
    allowed_root = tmp_path / "packages"
    package = allowed_root / "document-helper"
    package.mkdir(parents=True)
    policy = _policy(tmp_path, allowed_root)

    handle = policy.select_directory(package, now=NOW)

    assert handle.startswith("v1.")
    assert str(package) not in handle


@pytest.mark.parametrize(
    "selection",
    [
        lambda root, outside: outside,
        lambda root, outside: root / "missing",
        lambda root, outside: Path("relative-package"),
        lambda root, outside: root / "document-helper" / "..",
    ],
)
def test_selection_rejects_outside_missing_or_noncanonical_paths(
    tmp_path: Path, selection: object
) -> None:
    allowed_root = tmp_path / "packages"
    package = allowed_root / "document-helper"
    package.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()

    with pytest.raises(PackageSourceSelectionError):
        _policy(tmp_path, allowed_root).select_directory(
            selection(allowed_root, outside),
            now=NOW,  # type: ignore[operator]
        )


def test_selection_rejects_symlinked_path_components(tmp_path: Path) -> None:
    allowed_root = tmp_path / "packages"
    allowed_root.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    symlink = allowed_root / "document-helper"
    os.symlink(target, symlink)

    with pytest.raises(PackageSourceSelectionError, match="symlink"):
        _policy(tmp_path, allowed_root).select_directory(symlink, now=NOW)


def test_human_selected_zip_becomes_an_opaque_source_handle(
    tmp_path: Path,
) -> None:
    allowed_root = tmp_path / "packages"
    allowed_root.mkdir()
    archive = allowed_root / "document-helper.zip"
    with zipfile.ZipFile(archive, "w"):
        pass

    handle = _policy(tmp_path, allowed_root).select_zip(archive, now=NOW)

    assert handle.startswith("v1.")
    assert str(archive) not in handle


def test_zip_selection_rejects_a_symlink(tmp_path: Path) -> None:
    allowed_root = tmp_path / "packages"
    allowed_root.mkdir()
    target = tmp_path / "target.zip"
    target.write_bytes(b"not a zip")
    archive = allowed_root / "document-helper.zip"
    os.symlink(target, archive)

    with pytest.raises(PackageSourceSelectionError, match="symlink"):
        _policy(tmp_path, allowed_root).select_zip(archive, now=NOW)


def test_selection_requires_a_human_configured_root(tmp_path: Path) -> None:
    with pytest.raises(PackageSourceSelectionError, match="allowed root"):
        _policy(tmp_path, None).select_directory(tmp_path, now=NOW)
