"""Tests for capability/status reporting."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from dynamic_agent_runner.artifacts import load_runtime_manifest
from dynamic_agent_runner.errors import ArtifactLoadError, DynamicAgentRunnerError
from dynamic_agent_runner.models import LoadedAgentWorkflow, ToolDefinition
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
    assert dynamic_agent_runner.inspect_agent_workflow_capabilities is not None


def test_inspect_agent_workflow_capabilities_accepts_inline_manifest_mapping() -> None:
    from dynamic_agent_runner import inspect_agent_workflow_capabilities

    report = inspect_agent_workflow_capabilities(
        runtime_manifest={
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "inline-capability-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Answer {prompt}"},
                }
            ],
            "edges": [],
        }
    )

    items = {item.id: item for item in report.items}
    assert report.package_id == "inline-capability-agent"
    assert report.valid is True
    assert items["runtime.execution"].state == "live"
    assert items["model.answer"].details == {
        "model": "gpt-test",
        "coverage": "augmented",
    }


def test_inspect_agent_workflow_capabilities_accepts_inline_manifest_yaml() -> None:
    from dynamic_agent_runner import (
        CapabilityStatusReport,
        inspect_agent_workflow_capabilities,
    )

    report = inspect_agent_workflow_capabilities(
        runtime_manifest=dedent(
            """
            format_version: 1
            package_type: dynamic_agent_design
            package_id: inline-yaml-capability-agent
            entrypoint: answer
            packaging:
              mode: hybrid_bundle
            runtime:
              execution_policy:
                model: gpt-test
            nodes:
              - id: answer
                kind: llm_step
                prompt:
                  user_template: "Answer {prompt}"
            edges: []
            """
        )
    )

    assert isinstance(report, CapabilityStatusReport)
    assert report.package_id == "inline-yaml-capability-agent"
    assert report.valid is True


def test_inspect_agent_workflow_capabilities_accepts_loaded_workflow() -> None:
    from dynamic_agent_runner import InMemorySessionStore
    from dynamic_agent_runner.capabilities import (
        CapabilityState,
        inspect_agent_workflow_capabilities,
    )

    workflow = LoadedAgentWorkflow(
        runtime_manifest=load_runtime_manifest(
            {
                "format_version": 1,
                "package_type": "dynamic_agent_design",
                "package_id": "loaded-workflow-capability-agent",
                "entrypoint": "answer",
                "packaging": {"mode": "hybrid_bundle"},
                "runtime": {
                    "execution_policy": {
                        "model": "gpt-test",
                        "async_session": {
                            "mode": "create_or_resume",
                            "persist": "in_memory",
                            "history": "last_turn",
                            "session_id_state_key": "session_id",
                            "session_messages_state_key": "session_messages",
                        },
                    }
                },
                "nodes": [
                    {
                        "id": "answer",
                        "kind": "llm_step",
                        "prompt": {"user_template": "Answer {prompt}"},
                    }
                ],
                "edges": [],
            }
        )
    )

    report = inspect_agent_workflow_capabilities(
        workflow=workflow,
        session_store=InMemorySessionStore(),
    )
    items = {item.id: item for item in report.items}

    assert report.package_id == "loaded-workflow-capability-agent"
    assert items["runtime.async_session.in_memory"].state == CapabilityState.LIVE


def test_inspect_agent_workflow_capabilities_reports_invalid_inline_manifest() -> None:
    from dynamic_agent_runner import (
        CapabilityState,
        inspect_agent_workflow_capabilities,
    )

    report = inspect_agent_workflow_capabilities(
        runtime_manifest={"package_id": "invalid-inline-agent"}
    )

    items = {item.id: item for item in report.items}
    assert report.package_id == "invalid-inline-agent"
    assert report.valid is False
    assert report.validation_error is not None
    assert items["package.validation"].state == CapabilityState.INVALID

    with pytest.raises(DynamicAgentRunnerError):
        inspect_agent_workflow_capabilities(
            runtime_manifest={"package_id": "invalid-inline-agent"},
            strict=True,
        )


def test_inspect_agent_workflow_capabilities_reports_host_tool_ids() -> None:
    from dynamic_agent_runner import (
        HostToolBinding,
        create_host_tool_registry,
        inspect_agent_workflow_capabilities,
    )

    registry = create_host_tool_registry(
        [
            HostToolBinding(
                canonical_id="project.tools.search-docs",
                model_id="search_docs",
                aliases=("find_docs",),
                description="Search host project documents.",
                handler=lambda _args: {"ok": True},
            )
        ]
    )

    report = inspect_agent_workflow_capabilities(
        runtime_manifest={
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "host-tool-capability-agent",
            "entrypoint": "search",
            "packaging": {"mode": "hybrid_bundle"},
            "nodes": [
                {
                    "id": "search",
                    "kind": "tool_use_step",
                    "tool_id": "search_docs",
                    "inputs": {"query": "agent"},
                }
            ],
            "edges": [],
            "tools": [{"id": "search_docs"}],
        },
        tool_registry=registry,
    )

    items = {item.id: item for item in report.items}
    assert items["tool.search_docs"].state == "live"
    assert items["tool.search_docs"].details == {
        "host_canonical_id": "project.tools.search-docs",
        "host_model_id": "search_docs",
        "host_aliases": ("find_docs",),
    }


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


def test_inspect_agent_package_capabilities_reports_live_in_memory_sessions(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner import (
        InMemorySessionStore,
        inspect_agent_package_capabilities,
    )

    package_dir = write_agent_package(
        tmp_path,
        """
        format_version: 1
        package_type: dynamic_agent_design
        package_id: live-session-agent
        entrypoint: answer
        packaging:
          mode: hybrid_bundle
        runtime:
          execution_policy:
            model: gpt-test
            async_session:
              mode: create_or_resume
              persist: in_memory
              history: full
              session_id_state_key: session_id
              session_messages_state_key: session_messages
        nodes:
          - id: answer
            kind: llm_step
            prompt:
              user_template: "Answer {prompt}"
        edges: []
        """,
    )

    report = inspect_agent_package_capabilities(
        package_directory=package_dir,
        session_store=InMemorySessionStore(),
    )

    items = {item.id: item for item in report.items}
    assert items["metadata.async_session"].state == "metadata_only"
    assert items["runtime.async_session.in_memory"].state == "live"


def test_inspect_agent_package_capabilities_reports_live_skill_sources(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner import CapabilityState, inspect_agent_package_capabilities

    package_dir = write_agent_package(
        tmp_path,
        """
        format_version: 1
        package_type: dynamic_agent_design
        package_id: live-skill-source-agent
        entrypoint: answer
        packaging:
          mode: hybrid_bundle
          skill_bundle_dir: skill-bundle
        runtime:
          execution_policy:
            model: gpt-test
            skill_source_resolution:
              enabled: true
              allowed_sources:
                - package_bundle
              max_skill_bytes: 65536
              max_node_skill_bytes: 262144
              load_support_files: false
              prompt_role: developer
        skills:
          - id: concise-writer
            bundled_path: skills/concise-writer/SKILL.md
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
    skill_path = package_dir / "skill-bundle" / "skills" / "concise-writer" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text("# Concise writer\nBe brief.\n", encoding="utf-8")

    report = inspect_agent_package_capabilities(package_directory=package_dir)

    items = {item.id: item for item in report.items}
    assert report.valid is True
    assert "metadata.skill_refs" not in items
    assert items["runtime.skill_source_resolution"].state == CapabilityState.LIVE
    assert items["runtime.skill_source_resolution"].details == {
        "allowed_sources": ("package_bundle",),
        "prompt_role": "developer",
        "referenced_skills": 1,
    }


def test_inspect_agent_package_capabilities_reports_rejected_skill_sources(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner import CapabilityState, inspect_agent_package_capabilities

    package_dir = write_agent_package(
        tmp_path,
        """
        format_version: 1
        package_type: dynamic_agent_design
        package_id: rejected-skill-source-agent
        entrypoint: answer
        packaging:
          mode: hybrid_bundle
          skill_bundle_dir: skill-bundle
        runtime:
          execution_policy:
            model: gpt-test
            skill_source_resolution:
              enabled: true
              allowed_sources:
                - package_bundle
              max_skill_bytes: 65536
              max_node_skill_bytes: 262144
              load_support_files: false
              prompt_role: developer
        skills:
          - id: unsafe-skill
            bundled_path: skills/unsafe-skill/SKILL.md
        nodes:
          - id: answer
            kind: llm_step
            prompt:
              user_template: "Answer {prompt}"
            skill_refs:
              - unsafe-skill
        edges: []
        """,
    )
    skill_path = package_dir / "skill-bundle" / "skills" / "unsafe-skill" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_bytes(b"\x00binary")

    report = inspect_agent_package_capabilities(package_directory=package_dir)

    items = {item.id: item for item in report.items}
    assert report.package_id == "rejected-skill-source-agent"
    assert report.valid is False
    assert items["package.validation"].state == CapabilityState.INVALID
    assert items["runtime.skill_source_resolution"].state == CapabilityState.INVALID
    assert "appears to be binary" in str(
        items["runtime.skill_source_resolution"].details["validation_error"]
    )


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
    assert missing_items["built_in.web"].state == CapabilityState.DISABLED
    assert missing_items["built_in.workspace_data"].state == CapabilityState.DISABLED
    assert missing_items["built_in.subagent"].state == CapabilityState.DISABLED

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
        built_in_tool_packs=("local_workspace", "web", "workspace_data", "subagent"),
    )
    disabled_items = {item.id: item for item in disabled_report.items}

    assert disabled_items["tool.search_repo"].state == CapabilityState.DISABLED
    assert disabled_items["built_in.local_workspace"].state == CapabilityState.LIVE
    assert disabled_items["built_in.web"].state == CapabilityState.LIVE
    assert disabled_items["built_in.workspace_data"].state == CapabilityState.LIVE
    assert disabled_items["built_in.subagent"].state == CapabilityState.LIVE


def test_inspect_agent_package_capabilities_reports_rag_readiness(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner import CapabilityState, inspect_agent_package_capabilities

    package_dir = write_agent_package(
        tmp_path,
        """
        format_version: 1
        package_type: dynamic_agent_design
        package_id: rag-capability-agent
        entrypoint: answer
        packaging:
          mode: hybrid_bundle
        metadata:
          patterns_present:
            - rag
            - embedding_retrieval
          rag_pipeline:
            orchestration_mode: hybrid_retrieval
            retrieval_mode: hybrid
            retrievers:
              - id: keyword
                tool_id: keyword_search
                mode: lexical_keyword
                required: true
              - id: semantic
                tool_id: semantic_search
                mode: embedding_semantic
                required: true
              - id: graph_optional
                tool_id: graph_search
                mode: graph
                required: false
            fusion: rrf
            reranking: caller_adapter
            compression: none
            correction: optional
            embedding_capability: required
            graph_capability: not_applicable
            provenance_required: true
            context_assembly:
              target: prepare_model_input
              max_context_tokens: 4096
              required_evidence_fields:
                - source_id
                - chunk_id
                - citation_handle
            source_readiness:
              source_registry: external_service
              refresh_mode: scheduled
              stale_state: stale_but_allowed
            permissions:
              permission_filtering: required
              permission_failure_policy: fail_closed
              audit_required: true
            cache:
              retrieval_results: optional
            degraded_states:
              - stale_but_allowed
              - partial_results
        nodes:
          - id: answer
            kind: llm_step
            prompt:
              user_template: "Answer {prompt}"
        edges: []
        """,
    )

    metadata_report = inspect_agent_package_capabilities(package_directory=package_dir)
    metadata_items = {item.id: item for item in metadata_report.items}
    assert (
        metadata_items["metadata.rag_pipeline"].state == CapabilityState.METADATA_ONLY
    )
    assert metadata_items["metadata.rag_pipeline"].details == {
        "orchestration_mode": "hybrid_retrieval",
        "retrieval_mode": "hybrid",
        "required_retrievers": 2,
        "declared_retrievers": 3,
        "provenance_required": True,
        "context_assembly_target": "prepare_model_input",
        "context_max_tokens": 4096,
        "required_evidence_field_count": 3,
        "degraded_states": ("partial_results", "stale_but_allowed"),
        "stale_state": "stale_but_allowed",
        "permission_filtering": "required",
    }
    assert (
        "required_evidence_fields"
        not in metadata_items["metadata.rag_pipeline"].details
    )
    assert (
        metadata_items["rag.retriever.keyword"].state
        == CapabilityState.MISSING_COLLABORATOR
    )
    assert (
        metadata_items["rag.retriever.graph_optional"].state
        == CapabilityState.METADATA_ONLY
    )

    invoked = False

    def fail_if_invoked(_args):
        nonlocal invoked
        invoked = True
        raise AssertionError("capability inspection must not invoke retrievers")

    registry = InMemoryToolRegistry(
        [
            RegisteredTool(
                ToolDefinition.from_mapping({"id": "keyword_search"}),
                fail_if_invoked,
            ),
            RegisteredTool(
                ToolDefinition.from_mapping({"id": "semantic_search"}),
                fail_if_invoked,
            ),
        ]
    )

    live_report = inspect_agent_package_capabilities(
        package_directory=package_dir,
        tool_registry=registry,
    )
    live_items = {item.id: item for item in live_report.items}

    assert invoked is False
    assert live_items["rag.retriever.keyword"].state == CapabilityState.LIVE
    assert live_items["rag.retriever.semantic"].state == CapabilityState.LIVE
    assert (
        live_items["rag.retriever.graph_optional"].state
        == CapabilityState.METADATA_ONLY
    )
    assert live_items["rag.retriever.keyword"].details == {
        "retriever_id": "keyword",
        "tool_id": "keyword_search",
        "mode": "lexical_keyword",
        "required": True,
    }


def test_inspect_agent_package_capabilities_reports_pre_turn_compaction(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner import CapabilityState, inspect_agent_package_capabilities

    package_dir = write_agent_package(
        tmp_path,
        """
        format_version: 1
        package_type: dynamic_agent_design
        package_id: context-compaction-capability-agent
        entrypoint: answer
        packaging:
          mode: hybrid_bundle
        runtime:
          execution_policy:
            model: gpt-test
            prepare_model_input:
              context_compaction:
                auto:
                  enabled: true
                  implementation: injected
                  trigger: token_threshold
                  scope: current_run
        nodes:
          - id: answer
            kind: llm_step
            prompt:
              user_template: "Answer {prompt}"
        edges: []
        """,
    )

    report = inspect_agent_package_capabilities(package_directory=package_dir)

    item = next(
        item
        for item in report.items
        if item.id == "metadata.context.pre_turn_compaction"
    )
    assert item.state is CapabilityState.METADATA_ONLY
    assert item.owner == "context-management-prepare-stage"
    assert item.details == {
        "phase": "pre_turn",
        "implementation": "injected",
        "trigger": "token_threshold",
        "scope": "current_run",
    }


def test_provider_context_compaction_capability_reports_collaborator_state(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner import CapabilityState, inspect_agent_package_capabilities

    package_dir = write_agent_package(
        tmp_path,
        """
        format_version: 1
        package_type: dynamic_agent_design
        package_id: provider-context-compaction-capability-agent
        entrypoint: answer
        packaging:
          mode: hybrid_bundle
        runtime:
          execution_policy:
            model: gpt-test
            prepare_model_input:
              context_compaction:
                auto:
                  enabled: true
                  implementation: provider
                  strategy: provider_remote
                  remote:
                    provider_capability: responses_compact
        nodes:
          - id: answer
            kind: llm_step
            prompt:
              user_template: "Answer {prompt}"
        edges: []
        """,
    )

    class FakeProviderCompactor:
        capabilities = {"responses_compact": True}

    missing = inspect_agent_package_capabilities(package_directory=package_dir)
    live = inspect_agent_package_capabilities(
        package_directory=package_dir,
        provider_context_compactor=FakeProviderCompactor(),
    )

    missing_item = next(
        item
        for item in missing.items
        if item.id == "runtime.context.provider_compaction"
    )
    live_item = next(
        item for item in live.items if item.id == "runtime.context.provider_compaction"
    )
    assert missing_item.state is CapabilityState.MISSING_COLLABORATOR
    assert live_item.state is CapabilityState.LIVE


def test_inspect_agent_package_capabilities_reports_new_window_reset(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner import CapabilityState, inspect_agent_package_capabilities

    package_dir = write_agent_package(
        tmp_path,
        """
        format_version: 1
        package_type: dynamic_agent_design
        package_id: new-window-reset-capability-agent
        entrypoint: answer
        packaging:
          mode: hybrid_bundle
        runtime:
          execution_policy:
            model: gpt-test
            prepare_model_input:
              context_compaction:
                reset_behavior: new_window
        nodes:
          - id: answer
            kind: llm_step
            prompt:
              user_template: "Answer {prompt}"
        edges: []
        """,
    )

    report = inspect_agent_package_capabilities(package_directory=package_dir)

    item = next(
        item for item in report.items if item.id == "metadata.context.new_window_reset"
    )
    assert item.state is CapabilityState.METADATA_ONLY
    assert item.owner == "context-management-prepare-stage"
    assert item.details == {"reset_behavior": "new_window"}


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


def test_inspect_agent_package_capabilities_reports_input_guardrail_coverage(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner import (
        CapabilityState,
        GuardrailResult,
        InMemoryGuardrailRegistry,
        inspect_agent_package_capabilities,
    )

    package_dir = write_agent_package(
        tmp_path,
        """
        format_version: 1
        package_type: dynamic_agent_design
        package_id: guardrail-capability-agent
        entrypoint: answer
        packaging:
          mode: hybrid_bundle
        extensions:
          guardrails:
            declarations:
              - id: no_secrets
                phase: input
                behavior_on_tripwire: abort
        nodes:
          - id: answer
            kind: llm_step
            prompt:
              user_template: "Answer {prompt}"
        edges: []
        """,
    )

    missing_report = inspect_agent_package_capabilities(package_directory=package_dir)
    missing_items = {item.id: item for item in missing_report.items}
    assert missing_items["metadata.guardrails"].state == CapabilityState.METADATA_ONLY
    assert (
        missing_items["guardrail.input.no_secrets"].state
        == CapabilityState.MISSING_COLLABORATOR
    )

    registry = InMemoryGuardrailRegistry(
        {"no_secrets": lambda _subject: GuardrailResult(guardrail_id="no_secrets")}
    )
    live_report = inspect_agent_package_capabilities(
        package_directory=package_dir,
        guardrail_registry=registry,
    )
    live_items = {item.id: item for item in live_report.items}

    assert live_items["guardrail.input.no_secrets"].state == CapabilityState.LIVE


def test_memory_capability_reports_metadata_and_missing_required_retriever():
    from dynamic_agent_runner import inspect_agent_workflow_capabilities

    report = inspect_agent_workflow_capabilities(
        runtime_manifest={
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "memory-capability",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "metadata": {
                "patterns_present": ["memory_retrieval"],
                "memory_pipeline": {
                    "retrieval_tiers": {
                        "balanced": {"retriever_tool_id": "memory_search"}
                    }
                },
            },
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "{prompt}"},
                }
            ],
            "edges": [],
        }
    )
    items = {item.id: item for item in report.items}
    assert items["metadata.memory_pipeline"].state.value == "metadata_only"
    assert items["memory.retriever.balanced"].state.value == "missing_collaborator"
