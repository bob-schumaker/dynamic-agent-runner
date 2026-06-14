# MCP Runtime Integration V1 Plan

## Objective

Add the first policy-bound MCP runtime seam without launching MCP servers or
opening transports. V1 turns caller-supplied MCP tool descriptors and handlers
into repository `RegisteredTool` entries with MCP provenance and conservative
policy defaults.

## Scope

- Add public MCP source/tool binding dataclasses.
- Convert explicit MCP tool bindings into `RegisteredTool` instances.
- Preserve source id, server id, and MCP tool name in provenance metadata.
- Default MCP tools to hidden exposure and approval-required policy unless the
  caller supplies trusted metadata.
- Build an `InMemoryToolRegistry` from explicit MCP bindings.
- Report live MCP registry entries in capability status when callers provide a
  registry containing MCP-origin tools.

## Non-Goals

- No MCP transport implementation.
- No process launch, cleanup, reconnect, or schema cache.
- No implicit discovery from user config files.
- No live MCP network, stdio, SSE, or streamable HTTP calls in tests.
- No executor bypass around `ToolRegistry`.

## Design

Create a small `dynamic_agent_runner.mcp` module that owns MCP-specific
normalization. It should produce existing registry primitives instead of adding
a parallel invocation path.

The v1 API can expose:

- `MCPToolBinding`
- `registered_tool_from_mcp_binding(...)`
- `create_mcp_registry(...)`

The binding should contain final `tool_id`, `source_id`, `server_id`,
`mcp_tool_name`, optional description/schema/policy metadata, and a Python
handler. The resulting `ToolDefinition.source` should use MCP origin metadata
and the registered tool should invoke through existing registry validation,
retry, timeout, tracing, and approval behavior.

## Validation Strategy

- RED import/shape tests for the MCP public contract.
- GREEN tests for MCP provenance and conservative default policy.
- Registry tests proving duplicate ids still fail through existing registry
  behavior and invocation uses existing `InMemoryToolRegistry`.
- Capability-status tests proving metadata-only MCP declarations remain distinct
  from live MCP-origin registry entries.
