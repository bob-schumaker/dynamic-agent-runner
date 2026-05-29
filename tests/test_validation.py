"""Tests for dynamic-agent runtime artifact validation."""

from __future__ import annotations

from copy import deepcopy

import pytest

from dynamic_agent_runner.artifacts import (
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


def test_llm_step_requires_prompt_or_prompt_source() -> None:
    """LLM steps need inline prompt data or a prompt source."""

    data = valid_manifest_data()
    nodes = deepcopy(data["nodes"])
    assert isinstance(nodes, list)
    nodes[0] = {"id": "analyze_request", "kind": "llm_step"}
    data["nodes"] = nodes

    with pytest.raises(WorkflowValidationError, match="prompt or prompt_source"):
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
