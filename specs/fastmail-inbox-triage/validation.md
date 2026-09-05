# Fastmail Inbox Triage Validation

## Status

Automated implementation checks, including final pre-acceptance validation, and
the authorized local-only T003 probe passed on 2026-09-05. T007 remains an
unrun manual gate that requires separate explicit authorization.

## Traceability

| Requirement | Evidence | Status |
| --- | --- | --- |
| FR-001 host current surface | `test_dar_authoring_mcp_tools.py` fake reviewed-surface binding | passed; no live surface |
| FR-002 exact Qwen binding | `test_fastmail_triage_model.py`, `test_local_models.py`; T003 local-only probe | passed; local-only synthetic probe recorded below |
| FR-003 bounded read transaction | `test_executor.py`, `test_dar_authoring_mcp_tools.py` | passed; no Fastmail dispatch |
| FR-004 validated report | `test_fastmail_triage_report.py` | passed |
| FR-005 hostile data boundary | T004 adversarial projection tests | passed; fake-only |
| FR-006 no mutation | fake `search_email` surface and one-dispatch counter tests | passed; no live mutation ledger |

## Commands

| Command | Result | Notes |
| --- | --- | --- |
| `poetry run pytest tests/test_local_models.py -q` | passed: 153 | T001-T003 supporting code. |
| Focused Fastmail/MCP tests | passed: 10 | Fake-only binding and report tests. |
| `poetry run pytest -q` | passed: 1752; 1 skipped; 7 deselected | Seven pre-existing unknown-mark warnings. |
| `poetry run ruff check src tests` | passed | Full source and test tree. |
| `pre-commit run --files <changed-files>` | passed | Fastmail implementation, tests, and spec files. |
| `git diff --check` | passed | No whitespace errors. |

## T003 Local-only Probe Receipt

The probe used the pinned local GGUF with `allow_network=False`, synthetic
messages, and a synthetic empty `search_email` result. It did not construct an
MCP client or access Fastmail, credentials, or mailbox data.

| Field | Result |
| --- | --- |
| Artifact SHA-256 | `626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d` |
| Configuration fingerprint | `8f5619a7dd6215ced444ecc4966b849f453e7ba89376e046c4a08c4f0de34bcb` |
| Initial tool calls | 1 (`search_email({})`, schema-valid) |
| Continuation tool calls | 0 |
| Terminal response | Valid JSON (`{"status":"complete"}`); 21 bytes |

## Manual Gates

- T007 requires separate explicit authorization. Retain only redacted status,
  digest, dispatch count, configuration fingerprint, and diagnostics.
