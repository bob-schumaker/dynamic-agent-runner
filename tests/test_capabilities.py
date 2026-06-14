"""Tests for capability/status reporting."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from dynamic_agent_runner.errors import ArtifactLoadError
from dynamic_agent_runner.models import ToolDefinition
from dynamic_agent_runner.registry import InMemoryToolRegistry, RegisteredTool


def write_agent_package(tmp_path: Path, runtime_yaml: str) -> Path:
    package_dir = tmp_path / "agent"
    package_dir.mkdir()
    (package_dir / "agent-runtime.yaml").write_text(
        dedent(runtime_yaml), encoding="utf-8"
    )
    (package_dir / "agent-design.md").write_text("# Agent\n", encoding="utf-8")
    (package_dir / "agent-graph.mmd").write_text("flowchart TD\n", encoding="utf-8")
    return package_dir


def test_capability_report_types_are_package_exports() -> None:
    import dynamic_agent_runner

    assert dynamic_agent_runner.CapabilityState.LIVE == "live"
    assert dynamic_agent_runner.CapabilityStatusItem is not None
    assert dynamic_agent_runner.CapabilityStatusReport is not None
    assert dynamic_agent_runner.CapabilityStatusSummary is not None
    assert dynamic_agent_runner.inspect_agent_package_capabilities is not None


def test_capability_status_report_summarizes_items_deterministically() -> None:
    from dynamic_agent_runner.capabilities import (
        CapabilityState,
        CapabilityStatusItem,
        CapabilityStatusReport,
    )

    report = CapabilityStatusReport.from_items(
        package_id="demo-agent",
        items=[
            CapabilityStatusItem(
                id="metadata.guardrails",
                label="Guardrail declarations",
                state=CapabilityState.METADATA_ONLY,
                category="metadata",
                summary="Guardrail declarations are preserved but not executed.",
                owner="live-guardrail-execution",
            ),
            CapabilityStatusItem(
                id="runtime.execution",
                label="Finite workflow execution",
                state=CapabilityState.LIVE,
                category="runtime",
                summary="Finite workflow execution is implemented.",
            ),
        ],
    )

    assert report.package_id == "demo-agent"
    assert [item.id for item in report.items] == [
        "metadata.guardrails",
        "runtime.execution",
    ]
    assert report.summary.total == 2
    assert report.summary.counts_by_state == {
        "live": 1,
        "metadata_only": 1,
    }
    assert report.valid is True


def test_inspect_agent_package_capabilities_reports_metadata_only_features(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner import inspect_agent_package_capabilities

    package_dir = write_agent_package(
        tmp_path,
        """
        format_version: 1
        package_type: dynamic_agent_design
        package_id: capability-rich-agent
        entrypoint: answer
        packaging:
          mode: hybrid_bundle
        runtime:
          execution_policy:
            approval_interruption:
              mode: pause_on_approval
              persist: in_memory
              resume_from: approval_decision
              pending_tool_calls_state_key: pending_tools
              pending_approvals_state_key: pending_approvals
              interruption_state_key: interruption
              resume_token_state_key: resume_token
            async_session:
              mode: create_or_resume
              persist: in_memory
              history: last_turn
              session_id_state_key: session_id
              session_messages_state_key: session_messages
            sandbox_runtime:
              mode: per_run_workspace
              filesystem: workspace_write
              persist_workspace: per_run
              command_policy: allow_list
              writable_root_state_key: writable_root
              working_directory_state_key: working_directory
            tool_use_completion:
              run_again: required
              stop_on_tool: enabled
              final_output: state_field
              final_output_state_key: final_answer
        metadata:
          handoffs:
            - id: handoff_to_reviewer
              target: reviewer
              on_handoff: switch_active_profile
              nested_history: filtered
        extensions:
          guardrails:
            declarations:
              - id: input_policy
                phase: input
                behavior_on_tripwire: abort
          mcp_registry_sources:
            sources:
              - id: repo_tools
                server: repo-mcp
                status: active
                tool_cache: enabled
                disabled: false
                operation_locking: per_server
                memory_pollution: low
          mcp_lifecycle_diagnostics:
            startup_mode: degraded
            reconnect: automatic
            cleanup_timeout: 5s
            active_servers_state_key: mcp_active
            failed_servers_state_key: mcp_failed
            error_map_state_key: mcp_errors
        skills:
          - id: concise-writer
        nodes:
          - id: answer
            kind: llm_step
            prompt:
              user_template: "Answer {prompt}"
            skill_refs:
              - concise-writer
        edges: []
        """,
    )

    report = inspect_agent_package_capabilities(package_directory=package_dir)

    assert report.package_id == "capability-rich-agent"
    assert report.valid is True
    items = {item.id: item for item in report.items}
    assert items["runtime.execution"].state == "live"
    for item_id in (
        "metadata.approval_interruption",
        "metadata.async_session",
        "metadata.sandbox_runtime",
        "metadata.tool_use_completion",
        "metadata.handoffs",
        "metadata.guardrails",
        "metadata.mcp_registry_sources",
        "metadata.skill_refs",
    ):
        assert items[item_id].state == "metadata_only"
    assert report.summary.counts_by_state["metadata_only"] == 8


def test_inspect_agent_package_capabilities_reports_invalid_packages(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner import CapabilityState, inspect_agent_package_capabilities

    package_dir = tmp_path / "missing"

    report = inspect_agent_package_capabilities(package_directory=package_dir)

    assert report.valid is False
    assert report.validation_error is not None
    assert report.items[0].id == "package.validation"
    assert report.items[0].state == CapabilityState.INVALID

    with pytest.raises(ArtifactLoadError):
        inspect_agent_package_capabilities(package_directory=package_dir, strict=True)


def test_inspect_agent_package_capabilities_reports_collaborator_coverage(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner import CapabilityState, inspect_agent_package_capabilities

    class FakeAdapter:
        models = ("covered-model",)

    package_dir = write_agent_package(
        tmp_path,
        """
        format_version: 1
        package_type: dynamic_agent_design
        package_id: collaborator-agent
        entrypoint: answer
        packaging:
          mode: hybrid_bundle
        nodes:
          - id: answer
            kind: llm_step
            model: missing-model
            prompt:
              user_template: "Answer {prompt}"
            available_tools:
              - search_repo
          - id: search
            kind: tool_use_step
            tool_id: search_repo
        edges:
          - source: answer
            target: search
            edge_kind: sequential
        tools:
          - id: search_repo
            adapter: runtime.search_repo
        """,
    )
    missing_report = inspect_agent_package_capabilities(
        package_directory=package_dir,
        model_adapter=[FakeAdapter()],
        model_adapter_coverage="strict",
    )
    missing_items = {item.id: item for item in missing_report.items}

    assert missing_items["model.answer"].state == CapabilityState.MISSING_COLLABORATOR
    assert (
        missing_items["tool.search_repo"].state == CapabilityState.MISSING_COLLABORATOR
    )
    assert missing_items["built_in.local_workspace"].state == CapabilityState.DISABLED

    registry = InMemoryToolRegistry(
        [
            RegisteredTool(
                ToolDefinition.from_mapping(
                    {"id": "search_repo", "input_schema": {"type": "object"}}
                ),
                lambda _args: {"ok": True},
            )
        ],
        disabled_tools=("search_repo",),
    )
    disabled_report = inspect_agent_package_capabilities(
        package_directory=package_dir,
        tool_registry=registry,
        built_in_tool_packs=("local_workspace",),
    )
    disabled_items = {item.id: item for item in disabled_report.items}

    assert disabled_items["tool.search_repo"].state == CapabilityState.DISABLED
    assert disabled_items["built_in.local_workspace"].state == CapabilityState.LIVE


def test_inspect_agent_package_capabilities_reports_live_approval_interruption(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner import CapabilityState, inspect_agent_package_capabilities

    package_dir = write_agent_package(
        tmp_path,
        """
        format_version: 1
        package_type: dynamic_agent_design
        package_id: approval-capability-agent
        entrypoint: write
        packaging:
          mode: hybrid_bundle
        runtime:
          execution_policy:
            approval_interruption:
              mode: pause_on_approval
              persist: in_memory
              resume_from: approval_decision
              pending_tool_calls_state_key: pending_tools
              pending_approvals_state_key: pending_approvals
              interruption_state_key: interruption
              resume_token_state_key: resume_token
        nodes:
          - id: write
            kind: tool_use_step
            tool_id: workspace_write
            inputs:
              path: notes.txt
              content: hello
        edges: []
        tools:
          - id: workspace_write
            approval_required: yes
            side_effect: write
            sandbox: workspace
        """,
    )
    registry = InMemoryToolRegistry(
        [
            RegisteredTool(
                ToolDefinition.from_mapping(
                    {
                        "id": "workspace_write",
                        "approval_required": "yes",
                        "side_effect": "write",
                        "sandbox": "workspace",
                    }
                ),
                lambda _args: {"ok": True},
            )
        ]
    )

    report = inspect_agent_package_capabilities(
        package_directory=package_dir,
        tool_registry=registry,
    )
    items = {item.id: item for item in report.items}

    assert items["runtime.approval_interruption"].state == CapabilityState.LIVE
    assert items["runtime.approval_interruption"].details == {
        "node_id": "write",
        "tool_id": "workspace_write",
    }


def test_inspect_agent_package_capabilities_reports_live_mcp_registry_entries(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner import (
        CapabilityState,
        MCPToolBinding,
        create_mcp_registry,
        inspect_agent_package_capabilities,
    )

    package_dir = write_agent_package(
        tmp_path,
        """
        format_version: 1
        package_type: dynamic_agent_design
        package_id: mcp-capability-agent
        entrypoint: echo
        packaging:
          mode: hybrid_bundle
        extensions:
          mcp_registry_sources:
            sources:
              - id: repo-tools
                server: repo-mcp
                status: active
                tool_cache: enabled
                disabled: false
                operation_locking: per_server
                memory_pollution: low
        nodes:
          - id: echo
            kind: tool_use_step
            tool_id: mcp.echo
            inputs:
              text: hello
        edges: []
        tools:
          - id: mcp.echo
        """,
    )
    registry = create_mcp_registry(
        [
            MCPToolBinding(
                tool_id="mcp.echo",
                source_id="repo-tools",
                server_id="repo-mcp",
                mcp_tool_name="echo",
                handler=lambda _args: {"ok": True},
            )
        ]
    )

    report = inspect_agent_package_capabilities(
        package_directory=package_dir,
        tool_registry=registry,
    )
    items = {item.id: item for item in report.items}

    assert items["metadata.mcp_registry_sources"].state == CapabilityState.METADATA_ONLY
    assert items["mcp.tool.mcp.echo"].state == CapabilityState.LIVE
    assert items["mcp.tool.mcp.echo"].details == {
        "source_id": "repo-tools",
        "detail": "repo-mcp:echo",
    }
