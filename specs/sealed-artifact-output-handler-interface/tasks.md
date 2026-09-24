# Sealed Artifact Output Handler Interface Tasks

Status: Complete

## Prerequisites

- Spec: `spec.md` — implementation-ready
- Plan: `plan.md` — reviewed and ready for task-list authoring
- Validation: `validation.md` — Council and Ponytail review recorded
- Existing service: `src/dynamic_agent_runner/workflow_host/sealed_artifact_runner.py`

## Task list

- [x] T001 [discovery] Confirm source symbols, callers, and guarded side effects
  before writing RED tests.
  - Plan: Spec trace; Current-State Anchors.
  - Files/components: `src/dynamic_agent_runner/workflow_host/sealed_artifact_runner.py`,
    `reviewed_capability_outputs.py`, `reviewed_capability_publication.py`,
    `sealed_artifact_workflow_runner.py`, `host.py`,
    `src/dynamic_agent_runner/multimodal_model_runner.py`, and focused tests.
  - Depends on: none.
  - Validation: `codegraph explore "SealedArtifactOutputHandleService stage_declared promote discard read callers tests"` plus targeted symbol inspection.
  - Evidence: a route table below names the exact source owner, test owner, and
    first guarded side effect for every milestone; any owner substitution is
    recorded before T002.
  - Completed evidence: CodeGraph and targeted source inspection confirmed the
    service methods, reviewed-capability callers, and multimodal host callback
    seam listed below.

### Discovery route table (T001 output)

| Milestone | Source owner/symbol | Focused test owner | First guarded side effect |
| --- | --- | --- | --- |
| M1 | New `workflow_host/sealed_artifact_output_handler.py`: request/read-binding values and error types | New `tests/test_sealed_artifact_output_handler.py` | Value validation before any store call |
| M2 | `SealedArtifactOutputHandleService.stage_declared`, `promote`, `read`; `_declared_output_values` | `tests/test_sealed_artifact_output_handler.py`, `tests/test_sealed_artifact_output_handles.py` | No public handle before promotion |
| M3 | `SealedArtifactOutputHandleService` and `PrivateStateStore` transition seam | `tests/test_sealed_artifact_output_handler.py`, `tests/test_sealed_artifact_output_handles.py` | Atomic private-state transition before revocation/publication |
| M4 | `LocalWorkflowHost.dispatch_multimodal_runner` and `publish_result` in `workflow_host/host.py` | `tests/test_multimodal_model_runner_protocol.py` | Cleanup/reap and terminal checks before staging/publication |
| M5 | Existing reviewed-capability and workflow-runner callers | Their existing focused suites | Legacy behavior preserved before full regression |

- [x] T002 [tests, RED] Add immutable request/read-binding and error-contract
  vectors.
  - Spec: Recommended interface; Stage request; Error contract.
  - Plan: M1; Normative implementation decisions.
  - Files/components: new `tests/test_sealed_artifact_output_handler.py`.
  - Depends on: T001.
  - Validation: `poetry run pytest tests/test_sealed_artifact_output_handler.py -q` must fail before implementation.
  - Evidence: RED cases cover non-empty IDs, lowercase 64-character digests,
    aware UTC expiry, immutable ordered candidates, read-binding restrictions,
    error classifications, and redaction of candidate bytes/storage details.
    The fixture supplies one host-admitted declaration
    `tuple[SealedArtifactOutput, ...]` through a private declaration resolver;
    producers provide only `descriptor_digest` and candidate bytes.
  - Completed evidence: initial run failed with the missing handler module,
    proving the RED boundary.

- [x] T003 [implementation] Implement immutable handler values and package-owned
  errors.
  - Spec: Recommended interface; Stage request; Error contract.
  - Plan: M1.
  - Files/components: new
    `src/dynamic_agent_runner/workflow_host/sealed_artifact_output_handler.py`.
  - Depends on: T002.
  - Validation: `poetry run pytest tests/test_sealed_artifact_output_handler.py -q`; `poetry run ruff check src/dynamic_agent_runner/workflow_host/sealed_artifact_output_handler.py tests/test_sealed_artifact_output_handler.py`.
  - Evidence: values are immutable/runtime-validated; `private_set_id` is
    allowed only in host-private lifecycle receipts and never in public
    receipts, traces, protocol results, exceptions, or candidate serialization.
    The handler is configured with a host-owned declaration resolver keyed by
    `(workflow_id, package_id, descriptor_digest)`, so its call to
    `stage_declared` always uses an admitted declaration rather than a
    producer-selected output contract.
  - Completed evidence: added immutable request/read-binding values, declaration
    resolver binding, redacted errors, and the handler module.

- [x] T004 [tests, GREEN] Lock the value-level contract and redaction behavior.
  - Spec: concrete field types, private-ID boundary, error precedence.
  - Plan: M1 exit.
  - Files/components: `tests/test_sealed_artifact_output_handler.py`.
  - Depends on: T003.
  - Validation: `poetry run pytest tests/test_sealed_artifact_output_handler.py -q` plus `git diff --check`.
  - Evidence: positive/negative vectors pass and invalid values fail before a
    `PrivateStateStore` operation.
  - Completed evidence: focused handler tests pass — 13 passed; targeted Ruff
    and `git diff --check` pass.

- [x] T005 [tests, RED] Add adapter lifecycle tests for stage, promote, read,
  and failure cleanup.
  - Spec: lifecycle contract; ownership boundaries.
  - Plan: M2.
  - Files/components: `tests/test_sealed_artifact_output_handler.py` and
    `tests/test_sealed_artifact_output_handles.py`.
  - Depends on: T004.
  - Validation: `poetry run pytest tests/test_sealed_artifact_output_handler.py tests/test_sealed_artifact_output_handles.py -q` must fail before adapter implementation.
  - Evidence: RED cases prove stage creates no public handle, valid promotion
    returns opaque handles, read requires binding, and invalid/cancelled/
    producer-failed paths discard without publication.
  - Completed evidence: lifecycle RED coverage was added before adapter
    implementation; the pre-implementation collection failed at module import.

- [x] T006 [implementation] Implement the four-operation handler adapter over
  the existing service.
  - Spec: Recommended interface; Compatibility with the current service.
  - Plan: M2.
  - Files/components: `src/dynamic_agent_runner/workflow_host/sealed_artifact_output_handler.py`.
  - Depends on: T005.
  - Validation: T005 focused command passes; targeted Ruff passes.
  - Evidence: `stage_declared`, `promote`, `discard`, and `read` delegate to
    the existing service/store without a registry, event bus, second store, or
    producer abstraction; workflow/package/producer admission stays at the
    handler/caller boundary.
  - Completed evidence: handler delegates to the existing service and uses the
    injected host-owned declaration resolver.

- [x] T007 [tests, GREEN] Prove adapter mapping, ownership, and redaction.
  - Spec: Error contract; Ownership and validation boundaries.
  - Plan: M2 exit.
  - Files/components: handler tests plus existing
    `tests/test_sealed_artifact_output_handles.py`.
  - Depends on: T006.
  - Validation: `poetry run pytest tests/test_sealed_artifact_output_handler.py tests/test_sealed_artifact_output_handles.py -q`.
  - Evidence: service errors map to stable classifications and precedence;
    no candidate bytes, storage details, paths, credentials, provider errors,
    or service exception text leak.
  - Completed evidence: handler and existing output-handle suites pass — 22
    tests; targeted Ruff passes.

- [x] T008 [tests, RED] Add lifecycle race, replay, expiry, and terminal-state
  vectors.
  - Spec: promote/discard linearization; replay identity; strict expiry.
  - Plan: M3; required transition table.
  - Files/components: handler tests and
    `tests/test_sealed_artifact_output_handles.py`.
  - Depends on: T007.
  - Validation: `poetry run pytest tests/test_sealed_artifact_output_handler.py tests/test_sealed_artifact_output_handles.py -q -k "discard or promote or replay or expiry or lifecycle"` must fail before the service seam is implemented.
  - Evidence: RED cases cover second discard, discard-after-promote, concurrent
    promote/discard, duplicate promotion, `now == expires_at`, expired private
    records, and zero/multiple replay successors.
  - Completed evidence: lifecycle vectors were added before the transition seam;
    the lifecycle selector failed until the seam was implemented.

- [x] T009 [implementation] Add the handler-specific service-owned atomic
  terminal-outcome seam.
  - Spec: lifecycle contract; no second lifecycle authority.
  - Plan: M3.
  - Files/components: `src/dynamic_agent_runner/workflow_host/sealed_artifact_runner.py`,
    its `PrivateStateStore` seam, and adapter delegation. Keep the existing
    public `discard` behavior unchanged for legacy callers.
  - Depends on: T008.
  - Validation: targeted lifecycle tests; existing service tests remain green.
  - Evidence: add the internal seam
    `_transition_private_output(private_set_id, operation, now) ->
    SealedArtifactPrivateTransitionResult`, where `operation` is exactly
    `"promote"` or `"discard"` and the result status is exactly
    `"promoted"`, `"discarded"`, `"missing"`, or `"conflict"`. A promoted
    result carries the one successor's output values/expiry; a conflict carries
    no candidate bytes. Promotion is consume-and-issue; handler discard never
    revokes a public successor. If needed, only a minimal terminal marker in
    the same store is retained.
  - Completed evidence: added `transition_private_output` with atomic store
    transitions, replay matching, conflict detection, and handler-only discard
    semantics; legacy public `discard` remains unchanged.

- [x] T010 [tests, GREEN] Prove deterministic lifecycle and replay behavior.
  - Spec: required transition table and error precedence.
  - Plan: M3 exit.
  - Files/components: handler/service tests.
  - Depends on: T009.
  - Validation: `poetry run pytest tests/test_sealed_artifact_output_handler.py tests/test_sealed_artifact_output_handles.py -q -k "discard or promote or replay or expiry or lifecycle"`.
  - Evidence: replay never creates a second public set; second discard is a
    no-op; foreign/missing state remains distinguishable; expiry and conflict
    classifications match the contract.
  - Completed evidence: focused handler/output suites pass — 22 tests,
    including concurrent promote/discard, replay, strict expiry, and
    discard-after-promote coverage.

- [x] T011 [verification] Verify the multimodal publication-gate seam.
  - Spec: Multimodal migration binding.
  - Plan: M4; prerequisite protocol gate.
  - Files/components: `tests/test_multimodal_model_runner_protocol.py`,
    `workflow_host/host.py` dispatch seam, and handler tests.
  - Depends on: T010.
  - Validation: `poetry run pytest tests/test_multimodal_model_runner_protocol.py -q` must pass before migration edits; inspect the callback owner before wiring.
  - Evidence: first document the current `publish_result` callback owner and
    assert its completed-only behavior; RED cases then prove staging occurs
    only after identity/accounting/cleanup/reap checks and promotion only
    after terminal publication checks.
  - Completed evidence: the existing completed-only callback ordering test
    passes. No production callback currently carries private output candidates;
    the protocol result carries opaque handles only, so no handler wiring was
    added at this boundary.

- [x] T012 [verification] Preserve the multimodal callback boundary without
  inventing a publication path.
  - Spec: migration binding and normalized result boundary.
  - Plan: M4.
  - Files/components: `src/dynamic_agent_runner/workflow_host/host.py`
    (`LocalWorkflowHost.dispatch_multimodal_runner` and `publish_result`),
    plus the handler module.
  - Depends on: T011.
  - Validation: `poetry run pytest tests/test_multimodal_model_runner_protocol.py -q`; targeted Ruff passes.
  - Evidence: completed results already use opaque protocol handles only and
    the existing callback signature remains intact. Cleanup failure, timeout,
    cancellation, malformed result, producer failure, and foreign admission
    paths are covered by the protocol suite; no candidate-bearing production
    callback exists for this handler to replace.
  - Completed evidence: no production candidate-bearing callback exists to
    migrate. `dispatch_multimodal_runner` retains its completed-only callback
    signature and existing tests remain green; future candidate publication
    must supply the handler explicitly.

- [x] T013 [tests, GREEN] Prove migration ordering and legacy compatibility.
  - Spec: migration gates; compatibility with current service.
  - Plan: M4/M5.
  - Files/components: `tests/test_multimodal_model_runner_protocol.py`,
    `tests/test_sealed_artifact_workflow_runner.py`,
    `tests/test_dar_authoring_reviewed_capability_publication.py`, and
    `tests/test_dar_authoring_reviewed_capability_outputs.py`.
  - Depends on: T012.
  - Validation: `poetry run pytest tests/test_multimodal_model_runner_protocol.py tests/test_sealed_artifact_output_handler.py tests/test_sealed_artifact_workflow_runner.py tests/test_dar_authoring_reviewed_capability_publication.py tests/test_dar_authoring_reviewed_capability_outputs.py -q`.
  - Evidence: existing direct service `publish`, `stage_declared`, `promote`,
    `discard`, `read`, and expiry-extension behavior remains unchanged,
    including legacy direct discard semantics; handler-specific terminal
    behavior is covered separately. Multimodal publication cannot precede
    worker reap.
  - Completed evidence: focused migration and legacy suites pass — 54 tests;
    direct service callers retain their existing behavior.

- [x] T014 [verification] Run final regression and record handoff evidence.
  - Spec: all acceptance criteria.
  - Plan: M5; Handoff gate.
  - Files/components: changed source/tests and
    `specs/sealed-artifact-output-handler-interface/validation.md`.
  - Depends on: T013.
  - Validation: focused suites above, `poetry run ruff check src tests`,
    `git diff --check`, and the repository's full `poetry run pytest -q` suite
    when implementation is complete.
  - Evidence: record RED-before-implementation, final test counts, any
    compatibility exceptions, and confirmation that no live model/provider/
    network call was used. Record exact pass/skip/failure counts for every
    focused command and the full suite.
  - Completed evidence: full suite — 2800 passed, 1 skipped, 7 deselected;
    `poetry run ruff check src tests` passed; `git diff --check` passed. No
    live model/provider/network call was used.

## Handoff checklist

- [x] Every implementation task has a preceding RED test task.
- [x] The service-owned transition seam is atomic and remains the sole
  lifecycle authority.
- [x] `private_set_id` remains host-private and never enters public results.
- [x] Existing atomic publication callers remain green.
- [x] Multimodal protocol prerequisite passes before migration wiring.
- [x] `validation.md` contains final test and redaction evidence.
