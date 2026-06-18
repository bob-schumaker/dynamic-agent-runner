# Persistent Agent Sessions Validation

## Metadata

- Feature slug: `persistent-agent-sessions`
- Spec: `specs/persistent-agent-sessions/spec.md`
- Plan: `specs/persistent-agent-sessions/plan.md`
- Tasks: `specs/persistent-agent-sessions/tasks.md`
- Status: preparation validation only; implementation has not started

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

No RED/GREEN implementation cycles have run yet. Future implementation slices
must append exact outcomes in this format:

```text
Slice N / Task Tn.n:
- RED: `<command>` — fail — <expected failure>
- GREEN: `<command>` — pass — <observed result>
- Refactor: `<command>` — pass|not run — <observed result>
```

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
