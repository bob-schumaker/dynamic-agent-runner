"""Tests for package-only DAR authoring preflight."""

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
from dar_workflow_server.preflight import (  # noqa: E402
    PackagePreflightError,
    PackagePreflightService,
)
from dar_workflow_server.staging import PrivatePackageStager  # noqa: E402
from dar_workflow_server.state import PrivateStateStore  # noqa: E402


NOW = datetime(2026, 8, 23, tzinfo=UTC)
TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "templates"


def _service(
    tmp_path: Path, *, capabilities: set[str]
) -> tuple[PackagePreflightService, str]:
    source = tmp_path / "packages" / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
    store = PrivateStateStore(tmp_path / "state")
    source_handle = PackageSourceSelectionPolicy(
        allowed_root=source.parent, store=store
    ).select_directory(source, now=NOW)
    return (
        PackagePreflightService(
            stager=PrivatePackageStager(store=store, private_root=tmp_path / "staging"),
            catalog=PackageCatalog(tmp_path / "catalog"),
            available_capabilities=capabilities,
        ),
        source_handle,
    )


def test_preflight_returns_only_package_policy_and_capability_result(
    tmp_path: Path,
) -> None:
    service, source_handle = _service(tmp_path, capabilities={"local_model"})

    result = service.preflight(source_handle, now=NOW)

    assert result.package_id == "dar-authoring-no-tool-template"
    assert len(result.revision_digest) == 64
    assert len(result.workflow_policy_digest) == 64
    assert result.capability_resolution.status == "eligible"
    assert not hasattr(result, "workflow_id")
    assert not hasattr(result, "prepared_input_id")


def test_preflight_reports_unavailable_capabilities_without_binding(
    tmp_path: Path,
) -> None:
    service, source_handle = _service(tmp_path, capabilities=set())

    result = service.preflight(source_handle, now=NOW)

    assert result.capability_resolution.status == "capability_unavailable"
    assert result.capability_resolution.missing_capabilities == ("local_model",)


def test_preflight_rejects_a_raw_package_path(tmp_path: Path) -> None:
    service, _ = _service(tmp_path, capabilities={"local_model"})

    with pytest.raises(PackagePreflightError, match="opaque package source"):
        service.preflight(str(tmp_path / "packages" / "document-helper"), now=NOW)
