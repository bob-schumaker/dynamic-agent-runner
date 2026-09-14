# Workflow Model Support Matrix Implementation Plan

Status: Implemented through WMS4; WMS5 Fastmail probe identity repair is open

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
| FR-003 | fake-only Fastmail and embedding fixture tests | `poetry run pytest tests/test_workflow_model_support_matrix.py tests/test_dar_authoring_mcp_tools.py tests/test_dar_authoring_runner.py tests/test_fastmail_triage_report.py tests/test_mlx_gte_tiny_mle6_execution.py tests/test_embedding_execution.py -q` |
| FR-004/FR-005 | authorization and redacted-receipt tests with fakes | `poetry run pytest tests/test_workflow_model_support_matrix.py -q` |
| FR-006/FR-007 | binding/non-transferability and regression tests | `poetry run pytest tests/test_workflow_model_support_matrix.py tests/test_model_interface_matrix.py -q` |
| FR-008--FR-010 | profile fixture and no-external-I/O tests | `poetry run pytest tests/test_workflow_model_support_matrix.py tests/test_floorplan_svg_fixture.py tests/test_model_interface_matrix.py tests/test_agent_sessions.py tests/test_executor.py tests/test_registry.py tests/test_subagents.py tests/test_dar_authoring_authorized_tools.py -q` |
| All | full regression and lint | `poetry run pytest -q && poetry run ruff check src tests` |

## Risks and Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Provider names become proxy capabilities | false support claims | classify declared capability/material facts only |
| Live probe leaks content | privacy breach | redacted fixed receipt schema; no raw payload persistence |
| Fastmail package evidence is generalized | invalid compatibility claim | bind every receipt to package/material identity |
| A candidate lacks an exact MLX package row | misleading support claim | retain `deferred` rows until that candidate records its own sealed package/material receipt; the MLE6, MLE7, and MLE8 rows are each non-transferable |
| Floorplan evidence overstates portability | invalid model claim | bind profile and receipts to converter/material/validator/MPS facts |
| Synthetic profiles call real collaborators | unintended side effect | install I/O and process blockers in every profile test |
| A floorplan completion receipt overclaims worker cleanup | false live evidence | expose one generic scalar `worker_reaped` attestation after controller-confirmed cleanup; project it without worker internals |
| Fastmail registration and package identities differ | live probe cannot admit the real host state | accept a workflow ID only; inspect the registered immutable state and derive package/material/support facts before host opening |

## WMS3.3 Floorplan Completion Slice

Implement one narrow `floorplan_mps_completion_probe` boundary and one
operator-gated script. Reuse the support classifier, generic MPS worker
controller, registered package revision, compiled policy, and existing sealed
workflow-local JSON-admission/render/SVG-validator chain. Do not share the
Fastmail profile parser, accept operator-supplied support facts, add a probe
registry, or add a floorplan-named host configuration path.

The probe derives its profile and all sealed identity facts from the registered
revision/policy, classifies before host opening/worker construction, runs exactly
one sealed image only after explicit authorization, and renders the fixed
redacted receipt defined by the spec. Extend the generic worker result with the
minimum scalar cleanup attestation needed to preserve controller-confirmed reap
evidence; do not expose child handles, PIDs, or runtime internals.

## Rejected Alternatives

- Run every workflow against every adapter unconditionally — invalid because
  adapters and sealed packages do not share capabilities or material formats.
- Extend S1--S6 with Fastmail/MCP — rejected because that suite is deliberately
  harmless and offline.
- Add a live test to every workflow profile — rejected because most profiles
  have deterministic injected seams and no live external behavior to authorize.

## WMS5 Fastmail Probe Identity Repair

Repair the narrow operator probe only. Replace its ambiguous `--package-name`
input with `--workflow-id`, resolve that key through
`inspect_saved_workflow`, and derive the profile, registered package ID,
revision, material identity, and reviewed surface facts from the immutable
registered state. Remove `--support-facts`; it can only self-consistently echo
operator input and cannot establish admission.

The focused tests must first reproduce the actual supported shape: workflow ID
`fastmail-inbox-triage-qwen-v4` resolves to sealed package ID
`fastmail-inbox-triage-qwen`. They must prove that a missing workflow, an
inconsistent derived registration/policy, or a stale reviewed surface refuses
before host opening and dispatch. The route retains explicit opt-in, target,
and authorization-reference inputs; it records their digests only. Do not
record the owner-local state root, target, credentials, mailbox content, or
Codex session transcript in repository artifacts.

## Plan Approval

- Status: WMS1--WMS4 complete; WMS5.1--WMS5.3 remain open.
- Notes: One shared redacted execution-receipt extension supports six separate
  fully offline profiles. Synthetic Fastmail evidence cannot inherit a live
  mailbox receipt, and the three package-bound MLE6, MLE7, and MLE8 Darwin/MLX
  competency rows cannot transfer to a different package or material closure.
  WMS3.3 records one authorized floorplan MPS receipt; Fastmail live evidence
  remains absent because the current Fastmail command conflates the registered
  workflow key with the sealed package ID. The architecture-triad review
  required integrated workflow
  tests where existing unit seams are disjoint; Ponytail retained only those
  existing fakes and introduced no registry or provider abstraction.
