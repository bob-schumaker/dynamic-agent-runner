# Workflow Model Support Matrix Validation

Status: WMS1--WMS4 is complete; WMS5 Fastmail probe identity repair is open.
Deterministic profile coverage is recorded for
Fastmail, embedding, floorplan, structured output, stateful context, and
tool-pack composition. One floorplan MPS receipt is recorded; Fastmail live
evidence remains absent. Three package-bound MLX embedding competency rows are
recorded.

## Commands Run

| Command | Result | Notes |
| --- | --- | --- |
| WMS5 readiness review | pass | Council and Ponytail reconciled the distinct workflow/package identities, corrected the focused test targets, and separated static inspection from the host's dynamic MCP-surface revalidation. |
| WMS5.1--WMS5.2 focused regression | pass: 24 | `tests/test_fastmail_support_probe_script.py`, `tests/test_fastmail_live_probe.py`, and `tests/test_workflow_model_support_matrix.py` passed; script and focused tests passed Ruff. |
| WMS5.2 owner-local inspection | blocked: `saved package policy does not match` | Read-only inspection of the registered Fastmail workflow refused before host opening, model loading, MCP access, or mailbox dispatch. WMS5.4 owns exact package/revision/binding reconciliation. |
| WMS1 readiness review | pass | Closed classifier identity, reason-code, precedence, receipt-binding, and no-side-effect boundaries are specified; Council and Ponytail reviews require no further scope. |
| WMS2 readiness review | pass | WMS2.0 establishes the shared receipt boundary. Every profile has an offline fixture/seam, non-execution proof, and focused validation route; synthetic Fastmail and MLE6 evidence remain distinct from live/mailbox and Darwin competency receipts. |
| WMS2 readiness baseline | pass: 454 | Focused Fastmail, embedding, model-interface, session/overflow, web/workspace/subagent, authorization, and matrix suites passed. |
| WMS2 floorplan fixture baseline | pass: 4 | Passed outside the nested Codex sandbox because the existing deterministic fixture invokes macOS `sandbox-exec`; no MPS or model run occurred. |
| `poetry run pytest tests/test_workflow_model_support_matrix.py -q` | pass: 9 | Canonical Unicode profile digest, all four terminal statuses, all closed blocked reasons, and non-transferable pure receipt binding. |
| `poetry run pytest -q` | pass: 2,502; skipped: 1; deselected: 7 | Full regression after WMS1 implementation. |
| `poetry run ruff check src tests` | pass | Full source and test lint after WMS1 implementation. |
| MLE6 package-bound row | pass | `tests/test_mlx_gte_tiny_mle6_matrix.py` validates exact package/material/descriptor/capability/receipt binding and rejects changed package or material identity. |
| MLE7 package-bound row | pass | `tests/test_mlx_multilingual_e5_small_mle7_matrix.py` validates exact package/material/descriptor/capability/receipt binding and rejects changed package or material identity. |
| MLE8 package-bound row | pass | `tests/test_mlx_all_distilroberta_v1_mle8_matrix.py` validates exact package/material/descriptor/capability/receipt binding and rejects changed package or material identity. |
| WMS3.3 floorplan MPS completion | pass | Explicitly authorized one-image MPS run completed one dispatch; JSON admission, SVG rendering/validation, bounded resource scalars, and confirmed worker reap are recorded in the closed receipt below. |
| WMS3.3 focused regression | pass: 170 | `tests/test_workflow_model_support_matrix.py`, floorplan fixture/probe/script, generation worker, Transformers adapter, authoring profiles, and local preparation tests passed; `poetry run ruff check src tests scripts` passed. |
| WMS4 focused profile regression | pass: 483 | The task-mapped Fastmail, embedding, floorplan, structured-output, stateful-context, tool-pack, matrix, and authorization suites passed with controlled collaborators only. |
| WMS4 full regression | pass: 2,603; skipped: 1; deselected: 7 | Ran outside the nested sandbox because the deterministic floorplan fixture invokes macOS `sandbox-exec` and Darwin MPS controller tests require host MPS capability. |
| WMS4 lint and docs build | pass | `poetry run ruff check src tests` and `make -C docs html` passed; changed-file pre-commit and `git diff --check` passed. |

## Traceability Matrix

| AC | Requirement | Planned Check | Result |
| --- | --- | --- | --- |
| AC-001 | FR-001, FR-002 | WMS1.1--WMS1.2 classifier tests | pass: missing adapter capability is `not_applicable` before other facts |
| AC-002 | FR-001, FR-002 | WMS1.1--WMS1.2 and WMS2.3 fixture-derived classifier plus injected-provider execution | pass: controlled MLE6 provider dispatches once for the exact sealed synthetic cell; missing ABI/material and different package rows are zero-dispatch. |
| AC-003 | FR-003 | WMS2.1--WMS2.2 synthetic fixture | pass: controlled de-identified Fastmail fixture produces the bounded triage report through exactly one read-only dispatch with no MCP, OAuth, network, or mailbox access. |
| AC-004 | FR-004, FR-005 | WMS3.1--WMS3.2 fake authorization tests; later authorized receipt | pass (offline route): missing authorization, unavailable support, and stale identity refuse before opening or dispatch; admitted fake evidence is redacted. No live Fastmail receipt is recorded. |
| AC-005 | FR-006 | WMS1.3 binding tests | pass: profile, adapter, material, test-mode, status, and reason changes reject |
| AC-006 | FR-008, FR-009 | WMS2.4 and WMS3.3 floorplan profiles | pass: explicit MPS gate completed one exact descriptor/material/profile cell; model JSON was admitted, SVG rendered/validated, and the worker reap was confirmed before the redacted receipt. |
| AC-007 | FR-008, FR-010 | WMS2.5 structured-output profile | pass: one controlled tool dispatch yields the declared schema-valid terminal JSON; a missing capability is `not_applicable` before dispatch. |
| AC-008 | FR-008, FR-010 | WMS2.6 stateful-context profile | pass: controlled session restoration and overflow retry retain selected-context and terminal classification facts without raw turns. |
| AC-009 | FR-008, FR-010 | WMS2.7 tool-pack-composition profile | pass: injected web, workspace, and subagent collaborators prove packing, approval, invocation, and redaction without an external client or child process. |

## Manual Receipt Register

One explicitly authorized live floorplan MPS run is recorded: profile
`floorplan-svg-mps-completion-v1`, adapter `transformers-peft-adapter-v1`,
status `supported`, one dispatch, 2,223 packed-context tokens, 1,282 generated
tokens, 3,057 output bytes, and confirmed worker reap. The receipt binds
profile `184d33c4b0a320a2bb7022b1ca80a1b86daa3203ea39d8afe75ebf3407e5e093`,
descriptor `a986d842bb8d555ad6b5cfbe774a25a26db9eca34cd046d43a5158f9234526cb`,
material lock `79edaed8648cffb71972d0c8fcb3d18f100457d9cf46f0b58bc26fd16cc69cb8`,
and authorization reference
`4519c2c2574ae800049fc79335a672f43c00803ee94884a0f0c83227ca7c9f07`.
It contains no image/prompt/model JSON/SVG bytes, paths, process IDs, or worker
handles. No live Fastmail run is recorded. The separate local-only MLE6, MLE7,
and MLE8 Darwin competency receipts are recorded respectively at
`tests/fixtures/mlx-gte-tiny/mle6-package/mle6.5-receipt.json` and
`tests/fixtures/mlx-multilingual-e5-small/mle7-package/mle7.7-receipt.json`,
and `tests/fixtures/mlx-all-distilroberta-v1/mle8-package/mle8.7-receipt.json`.
Their static matrix rows are package-local beside each receipt. The MLE8 receipt
records three 768-dimensional vectors with `7.674098014831543e-07` maximum
absolute error against its locked fixture (threshold `0.005`). Future receipts
must contain only the fields specified by FR-005.

## Residual Risks

- Exact support is host-, adapter-, provider-, and material-lock-dependent.
  The initial profile inventory must be discovered during WMS1.1 rather than
  guessed in this spec.
- Profiles for proposed or intentionally deferred runtime features remain
  excluded until the owning specification records an implemented contract.
- The Fastmail live route has no receipt because its current command requires a
  single value to be both the registration key and sealed package ID. The
  verified owner-local registration uses distinct values; WMS5 must derive
  static identity through inspection and retain host revalidation of the dynamic
  MCP surface before a new explicitly authorized live attempt.
- The owner-local Fastmail registration currently fails static policy
  verification. WMS5.4 must reconcile that same sealed package/revision and
  reviewed binding before a fresh authorization can permit WMS5.3.
