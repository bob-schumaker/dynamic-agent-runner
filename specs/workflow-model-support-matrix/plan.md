# Workflow Model Support Matrix Implementation Plan

Status: Draft

## Spec Trace

- Spec: `spec.md`
- Discovery: `discovery.md`
- Related contracts: `../model-interface-parity/spec.md`,
  `../fastmail-inbox-triage/spec.md`, and
  `../workflow-embedding-index-artifacts/spec.md`

## Technical Summary

Add a package-owned declarative profile and classifier layer over existing
adapter, provider, sealed-material, and host-capability facts. Run safe
synthetic fixtures through it in pytest. Add a separately gated live Fastmail
entry point that consumes an eligible classified row and emits only a redacted
receipt.

## Architecture and Data Flow

```text
workflow profile + package/material lock + adapter/provider facts + host facts
                                  |
                                  v
                         support-cell classifier
                         |        |          |
                         v        v          v
                    supported  blocked  not_applicable/deferred
                         |
          +--------------+----------------+
          |                               |
          v                               v
synthetic fake-only fixture       authorized live Fastmail probe
          |                               |
          +---------------+---------------+
                          v
                    redacted receipt
```

The classifier must inspect only declared facts and immutable package/material
identity before selecting an execution route. Synthetic profiles are distinct
from production Fastmail package evidence. Live evidence is package-digest
bound and cannot be generalized to another model/material closure.

## Affected Areas

- `src/dynamic_agent_runner/` — new generic support-profile, classification,
  and receipt types plus a narrow runner entry point where existing patterns
  place it.
- `tests/` — fake profile/classifier, sealed-material mismatch, fixture, and
  redaction coverage.
- `scripts/` — operator-gated receipt runner, if the existing live-matrix
  command cannot safely host workflow-level profiles.
- `README.md`, `docs/files/validation-and-testing.rst` — supported test modes
  and explicit non-portability semantics.

## Contracts

The implementation will define, after existing capability-report types are
inspected:

- `WorkflowSupportProfile`: profile ID, workflow family, required capability
  facts, material roles/identity, permitted mode, and authorization class.
- `WorkflowSupportCell`: profile/adapter/environment identity, one status,
  ordered reason codes, and no execution side effects.
- `WorkflowSupportReceipt`: redacted execution evidence bound to the profile and
  exact package/material descriptors.

Status meaning:

| Status | Meaning | May execute? |
| --- | --- | --- |
| `supported` | All declared requirements are present and the profile is eligible. | Synthetic: yes; live: only after authorization. |
| `not_applicable` | The adapter intentionally cannot meet a workflow requirement. | No. |
| `blocked` | A required local fact, reviewed surface, host capability, provider, or material is unavailable. | No. |
| `deferred` | A required implementation/profile is not delivered yet. | No. |

## Verification Strategy

| Requirement | Test/Check | Command |
| --- | --- | --- |
| FR-001/FR-002 | profile validation and pure classification tests | `poetry run pytest tests/test_workflow_model_support_matrix.py -q` |
| FR-003 | fake-only Fastmail and embedding fixture tests | `poetry run pytest tests/test_workflow_model_support_matrix.py tests/test_fastmail_triage_report.py tests/test_embedding_execution.py -q` |
| FR-004/FR-005 | authorization and redacted-receipt tests with fakes | `poetry run pytest tests/test_workflow_model_support_matrix.py -q` |
| FR-006/FR-007 | binding/non-transferability and regression tests | `poetry run pytest tests/test_workflow_model_support_matrix.py tests/test_model_interface_matrix.py -q` |
| All | full regression and lint | `poetry run pytest -q && poetry run ruff check src tests` |

## Risks and Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Provider names become proxy capabilities | false support claims | classify declared capability/material facts only |
| Live probe leaks content | privacy breach | redacted fixed receipt schema; no raw payload persistence |
| Fastmail package evidence is generalized | invalid compatibility claim | bind every receipt to package/material identity |
| MLX embedding is unfinished | misleading failure | retain `deferred` profile rows until its ABI path is implemented |

## Rejected Alternatives

- Run every workflow against every adapter unconditionally — invalid because
  adapters and sealed packages do not share capabilities or material formats.
- Extend S1--S6 with Fastmail/MCP — rejected because that suite is deliberately
  harmless and offline.

## Plan Approval

- Status: skipped by user direction for artifact authoring only.
- Notes: implementation remains separately unapproved.
