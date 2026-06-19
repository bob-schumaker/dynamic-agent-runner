# Subagent Tool Pack Analysis Collateral

## Investigation Summary

This collateral preserves the local-repo and external-repo analysis that shaped
`subagent-tool-pack`. It is design evidence, not implementation authority.

## DAR Fit

Graphify and direct source inspection show the relevant DAR primitives are:

- `ToolRegistry` and `RegisteredTool` for model-visible callable tools.
- `ToolResult` for structured tool output, model-facing output, raw output, and
  trace payloads.
- `execute_workflow_async(...)` for bounded workflow execution.
- `llm_step` model tool calls for registry-mediated tool use.
- `AgentSession` and `InMemorySessionStore` for in-memory cross-prompt
  continuity.
- `AgentSession.accept_stream(...)` for redacted session event streaming.
- capability/status reporting for live versus metadata-only collaborators.

The cleanest fit is "subagent as tool." A parent workflow does not need a new
node kind to delegate work; it needs a registry entry whose handler can run
bounded child work and return a structured `ToolResult`.

## Cline Evidence

The Cline VS Code app implements subagents as tool-mediated delegation:

- `use_subagents` accepts multiple prompts, with a max of five in the inspected
  implementation.
- Child work is gated by a feature flag and approval policy.
- Child prompts run in parallel with aggregate result handling.
- Child agents get separate task state, context manager, usage accounting, and
  constrained tools.
- The default child system suffix frames the child as a research subagent with
  read/list/search/read-only-command style behavior and a terminal completion
  call.
- Dynamic named subagent tools can be generated from YAML configs under the
  user's Cline agents directory.

The portable lesson is not Cline-specific UI behavior. The portable lesson is:
bounded child work should be exposed as one or more tools, with explicit
allowed tools, budget/parallelism limits, approval gates, and aggregate
results.

## Cline SDK Plugin Evidence

The `agents-squad` example in Cline's SDK shows a more persistent direction:

- background subagent sessions are stored in an in-memory map
- callers can start, message, inspect, and list child agents
- handoff files live under a conversation-scoped directory
- recursion controls disable spawning inside child agents by default

This supports the split between:

- first-stage `subagent-tool-pack` for bounded fanout
- later `collaborative-agent-sessions` for persistent spawned agents

## Codex Evidence

The Codex app-server protocol has explicit collaboration-agent concepts:

- tools: `spawnAgent`, `sendInput`, `resumeAgent`, `wait`, `closeAgent`
- statuses: `pendingInit`, `running`, `interrupted`, `completed`, `errored`,
  `shutdown`, `notFound`
- thread topology with parent thread id, agent nickname, and agent role
- subagent activity records for started/interacted/interrupted
- source kinds for subagent, review, compact, thread-spawn, and other subagent
  uses
- JSONL event mapping for collaboration tool calls and state

The portable lesson is that persistent collaboration needs lifecycle and thread
state. That is beyond the first subagent tool pack and belongs in
`collaborative-agent-sessions`.

## Recommendation

Implement in two stages:

1. `subagent-tool-pack`: bounded callable specialist fanout through
   `ToolRegistry`, using fakeable child-runner interfaces and structured
   aggregate `ToolResult` output.
2. `collaborative-agent-sessions`: persistent child agents with spawn,
   message, wait, resume, close, inspect, and restart-from-state APIs.

Do not add a primitive `subagent_step` first. That would duplicate existing
registry and workflow execution boundaries and make safety/capability reporting
harder to keep coherent.

## LLM-as-Tool Placement

`LLM as tool` is the smallest member of the same design family:

- plain tool: deterministic or external action
- LLM as tool: one bounded model interaction
- workflow as tool: child DAR workflow execution
- session as tool: persistent child session interaction

The first pack should support workflow-as-tool and may optionally provide an
LLM-as-tool adapter. Persistent session-as-tool behavior should wait for
`collaborative-agent-sessions` unless a caller registers it manually.
