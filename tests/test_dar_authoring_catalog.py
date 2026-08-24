"""Tests for the immutable DAR authoring package catalog."""

from __future__ import annotations

import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path


PLUGIN_SERVER_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "server"
sys.path.insert(0, str(PLUGIN_SERVER_ROOT))

from dar_workflow_server.catalog import PackageCatalog  # noqa: E402
from dar_workflow_server.package_sources import PackageSourceSelectionPolicy  # noqa: E402
from dar_workflow_server.staging import PrivatePackageStager  # noqa: E402
from dar_workflow_server.state import PrivateStateStore  # noqa: E402


NOW = datetime(2026, 8, 23, tzinfo=UTC)
TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "templates"


def _stage(tmp_path: Path, content: str | None = None):
    source = tmp_path / "packages" / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
    if content is not None:
        (source / "agent-design.md").write_text(content, encoding="utf-8")
    store = PrivateStateStore(tmp_path / "state")
    source_handle = PackageSourceSelectionPolicy(
        allowed_root=source.parent, store=store
    ).select_directory(source, now=NOW)
    return PrivatePackageStager(store=store, private_root=tmp_path / "staging").stage(
        source_handle, now=NOW
    )


def test_catalog_reimport_is_idempotent(tmp_path: Path) -> None:
    staged = _stage(tmp_path)
    catalog = PackageCatalog(tmp_path / "catalog")

    first = catalog.import_staged(staged)
    second = catalog.import_staged(staged)

    assert first == second
    assert catalog.revisions("dar-authoring-no-tool-template") == (first,)
    assert first.package_id == "dar-authoring-no-tool-template"
    assert first.revision_digest == staged.digest
    assert first.package_root == staged.root


def test_catalog_retains_prior_revisions_for_same_package_id(tmp_path: Path) -> None:
    first_staged = _stage(tmp_path / "one", content="first revision")
    second_staged = _stage(tmp_path / "two", content="second revision")
    catalog = PackageCatalog(tmp_path / "catalog")

    first = catalog.import_staged(first_staged)
    second = catalog.import_staged(second_staged)

    revisions = catalog.revisions("dar-authoring-no-tool-template")
    assert {revision.revision_digest for revision in revisions} == {
        first.revision_digest,
        second.revision_digest,
    }
    assert len(revisions) == 2


def test_catalog_revisions_survive_reopen(tmp_path: Path) -> None:
    staged = _stage(tmp_path)
    root = tmp_path / "catalog"
    PackageCatalog(root).import_staged(staged)

    revisions = PackageCatalog(root).revisions("dar-authoring-no-tool-template")

    assert len(revisions) == 1
    assert revisions[0].revision_digest == staged.digest
