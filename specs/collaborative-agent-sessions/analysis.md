# Collaborative Agent Sessions Analysis Collateral

## Investigation Summary

This collateral preserves the analysis that shaped
`collaborative-agent-sessions`. It is design evidence, not implementation
authority.

## Why This Is Separate From Subagent Tool Pack

Bounded subagent fanout and persistent collaboration solve different problems:

- `subagent-tool-pack` answers "can the parent delegate this bounded task now?"
- `collaborative-agent-sessions` answers "can the caller keep this child agent
  alive, inspect it, message it again, and restart it later?"

Mixing both in one first slice would force lifecycle state, streaming,
restartability, and parent/child topology into the initial tool-pack contract.
The safer order is bounded subagent tools first, then persistent collaboration.

## DAR Fit

The current `AgentSession` baseline already provides:

- current-state retrieval
- snapshot restart
- in-memory storage through `InMemorySessionStore`
- bounded `accept(...)` runs
- same-session concurrency rejection
- session event streaming through `accept_stream(...)`

Collaborative sessions should compose those pieces by managing several
`AgentSession` instances under one parent session rather than creating a second
executor.

## Codex Protocol Evidence

The Codex app-server protocol models collaboration through explicit tools and
state:

- `spawnAgent`
- `sendInput`
- `resumeAgent`
- `wait`
- `closeAgent`

It also models child statuses, parent thread ids, agent nicknames, agent roles,
subagent activity records, and source kinds for review, compaction, spawn, and
other subagent uses.

The portable lesson is that persistent collaboration needs explicit lifecycle
operations and inspectable status. A single "run subagent" tool result is not
enough for this class of behavior.

## Cline SDK Evidence

The Cline SDK plugin example keeps background child agents in an in-memory map,
supports start/message/inspect/list operations, and stores handoff files in a
conversation-scoped directory.

The portable lesson is that v1 can be in-memory and still useful, provided the
API makes child ids, statuses, handoff/state, and recursion policy explicit.

## Recommended Boundary

For DAR, the recommended v1 boundary is:

- parent-owned manager over child `AgentSession` objects
- `InMemorySessionStore` enough for first pass
- explicit child presets for workflow, tools, model requirements, and policy
- direct host APIs first
- optional manager tools second, registered through `ToolRegistry`
- no durable external store
- no recursive spawn by default
- no always-running executor loop

## Relationship to LLM-as-Tool

Persistent collaboration is the stateful end of the same family:

- LLM-as-tool: one bounded model call
- workflow-as-tool: one bounded child workflow
- subagent tool: one bounded child specialist operation or fanout
- collaborative session: persistent child `AgentSession` with lifecycle APIs

The persistent variant needs restartable state and should not be hidden behind a
single opaque tool output.

## Open Design Pressure

The biggest future pressure is whether child sessions should run only when the
caller invokes lifecycle methods, or whether DAR should eventually support
background scheduling. The recommended v1 answer is lifecycle-method driven
only. Background scheduling, queues, process supervision, and durable locks
belong in a later coordination/runtime spec if a caller needs them.
