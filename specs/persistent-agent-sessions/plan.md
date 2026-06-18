# Persistent Agent Sessions Implementation Plan

## Purpose

Prepare a TDD-first v1 implementation for runner-owned persistent agent
sessions. The goal is to let callers reuse a stable `WorkflowExecutionContext`
across multiple prompts, retrieve copy-safe session state, and restart a session
from a saved snapshot using `InMemorySessionStore`, while preserving the current
bounded workflow-run executor model.

## Implementation Status

V1 is implemented. The remaining scope in this document describes deferred
expansions beyond in-memory persistent agent sessions.

## Current Baseline

Observed runtime surfaces:

- `WorkflowExecutionContext` already groups reusable workflow collaborators and
  intentionally excludes the per-run prompt.
- `execute_workflow_async(...)` creates a fresh `WorkflowExecutionState` per
  run and already accepts `run_id`.
- `WorkflowExecutionState.session_messages` is the existing executor input for
  prior session context.
- `prepare_model_input(...)` already includes, prunes, compacts, and reports
  supplied `session_messages`.
- `OpenAIMessage` is the existing user/assistant message representation.
- `run_agent_workflow_async(...)` returns only final output at the high-level
  API boundary, while `execute_workflow_async(...)` exposes `WorkflowResult` and
  `WorkflowInterruptedResult`.
- `capabilities.py` currently reports `metadata.async_session` as
  metadata-only because no live session store runs.

## V1 Scope

Implement only:

- public async `AgentSession` API
- public `AgentSessionState` snapshot contract
- public `InMemorySessionStore`
- multi-turn `accept(...)` that passes retained messages into bounded executor
  runs
- copy-safe current-state retrieval and snapshot restart
- conservative same-session concurrency handling
- sync wrappers only if they reuse the existing `_run_async_from_sync(...)`
  policy
- capability/status reporting for live in-memory session support
- tests with fake adapters, fake registries, and local fixtures only

Do not implement:

- durable filesystem, database, Redis, cloud, or OCI-backed stores
- long-running graph executors waiting for prompts
- model-backed summaries
- raw tool transcript replay by default
- durable approval resume
- cross-process locking
- model event streaming

## Runtime Contract

Proposed public module:

- `src/dynamic_agent_runner/sessions.py`

Proposed public exports:

- `AgentSession`
- `AgentSessionState`
- `AgentSessionResult`
- `InMemorySessionStore`
- package-owned session errors if existing `WorkflowExecutionError` is not
  specific enough for malformed snapshots, missing sessions, or concurrent
  turns

The session object should bind:

- `execution_context: WorkflowExecutionContext`
- `session_store: InMemorySessionStore`
- `session_id: str`
- retained user/assistant `OpenAIMessage` history
- optional caller metadata

`AgentSession.accept(prompt)` should:

1. acquire the same-session turn guard
2. load current state from the store
3. build a run context whose session messages match the current retention policy
4. call `execute_workflow_async(...)` as a normal bounded run
5. append the user prompt and assistant final result only after successful
   completion
6. save the updated state to the store
7. return a session result that exposes the workflow result and current session
   state

Failed or interrupted runs must not append a normal assistant turn.

## Key Plan Decisions

- Use a new `sessions.py` module instead of expanding `api.py` or `executor.py`;
  this keeps session continuity outside the bounded executor.
- Store only user and assistant chat messages by default; tool arguments and raw
  tool outputs remain out of retained chat history.
- Use `OpenAIMessage` for retained transcript messages so
  `prepare_model_input(...)` can consume session history without a translator.
- Represent snapshots as frozen dataclasses with ordinary Python mapping/list
  conversion helpers. Returned snapshots must be copy-safe.
- Treat workflow compatibility as strict enough for v1 to catch obvious
  mismatches. Prefer package id plus entrypoint when available; if neither is
  available, record a stable best-effort identity and fail clearly only when a
  snapshot identity conflicts with the current context identity.
- Reject same-session concurrent `accept(...)` calls clearly in v1 rather than
  attempting queued serialization. Different session ids may proceed
  independently.
- Preserve high-level sync-wrapper policy: sync session methods may exist only
  as wrappers over async methods and must fail inside a running event loop.

## Implementation Slices

### Slice 1: Session State and Store

Add snapshot/state and in-memory store contracts without invoking the executor.

Likely files:

- `src/dynamic_agent_runner/sessions.py`
- `src/dynamic_agent_runner/__init__.py`
- `tests/test_agent_sessions.py`

TDD focus:

- empty state creation
- generated and explicit session ids
- copy-safe snapshot retrieval
- store isolation by session id
- malformed and unsupported snapshot rejection

Validation:

```bash
poetry run pytest tests/test_agent_sessions.py -q
```

### Slice 2: Bounded `accept(...)` Continuity

Wire `AgentSession.accept(...)` to `execute_workflow_async(...)` and retained
messages.

Likely files:

- `src/dynamic_agent_runner/sessions.py`
- `src/dynamic_agent_runner/executor.py`
- `tests/test_agent_sessions.py`
- `tests/test_executor.py` only if executor seams need regression coverage

TDD focus:

- second prompt receives prior user/assistant messages
- successful run appends exactly one user turn and one assistant turn
- failed run does not append an assistant turn
- interrupted run does not append a normal assistant turn
- each prompt still creates a bounded executor run with normal guardrail and
  approval behavior

Validation:

```bash
poetry run pytest tests/test_agent_sessions.py tests/test_executor.py -q
```

### Slice 3: Retention Policy and Snapshot Restart

Apply concrete async-session history behavior and restart from saved state.

Likely files:

- `src/dynamic_agent_runner/sessions.py`
- `src/dynamic_agent_runner/models.py` only if existing policy accessors need a
  small helper
- `tests/test_agent_sessions.py`
- `tests/test_validation.py` only if metadata validation changes

TDD focus:

- `history: none` does not replay prior messages
- `history: last_turn` retains only the previous user/assistant pair
- `history: full` supplies all retained user/assistant messages
- `history: summary` preserves caller-supplied summary metadata only and does
  not generate a model-backed summary
- restart from snapshot restores retained messages
- incompatible workflow identities fail clearly

Validation:

```bash
poetry run pytest tests/test_agent_sessions.py tests/test_validation.py -q
```

### Slice 4: Public API, Sync Wrappers, and Capability Status

Expose the public surface and report live in-memory session capability.

Likely files:

- `src/dynamic_agent_runner/api.py`
- `src/dynamic_agent_runner/__init__.py`
- `src/dynamic_agent_runner/capabilities.py`
- `tests/test_agent_sessions.py`
- `tests/test_capabilities.py`
- `README.md` and relevant `docs/files/` pages if the public API is documented

TDD focus:

- public imports work
- sync wrappers return the same session result shape outside an event loop
- sync wrappers fail through existing event-loop policy inside a running loop
- capability/status keeps metadata-only async-session reporting without a store
- capability/status reports live in-memory session support when a session store
  is supplied through the selected public inspection seam

Validation:

```bash
poetry run pytest tests/test_agent_sessions.py tests/test_capabilities.py -q
poetry run ruff check src tests
```

## Test Strategy

Use TDD for every behavior-changing slice:

1. add one focused failing test in `tests/test_agent_sessions.py` or a nearby
   existing test file
2. run the narrowest command and confirm RED fails for the expected reason
3. implement the smallest production change for GREEN
4. rerun the targeted command
5. refactor only after GREEN, then rerun the same command

Use fake model adapters and local workflow fixtures. Do not make live OpenAI,
MCP, Hugging Face, Marimo, llama.cpp, MLX, or local model calls.

## Risks

- Silent transcript mutation: returned state and snapshots must be copy-safe.
- Executor boundary creep: session logic must remain outside the bounded
  executor, with executor changes limited to explicit seams needed to pass
  `session_messages`.
- History-policy confusion: `history: summary` must not imply model-backed
  summarization in v1.
- Trace or tool leakage: retained chat history must not include raw tool
  arguments or raw tool outputs by default.
- Concurrency ambiguity: same-session overlap must fail clearly unless a later
  plan chooses queued serialization.

## Readiness

This plan is ready for implementation after `tasks.md` is accepted as the active
execution checklist. The first implementation step should be Slice 1, Task 1.1,
starting with a failing `tests/test_agent_sessions.py` assertion.
