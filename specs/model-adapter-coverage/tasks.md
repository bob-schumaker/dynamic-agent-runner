# Model Adapter Coverage Task List

Status: ready for implementation

## Prerequisites

- Spec: `specs/model-adapter-coverage/spec.md`
- Plan: `specs/model-adapter-coverage/plan.md`
- Public policy values: `"augmented"` and `"strict"`
- Default policy: `"augmented"`

## Scope Rule

Keep this change limited to client-facing adapter coverage policy and executor
selection. Do not add provider discovery, local server startup, Hugging Face
download behavior, or workflow-manifest schema fields.

## Slice 1 — Public Contract Tests

- [ ] T1.1 [tests] Add RED tests that high-level sync and async APIs accept
      `model_adapter_coverage`.
  - Spec: FR-1, FR-2, FR-6
  - Plan: Implementation Shape
  - Files/components: `tests/test_executor.py`, `src/dynamic_agent_runner/api.py`
  - Validation: `poetry run pytest tests/test_executor.py -q`
  - Expected RED: keyword is not accepted or ignored before implementation.

- [ ] T1.2 [tests] Add RED tests that lower-level executor APIs and
      `WorkflowExecutionContext` accept and apply `model_adapter_coverage`.
  - Spec: FR-1, FR-2, FR-6
  - Plan: Implementation Shape
  - Files/components: `tests/test_executor.py`,
    `src/dynamic_agent_runner/context.py`,
    `src/dynamic_agent_runner/executor.py`
  - Validation: `poetry run pytest tests/test_executor.py -q`
  - Expected RED: context or executor does not carry the policy.

- [ ] T1.3 [tests] Add RED tests for strict missing-coverage failures.
  - Spec: FR-2, FR-3
  - Plan: Error Contract
  - Files/components: `tests/test_executor.py`
  - Cases:
    - `model_adapter=None`, strict
    - `model_adapter=[]`, strict
    - nonmatching supplied adapter, strict
    - required capabilities unavailable from supplied adapters, strict
  - Validation: `poetry run pytest tests/test_executor.py -q`
  - Expected RED: default OpenAI adapter or first supplied adapter is still used.

- [ ] T1.4 [tests] Add RED tests for augmented default OpenAI coverage.
  - Spec: FR-1, FR-5
  - Plan: Planning Decisions
  - Files/components: `tests/test_executor.py`
  - Cases:
    - omitted policy preserves default OpenAI adapter creation
    - supplied nonmatching adapter plus augmented policy uses default OpenAI
      adapter for eligible requested model
    - supplied nonmatching adapter plus omitted policy behaves as augmented
  - Validation: `poetry run pytest tests/test_executor.py -q`
  - Expected RED: provided adapter list remains authoritative.

- [ ] T1.5 [tests] Replace local-only routing tests with strict coverage tests.
  - Spec: FR-4
  - Plan: Existing Implementation Context
  - Files/components: `tests/test_executor.py`
  - Validation: `poetry run pytest tests/test_executor.py -q`
  - Expected RED: current implementation still filters adapters by `is_local`
    for `local_only` metadata.

## Slice 2 — API and Context Wiring

- [ ] T2.1 [implementation] Add `model_adapter_coverage` to
      `WorkflowExecutionContext`.
  - Spec: Proposed Public API, FR-6
  - Plan: Implementation Shape
  - Files/components: `src/dynamic_agent_runner/context.py`
  - Depends on: T1.2
  - Validation: `poetry run pytest tests/test_executor.py -q`

- [ ] T2.2 [implementation] Add `model_adapter_coverage` to high-level run APIs
      and forward it through to execution.
  - Spec: Proposed Public API, FR-1
  - Plan: Implementation Shape
  - Files/components: `src/dynamic_agent_runner/api.py`
  - Depends on: T2.1
  - Validation: `poetry run pytest tests/test_executor.py -q`

- [ ] T2.3 [implementation] Add `model_adapter_coverage` to sync and async
      executor APIs and context normalization.
  - Spec: Proposed Public API, FR-1, FR-6
  - Plan: Implementation Shape
  - Files/components: `src/dynamic_agent_runner/executor.py`
  - Depends on: T2.1
  - Validation: `poetry run pytest tests/test_executor.py -q`

- [ ] T2.4 [implementation] Validate policy values fail closed.
  - Spec: FR-6
  - Plan: Error Contract
  - Files/components: `src/dynamic_agent_runner/executor.py`
  - Depends on: T2.3
  - Validation: `poetry run pytest tests/test_executor.py -q`

## Slice 3 — Selection Semantics

- [ ] T3.1 [implementation] Implement strict adapter coverage.
  - Spec: FR-2, FR-3
  - Plan: Selection flow
  - Files/components: `src/dynamic_agent_runner/executor.py`
  - Depends on: T2.4
  - Validation: `poetry run pytest tests/test_executor.py -q`

- [ ] T3.2 [implementation] Implement augmented default OpenAI coverage.
  - Spec: FR-1, FR-5
  - Plan: Selection flow
  - Files/components: `src/dynamic_agent_runner/executor.py`
  - Depends on: T3.1
  - Validation: `poetry run pytest tests/test_executor.py
    tests/test_model_capabilities.py -q`

- [ ] T3.3 [implementation] Remove `local_only` adapter-routing semantics.
  - Spec: FR-4
  - Plan: Planning Decisions
  - Files/components: `src/dynamic_agent_runner/executor.py`,
    `tests/test_executor.py`
  - Depends on: T3.1
  - Validation: `poetry run pytest tests/test_executor.py -q`

## Slice 4 — Documentation and Final Validation

- [ ] T4.1 [docs] Document client-facing `model_adapter_coverage` behavior.
  - Spec: Proposed Public API, FR-1, FR-2, FR-5
  - Plan: Public contract
  - Files/components: `README.md`, `docs/files/python-api.rst`,
    `docs/skills/dynamic-agent-runner/SKILL.md`
  - Depends on: T3.3
  - Validation: `make -C docs html`

- [ ] T4.2 [validation] Run focused regression validation.
  - Spec: Validation Checklist
  - Plan: Validation Plan
  - Files/components: implementation and docs changed in Slices 1-4
  - Depends on: T4.1
  - Validation:
    `poetry run pytest tests/test_cli.py tests/test_executor.py
    tests/test_model_capabilities.py tests/test_import.py -q`

- [ ] T4.3 [spec-maintenance] Record implementation evidence and update status.
  - Spec: Metadata, Validation Checklist
  - Plan: Delivery completion
  - Files/components: `specs/model-adapter-coverage/spec.md`,
    `specs/model-adapter-coverage/tasks.md`, `specs/README.md`,
    `memory-bank/activeContext.md`, `memory-bank/progress.md`
  - Depends on: T4.2
  - Validation: `pre-commit run --files <changed files>`
