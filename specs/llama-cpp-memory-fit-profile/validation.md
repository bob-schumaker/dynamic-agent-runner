# llama.cpp Memory Fit Profile V1 Validation Log

Status: planning checkpoint prepared

## Scope

- Feature: `specs/llama-cpp-memory-fit-profile/spec.md`
- Plan: `specs/llama-cpp-memory-fit-profile/plan.md`
- Tasks: `specs/llama-cpp-memory-fit-profile/tasks.md`

## Planned Checks

- `poetry run pytest tests/test_local_models.py tests/test_import.py -q`
- `poetry run pytest tests/test_local_models.py -q`
- `pre-commit run --files src/dynamic_agent_runner/local_models.py`
  `src/dynamic_agent_runner/errors.py src/dynamic_agent_runner/__init__.py`
  `tests/test_local_models.py tests/test_import.py`
  `specs/llama-cpp-memory-fit-profile/spec.md`
  `specs/llama-cpp-memory-fit-profile/plan.md`
  `specs/llama-cpp-memory-fit-profile/tasks.md`
  `specs/llama-cpp-memory-fit-profile/validation.md specs/README.md`

## Planning Evidence

- V1 is limited to a read-only advisory API for concrete resolved GGUF assets.
- V1 uses injected evaluator/profiler behavior only; no subprocesses, real
  llama.cpp commands, model loads, live Hugging Face access, or automatic memory
  discovery are in scope.
- V1 reuses existing local-model path resolution and does not mutate
  `LlamaCppLocalModelConfig` or adapter execution.
- Fail-open mode returns advisory unavailable/unknown/failed-open results;
  strict mode raises only from the profiling call.

## Evidence

### Whitespace Check

- Command: `git diff --check`
- Observed result: passed
- Interpretation: no whitespace errors were present in the spec changes.

### Focused Pre-Commit

- Command:
  `pre-commit run --files specs/llama-cpp-memory-fit-profile/spec.md`
  `specs/llama-cpp-memory-fit-profile/plan.md`
  `specs/llama-cpp-memory-fit-profile/tasks.md`
  `specs/llama-cpp-memory-fit-profile/validation.md specs/README.md`
- Observed result: passed
- Interpretation: Markdown checks passed for the planning artifacts and spec
  index.

### Slice 1 — Public Advisory Contract

- Command:
  `poetry run pytest tests/test_local_models.py tests/test_import.py -q`
- RED observed result: failed because the strict-mode error and public advisory
  contract were missing.
- GREEN observed result: `24 passed in 0.16s`
- Interpretation: memory-fit statuses, measurement/result dataclasses,
  strict-mode error, placeholder profiling function, and package exports exist
  without invoking real profilers.

### Slice 2 — Fail-Open Profiling and Resolution

- Command: `poetry run pytest tests/test_local_models.py -q`
- RED observed result: failed because the placeholder profiling function did not
  call the injected evaluator.
- GREEN observed result: `26 passed in 0.15s`
- Interpretation: profiling now resolves the local model path through existing
  resolution, invokes an injected evaluator, returns unavailable in fail-open
  mode when no profiler exists, and raises a package-owned error in strict mode.
