"""Tests for DAR authoring's immutable no-tool workflow policy."""

from __future__ import annotations

import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest


PLUGIN_SERVER_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "server"
sys.path.insert(0, str(PLUGIN_SERVER_ROOT))

from dar_workflow_server.catalog import PackageCatalog  # noqa: E402
from dar_workflow_server.package_sources import PackageSourceSelectionPolicy  # noqa: E402
from dar_workflow_server.policy import (  # noqa: E402
    PolicyCompilationError,
    compile_workflow_policy,
    resolve_capabilities,
)
from dar_workflow_server.staging import PrivatePackageStager  # noqa: E402
from dar_workflow_server.state import PrivateStateStore  # noqa: E402


NOW = datetime(2026, 8, 23, tzinfo=UTC)
TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "templates"


def _catalog_revision(tmp_path: Path, *, package_id: str | None = None):
    source = tmp_path / "packages" / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
    if package_id is not None:
        descriptor = source / "workflow-descriptor.yaml"
        descriptor.write_text(
            descriptor.read_text(encoding="utf-8").replace(
                "dar-authoring-no-tool-template", package_id
            ),
            encoding="utf-8",
        )
    store = PrivateStateStore(tmp_path / "state")
    source_handle = PackageSourceSelectionPolicy(
        allowed_root=source.parent, store=store
    ).select_directory(source, now=NOW)
    staged = PrivatePackageStager(store=store, private_root=tmp_path / "staging").stage(
        source_handle, now=NOW
    )
    return PackageCatalog(tmp_path / "catalog").import_staged(staged)


def test_policy_compiles_a_cataloged_no_tool_package(tmp_path: Path) -> None:
    policy = compile_workflow_policy(_catalog_revision(tmp_path))

    assert policy.package_id == "dar-authoring-no-tool-template"
    assert len(policy.descriptor_digest) == 64
    assert len(policy.policy_digest) == 64
    assert policy.required_capabilities == frozenset({"local_model"})


def test_capability_resolution_is_eligible_or_nonexecuting(tmp_path: Path) -> None:
    policy = compile_workflow_policy(_catalog_revision(tmp_path))

    unavailable = resolve_capabilities(policy, available_capabilities=set())
    eligible = resolve_capabilities(policy, available_capabilities={"local_model"})

    assert unavailable.status == "capability_unavailable"
    assert unavailable.missing_capabilities == ("local_model",)
    assert eligible.status == "eligible"
    assert eligible.missing_capabilities == ()


def test_policy_rejects_descriptor_package_identity_mismatch(tmp_path: Path) -> None:
    revision = _catalog_revision(tmp_path, package_id="other-package")

    with pytest.raises(PolicyCompilationError, match="package_id"):
        compile_workflow_policy(revision)
