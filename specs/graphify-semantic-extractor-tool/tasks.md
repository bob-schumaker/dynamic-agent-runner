# Graphify Semantic Extractor Tool Tasks

Status: First-release implementation complete; stock Graphify handoff remains external

## Slice 0 — Planning Checkpoint

- [x] T0.1 Resolve the first-release boundary: artifact producer, external
      Graphify executable, Python API, registry tool, and console entrypoint;
      no endpoint.
      - Spec: FR-9, Non-Goals, First Release Boundary
- [x] T0.2 Define the package, manifest, worker, artifact, and safety
      contracts in `plan.md`.
- [x] T0.3 Create `tasks.md` and `validation.md` with TDD-first execution
      order and exact repository commands.
- [x] T0.4 Commit the planning checkpoint before source implementation.
      - Completed in `e4164e5`.

## Slice 1 — Package, Registry, and Console Contract

- [x] T1.1 [tests] Add RED tests for the public policy/result/worker contracts,
      explicit `RegisteredTool` factory, console `--help`, and invalid CLI
      argument handling.
      - Spec: FR-1, FR-8; Plan: Decisions 1–3
      - Files: `tests/test_graphify_tools.py`, `tests/test_cli.py`,
        `tests/test_import.py`
      - RED: `poetry run pytest tests/test_graphify_tools.py -q` failed during
        collection because `dynamic_agent_runner.tools` was absent.
- [x] T1.2 [implementation] Add `tools` package namespace, package-owned error
      and result types, worker protocol, policy, and
      `graphify_semantic_extract` tool factory.
      - Files: `src/dynamic_agent_runner/tools/__init__.py`,
        `src/dynamic_agent_runner/tools/graphify.py`,
        `src/dynamic_agent_runner/errors.py`,
        `src/dynamic_agent_runner/__init__.py`
      - Validation:
        `poetry run pytest tests/test_graphify_tools.py tests/test_import.py -q`
      - GREEN: `poetry run pytest tests/test_graphify_tools.py -q` — `4 passed`.
- [x] T1.3 [implementation] Add the
      `dynamic-agent-runner-graphify-extract` `[project.scripts]` entrypoint as
      a thin delegate to the package API, with repository root, manifest,
      output, concurrency, required-glob, and model-policy options.
      - Spec: FR-1, FR-5, First Release Boundary
      - Files: `src/dynamic_agent_runner/cli.py` or package-owned CLI module,
        `pyproject.toml`
      - Validation:
        `poetry run python -m dynamic_agent_runner.tools.graphify_cli --help`
      - Result: parser exposes repository, manifest, output, concurrency,
        required-glob, and model options; package metadata passes `poetry check`.

## Slice 2 — Manifest Validation and Chunk Planning

- [x] T2.1 [tests] Add RED fixtures for relative-path enforcement, traversal,
      absolute paths, missing files, symlink escape, code/generated-file
      rejection, accepted corpus files, source hashes, required globs, output
      root containment, and deterministic chunk planning.
      - Spec: FR-2, FR-6; Plan: Decisions 5–7
      - Files: `tests/test_graphify_tools.py`, `tests/fixtures/graphify/`
- [x] T2.2 [implementation] Implement immutable manifest validation, source
      hashing, required-glob coverage, candidate-output safety, and stable
      chunk planning before worker scheduling.
      - Files: `src/dynamic_agent_runner/tools/graphify.py`
      - Validation: `poetry run pytest tests/test_graphify_tools.py -q`
      - Invariant: any preflight failure starts zero workers.
      - RED: collection failed because manifest types and validators were absent.
      - GREEN: `poetry run pytest tests/test_graphify_tools.py -q` — `12 passed`.

## Slice 3 — Worker Isolation and Semantic Validation

- [x] T3.1 [tests] Add RED fake-worker tests for valid semantic JSON, malformed
      JSON, instruction-like corpus text, invalid source provenance, dangling
      endpoints, self-loops, duplicate edges, invalid confidence, missing
      required coverage, bounded retry, and explicit failed-chunk audit state.
      - Spec: FR-3, FR-4, FR-6, FR-7
      - Files: `tests/test_graphify_tools.py`, semantic JSON fixtures
- [x] T3.2 [implementation] Add fixed extraction request construction that
      treats corpus text as untrusted data, strict semantic-subset validation,
      provenance checks, bounded retry, and failure classification.
      - Files: `src/dynamic_agent_runner/tools/graphify.py`
      - Validation: `poetry run pytest tests/test_graphify_tools.py -q`
      - RED: collection failed because semantic validation and worker request
        helpers were absent.
      - GREEN: `poetry run pytest tests/test_graphify_tools.py -q` — `19 passed`.

## Slice 4 — Bounded Execution, Merge, and Audit

- [x] T4.1 [tests] Add RED async tests for semaphore-bounded scheduling,
      arbitrary worker completion order, deterministic artifact bytes, isolated
      per-chunk outputs, successful/failed/retried/repaired audit records, and
      no writes to accepted `graphify-out/`.
      - Spec: FR-5, FR-7; Plan: Data Flow and Decisions 6–8
      - Files: `tests/test_graphify_tools.py`
- [x] T4.2 [implementation] Implement bounded async execution, per-chunk JSON,
      deterministic merge, `.graphify_semantic_new.json`, validated
      `.graphify_semantic.json`, chunk manifest, source-hash audit, and stable
      result mapping.
      - Files: `src/dynamic_agent_runner/tools/graphify.py`
      - Validation: `poetry run pytest tests/test_graphify_tools.py -q`
      - RED: extraction helpers were absent and collection failed.
      - GREEN: `poetry run pytest tests/test_graphify_tools.py -q` — `21 passed`.

## Slice 5 — Runtime Integration, Console Delegation, and Documentation

- [x] T5.1 [tests] Add RED/GREEN coverage proving explicit registry
      registration is required, tool invocation uses existing result shaping,
      and sensitive corpus/worker details are not emitted in model-facing
      output or traces.
      - Spec: FR-1, FR-8; Files: `tests/test_graphify_tools.py`,
        `tests/test_registry.py`
- [x] T5.2 [tests] Add RED/GREEN coverage proving the console script delegates
      to the same extraction API with a fake worker/model path and does not
      spawn additional processes or invoke Graphify.
      - Spec: FR-1, FR-5, FR-9; Files: `tests/test_graphify_tools.py`
- [x] T5.3 [implementation] Wire only the required exports and registry
      metadata; preserve the existing `ToolRegistry` invocation path and
      capability boundaries.
      - Files: `src/dynamic_agent_runner/tools/graphify.py`, package exports
- [x] T5.4 [docs] Add installation, console usage, and staged-handoff
      documentation using authored README/Sphinx sources. Do not document an
      endpoint, live Graphify dependency, or accepted-snapshot mutation.
      - Files: `README.md` or `docs/files/` selected during implementation
      - Evidence: README documents console invocation, manifest/output
        boundaries, and stock Graphify handoff.

## Slice 6 — Completion Gate

- [x] T6.1 Run focused tests:
      `poetry run pytest tests/test_graphify_tools.py tests/test_import.py -q`
- [x] T6.2 Run affected registry tests and then the full suite:
      `poetry run pytest tests/test_registry.py tests/test_capabilities.py`
      `tests/test_import.py -q`
      and `poetry run pytest -q`
- [x] T6.3 Run `poetry run ruff check src tests` and package build
      `poetry build`.
- [x] T6.4 Run focused pre-commit on changed source, tests, docs, specs,
      `pyproject.toml`, and lockfile.
- [x] T6.5 Run spec-link/status consistency checks and update `specs/README.md`
      only after implementation evidence exists.
- [x] T6.6 Record final evidence, update feature status, and prepare a separate
      implementation commit from this planning checkpoint.

### Completion evidence

- Focused and affected tests: `86 passed`.
- Full suite: `poetry run pytest -q` — `616 passed`.
- Lint: `poetry run ruff check src tests` — passed.
- Metadata: `poetry check` — passed.
- Installed entrypoint help: `dynamic-agent-runner-graphify-extract --help` — passed.
- Package build: attempted with `poetry build`; blocked by unavailable
  `artifactory.oci.oraclecorp.com` in the execution environment.
- Focused pre-commit and `git diff --check` passed before the completion commit.
- Unit tests use fake workers; no live provider or Graphify process is required.

## Post-First-Release Backlog — Blended Chunking

These tasks are not authorized by the completed first-release slice:

- [x] T7.1 [benchmark] Compare fixed file-count and token-aware packing for
      request size, latency, failure rate, and semantic coverage.
      - Baseline recorded before planner changes; token-aware comparison is
        completed in T7.2 and documented in `validation.md`.
- [x] T7.2 [tests] Add TDD coverage for configurable token budgets, maximum
      files per chunk, per-file content caps, and deterministic directory-aware
      packing.
      - Implemented as an opt-in planner; fixed eight-file behavior remains
        the default pending T7.5.
- [ ] T7.3 [implementation] Add adaptive bisection for context overflow,
      truncation, and density-related validation failures while preserving
      chunk ids, audit records, and accepted-snapshot protection.
- [ ] T7.4 [evaluation] Test a summary-only cross-chunk reconciliation pass;
      do not resend source text or bypass DAR approval and tracing.
- [ ] T7.5 [decision] Change the default chunk policy only after benchmark and
      regression evidence is recorded in `validation.md`.
