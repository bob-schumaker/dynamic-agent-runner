# Persistent Agent Sessions Feature Specification

## Metadata

- Feature slug: `persistent-agent-sessions`
- Mode: `light`
- Artifact type: implemented feature specification
- Status: implemented v1 baseline
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Related feature packages:
  - `specs/async-session-memory-pipeline/spec.md`
  - `specs/context-management-prepare-stage/spec.md`
  - `specs/iterative-agent-loop-runtime/spec.md`
- Evaluated external session-continuity provenance:
  - [`sickn33/antigravity-awesome-skills`](https://github.com/sickn33/antigravity-awesome-skills)
  - `/Users/roschuma/Repos/github/antigravity-awesome-skills/skills/context-agent/SKILL.md`
  - `/Users/roschuma/Repos/github/antigravity-awesome-skills/skills/context-agent/references/context-format.md`
  - `/private/tmp/antigravity-awesome-skills-focused-graph/graphify-out/GRAPH_REPORT.md`

## Objective

Add a runner-owned, in-memory persistent agent session API that lets callers
reuse a compiled workflow and runtime collaborators across multiple user prompts
while preserving conversation/session context between bounded workflow runs.

The feature must let callers retrieve the current session state at any point and
restart a session from a previously saved state. `InMemorySessionStore` is enough
for the first pass; durable external storage remains out of scope.

## Problem Statement

The current runner executes one bounded workflow per call. That is a good safety
and observability boundary, but callers who build ReAct-style or other
multi-turn agents need a convenient way to keep using the same workflow context
across prompts without manually rebuilding `WorkflowExecutionContext`, tracking
session ids, and passing accumulated messages into each run.

The current architecture already has most of the right ingredients:

- `WorkflowExecutionContext` is reusable and intentionally excludes the
  per-run prompt.
- `WorkflowExecutionState` already has a `session_messages` field.
- `prepare_model_input(...)` already knows how to include, prune, and compact
  session messages when present.
- `runtime.execution_policy.async_session` declares portable session intent.
- Bounded iterative model-tool loops are already implemented inside eligible
  `llm_step` nodes.

The missing capability is a public session object and store that own continuity
between calls while preserving the executor's current bounded-run model.

## Design Position

This feature is **persistent agent sessions**, not an always-running graph
executor.

Each accepted user prompt still creates a normal bounded workflow run with its
own run id, trace events, guardrail checks, step limits, and approval boundaries.
The session object persists only the continuity inputs and outputs needed to
prepare the next run.

This avoids turning the executor into a long-running process manager while
still letting callers reuse a ReAct-style workflow as a stateful agent.

## Users and User Stories

- As an application host, I can create an agent session once and call
  `accept(prompt)` repeatedly so user follow-ups retain relevant context.
- As an application host, I can inspect the current session state so I can show
  history, diagnostics, or a checkpoint to the user.
- As an application host, I can save a session snapshot and later restart a
  session from that snapshot using `InMemorySessionStore`.
- As a workflow author, I can keep ReAct/tool behavior inside the existing
  bounded loop policy and rely on session continuity for cross-prompt context.
- As a safety reviewer, I can verify each prompt still goes through the normal
  executor limits, guardrails, approval checks, and trace behavior.

## Public Shape

The v1 public API is:

```python
context = WorkflowExecutionContext(
    workflow=compiled_workflow,
    tool_registry=tool_registry,
    model_adapter=model_adapter,
)
store = InMemorySessionStore()

session = AgentSession.create(
    execution_context=context,
    session_store=store,
    session_id="thread-123",
)

first = await session.accept("Inspect the repository.")
second = await session.accept("Now summarize the risky parts.")

snapshot = session.current_state().to_mapping()
restored = AgentSession.from_snapshot(
    snapshot,
    execution_context=context,
    session_store=store,
)
```

`accept_sync(...)` supports synchronous callers through the existing sync-wrapper
policy and fails inside a running event loop.

## Functional Requirements

### FR-1: Create reusable agent sessions

The runtime must expose a public session object that binds a
`WorkflowExecutionContext`, a session id, and a session store.

Acceptance criteria:

- Given a compiled workflow and runtime collaborators, when a caller creates a
  session, then the session can accept multiple prompts without reloading or
  recompiling the workflow.
- Given no explicit session id, when a caller creates a session, then the
  runtime generates a stable id for that session.
- Given an existing session id in the store, when creation uses that session id,
  then the session uses the existing state instead of starting empty.

### FR-2: Accept prompts as bounded workflow runs

Each prompt accepted by a session must execute through the existing workflow
executor as a bounded run.

Acceptance criteria:

- Given a session with prior messages, when `accept(prompt)` runs, then the
  workflow receives those messages through `WorkflowExecutionState`.
- Given each accepted prompt, then input guardrails, model/tool execution,
  approval interruption behavior, tracing, retry policy, token budgeting, and
  max-step limits behave as they do for ordinary workflow execution.
- Given a ReAct-style workflow with bounded model-tool loops, when the session
  accepts a prompt, then the loop remains bounded inside that run rather than
  turning into an unbounded cross-prompt loop.
- Given a run fails, then the session must not silently append a successful
  assistant turn for that failed run.

### FR-3: Maintain session transcript state

The session must maintain enough transcript state to preserve useful context
across prompts.

Acceptance criteria:

- Given a successful run, when it completes, then the session appends a user
  turn for the accepted prompt and an assistant turn for the final result.
- Given tool calls occur during a run, then raw tool arguments and raw tool
  outputs are not automatically appended to session chat history unless an
  explicit future policy says so.
- Given `history: last_turn`, then only the previous user/assistant turn pair is
  retained for the next run.
- Given `history: full`, then all retained user/assistant turn messages are
  available to context preparation.
- Given `history: summary`, then v1 may preserve an explicit summary field but
  must not invent model-backed summary generation unless that behavior is
  planned separately.

### FR-4: Provide `InMemorySessionStore`

The runtime must include an in-memory store for v1 session persistence.

Acceptance criteria:

- Given a session state, when it is saved to `InMemorySessionStore`, then a
  later lookup by session id returns an equivalent state snapshot.
- Given multiple session ids, then state is isolated by session id.
- Given concurrent access to different session ids, then the store does not mix
  transcripts or metadata.
- Given concurrent access to the same session id, then v1 either serializes
  access or fails clearly with a concurrency error; it must not interleave turns
  unpredictably.
- Given process exit, then in-memory sessions are lost; this is documented as a
  v1 limitation.

### FR-5: Expose current session state

Callers must be able to retrieve current session state without reaching into
private executor fields.

Acceptance criteria:

- Given an active session, when the caller asks for current state, then the API
  returns the session id, retained messages, turn count, last run id, last
  result summary or value, and store metadata needed for restart.
- Given a session with no turns, then state retrieval returns a valid empty
  session state.
- Given trace events or execution results are available from recent runs, then
  v1 may expose summarized run metadata, but must not require retaining every
  raw trace event forever.
- Given state contains sensitive prompt or output content, then docs must make
  clear that callers own snapshot handling and redaction.

### FR-6: Restart from saved session state

The runtime must let callers restart a session from a saved state snapshot.

Acceptance criteria:

- Given a session snapshot, when the caller constructs a new session with the
  same compatible `WorkflowExecutionContext`, then subsequent prompts receive
  the restored session messages.
- Given a snapshot references a different workflow identity than the provided
  context, then restart fails clearly unless the implementation explicitly marks
  compatibility as caller-owned.
- Given the snapshot schema is missing required fields, then restart fails with
  a package-owned error.
- Given the snapshot schema version is unsupported, then restart fails clearly.

### FR-7: Integrate with async-session policy metadata

The v1 behavior should respect the existing
`runtime.execution_policy.async_session` metadata where doing so is concrete and
low-risk.

Acceptance criteria:

- Given `persist: in_memory`, then `InMemorySessionStore` is an appropriate v1
  backing store.
- Given `history: none`, then the session does not replay prior messages into
  future runs.
- Given `session_id_state_key` is configured, then the session id is available
  in run state or node outputs through a documented mechanism.
- Given async-session metadata is absent, then explicit public session
  construction still works with conservative defaults.

### FR-8: Preserve capability/status honesty

Capability reporting should distinguish metadata-only session declarations from
live in-memory session support.

Acceptance criteria:

- Given a package declares async-session metadata and no session store is
  provided, then capability/status can still report metadata-only behavior.
- Given package capability inspection receives an `InMemorySessionStore`, then
  capability/status reports live in-memory session continuity.
- Given external checkpoint persistence is requested, then v1 does not report a
  live persistent-session capability.

### FR-9: Expose a structured session snapshot summary shape

Session snapshots may carry a structured summary projection that helps callers
resume work without replaying raw transcripts.

Acceptance criteria:

- Given a caller supplies or preserves summary metadata, when
  `current_state().to_mapping()` is called, then the snapshot can include
  structured fields for intent, decisions, pending tasks, modified files,
  blockers, next action, and metrics.
- Given the runtime has no caller-provided summary metadata, then it must not
  invent model-backed summaries or infer file modifications from raw text.
- Given a snapshot with structured summary metadata is restored, then the
  metadata is preserved as caller-owned state without requiring DAR-owned
  durable storage or full-text search.
- Given summary metadata contains sensitive prompt or output content, then
  snapshot documentation must make redaction and external persistence the
  caller's responsibility.

## Non-Functional Requirements

- Session APIs must be async-first, with synchronous wrappers only where they
  match existing sync-wrapper policy.
- Session state objects must be serializable using ordinary Python data
  structures so callers can persist snapshots themselves if they choose.
- Session snapshots must include a schema version.
- The implementation must avoid global mutable session state.
- Unit tests must use fake model adapters and fake tool registries only.
- The implementation must not make live OpenAI, MCP, Hugging Face, Marimo, or
  local model calls.

## In Scope

- Public `AgentSession`-style API.
- Public `AgentSessionState` or equivalent snapshot contract.
- Public `InMemorySessionStore`.
- Passing restored session messages into workflow execution.
- Updating session transcript after successful runs.
- State retrieval and restart from saved state.
- Optional structured snapshot summary metadata for caller-owned intent,
  decisions, pending tasks, modified files, blockers, next action, and metrics.
- Focused tests for multi-turn prompt continuity, snapshot/restore,
  session isolation, and same-session concurrency behavior.
- Documentation updates that honestly distinguish in-memory v1 from durable
  persistence.

## Out of Scope

- Durable filesystem, database, Redis, cloud, or OCI-backed session stores.
- Automatic semantic memory or vector retrieval.
- Runner-owned session archive, full-text search, or durable memory database.
- Model-backed summary generation.
- Branching transcript DAGs.
- Multi-agent shared memory.
- Long-running executor processes that wait on prompts.
- Approval decision persistence or durable approval resume.
- Raw tool transcript replay by default.
- Cross-process locking.

## Data Model Expectations

The v1 implementation defines dataclasses and state with these concepts:

- session id
- schema version
- workflow identity or compatibility marker
- retained session messages
- turn count
- last run id
- last result value or compact result record
- optional caller metadata
- optional structured summary metadata with intent, decisions, pending tasks,
  modified files, blockers, next action, and metrics

Snapshots should be copy-safe: mutating a returned snapshot must not mutate the
store unless explicitly saved back.

## Error Behavior

- Empty prompts should continue to fail through existing workflow execution
  validation.
- Missing session ids should fail clearly for lookup APIs.
- Unsupported snapshot schema versions should fail clearly.
- Incompatible workflow/context restart should fail clearly.
- Same-session concurrent `accept(...)` calls should serialize or fail clearly;
  silent interleaving is forbidden.
- Interrupted workflows should return or expose the interruption consistently
  with the existing lower-level executor behavior and should not append a normal
  assistant result.

## Security and Privacy Considerations

Session snapshots contain user prompts and model outputs. They must be treated
as sensitive application data. V1 should not add hidden persistence; the
in-memory store loses data on process exit unless the caller explicitly exports
and saves a snapshot.

Tool arguments and raw tool outputs may contain secrets or workspace data, so
they must not be added to retained chat history by default.

## Relationship to Existing Specs

- `async-session-memory-pipeline` owns the metadata-only seam and future memory
  pipeline analysis. This spec owns the first live public session object and
  in-memory store behavior.
- `context-management-prepare-stage` owns pruning, compaction, lane assembly,
  and prompt preparation from supplied session messages.
- `context-management-prepare-stage` and `model-backed-context-summaries` own
  prompt-visible summaries and summarizer behavior. This spec may preserve
  caller-supplied summary metadata in snapshots, but it does not generate
  model-backed summaries.
- `iterative-agent-loop-runtime` owns bounded model-tool loops inside one run.
  This spec owns continuity between runs.
- `approval-interruption-resume` remains the owner for durable approval resume.

## Validation Checklist

The implementation provides focused tests for:

- creating a session and accepting two prompts with prior messages visible on
  the second run
- retrieving current state from an empty session and a populated session
- saving state to `InMemorySessionStore` and restarting from it
- rejecting malformed or unsupported snapshots
- isolating two session ids in the same store
- preventing or clearly rejecting concurrent same-session turn interleaving
- preserving ordinary input guardrail and approval interruption behavior
- not appending assistant history for failed or interrupted runs
- retaining only user/assistant messages by default, without raw tool payloads
- preserving caller-supplied structured snapshot summary metadata without
  generating summaries or persisting external indexes

Validation commands include:

```bash
poetry run pytest tests/test_agent_sessions.py -q
poetry run pytest tests/test_executor.py -q
poetry run ruff check src tests
```

## Resolved V1 Decisions

- `AgentSession.accept(...)` returns `AgentSessionResult`, which exposes the
  bounded `WorkflowResult` or `WorkflowInterruptedResult` plus current session
  state.
- `accept_sync(...)` is public and reuses the existing sync-wrapper event-loop
  guard.
- Workflow compatibility on restore is checked with package id plus entrypoint.
- `history: summary` preserves caller-supplied metadata only and does not
  generate summaries.
- `session_id_state_key` writes the session id into initial run `node_outputs`,
  making it available to prompt templates through the existing state formatter.

## Implementation State

The v1 baseline is implemented with TDD evidence in:

- `specs/persistent-agent-sessions/plan.md`
- `specs/persistent-agent-sessions/tasks.md`
- `specs/persistent-agent-sessions/validation.md`

Implemented scope includes public `AgentSession`, `AgentSessionState`,
`AgentSessionResult`, `InMemorySessionStore`, bounded `accept(...)`, current
state retrieval, copy-safe snapshots, snapshot restart, history policies,
session-id state injection, same-session concurrency rejection, sync wrapper
parity, documentation, and live in-memory session capability/status reporting.

Future approved slices may extend the snapshot schema with structured
caller-owned summary metadata for intent, decisions, pending tasks, modified
files, blockers, next action, and metrics. That extension should preserve and
round-trip supplied metadata only; durable stores, FTS indexes, archival session
files, and model-generated summaries remain caller-owned or separately scoped.
