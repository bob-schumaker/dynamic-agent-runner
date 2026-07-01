# Apple Foundation Models Adapter Validation Log

Status: A1 implementation complete; eligible-Mac live verification pending

## Scope

- Feature: `specs/apple-foundation-model-adapter/spec.md`
- Plan: `specs/apple-foundation-model-adapter/plan.md`
- Tasks: `specs/apple-foundation-model-adapter/tasks.md`
- A1 only: local final text and explicit JSON Schema output.
- A2 Apple tool callbacks remain separately gated.

## Preparation checks

- Spec, plan, tasks, and validation artifacts now exist and agree on A1/A2
  boundaries.
- The existing async OpenAI adapter and strict model-coverage path are the only
  approved executor seams.
- Unit/live test separation is explicit: fakes for deterministic tests, marked
  eligible-Mac tests for real Apple generation.
- The original preparation slice made no source or dependency changes; A1
  implementation now exists in commits `4af46fb`, `df88337`, `e773531`, and
  `01c1146`, while runtime defaults remain unchanged.

## Executed A1 evidence

- Slice 1: `4af46fb` — lazy contract, portability, and fail-closed tests.
- Slice 2: `df88337` — session translation, cancellation, and optional SDK
  dependency metadata.
- Slice 3: `e773531` — structured-output validation, capability metadata, and
  package-owned error causes.
- Slice 4: `01c1146` — strict executor selection coverage.
- Slice 5: live text/JSON/workflow tests and README documentation are prepared;
  live tests skip unless `DAR_RUN_LIVE_APPLE=1` is set on an eligible Mac.
- Focused implementation suite: `149 passed, 2 skipped`.
- `poetry check`, Ruff, and focused pre-commit passed.

## Slice 6 completion-gate evidence

- Full suite: `poetry run pytest -q` — `654 passed, 4 skipped`.
- Live marker: `poetry run pytest -m apple_live -q` — `3 skipped` with the
  explicit `DAR_RUN_LIVE_APPLE=1` / eligible-mac prerequisite.
- Ruff: `poetry run ruff check src tests` — passed.
- Metadata: `poetry check` — passed.
- Package build: `poetry build` — passed with network-enabled retry.
- Focused pre-commit and `git diff --check` pass for the final slice.

The implementation and deterministic validation gates are complete. The live
Apple checks remain pending on the designated eligible Mac; the tests are
marked and ready to run with `DAR_RUN_LIVE_APPLE=1`.

## Required evidence by slice

### Slice 1

Record RED failures for missing public contract, lazy import portability, and
unsupported request/platform behavior, then GREEN results from
`poetry run pytest tests/test_apple_foundation_models.py tests/test_import.py -q`.

### Slice 2

Record fake-backed translation, fresh-session, cancellation, and generation
option tests. Prove no SDK import or session creation occurs for rejected
requests.

### Slice 3

Record normalized text/structured responses, capability metadata, package-owned
errors with preserved causes, and opaque-error classification behavior.

### Slice 4

Record strict Apple alias selection, strict missing-coverage failure, augmented
fallback preservation, and unchanged executor adapter boundaries.

### Slice 5

Record eligible-Mac live text, JSON Schema, and strict workflow results or the
precise prerequisite-based skip reason. Record documentation and import checks.

### Slice 6

Run and record:

```bash
poetry run pytest tests/test_apple_foundation_models.py \
  tests/test_executor.py tests/test_import.py -q
poetry run pytest -q
poetry run ruff check src tests
poetry check
poetry build
pre-commit run --files <changed files>
```

No live Apple test is part of the unit-test command. A1 completion requires the
designated eligible-Mac live command to pass or skip with an actionable reason;
the absence of an eligible Mac does not weaken deterministic unit coverage.
