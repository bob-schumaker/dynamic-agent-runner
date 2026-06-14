# llmfit Model Fit Filter Specification

## Metadata

- Feature slug: `llmfit-model-fit-filter`
- Mode: `light`
- Artifact type: future feature specification
- Status: proposed future feature; no implementation started
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Related feature specs:
  - `specs/hugging-face-model-search/spec.md`
  - `specs/hugging-face-support-layer/spec.md`
  - `specs/llama-cpp-local-model/spec.md`
  - `specs/mlx-local-model-adapter/spec.md`
- Related implementation surfaces:
  - `src/dynamic_agent_runner/hugging_face_models.py`
  - `src/dynamic_agent_runner/local_models.py`
  - `src/dynamic_agent_runner/mlx_models.py`
  - `src/dynamic_agent_runner/errors.py`

## Objective

Define an optional pre-download model-fit filter that uses an already-installed
`llmfit` executable, when present on `PATH`, to keep Hugging Face candidate
models that are recommended for the local machine while preserving unknown
models for caller review.

## Problem Statement

`dynamic-agent-runner` can already search Hugging Face models and can resolve
explicit Hugging Face file or snapshot references for local model adapters.
Those surfaces intentionally remain separate: discovery does not imply
download, and downloads require explicit caller-provided references.

The missing step is a lightweight advisory pass between discovery and download.
Callers preparing local llama.cpp or MLX execution need a way to avoid fetching
model assets that are already known to be a poor fit for the machine. The
repository should support that preflight without embedding llmfit's model
database, installing llmfit for the user, or making model search automatically
drive downloads.

Council roadmap note: this is a useful but lower-risk local-model ergonomics
feature. It should remain small, optional, read-only, and advisory rather than
competing with the approval/sandbox/status vertical slice for core runtime
priority.

## Discovery Summary

`~/Repos/github/llmfit` provides a Rust CLI/TUI that detects local hardware,
loads an embedded model metadata database, and scores models before any model
weights are downloaded.

Useful observed behavior:

- `llmfit system --json` reports local hardware including RAM, available RAM,
  CPU cores, GPU backend, GPU name, VRAM, GPU count, and unified-memory status.
- `llmfit fit --json --limit 5 --sort score` returns ranked model entries with
  fields such as `name`, `runtime`, `fit_level`, `best_quant`,
  `memory_required_gb`, `memory_available_gb`, `estimated_tps`, `context_length`,
  `capability_ids`, `gguf_sources`, and explanatory `notes`.
- On the inspected machine, llmfit reported Apple M3 Pro, Metal, unified memory,
  36 GB total RAM, and 29.5 GB available RAM.
- llmfit supports CLI JSON, local REST API, and MCP modes. CLI JSON is the
  lowest-friction optional integration for this package.

## Scope

This feature covers:

1. detecting whether `llmfit` is available on `PATH`
2. invoking an already-installed `llmfit` executable in read-only JSON mode
3. normalizing llmfit fit output into repository-owned advisory values
4. filtering candidate Hugging Face model results to recommended plus unknown
   models
5. preserving search/download separation and explicit download references
6. deterministic tests using fake llmfit outputs and no live network

This feature does not cover:

1. bundling, vendoring, embedding, installing, or updating llmfit
2. adding llmfit as a required dependency
3. copying llmfit's embedded model database into this repository
4. porting llmfit's Rust scoring engine into Python
5. starting `llmfit serve`, using MCP mode, or managing a background llmfit
   process in the first implementation
6. automatically converting recommended models into downloads or local adapters
7. replacing `search_hugging_face_models(...)`

## Assumptions and Definitions

- **Recommended model** means a model that llmfit explicitly reports as locally
  suitable under this package's configured threshold. The default threshold
  should be `good`, meaning `Perfect` and `Good` fit levels pass.
- **Unknown model** means a candidate Hugging Face result that cannot be matched
  to a llmfit result, or a result whose fit cannot be classified from available
  llmfit output. Unknown models pass through the filter.
- **Filtered-out model** means a candidate that llmfit can identify and
  classifies below the configured recommendation threshold, such as `Marginal`
  or `TooTight` when the threshold is `good`.
- If `llmfit` is not on `PATH`, the feature must not filter out any candidates.
  The caller may receive an advisory status explaining that llmfit was
  unavailable.
- The package must not install llmfit or instruct runtime code to install it.
  Installation remains caller- or environment-owned.

## Functional Requirements

### FR-1: Detect optional llmfit availability

The package must treat llmfit as an optional external executable.

Acceptance criteria:

- Given `llmfit` is present on `PATH`, when the fit filter is requested, then
  the package may invoke it through a narrow read-only command runner.
- Given `llmfit` is absent from `PATH`, when the fit filter is requested, then
  the package returns the original candidate set unchanged and marks the
  advisory state as unavailable.
- Given the package is imported, when no fit filter is requested, then no llmfit
  detection or subprocess invocation occurs.

### FR-2: Use llmfit only through read-only JSON output

The first implementation must consume llmfit through CLI JSON, not through
vendored code, REST server management, or MCP server management.

Acceptance criteria:

- Given llmfit is available, when model-fit evaluation runs, then the package
  invokes read-only commands such as `llmfit fit --json`.
- Given llmfit emits invalid JSON or exits unsuccessfully, when the filter is in
  fail-open mode, then candidates remain unchanged and the advisory status
  records the failure.
- Given tests cover llmfit behavior, when they run, then fake command runners
  provide JSON payloads instead of executing the real binary.

### FR-3: Normalize llmfit output into package-owned advisory records

The package must not expose raw llmfit JSON as the primary public contract.

Acceptance criteria:

- Given llmfit returns model rows, when the package exposes fit information, then
  each row is represented by repository-owned values with stable fields.
- The normalized result should include model id/name, fit level, runtime, best
  quantization, memory required, memory available, estimated tokens per second,
  effective context length, capabilities, GGUF sources, and notes when present.
- Unknown or future llmfit fields are ignored unless a later spec expands the
  public contract.

### FR-4: Filter to recommended plus unknown candidates

The filter must remove only candidates that are known to be below the configured
fit threshold.

Acceptance criteria:

- Given a Hugging Face candidate matches a llmfit row whose fit level is
  `Perfect` or `Good`, when the default threshold is `good`, then the candidate
  remains in the returned set.
- Given a candidate matches a llmfit row whose fit level is below the configured
  threshold, when filtering runs, then the candidate is excluded from the
  returned set and may be reported in diagnostics.
- Given a candidate cannot be matched to a llmfit row, when filtering runs, then
  the candidate remains in the returned set as unknown.
- Given multiple llmfit rows plausibly match a candidate, when one row satisfies
  the threshold and another does not, then the candidate should remain and the
  selected advisory should prefer the stronger fit.

### FR-5: Preserve explicit discovery and download boundaries

The filter must remain advisory and must not change asset-resolution semantics.

Acceptance criteria:

- Given `search_hugging_face_models(...)` returns candidates and llmfit marks
  some as recommended, when the caller wants to download a model, then the caller
  must still provide an explicit `HuggingFaceModelFileReference` or
  `HuggingFaceSnapshotReference`.
- Given a candidate survives the fit filter, when local-model execution is
  configured, then existing local path, cache, offline-policy, and identity
  validation behavior remains authoritative.
- Given llmfit includes `gguf_sources`, when those are surfaced, then they are
  advisory metadata only unless a later spec explicitly approves converting them
  into runtime-owned download references.

### FR-6: Keep failure behavior fail-open by default

Model-fit filtering must not make Hugging Face discovery brittle.

Acceptance criteria:

- Given llmfit is absent, broken, slow, or returns invalid output, when fail-open
  mode is active, then the package preserves all input candidates.
- Given a caller explicitly requests strict fit filtering, when llmfit is
  unavailable or unusable, then the package may raise a package-owned error
  rather than silently preserving candidates.
- Given filtering excludes models, when diagnostics are requested, then callers
  can inspect why a candidate was kept, excluded, or unknown.

### FR-7: Keep tests deterministic and live-network-free

Unit tests must not depend on live Hugging Face or real llmfit installation.

Acceptance criteria:

- Tests use fake Hugging Face search results and fake llmfit command outputs.
- Tests cover llmfit absent, invalid JSON, recommended match, below-threshold
  match, unknown candidate, ambiguous match, and strict failure mode.
- Tests do not start local REST servers, MCP servers, model runtimes, or model
  downloads.

## Suggested Public API Shape

A future implementation may expose a small package-owned API such as:

```python
filter_hugging_face_models_by_local_fit(
    candidates: Sequence[HuggingFaceModelSearchResult],
    *,
    min_fit: str = "good",
    mode: str = "fail_open",
    runtime: str | None = None,
    use_case: str | None = None,
    evaluator: LocalModelFitEvaluator | None = None,
) -> LocalModelFitFilterResult
```

Where `LocalModelFitFilterResult` contains:

- kept candidates
- excluded candidates
- advisory records keyed by candidate repo id
- unknown candidate ids
- filter status such as `available`, `unavailable`, or `failed_open`

This suggested shape is not implementation approval. Future `plan.md` and
`tasks.md` artifacts should decide exact names, exports, and data structures.

## Matching Guidance

The first implementation should keep matching conservative.

Possible matching inputs:

- exact repository id match against llmfit `name`
- exact match against llmfit `gguf_sources[].repo`
- case-insensitive exact match as a fallback

The first implementation should avoid broad fuzzy matching unless diagnostics
make ambiguity explicit. Unknown is safer than incorrectly filtering out a
candidate.

## Design Constraints

- Treat llmfit as optional environment capability, not a package dependency.
- Use repository-owned public dataclasses/errors rather than raw subprocess
  output as the public contract.
- Keep the implementation read-only.
- Do not add live network, real llmfit, model runtime, or model download
  requirements to unit tests.
- Preserve the existing separation among Hugging Face search, support-layer Hub
  calls, and local-model asset resolution.
- Do not automatically install missing tools.

## Risks and Compatibility Notes

- llmfit's embedded database may not contain every Hugging Face candidate. That
  is why unknown candidates pass through.
- llmfit recommendation quality depends on its installed version and local model
  metadata. The package should report advisory provenance where possible.
- Fit-level strings may change or appear in different casing. Normalization
  should be explicit and tested.
- Top llmfit recommendations are not equivalent to scoring arbitrary Hub search
  results. The first feature should be framed as filtering known candidates and
  preserving unknowns, not as comprehensive model compatibility proof.

## Validation Checklist

- [ ] `llmfit` absence keeps all candidates and reports unavailable status.
- [ ] Valid llmfit JSON keeps `Perfect` and `Good` candidates by default.
- [ ] Valid llmfit JSON filters below-threshold known candidates.
- [ ] Unknown candidates remain in the returned candidate set.
- [ ] Invalid llmfit JSON fails open by default.
- [ ] Strict mode raises a package-owned error when llmfit cannot be used.
- [ ] Candidate matching covers exact model names and GGUF source repos.
- [ ] Unit tests use fake command runners and no live Hugging Face/model calls.
- [ ] Documentation explains that llmfit is optional and never installed by the
      package.

## NEEDS CLARIFICATION

- Should the default threshold be `good`, or should `marginal` also pass for
  small local-model experiments?
- Should the first API filter existing `HuggingFaceModelSearchResult` values
  only, or should it also offer a combined search-and-filter convenience helper?
- Should llmfit `runtime` and `use_case` filters be part of v1 or left to a
  later implementation slice?
- Should strict mode be public in v1, or should all first-pass behavior be
  fail-open?
- Should advisory diagnostics be returned by default or only when explicitly
  requested?
