# Workflow Model Support Matrix Tasks

Status: Draft — implementation not approved

## Prerequisites

- Spec: `spec.md`
- Plan: `plan.md`
- Existing inputs: `../model-interface-parity/`, `../fastmail-inbox-triage/`,
  `../workflow-embedding-index-artifacts/`, and model-material/capability
  contracts.

## Task List

- [ ] WMS1.1 [discovery/tests, RED] Inspect the existing capability-report,
      package-lock, and live-matrix types; add focused failing tests for a
      profile/cell classifier without changing existing S1--S6 semantics.
  - Spec: FR-001, FR-002, AC-001, AC-002.
  - Files/components: `src/dynamic_agent_runner/` capability and material
    boundaries; `tests/test_workflow_model_support_matrix.py`.
  - Validation: `poetry run pytest tests/test_workflow_model_support_matrix.py -q`.

- [ ] WMS1.2 [implementation, GREEN] Implement validated declarative support
      profiles and pure cell classification with stable reasons for supported,
      not-applicable, blocked, and deferred states.
  - Spec: FR-001, FR-002, NFR-002, NFR-003.
  - Depends on: WMS1.1.
  - Evidence: fake facts prove no model load, download, provider invocation, or
    tool dispatch occurs during classification.

- [ ] WMS1.3 [tests, RED/GREEN] Add package/material identity binding tests,
      including rejection of a receipt whose profile/package/material digest
      differs from the evaluated cell.
  - Spec: FR-006, AC-005.
  - Files/components: classifier/receipt boundary and
    `tests/test_workflow_model_support_matrix.py`.
  - Depends on: WMS1.2.
  - Validation: `poetry run pytest tests/test_workflow_model_support_matrix.py -q`.

- [ ] WMS2.1 [tests, RED] Define a synthetic Fastmail support profile using
      only de-identified fixture messages and a controlled read-only
      `search_email` handler; demonstrate that the profile cannot touch MCP,
      OAuth, network, or mailbox state.
  - Spec: FR-003, AC-003.
  - Files/components: existing Fastmail test fixtures,
    `tests/test_workflow_model_support_matrix.py`.
  - Depends on: WMS1.2.

- [ ] WMS2.2 [implementation, GREEN] Integrate the synthetic Fastmail fixture
      with eligible adapters through the existing coordinator/host test seams,
      retaining exact dispatch-count and contract-valid report assertions.
  - Spec: FR-003, FR-007.
  - Depends on: WMS2.1.
  - Validation: `poetry run pytest
    tests/test_workflow_model_support_matrix.py
    tests/test_fastmail_triage_report.py -q`.

- [ ] WMS2.3 [tests, RED/GREEN] Define and execute a synthetic sealed embedding
      profile against an injected provider; cover missing ABI, wrong material
      role, and deferred MLX embedding support as classified non-executing rows.
  - Spec: FR-002, FR-003, AC-002.
  - Files/components: existing embedding test seams,
    `tests/test_workflow_model_support_matrix.py`.
  - Depends on: WMS1.3.
  - Validation: `poetry run pytest
    tests/test_workflow_model_support_matrix.py tests/test_embedding_execution.py
    -q`.

- [ ] WMS2.4 [tests, RED/GREEN] Define the floorplan SVG profile from the exact
      sealed converter, model-material, generation-budget, MPS-policy, and
      output-validator facts. Add deterministic non-executing classification
      vectors for every missing or mismatched fact.
  - Spec: FR-008, FR-009, AC-006.
  - Files/components: floorplan fixture/material tests and
    `tests/test_workflow_model_support_matrix.py`.
  - Depends on: WMS1.3.
  - Validation: `poetry run pytest tests/test_floorplan_svg_fixture.py
    tests/test_workflow_model_support_matrix.py -q`.

- [ ] WMS2.5 [tests, RED/GREEN] Add a controlled structured-output-after-tool-
      use profile with schema-valid success and pre-dispatch
      `not_applicable` coverage for adapters without the declared capability.
  - Spec: FR-008, FR-010, AC-007.
  - Files/components: `tests/test_workflow_model_support_matrix.py`, existing
    model-interface matrix fixtures.
  - Depends on: WMS1.2.
  - Validation: `poetry run pytest tests/test_workflow_model_support_matrix.py
    tests/test_model_interface_matrix.py -q`.

- [ ] WMS2.6 [tests, RED/GREEN] Add a stateful-context profile with bounded
      prior turns, session restoration, selected-context assertions, and an
      overflow-retry classification fixture. Prove raw turns are absent from
      the resulting matrix receipt.
  - Spec: FR-008, FR-010, AC-008.
  - Files/components: `tests/test_workflow_model_support_matrix.py`, session
    and context-management test seams.
  - Depends on: WMS1.2.
  - Validation: `poetry run pytest tests/test_workflow_model_support_matrix.py
    -q`.

- [ ] WMS2.7 [tests, RED/GREEN] Add a tool-pack-composition profile using
      injected web, workspace, and subagent collaborators. Prove descriptor
      selection, approval, dispatch, redaction, and external-I/O/process
      blocking without starting a child or external client.
  - Spec: FR-008, FR-010, AC-009.
  - Files/components: `tests/test_workflow_model_support_matrix.py` and
    existing tool-pack tests.
  - Depends on: WMS1.2.
  - Validation: `poetry run pytest tests/test_workflow_model_support_matrix.py
    -q`.

- [ ] WMS3.1 [tests, RED] Add a fake-only authorization and redaction contract
      for a Fastmail live candidate: no authorization, non-supported cell, or
      stale surface rejects before model construction or dispatch.
  - Spec: FR-004, FR-005, AC-004.
  - Files/components: live-matrix runner seam or a new narrow runner,
    `tests/test_workflow_model_support_matrix.py`.
  - Depends on: WMS2.2.

- [ ] WMS3.2 [implementation, GREEN] Add the operator-gated read-only Fastmail
      entry point and fixed redacted receipt renderer. Keep it out of pytest and
      CI; require explicit target/profile plus authorization evidence.
  - Spec: FR-004, FR-005, NFR-001.
  - Depends on: WMS3.1.
  - Validation: `poetry run pytest tests/test_workflow_model_support_matrix.py -q`.

- [ ] WMS3.3 [tests, RED/GREEN + manual gate] Add the operator-gated floorplan
      completion route. It must require a `supported` descriptor-bound MPS cell,
      preserve resource-budget/reap evidence, validate the SVG contract, and
      render only a redacted completion receipt.
  - Spec: FR-005, FR-009, AC-006.
  - Depends on: WMS2.4.
  - Validation: focused fake authorization/receipt tests; a later explicit MPS
    authorization for one exact profile/package/material cell.

- [ ] WMS4.1 [docs/validation] Document the generated support report, all four
      statuses, package non-transferability, and live-run authorization. Add a
      matrix validation record with deterministic results and an empty manual
      receipt section ready for future authorized evidence.
  - Spec: FR-005, FR-007.
  - Files/components: `README.md`, `docs/files/validation-and-testing.rst`,
    `validation.md`.
  - Depends on: WMS3.2.
  - Validation: full regression and doc build command discovered from existing
    documentation workflow.

## Checkpoints

- WMS1: pure, side-effect-free classification and non-transferable evidence.
- WMS2: fully offline Fastmail, embedding, floorplan, structured-output,
  stateful-context, and tool-pack workflow coverage.
- WMS3: human-gated Fastmail and floorplan receipt paths with fake authorization
  coverage.
- WMS4: documented coverage and validation record.

## Validation

- `poetry run pytest tests/test_workflow_model_support_matrix.py -q`
- `poetry run pytest -q`
- `poetry run ruff check src tests`

## Boundary Notes

- Live Fastmail and floorplan work remain per-run human authorization boundaries.
- Package/material locks are authoritative; adapters do not silently substitute
  files or providers.
- Proposed MLX embeddings, locked inference callbacks, sandboxed write/shell,
  runner-owned RAG, and natural-language authoring are excluded until their
  owning feature contracts are implemented.
