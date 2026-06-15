# Cline SDK / CLI evaluation for `dynamic-agent-runner`

<!-- markdownlint-disable MD013 -->

I completed a read-only review of `/Users/roschuma/Repos/github/cline`, focused
on reusable agent-runtime patterns and support mechanisms that could integrate
well with this Python package.

## Goal

Evaluate Cline for **general agent patterns and support mechanisms** that are
useful for `dynamic-agent-runner`, not to port Cline wholesale.

## What I reviewed

- Local package context:
  - `README.md`
  - `specs/dynamic-agent-runner/spec.md`
  - `specs/dynamic-agent-runner/tasks.md`
  - `src/dynamic_agent_runner/executor.py`
  - `src/dynamic_agent_runner/registry.py`
  - `src/dynamic_agent_runner/tracing.py`
  - `src/dynamic_agent_runner/models.py`
- Cline repo context:
  - `/Users/roschuma/Repos/github/cline/README.md`
  - `/Users/roschuma/Repos/github/cline/CLAUDE.md`
  - `/Users/roschuma/Repos/github/cline/sdk/README.md`
  - `/Users/roschuma/Repos/github/cline/sdk/ARCHITECTURE.md`
  - selected SDK modules under `sdk/packages/`, especially:
    - `packages/agents/src/agent-runtime.ts`
    - `packages/shared/src/agent.ts`
    - `packages/shared/src/tools/create.ts`
    - `packages/shared/src/hooks/contracts.ts`
    - `packages/shared/src/hooks/events.ts`
    - `packages/core/src/runtime/host/runtime-host.ts`
    - `packages/core/src/services/local-runtime-bootstrap.ts`
    - `packages/core/src/extensions/tools/types.ts`
    - `packages/core/src/extensions/tools/runtime.ts`
    - `packages/core/src/extensions/tools/presets.ts`
    - `packages/core/src/extensions/tools/team/spawn-agent-tool.ts`
    - `packages/core/src/extensions/tools/team/multi-agent.ts`
    - `packages/core/src/extensions/mcp/manager.ts`
    - `packages/core/src/extensions/plugin/plugin-loader.ts`
    - `packages/core/src/extensions/context/compaction.ts`

This review produced this documentation update only; it did not change runtime
code or SDD task artifacts.

---

## High-value patterns to consider

### 1. Layered runtime boundaries: shared contracts, stateless loop, stateful core, host apps

Cline’s SDK architecture has a clean separation that maps well to the future
shape of `dynamic-agent-runner`:

- `@cline/shared` owns low-level contracts such as tools, hooks, messages,
  logging, and schemas.
- `@cline/llms` owns provider/model concerns.
- `@cline/agents` owns a **stateless runtime loop**.
- `@cline/core` owns stateful orchestration, persistence, configuration,
  compaction, plugins, hub/transport, and default tools.
- host apps wire the core runtime into CLI, IDE, hub, or other shells.

`dynamic-agent-runner` currently has a smaller but similar split: artifact models,
registry, OpenAI adapter, executor, and tracing are already separate. The Cline
pattern suggests preserving this separation as new features arrive.

**Recommendation:** keep `src/dynamic_agent_runner/executor.py` focused on
executing validated primitive workflow nodes, and put heavier session concerns
elsewhere.

Potential future module boundaries:

```text
src/dynamic_agent_runner/
  context.py        # immutable run/session context and model capabilities
  hooks.py          # lifecycle hook contracts
  sessions.py       # optional persisted/resumable session layer
  tools/            # built-in tool-pack implementations
  mcp.py            # MCP registry source / manager when scoped
  compaction.py     # explicit context-management policies
```

The most important lesson is **do not let the executor become the place where
persistence, config discovery, provider routing, plugin loading, and compaction
all accumulate**.

---

### 2. Run context separate from mutable workflow state

Cline distinguishes host/session config, local bootstrap fields, transport-safe
runtime input, and mutable agent runtime state. In `dynamic-agent-runner`,
`WorkflowExecutionState` currently carries mutable execution results, while
function parameters carry the execution envelope.

**Recommendation:** introduce a `WorkflowExecutionContext` or `RunContext` when
the next few runtime features start creating parameter sprawl.

Good candidate fields:

```python
from dataclasses import dataclass
from typing import Any, Mapping

@dataclass(frozen=True)
class WorkflowExecutionContext:
    workflow: LoadedAgentWorkflow
    model_adapter: OpenAIClientAdapter
    tool_registry: ToolRegistry | None
    tracer: WorkflowTracer
    max_steps: int
    prompt_cache_enabled: bool | None
    model_capabilities: Mapping[str, Any]
    approval_policy: Mapping[str, Any]
    tool_policy: Mapping[str, Any]
```

This is a near-term fit because the package already has retries, token budgets,
prompt-cache telemetry, tool registries, and trace sinks.

---

### 3. Agent loop with explicit message parts and event stream

Cline’s `AgentRuntime` models messages as typed parts:

- text
- reasoning
- image
- file
- tool-call
- tool-result

It also emits structured events for run start, message addition, turn start,
assistant deltas, tool start/update/finish, usage updates, turn finish, status
notices, run finish, and run failure.

`dynamic-agent-runner` already has `TraceEvent` and OpenAI response normalization,
but not a streaming turn/event model.

**Recommendation:** do not rush into streaming, but preserve the event vocabulary
as a reference for future app-server or CLI interactive modes.

Useful future event additions for `WorkflowTracer`:

- `turn_started` / `turn_finished` for iterative LLM/tool loops
- `assistant_text_delta` only if streaming is introduced
- `assistant_reasoning_delta` only if reasoning summaries are supported
- `tool_started`, `tool_updated`, `tool_finished` for long-running tools
- `usage_updated` as distinct from model response payload
- `status_notice` for compaction, approval waits, or queued steering messages

For the current graph executor, existing node-level trace events remain simpler
and appropriate.

---

### 4. Hook contract with controlled mutation and stop behavior

Cline has a seven-callback runtime hook bag:

- `beforeRun`
- `afterRun`
- `beforeModel`
- `afterModel`
- `beforeTool`
- `afterTool`
- `onEvent`

The hook results are intentionally controlled: they can stop execution, rewrite
messages/tools/options, mutate tool input, skip a tool, or replace a tool result.

This is a strong fit for `dynamic-agent-runner` once hooks are scoped, because
it keeps extension behavior inside stable lifecycle gates instead of arbitrary
executor monkey-patching.

**Recommendation:** when adding hooks, start with a narrow Python equivalent:

```python
class WorkflowHooks(Protocol):
    def before_node(self, context: NodeHookContext) -> NodeControl | None: ...
    def before_model(self, context: ModelHookContext) -> ModelControl | None: ...
    def before_tool(self, context: ToolHookContext) -> ToolControl | None: ...
    def after_tool(self, context: ToolResultHookContext) -> ToolResultControl | None: ...
    def after_workflow(self, context: WorkflowResultHookContext) -> None: ...
```

Avoid arbitrary shell hook execution until approval and sandbox semantics exist.

---

### 5. Tool creation should validate object-shaped input schemas early

Cline’s `createTool(...)` normalizes JSON Schema and fails at registration time
when tool input schemas are not top-level object-shaped. It accepts either raw
JSON Schema or Zod schemas, strips unnecessary `$schema`, and detects problematic
top-level `oneOf` / `anyOf` / `allOf` cases.

`dynamic-agent-runner` currently validates only a small subset of input schemas
in `registry.py`.

**Recommendation:** strengthen tool registration validation so invalid schemas
fail before model execution. Since the runtime targets OpenAI-compatible tools,
top-level object schemas should be required for exposed function tools.

Near-term improvement:

- validate `input_schema` is a mapping
- require or infer `type: object` when properties/required are present
- reject top-level unions unless every branch is explicitly object-shaped
- strip or ignore `$schema` in model-facing tool schema output
- keep detailed error messages in `ToolRegistryError`

This would make tool failures easier to diagnose and aligns with the current
fail-closed registry direction.

---

### 6. Tool policy and tool catalog should be distinct

Cline separates:

- default tool catalog entries
- mode-dependent tool presets
- selected tool ids
- headless tool names
- tool policies such as enabled/auto-approved
- executor availability

`dynamic-agent-runner` already distinguishes metadata from callable registry
entries and has opt-in built-in tool packs. Cline suggests a next refinement:
separate **catalog availability** from **policy approval**.

**Recommendation:** keep built-in pack enablement, node exposure, callable
registry availability, and approval/safety policy as distinct dimensions.

Potential vocabulary:

```yaml
tool_packs:
  local_workspace:
    enabled: true
    allowlist: [read_file, list_files, search_files]
tool_policy:
  "*":
    enabled: true
    approval: on_request
  run_command:
    enabled: false
```

This is especially important before adding write or command-execution packs.

---

### 7. Completion as an explicit lifecycle signal/tool

Cline supports completion behavior through a completion policy and tool lifecycle
metadata. A tool can be marked as completing a run, and Cline’s architecture
notes treat explicit completion-tool observation as the primary completion
telemetry anchor.

`dynamic-agent-runner` currently completes graph execution when traversal ends.
That is right for manifest-defined workflows, but agent-loop patterns may need a
clear completion primitive.

**Recommendation:** if `dynamic-agent-runner` later supports ReAct-like iterative
agent loops or open-ended tool agents, model completion explicitly rather than
inferring it from “no tool calls”.

Possible manifest addition:

```yaml
tools:
  - id: submit_and_exit
    lifecycle:
      completes_run: true
execution_policy:
  completion:
    require_completion_tool: true
```

For the current finite graph executor, no change is needed.

---

### 8. Context compaction belongs in a prepare-turn pipeline, not in low-level model calls

Cline puts compaction behind a `prepareTurn` callback owned by the stateful core
layer. The low-level agent loop offers the seam, while core chooses policy,
strategy, token thresholds, telemetry, and status notices.

This matches `dynamic-agent-runner`’s current stance: token budgeting exists,
automatic truncation is intentionally unsupported, and context management needs a
scoped policy before implementation.

**Recommendation:** when adding compaction, implement it as an explicit
context-management stage before model request construction, not as hidden
behavior inside `OpenAIClientAdapter`.

Potential future manifest shape:

```yaml
execution_policy:
  context_management:
    on_exceed: compact
    strategy: basic_summary
    threshold_ratio: 0.8
    reserve_tokens: 2000
```

Trace events should include tokens before/after, strategy, duration, skipped
state, and whether compaction modified messages.

---

### 9. MCP manager as a registry source with connection state and tool cache

Cline’s `InMemoryMcpManager` keeps MCP servers as managed runtime state:

- server registration
- connection status
- disabled flag
- last error
- tool cache with TTL
- serialized per-server operations via locks
- explicit connect/disconnect/register/unregister lifecycle

This is a useful reference for future MCP support in `dynamic-agent-runner`.

**Recommendation:** model MCP as a **registry source**, not as ad hoc tools
injected into the executor.

Potential concepts:

- `McpRegistrySource`
- `McpServerRegistration`
- `McpToolDescriptor`
- `McpToolCachePolicy`
- `McpToolNameTransform`
- `server_status` trace or diagnostic events

Keep this deferred until MCP requirements are explicit. The current package does
not need live MCP support to execute generated runtime artifacts.

---

### 10. Plugin loading should validate manifests and produce diagnostics, not hard fail wholesale

Cline’s plugin loader validates plugin exports and manifests, supports provider
and model targeting, deduplicates by plugin name, records override warnings, and
returns load failures separately from successful plugins.

This is relevant if `dynamic-agent-runner` later supports plugin-based tool packs
or hook bundles.

**Recommendation:** if plugin loading is added, make plugin discovery a separate
preparation step that returns a diagnostic report:

- loaded plugins
- skipped plugins due to targeting
- warnings such as duplicate overrides
- failures with phase, path, message, and stack when available

Do not let arbitrary plugin imports become part of the initial runtime path. This
aligns with the existing decision to defer full `SKILL.md` source loading and
keep generated artifacts authoritative.

---

### 11. Multi-agent support: distinguish simple spawn from durable team runtime

Cline has two useful multi-agent patterns:

1. `spawn_agent` — a tool that delegates one focused task to a sub-agent with a
   custom system prompt and returns a compact result.
2. `AgentTeam` — a richer team runtime with members, mailbox/messages, mission
   logs, run records, queued/recovered runs, outcomes, fragments, and review.

For `dynamic-agent-runner`, this distinction is valuable because supported
pattern metadata includes `multi-agent-collaboration`, but the current executor
intentionally compiles patterns down to primitive nodes.

**Recommendation:** preserve two separate future designs:

- near-term: represent delegation as ordinary `tool_use_step` or tool-callable
  `spawn_agent` metadata when requirements justify it
- later: represent durable teams with explicit state sections, mailbox artifacts,
  run records, and outcome aggregation

Do not introduce a primitive `multi_agent_step` node just because Cline has team
support. The current primitive taxonomy remains a better fit for this package.

---

### 12. Pending prompts / steering messages as an explicit service

Cline’s runtime host API treats pending prompts as a service with list, update,
and delete operations, and the agent loop can consume a pending user message
between iterations.

This is useful for future interactive or long-running workflows where a caller
may steer an active run.

**Recommendation:** if `dynamic-agent-runner` evolves beyond synchronous
`run_agent_workflow(...)`, model human steering as explicit queued input events,
not as out-of-band mutation of state.

For now, preserve the synchronous API.

---

### 13. Automation specs: Markdown/YAML frontmatter -> durable queue -> reports

Cline’s cron architecture parses file-backed Markdown specs with YAML
frontmatter, reconciles them into durable queue records, executes runs through
the same runtime handlers, and writes Markdown reports.

This is not core to `dynamic-agent-runner`, but it is useful as a pattern if the
package later grows a runner daemon or scheduled execution helper.

**Recommendation:** keep this out of core. If needed later, implement it as a
separate package or optional module that consumes the existing public API.

---

## Most actionable integration candidates

### Near-term, high fit

1. **Run context object** distinct from mutable `WorkflowExecutionState`.
2. **Stronger tool schema validation** for OpenAI-compatible function schemas.
3. **Tool catalog/policy separation** before adding write or command tools.
4. **Lifecycle hook interfaces** around model/tool/workflow boundaries, but only
   in-process Python hooks at first.
5. **Additional trace vocabulary** for tool lifecycle and status notices.

### Medium-term

6. **Context-management prepare stage** for future compaction policies.
7. **MCP registry-source design** with server status, tool caching, disabled
   state, and serialized server operations.
8. **Completion tool lifecycle metadata** for iterative agent loops.
9. **Plugin diagnostics model** if plugin-based tool/hook bundles are added.
10. **Sub-agent delegation tool pattern** compiled through existing primitive
    nodes rather than new node kinds.

### Later / only when requirements justify

11. Durable multi-agent team runtime with mailbox, mission logs, outcomes, and
    recovered queued work.
12. Hub/RPC runtime host abstraction for shared sessions or remote clients.
13. Scheduled automation service with durable queue and Markdown reports.
14. Full multi-provider gateway; current package remains OpenAI-first.
15. Interactive TUI/IDE startup and rendering patterns.

---

## What I would not port now

- Cline’s full TypeScript package stack: useful architecture, but too broad for
  this Python runtime package.
- Full provider gateway: `dynamic-agent-runner` is intentionally OpenAI-first.
- Hub daemon and RPC transport: premature while the public API is synchronous.
- Durable team runtime: valuable later, but not needed for current primitive graph
  execution.
- Plugin sandboxing/import system: unsafe and unnecessary until plugin
  requirements exist.
- Cron/scheduled automation: should remain outside core runtime.
- Interactive TUI and IDE concerns: not relevant to the current package.
- Broad default tool presets that enable command or write tools by default; keep
  this package conservative and explicit.

---

## Suggested next spec/task additions

If you want to turn this evaluation into local backlog items, I recommend adding
a deferred section to `specs/dynamic-agent-runner/tasks.md` such as:

```markdown
# Deferred Cline SDK evaluation follow-ups

- [ ] CL1. Introduce a `WorkflowExecutionContext` object separate from mutable execution state.
- [ ] CL2. Strengthen tool input-schema validation for OpenAI-compatible top-level object schemas.
- [ ] CL3. Separate tool catalog availability, callable registry entries, node exposure, and approval policy.
- [ ] CL4. Define in-process lifecycle hook contracts for before-model, before-tool, after-tool, and after-workflow.
- [ ] CL5. Extend trace event vocabulary for tool lifecycle, status notices, and usage updates when streaming/interactive modes are scoped.
- [ ] CL6. Draft a context-management prepare stage for future compaction policies.
- [ ] CL7. Draft MCP registry-source support with server registration, connection status, disabled state, tool cache, and operation locking.
- [ ] CL8. Add completion-tool lifecycle metadata only if iterative agent-loop execution becomes in scope.
- [ ] CL9. Keep multi-agent collaboration represented through primitive nodes and metadata; defer durable team runtime until requirements justify it.
```

I did **not** edit the task file because the request was to review and evaluate,
not to update the local backlog.

---

## Validation

- Read-only source review — pass.
- Evaluation artifact update — pass; this file now reflects
  `/Users/roschuma/Repos/github/cline` instead of the previous Codex evaluation.
- Commands/tools used:
  - `list_files` on Cline repo roots and selected SDK directories.
  - `read_file` on selected architecture, README, agent runtime, tool, hook,
    MCP, plugin, compaction, and team-agent files.
  - `search_files` for selected runtime concepts; some searches returned no
    matches because the Cline codebase uses direct file organization and exported
    shared types rather than the searched symbol strings in those paths.
- Tests/builds — not run; not needed for this read-only evaluation and markdown
  artifact update.
- Runtime code changed — none.
