# Local Model Availability API Validation Log

Status: Slice A4 prepared for implementation; Slices A1-A3 complete

## Scope

- Feature: `specs/local-model-availability-api/spec.md`
- Plan: `specs/local-model-availability-api/plan.md`
- Tasks: `specs/local-model-availability-api/tasks.md`
- Downstream request:
  `cline-tasks/local-model-availability-api-feature-request.md`

## Planned Checks

- `poetry run pytest tests/test_local_models.py tests/test_import.py -q`
- `poetry run pytest tests/test_local_models.py -q`
- `poetry run pytest tests/test_mlx_models.py tests/test_local_models.py -q`
- `poetry run pytest tests/test_local_models.py`
  `tests/test_hugging_face_support.py -q`
- `poetry run pytest tests/test_local_models.py tests/test_mlx_models.py`
  `tests/test_hugging_face_support.py tests/test_import.py -q`
- `poetry run ruff check src tests`
- `pre-commit run --files <changed implementation, test, docs, and spec files>`
- Slice A4 focused checks:
  `poetry run pytest tests/test_local_models.py tests/test_import.py -q`
- Slice A4 targeted pre-commit:
  `pre-commit run --files src/dynamic_agent_runner/local_models.py`
  `src/dynamic_agent_runner/__init__.py tests/test_local_models.py`
  `tests/test_import.py docs/files/python-api.rst`
  `docs/skills/dynamic-agent-runner/SKILL.md`
  `specs/local-model-availability-api/spec.md`
  `specs/local-model-availability-api/plan.md`
  `specs/local-model-availability-api/tasks.md`
  `specs/local-model-availability-api/validation.md specs/README.md`

## Planning Evidence

- Slice A1 is limited to read-only explicit-reference availability checking.
- Slice A4 prepares narrow local cached inventory restricted to
  DAR-owned/default download cache locations and current caller-provided roots.
- Broad local inventory and native Hugging Face cache introspection remain
  deferred.
- Availability checks must not download, construct adapters, load models,
  execute generation, or run memory-fit profiling.
- Remote metadata remains an injected fake-testable seam in the first
  implementation slice.
- Backend validation reuses the current local-model boundaries:
  - GGUF validation is filesystem-only and suffix-based.
  - Converted MLX validation follows the existing required file structure:
    `config.json`, `tokenizer.model`, and `weights.npz` or `weights.*.npz`.
- Existing runtime resolution and execution behavior remain unchanged.

## Consistency Check

- Spec FR-1 maps to tasks A1.1-A1.2.
- Spec FR-2 maps to tasks A1.3-A1.6.
- Spec FR-3 maps to tasks A1.3-A1.4 and A2.1-A2.2.
- Spec FR-4 maps to tasks A2.3-A2.4.
- Spec FR-5 maps to tasks A1.1-A1.2 and A3.1.
- Spec FR-6 is explicitly deferred from Slice A1 in `plan.md` and the scope
  rule in `tasks.md`.
- Spec FR-7 maps to all RED test tasks and the planned fake metadata seam.
- Spec FR-8 maps to prepared tasks A4.1-A4.10.
- No implementation task requires live Hugging Face, real MLX, real llama.cpp,
  model weights, or downstream Power Marimo dependencies.
- No task adds portable workflow manifest fields.
- No A4 task persists, manages, deletes, migrates, or recursively discovers
  caller-provided roots.

## Open Implementation Questions

These are implementation-local decisions, not blockers to starting the prepared
slice:

- Whether `LocalModelAssetReference` should be the only public input shape or
  whether `LocalModelPathConfig` should also be accepted by an overload/helper.
- Whether MLX validation helpers should be shared from `local_models.py` into
  `mlx_models.py` during A2 or duplicated temporarily to avoid drift.
- Whether disabled remote metadata should return `missing` or `unknown` for a
  remote reference that misses local cache. Tests should lock the selected
  behavior before implementation.
- Whether Slice A4 returns invalid inventory entries or skips them with bounded
  warnings. Tests should lock the selected behavior before implementation.
- Whether the public inventory item should be named `LocalModelInventoryItem` or
  a more availability-aligned name.

## Evidence

### Slice A1 — Public Contract and Local Checks

- Command:
  `poetry run pytest tests/test_local_models.py tests/test_import.py -q`
- RED observed result: failed because `LocalModelAssetReference`,
  `LocalModelAvailability`, status/source enums,
  `check_local_model_availability(...)`, and package-root exports were missing.
- GREEN observed result: `32 passed in 0.21s`
- Interpretation: public availability value objects, status/source enums,
  placeholder availability function, and package-root exports exist.
- Command: `poetry run pytest tests/test_local_models.py -q`
- RED observed result: failed because explicit local path checks, invalid GGUF
  classification, explicit cache-root hits, and default cache-root hits returned
  placeholder missing results.
- GREEN observed result: `37 passed in 0.21s`
- Interpretation: explicit local path availability, missing path reporting,
  minimal GGUF validation, no fallback from explicit local paths, and
  no-download cache-root precedence are implemented.
- Command:
  `poetry run pytest tests/test_local_models.py tests/test_import.py -q`
- Observed result: `38 passed in 0.17s`
- Interpretation: Slice A1 local-model availability behavior and package exports
  are green together.

### Slice A2 — MLX Validation and Remote Metadata

- Command:
  `poetry run pytest tests/test_mlx_models.py tests/test_local_models.py -q`
- RED observed result: failed because incomplete converted MLX directories were
  accepted as available, `metadata_lookup` was not accepted, and
  `LocalModelRemoteMetadata` did not exist.
- GREEN observed result:
  `poetry run pytest tests/test_mlx_models.py tests/test_local_models.py`
  `tests/test_import.py -q` — `63 passed in 0.31s`
- Interpretation: MLX GGUF and converted MLX directory availability are
  validated without importing MLX, and the metadata helper is exported.
- Command:
  `poetry run pytest tests/test_local_models.py`
  `tests/test_hugging_face_support.py -q`
- Observed result: `49 passed in 0.20s`
- Interpretation: injected remote metadata supports `would_download`, invalid,
  and unknown results without live Hugging Face calls or downloads.

### Slice A3 — Documentation and Final Validation

- Command:
  `pre-commit run --files docs/files/python-api.rst`
  `docs/skills/dynamic-agent-runner/SKILL.md`
- Observed result: passed
- Interpretation: availability preflight documentation passes Markdown checks.
- Command:
  `poetry run pytest tests/test_local_models.py tests/test_mlx_models.py`
  `tests/test_hugging_face_support.py tests/test_import.py -q`
- Observed result: `71 passed in 0.27s`
- Interpretation: local-model availability, MLX validation, Hugging Face support
  regression coverage, and package exports are green together.
- Command: `poetry run ruff check src tests`
- Observed result: passed
- Interpretation: source and tests pass Ruff linting.
- Command:
  `pre-commit run --files src/dynamic_agent_runner/local_models.py`
  `src/dynamic_agent_runner/mlx_models.py`
  `src/dynamic_agent_runner/__init__.py tests/test_local_models.py`
  `tests/test_mlx_models.py tests/test_import.py docs/files/python-api.rst`
  `docs/skills/dynamic-agent-runner/SKILL.md`
  `specs/local-model-availability-api/spec.md`
  `specs/local-model-availability-api/plan.md`
  `specs/local-model-availability-api/tasks.md`
  `specs/local-model-availability-api/validation.md specs/README.md`
- Observed result: passed
- Interpretation: targeted pre-commit passed for implementation, tests, docs,
  and spec artifacts.

## Deferred From V1

- Broad local inventory remains deferred; Slice A4 prepares only narrow cached
  inventory over DAR-owned/default download cache locations and current
  caller-provided roots.
- Native Hugging Face cache introspection remains deferred.
- Real Hugging Face metadata integration remains deferred; v1 uses an injected
  fake-testable metadata seam.
- Strict exception mode for ordinary missing or invalid selected assets remains
  deferred.
- Model loading, generation, conversion, deletion, and memory-fit profiling
  remain outside availability checks.
