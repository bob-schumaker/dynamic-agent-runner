"""Tests for host-owned named reviewed tool-package resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from dynamic_agent_runner.workflow_host.reviewed_tool_packages import (
    ReviewedCapabilityTemplateControlPlane,
    ReviewedToolPackageBinding,
    ReviewedToolPackageControlPlane,
    ReviewedToolPackageError,
)
from dynamic_agent_runner.workflow_host.capabilities import (
    ReviewedCapabilityTemplate,
    ReviewedCapabilityTemplateOutput,
    reviewed_capability_template_digest,
)
from dynamic_agent_runner.workflow_host.descriptor import DeclaredArtifactTool
from dynamic_agent_runner.workflow_host.state import PrivateStateStore


def _binding() -> ReviewedToolPackageBinding:
    return ReviewedToolPackageBinding(
        binding_id="reviewed-binding-1",
        binding_digest="a" * 64,
        allowed_tool_ids=("packet_summary", "packet_filter"),
        artifact_aware_tool_ids=("packet_summary",),
    )


def _template(
    *, extension_binding: str = "host-vector-index-v1", enabled: bool = True
) -> ReviewedCapabilityTemplate:
    outputs = (
        ReviewedCapabilityTemplateOutput(
            "index_generation", "application/octet-stream", 1024, 60
        ),
        ReviewedCapabilityTemplateOutput(
            "index_manifest", "application/json", 1024, 60
        ),
        ReviewedCapabilityTemplateOutput(
            "coverage_report", "application/json", 1024, 60
        ),
    )
    operations = (
        "acknowledge_visibility",
        "begin_pending_publication",
        "compensate",
        "query_current_outcome",
    )
    return ReviewedCapabilityTemplate(
        capability_id="vector_index.build.v1",
        contract_version="1",
        template_digest=reviewed_capability_template_digest(
            capability_id="vector_index.build.v1",
            contract_version="1",
            input_fields=("job_handle",),
            required_dependency="embedding.execute.v1",
            outputs=outputs,
            max_receipt_bytes=1024,
            approval_class="human_write",
            extension_binding=extension_binding,
            recovery_operations=operations,
            success_receipt_schema_digest="d" * 64,
            generation_id_max_bytes=128,
            artifact_handle_max_bytes=128,
            count_ceiling=1024,
            failure_classifications=("host_failure", "publication_failed"),
            enabled=enabled,
        ),
        input_fields=("job_handle",),
        required_dependency="embedding.execute.v1",
        outputs=outputs,
        max_receipt_bytes=1024,
        approval_class="human_write",
        extension_binding=extension_binding,
        recovery_operations=operations,
        success_receipt_schema_digest="d" * 64,
        generation_id_max_bytes=128,
        artifact_handle_max_bytes=128,
        count_ceiling=1024,
        failure_classifications=("host_failure", "publication_failed"),
        enabled=enabled,
    )


def test_reviewed_template_registration_persists_one_exact_host_binding(
    tmp_path: Path,
) -> None:
    templates = ReviewedCapabilityTemplateControlPlane(
        store=PrivateStateStore(tmp_path / "state"), owner="local-user"
    )
    template = _template()

    templates.create(template=template)

    assert (
        templates.resolve(
            capability_id="vector_index.build.v1", current_template=template
        )
        == template
    )


def test_reviewed_template_registration_rejects_a_changed_host_binding(
    tmp_path: Path,
) -> None:
    templates = ReviewedCapabilityTemplateControlPlane(
        store=PrivateStateStore(tmp_path / "state"), owner="local-user"
    )
    templates.create(template=_template())

    with pytest.raises(ReviewedToolPackageError, match="unavailable"):
        templates.resolve(
            capability_id="vector_index.build.v1",
            current_template=_template(extension_binding="host-vector-index-v2"),
        )


def test_reviewed_template_registration_rejects_a_disabled_template(
    tmp_path: Path,
) -> None:
    templates = ReviewedCapabilityTemplateControlPlane(
        store=PrivateStateStore(tmp_path / "state"), owner="local-user"
    )
    disabled_template = _template(enabled=False)
    templates.create(template=disabled_template)

    with pytest.raises(ReviewedToolPackageError, match="unavailable"):
        templates.resolve(
            capability_id="vector_index.build.v1",
            current_template=disabled_template,
        )


def test_named_reviewed_package_captures_its_exact_binding_and_allowlists(
    tmp_path: Path,
) -> None:
    packages = ReviewedToolPackageControlPlane(
        store=PrivateStateStore(tmp_path / "state"),
        owner="local-user",
    )

    created = packages.create(package_name="network-tools", binding=_binding())
    resolved = packages.resolve(
        package_name="network-tools", current_binding=_binding()
    )

    assert created.package_name == "network-tools"
    assert resolved.binding_id == "reviewed-binding-1"
    assert resolved.allowed_tool_ids == ("packet_summary", "packet_filter")
    assert resolved.artifact_aware_tool_ids == ("packet_summary",)


def test_reviewed_package_rejects_unknown_or_stale_bindings(tmp_path: Path) -> None:
    packages = ReviewedToolPackageControlPlane(
        store=PrivateStateStore(tmp_path / "state"),
        owner="local-user",
    )
    packages.create(package_name="network-tools", binding=_binding())

    with pytest.raises(ReviewedToolPackageError, match="unavailable"):
        packages.resolve(package_name="missing-tools", current_binding=_binding())
    with pytest.raises(ReviewedToolPackageError, match="unavailable"):
        packages.resolve(
            package_name="network-tools",
            current_binding=ReviewedToolPackageBinding(
                binding_id="reviewed-binding-1",
                binding_digest="b" * 64,
                allowed_tool_ids=("packet_summary", "packet_filter"),
                artifact_aware_tool_ids=("packet_summary",),
            ),
        )


def test_reviewed_package_rejects_non_artifact_aware_tool_selection(
    tmp_path: Path,
) -> None:
    packages = ReviewedToolPackageControlPlane(
        store=PrivateStateStore(tmp_path / "state"),
        owner="local-user",
    )
    packages.create(package_name="network-tools", binding=_binding())

    with pytest.raises(ReviewedToolPackageError, match="not artifact-aware"):
        packages.require_artifact_tool(
            package_name="network-tools",
            tool_id="packet_filter",
            current_binding=_binding(),
        )


def test_artifact_tool_declaration_binds_one_reviewed_package_and_role() -> None:
    declared = DeclaredArtifactTool(
        tool_id="packet_summary",
        reviewed_package_name="network-tools",
        accepted_artifact_role="opaque_binary_artifact",
        max_result_bytes=4096,
    )

    assert declared.reviewed_package_name == "network-tools"
    assert declared.accepted_artifact_role == "opaque_binary_artifact"
