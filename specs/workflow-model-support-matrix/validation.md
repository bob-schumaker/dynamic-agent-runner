# Workflow Model Support Matrix Validation

Status: WMS1 pure classifier implementation complete; WMS2 profile coverage and
Fastmail/floorplan live receipts remain absent; one package-bound MLE6
competency row is recorded

## Commands Run

| Command | Result | Notes |
| --- | --- | --- |
| Artifact consistency review | pass | Requirements, plan, WMS1 types, and WMS1--WMS4 task dependencies agree. |
| WMS1 readiness review | pass | Closed classifier identity, reason-code, precedence, receipt-binding, and no-side-effect boundaries are specified; Council and Ponytail reviews require no further scope. |
| WMS2 readiness review | pass | WMS2.0 establishes the shared receipt boundary. Every profile has an offline fixture/seam, non-execution proof, and focused validation route; synthetic Fastmail and MLE6 evidence remain distinct from live/mailbox and Darwin competency receipts. |
| WMS2 readiness baseline | pass: 454 | Focused Fastmail, embedding, model-interface, session/overflow, web/workspace/subagent, authorization, and matrix suites passed. |
| WMS2 floorplan fixture baseline | pass: 4 | Passed outside the nested Codex sandbox because the existing deterministic fixture invokes macOS `sandbox-exec`; no MPS or model run occurred. |
| `poetry run pytest tests/test_workflow_model_support_matrix.py -q` | pass: 9 | Canonical Unicode profile digest, all four terminal statuses, all closed blocked reasons, and non-transferable pure receipt binding. |
| `poetry run pytest -q` | pass: 2,502; skipped: 1; deselected: 7 | Full regression after WMS1 implementation. |
| `poetry run ruff check src tests` | pass | Full source and test lint after WMS1 implementation. |
| MLE6 package-bound row | pass | `tests/test_mlx_gte_tiny_mle6_matrix.py` validates exact package/material/descriptor/capability/receipt binding and rejects changed package or material identity. |

## Traceability Matrix

| AC | Requirement | Planned Check | Result |
| --- | --- | --- | --- |
| AC-001 | FR-001, FR-002 | WMS1.1--WMS1.2 classifier tests | pass: missing adapter capability is `not_applicable` before other facts |
| AC-002 | FR-001, FR-002 | WMS1.1--WMS1.2 and WMS2.3 fixture-derived classifier plus injected-provider execution | not run |
| AC-003 | FR-003 | WMS2.1--WMS2.2 synthetic fixture | not run |
| AC-004 | FR-004, FR-005 | WMS3.1--WMS3.2 fake authorization tests; later authorized receipt | not run |
| AC-005 | FR-006 | WMS1.3 binding tests | pass: profile, adapter, material, test-mode, status, and reason changes reject |
| AC-006 | FR-008, FR-009 | WMS2.4 and WMS3.3 floorplan profiles | not run |
| AC-007 | FR-008, FR-010 | WMS2.5 structured-output profile | not run |
| AC-008 | FR-008, FR-010 | WMS2.6 stateful-context profile | not run |
| AC-009 | FR-008, FR-010 | WMS2.7 tool-pack-composition profile | not run |

## Manual Receipt Register

No live Fastmail or floorplan run is authorized or recorded by this artifact
creation. The separate local-only MLE6 Darwin competency receipt is recorded
at `tests/fixtures/mlx-gte-tiny/mle6-package/mle6.5-receipt.json`, and its
static matrix row is package-local at
`tests/fixtures/mlx-gte-tiny/mle6-package/support-matrix-row.json`.
Future receipts must contain only the fields specified by FR-005.

## Residual Risks

- Exact support is host-, adapter-, provider-, and material-lock-dependent.
  The initial profile inventory must be discovered during WMS1.1 rather than
  guessed in this spec.
- Profiles for proposed or intentionally deferred runtime features remain
  excluded until the owning specification records an implemented contract.
