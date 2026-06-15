# llama.cpp Memory Fit Profile V1 Plan

## Objective

Add a read-only advisory API that profiles a resolved local GGUF model asset
through caller-injected evaluator data, estimates safe context windows under a
caller-provided memory budget, and returns package-owned fit records without
changing llama.cpp adapter execution.

## Scope

- Add public memory-fit dataclasses and a small status vocabulary.
- Add a package-owned profiling function for `LlamaCppLocalModelConfig`.
- Reuse existing `resolve_local_model_path(...)` precedence and injected
  download callables.
- Accept an injected evaluator/profiler callable in v1.
- Normalize evaluator output into resident bytes, context bytes per 1k tokens,
  budget, requested-context fit, supported tiers, maximum usable context, and
  diagnostics.
- Return fail-open advisory results for missing/failed profilers by default.
- Raise a package-owned error in strict mode when profiling cannot produce a
  usable advisory.
- Export the API from `dynamic_agent_runner.local_models` and the package root.

## Non-Goals

- No subprocess runner or real llama.cpp command invocation.
- No `llama-cpp-python` model loading or metadata probing.
- No automatic model download beyond existing local-model resolution behavior.
- No automatic memory-budget discovery.
- No cache persistence.
- No adapter mutation or execution blocking.
- No GPU offload or backend-specific tuning recommendations beyond `n_ctx`.
- No live Hugging Face, llama.cpp, server, or model-runtime dependency in tests.

## Design

Keep the first implementation inside `src/dynamic_agent_runner/local_models.py`
unless the code grows enough to justify a separate module. The public helper
should resolve the model path using the existing `LocalModelPathConfig` path and
then call an injected evaluator when one is provided.

The evaluator should return simple package-owned measurements rather than raw
command output:

- resident bytes
- context bytes per 1k tokens
- optional memory budget bytes
- optional diagnostics

The profiling function should combine evaluator output with caller inputs:

- use caller `memory_budget_bytes` first
- fall back to evaluator-provided budget
- return `unknown` if no budget is available
- compute maximum usable context as
  `(budget - resident) / context_bytes_per_1k * 1000` when the inputs are valid
- mark configured tiers as supported when their estimated memory fits
- suggest `{"n_ctx": effective_context}` only when an effective context can be
  derived

## Compatibility

- Existing llama.cpp adapter construction and execution remain unchanged when
  profiling is not requested.
- Existing local-model resolution errors remain authoritative for unresolved
  assets.
- Fail-open profiling failures must not prevent callers from explicitly creating
  or running adapters.

## Validation Strategy

- RED import/shape tests for new dataclasses, statuses, error, and exports.
- RED tests proving missing profilers return `unavailable` in fail-open mode and
  raise in strict mode.
- RED tests proving fake evaluator output normalizes into fit estimates,
  supported tiers, maximum usable context, and suggested `n_ctx`.
- RED tests proving requested context above budget returns a lower effective
  context.
- RED tests proving existing llama.cpp adapter behavior remains unchanged.
- Focused validation:
  `poetry run pytest tests/test_local_models.py tests/test_import.py -q`
- Focused pre-commit on changed source, tests, and spec artifacts.
