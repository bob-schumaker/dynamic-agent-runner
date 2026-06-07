# Hugging Face Support Layer Task List

Status: ready for implementation

## Prerequisites

- Spec: `specs/hugging-face-support-layer/spec.md`
- Plan: `specs/hugging-face-support-layer/plan.md`
- Dependent MLX tasks: `specs/mlx-local-model-adapter/tasks.md` T3.5 and T3.6

## Scope Rule

Keep this change limited to internal Hugging Face SDK import/call mechanics.
Do not change public model search results, local-model resolution precedence,
offline policy, cache roots, package-root exports, or live network behavior.

## Slice 1 — Internal Support Module and Search Routing

- [x] T1.1 [tests] Add support-layer tests for lazy import and list-models
      call failures using fake Hub modules.
  - Spec: FR-1, FR-4
  - Plan: Slice 1
  - Files/components: `tests/test_hugging_face_support.py`,
    `src/dynamic_agent_runner/hugging_face_support.py`
  - Validation:
    `poetry run pytest tests/test_hugging_face_support.py -q`
  - RED: support-layer tests failed because `hugging_face_support.py` did not
    exist.
  - GREEN: `poetry run pytest tests/test_hugging_face_support.py
    tests/test_hugging_face_models.py tests/test_import.py -q` passed with
    10 tests.

- [x] T1.2 [implementation] Add `hugging_face_support.py` with internal
      read-only Hub helpers.
  - Spec: FR-1, FR-4
  - Plan: Planning Decisions
  - Files/components: `src/dynamic_agent_runner/hugging_face_support.py`
  - Depends on: T1.1
  - Validation:
    `poetry run pytest tests/test_hugging_face_support.py -q`
  - GREEN: `poetry run pytest tests/test_hugging_face_support.py
    tests/test_hugging_face_models.py tests/test_import.py -q` passed with
    10 tests.

- [x] T1.3 [implementation] Route model search through support-layer
      `list_hub_models(...)`.
  - Spec: FR-2, FR-3
  - Plan: Slice 1
  - Files/components: `src/dynamic_agent_runner/hugging_face_models.py`,
    `tests/test_hugging_face_models.py`, `tests/test_import.py`
  - Depends on: T1.2
  - Validation:
    `poetry run pytest tests/test_hugging_face_support.py
    tests/test_hugging_face_models.py tests/test_import.py -q`
  - GREEN: `poetry run pytest tests/test_hugging_face_support.py
    tests/test_hugging_face_models.py tests/test_import.py -q` passed with
    10 tests.

## Slice 2 — Local Download Routing

- [x] T2.1 [tests] Add support-layer tests for file and snapshot download
      wrappers using fake Hub callables.
  - Spec: FR-1, FR-4
  - Plan: Slice 2
  - Files/components: `tests/test_hugging_face_support.py`,
    `src/dynamic_agent_runner/hugging_face_support.py`
  - Validation:
    `poetry run pytest tests/test_hugging_face_support.py -q`
  - GREEN: `poetry run pytest tests/test_hugging_face_support.py -q` passed with
    8 tests.

- [x] T2.2 [implementation] Route local-model default Hub downloads through
      support-layer helpers.
  - Spec: FR-2, FR-3
  - Plan: Slice 2
  - Files/components: `src/dynamic_agent_runner/local_models.py`,
    `src/dynamic_agent_runner/hugging_face_support.py`,
    `tests/test_local_models.py`
  - Depends on: T2.1
  - Validation:
    `poetry run pytest tests/test_hugging_face_support.py
    tests/test_local_models.py -q`
  - GREEN: `poetry run pytest tests/test_hugging_face_support.py
    tests/test_local_models.py -q` passed with 23 tests.

## Slice 3 — Spec Maintenance and Regression

- [ ] T3.1 [validation] Run focused Hugging Face regression validation.
  - Spec: Validation Checklist
  - Plan: Slice 3
  - Files/components: implementation changed in Slices 1-2
  - Depends on: T2.2
  - Validation:
    `poetry run pytest tests/test_hugging_face_support.py
    tests/test_hugging_face_models.py tests/test_local_models.py -q`

- [ ] T3.2 [spec-maintenance] Record implementation evidence and update status.
  - Spec: Metadata, Validation Checklist
  - Plan: Slice 3
  - Files/components: `specs/hugging-face-support-layer/spec.md`,
    `specs/hugging-face-support-layer/plan.md`,
    `specs/hugging-face-support-layer/tasks.md`, `specs/README.md`,
    `memory-bank/activeContext.md`, `memory-bank/progress.md`
  - Depends on: T3.1
  - Validation: `pre-commit run --files <changed files>`
