# llama.cpp Memory Fit Profile Specification

## Metadata

- Feature slug: `llama-cpp-memory-fit-profile`
- Mode: `light`
- Artifact type: future feature specification
- Status: proposed optional advisory feature; no implementation started
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Related feature specs:
  - `specs/llama-cpp-local-model/spec.md`
  - `specs/llmfit-model-fit-filter/spec.md`
  - `specs/capability-status-report/spec.md`
- Related implementation surfaces:
  - `src/dynamic_agent_runner/local_models.py`
  - `src/dynamic_agent_runner/errors.py`

## Objective

Define an optional llama.cpp memory-fit profiling surface for already-resolved
local GGUF model assets. The feature should help callers decide whether a direct
in-process llama.cpp model can run safely at a requested context size without
turning memory checks into a required dependency, downloader, server manager, or
model-selection engine.

## Problem Statement

`dynamic-agent-runner` already has direct in-process llama.cpp support through
package-owned local-model helpers. Callers can configure a
`LlamaCppLocalModelConfig`, resolve an explicit local path or Hugging Face
reference, and run chat through the existing model-adapter contract.

That execution path still leaves a practical usability gap: a GGUF file may be
present and technically loadable while being a poor fit for the machine at the
requested context window. The current adapter accepts caller-supplied
`model_kwargs`, but it does not provide a package-owned way to estimate safe
context sizes, explain memory pressure, or surface a fit advisory before a real
agent run.

This feature fills that post-resolution gap. It is not the same as
`llmfit-model-fit-filter`: `llmfit` filters search candidates before explicit
asset download, while this feature profiles a concrete local llama.cpp model
asset after resolution and before or beside execution.

## Discovery Summary

The inspected LlamaBarn repository at `/Users/roschuma/Repos/github/LlamaBarn/`
implements local model fit as a memory feasibility check rather than as a
general model-quality ranking.

Useful observed behavior:

- Before download, LlamaBarn applies a rough local-memory budget and file-size
  estimate to avoid obviously unsuitable models.
- After install, it invokes llama.cpp fit-parameter probing at multiple context
  sizes, then stores an affine memory estimate with a resident-memory component
  and a per-context-token slope.
- It uses the profile to derive supported context tiers, effective context, and
  generated llama.cpp server configuration.
- The useful idea for this package is the profiling shape, not LlamaBarn's Swift
  app model, server management, or UI behavior.

## Scope

This feature covers:

1. resolving a concrete local GGUF model path through existing local-model
   resolution behavior
2. optionally invoking an already-installed llama.cpp probing capability through
   an injected command runner or evaluator
3. normalizing memory-fit output into package-owned advisory records
4. estimating fit for requested context sizes and common context tiers
5. suggesting safe llama.cpp model kwargs such as an effective `n_ctx`
6. deterministic tests using fake profilers, fake command output, and temporary
   files

This feature does not cover:

1. adding a new llama.cpp execution adapter
2. replacing `LlamaCppLocalModelConfig` or the existing adapter factories
3. downloading models automatically
4. filtering Hugging Face search results
5. installing, bundling, vendoring, or updating llama.cpp tools
6. starting, stopping, or configuring a llama.cpp server process
7. making profiling mandatory before local execution
8. porting LlamaBarn's Swift implementation wholesale

## Assumptions and Definitions

- **Memory fit profile** means package-owned advisory data for one resolved
  local model asset on the current machine.
- **Resident bytes** means the estimated base memory needed to load the model
  before context growth is applied.
- **Context bytes per 1k tokens** means the estimated incremental memory cost for
  each additional 1,000 context tokens.
- **Memory budget** means the caller-provided or evaluator-derived memory limit
  used for advisory fit calculations.
- **Fit status** should be one of a small package-owned set such as `fits`,
  `too_large`, `unknown`, `unavailable`, or `failed_open`.
- Unknown or unavailable profiling must not prevent local execution by default.
  Strict failure behavior may be added only as an explicit caller option.
- The package must not assume every environment has Apple unified memory. CPU
  RAM, unified memory, and discrete GPU/VRAM environments may need different
  evaluator inputs.

## Functional Requirements

### FR-1: Reuse existing llama.cpp local-model resolution

The feature must evaluate concrete model assets through the current local-model
boundary.

Acceptance criteria:

- Given a caller provides a `LlamaCppLocalModelConfig`, when profiling is
  requested, then the feature resolves the model path using the same precedence
  and Hugging Face reference behavior as direct llama.cpp execution.
- Given an explicit local model path already exists, when profiling is
  requested, then the feature can profile that path without network access.
- Given model resolution fails, when profiling is requested, then the feature
  reports or raises the existing package-owned local-model resolution error
  according to the caller's selected failure mode.
- Given profiling completes, when the caller later constructs or uses the
  llama.cpp adapter, then the existing adapter contract remains authoritative for
  execution.

### FR-2: Treat profiling as optional environment capability

The feature must not make llama.cpp probing a hard runtime dependency.

Acceptance criteria:

- Given no profiler or command runner is available, when profiling is requested
  in fail-open mode, then the result reports `unavailable` and contains no
  blocking recommendation.
- Given a profiler is available, when profiling is requested, then the package
  may invoke it through a narrow injected evaluator or command runner.
- Given the package is imported or a llama.cpp adapter is created normally, when
  profiling is not requested, then no profiler discovery or subprocess
  invocation occurs.
- Given tests cover profiler behavior, when they run, then they use fake
  evaluators or fake command outputs instead of invoking real llama.cpp binaries
  or loading real GGUF models.

### FR-3: Normalize profiler output into package-owned records

The feature must expose stable advisory data rather than raw profiler output.

Acceptance criteria:

- Given a profiler returns usable measurements, when the package exposes the
  result, then it includes the resolved model path, resident bytes, context bytes
  per 1k tokens, memory budget, fit status, supported context tiers, maximum
  usable context tokens, and diagnostics.
- Given the profiler returns extra fields, when normalization runs, then unknown
  fields are ignored unless a later spec expands the public contract.
- Given a profiler returns partial data, when a conservative estimate is still
  possible, then the result marks the profile as partial and includes
  diagnostics explaining the missing pieces.
- Given no trustworthy estimate is possible, when fail-open mode is active, then
  the result reports `unknown` or `failed_open` without blocking execution.

### FR-4: Estimate context fit and effective context

The feature must help callers choose a safe context window for local llama.cpp
execution.

Acceptance criteria:

- Given resident-memory and context-growth estimates plus a memory budget, when
  the caller asks about a requested context size, then the result reports whether
  that context size fits.
- Given a requested context size is too large, when an estimate is available,
  then the result includes a lower maximum usable context token count.
- Given common tiers such as 4k, 8k, 16k, 32k, 64k, and 128k are requested or
  configured, when an estimate is available, then the result reports which tiers
  fit under the budget.
- Given the caller asks for suggested kwargs, when an effective context can be
  derived, then the result may suggest `model_kwargs` such as `{"n_ctx": value}`
  without mutating the caller's config.

### FR-5: Preserve execution and discovery boundaries

Memory-fit profiling must remain advisory and must not take ownership of adjacent
features.

Acceptance criteria:

- Given a model profile says the requested context fits, when execution starts,
  then the normal llama.cpp adapter still loads and runs the model; the profile
  does not stand in for execution validation.
- Given a model profile says the requested context does not fit, when fail-open
  mode is active, then the package reports diagnostics but does not prevent the
  caller from explicitly running anyway.
- Given a caller wants pre-download model recommendations, when no concrete GGUF
  path exists, then the caller should use `llmfit-model-fit-filter` or a future
  discovery feature instead of this profiler.
- Given capability reporting exists, when profiling is unavailable or not
  configured, then capability/status reporting may surface that as an optional
  advisory capability rather than as a missing core runtime feature.

### FR-6: Keep failure behavior deterministic and safe

Profiling failures must be visible without making local model execution brittle.

Acceptance criteria:

- Given the profiler times out, exits unsuccessfully, emits invalid output, or
  cannot classify the model, when fail-open mode is active, then the feature
  returns a diagnostic result rather than raising an unhandled exception.
- Given strict mode is selected, when profiling cannot produce a usable result,
  then the package may raise a package-owned error.
- Given diagnostics include paths, when results are formatted for logs or CLI
  output, then callers can choose whether absolute paths are included.
- Given profiling is repeated for the same model path and evaluator inputs, when
  fake evaluators are used in tests, then the result ordering and fields are
  deterministic.

## Suggested Public API Shape

Exact names are not authoritative. A future implementation may expose a small
API such as:

```python
profile_llama_cpp_model_memory_fit(
    config: LlamaCppLocalModelConfig,
    *,
    requested_context_tokens: int | None = None,
    context_tiers: Sequence[int] = (4096, 8192, 16384, 32768, 65536, 131072),
    memory_budget_mb: int | None = None,
    mode: str = "fail_open",
    profiler: LlamaCppMemoryFitProfiler | None = None,
) -> LlamaCppMemoryFitProfileResult
```

Where `LlamaCppMemoryFitProfileResult` contains:

- resolved model path
- profile status
- resident bytes
- context bytes per 1k tokens
- memory budget in bytes
- requested context fit result
- maximum usable context tokens
- supported context tiers
- estimated memory by context tier
- suggested model kwargs
- diagnostics

This suggested shape is not implementation approval. A future implementation
plan should decide exact names, exports, caching behavior, and failure-mode
types.

## Design Constraints

- Keep the first implementation read-only.
- Use repository-owned dataclasses and package-owned errors.
- Reuse existing local-model resolution and identity context where possible.
- Do not add a required dependency on `llama-cpp-python`, llama.cpp server
  extras, or standalone llama.cpp binaries.
- Do not run live model loads or real profiler commands from unit tests.
- Do not silently mutate caller-provided `LlamaCppLocalModelConfig`.
- Prefer injected evaluator interfaces over hard-coded subprocess behavior.

## Relationship to Existing Specs

- `llama-cpp-local-model` owns local endpoint helpers, direct in-process
  execution, local path resolution, Hugging Face asset references, identity
  validation, response normalization, and adapter exports.
- `llmfit-model-fit-filter` owns pre-download filtering of Hugging Face search
  candidates through optional `llmfit` CLI JSON output.
- This spec owns post-resolution memory profiling for a concrete llama.cpp model
  asset and should not duplicate either adjacent feature.
- `capability-status-report` may later report whether memory-fit profiling is
  available, unavailable, disabled, or failed-open in a given environment.

## NEEDS CLARIFICATION

- Should the first profiler integrate with an existing llama.cpp command such as
  `llama fit-params`, use `llama-cpp-python` metadata, or support only an
  injected evaluator until a concrete command contract is selected?
- Should profile results be cached, and if so, should cache keys include model
  file path, size, modification time, backend, GPU offload settings, context
  tier set, and memory budget?
- Which memory budget default is acceptable across CPU-only, unified-memory, and
  discrete-GPU environments?
- Should strict mode block adapter creation, execution, or only the profiling
  call?
- Should suggested kwargs include only `n_ctx` in v1, or also backend-specific
  values such as GPU layer/offload options when available?

## Validation Checklist

- [ ] Existing llama.cpp adapter construction and execution remain unchanged
      when profiling is not requested.
- [ ] Missing profiler returns an unavailable advisory result in fail-open mode.
- [ ] Fake profiler output normalizes to resident bytes, context slope, fit
      status, supported tiers, and maximum usable context.
- [ ] Requested context sizes above budget produce a lower effective context
      recommendation.
- [ ] Strict mode raises a package-owned error for unavailable or failed
      profiling.
- [ ] Tests use fake evaluators or fake command outputs only; no live llama.cpp,
      Hugging Face, server, or model-runtime dependency is required.
