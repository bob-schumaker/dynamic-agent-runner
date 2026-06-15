# llama.cpp Memory Fit Profile V1 Tasks

Status: prepared for implementation

## Slice 0 — Planning Checkpoint

- [x] T0.1 Resolve v1 profiler, cache, budget, strict-mode, and suggested-kwargs
      decisions in `spec.md`.
- [x] T0.2 Add `plan.md`, `tasks.md`, and `validation.md` before
      implementation.
- [x] T0.3 Commit the planning checkpoint before implementation.
  - Completed by the planning checkpoint commit containing this task update.

## Slice 1 — Public Advisory Contract

- [x] T1.1 [tests] Add RED import/shape tests for memory-fit statuses,
      measurement/result dataclasses, strict-mode error, and package exports.
  - Spec: FR-2, FR-3, FR-6
  - Files/components: `tests/test_local_models.py`, `tests/test_import.py`,
    `src/dynamic_agent_runner/local_models.py`,
    `src/dynamic_agent_runner/errors.py`, `src/dynamic_agent_runner/__init__.py`
  - Validation:
    `poetry run pytest tests/test_local_models.py tests/test_import.py -q`
  - RED:
    - `poetry run pytest tests/test_local_models.py tests/test_import.py -q` —
      failed because `LlamaCppMemoryFitProfileError` and the advisory contract
      were not exported.

- [x] T1.2 [implementation] Add the public advisory dataclasses, status
      vocabulary, strict-mode error, and exports without invoking real profilers.
  - Spec: FR-2, FR-3, FR-6
  - Files/components: `src/dynamic_agent_runner/local_models.py`,
    `src/dynamic_agent_runner/errors.py`, `src/dynamic_agent_runner/__init__.py`
  - Validation:
    `poetry run pytest tests/test_local_models.py tests/test_import.py -q`
  - GREEN:
    - `poetry run pytest tests/test_local_models.py tests/test_import.py -q` —
      `24 passed in 0.16s`

## Slice 2 — Fail-Open Profiling and Resolution

- [x] T2.1 [tests] Add RED coverage for existing llama.cpp adapter no-drift,
      resolved local-path profiling, missing profiler fail-open results, and
      strict-mode unavailable errors.
  - Spec: FR-1, FR-2, FR-5, FR-6
  - Files/components: `tests/test_local_models.py`
  - Validation: `poetry run pytest tests/test_local_models.py -q`
  - RED:
    - `poetry run pytest tests/test_local_models.py -q` — failed because the
      placeholder profiling function did not call the injected evaluator.

- [x] T2.2 [implementation] Implement
      `profile_llama_cpp_model_memory_fit(...)` with existing path resolution,
      injected evaluator invocation, fail-open unavailable result, and
      strict-mode package-owned errors.
  - Spec: FR-1, FR-2, FR-5, FR-6
  - Files/components: `src/dynamic_agent_runner/local_models.py`
  - Validation: `poetry run pytest tests/test_local_models.py -q`
  - GREEN:
    - `poetry run pytest tests/test_local_models.py -q` — `26 passed in 0.15s`

## Slice 3 — Fit Math and Suggested Context

- [ ] T3.1 [tests] Add RED coverage for fake evaluator normalization, requested
      context fit, over-budget effective context, supported tiers, estimated
      memory by tier, diagnostics, and suggested `n_ctx`.
  - Spec: FR-3, FR-4
  - Files/components: `tests/test_local_models.py`
  - Validation: `poetry run pytest tests/test_local_models.py -q`

- [ ] T3.2 [implementation] Add deterministic fit calculations and result
      normalization for complete, partial, unknown, and failed-open profiles.
  - Spec: FR-3, FR-4, FR-6
  - Files/components: `src/dynamic_agent_runner/local_models.py`
  - Validation: `poetry run pytest tests/test_local_models.py -q`

## Slice 4 — Completion Evidence

- [ ] T4.1 [validation] Run focused affected tests.
  - Command:
    `poetry run pytest tests/test_local_models.py tests/test_import.py -q`

- [ ] T4.2 [validation] Run focused pre-commit.
  - Command:
    `pre-commit run --files src/dynamic_agent_runner/local_models.py`
    `src/dynamic_agent_runner/errors.py src/dynamic_agent_runner/__init__.py`
    `tests/test_local_models.py tests/test_import.py`
    `specs/llama-cpp-memory-fit-profile/spec.md`
    `specs/llama-cpp-memory-fit-profile/plan.md`
    `specs/llama-cpp-memory-fit-profile/tasks.md`
    `specs/llama-cpp-memory-fit-profile/validation.md specs/README.md`

- [ ] T4.3 [docs] Record completion evidence and update spec status before the
      next focus area.
