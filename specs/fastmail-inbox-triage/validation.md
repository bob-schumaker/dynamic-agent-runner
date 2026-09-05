# Fastmail Inbox Triage Validation

## Status

Prepared; implementation has not started.

## Traceability

| Requirement | Evidence | Status |
| --- | --- | --- |
| FR-001 host current surface | T004 fake reviewed-surface tests | not run |
| FR-002 exact Qwen binding | T001-T003 identity and local-only probe | not run |
| FR-003 bounded read transaction | T001, T001a, T002a, T004 tests | not run |
| FR-004 validated report | T001, T004 terminal-schema tests | not run |
| FR-005 hostile data boundary | T004 adversarial projection tests | not run |
| FR-006 no mutation | T004 tool-surface/dispatch tests | not run |

## Commands

| Command | Result | Notes |
| --- | --- | --- |
| `poetry run pytest tests/test_local_models.py -q` | not run | T001-T003. |
| Focused DAR authoring/MCP tests selected by T004 | not run | Fake only. |
| `poetry run pytest -q` | not run | Required before acceptance. |
| `poetry run ruff check src tests` | not run | Required before acceptance. |
| `pre-commit run --files <changed-files>` | not run | Required before completion. |
| `git diff --check` | not run | Required before completion. |

## Manual Gates

- T003 requires explicit authorization and is local-only: no MCP construction,
  network access, Fastmail credentials, or mailbox data.
- T007 requires separate explicit authorization. Retain only redacted status,
  digest, dispatch count, configuration fingerprint, and diagnostics.
