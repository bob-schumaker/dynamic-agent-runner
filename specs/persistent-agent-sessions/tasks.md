# Persistent Agent Sessions Tasks

## Metadata

- Feature slug: `persistent-agent-sessions`
- Spec: `specs/persistent-agent-sessions/spec.md`
- Plan: `specs/persistent-agent-sessions/plan.md`
- Status: prepared for TDD implementation

## TDD Rule

Each behavior task below must start with RED:

1. add or update the focused test
2. run the named targeted command and confirm the expected failure
3. implement the smallest GREEN change
4. rerun the command and inspect the result
5. refactor only after GREEN

Record command outcomes in `validation.md` as slices complete.

## Slice 1: Session State and Store

- [x] T1.1 Add a failing `tests/test_agent_sessions.py` test proving a new
      `AgentSession` can be created with an explicit session id and returns an
      empty `AgentSessionState`.
- [x] T1.2 Add `src/dynamic_agent_runner/sessions.py` with `AgentSessionState`,
      `InMemorySessionStore`, and minimal `AgentSession.create(...)` behavior.
- [x] T1.3 Add RED/GREEN coverage for generated session ids when no id is
      supplied.
- [x] T1.4 Add RED/GREEN coverage proving `current_state()` and store lookups
      return copy-safe snapshots.
- [x] T1.5 Add RED/GREEN coverage proving two session ids in one
      `InMemorySessionStore` remain isolated.
- [x] T1.6 Add RED/GREEN coverage for missing session lookup, malformed
      snapshot, and unsupported snapshot schema version failures using
      package-owned errors.
- [x] T1.7 Export public session types from `dynamic_agent_runner.__init__`.
- [x] T1.8 Run targeted validation:
      `poetry run pytest tests/test_agent_sessions.py -q`.

## Slice 2: Bounded `accept(...)` Continuity

- [ ] T2.1 Add a failing test proving the second `await session.accept(...)`
      call passes the first prompt/result as `session_messages` into the next
      bounded workflow run.
- [ ] T2.2 Implement async `AgentSession.accept(...)` by loading current state,
      invoking `execute_workflow_async(...)`, and saving retained messages only
      after success.
- [ ] T2.3 Add RED/GREEN coverage proving a successful run appends exactly one
      user message and one assistant message.
- [ ] T2.4 Add RED/GREEN coverage proving workflow execution failures do not
      append an assistant turn.
- [ ] T2.5 Add RED/GREEN coverage proving approval interruption returns or
      exposes the interruption consistently and does not append a normal
      assistant turn.
- [ ] T2.6 Add RED/GREEN coverage proving existing input guardrail behavior
      still runs before model/tool execution inside `accept(...)`.
- [ ] T2.7 Run targeted validation:
      `poetry run pytest tests/test_agent_sessions.py tests/test_executor.py -q`.

## Slice 3: Retention Policy and Snapshot Restart

- [ ] T3.1 Add RED/GREEN coverage for `history: none` proving prior turns are
      stored if needed for inspection but not replayed into future runs.
- [ ] T3.2 Add RED/GREEN coverage for `history: last_turn` proving only the
      previous user/assistant pair is replayed.
- [ ] T3.3 Add RED/GREEN coverage for `history: full` proving all retained
      user/assistant messages are replayed.
- [ ] T3.4 Add RED/GREEN coverage for `history: summary` proving v1 preserves
      caller-supplied summary metadata only and does not call a model to create
      summaries.
- [ ] T3.5 Add RED/GREEN coverage proving `session_id_state_key` makes the
      session id available through the documented run-state mechanism chosen in
      implementation.
- [ ] T3.6 Add RED/GREEN coverage proving `AgentSession.from_snapshot(...)`
      restarts a session with restored messages.
- [ ] T3.7 Add RED/GREEN coverage proving incompatible workflow identity,
      malformed snapshots, and unsupported schema versions fail clearly.
- [ ] T3.8 Run targeted validation:
      `poetry run pytest tests/test_agent_sessions.py tests/test_validation.py -q`.

## Slice 4: Concurrency, Public API, and Capability Status

- [ ] T4.1 Add RED/GREEN coverage proving overlapping same-session
      `accept(...)` calls fail clearly rather than interleaving turns.
- [ ] T4.2 Add RED/GREEN coverage proving different session ids in one store can
      accept prompts without transcript mixing.
- [ ] T4.3 Add public high-level helpers in `api.py` only if they reduce caller
      boilerplate without duplicating `AgentSession.create(...)`.
- [ ] T4.4 Add sync wrappers only if they reuse `_run_async_from_sync(...)` and
      preserve the existing "no sync wrapper inside a running event loop"
      behavior.
- [ ] T4.5 Add capability/status tests proving async-session metadata remains
      metadata-only without live session use.
- [ ] T4.6 Add capability/status tests and implementation for live
      `InMemorySessionStore` support through the selected public inspection
      seam.
- [ ] T4.7 Run targeted validation:
      `poetry run pytest tests/test_agent_sessions.py`
      `tests/test_capabilities.py -q`.

## Slice 5: Documentation and Completion Evidence

- [ ] T5.1 Update `README.md` and relevant `docs/files/` pages with the public
      session API, in-memory-only limitation, snapshot sensitivity, and
      bounded-run behavior.
- [ ] T5.2 Update `specs/README.md` to mark the implemented baseline only after
      the code and tests pass.
- [ ] T5.3 Update this task list with completed checkboxes as slices land.
- [ ] T5.4 Update `validation.md` with exact RED/GREEN/refactor command
      outcomes.
- [ ] T5.5 Run final focused validation:
      `poetry run pytest tests/test_agent_sessions.py tests/test_executor.py`
      `tests/test_capabilities.py -q`.
- [ ] T5.6 Run final lint:
      `poetry run ruff check src tests`.
- [ ] T5.7 Run `pre-commit run --files ...` for all changed files in the
      implementation slice.
- [ ] T5.8 Refresh `memory-bank/activeContext.md` and `memory-bank/progress.md`
      after implementation milestones if requested by the active workflow.

## Done Definition

- `AgentSession` can accept multiple prompts against one reusable
  `WorkflowExecutionContext`.
- `InMemorySessionStore` isolates session ids and returns copy-safe snapshots.
- Current state and saved snapshots can restart compatible sessions.
- Same-session concurrent `accept(...)` calls cannot interleave turns silently.
- Failed and interrupted runs do not append normal assistant turns.
- History policies `none`, `last_turn`, `full`, and v1 `summary` behavior are
  covered by tests.
- Capability/status distinguishes metadata-only async-session declarations from
  live in-memory session support.
- Tests use fake adapters and local fixtures only.
