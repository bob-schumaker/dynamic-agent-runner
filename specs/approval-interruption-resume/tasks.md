# Approval Interruption and Sandbox V1 Tasks

Status: planned next implementation slice

## Slice 0 — Planning Checkpoint

- [x] T0.1 Resolve v1 public API, non-goals, and executor boundary in
      `spec.md`.
- [x] T0.2 Add `plan.md`, `tasks.md`, and `validation.md` before
      implementation.
- [x] T0.3 Commit the planning checkpoint before code changes.
  - Completed in commit `2fe5b94`
    (`docs(specs): plan approval interruption slice`)

## Slice 1 — Public Interruption Contract

- [x] T1.1 [tests] Add RED import/shape tests for approval interruption result
      types.
  - Spec: approval-interruption-resume FR-2, FR-5
  - Files/components: `tests/test_executor.py`,
    `src/dynamic_agent_runner/executor.py`,
    `src/dynamic_agent_runner/__init__.py`
  - Validation: `poetry run pytest tests/test_import.py tests/test_executor.py -q`
  - RED:
    - `poetry run pytest tests/test_import.py tests/test_executor.py -q` —
      failed during collection because `ApprovalInterruption` was not exported
      from `dynamic_agent_runner.executor`

- [x] T1.2 [implementation] Add public approval interruption dataclasses and
      package exports.
  - Spec: approval-interruption-resume FR-2, FR-5
  - Files/components: `src/dynamic_agent_runner/executor.py`,
    `src/dynamic_agent_runner/__init__.py`
  - Validation: `poetry run pytest tests/test_import.py tests/test_executor.py -q`
  - GREEN:
    - `poetry run pytest tests/test_import.py tests/test_executor.py -q` —
      `74 passed in 0.45s`

## Slice 2 — Direct Tool Pause Before Invocation

- [x] T2.1 [tests] Add RED test proving an approval-required direct
      `tool_use_step` must not invoke its handler.
  - Spec: approval-interruption-resume FR-1, FR-2, FR-6;
    sandbox-workspace-runtime FR-3
  - Files/components: `tests/test_executor.py`, `tests/test_tracing.py`
  - Validation:
    `poetry run pytest tests/test_executor.py tests/test_tracing.py -q`
  - RED:
    - `poetry run pytest tests/test_executor.py tests/test_tracing.py -q` —
      failed because approval-required direct tool steps still invoked handlers
      and returned `WorkflowResult`

- [x] T2.2 [implementation] Pause direct approval-required tool steps before
      lifecycle hooks, retry, registry invocation, output recording, or edge
      traversal.
  - Spec: approval-interruption-resume FR-1, FR-2, FR-5, FR-6;
    sandbox-workspace-runtime FR-3
  - Files/components: `src/dynamic_agent_runner/executor.py`
  - Validation:
    `poetry run pytest tests/test_executor.py tests/test_tracing.py -q`
  - GREEN:
    - `poetry run pytest tests/test_executor.py tests/test_tracing.py -q` —
      `82 passed in 0.44s`

## Slice 3 — High-Level API Boundary and Capability Status

- [x] T3.1 [tests] Add RED tests that `run_agent_workflow*` fail clearly on an
      interrupted workflow and capability status reports live approval
      interruption when v1 prerequisites are present.
  - Spec: approval-interruption-resume FR-2, FR-5;
    capability-status-report FR-3
  - Files/components: `tests/test_executor.py`, `tests/test_capabilities.py`
  - Validation:
    `poetry run pytest tests/test_executor.py tests/test_capabilities.py -q`
  - RED:
    - `poetry run pytest tests/test_executor.py tests/test_capabilities.py -q` —
      failed because high-level APIs did not raise on interruption and
      capability status omitted `runtime.approval_interruption`

- [x] T3.2 [implementation] Add high-level API guardrails and update capability
      status reporting for v1 approval interruption.
  - Spec: approval-interruption-resume FR-2, FR-5;
    capability-status-report FR-3
  - Files/components: `src/dynamic_agent_runner/api.py`,
    `src/dynamic_agent_runner/capabilities.py`
  - Validation:
    `poetry run pytest tests/test_executor.py tests/test_capabilities.py -q`
  - GREEN:
    - `poetry run pytest tests/test_executor.py tests/test_capabilities.py -q` —
      `82 passed in 0.44s`

## Slice 4 — Completion Evidence

- [ ] T4.1 [validation] Run focused affected tests.
  - Command:
    `poetry run pytest tests/test_executor.py tests/test_tracing.py`
    `tests/test_capabilities.py tests/test_import.py -q`

- [ ] T4.2 [validation] Run focused pre-commit.
  - Command:
    `pre-commit run --files src/dynamic_agent_runner/executor.py`
    `src/dynamic_agent_runner/api.py src/dynamic_agent_runner/capabilities.py`
    `src/dynamic_agent_runner/__init__.py tests/test_executor.py`
    `tests/test_tracing.py tests/test_capabilities.py tests/test_import.py`
    `specs/approval-interruption-resume/spec.md`
    `specs/approval-interruption-resume/plan.md`
    `specs/approval-interruption-resume/tasks.md`
    `specs/approval-interruption-resume/validation.md`
    `specs/sandbox-workspace-runtime/spec.md specs/README.md`

- [ ] T4.3 [docs] Record completion evidence and update spec status before the
      next focus area.
