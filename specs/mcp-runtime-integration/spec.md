# MCP Runtime Integration Specification

## Metadata

- Feature slug: `mcp-runtime-integration`
- Mode: `light`
- Artifact type: future feature specification
- Status: proposed future feature; metadata diagnostics baseline exists, live MCP
  discovery/injection/lifecycle is not implemented
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Related runtime surfaces:
  - `extensions.mcp_registry_sources`
  - `extensions.mcp_lifecycle_diagnostics`
  - tool provenance and portable `tool_type`
  - tool exposure states and registry-authoritative invocation

## Objective

Define future MCP runtime integration that can discover, connect to, cache,
expose, invoke, and clean up tools from configured MCP servers without weakening
the repository-owned tool registry, approval, sandbox, and trace boundaries.

## Existing Baseline

The runtime preserves MCP registry-source metadata and MCP lifecycle diagnostics
metadata. It does not currently launch MCP servers, connect to MCP transports,
discover tool schemas, inject MCP tools into the registry, invoke MCP tools, or
manage MCP server lifecycle.

## Scope

This feature covers:

1. MCP server source configuration
2. transport and lifecycle management
3. tool discovery and schema normalization
4. registry injection and provenance
5. approval and sandbox policy mapping
6. invocation, retry, timeout, cleanup, and reconnect behavior
7. degraded versus strict startup behavior
8. diagnostics and trace events

## Council Roadmap Note

The council review treats live MCP invocation as a high-value follow-up, but not
the first live-action slice. MCP should wait until approval interruption,
sandbox/workspace policy, and capability/status reporting are clear enough that
write, shell, network, browser, and external-mutation MCP tools cannot bypass
policy or appear live when only metadata is preserved.

## Functional Requirements

### FR-1: Configure MCP sources explicitly

MCP servers must come from caller-owned or deployment-owned configuration, not
implicit environment scanning.

Acceptance criteria:

- Given no MCP source configuration, no MCP tools are discovered or injected.
- Given a configured MCP source, the runtime validates source id, transport,
  startup mode, allowed tools, disabled tools, cache policy, and timeout values.
- Given source metadata is present in a generated package, it is treated as
  declarative intent unless the caller or an approved runtime source authorizes
  executable MCP connection details.

### FR-2: Manage MCP lifecycle safely

The runtime must model MCP lifecycle explicitly.

Acceptance criteria:

- Startup can be strict or degraded according to policy.
- Strict startup failure aborts preparation before workflow execution.
- Degraded startup failure records diagnostics and omits unavailable MCP tools.
- Reconnect policy, cleanup timeout, and server shutdown behavior are explicit.
- The runtime never leaves package-owned child processes intentionally unmanaged.

### FR-3: Normalize MCP tools into the repository registry

MCP tools must become registry entries before workflow execution can invoke them.

Acceptance criteria:

- Discovered MCP tool schemas are converted into repository `ToolDefinition`
  objects.
- Tool ids are namespaced or otherwise disambiguated to avoid collisions.
- Tool provenance records source id, server id, tool name, origin `mcp`, and
  adapter metadata separately from portable `tool_type`.
- Unknown or malformed schemas fail closed for strict sources and are omitted
  with diagnostics for degraded sources.

### FR-4: Preserve policy boundaries

MCP tools must not bypass existing exposure, approval, sandbox, or side-effect
policy.

Acceptance criteria:

- MCP tools are hidden by default unless exposed by workflow metadata, registry
  overrides, or caller policy.
- Side-effect, approval, sandbox, and timeout metadata are inferred only from
  trusted source policy or explicit caller configuration, not guessed from tool
  names alone.
- Write, shell, network, browser, or external mutation MCP tools require
  approval-aware policy before invocation.
- Disabled MCP tools cannot be invoked even if a workflow references them.

### FR-5: Invoke MCP tools through registry authority

Runtime execution must call MCP tools through the same registry-authoritative
path used by local tools.

Acceptance criteria:

- `tool_use_step` and model-emitted tool calls resolve to effective registry
  entries before invocation.
- MCP invocation applies registry input validation, timeout policy, retry policy,
  and failure behavior.
- MCP results normalize into `ToolResult` facets: model-facing output, raw
  output, log preview, event payload, and sensitive trace fields.
- MCP transport/protocol failures surface as project-specific errors with source
  diagnostics.

### FR-6: Support diagnostics without memory pollution

MCP lifecycle and invocation diagnostics must be useful but bounded.

Acceptance criteria:

- Diagnostics include active servers, failed servers, discovered tool counts,
  disabled tools, cache status, reconnect attempts, and cleanup failures.
- Diagnostics avoid dumping large schemas, secrets, or full tool outputs into
  model-visible state.
- Trace events identify MCP source id, server id, tool id, lifecycle phase, and
  error category.

## Non-Goals

- No implicit MCP server discovery from local config files in v1.
- No direct executor bypass around the tool registry.
- No assumption that MCP tools are safe because they came from an MCP server.
- No portable workflow storage of secrets, absolute executable paths, or server
  launch credentials.
- No required MCP dependency in core runtime unless the feature is selected.

## Design Constraints

- Keep MCP source configuration runtime/deployment-owned.
- Keep concrete MCP lifecycle schemas downstream-owned unless upstream portable
  runtime-package guidance becomes stable.
- Fail closed for strict sources and high-risk tools.
- Keep source provenance separate from `tool_type`.
- Preserve fake-server unit testing without live external MCP infrastructure.

## NEEDS CLARIFICATION

- Which MCP transports should v1 support: stdio, SSE, streamable HTTP, or a
  caller-provided client abstraction only?
- Should the runtime launch MCP server processes or only consume already-running
  clients?
- What is the exact source configuration format?
- How should tool id namespacing and collision resolution work?
- What cache policy is acceptable for discovered schemas?
- Which MCP errors are retryable?
- How should credentials and environment variables be supplied to MCP clients?
- Should degraded MCP sources allow workflow execution when a required tool is
  missing?
- How should MCP progress/log messages map to trace events?
- What approval defaults apply to MCP tools whose side effects are unknown?

## Validation Checklist

- [ ] No MCP tools are exposed without explicit source configuration.
- [ ] Strict source startup failure aborts preparation.
- [ ] Degraded source startup failure records diagnostics and omits tools.
- [ ] Discovered tool schemas become registry definitions with MCP provenance.
- [ ] Disabled or hidden MCP tools cannot be invoked.
- [ ] MCP invocation uses registry validation, timeout, retry, and result facets.
- [ ] Diagnostics are bounded and redacted.
