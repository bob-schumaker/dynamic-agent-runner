"""Tests for DAR authoring's immutable no-tool workflow policy."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml


from dynamic_agent_runner.workflow_host.catalog import PackageCatalog  # noqa: E402
from dynamic_agent_runner.workflow_host.package_sources import (
    PackageSourceSelectionPolicy,
)  # noqa: E402
from dynamic_agent_runner.workflow_host.policy import (  # noqa: E402
    PolicyCompilationError,
    compile_workflow_policy,
    resolve_capabilities,
)
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


def _catalog_revision(
    tmp_path: Path,
    *,
    package_id: str | None = None,
    with_read_only_mcp_tool: bool = False,
    with_side_effecting_mcp_tool: bool = False,
    package_skill_id: str | None = None,
    package_skill_bundled_path: str | None = None,
    enable_package_skill_source_resolution: bool = True,
    terminal_output_schema_ref: str | None = None,
):
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
    if terminal_output_schema_ref is not None:
        descriptor = source / "workflow-descriptor.yaml"
        descriptor_value = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
        descriptor_value["output"]["schema_ref"] = terminal_output_schema_ref
        descriptor_value["task_invocation"]["terminal_output_schema_ref"] = (
            terminal_output_schema_ref
        )
        descriptor.write_text(yaml.safe_dump(descriptor_value), encoding="utf-8")
    if with_read_only_mcp_tool:
        descriptor = source / "workflow-descriptor.yaml"
        descriptor_value = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
        descriptor_value["tools"] = [
            {
                "id": "mail_list_unread",
                "kind": "mcp",
                "remote_tool_name": "list_unread",
                "side_effect": "read",
            }
        ]
        descriptor_value["task_invocation"].update(
            {"allowed_tool_ids": ["mail_list_unread"], "max_total_tool_calls": 3}
        )
        descriptor.write_text(yaml.safe_dump(descriptor_value), encoding="utf-8")
        runtime = source / "agent-runtime.yaml"
        runtime_value = yaml.safe_load(runtime.read_text(encoding="utf-8"))
        runtime_value["tools"] = [
            {
                "id": "mail_list_unread",
                "label": "List unread mail",
                "tool_type": "external_api",
                "description_for_llm": "List unread mail.",
                "adapter": "host.mcp",
                "input_schema": {"type": "object", "properties": {}},
                "side_effect": "read",
                "approval_required": False,
                "timeout": "runtime_default",
                "retry_policy": "none",
                "failure_behavior": "error",
            }
        ]
        runtime_value["nodes"][0]["available_tools"] = ["mail_list_unread"]
        runtime.write_text(yaml.safe_dump(runtime_value), encoding="utf-8")
    if with_side_effecting_mcp_tool:
        descriptor = source / "workflow-descriptor.yaml"
        descriptor_value = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
        descriptor_value["tools"] = [
            {
                "id": "mail_send",
                "kind": "mcp",
                "remote_tool_name": "send_email",
                "side_effect": "write",
                "approval_required": True,
            }
        ]
        descriptor_value["task_invocation"].update(
            {
                "allowed_tool_ids": ["mail_send"],
                "max_total_tool_calls": 1,
                "allowed_structured_input_fields": ["recipient"],
                "allowed_artifact_roles": ["email_body"],
                "argument_sources": {
                    "mail_send": {
                        "recipient": {
                            "sources": ["sealed_structured_field:recipient"],
                            "authority": True,
                        },
                        "body": {
                            "sources": ["artifact_role:email_body"],
                            "authority": False,
                        },
                    }
                },
            }
        )
        descriptor.write_text(yaml.safe_dump(descriptor_value), encoding="utf-8")
        runtime = source / "agent-runtime.yaml"
        runtime_value = yaml.safe_load(runtime.read_text(encoding="utf-8"))
        runtime_value["tools"] = [
            {
                "id": "mail_send",
                "label": "Send mail",
                "tool_type": "external_api",
                "description_for_llm": "Send one reviewed email.",
                "adapter": "host.mcp",
                "input_schema": {
                    "type": "object",
                    "properties": {"envelope": {"type": "string"}},
                    "required": ["envelope"],
                    "additionalProperties": False,
                },
                "side_effect": "write",
                "approval_required": True,
                "timeout": "runtime_default",
                "retry_policy": "none",
                "failure_behavior": "error",
            }
        ]
        runtime_value["nodes"][0]["available_tools"] = ["mail_send"]
        runtime.write_text(yaml.safe_dump(runtime_value), encoding="utf-8")
    if package_skill_id is not None:
        descriptor = source / "workflow-descriptor.yaml"
        descriptor_value = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
        descriptor_value["skills"] = [package_skill_id]
        descriptor.write_text(yaml.safe_dump(descriptor_value), encoding="utf-8")
        bundled_path = (
            package_skill_bundled_path or f"skills/{package_skill_id}/SKILL.md"
        )
        skill_path = source / "skill-bundle" / bundled_path
        skill_path.parent.mkdir(parents=True)
        skill_path.write_text("# Package guidance\nUse package-local guidance.\n")
        runtime = source / "agent-runtime.yaml"
        runtime_value = yaml.safe_load(runtime.read_text(encoding="utf-8"))
        runtime_value["packaging"]["skill_bundle_dir"] = "skill-bundle"
        if enable_package_skill_source_resolution:
            runtime_value["runtime"]["execution_policy"]["skill_source_resolution"] = {
                "enabled": True,
                "allowed_sources": ["package_bundle"],
                "max_skill_bytes": 65536,
                "max_node_skill_bytes": 262144,
                "load_support_files": False,
                "prompt_role": "developer",
            }
        runtime_value["skills"] = [
            {
                "id": package_skill_id,
                "bundled_path": bundled_path,
            }
        ]
        runtime_value["nodes"][0]["skill_refs"] = [package_skill_id]
        runtime.write_text(yaml.safe_dump(runtime_value), encoding="utf-8")
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
    assert policy.required_capabilities == frozenset({"text_generation"})
    assert policy.workspace.accepted_input_types == ("text/plain",)


def test_policy_compiles_descriptor_declared_package_skill(tmp_path: Path) -> None:
    policy = compile_workflow_policy(
        _catalog_revision(tmp_path, package_skill_id="document-guidance")
    )

    assert policy.declared_skill_ids == ("document-guidance",)


def test_policy_rejects_package_skills_without_source_resolution(
    tmp_path: Path,
) -> None:
    revision = _catalog_revision(
        tmp_path,
        package_skill_id="document-guidance",
        enable_package_skill_source_resolution=False,
    )

    with pytest.raises(PolicyCompilationError, match="cataloged package policy"):
        compile_workflow_policy(revision)


def test_capability_resolution_is_eligible_or_nonexecuting(tmp_path: Path) -> None:
    policy = compile_workflow_policy(_catalog_revision(tmp_path))

    unavailable = resolve_capabilities(policy, available_capabilities=set())
    eligible = resolve_capabilities(policy, available_capabilities={"text_generation"})

    assert unavailable.status == "capability_unavailable"
    assert unavailable.missing_capabilities == ("text_generation",)
    assert eligible.status == "eligible"
    assert eligible.missing_capabilities == ()


def test_read_only_mcp_policy_requires_its_nonexecuting_capability(
    tmp_path: Path,
) -> None:
    policy = compile_workflow_policy(
        _catalog_revision(tmp_path, with_read_only_mcp_tool=True)
    )

    assert policy.task_invocation.allowed_tool_ids == ("mail_list_unread",)
    assert policy.required_capabilities == frozenset(
        {"text_generation", "mcp_read_only"}
    )
    unavailable = resolve_capabilities(
        policy, available_capabilities={"text_generation"}
    )
    eligible = resolve_capabilities(
        policy, available_capabilities={"text_generation", "mcp_read_only"}
    )
    assert unavailable.missing_capabilities == ("mcp_read_only",)
    assert eligible.status == "eligible"


def test_side_effecting_mcp_policy_requires_a_separate_unavailable_capability(
    tmp_path: Path,
) -> None:
    policy = compile_workflow_policy(
        _catalog_revision(tmp_path, with_side_effecting_mcp_tool=True)
    )

    assert policy.declared_tools[0].side_effect == "write"
    assert policy.required_capabilities == frozenset(
        {"text_generation", "mcp_side_effects"}
    )
    unavailable = resolve_capabilities(
        policy, available_capabilities={"text_generation", "mcp_read_only"}
    )
    assert unavailable.missing_capabilities == ("mcp_side_effects",)


def test_mixed_mcp_policy_requires_both_reviewed_surfaces(tmp_path: Path) -> None:
    source = tmp_path / "packages" / "mixed-mail"
    shutil.copytree(TEMPLATE_ROOT, source)
    descriptor = source / "workflow-descriptor.yaml"
    descriptor_value = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
    descriptor_value["tools"] = [
        {
            "id": "mail_lookup",
            "kind": "mcp",
            "remote_tool_name": "list_unread",
            "side_effect": "read",
        },
        {
            "id": "mail_delete",
            "kind": "mcp",
            "remote_tool_name": "delete_email",
            "side_effect": "delete",
            "approval_required": False,
        },
    ]
    descriptor_value["task_invocation"].update(
        {
            "allowed_tool_ids": ["mail_lookup", "mail_delete"],
            "max_total_tool_calls": 2,
            "argument_sources": {
                "mail_delete": {
                    "message_id": {
                        "sources": ["cited_original_prompt_span"],
                        "authority": True,
                    }
                }
            },
        }
    )
    descriptor.write_text(yaml.safe_dump(descriptor_value), encoding="utf-8")
    runtime = source / "agent-runtime.yaml"
    runtime_value = yaml.safe_load(runtime.read_text(encoding="utf-8"))
    runtime_value["tools"] = [
        {
            "id": "mail_lookup",
            "label": "List unread mail",
            "tool_type": "external_api",
            "description_for_llm": "List unread mail.",
            "adapter": "host.mcp",
            "input_schema": {"type": "object"},
            "side_effect": "read",
            "approval_required": False,
            "timeout": "runtime_default",
            "retry_policy": "none",
            "failure_behavior": "error",
        },
        {
            "id": "mail_delete",
            "label": "Delete mail",
            "tool_type": "external_api",
            "description_for_llm": "Delete mail.",
            "adapter": "host.mcp",
            "input_schema": {"type": "object"},
            "side_effect": "delete",
            "approval_required": False,
            "timeout": "runtime_default",
            "retry_policy": "none",
            "failure_behavior": "error",
        },
    ]
    runtime_value["nodes"][0]["available_tools"] = ["mail_lookup", "mail_delete"]
    runtime.write_text(yaml.safe_dump(runtime_value), encoding="utf-8")
    store = PrivateStateStore(tmp_path / "state")
    handle = PackageSourceSelectionPolicy(
        allowed_root=source.parent, store=store
    ).select_directory(source, now=NOW)
    revision = PackageCatalog(tmp_path / "catalog").import_staged(
        PrivatePackageStager(store=store, private_root=tmp_path / "staging").stage(
            handle, now=NOW
        )
    )

    policy = compile_workflow_policy(revision)

    assert policy.required_capabilities == frozenset(
        {"text_generation", "mcp_read_only", "mcp_side_effects"}
    )
    assert resolve_capabilities(
        policy,
        available_capabilities={"text_generation", "mcp_read_only"},
    ).missing_capabilities == ("mcp_side_effects",)


def test_staging_rejects_descriptor_package_identity_mismatch(tmp_path: Path) -> None:
    with pytest.raises(PackageStagingError, match="descriptor is incompatible"):
        _catalog_revision(tmp_path, package_id="other-package")


def test_policy_rejects_unknown_registered_terminal_output_contract(
    tmp_path: Path,
) -> None:
    revision = _catalog_revision(
        tmp_path, terminal_output_schema_ref="missing-contract"
    )

    with pytest.raises(PolicyCompilationError, match="terminal output contract"):
        compile_workflow_policy(revision)
