# Provider-Backed Context Compaction Validation Record

Status: implemented first slice; documented gates passed 2026-08-23

## Observed Evidence

- `poetry run pytest tests/test_validation.py tests/test_executor.py
  tests/test_capabilities.py tests/test_context_compaction.py -q`: 243 passed.
- `poetry run ruff check src tests`: passed.
- `poetry run pytest -q`: 699 passed, 4 skipped.
- `poetry build`: passed.
- `poetry run make -C docs html`: passed.

The implementation uses only fake caller-owned compaction collaborators in
tests. It supports thresholded pre-turn replacement and the existing single
overflow retry, emits redacted metadata, reports missing/live collaborator
capability state, and deliberately leaves mid-turn/tool-loop compaction and
provider transport binding deferred.

## T0.3 Completion Evidence — 2026-08-27

- RED coverage exposed two overflow-retry gaps: `fallback: basic` did not retry,
  and overflow replacements did not enforce the pre-turn bounded-history and
  protected-boundary invariants.
- GREEN shares replacement validation across pre-turn and overflow retry,
  preserves the active user turn, retries the deterministic fallback once, and
  uses a runtime-generated window ID instead of emitting the provider's ID.
- `poetry run pytest tests/test_validation.py tests/test_executor.py
  tests/test_capabilities.py tests/test_import.py -q`: 264 passed.
- `poetry run pytest -q`: 1264 passed, 1 skipped, 6 deselected. Ruff, package
  build, and docs build passed.

## T0.4 Completion Evidence — 2026-08-27

- Capability preflight now distinguishes disabled, metadata-only, missing
  collaborator, unsupported required capability, and live provider compaction.
  It reports the declared `basic` or `error` fallback without claiming fallback
  has already occurred.
- `poetry run pytest tests/test_validation.py tests/test_executor.py
  tests/test_capabilities.py tests/test_import.py -q`: 270 passed.
- `poetry run pytest -q`: 1270 passed, 1 skipped, 6 deselected. Ruff, package
  build, and docs build passed.

## Required Evidence

- RED tests distinguish absent provider compaction from existing injected and
  deterministic compaction behavior.
- Typed request/result imports and context/direct execution threading work
  without a live provider.
- Validation rejects incomplete provider policy and does not regress current
  compaction policies.
- Pre-turn and overflow retry use only a capable fake collaborator and install
  only valid bounded replacements.
- Missing collaborator/capability, collaborator exception, malformed result,
  and protected-boundary violations either use deterministic basic fallback or
  fail closed according to policy.
- Trace and capability details contain no raw messages, replacement payloads,
  credentials, or provider window identifiers.
- Mid-turn/tool-loop execution remains unchanged and unsupported by this slice.

## Required Commands

```bash
poetry run pytest tests/test_validation.py tests/test_executor.py \
  tests/test_capabilities.py tests/test_import.py -q
poetry run ruff check src tests
poetry run pytest -q
poetry build
poetry run make -C docs html
```
