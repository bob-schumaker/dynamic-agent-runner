"""Tests for loading generated dynamic-agent runtime artifacts."""

from __future__ import annotations

from pathlib import Path

import pytest

from dynamic_agent_runner import load_agent_workflow
from dynamic_agent_runner.artifacts import (
    compile_agent_package,
    compile_loaded_workflow,
    load_agent_package,
    load_runtime_behavior_overrides,
    load_runtime_manifest,
    load_tool_index,
)
from dynamic_agent_runner.errors import ArtifactLoadError
from dynamic_agent_runner.models import PRIMITIVE_NODE_KINDS, SUPPORTED_AGENT_PATTERNS


RUNTIME_YAML = """
format_version: 1
package_type: dynamic_agent_design
package_id: metadata-rich-agent
name: Metadata Rich Agent
entrypoint: analyze_request
mermaid_diagram: agent-graph.mmd
packaging:
  mode: hybrid_bundle
runtime:
  execution_policy:
    autonomy_level: assistive
  state:
    artifacts:
      - id: evidence_bundle
metadata:
  patterns_present:
    - multi-agent-collaboration
    - memory-augmented-agent
  participant_groups:
    - id: review_panel
      name: Review panel
  modes:
    - id: quick_review
  phases:
    - id: fanout
      phase_kind: parallel_fanout
  roles:
    - id: architect
      label: Architect
extensions:
  optional_demo:
    required: false
    config:
      note: preserved
skills:
  - id: agent-development
    source_type: repo_skill
tools:
  - id: retrieve_memory
    label: Retrieve memory
    adapter: runtime.retrieve_memory
    side_effect: read
    approval_required: no
nodes:
  - id: analyze_request
    kind: llm_step
    label: Analyze request
    prompt:
      user_template: Analyze {prompt}
    available_tools:
      - retrieve_memory
  - id: retrieve_context
    kind: tool_use_step
    tool_id: retrieve_memory
  - id: route_result
    kind: decision_step
    decision_subtype: llm_route
edges:
  - source: analyze_request
    target: retrieve_context
    edge_kind: sequential
  - source: retrieve_context
    target: route_result
    edge_kind: sequential
output_contracts:
  - id: final_answer
    type: object
validation:
  required_checks:
    - node_ids_unique
"""

TOOL_INDEX_YAML = """
format_version: 1
index_type: agent_runtime_tool_index
index_id: example-tool-index
name: Example Tool Index
usage:
  default_import_mode: referenced_by_manifest
tools:
  - id: retrieve_memory
    label: Retrieve memory
    adapter: runtime.retrieve_memory
    side_effect: read
    approval_required: no
skills:
  - id: agent-development
    source_type: repo_skill
"""

AGENT_DESIGN = """
# Metadata Rich Agent

Runtime manifest: `agent-runtime.yaml`
Mermaid graph: `agent-graph.mmd`
"""

MERMAID_GRAPH = """flowchart TD
    analyze_request[Analyze request]
    retrieve_context[Retrieve context]
    route_result{Route result}
    analyze_request --> retrieve_context
    retrieve_context --> route_result
"""


def test_load_runtime_manifest_from_raw_yaml_preserves_pattern_metadata() -> None:
    """Raw YAML loading preserves supported patterns and structural metadata."""

    manifest = load_runtime_manifest(RUNTIME_YAML)

    assert manifest.format_version == 1
    assert manifest.package_type == "dynamic_agent_design"
    assert manifest.package_id == "metadata-rich-agent"
    assert manifest.patterns_present == (
        "multi-agent-collaboration",
        "memory-augmented-agent",
    )
    assert "multi-agent-collaboration" in SUPPORTED_AGENT_PATTERNS
    assert PRIMITIVE_NODE_KINDS == ("llm_step", "tool_use_step", "decision_step")
    assert manifest.participant_groups[0].id == "review_panel"
    assert manifest.modes[0].id == "quick_review"
    assert manifest.phases[0].id == "fanout"
    assert manifest.roles[0].id == "architect"
    assert manifest.nodes[0].available_tools == ("retrieve_memory",)
    assert manifest.nodes[0].skill_refs == ()
    assert manifest.nodes[1].tool_id == "retrieve_memory"
    assert manifest.nodes[2].decision_subtype == "llm_route"
    assert manifest.edges[0].edge_kind == "sequential"
    assert manifest.runtime["execution_policy"] == {"autonomy_level": "assistive"}
    assert manifest.metadata["patterns_present"] == [
        "multi-agent-collaboration",
        "memory-augmented-agent",
    ]
    assert manifest.extensions["optional_demo"]["config"] == {"note": "preserved"}
    assert manifest.output_contracts["final_answer"] == {
        "id": "final_answer",
        "type": "object",
    }
    assert manifest.handoffs == ()


def test_load_runtime_manifest_preserves_handoffs_and_agent_as_tool_metadata() -> None:
    """Grouped handoff metadata and node agent-as-tool metadata are preserved."""

    manifest = load_runtime_manifest(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "handoff-agent-tool-metadata",
            "entrypoint": "delegate",
            "packaging": {"mode": "hybrid_bundle"},
            "metadata": {
                "handoffs": [
                    {
                        "id": "handoff_to_reviewer",
                        "target": "reviewer",
                        "on_handoff": "switch_active_profile",
                        "input_filter": "latest_user_request",
                        "nested_history": "filtered",
                        "enabled_when": "needs_review",
                    }
                ]
            },
            "nodes": [
                {
                    "id": "delegate",
                    "kind": "tool_use_step",
                    "tool_id": "reviewer_agent",
                    "agent_as_tool": {
                        "skill_id": "reviewer-skill",
                        "skill_path": "skills/reviewer/SKILL.md",
                        "task_boundary": "review one bounded subtask",
                        "output_mode": "tool_result",
                    },
                }
            ],
            "edges": [],
            "tools": [{"id": "reviewer_agent", "adapter": "runtime.reviewer"}],
        }
    )

    assert len(manifest.handoffs) == 1
    assert manifest.handoffs[0].id == "handoff_to_reviewer"
    assert manifest.handoffs[0].target == "reviewer"
    assert manifest.handoffs[0].on_handoff == "switch_active_profile"
    assert manifest.handoffs[0].input_filter == "latest_user_request"
    assert manifest.handoffs[0].nested_history == "filtered"
    assert manifest.handoffs[0].enabled_when == "needs_review"
    assert manifest.nodes[0].agent_as_tool is not None
    assert manifest.nodes[0].agent_as_tool.skill_id == "reviewer-skill"
    assert manifest.nodes[0].agent_as_tool.skill_path == "skills/reviewer/SKILL.md"
    assert manifest.nodes[0].agent_as_tool.task_boundary == "review one bounded subtask"
    assert manifest.nodes[0].agent_as_tool.output_mode == "tool_result"


def test_load_runtime_manifest_preserves_approval_interruption_metadata() -> None:
    """Approval interruption policy metadata is preserved from execution policy."""

    manifest = load_runtime_manifest(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "approval-interruption-metadata",
            "entrypoint": "request_approval",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "approval_interruption": {
                        "mode": "pause_on_approval",
                        "persist": "external_checkpoint",
                        "resume_from": "approval_decision",
                        "pending_tool_calls_state_key": "pending_tool_calls",
                        "pending_approvals_state_key": "pending_approvals",
                        "interruption_state_key": "interruption_state",
                        "resume_token_state_key": "resume_token",
                    },
                }
            },
            "nodes": [
                {
                    "id": "request_approval",
                    "kind": "tool_use_step",
                    "tool_id": "write_repo",
                }
            ],
            "edges": [],
            "tools": [{"id": "write_repo", "adapter": "runtime.write_repo"}],
        }
    )

    assert manifest.approval_interruption_policy is not None
    assert manifest.approval_interruption_policy.mode == "pause_on_approval"
    assert manifest.approval_interruption_policy.persist == "external_checkpoint"
    assert manifest.approval_interruption_policy.resume_from == "approval_decision"
    assert (
        manifest.approval_interruption_policy.pending_tool_calls_state_key
        == "pending_tool_calls"
    )
    assert (
        manifest.approval_interruption_policy.pending_approvals_state_key
        == "pending_approvals"
    )
    assert (
        manifest.approval_interruption_policy.interruption_state_key
        == "interruption_state"
    )
    assert (
        manifest.approval_interruption_policy.resume_token_state_key == "resume_token"
    )


def test_load_runtime_manifest_preserves_sandbox_runtime_metadata() -> None:
    """Sandbox runtime policy metadata is preserved from execution policy."""

    manifest = load_runtime_manifest(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "sandbox-runtime-metadata",
            "entrypoint": "run_write_tool",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "sandbox_runtime": {
                        "mode": "per_run_workspace",
                        "filesystem": "workspace_write",
                        "persist_workspace": "named_session",
                        "command_policy": "allow_list",
                        "writable_root_state_key": "writable_root",
                        "working_directory_state_key": "working_directory",
                    },
                }
            },
            "nodes": [
                {
                    "id": "run_write_tool",
                    "kind": "tool_use_step",
                    "tool_id": "write_repo",
                }
            ],
            "edges": [],
            "tools": [{"id": "write_repo", "adapter": "runtime.write_repo"}],
        }
    )

    assert manifest.sandbox_runtime_policy is not None
    assert manifest.sandbox_runtime_policy.mode == "per_run_workspace"
    assert manifest.sandbox_runtime_policy.filesystem == "workspace_write"
    assert manifest.sandbox_runtime_policy.persist_workspace == "named_session"
    assert manifest.sandbox_runtime_policy.command_policy == "allow_list"
    assert manifest.sandbox_runtime_policy.writable_root_state_key == "writable_root"
    assert (
        manifest.sandbox_runtime_policy.working_directory_state_key
        == "working_directory"
    )


def test_load_runtime_manifest_preserves_async_session_metadata() -> None:
    """Async session policy metadata is preserved from execution policy."""

    manifest = load_runtime_manifest(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "async-session-metadata",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "async_session": {
                        "mode": "create_or_resume",
                        "persist": "external_checkpoint",
                        "history": "summary",
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

    assert manifest.async_session_policy is not None
    assert manifest.async_session_policy.mode == "create_or_resume"
    assert manifest.async_session_policy.persist == "external_checkpoint"
    assert manifest.async_session_policy.history == "summary"
    assert manifest.async_session_policy.session_id_state_key == "session_id"
    assert (
        manifest.async_session_policy.session_messages_state_key == "session_messages"
    )


def test_load_runtime_manifest_preserves_node_skill_refs() -> None:
    """LLM node skill references are preserved for behavior overrides."""

    manifest = load_runtime_manifest(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "skill-ref-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Answer {prompt}"},
                    "skill_refs": ["concise-writer", "policy-reviewer"],
                }
            ],
            "edges": [],
        }
    )

    assert manifest.nodes[0].skill_refs == ("concise-writer", "policy-reviewer")


def test_load_runtime_behavior_overrides_from_mapping() -> None:
    """Behavior override artifacts preserve skill and node operations."""

    overrides = load_runtime_behavior_overrides(
        {
            "format_version": 1,
            "override_type": "dynamic_agent_runtime_overrides",
            "skills": {
                "added": [
                    {
                        "id": "concise-writer",
                        "prompt_role": "developer",
                        "instructions": "Write briefly.",
                    }
                ]
            },
            "nodes": {
                "answer": {
                    "prompt": {
                        "prepend": {"system": "Before. "},
                        "append": {"developer": " After."},
                        "replace": {"user_template": "Override {prompt}"},
                    },
                    "skill_refs": {"add": ["concise-writer"]},
                }
            },
        }
    )

    assert overrides is not None
    assert overrides.added_skills[0].id == "concise-writer"
    assert overrides.node_overrides["answer"].prompt is not None
    assert overrides.node_overrides["answer"].prompt.replace == {
        "user_template": "Override {prompt}"
    }
    assert overrides.node_overrides["answer"].skill_refs is not None
    assert overrides.node_overrides["answer"].skill_refs.add == ("concise-writer",)


def test_load_runtime_manifest_from_parsed_object() -> None:
    """Already-parsed manifest objects are accepted without text parsing."""

    manifest = load_runtime_manifest(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "parsed-agent",
            "entrypoint": "start",
            "packaging": {"mode": "hybrid_bundle"},
            "metadata": {"patterns_present": ["basic-reasoning-agent"]},
            "nodes": [{"id": "start", "kind": "llm_step"}],
            "edges": [],
        }
    )

    assert manifest.package_id == "parsed-agent"
    assert manifest.patterns_present == ("basic-reasoning-agent",)
    assert manifest.nodes[0].id == "start"


def test_load_runtime_manifest_rejects_root_legacy_optional_fields() -> None:
    """Pre-customer flat optional root fields are no longer compatibility paths."""

    manifest = load_runtime_manifest(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "legacy-agent",
            "entrypoint": "start",
            "packaging": {"mode": "hybrid_bundle"},
            "execution_policy": {"model": "gpt-test"},
            "nodes": [{"id": "start", "kind": "llm_step"}],
            "edges": [],
        }
    )

    assert manifest.legacy_root_fields == ("execution_policy",)


def test_load_agent_workflow_resolves_mermaid_reference(tmp_path: Path) -> None:
    """Runtime YAML paths resolve referenced Mermaid graphs beside the manifest."""

    runtime_path = tmp_path / "agent-runtime.yaml"
    graph_path = tmp_path / "agent-graph.mmd"
    runtime_path.write_text(RUNTIME_YAML, encoding="utf-8")
    graph_path.write_text(MERMAID_GRAPH, encoding="utf-8")

    workflow = load_agent_workflow(runtime_manifest=runtime_path)

    assert workflow.runtime_manifest.package_id == "metadata-rich-agent"
    assert workflow.mermaid_graph == MERMAID_GRAPH


def test_load_agent_package_loads_canonical_sibling_artifacts(
    tmp_path: Path,
) -> None:
    """Package-directory loading uses fixed sibling artifact names."""

    package_dir = tmp_path / "metadata-rich-agent"
    package_dir.mkdir()
    (package_dir / "agent-runtime.yaml").write_text(RUNTIME_YAML, encoding="utf-8")
    (package_dir / "agent-graph.mmd").write_text(MERMAID_GRAPH, encoding="utf-8")
    (package_dir / "agent-design.md").write_text(AGENT_DESIGN, encoding="utf-8")

    workflow = load_agent_package(package_dir)

    assert workflow.package_root == str(package_dir)
    assert workflow.skill_bundle_root is None
    assert workflow.runtime_manifest.package_id == "metadata-rich-agent"
    assert workflow.mermaid_graph == MERMAID_GRAPH
    assert workflow.agent_design is not None
    assert workflow.agent_design.references_runtime_manifest is True
    assert workflow.agent_design.references_mermaid_graph is True


def test_compile_loaded_workflow_layers_overrides_without_mutating_base() -> None:
    """Compilation keeps the loaded base immutable while adding final overrides."""

    base_workflow = load_agent_workflow(
        runtime_manifest={
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "compile-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "skills": [{"id": "base-skill", "instructions": "Base skill."}],
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Base {prompt}"},
                    "skill_refs": ["base-skill"],
                }
            ],
            "edges": [],
        }
    )

    compiled = compile_loaded_workflow(
        base_workflow,
        runtime_overrides={
            "format_version": 1,
            "override_type": "dynamic_agent_runtime_overrides",
            "skills": {
                "added": [
                    {
                        "id": "added-skill",
                        "prompt_role": "developer",
                        "instructions": "Added skill.",
                    }
                ]
            },
            "nodes": {
                "answer": {
                    "prompt": {
                        "replace": {"user_template": "Compiled {prompt}"},
                    },
                    "skill_refs": {"add": ["added-skill"]},
                }
            },
        },
    )

    assert compiled.base_workflow is base_workflow
    assert compiled.runtime_manifest is base_workflow.runtime_manifest
    assert base_workflow.runtime_overrides is None
    assert compiled.runtime_overrides is not None
    assert compiled.runtime_overrides.node_overrides["answer"].prompt is not None
    assert compiled.runtime_overrides.node_overrides["answer"].prompt.replace == {
        "user_template": "Compiled {prompt}"
    }
    assert compiled.runtime_overrides.added_skills[0].id == "added-skill"


def test_compile_agent_package_preserves_base_package_and_adds_overrides(
    tmp_path: Path,
) -> None:
    """Package compilation returns compiled workflow metadata plus caller overrides."""

    package_dir = tmp_path / "compiled-package"
    package_dir.mkdir()
    (package_dir / "agent-runtime.yaml").write_text(
        """
format_version: 1
package_type: dynamic_agent_design
package_id: compiled-package
entrypoint: answer
packaging:
  mode: hybrid_bundle
skills:
  - id: base-skill
    instructions: Base skill.
nodes:
  - id: answer
    kind: llm_step
    prompt:
      user_template: Base {prompt}
    skill_refs:
      - base-skill
edges: []
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (package_dir / "agent-graph.mmd").write_text(MERMAID_GRAPH, encoding="utf-8")
    (package_dir / "agent-design.md").write_text(AGENT_DESIGN, encoding="utf-8")

    compiled = compile_agent_package(
        package_dir,
        runtime_overrides={
            "format_version": 1,
            "override_type": "dynamic_agent_runtime_overrides",
            "skills": {
                "added": [
                    {
                        "id": "added-skill",
                        "prompt_role": "developer",
                        "instructions": "Added skill.",
                    }
                ]
            },
        },
    )

    assert compiled.package_root == str(package_dir)
    assert compiled.base_workflow.package_root == str(package_dir)
    assert compiled.runtime_overrides is not None
    assert compiled.runtime_overrides.added_skills[0].id == "added-skill"


def test_load_agent_package_requires_runtime_manifest(tmp_path: Path) -> None:
    """Package-directory loading fails closed when agent-runtime.yaml is missing."""

    package_dir = tmp_path / "missing-runtime"
    package_dir.mkdir()

    with pytest.raises(ArtifactLoadError, match="missing required agent-runtime.yaml"):
        load_agent_package(package_dir)


@pytest.mark.parametrize(
    ("missing_name", "expected_message"),
    [
        ("agent-design.md", "missing required agent-design.md"),
        ("agent-graph.mmd", "missing required agent-graph.mmd"),
    ],
)
def test_load_agent_package_requires_canonical_sibling_artifacts(
    tmp_path: Path,
    missing_name: str,
    expected_message: str,
) -> None:
    """Package-directory loading fails closed when canonical sibling files are missing."""

    package_dir = tmp_path / "missing-sibling"
    package_dir.mkdir()
    (package_dir / "agent-runtime.yaml").write_text(RUNTIME_YAML, encoding="utf-8")
    if missing_name != "agent-design.md":
        (package_dir / "agent-design.md").write_text(AGENT_DESIGN, encoding="utf-8")
    if missing_name != "agent-graph.mmd":
        (package_dir / "agent-graph.mmd").write_text(MERMAID_GRAPH, encoding="utf-8")

    with pytest.raises(ArtifactLoadError, match=expected_message):
        load_agent_package(package_dir)


def test_load_agent_workflow_accepts_all_artifact_inputs() -> None:
    """Workflow loading accepts runtime, graph, design, and tool-index inputs."""

    workflow = load_agent_workflow(
        runtime_manifest=RUNTIME_YAML,
        mermaid_graph=MERMAID_GRAPH,
        agent_design=AGENT_DESIGN,
        tool_index=TOOL_INDEX_YAML,
    )

    assert workflow.runtime_manifest.entrypoint == "analyze_request"
    assert workflow.mermaid_graph == MERMAID_GRAPH
    assert workflow.agent_design is not None
    assert workflow.agent_design.references_runtime_manifest is True
    assert workflow.agent_design.references_mermaid_graph is True
    assert workflow.tool_index is not None
    assert workflow.tool_index.index_type == "agent_runtime_tool_index"
    assert workflow.tool_index.tools[0].id == "retrieve_memory"


def test_load_tool_index_from_parsed_object() -> None:
    """Parsed tool-index objects preserve tool and skill metadata."""

    tool_index = load_tool_index(
        {
            "format_version": 1,
            "index_type": "agent_runtime_tool_index",
            "index_id": "parsed-tools",
            "tools": [{"id": "search_repo", "adapter": "runtime.search_files"}],
            "skills": [{"id": "agent-development", "source_type": "repo_skill"}],
        }
    )

    assert tool_index is not None
    assert tool_index.index_id == "parsed-tools"
    assert tool_index.tools[0].adapter == "runtime.search_files"
    assert tool_index.skills[0].id == "agent-development"


def test_load_runtime_manifest_rejects_malformed_yaml() -> None:
    """Malformed YAML raises an artifact load error."""

    with pytest.raises(ArtifactLoadError, match="Could not parse runtime manifest"):
        load_runtime_manifest("nodes: [")


def test_load_runtime_manifest_requires_yaml_mapping() -> None:
    """YAML inputs must parse to mappings for artifact loading."""

    with pytest.raises(ArtifactLoadError, match="Expected runtime manifest"):
        load_runtime_manifest("- not\n- a\n- mapping\n")


def test_missing_referenced_mermaid_graph_raises(tmp_path: Path) -> None:
    """A missing graph referenced by a path-based runtime manifest fails clearly."""

    runtime_path = tmp_path / "agent-runtime.yaml"
    runtime_path.write_text(RUNTIME_YAML, encoding="utf-8")

    with pytest.raises(ArtifactLoadError, match="Mermaid graph not found"):
        load_agent_workflow(runtime_manifest=runtime_path)
