# macOS MLX Local-Model Adapter Task List

Status: ready for implementation

## Prerequisites

- Spec: `specs/mlx-local-model-adapter/spec.md`
- Plan: `specs/mlx-local-model-adapter/plan.md`
- Adapter coverage policy: `model_adapter_coverage="strict"` is required for
  local-only client intent
- Default coverage policy: `"augmented"` may still fall back to default OpenAI
  coverage when MLX adapters do not match an eligible OpenAI model

## Scope Rule

Keep this change limited to macOS-only in-process MLX text generation adapters
and their client-facing helper surface. Do not add server lifecycle management,
model conversion, embeddings, multimodal behavior, streaming public APIs, tool
calling, structured output, provider discovery, or workflow-manifest schema
fields.

## Slice 1 — Public Contract and Failure Tests

- [x] T1.1 [tests] Add RED tests that package import does not require MLX.
  - Spec: FR-2
  - Plan: Dependency policy
  - Files/components: `tests/test_import.py`,
    `src/dynamic_agent_runner/__init__.py`
  - Validation: `poetry run pytest tests/test_import.py -q`
  - Expected RED: public exports or imports do not exist yet.
  - RED: targeted import/MLX tests failed because package-root MLX exports did
    not exist.
  - GREEN: `poetry run pytest tests/test_import.py tests/test_mlx_models.py -q`
    passed with 7 tests.

- [x] T1.2 [tests] Add RED tests for `MLXLocalModelConfig` and sync/async
      factory exports.
  - Spec: Proposed Public API, FR-1, FR-2
  - Plan: Public exports, New MLX helper module
  - Files/components: `tests/test_mlx_models.py`,
    `src/dynamic_agent_runner/mlx_models.py`,
    `src/dynamic_agent_runner/__init__.py`
  - Validation: `poetry run pytest tests/test_mlx_models.py -q`
  - Expected RED: module, config, and factories do not exist.
  - RED: targeted MLX tests failed with missing `MLXLocalModelConfig` and
    factory exports.
  - GREEN: `poetry run pytest tests/test_import.py tests/test_mlx_models.py -q`
    passed with 7 tests.

- [x] T1.3 [tests] Add RED tests for unsupported platform and missing MLX
      dependency failures.
  - Spec: FR-2
  - Plan: Error Contract
  - Files/components: `tests/test_mlx_models.py`,
    `src/dynamic_agent_runner/mlx_models.py`,
    `src/dynamic_agent_runner/errors.py`
  - Validation: `poetry run pytest tests/test_mlx_models.py -q`
  - Expected RED: no package-owned MLX platform/dependency errors exist.
  - RED: targeted MLX tests failed before the adapter existed.
  - GREEN: `poetry run pytest tests/test_import.py tests/test_mlx_models.py -q`
    passed with 7 tests.

- [x] T1.4 [tests] Add RED tests for unsupported request features.
  - Spec: FR-5
  - Plan: Planning Decisions, Error Contract
  - Files/components: `tests/test_mlx_models.py`,
    `src/dynamic_agent_runner/mlx_models.py`
  - Cases:
    - tool calls requested
    - structured response format requested
  - Validation: `poetry run pytest tests/test_mlx_models.py -q`
  - Expected RED: no MLX adapter request validation exists.
  - RED: targeted MLX tests failed before request validation existed.
  - GREEN: `poetry run pytest tests/test_import.py tests/test_mlx_models.py -q`
    passed with 7 tests.

## Slice 2 — Core MLX Adapter Surface

- [x] T2.1 [implementation] Add `mlx_models.py` with config, backend protocol,
      lazy checks, and sync adapter factory.
  - Spec: Proposed Public API, FR-1, FR-2, FR-5
  - Plan: New MLX helper module, Error Contract
  - Files/components: `src/dynamic_agent_runner/mlx_models.py`,
    `src/dynamic_agent_runner/errors.py`
  - Depends on: T1.2, T1.3, T1.4
  - Validation: `poetry run pytest tests/test_mlx_models.py -q`
  - GREEN: `poetry run pytest tests/test_import.py tests/test_mlx_models.py -q`
    passed with 7 tests.

- [x] T2.2 [implementation] Add async MLX adapter factory without blocking the
      event loop directly.
  - Spec: Proposed Public API, FR-1, FR-5
  - Plan: Planning Decisions, Implementation Shape
  - Files/components: `src/dynamic_agent_runner/mlx_models.py`,
    `tests/test_mlx_models.py`
  - Depends on: T2.1
  - Validation: `poetry run pytest tests/test_mlx_models.py -q`
  - GREEN: `poetry run pytest tests/test_import.py tests/test_mlx_models.py -q`
    passed with 7 tests.

- [x] T2.3 [implementation] Export MLX config and factories from package root.
  - Spec: Proposed Public API, FR-2
  - Plan: Public exports
  - Files/components: `src/dynamic_agent_runner/__init__.py`,
    `tests/test_import.py`, `tests/test_mlx_models.py`
  - Depends on: T2.1, T2.2
  - Validation:
    `poetry run pytest tests/test_import.py tests/test_mlx_models.py -q`
  - GREEN: `poetry run pytest tests/test_import.py tests/test_mlx_models.py -q`
    passed with 7 tests.

## Slice 3 — Model Assets, Identity, and Generation Normalization

- [x] T3.1 [tests] Add RED tests for converted MLX directory path resolution.
  - Spec: FR-3
  - Plan: Implementation Shape
  - Files/components: `tests/test_mlx_models.py`,
    `src/dynamic_agent_runner/mlx_models.py`,
    `src/dynamic_agent_runner/local_models.py`
  - Validation: `poetry run pytest tests/test_mlx_models.py -q`
  - Expected RED: MLX path preflight is not implemented.
  - RED: targeted MLX tests failed because missing model directories did not
    raise local-model resolution errors.
  - GREEN: `poetry run pytest tests/test_mlx_models.py
    tests/test_local_models.py -q` passed with 26 tests.

- [x] T3.2 [implementation] Implement converted MLX directory preflight and
      local-model resolution errors.
  - Spec: FR-3
  - Plan: New MLX helper module, Error Contract
  - Files/components: `src/dynamic_agent_runner/mlx_models.py`,
    `src/dynamic_agent_runner/errors.py`
  - Depends on: T3.1
  - Validation: `poetry run pytest tests/test_mlx_models.py -q`
  - GREEN: `poetry run pytest tests/test_mlx_models.py
    tests/test_local_models.py -q` passed with 26 tests.

- [x] T3.3 [tests] Add RED tests for model identity mismatch reporting.
  - Spec: FR-4
  - Plan: Error Contract
  - Files/components: `tests/test_mlx_models.py`,
    `src/dynamic_agent_runner/mlx_models.py`
  - Validation: `poetry run pytest tests/test_mlx_models.py -q`
  - Expected RED: MLX adapter does not preserve authoritative identity yet.
  - RED: targeted MLX tests failed because backend model identity was not
    compared to `expected_model_id`.
  - GREEN: `poetry run pytest tests/test_mlx_models.py
    tests/test_local_models.py -q` passed with 26 tests.

- [x] T3.4 [implementation] Wire identity validation and normalized
      `ModelResponse` output.
  - Spec: FR-4, FR-5
  - Plan: Implementation Shape, Error Contract
  - Files/components: `src/dynamic_agent_runner/mlx_models.py`,
    `tests/test_mlx_models.py`
  - Depends on: T3.3
  - Validation: `poetry run pytest tests/test_mlx_models.py -q`
  - GREEN: `poetry run pytest tests/test_mlx_models.py
    tests/test_local_models.py -q` passed with 26 tests.

- [x] T3.5 [tests] Add RED tests for injected Hugging Face snapshot/file
      resolution without network.
  - Spec: FR-3
  - Plan: New MLX helper module
  - Depends on: `hugging-face-support-layer` implemented
  - Files/components: `tests/test_mlx_models.py`,
    `src/dynamic_agent_runner/mlx_models.py`,
    `src/dynamic_agent_runner/local_models.py`
  - Validation: `poetry run pytest tests/test_mlx_models.py -q`
  - Expected RED: MLX helper does not accept injected Hub resolution yet.
  - RED: targeted MLX tests failed because MLX config did not accept Hub
    reference fields.
  - GREEN: `poetry run pytest tests/test_mlx_models.py
    tests/test_local_models.py -q` passed with 26 tests.

- [x] T3.6 [implementation] Reuse existing local-model Hub reference mechanics
      for MLX model directories.
  - Spec: FR-3
  - Plan: Existing Implementation Context, Implementation Shape
  - Files/components: `src/dynamic_agent_runner/mlx_models.py`,
    `src/dynamic_agent_runner/local_models.py`
  - Depends on: T3.5 and `hugging-face-support-layer` implemented
  - Validation:
    `poetry run pytest tests/test_mlx_models.py tests/test_local_models.py -q`
  - GREEN: `poetry run pytest tests/test_mlx_models.py
    tests/test_local_models.py -q` passed with 26 tests.

## Slice 4 — Executor Coverage and Public Documentation

- [ ] T4.1 [tests] Add RED executor tests proving strict and augmented behavior
      with MLX adapters.
  - Spec: FR-1
  - Plan: Executor integration
  - Files/components: `tests/test_executor.py`,
    `src/dynamic_agent_runner/mlx_models.py`
  - Cases:
    - strict mode with only MLX adapters prevents default OpenAI fallback
    - augmented mode can still use default OpenAI fallback when MLX aliases do
      not match an eligible OpenAI model
  - Validation: `poetry run pytest tests/test_executor.py -q`
  - Expected RED: MLX adapter test helpers do not exist or do not integrate.

- [ ] T4.2 [implementation] Complete executor-facing adapter metadata behavior.
  - Spec: FR-1
  - Plan: Executor integration
  - Files/components: `src/dynamic_agent_runner/mlx_models.py`,
    `tests/test_executor.py`
  - Depends on: T4.1
  - Validation:
    `poetry run pytest tests/test_executor.py tests/test_mlx_models.py -q`

- [ ] T4.3 [docs] Document client-facing MLX adapter usage.
  - Spec: Validation Checklist
  - Plan: Public exports, Dependency policy
  - Files/components: `README.md`, `docs/files/python-api.rst`,
    `docs/skills/dynamic-agent-runner/SKILL.md`,
    `specs/README.md`
  - Depends on: T4.2
  - Validation: `make -C docs html`

- [ ] T4.4 [validation] Run focused regression validation.
  - Spec: Validation Checklist
  - Plan: Validation Plan
  - Files/components: implementation and docs changed in Slices 1-4
  - Depends on: T4.3
  - Validation:
    `poetry run pytest tests/test_import.py tests/test_local_models.py
    tests/test_mlx_models.py tests/test_executor.py tests/test_cli.py -q`

- [ ] T4.5 [spec-maintenance] Record implementation evidence and update
      status.
  - Spec: Metadata, Validation Checklist
  - Plan: Validation Plan
  - Files/components: `specs/mlx-local-model-adapter/spec.md`,
    `specs/mlx-local-model-adapter/plan.md`,
    `specs/mlx-local-model-adapter/tasks.md`, `specs/README.md`,
    `memory-bank/activeContext.md`, `memory-bank/progress.md`
  - Depends on: T4.4
  - Validation: `pre-commit run --files <changed files>`
