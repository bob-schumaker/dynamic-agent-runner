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
