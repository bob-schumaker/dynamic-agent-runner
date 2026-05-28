"""Tests for the repository-owned dynamic-agent tool registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from dynamic_agent_runner.artifacts import load_runtime_manifest
from dynamic_agent_runner.errors import ToolRegistryError
from dynamic_agent_runner.models import RuntimeNode, ToolDefinition
from dynamic_agent_runner.registry import (
    InMemoryToolRegistry,
    RegisteredTool,
    ToolExposureOverride,
    ToolRegistryOverrides,
    create_local_workspace_registry,
    openai_tool_schema,
    validate_registry_tool_references,
)


def make_tool(tool_id: str, output: object | None = None) -> RegisteredTool:
    raw = {
        "id": tool_id,
        "label": tool_id.replace("_", " ").title(),
        "description_for_llm": f"Use {tool_id}",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        "side_effect": "read",
        "approval_required": "no",
        "timeout": "runtime_default",
        "retry_policy": "none",
        "failure_behavior": "error",
    }
    return RegisteredTool(
        ToolDefinition.from_mapping(raw),
        lambda args: output if output is not None else {"query": args["query"]},
    )


def manifest_with_tool(tool_id: str = "search_repo"):
    return load_runtime_manifest(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "registry-agent",
            "entrypoint": "start",
            "packaging": {"mode": "hybrid_bundle"},
            "nodes": [
                {
                    "id": "start",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Search"},
                    "available_tools": [tool_id],
                },
                {"id": "use_tool", "kind": "tool_use_step", "tool_id": tool_id},
            ],
            "edges": [
                {"source": "start", "target": "use_tool", "edge_kind": "sequential"}
            ],
            "tools": [{"id": tool_id, "adapter": f"runtime.{tool_id}"}],
        }
    )


def test_registry_lookup_schema_conversion_and_invocation() -> None:
    registry = InMemoryToolRegistry([make_tool("search_repo")])

    assert registry.get_tool("search_repo").id == "search_repo"
    schema = registry.to_openai_tools(["search_repo"])
    assert schema == [openai_tool_schema(registry.get_tool("search_repo").definition)]
    assert schema[0]["function"]["name"] == "search_repo"

    result = registry.invoke_tool("search_repo", {"query": "agents"})

    assert result.success is True
    assert result.output == {"query": "agents"}


def test_registry_reports_missing_inputs_and_tool_failures() -> None:
    failing_tool = RegisteredTool(
        ToolDefinition.from_mapping(
            {
                "id": "explode",
                "input_schema": {"type": "object", "required": ["query"]},
            }
        ),
        lambda _args: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    registry = InMemoryToolRegistry([failing_tool])

    missing_input = registry.invoke_tool("explode", {})
    failure = registry.invoke_tool("explode", {"query": "x"})

    assert missing_input.success is False
    assert "missing required input" in str(missing_input.error)
    assert failure.success is False
    assert failure.error == "boom"
    with pytest.raises(ToolRegistryError, match="not registered"):
        registry.get_tool("missing")


@pytest.mark.parametrize(
    ("input_schema", "message"),
    [
        ({"type": "string"}, "must be an object schema"),
        ({"type": "object", "properties": []}, "properties must be a mapping"),
        ({"type": "object", "required": "query"}, "required must be a list"),
        (
            {"type": "object", "required": ["query", 1]},
            "required entries must be strings",
        ),
        ({"oneOf": [{"type": "object"}]}, "must not use top-level oneOf"),
        ({"anyOf": [{"type": "object"}]}, "must not use top-level anyOf"),
        ({"allOf": [{"type": "object"}]}, "must not use top-level allOf"),
    ],
)
def test_openai_tool_schema_rejects_malformed_input_schemas(
    input_schema: object,
    message: str,
) -> None:
    definition = ToolDefinition.from_mapping(
        {
            "id": "bad_schema",
            "description_for_llm": "Use bad_schema",
            "input_schema": input_schema,
        }
    )

    with pytest.raises(ToolRegistryError, match=message):
        openai_tool_schema(definition)


def test_openai_tool_schema_strips_schema_metadata_for_model_output() -> None:
    definition = ToolDefinition.from_mapping(
        {
            "id": "search_repo",
            "description_for_llm": "Search repository files.",
            "input_schema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        }
    )

    schema = openai_tool_schema(definition)

    assert schema["function"]["parameters"] == {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }


def test_registry_validates_callable_tool_references_not_metadata_only() -> None:
    manifest = manifest_with_tool("metadata_only")
    registry = InMemoryToolRegistry([])

    with pytest.raises(ToolRegistryError, match="unavailable registry tool"):
        validate_registry_tool_references(manifest, registry)

    validate_registry_tool_references(
        manifest,
        InMemoryToolRegistry([make_tool("metadata_only")]),
    )


def test_runtime_overrides_add_replace_disable_and_restrict_per_node() -> None:
    manifest = manifest_with_tool("search_repo")
    base_registry = InMemoryToolRegistry([make_tool("search_repo", output="old")])
    overrides = ToolRegistryOverrides(
        added_tools=(make_tool("read_file", output="read"),),
        replacement_tools=(make_tool("search_repo", output="new"),),
        node_overrides={"start": ToolExposureOverride(add=("read_file",))},
    )

    registry = base_registry.with_overrides(overrides, manifest=manifest)
    node = manifest.nodes[0]

    assert [tool.id for tool in registry.list_tools_for_node(node)] == [
        "search_repo",
        "read_file",
    ]
    assert registry.invoke_tool("search_repo", {"query": "x"}).output == "new"

    disabled = ToolRegistryOverrides(disabled_tools=("search_repo",))
    with pytest.raises(ToolRegistryError, match="required tool_use_step tool"):
        base_registry.with_overrides(disabled, manifest=manifest)


def test_runtime_overrides_reject_unknown_tools_and_non_llm_nodes() -> None:
    manifest = manifest_with_tool("search_repo")
    registry = InMemoryToolRegistry([make_tool("search_repo")])
    overrides = ToolRegistryOverrides(
        disabled_tools=("missing",),
        node_overrides={
            "use_tool": ToolExposureOverride(add=("missing",)),
        },
    )

    with pytest.raises(ToolRegistryError) as exc_info:
        registry.with_overrides(overrides, manifest=manifest)

    message = str(exc_info.value)
    assert "disabled tool 'missing' does not exist" in message
    assert "non-llm_step node 'use_tool'" in message
    assert "unknown tool 'missing'" in message


def test_llm_node_tool_exposure_requires_node_references() -> None:
    registry = InMemoryToolRegistry([make_tool("read_file")])
    node = RuntimeNode.from_mapping(
        {"id": "llm", "kind": "llm_step", "prompt_source": "inline"}
    )

    assert registry.list_tools_for_node(node) == ()

    exposed = registry.with_overrides(
        ToolRegistryOverrides(
            node_overrides={"llm": ToolExposureOverride(add=("read_file",))}
        ),
        manifest=load_runtime_manifest(
            {
                "format_version": 1,
                "package_type": "dynamic_agent_design",
                "package_id": "node-agent",
                "entrypoint": "llm",
                "packaging": {"mode": "hybrid_bundle"},
                "nodes": [{"id": "llm", "kind": "llm_step", "prompt_source": "inline"}],
                "edges": [],
            }
        ),
    )

    assert [tool.id for tool in exposed.list_tools_for_node(node)] == ["read_file"]


def test_local_workspace_tool_pack_is_opt_in_and_path_restricted(
    tmp_path: Path,
) -> None:
    workspace_file = tmp_path / "notes.txt"
    workspace_file.write_text("alpha\nbeta\n", encoding="utf-8")
    registry = create_local_workspace_registry([tmp_path])

    assert [tool["function"]["name"] for tool in registry.to_openai_tools()] == [
        "read_file",
        "list_files",
        "search_files",
        "inspect_path",
    ]
    assert (
        registry.invoke_tool("read_file", {"path": "notes.txt"}).output
        == "alpha\nbeta\n"
    )
    assert registry.invoke_tool("list_files", {"path": "."}).output == ["notes.txt"]
    assert registry.invoke_tool(
        "search_files", {"path": ".", "regex": "beta"}
    ).output == [{"path": "notes.txt", "line": 2, "text": "beta"}]
    assert (
        registry.invoke_tool("inspect_path", {"path": "notes.txt"}).output["is_file"]
        is True
    )

    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    blocked = registry.invoke_tool("read_file", {"path": str(outside)})

    assert blocked.success is False
    assert "outside approved workspace roots" in str(blocked.error)
