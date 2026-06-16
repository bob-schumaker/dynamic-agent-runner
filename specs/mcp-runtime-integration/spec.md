# MCP Runtime Integration Specification

## Metadata

- Feature slug: `mcp-runtime-integration`
- Mode: `light`
- Artifact type: authoritative SDD feature specification
- Status: implemented v1 explicit registry-injection baseline; live transports
  and lifecycle remain deferred
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Related runtime surfaces:
  - `extensions.mcp_registry_sources`
  - `extensions.mcp_lifecycle_diagnostics`
  - tool provenance and portable `tool_type`
  - tool exposure states and registry-authoritative invocation

## Objective

Define MCP runtime integration that can expose explicitly supplied MCP tool
registries now and later discover, connect to, cache, invoke, and clean up tools
from configured MCP servers without weakening the repository-owned tool
registry, approval, sandbox, and trace boundaries.

## Existing Baseline

The runtime preserves MCP registry-source metadata, MCP lifecycle diagnostics
metadata, and v1 caller-supplied MCP registry injection. It does not currently
launch MCP servers, connect to MCP transports, discover tool schemas, or manage
MCP server lifecycle.

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

## V1 Slice Boundary

The first MCP implementation slice does not launch servers, open transports,
scan local config, or invoke live MCP infrastructure. It adds a repository-owned
normalization layer for caller-supplied MCP tool descriptors and handlers so MCP
tools enter execution only through the existing `ToolRegistry`.

V1 includes:

- public MCP tool source/config dataclasses
- conversion of caller-supplied MCP tool descriptors into `RegisteredTool`
  instances
- MCP provenance with origin `mcp`
- conservative default exposure and policy metadata
- optional registry construction from explicit MCP tool bindings
- capability status that distinguishes metadata-only MCP declarations from live
  caller-supplied MCP registry entries

V1 defers:

- stdio, SSE, streamable HTTP, or other transports
- process launch and cleanup
- schema discovery from a live server
- reconnect, cache refresh, and lifecycle diagnostics beyond metadata
- live MCP progress/log event mapping

## Implementation Status

- Implemented `MCPToolBinding`.
- Implemented `registered_tool_from_mcp_binding(...)`.
- Implemented `create_mcp_registry(...)`.
- Implemented MCP-origin tool provenance using existing `ToolSource` metadata.
- Implemented conservative hidden and approval-required defaults, with trusted
  caller metadata overrides.
- Implemented capability-status reporting for live MCP-origin registry entries.
- Deferred transports, process lifecycle, live discovery, schema caching,
  reconnect, cleanup, and MCP progress/log events.

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

## Future Work

Lanham's `AI Agents in Action, Second Edition` reinforces that MCP can expose
more than tools. Future approved slices may add:

- MCP `resources` as bounded, provenance-bearing read context that can feed
  `context-management-prepare-stage` without bypassing file/context policies
- MCP `prompts` as explicit host-provided prompt templates or prompt fragments,
  subject to hierarchy, trust, and redaction policy
- MCP progress/log event mapping into package trace events
- lifecycle handling for local, remote, and hybrid MCP transports
- degraded-source policy for required vs optional MCP capabilities

Those slices must preserve the v1 boundary: explicit caller/deployment
configuration, registry authority for actions, conservative exposure defaults,
and fake-server unit tests.

## NEEDS CLARIFICATION

- RESOLVED for v1: support caller-provided descriptors/handlers only; no
  transport implementation.
- RESOLVED for v1: do not launch MCP server processes.
- RESOLVED for v1: source configuration is an explicit Python API, not package
  metadata or environment discovery.
- RESOLVED for v1: callers must provide final tool ids; duplicate ids fail
  through existing registry behavior.
- RESOLVED for v1: no schema cache is implemented because schemas are
  caller-supplied.
- Which MCP errors are retryable?
- How should credentials and environment variables be supplied to MCP clients?
- Should degraded MCP sources allow workflow execution when a required tool is
  missing?
- How should MCP progress/log messages map to trace events?
- RESOLVED for v1: MCP tools default to hidden exposure and approval required
  unless the caller supplies more specific trusted policy metadata.

## Validation Checklist

- [x] No MCP tools are exposed without explicit source configuration.
- [ ] Strict source startup failure aborts preparation.
- [ ] Degraded source startup failure records diagnostics and omits tools.
- [x] Caller-supplied tool schemas become registry definitions with MCP
      provenance.
- [x] Disabled or hidden MCP tools cannot be model-exposed.
- [x] MCP invocation uses registry validation and result facets.
- [ ] Diagnostics are bounded and redacted.
