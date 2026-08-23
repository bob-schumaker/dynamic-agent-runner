# Provider-Backed Context Compaction Validation Record

Status: implementation-ready; no runtime validation has run

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
