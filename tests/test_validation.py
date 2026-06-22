"""Tests for dynamic-agent runtime artifact validation."""

from __future__ import annotations

from copy import deepcopy

import pytest

from dynamic_agent_runner.artifacts import (
    load_agent_package,
    load_runtime_behavior_overrides,
    load_runtime_manifest,
    load_tool_index,
)
from dynamic_agent_runner.errors import WorkflowValidationError
from dynamic_agent_runner.models import LoadedAgentWorkflow
from dynamic_agent_runner.skill_sources import (
    RejectedSkillSource,
    ResolvedSkillSource,
    SkillSourceResolutionPolicy,
)
from dynamic_agent_runner.validation import (
    validate_agent_workflow,
    validate_runtime_manifest,
    validate_tool_index,
)


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


def valid_manifest_data() -> dict[str, object]:
    """Return a minimal valid manifest mapping for validation tests."""

    return {
        "format_version": 1,
        "package_type": "dynamic_agent_design",
        "package_id": "valid-agent",
        "entrypoint": "analyze_request",
        "packaging": {"mode": "hybrid_bundle"},
        "runtime": {"execution_policy": {"model": "gpt-test"}},
        "nodes": [
            {
                "id": "analyze_request",
                "kind": "llm_step",
                "prompt": {"user_template": "Analyze {prompt}"},
            },
            {"id": "lookup_context", "kind": "tool_use_step", "tool_id": "search_repo"},
            {
                "id": "route_result",
                "kind": "decision_step",
                "decision_subtype": "llm_route",
            },
        ],
        "edges": [
            {
                "source": "analyze_request",
                "target": "lookup_context",
                "edge_kind": "sequential",
            },
            {
                "source": "lookup_context",
                "target": "route_result",
                "edge_kind": "sequential",
            },
        ],
        "tools": [{"id": "search_repo", "adapter": "runtime.search_files"}],
    }


def validate_mapping(mapping: dict[str, object]) -> None:
    """Load and validate a manifest mapping."""

    validate_runtime_manifest(load_runtime_manifest(mapping))


def test_valid_runtime_manifest_passes_validation() -> None:
    """A minimally valid manifest passes the Slice 3 validation engine."""

    validate_mapping(valid_manifest_data())


def test_tool_descriptor_budget_policy_accepts_disabled_value() -> None:
    data = valid_manifest_data()
    data["runtime"] = {
        "execution_policy": {
            "model": "gpt-test",
            "tool_descriptor_budget": {"enabled": False},
        }
    }

    validate_mapping(data)


@pytest.mark.parametrize(
    ("policy", "message"),
    [
        (True, "runtime.execution_policy.tool_descriptor_budget must be a mapping"),
        (
            {"enabled": True, "max_tokens": 0},
            "runtime.execution_policy.tool_descriptor_budget.max_tokens "
            "must be a positive integer",
        ),
        (
            {"enabled": True, "max_tools": 0},
            "runtime.execution_policy.tool_descriptor_budget.max_tools "
            "must be a positive integer",
        ),
        (
            {"enabled": True, "strategy": "semantic_embedding"},
            "runtime.execution_policy.tool_descriptor_budget.strategy must be one of",
        ),
    ],
)
def test_tool_descriptor_budget_policy_validation_errors(
    policy: object,
    message: str,
) -> None:
    data = valid_manifest_data()
    data["runtime"] = {
        "execution_policy": {
            "model": "gpt-test",
            "tool_descriptor_budget": policy,
        }
    }

    with pytest.raises(WorkflowValidationError, match=message):
        validate_mapping(data)


def test_tool_descriptor_budget_node_override_accepts_llm_step_mapping() -> None:
    data = valid_manifest_data()
    nodes = list(data["nodes"])  # type: ignore[arg-type]
    llm_node = dict(nodes[0])
    llm_node["tool_descriptor_budget"] = {
        "max_tokens": 800,
        "required_tools": ["search_repo"],
    }
    nodes[0] = llm_node
    data["nodes"] = nodes

    validate_mapping(data)


def test_tool_descriptor_budget_node_override_rejected_on_non_llm_step() -> None:
    data = valid_manifest_data()
    nodes = list(data["nodes"])  # type: ignore[arg-type]
    tool_node = dict(nodes[1])
    tool_node["tool_descriptor_budget"] = {"max_tokens": 800}
    nodes[1] = tool_node
    data["nodes"] = nodes

    with pytest.raises(
        WorkflowValidationError,
        match="nodes\\[1\\].tool_descriptor_budget is only allowed on llm_step nodes",
    ):
        validate_mapping(data)


def test_valid_workflow_with_external_tool_index_passes() -> None:
    """Workflow validation includes optional external tool-index validation."""

    manifest_data = valid_manifest_data()
    manifest_data["tools"] = []
    manifest_data["nodes"] = [
        {"id": "analyze_request", "kind": "llm_step", "prompt_source": "inline"},
        {
            "id": "lookup_context",
            "kind": "tool_use_step",
            "tool_id": "retrieve_memory",
        },
    ]
    manifest_data["edges"] = [
        {
            "source": "analyze_request",
            "target": "lookup_context",
            "edge_kind": "sequential",
        }
    ]

    workflow = LoadedAgentWorkflow(
        runtime_manifest=load_runtime_manifest(manifest_data),
        tool_index=load_tool_index(TOOL_INDEX_YAML),
    )

    validate_agent_workflow(workflow)


def test_package_workflow_with_bundled_skill_and_support_files_passes(
    tmp_path,
) -> None:
    """Package validation accepts bundled skill and support files under skill-bundle/."""

    package_dir = tmp_path / "bundled-skill-package"
    package_dir.mkdir()
    skill_bundle_dir = package_dir / "skill-bundle"
    (skill_bundle_dir / "skills" / "demo-skill").mkdir(parents=True)
    (skill_bundle_dir / "assets").mkdir(parents=True)
    (skill_bundle_dir / "skills" / "demo-skill" / "SKILL.md").write_text(
        "# Demo Skill\n",
        encoding="utf-8",
    )
    (skill_bundle_dir / "assets" / "guide.md").write_text(
        "guide\n",
        encoding="utf-8",
    )
    (package_dir / "agent-design.md").write_text(
        "Runtime manifest: `agent-runtime.yaml`\nMermaid graph: `agent-graph.mmd`\n",
        encoding="utf-8",
    )
    (package_dir / "agent-graph.mmd").write_text("flowchart TD\n", encoding="utf-8")
    (package_dir / "agent-runtime.yaml").write_text(
        """
format_version: 1
package_type: dynamic_agent_design
package_id: bundled-skill-package
entrypoint: analyze_request
packaging:
  mode: hybrid_bundle
  skill_bundle_dir: skill-bundle
skills:
  - id: demo-skill
    bundled_path: skills/demo-skill/SKILL.md
    support_files:
      - id: guide
        bundled_path: assets/guide.md
nodes:
  - id: analyze_request
    kind: llm_step
    prompt:
      user_template: Analyze {prompt}
edges: []
""".strip()
        + "\n",
        encoding="utf-8",
    )

    workflow = load_agent_package(package_dir)

    validate_agent_workflow(workflow)


def test_package_workflow_fails_for_missing_bundled_skill_file(tmp_path) -> None:
    """Package validation fails clearly when a bundled skill file is missing."""

    package_dir = tmp_path / "missing-bundled-skill"
    package_dir.mkdir()
    (package_dir / "skill-bundle").mkdir()
    (package_dir / "agent-design.md").write_text(
        "Runtime manifest: `agent-runtime.yaml`\nMermaid graph: `agent-graph.mmd`\n",
        encoding="utf-8",
    )
    (package_dir / "agent-graph.mmd").write_text("flowchart TD\n", encoding="utf-8")
    (package_dir / "agent-runtime.yaml").write_text(
        """
format_version: 1
package_type: dynamic_agent_design
package_id: missing-bundled-skill
entrypoint: analyze_request
packaging:
  mode: hybrid_bundle
  skill_bundle_dir: skill-bundle
skills:
  - id: demo-skill
    bundled_path: skills/demo-skill/SKILL.md
nodes:
  - id: analyze_request
    kind: llm_step
    prompt:
      user_template: Analyze {prompt}
edges: []
""".strip()
        + "\n",
        encoding="utf-8",
    )

    workflow = load_agent_package(package_dir)

    with pytest.raises(WorkflowValidationError, match="bundled_path not found"):
        validate_agent_workflow(workflow)


def test_package_workflow_fails_for_missing_bundled_support_file(tmp_path) -> None:
    """Package validation fails clearly when a bundled support file is missing."""

    package_dir = tmp_path / "missing-bundled-support"
    package_dir.mkdir()
    skill_dir = package_dir / "skill-bundle" / "skills" / "demo-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
    (package_dir / "agent-design.md").write_text(
        "Runtime manifest: `agent-runtime.yaml`\nMermaid graph: `agent-graph.mmd`\n",
        encoding="utf-8",
    )
    (package_dir / "agent-graph.mmd").write_text("flowchart TD\n", encoding="utf-8")
    (package_dir / "agent-runtime.yaml").write_text(
        """
format_version: 1
package_type: dynamic_agent_design
package_id: missing-bundled-support
entrypoint: analyze_request
packaging:
  mode: hybrid_bundle
  skill_bundle_dir: skill-bundle
skills:
  - id: demo-skill
    bundled_path: skills/demo-skill/SKILL.md
    support_files:
      - id: guide
        bundled_path: assets/guide.md
nodes:
  - id: analyze_request
    kind: llm_step
    prompt:
      user_template: Analyze {prompt}
edges: []
""".strip()
        + "\n",
        encoding="utf-8",
    )

    workflow = load_agent_package(package_dir)

    with pytest.raises(
        WorkflowValidationError, match="support file 'guide'.*bundled_path not found"
    ):
        validate_agent_workflow(workflow)


def test_missing_required_runtime_field_fails() -> None:
    """Required runtime manifest fields are validated before execution."""

    data = valid_manifest_data()
    del data["entrypoint"]

    with pytest.raises(WorkflowValidationError, match="missing required field"):
        validate_mapping(data)


def test_unsupported_runtime_enums_fail() -> None:
    """Unsupported format, package, node, decision, and edge values fail closed."""

    data = valid_manifest_data()
    data["format_version"] = 2
    data["package_type"] = "other"
    data["nodes"] = [
        {"id": "bad_node", "kind": "memory_step"},
        {
            "id": "bad_decision",
            "kind": "decision_step",
            "decision_subtype": "coin_flip",
        },
    ]
    data["entrypoint"] = "bad_node"
    data["edges"] = [
        {"source": "bad_node", "target": "bad_decision", "edge_kind": "teleport"}
    ]

    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_mapping(data)

    message = str(exc_info.value)
    assert "unsupported format_version" in message
    assert "unsupported package_type" in message
    assert "unsupported kind" in message
    assert "unsupported decision_subtype" in message
    assert "unsupported edge_kind" in message


def test_sandbox_runtime_policy_fails_closed_for_bad_values() -> None:
    """Sandbox runtime metadata rejects unsupported enums and bad state keys."""

    data = valid_manifest_data()
    data["runtime"] = {
        "execution_policy": {
            "model": "gpt-test",
            "sandbox_runtime": {
                "mode": "always_on",
                "filesystem": "mutable",
                "persist_workspace": "forever",
                "command_policy": "all_commands",
                "writable_root_state_key": 7,
                "working_directory_state_key": "   ",
            },
        }
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_mapping(data)

    message = str(exc_info.value)
    assert "sandbox_runtime.mode has unsupported value 'always_on'" in message
    assert "sandbox_runtime.filesystem has unsupported value 'mutable'" in message
    assert (
        "sandbox_runtime.persist_workspace has unsupported value 'forever'" in message
    )
    assert (
        "sandbox_runtime.command_policy has unsupported value 'all_commands'" in message
    )
    assert "sandbox_runtime.writable_root_state_key must be a string" in message
    assert "sandbox_runtime.working_directory_state_key must not be blank" in message


def test_sandbox_runtime_policy_requires_state_keys_for_persisted_workspace() -> None:
    """Persisted sandbox workspaces require state keys for resumable location data."""

    data = valid_manifest_data()
    data["runtime"] = {
        "execution_policy": {
            "model": "gpt-test",
            "sandbox_runtime": {
                "mode": "shared_workspace",
                "filesystem": "workspace_write",
                "persist_workspace": "per_run",
                "command_policy": "caller_controlled",
            },
        }
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_mapping(data)

    message = str(exc_info.value)
    assert (
        "sandbox_runtime.writable_root_state_key is required when persist_workspace is 'per_run'"
        in message
    )
    assert (
        "sandbox_runtime.working_directory_state_key is required when persist_workspace is 'per_run'"
        in message
    )


def test_sandbox_runtime_policy_rejects_state_keys_when_persist_workspace_is_none() -> (
    None
):
    """Non-persisted sandbox metadata must not declare persisted workspace keys."""

    data = valid_manifest_data()
    data["runtime"] = {
        "execution_policy": {
            "model": "gpt-test",
            "sandbox_runtime": {
                "mode": "metadata_only",
                "filesystem": "read_only",
                "persist_workspace": "none",
                "command_policy": "forbid",
                "writable_root_state_key": "writable_root",
            },
        }
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_mapping(data)

    assert (
        "state-key fields are only allowed when persist_workspace is not 'none'"
        in str(exc_info.value)
    )


def test_sandbox_runtime_policy_rejects_command_policy_with_read_only_filesystem() -> (
    None
):
    """Command execution metadata must not pair with a read-only filesystem policy."""

    data = valid_manifest_data()
    data["runtime"] = {
        "execution_policy": {
            "model": "gpt-test",
            "sandbox_runtime": {
                "mode": "per_run_workspace",
                "filesystem": "read_only",
                "persist_workspace": "named_session",
                "command_policy": "allow_list",
                "writable_root_state_key": "writable_root",
                "working_directory_state_key": "working_directory",
            },
        }
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_mapping(data)

    assert (
        "sandbox_runtime.filesystem must not be 'read_only' when command_policy is not 'forbid'"
        in str(exc_info.value)
    )


def test_sandbox_runtime_policy_passes_with_supported_metadata() -> None:
    """Supported sandbox runtime metadata passes validation without enabling execution."""

    data = valid_manifest_data()
    data["runtime"] = {
        "execution_policy": {
            "model": "gpt-test",
            "sandbox_runtime": {
                "mode": "per_run_workspace",
                "filesystem": "workspace_write",
                "persist_workspace": "named_session",
                "command_policy": "caller_controlled",
                "writable_root_state_key": "writable_root",
                "working_directory_state_key": "working_directory",
            },
        }
    }

    validate_mapping(data)


def test_duplicate_node_ids_fail() -> None:
    """Node IDs must be unique."""

    data = valid_manifest_data()
    data["nodes"] = [
        {"id": "duplicate", "kind": "llm_step", "prompt_source": "inline"},
        {"id": "duplicate", "kind": "llm_step", "prompt_source": "inline"},
    ]
    data["entrypoint"] = "duplicate"
    data["edges"] = []

    with pytest.raises(WorkflowValidationError, match="duplicate node id"):
        validate_mapping(data)


def test_edge_endpoint_references_fail() -> None:
    """Edges must reference existing node IDs."""

    data = valid_manifest_data()
    data["edges"] = [
        {
            "source": "missing_source",
            "target": "missing_target",
            "edge_kind": "sequential",
        }
    ]

    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_mapping(data)

    message = str(exc_info.value)
    assert "edge source" in message
    assert "edge target" in message


def test_entrypoint_reference_fails() -> None:
    """Entrypoint must reference an existing node."""

    data = valid_manifest_data()
    data["entrypoint"] = "missing"

    with pytest.raises(WorkflowValidationError, match="entrypoint"):
        validate_mapping(data)


def test_tool_use_step_requires_known_tool() -> None:
    """Tool-use nodes must reference manifest or external tool-index metadata."""

    data = valid_manifest_data()
    data["tools"] = []

    with pytest.raises(WorkflowValidationError, match="unknown metadata tool"):
        validate_mapping(data)


def test_tool_metadata_rejects_unknown_exposure() -> None:
    """Tool exposure metadata fails closed for manifests and tool indexes."""

    data = valid_manifest_data()
    data["tools"] = [
        {
            "id": "search_repo",
            "adapter": "runtime.search_files",
            "exposure": "surprise",
        }
    ]

    with pytest.raises(WorkflowValidationError, match="unsupported exposure"):
        validate_mapping(data)

    tool_index = load_tool_index(
        {
            "format_version": 1,
            "index_type": "agent_runtime_tool_index",
            "tools": [{"id": "external_search", "exposure": "surprise"}],
        }
    )
    assert tool_index is not None

    with pytest.raises(WorkflowValidationError, match="unsupported exposure"):
        validate_tool_index(tool_index)


def test_tool_metadata_accepts_supported_portable_tool_type() -> None:
    """Portable tool_type metadata is preserved and validated separately from adapters."""

    data = valid_manifest_data()
    data["tools"] = [
        {
            "id": "search_repo",
            "tool_type": "external_api",
            "adapter": "runtime.search_files",
        }
    ]

    manifest = load_runtime_manifest(data)

    validate_runtime_manifest(manifest)
    assert manifest.tools[0].tool_type is not None
    assert manifest.tools[0].tool_type.value == "external_api"


def test_tool_metadata_rejects_unknown_portable_tool_type() -> None:
    """Unsupported portable tool_type values fail closed for manifests and tool indexes."""

    data = valid_manifest_data()
    data["tools"] = [
        {
            "id": "search_repo",
            "adapter": "runtime.search_files",
            "tool_type": "spreadsheet_macro",
        }
    ]

    with pytest.raises(WorkflowValidationError, match="unsupported tool_type"):
        validate_mapping(data)

    tool_index = load_tool_index(
        {
            "format_version": 1,
            "index_type": "agent_runtime_tool_index",
            "tools": [{"id": "external_search", "tool_type": "spreadsheet_macro"}],
        }
    )
    assert tool_index is not None

    with pytest.raises(WorkflowValidationError, match="unsupported tool_type"):
        validate_tool_index(tool_index)


def test_legacy_root_runtime_fields_fail_validation() -> None:
    """Legacy flat optional root fields fail instead of acting as compatibility."""

    data = valid_manifest_data()
    data["execution_policy"] = {"model": "gpt-test"}
    data["patterns_present"] = ["basic-reasoning-agent"]

    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_mapping(data)

    message = str(exc_info.value)
    assert "legacy root field 'execution_policy'" in message
    assert "legacy root field 'patterns_present'" in message


def test_required_extension_fails_closed() -> None:
    """Unsupported required extension envelopes fail validation."""

    data = valid_manifest_data()
    data["extensions"] = {"future_feature": {"required": True, "config": {}}}

    with pytest.raises(WorkflowValidationError, match="required unsupported extension"):
        validate_mapping(data)


def test_malformed_extension_envelope_fails_validation() -> None:
    """Extension envelopes need a mapping with a boolean required flag."""

    data = valid_manifest_data()
    data["extensions"] = {"bad_extension": {"required": "yes"}}

    with pytest.raises(WorkflowValidationError, match="malformed extension"):
        validate_mapping(data)


def test_guardrail_metadata_is_preserved_and_validated() -> None:
    """Deferred guardrail declarations preserve supported phase and behavior metadata."""

    data = valid_manifest_data()
    data["extensions"] = {
        "guardrails": {
            "declarations": [
                {
                    "id": "pii_check",
                    "phase": "input",
                    "behavior_on_tripwire": "abort",
                },
                {
                    "id": "safe_tool_args",
                    "phase": "tool_input",
                    "behavior_on_tripwire": "reject_content",
                    "reject_content_message": "Tool arguments were rejected.",
                },
            ]
        }
    }

    manifest = load_runtime_manifest(data)

    assert [guardrail.id for guardrail in manifest.guardrails] == [
        "pii_check",
        "safe_tool_args",
    ]
    assert [guardrail.phase for guardrail in manifest.guardrails] == [
        "input",
        "tool_input",
    ]
    assert manifest.guardrails[1].behavior_on_tripwire == "reject_content"
    assert manifest.guardrails[1].message == "Tool arguments were rejected."

    validate_runtime_manifest(manifest)


def test_guardrail_metadata_fails_closed_for_bad_phase_and_behavior() -> None:
    """Guardrail metadata rejects unsupported phases and behaviors."""

    data = valid_manifest_data()
    data["extensions"] = {
        "guardrails": {
            "declarations": [
                {
                    "id": "bad_guardrail",
                    "phase": "session",
                    "behavior_on_tripwire": "continue",
                }
            ]
        }
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_mapping(data)

    message = str(exc_info.value)
    assert "unsupported phase" in message
    assert "unsupported behavior_on_tripwire" in message


def test_guardrail_reject_content_requires_message() -> None:
    """Reject-content guardrails need a model-visible message."""

    data = valid_manifest_data()
    data["extensions"] = {
        "guardrails": {
            "declarations": [
                {
                    "id": "safe_output",
                    "phase": "output",
                    "behavior_on_tripwire": "reject_content",
                }
            ]
        }
    }

    with pytest.raises(WorkflowValidationError, match="must define message"):
        validate_mapping(data)


def test_mcp_extension_metadata_is_preserved_and_validated() -> None:
    """MCP registry-source and lifecycle diagnostics metadata round-trips and validates."""

    data = valid_manifest_data()
    data["extensions"] = {
        "mcp_registry_sources": {
            "sources": [
                {
                    "id": "primary_registry",
                    "server": "demo-mcp",
                    "status": "active",
                    "tool_cache": "enabled",
                    "disabled": False,
                    "operation_locking": "per_server",
                    "memory_pollution": "medium",
                }
            ]
        },
        "mcp_lifecycle_diagnostics": {
            "startup_mode": "degraded",
            "reconnect": "automatic",
            "cleanup_timeout": "30s",
            "active_servers_state_key": "mcp_active_servers",
            "failed_servers_state_key": "mcp_failed_servers",
            "error_map_state_key": "mcp_error_map",
        },
    }

    manifest = load_runtime_manifest(data)

    assert [source.id for source in manifest.mcp_registry_sources] == [
        "primary_registry"
    ]
    assert manifest.mcp_registry_sources[0].server == "demo-mcp"
    assert manifest.mcp_registry_sources[0].status == "active"
    assert manifest.mcp_lifecycle_diagnostics is not None
    assert manifest.mcp_lifecycle_diagnostics.startup_mode == "degraded"
    assert manifest.mcp_lifecycle_diagnostics.reconnect == "automatic"

    validate_runtime_manifest(manifest)


def test_mcp_extension_metadata_fails_closed_for_bad_values() -> None:
    """MCP extension metadata rejects malformed status and lifecycle values."""

    data = valid_manifest_data()
    data["extensions"] = {
        "mcp_registry_sources": {
            "sources": [
                {
                    "id": "broken_registry",
                    "server": "demo-mcp",
                    "status": "warming",
                    "tool_cache": "sometimes",
                    "disabled": "no",
                    "operation_locking": "cluster",
                    "memory_pollution": "extreme",
                }
            ]
        },
        "mcp_lifecycle_diagnostics": {
            "startup_mode": "best_effort",
            "reconnect": "often",
        },
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_mapping(data)

    message = str(exc_info.value)
    assert "unsupported status" in message
    assert "unsupported tool_cache" in message
    assert "must define disabled as boolean" in message
    assert "unsupported operation_locking" in message
    assert "unsupported memory_pollution" in message
    assert "unsupported startup_mode" in message
    assert "unsupported reconnect" in message
    assert "must define cleanup_timeout" in message


def test_llm_step_requires_prompt_or_prompt_source() -> None:
    """LLM steps need inline prompt data or a prompt source."""

    data = valid_manifest_data()
    nodes = deepcopy(data["nodes"])
    assert isinstance(nodes, list)
    nodes[0] = {"id": "analyze_request", "kind": "llm_step"}
    data["nodes"] = nodes

    with pytest.raises(WorkflowValidationError, match="prompt or prompt_source"):
        validate_mapping(data)


def test_context_pipeline_attachment_requires_explicit_sources_and_contract() -> None:
    """Context-pipeline metadata must fail closed when attachment fields are incomplete."""

    data = valid_manifest_data()
    nodes = deepcopy(data["nodes"])
    assert isinstance(nodes, list)
    nodes[0] = {
        "id": "analyze_request",
        "kind": "llm_step",
        "prompt": {"user_template": "Analyze {prompt} with {prepared_context}"},
        "context_pipeline": {
            "enabled": True,
            "strategy": "semantic_pruning",
            "profile": "default",
        },
        "context_sources": [
            {"kind": "conversation_history", "source": "state.chat_history"}
        ],
    }
    data["nodes"] = nodes

    with pytest.raises(WorkflowValidationError, match="context_contract"):
        validate_mapping(data)


def test_context_pipeline_attachment_rejects_non_llm_step_nodes() -> None:
    """Context-pipeline metadata must not attach to non-llm-step nodes."""

    data = valid_manifest_data()
    nodes = deepcopy(data["nodes"])
    assert isinstance(nodes, list)
    nodes[1] = {
        "id": "lookup_context",
        "kind": "tool_use_step",
        "tool_id": "search_repo",
        "context_pipeline": {
            "enabled": True,
            "strategy": "semantic_pruning",
            "profile": "default",
        },
        "context_sources": [
            {"kind": "conversation_history", "source": "state.chat_history"},
            {"kind": "latest_user_prompt", "source": "prompt"},
        ],
        "context_contract": {
            "history_input": "state.chat_history",
            "current_prompt_input": "prompt",
            "output_slot": "prepared_context",
        },
    }
    data["nodes"] = nodes

    with pytest.raises(
        WorkflowValidationError, match="non-llm_step node 'lookup_context'"
    ):
        validate_mapping(data)


def test_rag_manifest_preserves_and_validates_pipeline_and_model_requirements() -> None:
    """RAG metadata and LLM embedding requirements are accepted as manifest guidance."""

    data = valid_manifest_data()
    data["metadata"] = {
        "patterns_present": ["memory-augmented-agent", "rag", "embedding_retrieval"],
        "rag_pipeline": {
            "retrieval_mode": "embedding_semantic",
            "embedding_capability": "required",
            "graph_capability": "not_applicable",
            "index_owner": "runtime",
            "graph_store_owner": "unknown",
            "corpus_boundary": "runtime fixture documents",
            "chunking_policy": "runtime default",
            "metadata_filters": ["tenant", "document_type"],
            "reranking": "vector_score",
            "freshness_policy": "manual",
            "provenance_required": True,
            "context_assembly": {
                "target": "prepare_model_input",
                "required_evidence_fields": ["source_id", "chunk_id"],
            },
        },
    }
    data["nodes"] = [
        {
            "id": "analyze_request",
            "kind": "llm_step",
            "prompt": {
                "user_template": "Plan retrieval for {prompt}",
                "output_schema_ref": "retrieval_plan",
            },
            "model_requirements": {
                "required_capabilities": ["structured_output", "embeddings"],
                "reasoning_profile": {
                    "level": "medium",
                    "task_type": "planning",
                    "task_subtype": "synthesis",
                    "uncertainty_handling": "ask_clarification",
                },
                "context_requirements": {
                    "expected_input_size": "medium",
                    "minimum_context_window": 16000,
                    "needs_retrieved_context": "conditional",
                },
                "output_requirements": {
                    "format": "schema_ref",
                    "schema_ref": "retrieval_plan",
                    "evidence_citations": "preferred",
                },
                "operational_preferences": {
                    "latency_sensitivity": "medium",
                    "cost_sensitivity": "medium",
                    "determinism": "balanced",
                    "data_boundary": "private_runtime",
                },
                "fallback_policy": {
                    "if_unavailable": "escalate",
                    "minimum_acceptable_level": "low",
                },
            },
        }
    ]
    data["edges"] = []
    data["tools"] = []
    data["output_contracts"] = [{"id": "retrieval_plan", "required_fields": ["query"]}]

    manifest = load_runtime_manifest(data)

    validate_runtime_manifest(manifest)
    assert manifest.rag_pipeline["retrieval_mode"] == "embedding_semantic"
    assert manifest.nodes[0].model_requirements["required_capabilities"] == [
        "structured_output",
        "embeddings",
    ]


def test_staged_rag_pipeline_metadata_passes_validation() -> None:
    """Staged RAG orchestration metadata validates without adding execution behavior."""

    data = valid_manifest_data()
    data["metadata"] = {
        "patterns_present": ["rag", "embedding_retrieval"],
        "rag_pipeline": {
            "orchestration_mode": "hybrid_retrieval",
            "retrieval_mode": "hybrid",
            "retrievers": [
                {
                    "id": "keyword",
                    "tool_id": "keyword_search",
                    "mode": "lexical_keyword",
                    "required": True,
                },
                {
                    "id": "semantic",
                    "tool_id": "semantic_search",
                    "mode": "embedding_semantic",
                    "required": True,
                },
            ],
            "fusion": "rrf",
            "reranking": "caller_adapter",
            "compression": "none",
            "correction": "optional",
            "candidate_budget": {
                "stage1_k": 50,
                "stage2_k": 20,
                "final_k": 5,
            },
            "embedding_capability": "required",
            "graph_capability": "not_applicable",
            "provenance_required": True,
            "context_assembly": {
                "target": "prepare_model_input",
                "max_context_tokens": 8192,
                "required_evidence_fields": [
                    "source_id",
                    "chunk_id",
                    "citation_handle",
                ],
            },
            "permissions": {
                "permission_filtering": "required",
                "permission_failure_policy": "fail_closed",
                "audit_required": True,
            },
            "source_readiness": {
                "source_registry": "external_service",
                "refresh_mode": "scheduled",
                "index_version": "caller_supplied",
                "stale_state": "fresh",
            },
            "cache": {
                "retrieval_results": "optional",
                "semantic_query_cache": "optional",
            },
            "degraded_states": ["stale_but_allowed", "partial_results"],
        },
    }

    validate_mapping(data)


def test_staged_rag_pipeline_metadata_fails_for_malformed_values() -> None:
    """Staged RAG metadata reports malformed v1 fields clearly."""

    data = valid_manifest_data()
    data["metadata"] = {
        "patterns_present": ["rag", "embedding_retrieval"],
        "rag_pipeline": {
            "orchestration_mode": "surprise",
            "retrieval_mode": "hybrid",
            "retrievers": [
                {
                    "id": "",
                    "tool_id": 7,
                    "mode": "telepathy",
                    "required": "yes",
                },
                "not-a-mapping",
            ],
            "fusion": "magic",
            "reranking": "oracle",
            "compression": "lossy_magic",
            "correction": "always",
            "candidate_budget": {"stage1_k": 0, "stage2_k": True, "final_k": "five"},
            "embedding_capability": "required",
            "context_assembly": {
                "target": "raw_prompt_append",
                "max_context_tokens": 0,
                "required_evidence_fields": ["source_id", 3],
            },
            "permissions": {
                "permission_filtering": "maybe",
                "permission_failure_policy": "continue",
                "audit_required": "yes",
            },
            "source_readiness": {
                "source_registry": "ambient_runtime",
                "refresh_mode": "whenever",
                "stale_state": "moldy",
            },
            "cache": {
                "retrieval_results": "always",
                "semantic_query_cache": 5,
            },
            "degraded_states": ["partial_results", "ominous"],
        },
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_mapping(data)

    message = str(exc_info.value)
    assert "metadata.rag_pipeline.orchestration_mode has unsupported value" in message
    assert "metadata.rag_pipeline.retrievers[0].id must not be blank" in message
    assert "metadata.rag_pipeline.retrievers[0].tool_id must be a string" in message
    assert "metadata.rag_pipeline.retrievers[0].mode has unsupported value" in message
    assert "metadata.rag_pipeline.retrievers[0].required must be boolean" in message
    assert "metadata.rag_pipeline.retrievers[1] must be a mapping" in message
    assert "metadata.rag_pipeline.fusion has unsupported value 'magic'" in message
    assert "metadata.rag_pipeline.reranking has unsupported value 'oracle'" in message
    assert (
        "metadata.rag_pipeline.compression has unsupported value 'lossy_magic'"
        in message
    )
    assert "metadata.rag_pipeline.correction has unsupported value 'always'" in message
    assert (
        "metadata.rag_pipeline.candidate_budget.stage1_k must be a positive integer"
        in message
    )
    assert (
        "metadata.rag_pipeline.context_assembly.target has unsupported value" in message
    )
    assert (
        "metadata.rag_pipeline.context_assembly.required_evidence_fields must be a list of strings"
        in message
    )
    assert (
        "metadata.rag_pipeline.permissions.permission_filtering has unsupported value"
        in message
    )
    assert "metadata.rag_pipeline.permissions.audit_required must be boolean" in message
    assert (
        "metadata.rag_pipeline.source_readiness.stale_state has unsupported value"
        in message
    )
    assert (
        "metadata.rag_pipeline.cache.semantic_query_cache has unsupported value"
        in message
    )
    assert (
        "metadata.rag_pipeline.degraded_states contains unsupported values" in message
    )


def test_rag_provenance_required_needs_evidence_fields_or_provenance_retriever() -> (
    None
):
    """Provenance-required RAG metadata needs a declared evidence source."""

    data = valid_manifest_data()
    data["metadata"] = {
        "patterns_present": ["rag"],
        "rag_pipeline": {
            "retrieval_mode": "keyword",
            "retrievers": [
                {
                    "id": "keyword",
                    "tool_id": "keyword_search",
                    "mode": "keyword",
                    "required": True,
                }
            ],
            "provenance_required": True,
        },
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_mapping(data)

    assert (
        "metadata.rag_pipeline.provenance_required requires "
        "context_assembly.required_evidence_fields or a required provenance retriever"
        in str(exc_info.value)
    )

    data["metadata"]["rag_pipeline"]["retrievers"][0]["provides_provenance"] = True
    validate_mapping(data)


def test_rag_provenance_required_accepts_context_evidence_fields() -> None:
    """Required evidence fields satisfy provenance-required RAG metadata."""

    data = valid_manifest_data()
    data["metadata"] = {
        "patterns_present": ["rag"],
        "rag_pipeline": {
            "retrieval_mode": "keyword",
            "provenance_required": True,
            "context_assembly": {
                "target": "prepare_model_input",
                "max_context_tokens": 2048,
                "required_evidence_fields": ["source_id", "chunk_id"],
            },
        },
    }

    validate_mapping(data)


def test_invalid_rag_pipeline_and_model_requirements_fail_validation() -> None:
    """RAG and model-requirement metadata fail clearly when generated malformed."""

    data = valid_manifest_data()
    data["metadata"] = {
        "patterns_present": ["embedding_retrieval", "graphrag"],
        "rag_pipeline": {
            "retrieval_mode": "keyword",
            "embedding_capability": "optional",
            "graph_capability": "optional",
            "metadata_filters": ["tenant", 3],
            "provenance_required": "yes",
        },
    }
    data["nodes"] = [
        {
            "id": "analyze_request",
            "kind": "llm_step",
            "prompt": {
                "user_template": "Plan retrieval for {prompt}",
                "output_schema_ref": "retrieval_plan",
            },
            "model_requirements": {
                "required_capabilities": ["embeddings", "telepathy"],
                "reasoning_profile": {"level": "heroic"},
                "context_requirements": {
                    "expected_input_size": "huge",
                    "minimum_context_window": 0,
                    "needs_retrieved_context": "sometimes",
                },
                "output_requirements": {
                    "format": "spreadsheet",
                    "schema_ref": "other_contract",
                    "evidence_citations": "always",
                },
                "operational_preferences": {"data_boundary": "public_internet"},
                "fallback_policy": {"if_unavailable": "guess"},
            },
        },
        {
            "id": "lookup_context",
            "kind": "tool_use_step",
            "tool_id": "search_repo",
            "model_requirements": {"required_capabilities": ["embeddings"]},
        },
    ]
    data["edges"] = [
        {
            "source": "analyze_request",
            "target": "lookup_context",
            "edge_kind": "sequential",
        }
    ]
    data["output_contracts"] = [{"id": "retrieval_plan", "required_fields": ["query"]}]

    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_mapping(data)

    message = str(exc_info.value)
    assert "required_capabilities contains unsupported values" in message
    assert "reasoning_profile.level has unsupported value 'heroic'" in message
    assert "minimum_context_window must be a positive integer or 'unknown'" in message
    assert "prompt output_schema_ref 'retrieval_plan' must match" in message
    assert (
        "non-llm_step node 'lookup_context' must not define model_requirements"
        in message
    )
    assert (
        "embedding_retrieval requires metadata.rag_pipeline.retrieval_mode" in message
    )
    assert (
        "graph retrieval patterns require metadata.rag_pipeline.graph_capability"
        in message
    )


def test_react_loop_manifest_requires_loopback_iterations_state_and_tool_step() -> None:
    """ReAct-style manifests fail clearly when loop metadata is incomplete."""

    data = valid_manifest_data()
    data["metadata"] = {"patterns_present": ["react_loop"]}
    data["runtime"] = {"execution_policy": {"model": "gpt-test", "max_iterations": 0}}
    data["nodes"] = [
        {
            "id": "reason",
            "kind": "llm_step",
            "prompt": {"user_template": "Reason about {prompt}"},
        }
    ]
    data["edges"] = []
    data["tools"] = []

    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_mapping(data)

    message = str(exc_info.value)
    assert "react_loop requires runtime.execution_policy.max_iterations" in message
    assert "react_loop requires at least one loopback edge" in message
    assert "react_loop requires runtime.state metadata" in message
    assert (
        "react_loop requires at least one llm_step and one tool_use_step node"
        in message
    )


def test_react_loop_manifest_passes_with_loopback_iterations_state_and_tool_step() -> (
    None
):
    """ReAct-style manifests pass when the minimal loop contract is present."""

    data = valid_manifest_data()
    data["entrypoint"] = "reason"
    data["metadata"] = {"patterns_present": ["react_loop", "evidence_loop"]}
    data["runtime"] = {
        "execution_policy": {"model": "gpt-test", "max_iterations": 3},
        "state": {
            "artifacts": [
                {"id": "observation_log", "description": "Model-safe observations"}
            ],
            "mutable_fields": ["observation_log"],
        },
    }
    data["nodes"] = [
        {
            "id": "reason",
            "kind": "llm_step",
            "prompt": {"user_template": "Reason about {prompt}"},
            "model_requirements": {
                "reasoning_profile": {
                    "level": "medium",
                    "task_type": "planning",
                    "uncertainty_handling": "ask_clarification",
                },
                "output_requirements": {
                    "format": "free_text",
                    "evidence_citations": "preferred",
                },
            },
        },
        {"id": "act", "kind": "tool_use_step", "tool_id": "search_repo"},
        {
            "id": "assess",
            "kind": "decision_step",
            "decision_subtype": "simple_check",
        },
    ]
    data["edges"] = [
        {"source": "reason", "target": "act", "edge_kind": "sequential"},
        {"source": "act", "target": "assess", "edge_kind": "sequential"},
        {"source": "assess", "target": "reason", "edge_kind": "loopback"},
    ]

    validate_mapping(data)


def test_tool_use_completion_policy_fails_closed_for_bad_values() -> None:
    """Tool-use completion policy rejects malformed loop-completion metadata."""

    data = valid_manifest_data()
    data["runtime"] = {
        "execution_policy": {
            "model": "gpt-test",
            "tool_use_completion": {
                "run_again": "sometimes",
                "stop_on_tool": "afterwards",
                "final_output": "custom",
                "final_output_state_key": 99,
            },
        }
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_mapping(data)

    message = str(exc_info.value)
    assert ".run_again has unsupported value 'sometimes'" in message
    assert ".stop_on_tool has unsupported value 'afterwards'" in message
    assert ".final_output has unsupported value 'custom'" in message
    assert ".final_output_state_key must be a string" in message


def test_tool_use_completion_policy_requires_state_key_for_state_field() -> None:
    """State-field final output requires an explicit state key."""

    data = valid_manifest_data()
    data["runtime"] = {
        "execution_policy": {
            "model": "gpt-test",
            "tool_use_completion": {
                "run_again": "required",
                "stop_on_tool": "enabled",
                "final_output": "state_field",
            },
        }
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_mapping(data)

    assert "final_output_state_key is required" in str(exc_info.value)


def test_tool_use_completion_policy_passes_with_supported_metadata() -> None:
    """Tool-use completion policy accepts the current metadata-only OA5 shape."""

    data = valid_manifest_data()
    data["runtime"] = {
        "execution_policy": {
            "model": "gpt-test",
            "tool_use_completion": {
                "run_again": "required",
                "stop_on_tool": "enabled",
                "final_output": "state_field",
                "final_output_state_key": "latest_tool_result",
            },
        }
    }

    validate_mapping(data)


def test_skill_source_resolution_policy_passes_with_supported_metadata() -> None:
    """Skill-source resolution accepts the prepared package-local v1 policy."""

    data = valid_manifest_data()
    data["runtime"] = {
        "execution_policy": {
            "model": "gpt-test",
            "skill_source_resolution": {
                "enabled": True,
                "allowed_sources": ["package_bundle"],
                "max_skill_bytes": 1024,
                "max_node_skill_bytes": 4096,
                "load_support_files": False,
                "prompt_role": "developer",
            },
        }
    }

    manifest = load_runtime_manifest(data)

    validate_runtime_manifest(manifest)
    assert manifest.skill_source_resolution_policy is not None
    assert manifest.skill_source_resolution_policy.enabled is True
    assert manifest.skill_source_resolution_policy.allowed_sources == (
        "package_bundle",
    )
    assert manifest.skill_source_resolution_policy.to_policy() == (
        SkillSourceResolutionPolicy(
            enabled=True,
            allowed_sources=("package_bundle",),
            max_skill_bytes=1024,
            max_node_skill_bytes=4096,
            load_support_files=False,
            prompt_role="developer",
            raw=manifest.skill_source_resolution_policy.raw,
        )
    )


def test_skill_source_resolution_policy_fails_closed_for_bad_values() -> None:
    """Skill-source resolution rejects unsupported v1 policy metadata."""

    data = valid_manifest_data()
    data["runtime"] = {
        "execution_policy": {
            "model": "gpt-test",
            "skill_source_resolution": {
                "enabled": "yes",
                "allowed_sources": ["package_bundle", "global_user"],
                "max_skill_bytes": 4096,
                "max_node_skill_bytes": 1024,
                "load_support_files": True,
                "prompt_role": "user",
            },
        }
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_mapping(data)

    message = str(exc_info.value)
    assert ".enabled must be boolean" in message
    assert ".allowed_sources contains unsupported values ['global_user']" in message
    assert (
        ".max_node_skill_bytes must be greater than or equal to max_skill_bytes"
        in message
    )
    assert ".load_support_files is not supported in v1" in message
    assert ".prompt_role has unsupported value 'user'" in message


def test_skill_source_provenance_models_redact_raw_content() -> None:
    """Resolver provenance models expose diagnostics without skill bodies."""

    resolved = ResolvedSkillSource(
        skill_id="demo",
        body="# Demo\nsecret details",
        source_kind="package_bundle",
        trust="package_local",
        package_id="pkg",
        bundled_path="skills/demo/SKILL.md",
        content_hash="sha256:abc",
        byte_count=21,
    )
    rejected = RejectedSkillSource(
        skill_id="demo",
        reason="unsupported encoding",
        source_kind="package_bundle",
        bundled_path="skills/demo/SKILL.md",
    )

    resolved_metadata = resolved.redacted_metadata()
    rejected_metadata = rejected.redacted_metadata()

    assert "body" not in resolved_metadata
    assert "secret details" not in str(resolved_metadata)
    assert resolved_metadata["skill_id"] == "demo"
    assert resolved_metadata["content_hash"] == "sha256:abc"
    assert rejected_metadata == {
        "skill_id": "demo",
        "reason": "unsupported encoding",
        "source_kind": "package_bundle",
        "bundled_path": "skills/demo/SKILL.md",
    }


def test_async_session_policy_fails_closed_for_bad_values() -> None:
    """Async session policy rejects malformed deferred session metadata."""

    data = valid_manifest_data()
    data["runtime"] = {
        "execution_policy": {
            "model": "gpt-test",
            "async_session": {
                "mode": "always_on",
                "persist": "disk",
                "history": "all_turns",
                "session_id_state_key": 9,
                "session_messages_state_key": "   ",
            },
        }
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_mapping(data)

    message = str(exc_info.value)
    assert ".mode has unsupported value 'always_on'" in message
    assert ".persist has unsupported value 'disk'" in message
    assert ".history has unsupported value 'all_turns'" in message
    assert ".session_id_state_key must be a string" in message
    assert ".session_messages_state_key must not be blank" in message


def test_async_session_policy_requires_session_id_for_persisted_state() -> None:
    """Persisted async session metadata requires a stable session id state key."""

    data = valid_manifest_data()
    data["runtime"] = {
        "execution_policy": {
            "model": "gpt-test",
            "async_session": {
                "mode": "create_or_resume",
                "persist": "external_checkpoint",
                "history": "summary",
                "session_messages_state_key": "session_messages",
            },
        }
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_mapping(data)

    assert ".session_id_state_key is required" in str(exc_info.value)


def test_async_session_policy_rejects_state_keys_when_persist_is_none() -> None:
    """Non-persisted async session metadata must not declare persisted state keys."""

    data = valid_manifest_data()
    data["runtime"] = {
        "execution_policy": {
            "model": "gpt-test",
            "async_session": {
                "mode": "metadata_only",
                "persist": "none",
                "history": "last_turn",
                "session_id_state_key": "session_id",
            },
        }
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_mapping(data)

    assert "state-key fields are only allowed when persist is not 'none'" in str(
        exc_info.value
    )


def test_async_session_policy_rejects_message_key_when_history_is_none() -> None:
    """Session-message state keys require history retention beyond 'none'."""

    data = valid_manifest_data()
    data["runtime"] = {
        "execution_policy": {
            "model": "gpt-test",
            "async_session": {
                "mode": "reuse_existing",
                "persist": "in_memory",
                "history": "none",
                "session_id_state_key": "session_id",
                "session_messages_state_key": "session_messages",
            },
        }
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_mapping(data)

    assert (
        "session_messages_state_key is only allowed when history is not 'none'"
        in str(exc_info.value)
    )


def test_async_session_policy_passes_with_supported_metadata() -> None:
    """OA8 async session metadata passes with the supported metadata-only shape."""

    data = valid_manifest_data()
    data["runtime"] = {
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
    }

    validate_mapping(data)


def test_approval_interruption_policy_fails_closed_for_bad_values() -> None:
    """Approval interruption policy rejects malformed pause/resume metadata."""

    data = valid_manifest_data()
    data["runtime"] = {
        "execution_policy": {
            "model": "gpt-test",
            "approval_interruption": {
                "mode": "sometimes_pause",
                "persist": "disk",
                "resume_from": "wherever",
                "pending_tool_calls_state_key": 99,
                "pending_approvals_state_key": "   ",
                "interruption_state_key": False,
                "resume_token_state_key": [],
            },
        }
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_mapping(data)

    message = str(exc_info.value)
    assert ".mode has unsupported value 'sometimes_pause'" in message
    assert ".persist has unsupported value 'disk'" in message
    assert ".resume_from has unsupported value 'wherever'" in message
    assert ".pending_tool_calls_state_key must be a string" in message
    assert ".pending_approvals_state_key must not be blank" in message
    assert ".interruption_state_key must be a string" in message
    assert ".resume_token_state_key must be a string" in message


def test_approval_interruption_policy_requires_state_keys_for_persisted_state() -> None:
    """Persisted interruption metadata requires non-blank resumable state keys."""

    data = valid_manifest_data()
    data["runtime"] = {
        "execution_policy": {
            "model": "gpt-test",
            "approval_interruption": {
                "mode": "pause_on_approval",
                "persist": "external_checkpoint",
                "resume_from": "approval_decision",
                "resume_token_state_key": "resume_token",
            },
        }
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_mapping(data)

    message = str(exc_info.value)
    assert ".pending_tool_calls_state_key is required" in message
    assert ".pending_approvals_state_key is required" in message
    assert ".interruption_state_key is required" in message


def test_approval_interruption_policy_rejects_state_keys_when_persist_is_none() -> None:
    """Non-persisted interruption metadata must not declare resumable state keys."""

    data = valid_manifest_data()
    data["runtime"] = {
        "execution_policy": {
            "model": "gpt-test",
            "approval_interruption": {
                "mode": "metadata_only",
                "persist": "none",
                "resume_from": "workflow_restart",
                "pending_tool_calls_state_key": "pending_tool_calls",
            },
        }
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_mapping(data)

    assert "state-key fields are only allowed when persist is not 'none'" in str(
        exc_info.value
    )


def test_approval_interruption_policy_passes_with_supported_metadata() -> None:
    """OA7 approval interruption metadata passes with the supported metadata-only shape."""

    data = valid_manifest_data()
    data["runtime"] = {
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
    }

    validate_mapping(data)


def test_handoff_metadata_fails_closed_for_bad_values() -> None:
    """Handoff metadata rejects malformed grouped multi-agent settings."""

    data = valid_manifest_data()
    data["metadata"] = {
        "handoffs": [
            {
                "id": "",
                "target": "",
                "on_handoff": "replace_manager",
                "input_filter": "   ",
                "nested_history": "sometimes",
                "enabled_when": "  ",
            }
        ]
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_mapping(data)

    message = str(exc_info.value)
    assert "handoff metadata at position 0 is missing id" in message
    assert "handoff metadata '' must define target" in message
    assert "has unsupported on_handoff 'replace_manager'" in message
    assert "input_filter must not be blank" in message
    assert "has unsupported nested_history 'sometimes'" in message
    assert "enabled_when must not be blank" in message


def test_agent_as_tool_metadata_fails_closed_for_bad_values() -> None:
    """Agent-as-tool metadata rejects malformed bounded delegation settings."""

    data = valid_manifest_data()
    data["nodes"] = [
        {
            "id": "analyze_request",
            "kind": "llm_step",
            "prompt": {"user_template": "Analyze {prompt}"},
            "agent_as_tool": "not-a-mapping",
        },
        {
            "id": "lookup_context",
            "kind": "tool_use_step",
            "tool_id": "search_repo",
            "agent_as_tool": {
                "skill_id": "",
                "task_boundary": "",
                "output_mode": "custom",
            },
        },
    ]
    data["entrypoint"] = "analyze_request"
    data["edges"] = [
        {
            "source": "analyze_request",
            "target": "lookup_context",
            "edge_kind": "sequential",
        }
    ]

    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_mapping(data)

    message = str(exc_info.value)
    assert "node 'analyze_request' agent-as-tool metadata must be a mapping" in message
    assert (
        "node 'lookup_context' agent-as-tool metadata must define skill_id" in message
    )
    assert (
        "node 'lookup_context' agent-as-tool metadata must define task_boundary"
        in message
    )
    assert (
        "node 'lookup_context' agent-as-tool metadata has unsupported output_mode 'custom'"
        in message
    )


def test_handoff_and_agent_as_tool_metadata_pass_with_supported_shapes() -> None:
    """OA6 metadata passes with grouped handoff and bounded delegation settings."""

    data = valid_manifest_data()
    data["metadata"] = {
        "handoffs": [
            {
                "id": "handoff_to_reviewer",
                "target": "reviewer",
                "on_handoff": "switch_active_profile",
                "input_filter": "latest_request_only",
                "nested_history": "filtered",
                "enabled_when": "needs_review",
            }
        ]
    }
    data["nodes"][1]["agent_as_tool"] = {
        "skill_id": "reviewer-skill",
        "skill_path": "skills/reviewer/SKILL.md",
        "task_boundary": "review a bounded subtask",
        "output_mode": "tool_result",
    }

    validate_mapping(data)


def test_file_context_policy_fails_for_unbounded_or_non_relative_settings() -> None:
    """File-backed prompt-context policy fails closed for unsafe settings."""

    data = valid_manifest_data()
    data["runtime"] = {
        "execution_policy": {
            "model": "gpt-test",
            "prepare_model_input": {
                "file_context": {
                    "enabled": True,
                    "roots": ["", "/absolute", "../escape"],
                    "max_depth": 0,
                    "max_files": "unknown",
                    "max_bytes": -1,
                    "max_tokens": False,
                    "prompt_role": "user",
                    "header": 99,
                }
            },
        }
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_mapping(data)

    message = str(exc_info.value)
    assert ".roots must not contain blank paths" in message
    assert ".roots must use package-relative paths" in message
    assert ".roots must not escape the package root" in message
    assert ".max_depth must be a positive integer or 'unknown'" in message
    assert ".max_bytes must be a positive integer or 'unknown'" in message
    assert ".max_tokens must be a positive integer or 'unknown'" in message
    assert ".prompt_role has unsupported value 'user'" in message
    assert ".header must be a string" in message


def test_file_context_policy_passes_with_bounded_relative_settings() -> None:
    """File-backed prompt-context policy accepts bounded relative configuration."""

    data = valid_manifest_data()
    data["runtime"] = {
        "execution_policy": {
            "model": "gpt-test",
            "prepare_model_input": {
                "file_context": {
                    "enabled": True,
                    "roots": ["docs", "README.md"],
                    "max_depth": 2,
                    "max_files": 4,
                    "max_bytes": 2048,
                    "max_tokens": 400,
                    "prompt_role": "developer",
                    "header": "Project context:",
                }
            },
        }
    }

    validate_mapping(data)


def test_context_compaction_auto_policy_fails_for_unsupported_values() -> None:
    """Automatic context-management policy fails closed for malformed metadata."""

    data = valid_manifest_data()
    data["runtime"] = {
        "execution_policy": {
            "model": "gpt-test",
            "prepare_model_input": {
                "context_compaction": {
                    "auto": {
                        "enabled": "yes",
                        "threshold_ratio": "high",
                        "reserve_tokens": -1,
                        "scope": "global_memory",
                        "implementation": "magic",
                        "strategy": "semantic_embeddings",
                        "mode": "always",
                        "manual_mode": "surprise",
                        "trigger": "provider_error",
                        "reset_behavior": "compact",
                        "lifecycle_stages": ["validate", "teleport"],
                        "metrics": ["lane_utilization", "vibes"],
                    }
                },
                "context_compression": {
                    "profile": "dreamy",
                    "lanes": {
                        "pinned_tokens": 0,
                        "current_turn_tokens": False,
                        "recent_turn_tokens": -1,
                    },
                    "selection": {
                        "strategy": "vector_search",
                        "max_selected_turns": "many",
                        "chronological_reassembly": "yes",
                    },
                },
            },
        }
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_mapping(data)

    message = str(exc_info.value)
    assert ".auto.enabled must be boolean" in message
    assert ".auto.threshold_ratio must be a number between 0 and 1" in message
    assert ".auto.reserve_tokens must be a positive integer" in message
    assert ".auto.scope has unsupported value 'global_memory'" in message
    assert ".auto.implementation has unsupported value 'magic'" in message
    assert ".auto.strategy has unsupported value 'semantic_embeddings'" in message
    assert ".auto.mode has unsupported value 'always'" in message
    assert ".auto.manual_mode has unsupported value 'surprise'" in message
    assert ".auto.trigger has unsupported value 'provider_error'" in message
    assert ".auto.reset_behavior must not request compaction" in message
    assert ".auto.lifecycle_stages contains unsupported values" in message
    assert ".auto.metrics contains unsupported values" in message
    assert ".context_compression.profile has unsupported value 'dreamy'" in message
    assert (
        ".context_compression.lanes.pinned_tokens must be a positive integer" in message
    )
    assert (
        ".context_compression.selection.strategy has unsupported value 'vector_search'"
        in message
    )
    assert ".context_compression.selection.max_selected_turns" in message
    assert (
        ".context_compression.selection.chronological_reassembly must be boolean"
        in message
    )


def test_context_compaction_auto_policy_passes_with_supported_values() -> None:
    """Automatic context-management policy accepts the Slice 1 metadata contract."""

    data = valid_manifest_data()
    data["runtime"] = {
        "execution_policy": {
            "model": "gpt-test",
            "prepare_model_input": {
                "context_compaction": {
                    "auto": {
                        "enabled": True,
                        "threshold_ratio": 0.85,
                        "reserve_tokens": 2048,
                        "scope": "current_run",
                        "implementation": "metadata_only",
                        "strategy": "basic",
                        "mode": "auto",
                        "manual_mode": "allowed",
                        "trigger": "token_threshold",
                        "reset_behavior": "new_window",
                        "lifecycle_stages": ["validate", "segment", "report"],
                        "metrics": ["lane_utilization", "coverage_completeness"],
                    }
                },
                "context_compression": {
                    "profile": "instruction_weighted",
                    "lanes": {
                        "pinned_tokens": 2048,
                        "current_turn_tokens": 4096,
                        "recent_turn_tokens": 8192,
                        "summary_tokens": 1024,
                        "selected_turn_tokens": 4096,
                        "file_context_tokens": 1024,
                        "retrieved_context_tokens": 2048,
                    },
                    "selection": {
                        "strategy": "deterministic_overlap",
                        "max_selected_turns": 4,
                        "chronological_reassembly": True,
                    },
                },
            },
        }
    }

    validate_mapping(data)


def test_runtime_behavior_overrides_pass_validation() -> None:
    """Valid prompt and skill overrides pass before execution."""

    data = valid_manifest_data()
    data["nodes"] = [
        {
            "id": "analyze_request",
            "kind": "llm_step",
            "prompt": {"user_template": "Analyze {prompt}"},
            "skill_refs": ["base-skill"],
        },
    ]
    data["edges"] = []
    data["skills"] = [
        {
            "id": "base-skill",
            "prompt_role": "developer",
            "instructions": "Use the base style.",
        }
    ]
    workflow = LoadedAgentWorkflow(
        runtime_manifest=load_runtime_manifest(data),
        runtime_overrides=load_runtime_behavior_overrides(
            {
                "format_version": 1,
                "override_type": "dynamic_agent_runtime_overrides",
                "skills": {
                    "added": [
                        {
                            "id": "concise-writer",
                            "prompt_role": "developer",
                            "instructions": "Write tersely.",
                        }
                    ]
                },
                "nodes": {
                    "analyze_request": {
                        "prompt": {
                            "append": {"developer": " Keep it short."},
                            "replace": {"user_template": "Override {prompt}"},
                        },
                        "skill_refs": {"add": ["concise-writer"]},
                    }
                },
            }
        ),
    )

    validate_agent_workflow(workflow)


def test_runtime_behavior_overrides_fail_closed() -> None:
    """Invalid override versions, targets, fields, and skill refs fail closed."""

    data = valid_manifest_data()
    data["skills"] = [{"id": "known-skill", "instructions": "Known."}]
    data["nodes"] = [
        {
            "id": "analyze_request",
            "kind": "llm_step",
            "prompt": {"user_template": "Analyze {prompt}"},
            "skill_refs": ["missing-base-skill"],
        },
        {"id": "lookup_context", "kind": "tool_use_step", "tool_id": "search_repo"},
    ]
    data["edges"] = [
        {
            "source": "analyze_request",
            "target": "lookup_context",
            "edge_kind": "sequential",
        }
    ]
    workflow = LoadedAgentWorkflow(
        runtime_manifest=load_runtime_manifest(data),
        runtime_overrides=load_runtime_behavior_overrides(
            {
                "format_version": 2,
                "override_type": "wrong",
                "skills": {"added": [{"id": "bad-skill"}]},
                "nodes": {
                    "missing_node": {"prompt": {"replace": {"user_template": "x"}}},
                    "lookup_context": {"prompt": {"replace": {"user_template": "x"}}},
                    "analyze_request": {
                        "prompt": {
                            "replace": {"unsupported": "x"},
                            "append": {"output_schema_ref": "schema"},
                        },
                        "skill_refs": {"add": ["unknown-skill"]},
                    },
                },
            }
        ),
    )

    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_agent_workflow(workflow)

    message = str(exc_info.value)
    assert "unsupported behavior override format_version" in message
    assert "unsupported behavior override override_type" in message
    assert "behavior override skill 'bad-skill' is missing instructions" in message
    assert "targets unknown node 'missing_node'" in message
    assert "targets non-llm_step node 'lookup_context'" in message
    assert "replaces unsupported field 'unsupported'" in message
    assert "appends unsupported field 'output_schema_ref'" in message
    assert "references unknown skill 'unknown-skill'" in message
    assert "references unknown skill 'missing-base-skill'" in message


def test_manifest_skill_refs_fail_when_no_override_artifact() -> None:
    """Base node skill references are checked against the skill catalog."""

    data = valid_manifest_data()
    data["nodes"] = [
        {
            "id": "analyze_request",
            "kind": "llm_step",
            "prompt": {"user_template": "Analyze {prompt}"},
            "skill_refs": ["missing-skill"],
        }
    ]
    data["edges"] = []
    workflow = LoadedAgentWorkflow(runtime_manifest=load_runtime_manifest(data))

    with pytest.raises(WorkflowValidationError, match="unknown skill 'missing-skill'"):
        validate_agent_workflow(workflow)


def test_tool_index_validation_rejects_bad_shape() -> None:
    """External tool-index structure is validated with clear errors."""

    tool_index = load_tool_index(
        {
            "format_version": 2,
            "index_type": "wrong",
            "tools": [{"label": "missing id"}],
            "skills": [{"source_type": "repo_skill"}],
        }
    )
    assert tool_index is not None

    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_tool_index(tool_index)

    message = str(exc_info.value)
    assert "unsupported tool index format_version" in message
    assert "unsupported tool index index_type" in message
    assert "tool at position 0 is missing id" in message
    assert "skill at position 0 is missing id" in message
