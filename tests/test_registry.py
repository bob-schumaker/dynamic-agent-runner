"""Tests for the repository-owned dynamic-agent tool registry."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import pytest

from dynamic_agent_runner.artifacts import load_runtime_manifest, load_tool_index
from dynamic_agent_runner.errors import ToolRegistryError
from dynamic_agent_runner.models import (
    RuntimeNode,
    ToolDefinition,
    ToolExposure,
    ToolOriginKind,
    ToolSource,
    ToolSourceKind,
    ToolType,
)
from dynamic_agent_runner.registry import (
    InMemoryToolRegistry,
    RegisteredTool,
    ToolResult,
    WebToolPolicy,
    WorkspaceDataToolPolicy,
    ToolExposureOverride,
    ToolRegistryOverrides,
    create_web_registry,
    create_local_workspace_registry,
    create_workspace_data_registry,
    openai_tool_schema,
    tool_from_function,
    validate_registry_tool_references,
)


def make_tool(
    tool_id: str,
    output: object | None = None,
    *,
    exposure: str = "direct",
) -> RegisteredTool:
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
        "exposure": exposure,
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
    assert registry.get_tool("search_repo").definition.source == ToolSource(
        kind=ToolSourceKind.CALLER_REGISTERED,
        origin=ToolOriginKind.REGISTERED,
    )
    schema = registry.to_openai_tools(["search_repo"])
    assert schema == [openai_tool_schema(registry.get_tool("search_repo").definition)]
    assert schema[0]["name"] == "search_repo"

    result = registry.invoke_tool("search_repo", {"query": "agents"})

    assert result.success is True
    assert result.output == {"query": "agents"}


def test_registered_tool_records_callable_shape() -> None:
    async def async_handler(_args: object) -> object:
        return {"ok": True}

    sync_tool = make_tool("sync_tool")
    async_tool = RegisteredTool(
        ToolDefinition.from_mapping(
            {"id": "async_tool", "input_schema": {"type": "object"}}
        ),
        async_handler,
    )

    assert sync_tool.handler_is_async is False
    assert async_tool.handler_is_async is True


def test_registry_awaits_async_tool_handlers() -> None:
    async def handler(args: object) -> ToolResult:
        return ToolResult(
            tool_id="async_lookup",
            success=True,
            output={"raw": args},
            model_output={"summary": "awaited"},
        )

    registry = InMemoryToolRegistry(
        [
            RegisteredTool(
                ToolDefinition.from_mapping(
                    {
                        "id": "async_lookup",
                        "input_schema": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                            "required": ["query"],
                        },
                    }
                ),
                handler,
            )
        ]
    )

    result = asyncio.run(registry.invoke_tool_async("async_lookup", {"query": "x"}))

    assert result.success is True
    assert result.model_facing_output == {"summary": "awaited"}


def test_registry_runs_sync_tool_handlers_through_async_boundary() -> None:
    event_loop_thread_id = threading.get_ident()
    handler_thread_ids: list[int] = []

    def handler(args: object) -> object:
        handler_thread_ids.append(threading.get_ident())
        return {"query": args["query"]}

    registry = InMemoryToolRegistry(
        [
            RegisteredTool(
                ToolDefinition.from_mapping(
                    {
                        "id": "sync_lookup",
                        "input_schema": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                            "required": ["query"],
                        },
                    }
                ),
                handler,
            )
        ]
    )

    result = asyncio.run(registry.invoke_tool_async("sync_lookup", {"query": "x"}))

    assert result.success is True
    assert result.output == {"query": "x"}
    assert handler_thread_ids
    assert handler_thread_ids[0] != event_loop_thread_id


def test_registry_async_invocation_converts_handler_exceptions() -> None:
    async def handler(_args: object) -> object:
        raise RuntimeError("async boom")

    registry = InMemoryToolRegistry(
        [
            RegisteredTool(
                ToolDefinition.from_mapping(
                    {"id": "async_failure", "input_schema": {"type": "object"}}
                ),
                handler,
            )
        ]
    )

    result = asyncio.run(registry.invoke_tool_async("async_failure", {}))

    assert result.success is False
    assert result.error == "async boom"


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


def test_registry_preserves_structured_tool_result_facets() -> None:
    expected = ToolResult(
        tool_id="facet_tool",
        success=True,
        output={"raw": "full"},
        model_output={"summary": "safe"},
        raw_output={"raw": "full"},
        log_preview="safe preview",
        event_payload={"record_count": 1},
        sensitive_fields=("raw_output",),
    )
    registry = InMemoryToolRegistry(
        [
            RegisteredTool(
                ToolDefinition.from_mapping(
                    {
                        "id": "facet_tool",
                        "input_schema": {"type": "object", "properties": {}},
                    }
                ),
                lambda _args: expected,
            )
        ]
    )

    result = registry.invoke_tool("facet_tool", {})

    assert result == expected
    assert result.model_output == {"summary": "safe"}
    assert result.raw_output == {"raw": "full"}
    assert result.log_preview == "safe preview"
    assert result.event_payload == {"record_count": 1}
    assert result.sensitive_fields == ("raw_output",)


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

    assert schema["parameters"] == {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }


def test_tool_definition_separates_exposure_and_policy_metadata() -> None:
    definition = ToolDefinition.from_mapping(
        {
            "id": "review_notebook",
            "label": "Review notebook",
            "exposure": "hidden",
            "side_effect": "write",
            "approval_required": "yes",
            "sandbox": "workspace",
            "timeout": "short",
            "retry_policy": "none",
            "failure_behavior": "error",
        }
    )

    assert definition.exposure is ToolExposure.HIDDEN
    assert definition.side_effect == "write"
    assert definition.approval_required == "yes"
    assert definition.policy.side_effect == "write"
    assert definition.policy.approval_required == "yes"
    assert definition.policy.sandbox == "workspace"
    assert definition.policy.timeout == "short"
    assert definition.policy.retry_policy == "none"
    assert definition.policy.failure_behavior == "error"


def test_tool_definition_records_manifest_and_index_source_metadata() -> None:
    manifest = manifest_with_tool("manifest_tool")
    index = load_tool_index(
        {
            "format_version": 1,
            "index_type": "tool_index",
            "index_id": "shared-tools",
            "tools": [{"id": "indexed_tool", "adapter": "runtime.indexed_tool"}],
        }
    )

    assert manifest.tools[0].source == ToolSource(
        kind=ToolSourceKind.MANIFEST,
        origin=ToolOriginKind.REGISTERED,
        source_id="registry-agent",
        detail="tools",
    )
    assert index is not None
    assert index.tools[0].source == ToolSource(
        kind=ToolSourceKind.TOOL_INDEX,
        origin=ToolOriginKind.REGISTERED,
        source_id="shared-tools",
        detail="tools",
    )


def test_tool_definition_preserves_portable_tool_type_metadata() -> None:
    definition = ToolDefinition.from_mapping(
        {
            "id": "workspace_search",
            "tool_type": "file_read",
            "adapter": "runtime.search_files",
        }
    )

    assert definition.tool_type is ToolType.FILE_READ


def test_registry_validates_callable_tool_references_not_metadata_only() -> None:
    manifest = manifest_with_tool("metadata_only")
    registry = InMemoryToolRegistry([])

    with pytest.raises(ToolRegistryError, match="unavailable registry tool"):
        validate_registry_tool_references(manifest, registry)

    validate_registry_tool_references(
        manifest,
        InMemoryToolRegistry([make_tool("metadata_only")]),
    )


def test_registry_rejects_model_only_tools_for_direct_tool_steps() -> None:
    manifest = manifest_with_tool("model_only_tool")
    registry = InMemoryToolRegistry(
        [make_tool("model_only_tool", exposure="direct_model_only")]
    )

    with pytest.raises(ToolRegistryError, match="not callable for direct execution"):
        validate_registry_tool_references(manifest, registry)


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
    assert registry.get_tool("read_file").definition.source == ToolSource(
        kind=ToolSourceKind.RUNTIME_OVERRIDE,
        origin=ToolOriginKind.OVERRIDE,
        source_id="added",
        detail="tool_registry_overrides",
    )
    assert registry.get_tool("search_repo").definition.source == ToolSource(
        kind=ToolSourceKind.RUNTIME_OVERRIDE,
        origin=ToolOriginKind.OVERRIDE,
        source_id="replacement",
        detail="tool_registry_overrides",
    )

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


def test_tool_exposure_states_control_model_visibility_and_invocation() -> None:
    registry = InMemoryToolRegistry(
        [
            make_tool("direct_tool", exposure="direct"),
            make_tool("deferred_tool", exposure="deferred"),
            make_tool("model_only_tool", exposure="direct_model_only"),
            make_tool("hidden_tool", exposure="hidden"),
        ]
    )
    node = RuntimeNode.from_mapping(
        {
            "id": "llm",
            "kind": "llm_step",
            "prompt_source": "inline",
            "available_tools": [
                "direct_tool",
                "deferred_tool",
                "model_only_tool",
                "hidden_tool",
            ],
        }
    )

    assert [tool.id for tool in registry.list_tools_for_node(node)] == [
        "direct_tool",
        "model_only_tool",
    ]
    assert registry.to_openai_tools(["model_only_tool"])[0]["name"] == (
        "model_only_tool"
    )
    assert [tool["name"] for tool in registry.to_openai_tools()] == [
        "direct_tool",
        "model_only_tool",
    ]
    with pytest.raises(ToolRegistryError, match="not model-exposable"):
        registry.to_openai_tools(["hidden_tool"])
    blocked = registry.invoke_tool("model_only_tool", {"query": "x"})
    internal = registry.invoke_tool("hidden_tool", {"query": "x"})

    assert blocked.success is False
    assert "not callable for direct execution" in str(blocked.error)
    assert internal.success is True


def test_unknown_tool_exposure_fails_closed() -> None:
    registry = InMemoryToolRegistry([make_tool("bad", exposure="surprise")])
    node = RuntimeNode.from_mapping(
        {
            "id": "llm",
            "kind": "llm_step",
            "prompt_source": "inline",
            "available_tools": ["bad"],
        }
    )

    with pytest.raises(ToolRegistryError, match="unsupported exposure"):
        registry.list_tools_for_node(node)


def test_local_workspace_tool_pack_is_opt_in_and_path_restricted(
    tmp_path: Path,
) -> None:
    workspace_file = tmp_path / "notes.txt"
    workspace_file.write_text("alpha\nbeta\n", encoding="utf-8")
    registry = create_local_workspace_registry([tmp_path])

    assert registry.get_tool("read_file").definition.source == ToolSource(
        kind=ToolSourceKind.BUILT_IN,
        origin=ToolOriginKind.BUILT_IN,
        source_id="local_workspace",
        detail="read_file",
    )
    assert registry.get_tool("read_file").definition.tool_type is ToolType.FILE_READ
    assert registry.get_tool("list_files").definition.tool_type is ToolType.FILE_READ
    assert registry.get_tool("search_files").definition.tool_type is ToolType.FILE_READ
    assert registry.get_tool("inspect_path").definition.tool_type is ToolType.FILE_READ
    assert [tool["name"] for tool in registry.to_openai_tools()] == [
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


class FakeSearchClient:
    def search(self, query: str, *, limit: int) -> list[dict[str, object]]:
        return [
            {
                "title": "Result",
                "url": "https://example.com/result",
                "snippet": f"Found {query}",
                "extra": "ignored",
            }
        ][:limit]


class FakeFetchClient:
    def fetch(self, url: str) -> dict[str, object]:
        return {
            "url": url,
            "status": 200,
            "content_type": "text/html",
            "title": "Fetched",
            "text": "abcdef",
            "raw": "ignored",
        }


def test_web_tool_pack_uses_fake_clients_and_normalizes_results() -> None:
    registry = create_web_registry(
        search_client=FakeSearchClient(),
        fetch_client=FakeFetchClient(),
        policy=WebToolPolicy(
            allowed_domains=("example.com",),
            max_search_results=3,
            max_fetch_chars=4,
        ),
    )

    assert registry.get_tool("web_search").definition.tool_type is ToolType.WEB_SEARCH
    assert registry.get_tool("web_fetch").definition.tool_type is ToolType.WEB_FETCH
    assert [tool["name"] for tool in registry.to_openai_tools()] == [
        "web_search",
        "web_fetch",
    ]

    search = registry.invoke_tool("web_search", {"query": "agents"})
    fetch = registry.invoke_tool("web_fetch", {"url": "https://example.com/page"})

    assert search.success is True
    assert search.output == {
        "query": "agents",
        "results": [
            {
                "rank": 1,
                "title": "Result",
                "url": "https://example.com/result",
                "snippet": "Found agents",
            }
        ],
    }
    assert fetch.success is True
    assert fetch.output == {
        "url": "https://example.com/page",
        "status": 200,
        "content_type": "text/html",
        "title": "Fetched",
        "text": "abcd",
        "truncated": True,
    }


def test_web_tool_pack_rejects_disallowed_urls() -> None:
    registry = create_web_registry(
        search_client=FakeSearchClient(),
        fetch_client=FakeFetchClient(),
        policy=WebToolPolicy(allowed_domains=("example.com",)),
    )

    blocked = registry.invoke_tool("web_fetch", {"url": "http://evil.test/page"})

    assert blocked.success is False
    assert "scheme 'http' is not allowed" in str(blocked.error)


def test_web_tool_pack_requires_injected_clients() -> None:
    with pytest.raises(ToolRegistryError, match="requires search_client"):
        create_web_registry(fetch_client=FakeFetchClient())

    with pytest.raises(ToolRegistryError, match="requires fetch_client"):
        create_web_registry(search_client=FakeSearchClient())


class FakeWorkspaceDataStore:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, object]] = {}

    def write(self, item: dict[str, object]) -> dict[str, object]:
        item_id = str(item.get("id") or f"item-{len(self.items) + 1}")
        stored = {"id": item_id, **item}
        self.items[item_id] = stored
        return stored

    def read(self, item_id: str) -> dict[str, object] | None:
        return self.items.get(item_id)

    def search(self, query: str, *, limit: int) -> list[dict[str, object]]:
        del query
        return list(self.items.values())[:limit]

    def list(self, *, limit: int) -> list[dict[str, object]]:
        return list(self.items.values())[:limit]

    def delete(self, item_id: str) -> bool:
        return self.items.pop(item_id, None) is not None


def test_workspace_data_tool_pack_writes_reads_and_lists_metadata_first() -> None:
    store = FakeWorkspaceDataStore()
    registry = create_workspace_data_registry(
        store=store,
        policy=WorkspaceDataToolPolicy(default_search_limit=5),
    )

    assert (
        registry.get_tool("workspace_data_write").definition.tool_type
        is ToolType.STRUCTURED_DATA_QUERY
    )
    assert [tool["name"] for tool in registry.to_openai_tools()] == [
        "workspace_data_write",
        "workspace_data_read",
        "workspace_data_search",
        "workspace_data_list",
        "workspace_data_delete",
    ]

    write = registry.invoke_tool(
        "workspace_data_write",
        {
            "id": "note-1",
            "kind": "note",
            "title": "Finding",
            "tags": ["agent"],
            "data": {"body": "large result"},
        },
    )
    read = registry.invoke_tool("workspace_data_read", {"id": "note-1"})
    listing = registry.invoke_tool("workspace_data_list", {})

    assert write.success is True
    assert write.output["status"] == "ok"
    assert write.output["item"]["id"] == "note-1"
    assert read.output["item"]["data"] == {"body": "large result"}
    assert listing.output == {
        "status": "ok",
        "items": [
            {
                "id": "note-1",
                "kind": "note",
                "title": "Finding",
                "tags": ["agent"],
            }
        ],
    }


def test_workspace_data_tool_pack_search_can_include_data_and_delete() -> None:
    store = FakeWorkspaceDataStore()
    registry = create_workspace_data_registry(
        store=store,
        policy=WorkspaceDataToolPolicy(require_delete_approval=False),
    )
    registry.invoke_tool(
        "workspace_data_write",
        {"id": "note-1", "title": "Finding", "data": {"body": "kept"}},
    )

    search = registry.invoke_tool(
        "workspace_data_search", {"query": "Finding", "include_data": True}
    )
    delete = registry.invoke_tool("workspace_data_delete", {"id": "note-1"})
    missing = registry.invoke_tool("workspace_data_read", {"id": "note-1"})

    assert search.output["items"][0]["data"] == {"body": "kept"}
    assert delete.output == {"status": "deleted", "id": "note-1"}
    assert missing.output == {
        "status": "not_found",
        "id": "note-1",
        "next_steps": ["write the item before reading it"],
    }


def test_workspace_data_tool_pack_rejects_missing_store_and_oversized_payload() -> None:
    with pytest.raises(ToolRegistryError, match="requires store"):
        create_workspace_data_registry()

    registry = create_workspace_data_registry(
        store=FakeWorkspaceDataStore(),
        policy=WorkspaceDataToolPolicy(max_item_bytes=10),
    )

    blocked = registry.invoke_tool(
        "workspace_data_write",
        {"id": "too-large", "data": {"text": "this is too large"}},
    )

    assert blocked.success is False
    assert "exceeds max_item_bytes" in str(blocked.error)


def test_tool_source_defaults_origin_from_existing_kind_values() -> None:
    caller = ToolSource.from_mapping({"kind": "caller_registered"})
    built_in = ToolSource.from_mapping({"kind": "built_in"})
    override = ToolSource.from_mapping({"kind": "runtime_override"})

    assert caller.origin is ToolOriginKind.REGISTERED
    assert built_in.origin is ToolOriginKind.BUILT_IN
    assert override.origin is ToolOriginKind.OVERRIDE


def test_tool_source_preserves_explicit_future_origin_values() -> None:
    mcp_source = ToolSource.from_mapping(
        {
            "kind": "tool_index",
            "origin": "mcp",
            "source_id": "demo-server",
            "detail": "search_files",
        }
    )
    agent_source = ToolSource.from_mapping(
        {
            "kind": "caller_registered",
            "origin": "agent_as_tool",
            "source_id": "marimo-pair",
        }
    )

    assert mcp_source.origin is ToolOriginKind.MCP
    assert mcp_source.to_mapping()["origin"] == "mcp"
    assert agent_source.origin is ToolOriginKind.AGENT_AS_TOOL
    assert agent_source.to_mapping()["origin"] == "agent_as_tool"


def test_tool_from_function_infers_metadata_and_invokes_handler() -> None:
    def search_repo(query: str, limit: int = 5) -> dict[str, object]:
        """Search repository content."""

        return {"query": query, "limit": limit}

    tool = tool_from_function(search_repo)
    registry = InMemoryToolRegistry([tool])

    assert tool.definition.id == "search_repo"
    assert tool.definition.label == "Search Repo"
    assert tool.definition.raw["description_for_llm"] == "Search repository content."
    assert tool.definition.raw["input_schema"] == {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer"},
        },
        "required": ["query"],
    }
    assert registry.invoke_tool("search_repo", {"query": "agents"}).output == {
        "query": "agents",
        "limit": 5,
    }


def test_tool_from_function_merges_partial_metadata_with_inference() -> None:
    def review_notebook(path: str, include_outputs: bool = False) -> dict[str, object]:
        """Review a notebook file."""

        return {"path": path, "include_outputs": include_outputs}

    tool = tool_from_function(
        review_notebook,
        metadata={
            "label": "Notebook reviewer",
            "side_effect": "read",
            "approval_required": "no",
            "input_schema": {
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Repository-relative notebook path.",
                    }
                }
            },
        },
    )

    assert tool.definition.id == "review_notebook"
    assert tool.definition.label == "Notebook reviewer"
    assert tool.definition.side_effect == "read"
    assert tool.definition.raw["description_for_llm"] == "Review a notebook file."
    assert tool.definition.raw["input_schema"] == {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Repository-relative notebook path.",
            },
            "include_outputs": {"type": "boolean"},
        },
        "required": ["path"],
    }


def test_tool_from_function_requires_supported_signature_shapes() -> None:
    def invalid_tool(*args: object) -> None:
        return None

    with pytest.raises(ToolRegistryError, match="only supports positional-or-keyword"):
        tool_from_function(invalid_tool)


def test_tool_from_function_requires_explicit_id_for_lambda() -> None:
    with pytest.raises(ToolRegistryError, match="could not infer a stable tool id"):
        tool_from_function(lambda query: query)
