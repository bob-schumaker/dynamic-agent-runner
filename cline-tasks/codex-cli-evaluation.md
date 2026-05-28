# Codex CLI evaluation for `dynamic-agent-runner`

<!-- markdownlint-disable MD013 -->

I completed a read-only review of `/Users/roschuma/Repos/github/codex` focused on reusable agent-runtime patterns that could integrate well with this package.

## Goal

Evaluate Codex CLI for **general agent patterns and support mechanisms** that are useful for `dynamic-agent-runner`, not to port Codex wholesale.

## What I reviewed

- Local package context:
  - `README.md`
  - `specs/dynamic-agent-runner/spec.md`
  - `specs/dynamic-agent-runner/plan.md`
  - `specs/dynamic-agent-runner/tasks.md`
- Codex repo context:
  - `/Users/roschuma/Repos/github/codex/README.md`
  - `/Users/roschuma/Repos/github/codex/AGENTS.md`
  - `/Users/roschuma/Repos/github/codex/docs/*`
  - selected Rust workspace modules under `codex-rs/`, especially:
    - `tools/`
    - `codex-mcp/`
    - `core/src/session/`
    - `core/src/exec_policy.rs`
    - `core/src/hook_runtime.rs`
    - `core/src/compact.rs`
    - `core/src/thread_rollout_truncation.rs`
    - `core-skills/src/loader.rs`
    - `memories/README.md`
    - `protocol/src/openai_models.rs`
    - `protocol/src/protocol.rs`

No files were modified.

---

## High-value patterns to consider

### 1. Tool exposure as a first-class policy layer

Codex separates **registered tool capability** from **model-visible tool exposure**. In `codex-rs/tools/src/tool_executor.rs`, `ToolExposure` distinguishes:

- `Direct`
- `Deferred`
- `DirectModelOnly`
- `Hidden`

This maps very well to `dynamic-agent-runner`’s existing registry direction.

**Recommendation:** add an explicit `exposure` concept to tool definitions or runtime overrides, separate from whether a tool exists or is callable.

Potential manifest/registry vocabulary:

```yaml
tools:
  - id: search_repo
    exposure: direct
  - id: expensive_deep_search
    exposure: deferred
  - id: internal_audit_sink
    exposure: hidden
```

This would improve current `available_tools` / per-node exposure semantics by making “registered but not initially model-visible” a supported state.

---

### 2. Deferred / lazy-loaded tools

Codex’s `ToolDefinition` includes `defer_loading`, and Responses API adaptation preserves `defer_loading`. This is useful for large tool surfaces and MCP-style tool catalogs.

**Recommendation:** consider a future `defer_loading` flag for `dynamic-agent-runner` tool metadata.

Good fit for:

- MCP-style agents
- large tool catalogs
- plugin-like tool discovery
- expensive schema generation
- tool search / tool install flows

This should remain metadata until executor behavior is scoped.

---

### 3. Tool contract split: spec, invocation, output, visible event lifecycle

Codex decomposes tool handling into reusable concepts:

- `ToolDefinition` — metadata/schema
- `ToolExecutor` — executable runtime contract
- `ToolCall` — invocation context with turn id, call id, tool name, truncation policy, history, payload
- `ToolOutput` — conversion to model-facing response items plus log previews and post-tool hooks
- `TurnItemEmitter` — host-owned visible event lifecycle for extension tools

`dynamic-agent-runner` already has a repository-owned registry and `ToolResult`; Codex suggests a useful next refinement: separate **model-facing output**, **logging preview**, and **hook/event-facing output**.

**Recommendation:** when the registry grows beyond simple JSON tools, split `ToolResult` into clearer facets:

- `model_output`
- `success_for_logging`
- `log_preview`
- `post_tool_event_payload`
- optional visible lifecycle events

This would integrate naturally with the existing tracing layer.

---

### 4. MCP aggregation with visibility, provenance, approval, and startup status

Codex’s `McpConnectionManager` is a strong model for MCP support. It owns:

- server clients keyed by server name
- server metadata and origin/provenance
- model visibility filtering via MCP `_meta.ui.visibility`
- startup status events
- tool normalization and prefixing
- server shutdown
- approval policy and elicitation routing
- memory-pollution metadata
- parallel-tool-call capability metadata

**Recommendation:** if `dynamic-agent-runner` adds MCP support, model it as a registry source with explicit metadata rather than as a raw tool adapter.

Useful fields:

```yaml
mcp_servers:
  - id: confluence
    origin: caller_config
    prefix_tool_names: true
    pollutes_memory: false
    supports_parallel_tool_calls: false
    visibility: model
```

Especially useful: preserving whether a source “pollutes memory” or is allowed into memory/context artifacts.

---

### 5. Approval policy and sandbox policy should stay separate

Codex has separate concepts for:

- approval mode (`AskForApproval`)
- filesystem sandbox policy
- network sandbox policy
- permission profile
- exec-policy rule evaluation

`core/src/exec_policy.rs` also shows a useful pattern: if a policy requires approval but approval settings disallow prompting, the operation is rejected with a clear reason.

**Recommendation:** when `dynamic-agent-runner` adds write tools or command tools, do not collapse approval and sandboxing into one boolean like `approval_required`.

Prefer explicit dimensions:

```yaml
side_effect: write
approval:
  mode: on_request
sandbox:
  filesystem: workspace_write
  network: restricted
exec_policy:
  allowlisted_prefixes: [...]
```

Near-term, this can refine the currently deferred “write/command tool packs” direction.

---

### 6. Hooks around session, prompt, permission request, pre-tool, post-tool, compaction

Codex’s `hook_runtime.rs` supports hook points such as:

- session start
- user prompt submit
- permission request
- pre-tool use
- post-tool use
- pre/post compaction

Pre-tool hooks can mutate input or block execution; permission hooks can decide approvals; post-tool hooks receive stable adapted payloads.

**Recommendation:** consider adding package-owned hook interfaces later, but keep them narrow at first.

Best initial fit:

- `before_node`
- `before_tool_call`
- `after_tool_call`
- `on_permission_request`
- `after_workflow`

Do not add arbitrary shell hook execution until sandbox/approval rules are specified.

---

### 7. Turn context as an explicit runtime envelope

Codex’s `TurnContext` gathers the runtime envelope for one turn:

- model metadata
- provider
- reasoning settings
- approval policy
- permission profile
- network policy
- environment / cwd
- tool environment mode
- skill context
- truncation policy
- dynamic tools
- trace id / timing state

`dynamic-agent-runner` currently has `WorkflowExecutionState`, but Codex suggests a separate immutable-ish **execution context** object distinct from mutable state.

**Recommendation:** consider a `WorkflowExecutionContext` or `RunContext` that holds:

- model metadata
- registry
- approval/sandbox policy
- token/truncation policy
- trace sink
- prompt-cache override
- environment roots
- behavior overrides

This would reduce future parameter sprawl as runtime features grow.

---

### 8. Model metadata-driven behavior

Codex model metadata includes:

- context window
- effective context window percent
- auto-compaction limit
- shell tool type
- truncation policy
- support for reasoning summaries
- verbosity support
- web search support
- parallel tool calls
- input modalities

`dynamic-agent-runner` currently has token budgeting and OpenAI-first semantics. Codex suggests promoting model capabilities into a structured metadata object instead of scattering flags.

**Recommendation:** introduce a lightweight `ModelCapabilities` layer later, even while staying OpenAI-first.

Potential fields:

```python
@dataclass
class ModelCapabilities:
    context_window: int | None
    effective_context_window_percent: int = 95
    supports_parallel_tool_calls: bool = False
    supports_structured_outputs: bool = True
    supports_reasoning: bool = False
    input_modalities: tuple[str, ...] = ("text",)
```

This would help token budgeting, tool-call scheduling, prompt-cache decisions, and eventual multimodal support.

---

### 9. Context compaction with hook gates and cache-preserving behavior

Codex’s compaction flow is more advanced than this package currently needs, but two patterns are valuable:

- compaction has pre/post hooks and explicit analytics/status
- when context-window errors happen during compaction, Codex trims oldest history to preserve prefix cache and recent messages

**Recommendation:** keep current “automatic truncation unsupported” behavior for now, but when adding compaction, model it as an explicit node/policy with trace events and pre/post hooks.

Potential future manifest:

```yaml
execution_policy:
  context_management:
    on_exceed: compact
    strategy: summarize_oldest_turns
    preserve_prefix_cache: true
```

---

### 10. Memory pipeline split into extraction and consolidation phases

Codex memory pipeline is particularly relevant to future memory-augmented agents:

- Phase 1 extracts structured memory from eligible rollouts in parallel with a concurrency cap.
- Phase 2 serializes global consolidation under a lock.
- Memory artifacts are synchronized into a git-baselined workspace.
- A dedicated consolidation sub-agent runs with no approvals, no network, and local write access only.
- Secret redaction is explicit.
- Retry backoff and leases avoid duplicate work/hot loops.

**Recommendation:** this is worth preserving as a future design reference for memory-augmented runtime support.

For `dynamic-agent-runner`, a smaller adaptation would be:

- per-run memory extraction output contract
- explicit redaction step
- bounded concurrency for extraction
- serialized consolidation step
- durable memory write policy separate from normal workflow execution

Do not add this to core runtime until memory persistence requirements are explicit.

---

### 11. Hierarchical project instructions with budget and source tracking

Codex’s `AGENTS.md` loading:

- walks from project root to cwd
- stops at project root markers
- concatenates instructions in order
- respects byte budgets
- records instruction source paths
- supports local overrides

`dynamic-agent-runner` already supports behavior overrides and defers arbitrary skill file loading. Codex’s pattern is useful for future **project-context injection**.

**Recommendation:** if adding file-backed prompt context, use source tracking and budgeted hierarchical loading rather than arbitrary recursive prompt ingestion.

---

### 12. Skill discovery constraints and metadata policy

Codex’s `core-skills` loader validates:

- `SKILL.md` file shape
- YAML frontmatter
- required `name` and `description`
- field length limits
- skill scope and root precedence
- dependencies and policy metadata
- scan depth limits
- root deduplication

This strongly supports this package’s current decision to defer arbitrary skill-source loading.

**Recommendation:** when `dynamic-agent-runner` eventually loads `SKILL.md` files, reuse these principles:

- bounded scan depth
- explicit roots/scopes
- frontmatter validation
- field size limits
- dependency declaration
- policy for implicit invocation
- source path provenance

---

### 13. Session protocol: submission queue / event queue

Codex protocol explicitly uses a Submission Queue / Event Queue pattern for async user-agent communication. This is useful if `dynamic-agent-runner` evolves from synchronous `run_agent_workflow(...)` into a streaming or app-server mode.

**Recommendation:** preserve the current synchronous API, but design future streaming around explicit events rather than stdout scraping.

This aligns with the existing `TraceEvent` model.

---

## Most actionable integration candidates

### Near-term, high fit

1. **Tool exposure enum**: `direct`, `deferred`, `direct_model_only`, `hidden`.
2. **Model capabilities object** for context window, parallel tool calls, modalities, structured output support.
3. **Run context object** to separate immutable execution envelope from mutable state.
4. **Better tool output facets**: model output vs trace/log preview vs post-tool event payload.
5. **MCP registry-source design note** before implementing MCP directly.

### Medium-term

6. Hook interface around node/tool/permission lifecycle.
7. File-backed hierarchical prompt context with explicit source paths and byte/token budgets.
8. Deferred tool loading / tool discovery metadata.
9. Context compaction policy with trace events.

### Later / only when requirements justify

10. Memory extraction/consolidation pipeline.
11. App-server style SQ/EQ runtime protocol.
12. Full sandbox / exec-policy engine for command execution tools.
13. Multi-provider model-provider architecture.

---

## What I would not port now

- Codex’s full Rust crate architecture: too broad and product-specific.
- Full sandbox implementations: valuable reference, but premature for this Python runner.
- Full memory pipeline: excellent pattern, but requires a durable memory product decision.
- Full skills loader: current package intentionally defers arbitrary skill-source loading.
- Multi-provider routing: current spec is OpenAI-first and explicitly defers LiteLLM/multi-provider direction.
- TUI/app-server protocols: useful later, not needed for current library API.

---

## Suggested next spec/task additions

If you want to turn this evaluation into local backlog items, I recommend adding a new section to `specs/dynamic-agent-runner/tasks.md` such as:

```markdown
# Deferred Codex CLI evaluation follow-ups

- [ ] C1. Add a tool exposure model with direct, deferred, direct-model-only, and hidden exposure states.
- [ ] C2. Introduce a model-capabilities object for context window, parallel tool calls, structured output support, and modalities.
- [ ] C3. Refactor execution setup toward a run-context object distinct from mutable workflow state.
- [ ] C4. Split tool results into model-facing output, trace/log preview, and hook/event-facing payload facets.
- [ ] C5. Draft MCP registry-source support with server provenance, model visibility, approval, and memory-pollution metadata.
- [ ] C6. Consider lifecycle hooks for before-tool, after-tool, permission-request, and workflow-completion events.
- [ ] C7. Consider hierarchical file-backed prompt context only with bounded source tracking and budget controls.
- [ ] C8. Defer memory extraction/consolidation pipeline until durable memory requirements are explicit.
```

I did **not** edit the task file because the request was to review and evaluate, not to update local artifacts.

---

## Validation

- Read-only source review — pass.
- Commands run:
  - `list_files` on Codex repo roots and docs.
  - `read_file` on selected docs and source modules.
  - `rg` searches for approval, sandbox, tool-call, memory, prompt-cache, trace, rollout, session, and model-capability terms.
- Tests/builds — not run; not needed for this read-only evaluation.
- Local files changed — none.
