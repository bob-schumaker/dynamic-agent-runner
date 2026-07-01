# Graphify Semantic Extractor Tool Validation Log

Status: First-release implementation complete; stock Graphify handoff remains external

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

FR-10 is intentionally not marked complete. Its benchmark, TDD, adaptive
retry, and reconciliation work is tracked in the post-first-release backlog in
`plan.md` and `tasks.md`; the current fixed chunk policy remains authoritative
until that evidence exists.
