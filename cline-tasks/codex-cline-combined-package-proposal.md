# Codex/Cline combined package proposal for `dynamic-agent-runner`

<!-- markdownlint-disable MD013 -->

## Goal

Synthesize the read-only evaluations in:

- `cline-tasks/codex-cli-evaluation.md`
- `cline-tasks/cline-evaluation.md`

into one proposal for acceptable additions to `dynamic-agent-runner`.

## Proposal principles

Accept additions only when they meet these constraints:

1. Preserve the current primitive graph executor: keep `llm_step`,
   `tool_use_step`, and `decision_step` as the core execution taxonomy.
2. Keep the executor small: session, MCP, hooks, compaction, and policy concerns
   should live in separate modules rather than accumulating in `executor.py`.
3. Keep OpenAI-first semantics: no LiteLLM/provider gateway unless the spec
   changes.
4. Keep tools explicit and registry-owned: metadata, exposure, callable
   availability, approval, and sandbox policy should remain separate dimensions.
5. Add package-owned contracts before integrations: define internal
   models/interfaces before adding plugin systems, MCP runtime, external
   observability, or command tools.
6. Fail closed, especially for schema validation, unsupported policies,
   write/command tools, prompt/source loading, and MCP/plugin loading.

## Recommended acceptable additions, in priority order

### 1. Introduce `WorkflowExecutionContext` / `RunContext`

Both evaluations recommend separating the runtime envelope from mutable
`WorkflowExecutionState`.

Likely module:

```text
src/dynamic_agent_runner/context.py
```

Candidate fields:

- loaded workflow/package
- model adapter
- tool registry
- tracer / trace sink
- max steps
- prompt-cache override
- token-budget defaults
- model capabilities
- tool policy / approval policy placeholders
- environment roots / workspace roots
- behavior overrides

This is acceptable because it directly supports current implemented features and
reduces parameter sprawl without changing runtime behavior.

Scope boundary: this should be a refactor/contract addition, not a new session
manager or app-server abstraction.

### 2. Add a structured `ModelCapabilities` layer

Codex recommends model metadata-driven behavior, and Cline's layered runtime
supports keeping provider/model concerns distinct.

Candidate fields:

```python
@dataclass(frozen=True)
class ModelCapabilities:
    context_window: int | None = None
    effective_context_window_percent: int = 95
    supports_parallel_tool_calls: bool = False
    supports_structured_outputs: bool = True
    supports_reasoning: bool = False
    input_modalities: tuple[str, ...] = ("text",)
```

This is acceptable because the package already has token budgeting,
prompt-cache intent, structured-output validation, and OpenAI request
construction. Capabilities centralize assumptions that would otherwise spread
across features.

Scope boundary: do not turn this into multi-provider routing.

### 3. Strengthen tool schema validation

Enhance `src/dynamic_agent_runner/registry.py` validation so exposed
OpenAI-compatible function tools fail early when schemas are malformed.

Recommended checks:

- `input_schema` must be a mapping.
- Top-level schema should be object-shaped.
- Infer or require `type: object` when `properties` / `required` are present.
- Reject top-level `oneOf` / `anyOf` / `allOf` unless explicitly object-shaped
  and intentionally supported.
- Strip or ignore `$schema` in model-facing OpenAI tool schema output.
- Produce clear `ToolRegistryError` diagnostics.

This is acceptable because it improves current package reliability and aligns
with the existing fail-closed registry direction.

### 4. Add explicit tool exposure states

Add an exposure concept separate from whether a tool exists, is callable, or is
approved.

Candidate enum:

```python
class ToolExposure(str, Enum):
    DIRECT = "direct"
    DEFERRED = "deferred"
    DIRECT_MODEL_ONLY = "direct_model_only"
    HIDDEN = "hidden"
```

Candidate manifest/override vocabulary:

```yaml
tools:
  - id: search_repo
    exposure: direct
  - id: expensive_deep_search
    exposure: deferred
  - id: internal_audit_sink
    exposure: hidden
```

This is acceptable because current package semantics already support per-node
exposure and runtime tool overrides. This addition makes “registered but not
immediately model-visible” first class.

Scope boundary: `deferred` should initially be metadata only unless a later
slice defines executor behavior for lazy discovery/loading.

### 5. Separate tool catalog, callable registry, exposure, and policy

The package already distinguishes metadata-only tool-index entries from callable
registry entries. A next refinement should make this separation clearer in public
models and docs:

- catalog metadata: what a tool is and how it should be described
- callable registry: what can actually be invoked
- node exposure: what a specific `llm_step` may show the model
- approval/safety policy: what requires permission or is disabled
- sandbox/side-effect policy: what the tool is allowed to affect

This is acceptable because it is needed before write tools, command tools, MCP
tools, or plugin-provided tools.

Scope boundary: do not add broad write/command packs yet.

### 6. Split `ToolResult` into clearer output facets

Refine `ToolResult` so model-output needs are not conflated with observability
or hook/event needs.

Possible fields:

```python
@dataclass(frozen=True)
class ToolResult:
    model_output: Any
    raw_output: Any | None = None
    success: bool = True
    log_preview: str | None = None
    event_payload: Mapping[str, Any] | None = None
    sensitive_fields: tuple[str, ...] = ()
```

This is acceptable because tracing and redaction already exist.

Scope boundary: preserve backward compatibility if `ToolResult` is already
public.

### 7. Add narrow in-process lifecycle hooks

Add Python hook protocols around stable lifecycle points:

```python
class WorkflowHooks(Protocol):
    def before_node(self, context: NodeHookContext) -> NodeControl | None: ...
    def before_model(self, context: ModelHookContext) -> ModelControl | None: ...
    def after_model(self, context: ModelResultHookContext) -> None: ...
    def before_tool(self, context: ToolHookContext) -> ToolControl | None: ...
    def after_tool(self, context: ToolResultHookContext) -> ToolResultControl | None: ...
    def after_workflow(self, context: WorkflowResultHookContext) -> None: ...
```

Initial controls should be deliberately narrow:

- stop execution with a structured reason
- mutate model options/messages only if explicitly supported
- mutate tool input only if explicitly supported
- skip/replace tool result only if explicitly supported

This is acceptable because it creates useful extension seams without plugin
imports or shell hooks.

Scope boundary: no arbitrary shell hook execution, no plugin loader, and no
untrusted hook sources.

### 8. Extend trace vocabulary for tool lifecycle and status notices

Current tracing already covers core workflow events. Acceptable additions:

- `tool_started`
- `tool_updated`
- `tool_finished`
- `usage_updated`
- `status_notice`
- `permission_requested` if approval policy is added
- `context_prepared` / `context_management_checked` for future compaction

This is acceptable because it builds on existing package-owned tracing and
avoids stdout scraping.

Scope boundary: streaming assistant deltas should wait until interactive or
streaming mode is scoped.

### 9. Draft MCP as a registry-source design, not runtime implementation yet

Create a design/spec addition before implementation. Candidate concepts:

- `McpRegistrySource`
- `McpServerRegistration`
- `McpToolDescriptor`
- `McpToolCachePolicy`
- `McpToolNameTransform`
- server status trace events
- origin/provenance metadata
- disabled state and last error
- tool cache TTL
- serialized per-server operations
- model visibility metadata
- memory-pollution metadata
- parallel-tool-call support metadata

This is acceptable because MCP fits the package's future
`tool-server-or-mcp-style-agent` pattern, but should enter through the
registry-source boundary.

Scope boundary: do not add live MCP support until requirements define transport,
auth, approval, caching, and failure behavior.

### 10. Add a context-management prepare stage before compaction

Preserve current “automatic truncation unsupported” behavior, but add a seam for
future policies:

```yaml
execution_policy:
  context_management:
    on_exceed: error # future: compact
    strategy: none   # future: basic_summary
    threshold_ratio: 0.8
    reserve_tokens: 2000
```

This is acceptable because token budgeting already exists and a prepare stage
gives compaction a correct home later.

Scope boundary: no summarizing compaction yet unless separately specified; no
hidden truncation inside `OpenAIClientAdapter`.

### 11. Constrain any file-backed hierarchical prompt context

Accept only if implemented with:

- explicit roots
- bounded scan depth
- byte/token budget
- source path provenance
- deterministic ordering
- caller opt-in
- no arbitrary recursive prompt ingestion

This is acceptable as a future project-context injection design.

Scope boundary: do not implicitly read arbitrary `SKILL.md` files or local
instruction files.

### 12. Represent sub-agent delegation as a tool pattern, not a new primitive node

If needed, model simple delegation as:

- an ordinary `tool_use_step`,
- model-visible `spawn_agent` tool metadata, or
- a workflow pattern compiled into existing primitive nodes.

This is acceptable because it preserves the package's primitive executor
taxonomy.

Scope boundary: no durable team runtime yet; no `multi_agent_step` node kind.

## Additions to defer or reject for now

These are not acceptable as near-term package additions unless the spec changes:

- full Codex Rust architecture
- full Cline TypeScript package/runtime stack
- multi-provider gateway / LiteLLM
- hub/RPC server or app-server runtime
- interactive TUI/IDE runtime concerns
- durable multi-agent team runtime with mailboxes and recovered runs
- cron/scheduled automation service in core
- plugin import/sandbox system
- arbitrary `SKILL.md` source loading
- arbitrary shell hooks
- full sandbox/exec-policy engine before command tools are in scope
- write or command tool packs enabled by default
- memory extraction/consolidation pipeline before durable memory requirements
  exist
- automatic compaction/truncation hidden inside model calls

## Suggested combined backlog section

The spec should include a single consolidated follow-up section rather than
separate Codex and Cline lists:

```markdown
## Deferred Codex/Cline evaluation follow-ups

- [ ] E1. Introduce a `WorkflowExecutionContext` / `RunContext` object separate from mutable `WorkflowExecutionState`.
- [ ] E2. Add a lightweight `ModelCapabilities` model for context window, structured-output support, reasoning support, modalities, and parallel tool-call support.
- [ ] E3. Strengthen tool input-schema validation for OpenAI-compatible object-shaped function schemas.
- [ ] E4. Add explicit tool exposure states: `direct`, `deferred`, `direct_model_only`, and `hidden`.
- [ ] E5. Clarify separation between tool catalog metadata, callable registry entries, node exposure, approval policy, and sandbox/side-effect policy.
- [ ] E6. Refine `ToolResult` into model-facing output, raw output, trace/log preview, and hook/event payload facets.
- [ ] E7. Define narrow in-process lifecycle hook protocols for model, tool, node, permission, and workflow boundaries.
- [ ] E8. Extend trace vocabulary for tool lifecycle, usage updates, status notices, and future permission/context-management events.
- [ ] E9. Draft MCP registry-source support with server provenance, visibility, status, tool cache, disabled state, operation locking, and memory-pollution metadata.
- [ ] E10. Add a context-management prepare-stage design for future compaction policies while preserving current fail-closed token-budget behavior.
- [ ] E11. Consider hierarchical file-backed prompt context only with explicit roots, source tracking, scan limits, and token/byte budgets.
- [ ] E12. Keep multi-agent collaboration represented through primitive nodes and optional delegation tools; defer durable team runtime until requirements justify it.
```

## Validation

- Read `cline-tasks/codex-cli-evaluation.md` — pass.
- Read `cline-tasks/cline-evaluation.md` — pass.
- Cross-checked against `specs/dynamic-agent-runner/spec.md`,
  `specs/dynamic-agent-runner/tasks.md`, and `README.md` — pass.
- Runtime tests/builds — not run; this was a documentation/spec synthesis task.
- Files changed during proposal creation — this proposal file and the spec
  backlog section.
