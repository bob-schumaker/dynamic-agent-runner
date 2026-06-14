# Iterative Agent-Loop Runtime V1 Tasks

Status: prepared for implementation

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

- [ ] T2.1 [tests] Add RED coverage for one model-emitted tool call followed by
      a second model turn that sees the tool result.
  - Spec: FR-2, FR-3, FR-4, FR-6
  - Files/components: `tests/test_executor.py`
  - Validation: `poetry run pytest tests/test_executor.py -q`

- [ ] T2.2 [implementation] Dispatch serial model tool calls through
      `ToolRegistry`, append model-facing tool result messages, and re-call the
      same model until final/no-tool response.
  - Spec: FR-2, FR-3, FR-4, FR-6
  - Files/components: `src/dynamic_agent_runner/executor.py`
  - Validation: `poetry run pytest tests/test_executor.py -q`

## Slice 3 — Safety and Failure Boundaries

- [ ] T3.1 [tests] Add RED coverage for unexposed tools, hidden tools, malformed
      arguments, tool failures, max iteration exhaustion, and
      approval-required model tool calls.
  - Spec: FR-2, FR-3, FR-5
  - Files/components: `tests/test_executor.py`, `tests/test_registry.py`
  - Validation:
    `poetry run pytest tests/test_executor.py tests/test_registry.py -q`

- [ ] T3.2 [implementation] Fail closed for unauthorized or malformed model tool
      calls, apply bounded max iterations, preserve direct tool approval
      semantics, and stop before approval-required model tool invocation.
  - Spec: FR-2, FR-3, FR-5
  - Files/components: `src/dynamic_agent_runner/executor.py`
  - Validation:
    `poetry run pytest tests/test_executor.py tests/test_registry.py -q`

## Slice 4 — Trace, Status, and Completion Evidence

- [ ] T4.1 [tests] Add trace assertions for loop lifecycle and final output
      selection.
  - Spec: FR-6
  - Files/components: `tests/test_executor.py`, `tests/test_tracing.py`
  - Validation:
    `poetry run pytest tests/test_executor.py tests/test_tracing.py -q`

- [ ] T4.2 [implementation] Emit loop trace events with redacted content,
      arguments, and outputs.
  - Spec: FR-6
  - Files/components: `src/dynamic_agent_runner/executor.py`
  - Validation:
    `poetry run pytest tests/test_executor.py tests/test_tracing.py -q`

- [ ] T4.3 [validation] Run focused affected tests.
  - Command:
    `poetry run pytest tests/test_executor.py tests/test_registry.py`
    `tests/test_tracing.py tests/test_capabilities.py tests/test_import.py -q`

- [ ] T4.4 [validation] Run focused pre-commit.
  - Command:
    `pre-commit run --files src/dynamic_agent_runner/executor.py`
    `tests/test_executor.py tests/test_registry.py tests/test_tracing.py`
    `tests/test_capabilities.py tests/test_import.py`
    `specs/iterative-agent-loop-runtime/spec.md`
    `specs/iterative-agent-loop-runtime/plan.md`
    `specs/iterative-agent-loop-runtime/tasks.md`
    `specs/iterative-agent-loop-runtime/validation.md specs/README.md`

- [ ] T4.5 [docs] Record completion evidence and update spec status before the
      next focus area.
