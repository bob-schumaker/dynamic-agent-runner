# Workflow Model Support Matrix Tasks

Status: WMS1 pure classifier implementation complete; WMS2 profile coverage
remains unimplemented

## Prerequisites

- Spec: `spec.md`
- Plan: `plan.md`
- Existing inputs: `../model-interface-parity/`, `../fastmail-inbox-triage/`,
  `../workflow-embedding-index-artifacts/`, and model-material/capability
  contracts.

## Task List

- [x] WMS1.1 [discovery/tests, RED] Inspect the existing capability-report,
      package-lock, and live-matrix types; add focused failing tests for a
      profile/cell classifier without changing existing S1--S6 semantics.
  - Spec: FR-001, FR-002, AC-001, AC-002, WMS1 Classifier Contract.
  - Files/components: `src/dynamic_agent_runner/` capability and material
    boundaries; `tests/test_workflow_model_support_matrix.py`.
  - Validation: `poetry run pytest tests/test_workflow_model_support_matrix.py -q`.
  - Evidence: the new focused suite fails at collection before implementation;
    it fixes the canonical profile/material facts and all four status outcomes
    without importing an adapter, provider, or runtime.

- [x] WMS1.2 [implementation, GREEN] Implement validated declarative support
      profiles and pure cell classification with stable reasons for supported,
      not-applicable, blocked, and deferred states.
  - Spec: FR-001, FR-002, NFR-002, NFR-003, WMS1 Classifier Contract.
  - Depends on: WMS1.1.
  - Evidence: fake facts prove no model load, download, provider invocation, or
    tool dispatch occurs during classification.
  - Boundary: one internal classifier module and its tests only; do not add a
    runner, script, live entry point, or broad public export in WMS1.
  - Evidence: `workflow_support_matrix.py` accepts only immutable profile and
    candidate facts, canonicalizes profile digests, and produces the closed
    terminal status/reason set without importing a runtime collaborator.

- [x] WMS1.3 [tests, RED/GREEN] Add package/material identity binding tests,
      including rejection of a receipt whose profile/package/material digest
      differs from the evaluated cell.
  - Spec: FR-006, AC-005, WMS1 Classifier Contract.
  - Files/components: classifier/receipt boundary and
    `tests/test_workflow_model_support_matrix.py`.
  - Depends on: WMS1.2.
  - Validation: `poetry run pytest tests/test_workflow_model_support_matrix.py -q`.
  - Evidence: focused receipt-transfer tests were RED before the receipt data
    contract and pure evaluator existed, then GREEN with exact profile, adapter,
    material, test-mode, status, and reason binding checks.

- [x] WMS2.0 [tests, RED/GREEN] Extend the pure receipt contract for every
      deterministic WMS2 result before adding profile-specific execution.
  - Spec: FR-005, NFR-001, NFR-003.
  - Files/components: `workflow_support_matrix.py`,
    `tests/test_workflow_model_support_matrix.py`.
  - Depends on: WMS1.3.
  - RED: require a non-negative `dispatch_count` and retain only stable
    classification reasons as bounded diagnostics. A non-supported classified
    cell cannot record a nonzero dispatch count; profile tests must be able to
    prove one exact synthetic dispatch or zero dispatch before execution.
  - GREEN: retain no model input/output, tool result, mailbox content, prompt,
    credential, path, or host detail in the receipt representation. Update the
    existing pure receipt-binding vectors rather than adding a renderer or a
    second receipt type.
  - Validation: `poetry run pytest tests/test_workflow_model_support_matrix.py -q`.

- [x] WMS2.1 [tests, RED] Define a synthetic Fastmail support profile using
      only de-identified fixture messages and a controlled read-only
      `search_email` handler; demonstrate that the profile cannot touch MCP,
      OAuth, network, or mailbox state.
  - Spec: FR-003, AC-003.
  - Files/components: de-identified Fastmail shape fixture and current
    Fastmail binding/terminal-report seams,
    `tests/test_dar_authoring_mcp_tools.py`,
    `tests/test_dar_authoring_runner.py`, and
    `tests/test_workflow_model_support_matrix.py`.
  - Depends on: WMS2.0.
  - RED: add one test-owned, de-secreted identity fixture for the registered
    v4 package digest, pinned Qwen artifact hash/configuration fingerprint, and
    reviewed read-only surface digest. Derive the profile material identity
    from that fixture; do not treat prose-only historical acceptance evidence
    as a reusable material lock.
  - RED: define `fastmail-triage-synthetic-v1` as synthetic-only, requiring
    tool use plus the exact read-only `search_email` surface. A missing tool
    path is `not_applicable`; stale or mismatched package/surface identity is a
    zero-dispatch blocked row.
  - Boundary: install fail-on-call MCP/OAuth/network sentries. The fixture
    handler accepts only `{}`, returns de-identified bounded data, and the
    classifier runs before any fake model or tool construction.

- [x] WMS2.2 [implementation, GREEN] Integrate the synthetic Fastmail fixture
      with eligible adapters through the existing coordinator/host test seams,
      retaining exact dispatch-count and contract-valid report assertions.
  - Spec: FR-003, FR-007.
  - Depends on: WMS2.1.
  - GREEN: reuse the existing fake Fastmail binding and deterministic adapter
    path to require exactly one `search_email({})` dispatch, zero mutation,
    and a terminal `FastmailTriageReport`-valid result. Record a synthetic
    receipt with `dispatch_count == 1`; stale, unsupported, and denied rows
    remain zero-dispatch.
  - Validation: `poetry run pytest
    tests/test_workflow_model_support_matrix.py
    tests/test_dar_authoring_mcp_tools.py
    tests/test_dar_authoring_runner.py
    tests/test_fastmail_triage_report.py -q`.

- [x] WMS2.3 [tests, RED/GREEN] Define and execute the distinct synthetic
      `embedding-index-synthetic-mle6-v1` sealed-embedding profile against an
      injected provider; cover missing ABI, wrong material role, and an
      unonboarded embedding package as classified non-executing rows.
  - Spec: FR-002, FR-003, AC-002.
  - Files/components: existing MLE6 package and fake embedding/index test
    seam, `tests/test_workflow_model_support_matrix.py`,
    `tests/test_mlx_gte_tiny_mle6_execution.py`, and the pure receipt boundary.
  - Depends on: WMS2.0.
  - RED: parse the existing sealed MLE6 package lock, execution descriptor,
    and capability requirements from test fixtures; derive the profile's exact
    package ID, material-lock digest, `tokenizer`/`weights` roles,
    execution-descriptor digest, `embedding.execute.v1` capability identity,
    and ABI identity. Do not duplicate those identities as literals. The
    synthetic profile has no host/MPS requirement and is distinct from the
    package's `embedding-index-sealed-v1` Darwin competency row.
  - RED: use the WMS2.0 pure receipt contract for a supported synthetic result
    with one dispatch and each non-executing row with zero dispatches.
  - GREEN: run exactly one bounded synthetic input through the existing
    `EmbeddingExecutionService` using its injected deterministic fake provider
    and the binding derived from that same lock, descriptor, and capability
    requirement. Assert the supported profile/candidate cell, one provider
    dispatch, and no model import, model download, network, mailbox, OAuth,
    or MPS access.
  - GREEN: use the same profile for three zero-dispatch rows: an absent exact
    ABI capability is `blocked/required_abi_unavailable`; an otherwise matching
    identity missing `tokenizer` is `blocked/required_material_missing`; and a
    different package identity is `blocked/material_identity_mismatch`. These
    rows must not call the injected provider and cannot inherit the package's
    Darwin competency receipt or supported row.
  - Review disposition (2026-09-13): Council required the distinct synthetic
    profile identity, fixture-derived facts, explicit dispatch receipts, and
    the sealed MLE6 execution test in the validation command. Ponytail accepted
    reuse of the existing fake provider and package fixture; no new runtime
    registry, provider adapter, model fixture, or dependency is warranted.
  - Validation: `poetry run pytest
    tests/test_workflow_model_support_matrix.py
    tests/test_mlx_gte_tiny_mle6_execution.py
    tests/test_embedding_execution.py
    -q`.

- [x] WMS2.4 [tests, RED/GREEN] Define the floorplan SVG profile from the exact
      sealed converter, model-material, generation-budget, MPS-policy, and
      output-validator facts. Add deterministic non-executing classification
      vectors for every missing or mismatched fact.
  - Spec: FR-008, FR-009, AC-006.
  - Files/components: floorplan fixture/material tests and
    `tests/test_workflow_model_support_matrix.py`.
  - Depends on: WMS2.0.
  - RED: derive a synthetic fixture profile and a separate
    `floorplan-svg-mps-completion-v1` live profile from the sealed floorplan
    package. Bind package/material lock, execution descriptor, converter asset,
    generation budget (through the descriptor), and terminal SVG validator
    digests. The synthetic profile has no MPS requirement; the live profile
    requires the declared MPS host policy and authorization, but does not run
    MPS in pytest.
  - GREEN: run the existing admitted JSON-to-SVG converter/validator fixture
    only after the synthetic cell is supported. Cover zero-execution rows for
    absent/mismatched material, converter, descriptor/budget, validator,
    runner, MPS policy, and authorization facts. The MPS completion row and its
    receipt remain WMS3.3 work.
  - Execution note: the existing fixture invokes macOS `sandbox-exec`; when
    nested sandbox policy rejects it, run this focused deterministic test
    outside the Codex sandbox. That is neither an MPS probe nor authorization
    for a model run.
  - Validation: `poetry run pytest tests/test_floorplan_svg_fixture.py
    tests/test_workflow_model_support_matrix.py -q`.

- [x] WMS2.5 [tests, RED/GREEN] Add a controlled structured-output-after-tool-
      use profile with schema-valid success and pre-dispatch
      `not_applicable` coverage for adapters without the declared capability.
  - Spec: FR-008, FR-010, AC-007.
  - Files/components: `tests/test_workflow_model_support_matrix.py`, existing
    model-interface matrix fixtures.
  - Depends on: WMS2.0.
  - RED: build one controlled two-turn fixture—not a pairing of unrelated S3
    and S5 tests—in which the adapter performs the declared harmless tool call
    and then returns a locally validated fixed JSON result schema. A missing
    `structured_output` adapter capability is `not_applicable` before adapter
    construction or tool dispatch.
  - GREEN: assert the exact tool dispatch sequence, schema-valid terminal JSON,
    one dispatch receipt, and no remote model/client access. Reuse the existing
    in-memory registry and deterministic adapter recorder; do not add a schema
    subsystem or provider special case.
  - Validation: `poetry run pytest tests/test_workflow_model_support_matrix.py
    tests/test_model_interface_matrix.py -q`.

- [x] WMS2.6 [tests, RED/GREEN] Add a stateful-context profile with bounded
      prior turns, session restoration, selected-context assertions, and an
      overflow-retry classification fixture. Prove raw turns are absent from
      the resulting matrix receipt.
  - Spec: FR-008, FR-010, AC-008.
  - Files/components: `tests/test_workflow_model_support_matrix.py`, session
    and context-management test seams.
  - Depends on: WMS2.0.
  - RED: bind one profile to the existing fake session restoration and one-shot
    overflow-retry/compaction seam. Require the selected-context counts and
    retry terminal classification, rather than raw turns or provider payloads.
  - GREEN: prove the receipt stores only profile/cell facts, stable reason
    codes, and dispatch count; sentinel turns, summaries, and provider-window
    identifiers must be absent from its representation. No external model or
    compactor is allowed.
  - Validation: `poetry run pytest tests/test_workflow_model_support_matrix.py
    tests/test_agent_sessions.py tests/test_executor.py -q`.

- [ ] WMS2.7 [tests, RED/GREEN] Add a tool-pack-composition profile using
      injected web, workspace, and subagent collaborators. Prove descriptor
      selection, approval, dispatch, redaction, and external-I/O/process
      blocking without starting a child or external client.
  - Spec: FR-008, FR-010, AC-009.
  - Files/components: `tests/test_workflow_model_support_matrix.py` and
    existing web, workspace, subagent, and authorization test seams.
  - Depends on: WMS2.0.
  - RED: make one integrated controlled profile with injected fake web clients,
    workspace store, and subagent runner. It must exercise descriptor selection
    and approval before dispatch; existing isolated tool-pack unit tests alone
    are not matrix evidence.
  - GREEN: assert the exact selected descriptors, approval decision, bounded
    result shaping/redaction, and one dispatch count for each admitted
    collaborator. Install fail-on-call external-client and child-process
    sentries; the fake subagent runner is the only permitted collaborator.
  - Validation: `poetry run pytest tests/test_workflow_model_support_matrix.py
    tests/test_registry.py tests/test_subagents.py
    tests/test_dar_authoring_authorized_tools.py -q`.

## WMS2 Readiness Review (2026-09-13)

- Council: the architecture triad (Aristotle, Ada, Feynman), run as a
  reduced-independence sequential review, required a shared execution-receipt
  prerequisite; fixture-derived identities; separate synthetic, live, and
  Darwin/MPS evidence; and integrated tests where the workflow contract crosses
  existing unit-test seams.

- Ponytail: reuse the existing fake Fastmail binding, MLE6 package execution,
  floorplan fixture, in-memory tool registry, fake session/compaction adapter,
  and fake web/workspace/subagent collaborators. Do not add a profile registry,
  model fixture, adapter, provider, schema framework, or new dependency.

- Verdict: WMS2.0--WMS2.7 are implementation-ready in dependency order. The
  only host-specific test condition is the existing floorplan fixture's nested
  `sandbox-exec` limitation recorded above.

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
- One exact MLX package row is recorded by MLE6 evidence; generic MLX row
  classification remains WMS2.3 work. Sandboxed write/shell and runner-owned
  RAG remain excluded until
  their owning feature contracts are implemented.
