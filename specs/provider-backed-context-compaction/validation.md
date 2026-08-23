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
