<!-- rumdl-disable MD013 -->

# Reviewed Vector-Index Host Extension Tasks

Status: Complete

## Prerequisites

- Spec: `spec.md`
- Plan: `plan.md`
- Data model: none; the reviewed template, sealed job, reservation, staged
  artifact, and receipt shapes are contract work owned by `spec.md`.
- Contracts: none beyond the host-template contract in `spec.md`.

## Cited Inputs

- `specs/reviewed-vector-index-host-extension/spec.md` — Normative reviewed
  host-extension contract and verification requirements — inspected.
- `specs/reviewed-vector-index-host-extension/plan.md` — Approved delivery
  order, current-state anchors, and implementation boundaries — inspected.
- `specs/workflow-capability-requirements/` — Existing exact-contract and
  descriptor/admission precedent — inspected where task planning needs a
  compatibility boundary.
- `specs/workflow-embedding-index-artifacts/` — Existing concrete index
  artifact precedent; regression-only input, not a generic primitive —
  inspected.

## Task List

- [x] T001 [discovery] Inventory the exact implementation and test seams named
  by the plan before writing a test.
  - Spec: FR-1 through FR-6; Required Verification.
  - Plan: Current-State Anchors; Delivery Rules.
  - Files/components: `src/dynamic_agent_runner/workflow_host/capabilities.py`,
    `reviewed_tool_packages.py`, `workflow_authoring_registration.py`,
    `policy.py`, `authorized_tools.py`, `action_ledger.py`,
    `sealed_artifact_preparation.py`, `sealed_artifact_runner.py`,
    `embedding_index_artifacts.py`, `embedding_sealed_artifact_callback.py`,
    `host.py`, and their focused tests.
  - Depends on: none.
  - Validation: `codegraph explore` for each named owner and its callers;
    record the exact focused test modules and every pre-dispatch side-effect
    boundary in this task before T002.
  - Evidence: a route table in this file that assigns each S1–S5 test matrix
    to one test module and one source owner; it identifies no new coordinator,
    plugin manager, index runtime, or model registry.

  | Slice | Source owner | Focused test owner | First guarded boundary |
  | --- | --- | --- | --- |
  | S1 | `capabilities.py`; `reviewed_tool_packages.py` | `tests/test_workflow_capabilities.py`; `tests/test_dar_authoring_reviewed_tool_packages.py` | Template registration completes before package, job, dependency, or extension execution. |
  | S2 | `reviewed_tool_packages.py`; descriptor/parser; `policy.py`; registration/preflight path | `tests/test_dar_authoring_reviewed_tool_packages.py`; `tests/test_dar_authoring_descriptor.py`; `tests/test_dar_authoring_policy.py`; `tests/test_dar_authoring_registration.py`; `tests/test_dar_authoring_preflight.py` | Separate host discovery completes before package writing; descriptor/policy admission precedes job ingress, package code, extension dispatch, and output allocation. |
  | S3 | `authorized_tools.py`; `action_ledger.py` | `tests/test_dar_authoring_authorized_tools.py`; `tests/test_dar_authoring_action_ledger.py` | `_consume_approved_decision` and the action ledger bind approval/reservation before host dispatch. |
  | S4 | `sealed_artifact_preparation.py`; `sealed_artifact_runner.py`; `sealed_artifact_workflow_runner.py`; `action_ledger.py` | `tests/test_sealed_artifact_preparation.py`; `tests/test_sealed_artifact_handles.py`; `tests/test_sealed_artifact_output_handles.py`; `tests/test_sealed_artifact_workflow_runner.py` | `SealedArtifactWorkflowRunner.run` validates admission before callback resolution; output handles remain private until output-set publication. |
  | S5 | `host.py`; `embedding_sealed_artifact_callback.py` | `tests/test_dar_authoring_host.py`; `tests/test_embedding_sealed_artifact_callback.py`; existing S1–S4 suites | `LocalWorkflowHost` composition decides extension availability before authoring/admission; the legacy embedding resolver remains its separate callback path. |

  - Discovery evidence: CodeGraph traced these owners and callers on 2026-09-15.
    No current seam is a vector-index runtime, model registry, plugin manager,
    or second action coordinator.

- [x] T002 [tests, RED] Add reviewed-template registry and discovery vectors.
  - Spec: Reviewed template; FR-1 host-controlled registry prerequisite;
    FR-6 registration gate.
  - Plan: S1.1.
  - Files/components: capability and reviewed-host-binding test modules named
    by T001; `workflow_host/capabilities.py` and
    `workflow_host/reviewed_tool_packages.py`.
  - Depends on: T001.
  - Validation: focused test command recorded by T001 must fail for missing
    immutable reviewed-template/discovery behavior.
  - Evidence: fake-only RED vectors cover canonical ID/version/digest,
    zero/one/multiple/disabled discovery, closed `{job_handle}` input,
    output triple and limits, receipt size/identifier/count bounds and the
    immutable success-receipt schema digest,
    mandatory `embedding.execute.v1` binding, and rejection of a host lacking
    reversible pending publication or an idempotent recovery operation. S4
    validates the schema's receipt grammar and count values against candidate
    host results.
  - Completed evidence: `tests/test_workflow_capabilities.py` and
    `tests/test_dar_authoring_reviewed_tool_packages.py` use fake-only vectors
    for exact discovery, immutable digest binding, disabled resolution, the
    closed input/output/recovery contract, and receipt metadata.

- [x] T003 [implementation] Add the minimal immutable reviewed-template
  registration and discovery values.
  - Spec: Reviewed template; FR-1 host-controlled registry prerequisite.
  - Plan: S1.2–S1.3.
  - Files/components: source owners confirmed by T001, beginning with
    `workflow_host/capabilities.py` and `workflow_host/reviewed_tool_packages.py`.
  - Depends on: T002.
  - Validation: T002 focused suite passes; existing ordinary
    capability-provider tests still pass.
  - Evidence: registration is host-owned and private, resolution returns one
    exact identity or the stable unavailable/ambiguous outcome, and ordinary
    capability-provider semantics have no vector-template rules.
  - Completed evidence: the immutable template, discovery registry, and
    private-state control plane live beside the existing capability and
    reviewed-tool-package primitives; resolution revalidates the full digest
    and rejects disabled or stale registrations.

- [x] T004 [tests, GREEN] Prove reviewed-template resolution is fail-closed and
  isolated from legacy capability requirements.
  - Spec: Reviewed template; FR-1 host-controlled registry prerequisite;
    FR-2; Non-Goals.
  - Plan: S1 exit.
  - Files/components: focused registry tests from T001 and legacy capability
    requirement tests.
  - Depends on: T003.
  - Validation: recorded S1 focused test command plus
    `poetry run pytest tests/test_workflow_capabilities.py -q` when that file
    remains the existing contract-test owner.
  - Evidence: registration/discovery requires no package, job, embedding
    material, or extension execution; legacy requirements retain their prior
    behavior.
  - Completed evidence: focused S1 tests pass for unavailable, ambiguous,
    stale, and disabled cases, while the ordinary capability-contract tests in
    `tests/test_workflow_capabilities.py` remain green.

- [x] T005 [tests, RED] Add separate host-discovery, descriptor, and admission
  vectors for the exact reviewed-template declaration.
  - Spec: FR-1; FR-2; Public invocation; Required Verification 1, 2, and 10.
  - Plan: S2.1.
  - Files/components: reviewed-template, descriptor, and policy tests named by
    T001; `workflow_host/reviewed_tool_packages.py`, descriptor/parser, and
    `workflow_host/policy.py`.
  - Depends on: T004.
  - Validation: focused S2 test command recorded by T001 fails before parser,
    policy, and registration changes.
  - Evidence: RED cases prove the separate host API returns only the exact
    identity and one-field declaration contract, then rejects zero/multiple
    discovery without writing a package or creating a job/approval/dispatch.
    They reject zero/multiple call sites, changed/disabled/digest-mismatched
    templates, and every forbidden package authority field; successful
    authoring binds only the returned exact identity and one-field call
    contract. The API is not injected through `WorkflowAuthoringHost`.
  - Completed evidence: `tests/test_dar_authoring_reviewed_tool_packages.py`
    first failed for the absent discovery API, then covers the available,
    unavailable, and ambiguous results. The existing focused descriptor,
    policy, registration, and preflight vectors cover the closed declaration,
    policy binding, unavailable host state, and pre-ingress rejection.

- [x] T006 [implementation] Add separate host discovery and bind one exact
  reviewed-template declaration into descriptor, policy digest, registration,
  and preflight.
  - Spec: FR-1; FR-2; FR-4.
  - Plan: S2.2.
  - Files/components: `workflow_host/reviewed_tool_packages.py`,
    `workflow_host/policy.py`, descriptor/parser, registration, preflight, and
    host owners identified by T001.
  - Depends on: T005.
  - Validation: T005 focused suite passes.
  - Evidence: the host API exposes only available declaration identity/contract
    before an external authoring client writes a package; it performs no
    package write, job creation, approval, or dispatch. Admission rejects an
    invalid declaration or registration before sealed-job ingress, package
    code, extension dispatch, or artifact allocation; no package field can
    select host implementation or policy.
  - Completed evidence: `ReviewedCapabilityTemplateAuthoringDiscoveryService`
    joins the runtime registry with the persisted host registration and returns
    only declaration identity/contract. `WorkflowRegistration` now records the
    reviewed capability ID, version, and template digest explicitly and binds
    them into its registration digest; descriptor, policy, registration, and
    preflight revalidate the declared identity.

- [x] T007 [tests, GREEN] Prove reviewed-template admission and legacy package
  compatibility.
  - Spec: FR-1; FR-2; Non-Goals.
  - Plan: S2.3 and S2 exit.
  - Files/components: descriptor, authoring, registration, preflight, and
    legacy-package fixtures identified by T001.
  - Depends on: T006.
  - Validation: recorded S2 focused suites.
  - Evidence: reviewed packages fail closed on identity or mandatory-dependency
    drift; the separate discovery API writes no package and returns the stable
    unavailable/ambiguous result; and packages without the reviewed declaration
    use their unchanged legacy admission path.
  - Completed evidence: `poetry run pytest
    tests/test_dar_authoring_reviewed_tool_packages.py
    tests/test_dar_authoring_descriptor.py tests/test_dar_authoring_policy.py
    tests/test_dar_authoring_registration.py tests/test_dar_authoring_preflight.py
    -q` passed 102 tests after the admission-record identity binding.

- [x] T008 [tests, RED] Add sealed-job, approval, and reservation failure
  vectors using a fake host extension.
  - Spec: FR-3; FR-4; Required Verification 3 through 5.
  - Plan: S3.1 and S3.4.
  - Files/components: authorization/action-ledger and host-dispatch test
    modules named by T001; `workflow_host/authorized_tools.py` and
    `workflow_host/action_ledger.py`.
  - Depends on: T007.
  - Validation: focused S3 test command recorded by T001 fails for missing
    reservation and revalidation behavior.
  - Evidence: fake-only cases prove zero dispatch/handles for malformed,
    foreign, expired, unauthorized, envelope/member/template/extension/
    dependency mismatches; they prove post-approval binding mutation requires
    a new approval, no fallback dependency selection, one call per run, and no
    concurrent/replayed job dispatch. Focused S3 RED/GREEN coverage is in
    `tests/test_dar_authoring_reviewed_capability_jobs.py`,
    `tests/test_dar_authoring_action_ledger.py`, and
    `tests/test_dar_authoring_reviewed_capability_execution.py`.

- [x] T009 [implementation] Add the generic sealed-job resolver and durable
  single-store reservation record.
  - Spec: FR-3; FR-4.
  - Plan: S3.2–S3.4.
  - Files/components: `workflow_host/authorized_tools.py`,
    `workflow_host/action_ledger.py`, and the sealed-job/host resolver seams
    identified by T001.
  - Depends on: T008.
  - Validation: T008 focused suite passes.
  - Evidence: the reservation atomically consumes the full run/package/call
    site/template/job issuer/job opaque ID/job revision/job digest/principal/
    approval-nonce tuple; its identity is the sole replay and recovery key.
    `ReviewedCapabilityExecutor` uses the sealed transport and the single-store
    approval-to-reservation transition without host authority over the tuple.

- [x] T010 [tests, GREEN] Prove exact pre-dispatch revalidation and ordinary
  dispatch failure semantics.
  - Spec: FR-3; FR-4; FR-5 failure-before-`host_pending` rule.
  - Plan: S3 exit.
  - Files/components: focused S3 tests from T001.
  - Depends on: T009.
  - Validation: recorded S3 focused suite.
  - Evidence: valid jobs dispatch once; every invalid, replayed, or concurrent
    attempt has zero dispatches/handles; a pre-`host_pending` host-dispatch
    failure durably reaches `aborted` and returns only the closed redacted
    failure receipt. `poetry run pytest
    tests/test_dar_authoring_action_ledger.py
    tests/test_dar_authoring_reviewed_capability_jobs.py
    tests/test_dar_authoring_reviewed_capability_execution.py -q` passed 30
    tests after exact template revalidation was added.

- [x] T011 [tests, RED] Add the staged-egress and recovery state-machine test
  matrix with fake artifacts, host, and clock.
  - Spec: FR-5; FR-6; Required Verification 6 through 11.
  - Plan: S4.1–S4.4.
  - Files/components: sealed-artifact/action-ledger/host-extension test
    modules named by T001; `workflow_host/sealed_artifact_preparation.py`,
    `sealed_artifact_runner.py`, and `action_ledger.py`.
  - Depends on: T010.
  - Validation: focused S4 test command recorded by T001 fails before staged
    egress and recovery implementation.
  - Evidence: fake-only RED vectors reject before `host_pending` missing roles,
    invalid role media, oversized artifacts, invalid counts, unknown or
    sensitive receipt fields, host-supplied status/handles/timestamp, unsafe
    manifest source identifiers/content/vectors/paths/profile contents, and
    non-aggregate coverage fields. Injected crash/restart cases cover every
    durable transition and each side of every host recovery call: recoverable
    post-`host_pending` crashes reconcile the same attempt to completion with
    no rebuild/republish, while unrecoverable cases revoke private candidates
    and inaccessible handles, compensate, and preserve the prior visible
    generation. Add a delivery-retry vector after durable `completed` that
    returns the exact stored receipt for the same correlation ID with no host
    call, build, or publication. Add fake-clock retention vectors for current
    generation deferral through `assert_generation_current`, non-current
    successful `unpublish_generation_atomically` before revocation, either
    host-operation error retention, and cross-principal/run retrieval denial
    for all three roles.

- [x] T012 [implementation] Add generic private candidate staging, bounded
  role validation, inaccessible promotion, and receipt assembly.
  - Spec: FR-5.
  - Plan: S4.2.
  - Files/components: `workflow_host/sealed_artifact_preparation.py`,
    `workflow_host/sealed_artifact_runner.py`, and artifact-service seams
    identified by T001.
  - Depends on: T011.
  - Validation: applicable T011 staging/receipt tests pass.
  - Evidence: DAR validates exactly the template-declared artifact roles,
    media, size, retention, counts, manifest/coverage safety, and closed host
    result; only DAR creates handles, status, and `published_at` from its host
    clock.

- [x] T013 [implementation] Add reservation-keyed recovery transitions and the
  four-operation host recovery protocol.
  - Spec: FR-5; FR-6.
  - Plan: S4.3.
  - Files/components: `workflow_host/action_ledger.py`,
    `workflow_host/sealed_artifact_runner.py`, and host-extension seam
    identified by T001.
  - Depends on: T011, T012.
  - Validation: applicable T011 recovery/restart tests pass.
  - Evidence: DAR and host durable-record ordering follows the specification;
    recovery only resumes the original reservation identity, either completes
    it or compensates it, and never rebuilds or republishes.

- [x] T014 [implementation] Enforce option-2 current-generation retention
  before artifact revocation.
  - Spec: Authority split; FR-5.
  - Plan: S4.4.
  - Files/components: generic artifact-retention owner and host-extension
    resolution/unpublication seam identified by T001.
  - Depends on: T012, T013.
  - Validation: applicable T011 fake-clock and cross-principal/run retrieval
    tests pass.
  - Evidence: DAR calls `assert_generation_current` before revocation and
    defers it for a current generation. For a non-current generation, DAR first
    obtains successful `unpublish_generation_atomically`; either host-operation
    error retains artifacts and leaves the current generation unchanged for all
    three output roles.

- [x] T015 [tests, GREEN] Prove the completed publication receipt and all
  failure/recovery outcomes.
  - Spec: FR-5; FR-6; Required Verification 6 through 11.
  - Plan: S4 exit.
  - Files/components: focused S4 suites from T001.
  - Depends on: T012, T013, T014.
  - Validation: recorded S4 focused suite.
  - Evidence: only `completed` exposes three principal/run-bound opaque handles
    and the DAR-clocked aggregate receipt; unrecoverable attempts return only a
    closed redacted failure receipt and preserve the prior visible generation;
    a delivery retry returns the same stored completed receipt without another
    host operation, build, or publication. `poetry run pytest
    tests/test_dar_authoring_reviewed_capability_outputs.py
    tests/test_dar_authoring_reviewed_capability_publication.py
    tests/test_dar_authoring_reviewed_capability_execution.py -q` passed 31
    focused tests after receipt-bound validation and runner completion wiring.

- [x] T016 [tests, RED] Add host-composition and end-to-end fake-extension
  vectors.
  - Spec: Objective; Authority split; Non-Goals.
  - Plan: S5.1–S5.2.
  - Files/components: `workflow_host/host.py`, host-composition/end-to-end test
    modules named by T001.
  - Depends on: T015.
  - Validation: focused S5 suite recorded by T001 fails before composition.
  - Evidence: default `LocalWorkflowHost` has no vector extension and fails
    discovery/admission closed; an explicitly composed fake extension covers
    authoring through approval, dispatch, completion, and receipt retrieval
    without leaking sealed members or host policy to arguments or traces.

- [x] T017 [implementation, GREEN] Compose the optional reviewed extension and
  preserve legacy embedding behavior.
  - Spec: Objective; Non-Goals.
  - Plan: S5.1–S5.3 and S5 exit.
  - Files/components: `workflow_host/host.py`,
    `workflow_host/embedding_sealed_artifact_callback.py`, and the host and
    embedding regression tests identified by T001.
  - Depends on: T016.
  - Validation: recorded S5 suite plus focused existing embedding-index,
    reviewed-tool-package, action-ledger, sealed-artifact, authoring, and
    workflow-host suites.
  - Evidence: a deployment opt-in composes the reviewed vector extension;
    default DAR and legacy workflows gain no template behavior, and
    `EmbeddingSealedArtifactCallbackResolver` remains composed for its
    existing embedding workflow when no vector extension is installed. `poetry
    run pytest tests/test_dar_authoring_host.py
    tests/test_dar_authoring_runner.py
    tests/test_dar_authoring_reviewed_tool_packages.py
    tests/test_dar_authoring_action_ledger.py
    tests/test_embedding_index_artifacts.py -q` passed 135 tests.

- [x] T018 [verification] Run the complete regression and static-validation
  gate after all focused suites are green.
  - Spec: Required Verification; Acceptance Criteria.
  - Plan: Validation Strategy.
  - Files/components: all changed source, tests, and specification artifacts.
  - Depends on: T017.
  - Validation: `poetry run pytest -q`; `poetry run ruff check src tests`;
    `poetry run pre-commit run --files <changed files>`; `git diff --check`.
  - Evidence: every command passes; test logs establish fake-only execution,
    zero side effects on failed admission/dispatch/nonterminal recovery, and no
    live model, network, vault, vector database, external tool, or published
    index destination. Elevated macOS sandbox/MPS validation ran `poetry run
    pytest -q` successfully: 2698 passed, 1 skipped, 7 deselected in 71.62s;
    `poetry run ruff check src tests`, `poetry run pre-commit run --files
    specs/reviewed-vector-index-host-extension/tasks.md`, and `git diff
    --check` passed.

## Checkpoints

- C1 — T004: exact reviewed-template registration requires the host binding's
  reversible-publication and idempotent-recovery operations, but performs no
  package load or host implementation execution.
- C2 — T007: separate host discovery writes no package or authority, while
  authoring and admission bind exactly one reviewed call site and legacy
  packages remain unchanged.
- C3 — T010: one sealed job and one approval consume exactly one dispatch.
- C4 — T015: staged publication/recovery provides bounded opaque egress with
  no partial public outcome.
- C5 — T018: opt-in host composition and full regression are verified.

## Validation

- Focused RED/GREEN commands recorded by T001 — use after every task; a failed
  RED baseline is required before its paired implementation task starts.
- `poetry run pytest -q` — final repository regression gate.
- `poetry run ruff check src tests` — final static-analysis gate.
- `poetry run pre-commit run --files <changed files>` — final formatting and
  repository-hook gate.
- `git diff --check` — final whitespace gate.

## Domain and Boundary Notes

- Domain assumptions verified: DAR provides generic reviewed-template,
  approval, sealed-artifact, egress, and retention machinery only. The host
  extension owns all source, material, indexing, resource, retry, publication,
  and deletion semantics.
- Bounded-context checks: no task may implement `build_vector_index`, MLX, a
  vault, an embedding backend, an ANN/vector store, or a publication target in
  DAR. All task tests use fakes, in-memory state, or a temporary private-state
  root.
