"""Tests for explicit MCP registry injection helpers."""

from __future__ import annotations

from dynamic_agent_runner.registry import ToolResult


def test_mcp_registry_injection_contract_is_exported() -> None:
    import dynamic_agent_runner

    assert dynamic_agent_runner.MCPToolBinding is not None
    assert dynamic_agent_runner.registered_tool_from_mcp_binding is not None
    assert dynamic_agent_runner.create_mcp_registry is not None


def test_registered_tool_from_mcp_binding_builds_callable_tool() -> None:
    from dynamic_agent_runner import MCPToolBinding, registered_tool_from_mcp_binding

    binding = MCPToolBinding(
        tool_id="mcp.search",
        source_id="repo-tools",
        server_id="repo-mcp",
        mcp_tool_name="search",
        handler=lambda args: {"query": args["query"]},
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )

    tool = registered_tool_from_mcp_binding(binding)

    assert tool.id == "mcp.search"
    assert tool.handler({"query": "agents"}) == {"query": "agents"}


def test_create_mcp_registry_builds_registry_from_explicit_bindings() -> None:
    from dynamic_agent_runner import MCPToolBinding, create_mcp_registry

    registry = create_mcp_registry(
        [
            MCPToolBinding(
                tool_id="mcp.echo",
                source_id="repo-tools",
                server_id="repo-mcp",
                mcp_tool_name="echo",
                handler=lambda args: ToolResult(
                    tool_id="mcp.echo",
                    success=True,
                    output={"echo": args["text"]},
                ),
                input_schema={
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            )
        ]
    )

    result = registry.invoke_tool("mcp.echo", {"text": "hello"})

    assert result.success is True
    assert result.output == {"echo": "hello"}
