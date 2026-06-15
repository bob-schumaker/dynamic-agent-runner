# OpenAI Agents SDK Python evaluation for `dynamic-agent-runner`

<!-- markdownlint-disable MD013 -->

I completed a read-only review of `/Users/roschuma/Repos/github/openai-agents-python`, focused on reusable agent-runtime patterns and support mechanisms that could integrate well with this package.

## Goal

Evaluate OpenAI Agents SDK Python for **general agent patterns and support mechanisms** useful for `dynamic-agent-runner`, not to port the SDK wholesale.

Note: the user described the target as the “codex-cli repo,” but the provided path is the local checkout of OpenAI Agents SDK Python. This evaluation follows the provided path.

## What I reviewed

- Local package context:
  - `README.md`
  - `specs/dynamic-agent-runner/spec.md`
  - `specs/dynamic-agent-runner/tasks.md`
  - `cline-tasks/codex-cli-evaluation.md`
  - `cline-tasks/cline-evaluation.md`
  - `cline-tasks/evaluation-follow-up-implementation-plan.md`
- OpenAI Agents SDK Python context:
  - `/Users/roschuma/Repos/github/openai-agents-python/README.md`
  - `/Users/roschuma/Repos/github/openai-agents-python/docs/index.md`
  - `/Users/roschuma/Repos/github/openai-agents-python/docs/multi_agent.md`
  - `/Users/roschuma/Repos/github/openai-agents-python/docs/human_in_the_loop.md`
  - `/Users/roschuma/Repos/github/openai-agents-python/docs/sessions/index.md`
  - `/Users/roschuma/Repos/github/openai-agents-python/docs/sandbox_agents.md`
  - `/Users/roschuma/Repos/github/openai-agents-python/examples/agent_patterns/README.md`
  - selected source modules under `src/agents/`, especially:
    - `agent.py`
    - `run.py`
    - `run_config.py`
    - `run_context.py`
    - `run_state.py`
    - `run_internal/run_steps.py`
    - `run_internal/run_loop.py`
    - `run_internal/turn_preparation.py`
    - `run_internal/turn_resolution.py`
    - `run_internal/tool_execution.py`
    - `tool.py`
    - `tool_guardrails.py`
    - `guardrail.py`
    - `handoffs/__init__.py`
    - `agent_output.py`
    - `function_schema.py`
    - `result.py`
    - `stream_events.py`
    - `models/interface.py`
    - `mcp/manager.py`
    - `memory/session.py`
    - `sandbox/manifest.py`

This review produced this documentation artifact only; it did not change runtime code or SDD task artifacts.

---

## High-value patterns to consider

### 1. Agent primitive as a reusable configuration bundle

OpenAI Agents models an `Agent` as a compact configuration object containing:

- instructions or dynamic instructions
- optional prompt object
- tools and MCP servers
- handoffs
- model and model settings
- input and output guardrails
- output schema/type
- lifecycle hooks
- tool-use behavior
- tool-choice reset behavior

This is intentionally smaller and more Python-native than a manifest graph, but it is a useful conceptual reference.

**Recommendation:** keep `dynamic-agent-runner`’s generated manifest as the source of truth, but consider a derived `RunnableAgentProfile` or `NodeAgentProfile` for future agent-loop nodes.

Potential fields:

```python
@dataclass(frozen=True)
class RunnableAgentProfile:
    name: str
    instructions: str | None
    model: str | None
    model_settings: ModelCapabilities | Mapping[str, object]
    tool_ids: tuple[str, ...]
    handoff_ids: tuple[str, ...]
    output_contract_ref: str | None
    guardrail_refs: tuple[str, ...] = ()
```

This would be most useful only if the runner adds iterative `agent_loop` support; the current finite node executor should not be refactored just to mimic the SDK.

---

### 2. Managed turn loop with explicit `NextStep` outcomes

The SDK’s loop is summarized in `Runner.run(...)` and implemented around internal step outcomes in `run_internal/run_steps.py`:

- `NextStepFinalOutput`
- `NextStepHandoff`
- `NextStepRunAgain`
- `NextStepInterruption`

`ProcessedResponse` separates model output processing into handoffs, function tool calls, computer actions, shell/apply-patch calls, MCP approval requests, missing tool calls, and interruptions.

This is a strong pattern for any future `dynamic-agent-runner` iterative runtime because it avoids ambiguous “continue or stop?” logic buried in tool handling.

**Recommendation:** if a future manifest version adds open-ended or ReAct-style agent loops, use an explicit step-result enum rather than inferring state from model output shape.

Possible manifest/runtime vocabulary:

```yaml
nodes:
  - id: agent_loop
    kind: llm_step
    loop_policy:
      max_turns: 10
      completion:
        mode: final_output_or_tool_policy
      on_tool_calls: run_tools_and_continue
      on_handoff: switch_active_profile
      on_interruption: pause_with_run_state
```

Near-term impact is low because `dynamic-agent-runner` currently executes finite generated graphs.

---

### 3. Distinguish handoffs from agents-as-tools

The SDK’s docs and code make a clear distinction:

- **Handoff**: the specialist agent takes over the conversation. Handoffs carry a tool-like schema, optional `on_handoff`, optional input filter, optional nested history behavior, and enablement predicate.
- **Agent as tool**: a manager agent remains in control and calls the specialist as a bounded subtask. `Agent.as_tool(...)` supports custom output extraction, structured input, streaming nested events, approval, and nested run metadata.

This maps directly to `dynamic-agent-runner`’s current design principle that multi-agent collaboration should compile down to primitive nodes and metadata rather than a new `multi_agent_step` primitive.

**Recommendation:** preserve two future metadata patterns:

1. `handoff` metadata for active-agent transfer.
2. `agent_tool` metadata for bounded delegation that returns a result to the current flow.

Do not collapse both into a generic “subagent” node. The difference affects history, final-output ownership, approval surfacing, and result aggregation.

---

### 4. Tool-use behavior as an explicit completion policy

OpenAI Agents exposes `tool_use_behavior` on `Agent`:

- `run_llm_again`
- `stop_on_first_tool`
- stop at specified tool names
- a custom function returning `ToolsToFinalOutputResult`

This is a cleaner model than treating tool calls as always “run then continue” or always “tool output is final.”

**Recommendation:** if `dynamic-agent-runner` adds iterative agent loops or model-emitted tool calls beyond finite direct `tool_use_step` nodes, add explicit tool-completion policy.

Potential manifest shape:

```yaml
execution_policy:
  tool_use_behavior:
    default: run_llm_again
    stop_at_tools:
      - submit_final_answer
```

For the current finite graph executor, direct `tool_use_step` nodes already determine flow and do not need this policy.

---

### 5. Guardrails as first-class inputs, outputs, and tool gates

The SDK has separate guardrail surfaces:

- `InputGuardrail` returns `GuardrailFunctionOutput(output_info, tripwire_triggered)` and can run in parallel with agent execution.
- `OutputGuardrail` validates final output.
- `ToolInputGuardrail` and `ToolOutputGuardrail` can allow, reject content with a model-visible message, or raise to halt execution.

This is more expressive than a single validation callback, especially for tools where “reject this specific call but continue with a model-visible reason” is different from “abort the run.”

**Recommendation:** add guardrail metadata before adding executable guardrail hooks.

Good deferred manifest concepts:

```yaml
guardrails:
  - id: pii_check
    phase: input
    behavior_on_tripwire: abort
  - id: safe_tool_args
    phase: tool_input
    behavior_on_tripwire: reject_content
```

Executable guardrails should integrate with existing lifecycle hooks and trace events, not bypass them.

---

### 6. Human-in-the-loop as durable interruption plus resumable run state

The SDK’s HITL flow is particularly relevant:

- Tools declare `needs_approval`, either always or via a per-call async predicate.
- The run pauses with `RunResult.interruptions` containing approval items.
- The caller converts the result to `RunState`, approves or rejects items, and resumes the original top-level run.
- Rejections can have model-visible messages.
- Sticky approvals/rejections can persist within the serialized run state.
- Nested `Agent.as_tool()` approvals surface on the outer run.

`dynamic-agent-runner` already preserves approval policy metadata but does not implement approval pauses.

**Recommendation:** model future approval as a pause/resume state machine, not as an inline blocking callback.

Potential additions:

- `WorkflowInterruption` result type.
- `WorkflowRunState` serialization boundary.
- per-call approval IDs and rejection messages.
- explicit resume API such as `resume_workflow_async(state, decisions=...)`.

This is a higher-value pattern than immediate auto-approval callbacks because it fits long-running automation and UI-mediated approval better.

---

### 7. `RunState` schema-version policy for durable pause/resume

`run_state.py` is large, but its schema policy is valuable even if the implementation is too broad to port:

- emitted state has `CURRENT_SCHEMA_VERSION`
- supported schema versions are enumerated with summaries
- forward compatibility fails fast
- context serialization is conservative
- missing custom context serializers produce warnings or strict failures
- serialized state includes approvals, usage, generated items, trace state, prompt cache keys, reasoning-item policy, and sandbox state

**Recommendation:** if `dynamic-agent-runner` introduces durable run-state snapshots, start with explicit schema versioning and a small chronological summary map from day one.

Suggested minimal policy:

```python
CURRENT_WORKFLOW_STATE_SCHEMA_VERSION = "1.0"
SUPPORTED_WORKFLOW_STATE_SCHEMA_VERSIONS = {
    "1.0": "Initial pause/resume state for approval interruptions."
}
```

Do not serialize arbitrary caller context by default; require explicit serializer/deserializer hooks or mapping-only context.

---

### 8. Sessions as a small protocol with history merge callbacks

The SDK’s `Session` protocol is intentionally small:

- `get_items(limit=None)`
- `add_items(items)`
- `pop_item()`
- `clear_session()`

Docs distinguish client-managed sessions from server-managed `conversation_id` / `previous_response_id` continuation, and `RunConfig.session_input_callback` lets callers customize how old history and new input merge.

**Recommendation:** when `dynamic-agent-runner` adds memory/session support, keep the first interface small and avoid coupling it to one storage backend.

Good fit:

- a `WorkflowSession` protocol with latest-N retrieval
- a `session_input_callback` or `prepare_history` hook
- explicit incompatibility rules between local session history and provider-managed continuation

This complements, but does not replace, the existing deferred context-management and compaction work.

---

### 9. `call_model_input_filter` as a prepare-turn seam

`RunConfig.call_model_input_filter` receives a `CallModelData` object with model input, agent, and context, and returns a possibly modified `ModelInputData` before the model call.

This is a general seam for token pruning, context injection, extra system/developer messages, and policy enforcement without embedding that logic in the model adapter.

**Recommendation:** keep `dynamic-agent-runner`’s OpenAI adapter narrow. If adding context compaction, session pruning, or hierarchical prompt-context injection, implement it as a pre-model prepare stage.

This aligns with the existing deferred E10/E11 follow-ups:

- E10 context-management prepare stage
- E11 hierarchical file-backed prompt context with budgets

---

### 10. Function-tool schema generation from Python callables

`function_schema.py` extracts tool schemas from Python function signatures, type hints, `Annotated[...]` metadata, and docstrings. It uses Pydantic models and strict JSON schema conversion.

`dynamic-agent-runner` currently requires explicit `ToolDefinition` metadata, which is good for generated artifacts and portable manifests.

**Recommendation:** do not replace explicit tool definitions, but consider an optional helper later:

```python
tool = tool_from_function(read_file, id="read_file", side_effect="read")
```

Rules for a future helper:

- generated metadata must be inspectable and overridable
- side-effect and approval policy must remain explicit
- schema generation should be registration-time validation, not model-call-time guessing

This is a convenience feature, not core runtime architecture.

---

### 11. Tool origin metadata across function, MCP, and agent-as-tool sources

OpenAI Agents tracks `ToolOrigin` with origin types:

- `function`
- `mcp`
- `agent_as_tool`

Origin metadata appears in tool result/run-state handling, which helps diagnose where a tool came from after multiple sources have been normalized into model-visible calls.

**Recommendation:** extend `dynamic-agent-runner`’s registry provenance model before adding MCP or agent-as-tool support.

Potential fields:

```python
@dataclass(frozen=True)
class ToolOrigin:
    source_type: Literal["registered", "builtin_pack", "mcp", "agent_tool", "override"]
    source_id: str | None = None
    original_name: str | None = None
```

This would build on current registry metadata without changing the executor’s primitive node taxonomy.

---

### 12. MCP manager with active/failed server subsets and task-affinity cleanup

The SDK’s `MCPServerManager` is smaller than Codex/Cline MCP managers but has useful lifecycle behavior:

- connect and cleanup timeouts
- strict vs non-strict connection failure behavior
- active server subset after connection attempts
- failed server list and error map
- reconnect failed-only or all
- optional parallel connection while preserving connect/cleanup task affinity through per-server workers

**Recommendation:** if implementing E9 MCP registry-source support, include server lifecycle diagnostics from the beginning:

- `active_servers`
- `failed_servers`
- `errors_by_server`
- `strict` vs degraded startup mode
- reconnect policy
- cleanup timeout and cancellation behavior

This supplements the Codex/Cline recommendations around MCP provenance, visibility, status, cache, disabled state, operation locking, and memory-pollution metadata.

---

### 13. Structured run results and replayable input views

`RunResultBase` separates:

- original input
- generated run items
- raw model responses
- final output
- input/output/tool guardrail results
- context wrapper
- trace state
- sandbox resume state

It also exposes `to_input_list(...)` to replay a run into a later input, with a `normalized` mode for handoff-filtered histories.

**Recommendation:** preserve `dynamic-agent-runner`’s simple `WorkflowResult` for now, but consider adding a replayable `to_input_items()` or `to_continuation_input()` only when iterative or multi-turn workflows become in scope.

Do not overload the current final-result return value with all run history by default; keep detailed state inspectable through the execution state object.

---

### 14. Streaming events are deliberately layered

The SDK’s stream event model distinguishes:

- raw provider stream events
- processed run-item events such as message output, handoff requested, tool called, tool output, reasoning item, MCP approval request, MCP list tools
- active agent update events

This mirrors the distinction `dynamic-agent-runner` already makes between model adapter responses and package-owned trace events.

**Recommendation:** if streaming is added, expose layered event types instead of only raw OpenAI chunks.

Useful future event classes:

- raw provider event
- normalized model delta
- node/run item event
- tool lifecycle event
- interruption event
- agent/profile switch event

For the current synchronous/async finite executor, trace events remain the right abstraction.

---

### 15. Sandbox agents as a separate workspace runtime, not a default tool pack

Sandbox Agents combine:

- a manifest-defined workspace
- sandbox-native capabilities such as filesystem, shell, skills, memory, and compaction
- sandbox client selection
- session or snapshot resume
- path validation and archive/resource limits

The sandbox manifest code validates relative paths, rejects absolute paths and `..` escapes, records environment entries, and has concurrency/resource limits for materialization.

**Recommendation:** keep workspace/sandbox execution separate from the current read-only `local_workspace` built-in tool pack.

If `dynamic-agent-runner` later adds write/command packs, borrow the sandbox-agent separation:

- explicit workspace manifest
- explicit client/backend
- path grants
- resource limits
- approval-aware shell/apply-patch tools
- resumable workspace state

Do not turn local shell or apply-patch into ambient core capabilities.

---

## Most actionable integration candidates

### Near-term, high fit

1. **Guardrail metadata model** for input, output, tool-input, and tool-output phases, with abort vs reject-content behavior.
2. **Tool origin/provenance metadata** that distinguishes registered, built-in, override, MCP, and future agent-as-tool sources.
3. **Prepare-model-input seam** for context compaction, history pruning, and file-backed prompt injection before model adapter calls.
4. **MCP lifecycle diagnostics** as part of the already-deferred E9 registry-source design.
5. **Explicit tool-use completion policy design note** for future iterative agent-loop support.

### Medium-term

6. **Handoff vs agent-as-tool metadata** for multi-agent manifests without adding new primitive node kinds.
7. **Workflow interruption and resumable state design** for approval-required tools.
8. **Small session protocol** with latest-N retrieval and history/new-input merge callback.
9. **Optional Python callable-to-tool helper** that generates explicit tool metadata at registration time.
10. **Layered streaming event model** if interactive or app-server execution becomes in scope.

### Later / only when requirements justify

11. Full durable `WorkflowRunState` schema with approvals, trace state, prompt-cache state, and resume support.
12. Sandbox/workspace runtime with manifests, path grants, shell/apply-patch tools, snapshots, and resource limits.
13. Realtime/voice agent support.
14. Full model-provider routing across OpenAI, LiteLLM, or other providers; current package remains OpenAI-first.
15. Full managed agent-loop runtime that competes with OpenAI Agents SDK’s `Runner`.

---

## What I would not port now

- The full Agents SDK managed runner: `dynamic-agent-runner` is a manifest graph executor, not a general Python-first agent framework.
- Multi-provider model routing: current spec remains OpenAI-first and already defers LiteLLM/multi-provider routing.
- Realtime/voice APIs: valuable domain, but outside current runtime package scope.
- Full sandbox-agent subsystem: useful reference, but too broad until write/command tools and workspace isolation are explicitly scoped.
- Full `RunState` serialization: implement only if approval pauses or resumable long-running workflows become active requirements.
- Built-in session backends such as Redis, SQLAlchemy, MongoDB, Dapr, or encrypted session wrappers: defer until a concrete memory/session requirement exists.
- Automatic function-schema generation as the primary registry path: generated artifacts need explicit, portable tool metadata.
- Broad human-in-the-loop implementation before defining workflow interruption and resume APIs.

---

## Suggested next spec/task additions

If you want to turn this evaluation into local backlog items, I recommend adding a deferred section to `specs/dynamic-agent-runner/tasks.md` such as:

```markdown
## Deferred OpenAI Agents SDK Python evaluation follow-ups

- [ ] OA1. Add guardrail metadata for input, output, tool-input, and tool-output phases, including abort and reject-content behavior.
- [ ] OA2. Extend tool provenance metadata to distinguish registered, built-in, override, MCP, and future agent-as-tool origins.
- [ ] OA3. Design a prepare-model-input stage for context compaction, session pruning, and hierarchical prompt injection before model adapter calls.
- [ ] OA4. Fold MCP lifecycle diagnostics into E9: active/failed server lists, error maps, strict/degraded startup, reconnect, and cleanup timeouts.
- [ ] OA5. Draft tool-use completion policy for future iterative agent-loop support, including run-again, stop-on-tool, and custom final-output decisions.
- [ ] OA6. Preserve handoff vs agent-as-tool as distinct manifest metadata patterns for multi-agent workflows.
- [ ] OA7. Design workflow interruption and resumable run state for approval-required tools before implementing live approval pauses.
- [ ] OA8. Consider a small async session protocol only after multi-turn memory requirements are explicit.
- [ ] OA9. Consider an optional `tool_from_function(...)` helper that generates explicit registry metadata while preserving side-effect and approval policy.
- [ ] OA10. Keep sandbox/workspace runtime support separate from default local tool packs and defer it until write/command tool requirements are approved.
```

I did **not** edit the task file because the request was to review and evaluate, not to update the local backlog.

---

## Relationship to existing Codex/Cline follow-ups

Several OpenAI Agents SDK findings reinforce existing deferred items:

- E9 MCP registry-source support should include lifecycle diagnostics and degraded startup behavior.
- E10 context-management prepare stage is reinforced by `call_model_input_filter` and session merge callbacks.
- E11 hierarchical prompt context should remain budgeted and source-tracked, not adapter-internal.
- E12 multi-agent collaboration should preserve handoff vs agent-as-tool semantics while compiling to primitive nodes and metadata.
- E14 async-first execution is consistent with the SDK’s async-canonical runner and sync wrapper strategy.

The new evaluation adds the most incremental value around guardrails, durable interruption/resume, tool origin metadata, and sandbox separation.

---

## Validation

- Read-only source review — pass.
- Evaluation artifact creation — pass; this file was created under `cline-tasks/`.
- Commands/tools used:
  - `read_file` on local package README, SDD spec/tasks, existing evaluation artifacts, OpenAI Agents SDK docs, and selected source modules.
  - `list_files` on OpenAI Agents SDK root and `src/agents` tree.
  - `execute_command` with `find` to survey repository files.
  - `execute_command` with `git status --short` to check local working tree before writing.
- Tests/builds — not run; not needed for this read-only evaluation and markdown artifact creation.
- Runtime code changed — none.
- Existing unrelated local changes observed before writing: untracked `docs/` in this repository.
