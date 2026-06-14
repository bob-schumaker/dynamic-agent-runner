# Live Guardrail Execution V1 Tasks

Status: planned next implementation slice

## Slice 0 — Planning Checkpoint

- [x] T0.1 Resolve v1 phase, adapter, decision, subject, and deferred behavior
      decisions in `spec.md`.
- [x] T0.2 Add `plan.md`, `tasks.md`, and `validation.md` before
      implementation.
- [x] T0.3 Commit the planning checkpoint before code changes.
  - Completed in commit `eb6eb98`
    (`docs(specs): plan input guardrail slice`)

## Slice 1 — Public Guardrail Contract

- [x] T1.1 [tests] Add RED import/shape tests for guardrail decisions, results,
      and registry helpers.
  - Spec: FR-2, FR-3
  - Files/components: `tests/test_guardrails.py`,
    `src/dynamic_agent_runner/guardrails.py`,
    `src/dynamic_agent_runner/__init__.py`
  - Validation:
    `poetry run pytest tests/test_guardrails.py tests/test_import.py -q`
  - RED:
    - `poetry run pytest tests/test_guardrails.py tests/test_import.py -q` —
      failed because guardrail contract exports were missing

- [x] T1.2 [implementation] Add public guardrail result types and a simple
      caller-owned guardrail registry.
  - Spec: FR-2, FR-3
  - Files/components: `src/dynamic_agent_runner/guardrails.py`,
    `src/dynamic_agent_runner/__init__.py`
  - Validation:
    `poetry run pytest tests/test_guardrails.py tests/test_import.py -q`
  - GREEN:
    - `poetry run pytest tests/test_guardrails.py tests/test_import.py -q` —
      `4 passed in 0.11s`

## Slice 2 — Input Guardrail Enforcement

- [x] T2.1 [tests] Add RED tests for missing input guardrail adapters and abort
      decisions before model/tool execution.
  - Spec: FR-1, FR-2, FR-4, FR-6
  - Files/components: `tests/test_executor.py`, `tests/test_tracing.py`
  - Validation:
    `poetry run pytest tests/test_executor.py tests/test_tracing.py -q`
  - RED:
    - `poetry run pytest tests/test_executor.py tests/test_tracing.py -q` —
      failed during collection because `GuardrailExecutionError` was missing

- [x] T2.2 [implementation] Execute input guardrails before the first node and
      abort fail-closed before any model/tool action.
  - Spec: FR-1, FR-2, FR-4, FR-6
  - Files/components: `src/dynamic_agent_runner/executor.py`,
    `src/dynamic_agent_runner/context.py`
  - Validation:
    `poetry run pytest tests/test_executor.py tests/test_tracing.py -q`
  - GREEN:
    - `poetry run pytest tests/test_executor.py tests/test_tracing.py -q` —
      `87 passed in 0.47s`

## Slice 3 — Capability Status

- [ ] T3.1 [tests] Add RED tests for live input guardrail coverage and missing
      guardrail collaborator reporting.
  - Spec: FR-2, FR-6
  - Files/components: `tests/test_capabilities.py`
  - Validation:
    `poetry run pytest tests/test_capabilities.py tests/test_guardrails.py -q`

- [ ] T3.2 [implementation] Report guardrail metadata separately from live
      input guardrail adapter coverage.
  - Spec: FR-2, FR-6
  - Files/components: `src/dynamic_agent_runner/capabilities.py`
  - Validation:
    `poetry run pytest tests/test_capabilities.py tests/test_guardrails.py -q`

## Slice 4 — Completion Evidence

- [ ] T4.1 [validation] Run focused affected tests.
  - Command:
    `poetry run pytest tests/test_guardrails.py tests/test_executor.py`
    `tests/test_tracing.py tests/test_capabilities.py tests/test_import.py -q`

- [ ] T4.2 [validation] Run focused pre-commit.
  - Command:
    `pre-commit run --files src/dynamic_agent_runner/guardrails.py`
    `src/dynamic_agent_runner/executor.py`
    `src/dynamic_agent_runner/context.py`
    `src/dynamic_agent_runner/capabilities.py`
    `src/dynamic_agent_runner/__init__.py tests/test_guardrails.py`
    `tests/test_executor.py tests/test_tracing.py`
    `tests/test_capabilities.py tests/test_import.py`
    `specs/live-guardrail-execution/spec.md`
    `specs/live-guardrail-execution/plan.md`
    `specs/live-guardrail-execution/tasks.md`
    `specs/live-guardrail-execution/validation.md specs/README.md`

- [ ] T4.3 [docs] Record completion evidence and update spec status before the
      next focus area.
