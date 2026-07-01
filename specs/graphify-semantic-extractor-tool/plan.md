# Graphify Semantic Extractor Tool Implementation Plan

## Status

Implementation-ready planning artifact. This plan does not authorize code
changes until its task slice is explicitly scheduled. The user-requested
preparation expands the former light spec into a guided plan with TDD tasks.

## Objective and First Release

Add an opt-in package-owned Graphify exemplar that accepts a validated,
caller-supplied Graphify corpus manifest, invokes DAR-owned model/worker
collaborators in a bounded async workflow, validates Graphify-compatible
semantic JSON, and writes deterministic candidate artifacts outside the
accepted `graphify-out/` snapshot.

Graphify remains an external executable and owns graph construction, clustering,
reports, curation, diagnostics, query, and promotion. DAR exposes a dedicated
console entrypoint for the extraction stage, not an OpenAI-compatible server.

## Decisions and Boundaries

1. **Package boundary.** Add `src/dynamic_agent_runner/tools/graphify.py` and a
   small `src/dynamic_agent_runner/tools/__init__.py`. The module uses existing
   package dependencies and remains import-safe on every supported install.
2. **CLI shape.** Add the `dynamic-agent-runner-graphify-extract` script under
   `[project.scripts]`. It parses repository root, corpus manifest, candidate
   output, concurrency, required-glob, and model-policy options, then delegates
   to the package API. It must not create a second provider client or spawn
   additional Codex processes.
3. **Registry shape.** `create_graphify_semantic_extractor_tool(...)` returns a
   `RegisteredTool` for the canonical model-visible id
   `graphify_semantic_extract`. Callers register it explicitly in their
   effective `ToolRegistry`; installation never makes it ambient.
4. **Execution seam.** The implementation accepts an injected async-first
   worker/model collaborator. It must use DAR result shaping and registry
   boundaries; it must not construct an ad hoc OpenAI, Osaurus, Graphify, or
   Codex client.
5. **Manifest contract.** Define a package-owned immutable manifest value with
   repository root, relative source paths, source hashes, and optional required
   globs. A caller may derive it from Graphify detection output, but DAR does
   not invoke or parse the Graphify CLI.
6. **Filesystem safety.** Resolve and validate every source before any worker
   starts. Reject absolute paths, traversal, symlink escapes, source-code
   extensions, generated output, missing files, and files outside the admitted
   corpus. Candidate output must be a separate directory and may not be the
   accepted `graphify-out/` directory or snapshot.
7. **Worker isolation.** Workers receive corpus text as untrusted data in a
   fixed extraction prompt. Corpus instructions never become runtime policy.
   Chunk work is deterministic; a semaphore bounds concurrency; workers return
   mappings, not shared-file writes.
8. **Artifact contract.** Write a chunk manifest, per-chunk JSON results,
   `.graphify_semantic_new.json`, `.graphify_semantic.json` after validation, and
   an audit JSON. Merge order is chunk id then stable entity id. Failed chunks
   are explicit audit records and cannot silently disappear.
9. **Schema policy.** Validate the stable Graphify semantic subset and source
   provenance before merge. Reject dangling endpoints, self-loops, duplicate
   edges, invalid confidence values, unadmitted source paths, and missing
   required-file coverage.
10. **Release shape.** Python API, registry tool, and console entrypoint only.
    A Graphify dependency, OpenAI-compatible endpoint, ten-process Codex farm,
    and accepted-snapshot mutation are deferred.
11. **Blended chunking follow-on.** A later slice may add token-budget packing
    combined with a maximum file count, per-file content caps, adaptive
    bisection, and an optional summary-only reconciliation pass. Those changes
    are not part of the completed first-release plan and require benchmarks
    plus TDD coverage before changing the fixed chunk default.
12. **Adaptive policy selection.** A pure selector should estimate the admitted
    corpus and model headroom, compare fixed8 and token-aware request counts,
    return an auditable policy recommendation, and preserve fixed8 as the
    fallback when estimates or provider context are uncertain. Selection must
    remain separate from model execution until its benchmark gate passes.

## Affected Files and Components

### Source

- `src/dynamic_agent_runner/tools/__init__.py` — tool namespace and explicit
  exports.
- `src/dynamic_agent_runner/tools/graphify.py` — manifest, policy, worker
  protocol, chunk planning, validation, bounded execution, deterministic merge,
  audit, and `RegisteredTool` factory.
- `src/dynamic_agent_runner/cli.py` or a package-owned CLI module — thin
  `dynamic-agent-runner-graphify-extract` argument parser and delegation path,
  following existing CLI injection conventions.
- `src/dynamic_agent_runner/errors.py` — reuse existing package-owned boundary
  or add only the narrow Graphify extraction error types needed for actionable
  failure categories.
- `src/dynamic_agent_runner/__init__.py` — explicit package-root exports only
  if the existing public-export convention requires them.
- `pyproject.toml` — `dynamic-agent-runner-graphify-extract` script entrypoint.
- No dependency-file change is required; Graphify remains external and the
  implementation uses existing package dependencies and the standard library.

### Tests and fixtures

- `tests/test_graphify_tools.py` — fake workers, manifest safety, schema
  validation, deterministic merge, retries, audit, and opt-in registration.
- `tests/test_import.py` — import coverage if package-root exports are added.
- `tests/fixtures/graphify/` — small allowlisted Markdown corpus and stable
  semantic JSON fixtures; no generated graph output or live model data.

### Documentation and artifacts

- `README.md` or authored `docs/files/` page — installation and staged Graphify
  handoff example, following the existing documentation workflow.
- `specs/graphify-semantic-extractor-tool/{spec,plan,tasks,validation}.md` —
  implementation artifacts and evidence.
- `specs/README.md` — status remains future/implementation-ready until code and
  validation are complete.

## Data Flow

```text
caller/Graphify detect evidence
  -> GraphifyCorpusManifest validation
  -> deterministic chunk plan
  -> bounded async GraphifySemanticWorker calls
  -> per-chunk schema/provenance validation
  -> deterministic merge + audit in candidate output root
  -> stock Graphify build/curate/validate/diagnose/promote
```

The accepted `graphify-out/` path is never a write target for the DAR helper.
Graphify's existing curation and promotion helper remains the authority for
accepting a candidate graph.

## Slice Plan

### Slice 0 — Planning checkpoint

Finalize this plan, TDD task list, validation log, decisions, and corpus-index
status. Run Markdown validation and record the planning checkpoint before source
implementation.

### Slice 1 — Package, registry, and console contract

Add the package namespace, package-owned policy/result types, worker protocol,
explicit `RegisteredTool` factory, and console `--help`/argument contract. Tests
prove the tool remains opt-in and the script delegates rather than reimplements
extraction.

### Slice 2 — Manifest validation and chunk planning

Implement immutable manifest validation, source hashing, corpus allowlist and
path containment checks, output-root safety, required-glob checks, and stable
chunk planning. Tests prove no worker runs after a preflight rejection.

### Slice 3 — Worker isolation and semantic validation

Implement the fixed untrusted-data extraction request, strict JSON decoding,
Graphify subset validation, provenance checks, confidence normalization, and
bounded retry/failure classification. Tests use fake workers that return valid,
invalid, instruction-injection, and partial results.

### Slice 4 — Bounded execution, merge, and audit

Implement async semaphore scheduling, arbitrary completion-order collection,
deterministic merge, per-chunk artifacts, final candidate artifacts, and audit
records. Tests repeat merges with shuffled worker completion and compare bytes.

### Slice 5 — Runtime integration, console delegation, and handoff

Verify `RegisteredTool` invocation uses existing validation/result shaping,
redacts traces, and remains opt-in. Verify the console script delegates to the
same API with fake model/worker collaborators. Add installation and staged-
handoff docs; do not add live Graphify integration in this release.

### Slice 6 — Completion gate

Run focused tests, full tests, lint, package build, focused pre-commit, and
spec-index consistency checks. Update status only after all gates pass.

### T7 — Post-first-release blended extraction (implemented opt-in)

The T7 follow-on scope is implemented as opt-in behavior and does not change
the first-release fixed-chunk default:

- benchmark token-aware packing against the current fixed file-count planner;
- add configurable token budget, maximum files, and per-file content cap;
- add adaptive split/retry tests for context overflow and dense output;
- evaluate a summary-only cross-chunk reconciliation pass for accuracy gains;
- update the default only after deterministic merge, audit, and DAR policy
  behavior remain unchanged.

### Slice 8 — Adaptive chunk-policy selector

Prepare a pure estimator and selector over an admitted manifest. Add TDD
coverage for missing estimates, oversized files, fixed-versus-token predicted
chunk counts, model headroom, deterministic reason codes, and the unchanged
fixed8 fallback. Do not wire selection into live execution until benchmark
evidence and a separate default-policy decision are recorded.

## Risks and Mitigations

- **Prompt injection from corpus files:** fixed system/developer extraction
  instructions, explicit data delimiters, no tool access in workers, and output
  schema validation.
- **Graph corruption:** validate every chunk before merge, reject malformed
  endpoints, preserve the prior accepted snapshot, and require stock curation.
- **Nondeterministic parallelism:** stable chunk ids, stable entity sorting,
  single-parent merge, and no shared worker writes.
- **Scope creep into a server:** keep the endpoint, CLI, Graphify dependency,
  Codex process farm, and accepted-snapshot mutation as explicit non-goals.

## Required Gate Before Implementation

- User or maintainer schedules Slice 1 after reviewing this plan.
- `tasks.md` remains test-first and maps every first-release requirement.
- `validation.md` records planning evidence and exact commands before source
  edits begin.
