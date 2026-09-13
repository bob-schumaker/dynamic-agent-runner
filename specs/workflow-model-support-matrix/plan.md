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
adapter, provider, sealed-material, host-capability, session/context, and
tool-pack facts. Run safe synthetic fixtures through it in pytest. Add separate
gated Fastmail and floorplan entry points that consume eligible classified rows
and emit only redacted receipts.

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
synthetic fake-only profiles      authorized Fastmail/floorplan probes
          |                               |
          +---------------+---------------+
                          v
                    redacted receipt
```

The classifier must inspect only declared facts and immutable package/material
identity before selecting an execution route. Synthetic profiles are distinct
from production package evidence. Live evidence is package-digest bound and
cannot be generalized to another model/material closure.

## Initial Profile Catalog

| Profile | Execution mode | Required facts | Evidence boundary |
| --- | --- | --- | --- |
| Fastmail triage | synthetic; separately authorized live read-only | tool use, reviewed read-only surface, exact package lock | no mailbox content or OAuth data |
| Embedding/index | synthetic | matching sealed embedding material and admitted ABI/provider | injected documents/provider only |
| Floorplan SVG | deterministic fixture; separately authorized MPS completion | exact converter, material closure, validator, bounded runner, eligible MPS policy | source fixture and redacted receipt only |
| Structured output after tool use | synthetic | tool use and declared JSON/schema output capability | controlled schemas/results only |
| Stateful context | synthetic | session/context preparation and bounded overflow retry | redacted selection/classification only |
| Tool-pack composition | synthetic | descriptor packing, approval, injected web/workspace/subagent collaborators | no external clients or child processes |

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

WMS1 defines these pure types in one internal classifier module after existing
capability-report types are inspected:

- `WorkflowSupportProfile`: profile ID, workflow family, required adapter, ABI,
  provider, and host facts, material roles/identity, permitted mode,
  authorization class, and canonical digest.
- `WorkflowSupportCell`: profile/adapter/environment identity, one status,
  ordered reason codes, and no execution side effects.
- `WorkflowSupportReceipt`: redacted execution evidence bound to the profile and
  exact package/material descriptors. WMS1 validates the data shape only;
  WMS3 owns rendering and live entry points.

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
| FR-008--FR-010 | profile fixture and no-external-I/O tests | `poetry run pytest tests/test_workflow_model_support_matrix.py -q` |
| All | full regression and lint | `poetry run pytest -q && poetry run ruff check src tests` |

## Risks and Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Provider names become proxy capabilities | false support claims | classify declared capability/material facts only |
| Live probe leaks content | privacy breach | redacted fixed receipt schema; no raw payload persistence |
| Fastmail package evidence is generalized | invalid compatibility claim | bind every receipt to package/material identity |
| A candidate lacks an exact MLX package row | misleading support claim | retain `deferred` rows until that candidate records its own sealed package/material receipt; MLE6's existing row is non-transferable |
| Floorplan evidence overstates portability | invalid model claim | bind profile and receipts to converter/material/validator/MPS facts |
| Synthetic profiles call real collaborators | unintended side effect | install I/O and process blockers in every profile test |

## Rejected Alternatives

- Run every workflow against every adapter unconditionally — invalid because
  adapters and sealed packages do not share capabilities or material formats.
- Extend S1--S6 with Fastmail/MCP — rejected because that suite is deliberately
  harmless and offline.
- Add a live test to every workflow profile — rejected because most profiles
  have deterministic injected seams and no live external behavior to authorize.

## Plan Approval

- Status: WMS1 readiness review complete.
- Notes: implementation remains separately unapproved; WMS1 is ready for that
  approval and must remain a pure classifier plus fake-test slice.
