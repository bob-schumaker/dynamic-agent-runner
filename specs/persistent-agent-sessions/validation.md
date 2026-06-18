# Persistent Agent Sessions Validation

## Metadata

- Feature slug: `persistent-agent-sessions`
- Spec: `specs/persistent-agent-sessions/spec.md`
- Plan: `specs/persistent-agent-sessions/plan.md`
- Tasks: `specs/persistent-agent-sessions/tasks.md`
- Status: v1 implementation validation complete

## Preparation Evidence

Repository discovery for this preparation pass confirmed the intended seams:

- `WorkflowExecutionContext` is reusable and excludes per-run prompt state.
- `WorkflowExecutionState.session_messages` already carries prior session
  messages into prompt preparation.
- `prepare_model_input(...)` already handles supplied session messages.
- `OpenAIMessage` is the existing model-message type for retained user and
  assistant turns.
- `capabilities.py` currently reports async-session metadata as metadata-only.
- Existing tests use fake model adapters and local workflow fixtures.

## TDD Validation Log

Future implementation slices must append exact outcomes in this format:

```text
Slice N / Task Tn.n:
- RED: `<command>` — fail — <expected failure>
- GREEN: `<command>` — pass — <observed result>
- Refactor: `<command>` — pass|not run — <observed result>
```

Slice 1 / Tasks T1.1-T1.8:

- RED: `poetry run pytest tests/test_agent_sessions.py -q` - fail - import
  failed because `AgentSessionError` and the session surface did not exist.
- GREEN: `poetry run pytest tests/test_agent_sessions.py -q` - pass - six
  session state/store tests passed.
- Refactor: not run - no post-GREEN refactor was needed.

Slice 2 / Tasks T2.1-T2.7:

- RED: `poetry run pytest tests/test_agent_sessions.py -q` - fail - four
  `accept(...)` tests failed because `AgentSession.accept` did not exist.
- GREEN: `poetry run pytest tests/test_agent_sessions.py -q` - pass - ten
  session tests passed after adding bounded `accept(...)` execution and the
  executor `session_messages` seam.
- Refactor: `poetry run pytest tests/test_agent_sessions.py`
  `tests/test_executor.py -q` - pass - 115 tests passed. The first sandboxed
  run failed in two existing token-budget tests because `tiktoken` attempted to
  fetch a missing encoding cache; rerunning the same command with network
  access passed.

Slice 3 / Tasks T3.1-T3.8:

- RED: `poetry run pytest tests/test_agent_sessions.py -q` - fail - six
  history, state-key, and snapshot restart tests failed because replay policy,
  `session_id_state_key` injection, and `from_snapshot(...)` were missing.
- GREEN: `poetry run pytest tests/test_agent_sessions.py -q` - pass - 17
  session tests passed.
- Refactor: `poetry run pytest tests/test_agent_sessions.py`
  `tests/test_validation.py -q` - pass - 81 tests passed.

Slice 4 / Tasks T4.1-T4.7:

- RED: `poetry run pytest tests/test_agent_sessions.py`
  `tests/test_capabilities.py -q` - fail - four tests failed because
  same-session overlap rejection, `accept_sync(...)`, and live session
  capability reporting were missing.
- GREEN: `poetry run pytest tests/test_agent_sessions.py`
  `tests/test_capabilities.py -q` - pass - 35 tests passed.
- Refactor: `poetry run pytest tests/test_agent_sessions.py`
  `tests/test_capabilities.py -q` - pass - 35 tests passed after extracting
  async-session capability item construction to keep complexity within the
  lint threshold.

Slice 5 / Tasks T5.1-T5.8:

- RED: not applicable - Slice 5 was documentation, status, and completion
  evidence for already implemented behavior.
- GREEN: `poetry run pytest tests/test_agent_sessions.py tests/test_executor.py`
  `tests/test_capabilities.py -q` - pass - 140 tests passed.
- Refactor: `poetry run ruff check src tests` - pass - all checks passed.

## Planned Commands

Targeted implementation commands:

```bash
poetry run pytest tests/test_agent_sessions.py -q
poetry run pytest tests/test_agent_sessions.py tests/test_executor.py -q
poetry run pytest tests/test_agent_sessions.py tests/test_validation.py -q
poetry run pytest tests/test_agent_sessions.py tests/test_capabilities.py -q
```

Final focused commands:

```bash
poetry run pytest tests/test_agent_sessions.py tests/test_executor.py \
  tests/test_capabilities.py -q
poetry run ruff check src tests
pre-commit run --files <changed files>
```

## Preparation Gate

- Spec exists and defines the v1 behavior boundary.
- Plan exists and chooses a TDD-first implementation sequence.
- Tasks exist and require RED/GREEN/refactor validation per behavior slice.
- No production code has been changed.
