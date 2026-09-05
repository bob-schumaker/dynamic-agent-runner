# Fastmail Inbox Triage Validation

## Status

Automated implementation checks, including final pre-acceptance validation, and
the authorized local-only T003 probe passed on 2026-09-05. A later non-empty
owner-authorized run exposed that FR-004 was not enforced at the host terminal
boundary; T009 corrects that gap with fake-only regression tests. Any future
acceptance must pass the new host validation. T010 created a strengthened v3
package revision and refreshed its reviewed binding; its live acceptance is
intentionally unrun pending a separate owner instruction. T011 added a narrow
raw-projection normalizer and registered v4; its live acceptance is likewise
unrun pending a separate owner instruction.

## Traceability

| Requirement | Evidence | Status |
| --- | --- | --- |
| FR-001 host current surface | `test_dar_authoring_mcp_tools.py` fake reviewed-surface binding | passed; no live surface |
| FR-002 exact Qwen binding | `test_fastmail_triage_model.py`, `test_local_models.py`; T003 local-only probe | passed; local-only synthetic probe recorded below |
| FR-003 bounded read transaction | `test_executor.py`, `test_dar_authoring_mcp_tools.py` | passed; no Fastmail dispatch |
| FR-004 validated report | `test_fastmail_triage_report.py`, `test_dar_authoring_runner.py` | parser and Fastmail host-boundary regressions passed |
| FR-005 hostile data boundary | T004 adversarial projection tests | passed; fake-only |
| FR-006 no mutation | fake `search_email` surface and one-dispatch counter tests | passed; no live mutation ledger |

## Commands

| Command | Result | Notes |
| --- | --- | --- |
| `poetry run pytest tests/test_local_models.py -q` | passed: 153 | T001-T003 supporting code. |
| Focused Fastmail/MCP tests | passed: 10 | Fake-only binding and report tests. |
| `poetry run pytest -q` | passed: 1754; 1 skipped; 7 deselected | Seven pre-existing unknown-mark warnings. |
| `poetry run ruff check src tests` | passed | Full source and test tree. |
| `pre-commit run --files <changed-files>` | passed | Fastmail implementation, tests, and spec files. |
| `git diff --check` | passed | No whitespace errors. |
| `poetry run pytest tests/test_dar_authoring_runner.py -q -k 'fastmail_terminal_output or rejects_terminal_output'` | passed: 3 | T009 raw-projection rejection and valid-report normalization. |
| `poetry run ruff check src/dynamic_agent_runner/workflow_host/runner.py tests/test_dar_authoring_runner.py` | passed | T009 changed Python files. |
| T010 package finalization | passed | Four-file v3 package digest `a58daadd354ebde4c46900b58ac39c944d69daeca7973a928c5738d0e6e78087`. |
| T010 reviewed binding and registration | passed | Fresh read-only `search_email` review; registered as `fastmail-inbox-triage-qwen-v3`. |
| `poetry run pytest tests/test_dar_authoring_runner.py tests/test_fastmail_triage_report.py -q -k 'fastmail_terminal_output or parse_fastmail_triage_report_rejects'` | passed: 8 | T011 known projection-field normalization and invalid-status rejection. |
| T011 package finalization | passed | Four-file v4 package digest `ce7f3d349745ee113ed6d11584cb58e87bdc896a2b1625babcbc9f7ed46a54ec`. |
| T011 binding and registration | passed | Bound to the current reviewed read-only surface; registered as `fastmail-inbox-triage-qwen-v4`. |

## T009 Post-acceptance report-validation defect

A non-empty owner-authorized run returned syntactically valid JSON but echoed
the bounded raw projection fields instead of supplying a classification and
rationale for each item. The host marked that result completed because its
generic terminal-output check only required a non-empty `message`; the strict
Fastmail parser existed but was not invoked by `WorkflowRunner`.

T009 routes output from the pinned Fastmail llama.cpp adapter through
`parse_fastmail_triage_report` before a run can complete. Invalid reports now
fail closed with a redacted terminal-output error; valid reports are normalized
before return. The regression tests use synthetic references and contain no
mailbox data. No additional Fastmail request was made to validate this fix.

## T010 Qwen non-empty report prompt revision

The failed live run proved that the prior package prompt named only top-level
report keys and supplied only an empty-result example. It did not define the
non-empty item shape or forbid raw projection fields, so the model could echo
the bounded tool projection and be rejected by T009.

The finalized v3 package now requires `message_reference`, `classification`,
and a concise `rationale` for every non-empty item; limits classifications to
the approved enum; directs uncertainty to `needs_review`; and forbids
`sender`, `received_at`, `preview`, attachments, action fields, recipients,
drafts, tool calls, and Markdown. It was finalized against the existing
approved reference-only material set, bound to a fresh reviewed `search_email`
surface, and registered without a second Fastmail dispatch. A new owner-
authorized live run is still required to demonstrate model compliance.

## T011 Raw-projection normalization and status contract

The local synthetic subagent probe showed that Qwen supplied classifications
and rationales but retained the three bounded projection fields and selected
the unsupported status `in_progress`. T011 preserves the parser's allowed
status set and adds a host normalizer that removes only `sender`,
`received_at`, and `preview` before applying the strict report contract.
Unknown item fields, missing triage data, and `in_progress` still fail closed.

The v4 prompt now enumerates `complete`, `needs_review`, and `failed`, with
instructions to use `complete` after a successful search. A fresh
reference-only material receipt finalized the four-file package, which was
bound and registered without another Fastmail dispatch. A new owner-authorized
live run remains required to demonstrate v4 model compliance.

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
| Terminal response | JSON syntax was observed, but this legacy probe did not prove the complete FR-004 report shape; T009 adds host enforcement. |

## T006 Authoring Receipt

The owner-authorized current reviewed surface produced an internal material
receipt and a host-finalized four-file package. The receipt contains only
reference-only specification, plan, and redacted surface-context material.

| Field | Result |
| --- | --- |
| Reviewed snapshot | `v1.4qvjAiNxDWokPx7u9tpBymUTW8DHeWdNn-CfUvwsQU4.UebvTW_9kr5BbKFV4g23pA` |
| Package id | `fastmail-inbox-triage-qwen` |
| File count | 4 |
| Package digest | `45df571d2bdf2e7612a90f1f3cecbb7dfd2e92a311036fd406ae8042423d04b2` |

The corrected package revision was locally qualified, registered with the
pinned direct llama.cpp profile, and bound to the reviewed `search_email`
surface before acceptance.

## T007 Acceptance Receipt

One owner-authorized read-only acceptance run completed with no retained mailbox
content. The terminal report was valid and empty: status `complete`, previous
24-hour window, matched count zero, no truncation, no items, and no warnings.

| Field | Result |
| --- | --- |
| Corrected package digest | `f047fb13f4fa34bf4a02affc1eda2c80d9dcfb370d68b5fb25bc5a59985fce50` |
| Registration digest | `b83d58b7f5c679ced332055d6c8f445f9cda527035655f39e76c77f90d7eaf23` |
| Run status | `completed` |
| Run id | `bb3e1545-f34c-4f89-b83e-87f8d8d7fc88` |
| Mutation ledger | Empty; the package exposes only one read-only capability. |

## Manual Gates

- T007 requires separate explicit authorization. Retain only redacted status,
  digest, dispatch count, configuration fingerprint, and diagnostics.
