# Iterative Agent-Loop Runtime V1 Tasks

Status: v1 baseline complete

## Slice 0 — Planning Checkpoint

- [x] T0.1 Resolve v1 boundary in `spec.md`.
- [x] T0.2 Add `plan.md`, `tasks.md`, and `validation.md` before code changes.
- [x] T0.3 Commit the planning checkpoint before implementation.
  - Completed by the planning checkpoint commit containing this task update.

## Slice 1 — Activation and No-Drift Baseline

- [x] T1.1 [tests] Add executor coverage proving existing `llm_step` behavior is
      unchanged when `tool_use_completion.run_again` is absent.
  - Spec: FR-1
  - Files/components: `tests/test_executor.py`
  - Validation: `poetry run pytest tests/test_executor.py -q`
  - GREEN:
    - `poetry run pytest tests/test_executor.py -q` — `79 passed in 0.54s`

- [x] T1.2 [implementation] Add an internal policy check that only enters loop
      execution when `run_again` is `required`.
  - Spec: FR-1
  - Files/components: `src/dynamic_agent_runner/executor.py`
  - Validation: `poetry run pytest tests/test_executor.py -q`
  - GREEN:
    - `poetry run pytest tests/test_executor.py -q` — `79 passed in 0.54s`

## Slice 2 — Serial Model Tool Dispatch

- [x] T2.1 [tests] Add RED coverage for one model-emitted tool call followed by
      a second model turn that sees the tool result.
  - Spec: FR-2, FR-3, FR-4, FR-6
  - Files/components: `tests/test_executor.py`
  - Validation: `poetry run pytest tests/test_executor.py -q`
  - RED:
    - `poetry run pytest tests/test_executor.py -q` — failed because the
      workflow returned after the first model tool call instead of dispatching
      the tool and issuing a second model request.

- [x] T2.2 [implementation] Dispatch serial model tool calls through
      `ToolRegistry`, append model-facing tool result messages, and re-call the
      same model until final/no-tool response.
  - Spec: FR-2, FR-3, FR-4, FR-6
  - Files/components: `src/dynamic_agent_runner/executor.py`
  - Validation: `poetry run pytest tests/test_executor.py -q`
  - GREEN:
    - `poetry run pytest tests/test_executor.py -q` — `80 passed in 0.41s`

## Slice 3 — Safety and Failure Boundaries

- [x] T3.1 [tests] Add RED coverage for unexposed tools, hidden tools, malformed
      arguments, tool failures, max iteration exhaustion, and
      approval-required model tool calls.
  - Spec: FR-2, FR-3, FR-5
  - Files/components: `tests/test_executor.py`, `tests/test_registry.py`
  - Validation:
    `poetry run pytest tests/test_executor.py tests/test_registry.py -q`
  - RED:
    - `poetry run pytest tests/test_executor.py -q` — failed because hidden
      model tools were silently ignored and approval-required model tools did
      not pause before invocation.

- [x] T3.2 [implementation] Fail closed for unauthorized or malformed model tool
      calls, apply bounded max iterations, preserve direct tool approval
      semantics, and stop before approval-required model tool invocation.
  - Spec: FR-2, FR-3, FR-5
  - Files/components: `src/dynamic_agent_runner/executor.py`
  - Validation:
    `poetry run pytest tests/test_executor.py tests/test_registry.py -q`
  - GREEN:
    - `poetry run pytest tests/test_executor.py -q` — `86 passed in 0.42s`
    - `poetry run pytest tests/test_executor.py tests/test_registry.py -q` —
      `118 passed in 0.45s`

## Slice 4 — Trace, Status, and Completion Evidence

- [x] T4.1 [tests] Add trace assertions for loop lifecycle and final output
      selection.
  - Spec: FR-6
  - Files/components: `tests/test_executor.py`, `tests/test_tracing.py`
  - Validation:
    `poetry run pytest tests/test_executor.py tests/test_tracing.py -q`
  - RED:
    - `poetry run pytest tests/test_executor.py -q` — failed because the loop
      emitted no dedicated lifecycle or final-output trace events.

- [x] T4.2 [implementation] Emit loop trace events with redacted content,
      arguments, and outputs.
  - Spec: FR-6
  - Files/components: `src/dynamic_agent_runner/executor.py`
  - Validation:
    `poetry run pytest tests/test_executor.py tests/test_tracing.py -q`
  - GREEN:
    - `poetry run pytest tests/test_executor.py tests/test_tracing.py -q` —
      `96 passed in 0.42s`

- [x] T4.3 [validation] Run focused affected tests.
  - Command:
    `poetry run pytest tests/test_executor.py tests/test_registry.py`
    `tests/test_tracing.py tests/test_capabilities.py tests/test_import.py -q`
  - Result: `137 passed in 0.48s`

- [x] T4.4 [validation] Run focused pre-commit.
  - Command:
    `pre-commit run --files src/dynamic_agent_runner/executor.py`
    `tests/test_executor.py tests/test_registry.py tests/test_tracing.py`
    `tests/test_capabilities.py tests/test_import.py`
    `specs/iterative-agent-loop-runtime/spec.md`
    `specs/iterative-agent-loop-runtime/plan.md`
    `specs/iterative-agent-loop-runtime/tasks.md`
    `specs/iterative-agent-loop-runtime/validation.md specs/README.md`
  - Result: passed

- [x] T4.5 [docs] Record completion evidence and update spec status before the
      next focus area.
