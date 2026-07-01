# Graphify Semantic Extractor Tool Validation Log

Status: First-release and T8 selector implementation complete; stock Graphify
handoff and default-policy gate remain external

## Scope

- Feature: `specs/graphify-semantic-extractor-tool/spec.md`
- Plan: `specs/graphify-semantic-extractor-tool/plan.md`
- Tasks: `specs/graphify-semantic-extractor-tool/tasks.md`
- Evidence: `specs/graphify-semantic-extractor-tool/analysis.md`

## Planning Decisions Recorded

- Graphify remains an external executable; DAR produces staged semantic
  artifacts and does not provide an OpenAI-compatible server.
- The first release is a Python API, explicit registry tool, and
  `dynamic-agent-runner-graphify-extract` console entrypoint.
- The caller supplies a small DAR-owned corpus manifest derived from reviewed
  Graphify detection evidence; DAR does not invoke Graphify.
- Workers are injected async-first collaborators and receive corpus text as
  untrusted data. Unit tests use fakes only.
- Candidate artifacts are written outside accepted `graphify-out/`; stock
  Graphify curation, validation, diagnostics, and promotion remain required.
- The implementation uses existing package dependencies and the standard
  library; Graphify itself is not a package dependency.

## Planning Gate Checks

| Check | Result |
| --- | --- |
| First-release requirements mapped to plan slices | Pass: FR-1 through FR-9 map to Slices 1–5; FR-10 is explicitly post-first-release |
| Every first-release item has TDD coverage | Pass: RED tasks precede implementation tasks |
| No task authorizes live provider or Graphify calls | Pass |
| Accepted snapshot mutation prohibited | Pass |
| Optional endpoint/Codex-process-farm scope deferred; console entrypoint in scope | Pass |
| Existing registry and result-shaping boundaries preserved | Pass |
| Implementation-blocking questions resolved | Pass: decisions recorded in `spec.md` and `plan.md` |

## Slice 1 — Package, Registry, and Console Contract

### RED

- Command: `poetry run pytest tests/test_graphify_tools.py -q`
- Observed result: collection failed because `dynamic_agent_runner.tools` did
  not exist.
- Interpretation: the public package and Graphify tool contract were not yet
  implemented.

### GREEN

- Command: `poetry run pytest tests/test_graphify_tools.py -q`
- Observed result: `4 passed`.
- Interpretation: policy/result/worker contracts, explicit registry factory,
  and parser argument shape are covered by fakes and local values.

### Console and Packaging Checks

- Command: `poetry run python -m dynamic_agent_runner.tools.graphify_cli --help`
- Observed result: usage includes `--repo-root`, `--corpus-manifest`,
  `--output-dir`, `--concurrency`, `--required-glob`, and `--model`.
- Command: `poetry run ruff check src/dynamic_agent_runner/tools tests/test_graphify_tools.py`
- Observed result: passed.

## Slice 3 — Worker Isolation and Semantic Validation

### RED

- Command: `poetry run pytest tests/test_graphify_tools.py -q`
- Observed result: collection failed because semantic validation and worker
  request helpers were absent.

### GREEN

- Command: `poetry run pytest tests/test_graphify_tools.py -q`
- Observed result: `19 passed`.
- Interpretation: strict JSON decoding, source provenance, endpoint integrity,
  self-loop and duplicate rejection, confidence bounds, and untrusted corpus
  request construction are covered.
- Command: `poetry run ruff check src/dynamic_agent_runner/tools tests/test_graphify_tools.py`
- Observed result: passed.
- Command: `poetry check`
- Observed result: `All set!`.

## Slice 2 — Manifest Validation and Chunk Planning

### RED

- Command: `poetry run pytest tests/test_graphify_tools.py -q`
- Observed result: collection failed because `GraphifyCorpusManifest` and
  manifest validation helpers were absent.

### GREEN

- Command: `poetry run pytest tests/test_graphify_tools.py -q`
- Observed result: `12 passed`.
- Interpretation: relative-path, traversal, code/generated-file, symlink,
  output-root, hash, required-glob, and deterministic chunk checks pass.
- Command: `poetry run ruff check src/dynamic_agent_runner/tools tests/test_graphify_tools.py`
- Observed result: passed.

## Slice 4 — Bounded Execution, Merge, and Audit

### RED

- Command: `poetry run pytest tests/test_graphify_tools.py -q`
- Observed result: collection failed because bounded extraction and merge
  helpers were absent.

### GREEN

- Command: `poetry run pytest tests/test_graphify_tools.py -q`
- Observed result: `21 passed`.
- Interpretation: semaphore-bounded async workers, out-of-order completion,
  deterministic merged bytes, per-chunk artifacts, retries, failed-chunk audit,
  and accepted-snapshot protection are covered.
- Command: `poetry run ruff check src/dynamic_agent_runner/tools tests/test_graphify_tools.py`
- Observed result: passed after formatter cleanup.

### Console Delegation and Documentation

- Command: `poetry install --only main`
- Observed result: current package installed with the new script metadata.
- Command: `poetry run dynamic-agent-runner-graphify-extract --help`
- Observed result: command exposes repository, manifest, output, concurrency,
  required-glob, and model options.
- Documentation: `README.md` now documents cross-repository invocation and the
  stock Graphify staged-artifact handoff.

## Commands for Planning Checkpoint

- `git diff --check`
- `pre-commit run --files specs/graphify-semantic-extractor-tool/spec.md`
  `specs/graphify-semantic-extractor-tool/analysis.md`
  `specs/graphify-semantic-extractor-tool/plan.md`
  `specs/graphify-semantic-extractor-tool/tasks.md`
  `specs/graphify-semantic-extractor-tool/validation.md specs/README.md`
- Repository spec-link/status consistency script used during the prior corpus
  pass: all 41 README feature links resolved and no unqualified missing internal
  spec references remained.

## Completion Evidence

- Focused and affected tests: `86 passed`.
- Full suite: `poetry run pytest -q` — `616 passed`.
- Ruff: `poetry run ruff check src tests` — passed.
- Metadata: `poetry check` — passed.
- Installed console entrypoint help passed for
  `dynamic-agent-runner-graphify-extract --help`.
- Package build was attempted with `poetry build` but could not resolve the
  configured Artifactory host in this environment. No source or test failure
  was observed.
- Focused pre-commit and `git diff --check` passed for the completion slice.
- Unit tests use fake workers and do not call a live model or Graphify.

The staged artifacts remain outside accepted `graphify-out/`; running stock
Graphify to curate, validate, diagnose, and promote them is an explicit
downstream handoff and is not part of this package implementation.

## Deferred blended-chunking scope

FR-10 is implemented as opt-in behavior. Its benchmark, TDD, adaptive retry,
and reconciliation evidence is recorded below; the current fixed chunk policy
remains authoritative because the default-policy gate did not pass.

## T7.1 — Fixed-chunk baseline

- Command: `poetry run python - <<'PY' ...` using 100 synthetic 1,000-byte
  Markdown files and the current `plan_graphify_chunks(..., chunk_size=8)`.
- Observed result: 13 chunks with distribution `8, 8, 8, ..., 4`.
- Interpretation: the current policy is deterministic but has no relationship
  to request size; this is the baseline for the token-aware comparison in T7.2.

## T7.2 — Token/file-bounded planner

- RED: added focused tests for token budget, maximum file count, directory
  grouping, and shared per-file content caps; the new planner API was absent.
- GREEN: `poetry run pytest tests/test_graphify_tools.py -q` — `26 passed`.
- Implementation: `plan_graphify_chunks(..., token_budget=...,`
  `max_files_per_chunk=..., max_file_chars=...)` is opt-in; request construction
  applies the same per-file cap and the fixed eight-file default is preserved.

## T7.3 — Adaptive density splitting

- RED: added a fake-worker test returning `finish_reason="length"` for dense
  multi-file chunks; the prior implementation retried the same chunk and then
  failed without producing leaf results.
- GREEN: `poetry run pytest tests/test_graphify_tools.py -q` — `27 passed`.
- Implementation: explicit context/truncation signals are bisected recursively
  within the configured retry depth; ordinary schema failures retain the
  existing bounded retry and audit behavior.

## T7.4 — Summary-only reconciliation evaluation

- RED: added a test proving a reconciliation payload must omit document
  content; no summary-only request seam existed.
- GREEN: `poetry run pytest tests/test_graphify_tools.py -q` — `28 passed`.
- Implementation: `build_graphify_reconciliation_request(...)` carries only
  node, edge, hyperedge identifiers, labels, relations, endpoints, and source
  provenance. It is opt-in and does not execute a model or write artifacts.

## T7.5 — Default-policy decision gate

- Command: `poetry run pytest tests/test_graphify_tools.py`
  `tests/test_import.py -q` — `29 passed`.
- Command: `poetry run ruff check src/dynamic_agent_runner/tools`
  `tests/test_graphify_tools.py` — passed.
- Decision: retain the fixed eight-file default. The token-aware planner,
  adaptive splitting, and reconciliation seam are opt-in until a benchmark
  compares request size, latency, failure rate, and semantic coverage on a
  representative corpus.

## T8 — Adaptive chunk-policy selector preparation

T8 implementation is complete for the package-owned immutable estimate/decision
values and pure
helpers in `src/dynamic_agent_runner/tools/graphify.py`, with focused tests in
`tests/test_graphify_tools.py` (or a narrowly split policy test module).

Required evidence for the implementation slice:

- RED tests for manifest statistics, capped and unreliable estimates, model
  input headroom, predicted fixed/token-aware chunk counts, concurrency, and
  stable reason codes;
- GREEN tests proving unknown context, provider instability, and unsafe files
  choose the explicit `fixed8` fallback or isolate the file;
- a no-side-effect assertion showing that selection neither calls a worker or
  model nor mutates the manifest;
- focused Graphify tests, Ruff, `git diff --check`, and focused pre-commit.

The selector remains advisory: T8 does not add CLI wiring, alter extraction
defaults, or make live provider calls. Sibling-corpus benchmark evidence and a
separate approval are required before any runtime policy change.

## T8 implementation evidence

- Commit `6795a76` added immutable `GraphifyCorpusEstimate` and
  `GraphifyChunkPolicyDecision` values plus pure estimator/selector helpers.
- Commit `b1ab04e` added safety coverage for oversized-file isolation,
  provider-instability fallback, and deterministic concurrency reduction.
- Focused tests: `poetry run pytest tests/test_graphify_tools.py -q` — `39 passed`.
- Ruff: `poetry run ruff check src/dynamic_agent_runner/tools
  tests/test_graphify_tools.py` — passed.
- Focused pre-commit and `git diff --check` passed for the implementation
  slices.

## T8 planning benchmark

The selector was run locally against 13 sibling repositories containing a
`memory-bank` or `cline-tasks` directory, using a 114,688-token context and an
8,192-token output reserve. It selected `token_aware` for 3 repositories and
`fixed8` for 10; no files were isolated. This benchmark measured deterministic
planning only. Live observed latency, provider failures, and provenance
coverage were not rerun, so T8.7 and the runtime-default decision remain open.
