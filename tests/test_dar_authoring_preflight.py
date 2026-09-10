"""Tests for package-only DAR authoring preflight."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml


from dynamic_agent_runner.workflow_host.catalog import PackageCatalog  # noqa: E402
from dynamic_agent_runner.workflow_host.capabilities import (  # noqa: E402
    BUILTIN_CAPABILITY_CONTRACTS,
    CapabilityCatalog,
    CapabilityRequirement,
    CapabilityRequirements,
)
from dynamic_agent_runner.workflow_host.package_sources import (
    PackageSourceSelectionPolicy,
)  # noqa: E402
from dynamic_agent_runner.workflow_host.preflight import (  # noqa: E402
    PackagePreflightError,
    PackagePreflightService,
)
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


def _service(
    tmp_path: Path,
    *,
    capabilities: set[str],
    capability_catalog: CapabilityCatalog | None = None,
    with_capability_requirements: bool = False,
) -> tuple[PackagePreflightService, str]:
    source = tmp_path / "packages" / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
    if with_capability_requirements:
        contract = BUILTIN_CAPABILITY_CONTRACTS[0]
        requirement = CapabilityRequirement(
            contract.capability_id,
            contract.contract_version,
            contract.contract_digest,
            ("multimodal",),
        )
        requirements = CapabilityRequirements((requirement,))
        descriptor = source / "workflow-descriptor.yaml"
        value = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
        value["dar_runtime"]["required_version"] = "0.1.17"
        value["capability_requirements"] = {
            "format_version": 1,
            "required_capabilities": [requirement.to_mapping()],
            "capability_requirements_digest": requirements.digest,
            "bindings": {},
        }
        descriptor.write_text(yaml.safe_dump(value), encoding="utf-8")
    store = PrivateStateStore(tmp_path / "state")
    source_handle = PackageSourceSelectionPolicy(
        allowed_root=source.parent, store=store
    ).select_directory(source, now=NOW)
    return (
        PackagePreflightService(
            stager=PrivatePackageStager(store=store, private_root=tmp_path / "staging"),
            catalog=PackageCatalog(tmp_path / "catalog"),
            available_capabilities=capabilities,
            capability_catalog=capability_catalog,
        ),
        source_handle,
    )


def test_preflight_returns_only_package_policy_and_capability_result(
    tmp_path: Path,
) -> None:
    service, source_handle = _service(tmp_path, capabilities={"text_generation"})

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
    assert result.capability_resolution.missing_capabilities == ("text_generation",)


def test_preflight_rejects_a_raw_package_path(tmp_path: Path) -> None:
    service, _ = _service(tmp_path, capabilities={"text_generation"})

    with pytest.raises(PackagePreflightError, match="opaque package source"):
        service.preflight(str(tmp_path / "packages" / "document-helper"), now=NOW)


def test_preflight_rejects_unsatisfied_exact_capability_before_policy_binding(
    tmp_path: Path,
) -> None:
    contract = BUILTIN_CAPABILITY_CONTRACTS[0]
    service, source_handle = _service(
        tmp_path,
        capabilities={"text_generation"},
        capability_catalog=CapabilityCatalog((contract,), ()),
        with_capability_requirements=True,
    )

    with pytest.raises(PackagePreflightError, match="preflight failed"):
        service.preflight(source_handle, now=NOW)
