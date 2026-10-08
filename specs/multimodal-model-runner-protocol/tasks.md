# DAR Multimodal Model Runner Protocol Tasks

Status: Complete

## Prerequisites

- Spec: `spec.md` — implemented v1
- Plan: `plan.md` — implemented
- Data model: none; v1 contract values are owned by the protocol module and
  existing material/worker/sealed-artifact contracts.
- Contracts: none beyond `spec.md` and the related specifications listed in
  `plan.md`.

## Cited Inputs

- `specs/multimodal-model-runner-protocol/spec.md` — approved protocol boundary,
  non-goals, and acceptance criteria — inspected.
- `specs/multimodal-model-runner-protocol/plan.md` — approved delivery order,
  normative encoding/lifecycle invariants, source anchors, and verification
  matrix — inspected.
- `specs/local-model-runner-interface/spec.md` — existing runner and floorplan
  ownership boundary — inspected.
- `specs/workflow-input-converter-plugin/spec.md` — sealed converter contract
  and private packed-input boundary — inspected.
- `specs/model-generation-resource-budgets/spec.md` — canonical budget and
  worker containment contract — inspected.
- `specs/sealed-artifact-workflow-runner/spec.md` — sealed input/output and
  cleanup precedent — inspected.
- `specs/sealed-artifact-output-handler-interface/spec.md` — host-owned staged
  output lifecycle and redacted error boundary — implementation-ready.
- `specs/sealed-artifact-output-handler-interface/validation.md` — handler
  implementation evidence and focused/full test results — inspected.

## Task List

- [x] T001 [discovery] Confirm the plan's source symbols, test owners, and
  pre-dispatch side-effect boundaries before writing RED tests.
  - Spec: all acceptance criteria; especially exact admission and cleanup.
  - Plan: Current-State Anchors; Architecture and Data Flow.
  - Files/components: `src/dynamic_agent_runner/external_adapter.py`,
    `src/dynamic_agent_runner/workflow_host/local_model_runners.py`,
    `model_material_admission.py`, `model_materials.py`, `generation_worker.py`,
    `reviewed_capability_host_extension.py`, `host.py`,
    `transformers_peft_model.py`, and their focused tests.
  - Depends on: none.
  - Validation: `codegraph explore` each named owner and its callers; update
    the Discovery Route Table below with exact symbols and any substitution
    before T002.
  - Evidence: a route table naming one source owner, one focused test owner,
    and the first guarded side effect for M1–M5; no second registry,
    scheduler, provider abstraction, or lifecycle coordinator is introduced.
  - Completed evidence: CodeGraph confirmed
    `canonical_descriptor_digest`, `LocalModelRunnerCatalog`,
    `ModelMaterialAdmission`, `ModelDependencyLock`,
    `GenerationWorkerSession`, `GenerationWorkerResult`,
    `ReviewedCapabilityHostExtension`, `configure_prepared_transformers_host`,
    and `TransformersGenerateRunner`, with the focused test owners listed below.

### Discovery Route Table (T001 output)

| Milestone | Source owner and symbols to confirm | Focused test owner | First guarded side effect |
| --- | --- | --- | --- |
| M1 | Candidate `src/dynamic_agent_runner/multimodal_model_runner.py` contract values; `src/dynamic_agent_runner/external_adapter.py:canonical_descriptor_digest`; workflow-host canonical JSON helpers | New `tests/test_multimodal_model_runner_protocol.py`; `tests/test_external_adapter_protocol.py` for digest precedent | Contract parsing and digest validation before registration or request staging |
| M2 | `src/dynamic_agent_runner/workflow_host/local_model_runners.py:LocalModelRunnerCatalog`; `reviewed_capability_host_extension.py:ReviewedCapabilityHostExtension`; `host.py:configure_prepared_transformers_host` | `tests/test_local_model_runners.py`; `tests/test_dar_authoring_host.py` | Descriptor/admission rejection before materialization and worker creation |
| M3 | `src/dynamic_agent_runner/workflow_host/generation_worker.py:GenerationWorkerSession/GenerationWorkerResult`; `workflow_host/approvals.py`; `state.py`; `reviewed_capability_execution.py`; `host.py` | `tests/test_generation_worker.py`; `tests/test_generation_worker_controllers.py`; new protocol lifecycle cases | Binding/replay rejection before sealed-input ingress and dispatch |
| M4 | `workflow_host/host.py` Option 1 materializer adapter; `workflow_host/sealed_artifact_output_handler.py`; `workflow_host/sealed_artifact_runner.py`; `sealed_artifact_workflow_runner.py`; `reviewed_capability_outputs.py`; `reviewed_capability_publication.py` | `tests/test_multimodal_model_runner_protocol.py`; `tests/test_sealed_artifact_output_handler.py`; `tests/test_sealed_artifact_output_handles.py`; `tests/test_sealed_artifact_workflow_runner.py` | Result validation and private materialization before public output-handle publication |
| M5 | `src/dynamic_agent_runner/workflow_host/transformers_peft_model.py:TransformersGenerateRunner`; `host.py:configure_prepared_transformers_host`; sealed converter fixture | `tests/test_transformers_peft_model.py`; `tests/test_qwen25_vl_3b_grpo_converter.py`; `tests/test_dar_authoring_runner.py` | Protocol identity check before floorplan materialization |

- [x] T002 [tests, RED] Add protocol contract and canonical identity vectors.
  - Spec: protocol boundary; descriptor/result contract; acceptance criteria 1,
    4, and 5.
  - Plan: M1; Planned Contract Surface; Normative Encoding and Lifecycle
    Invariants.
  - Files/components: `tests/test_multimodal_model_runner_protocol.py` and
    the planned contract owner `src/dynamic_agent_runner/multimodal_model_runner.py`.
  - Depends on: T001.
  - Validation: `poetry run pytest tests/test_multimodal_model_runner_protocol.py -q`
    must fail before implementation.
  - Evidence: RED cases cover closed descriptor/health/request/context/result
    mappings, protocol/version mismatch, field ranges/grammars, forbidden raw
    values, canonical JSON bytes, lowercase SHA-256 vectors, and every
    identity-tuple mutation.
  - Completed evidence: the initial collection failed with
    `ModuleNotFoundError: dynamic_agent_runner.multimodal_model_runner`,
    proving the RED boundary before implementation.

- [x] T003 [implementation] Implement immutable v1 contract values and
  package-owned errors.
  - Spec: approved boundary, descriptor/lifecycle, result contract, and all
    redaction requirements.
  - Plan: M1; Planned Contract Surface; Normative Encoding and Lifecycle
    Invariants.
  - Files/components: `src/dynamic_agent_runner/multimodal_model_runner.py`,
    existing canonical digest/redaction helpers, and package exports only if
    the established public-export pattern requires them.
  - Depends on: T002.
  - Validation: `poetry run pytest tests/test_multimodal_model_runner_protocol.py -q`
    passes; `poetry run ruff check src tests` passes for changed files.
  - Evidence: all values are immutable and strictly validated; canonical bytes
    use the established compact sorted-key JSON convention; no vendor error,
    path, prompt, credential, process, or native object crosses the contract.
  - Completed evidence: added
    `src/dynamic_agent_runner/multimodal_model_runner.py` with strict descriptor,
    health, sealed-handle/request, generation-context, result, digest, and
    package-owned error values; the protocol surface is exported from
    `src/dynamic_agent_runner/__init__.py`.

- [x] T004 [tests, GREEN] Prove contract transfer, lifecycle, and cleanup
  invariants at the protocol boundary.
  - Spec: acceptance criteria 1, 3, and 4.
  - Plan: M1 exit; Normative Encoding and Lifecycle Invariants.
  - Files/components: `tests/test_multimodal_model_runner_protocol.py`.
  - Depends on: T003.
  - Validation: `poetry run pytest tests/test_multimodal_model_runner_protocol.py -q`.
  - Evidence: value-level tests prove input-handle linearity,
    terminal-state/error mapping, `worker_reaped` semantics, aggregate counter
    equality, and rejection of foreign/replayed result identities. Integrated
    worker cleanup and reap ordering are proved by T010.
  - Completed evidence: `poetry run pytest
    tests/test_multimodal_model_runner_protocol.py -q` — 10 passed; targeted
    Ruff check passed.

- [x] T005 [tests, RED] Add exact receiver registration, health, and admission
  vectors for one fake multimodal runner.
  - Spec: descriptor/lifecycle and acceptance criteria 1 and 2.
  - Plan: M2; Current-State Anchors for runner registration and reviewed host
    composition.
  - Files/components: `tests/test_multimodal_model_runner_protocol.py`,
    `tests/test_local_model_runners.py`, `tests/test_dar_authoring_host.py`,
    `src/dynamic_agent_runner/workflow_host/local_model_runners.py`,
    `reviewed_capability_host_extension.py`, and `host.py`.
  - Depends on: T004.
  - Validation: `poetry run pytest tests/test_multimodal_model_runner_protocol.py tests/test_local_model_runners.py tests/test_dar_authoring_host.py -q`
    must fail before registration integration.
  - Evidence: fake-only cases cover install/reload, duplicate/reserved IDs,
    malformed descriptors, bounded health without material loading, exact
    resolution, package-admission refusal, and zero worker/input side effects
    for every mismatch.
  - Completed evidence: RED admission/catalog cases first failed because
    `LocalModelRunnerCatalog.register_multimodal_runner` was absent; the
    focused suite now covers exact registration, reload support, duplicate and
    reserved IDs, descriptor drift, health refusal, and zero dispatch calls.

- [x] T006 [implementation] Register and resolve one exact admitted
  `dar.multimodal-runner.v1` runner.
  - Spec: exact admission and fail-closed requirements.
  - Plan: M2; Architecture and Data Flow.
  - Files/components: `src/dynamic_agent_runner/workflow_host/local_model_runners.py`,
    `src/dynamic_agent_runner/workflow_host/reviewed_capability_host_extension.py`,
    and `src/dynamic_agent_runner/workflow_host/host.py`.
  - Depends on: T005.
  - Validation: T005 focused command passes; `poetry run ruff check src tests`.
  - Evidence: registration binds protocol/version, descriptor, material lock,
    execution ABI, converter, output contract, resource limits, extension, and
    dependency identities before sealed-input ingress; existing external and
    ordinary local-runner paths remain unchanged.
  - Completed evidence: `LocalModelRunnerCatalog` now owns exact multimodal
    registration, reload, and resolution; `LocalWorkflowHost.open` accepts
    receiver-installed `(runner, descriptor)` pairs and retains the same
    catalog for later host resolution. No second persisted registry was added.

- [x] T007 [tests, GREEN] Prove admission compatibility and no material or
  worker side effects on drift.
  - Spec: acceptance criteria 1 and 2; non-goals.
  - Plan: M2 exit; Current-State Anchors.
  - Files/components: `tests/test_multimodal_model_runner_protocol.py`,
    `tests/test_local_model_runners.py`, `tests/test_workflow_model_material_admission.py`,
    and `tests/test_dar_authoring_host.py`.
  - Depends on: T006.
  - Validation: `poetry run pytest tests/test_multimodal_model_runner_protocol.py tests/test_local_model_runners.py tests/test_workflow_model_material_admission.py tests/test_dar_authoring_host.py -q`.
  - Evidence: changed material/converter/ABI/output/resource/extension facts
    fail before materialization, worker creation, or handle allocation; legacy
    paths retain their prior behavior.
  - Completed evidence: descriptor drift is rejected before a binding is
    stored, unavailable health is rejected during admission, and focused
    registration/resolution tests assert zero runner dispatches; protocol,
    local-runner, material-admission, and host suites pass (56 tests).

- [x] T008 [tests, GREEN] Add sealed-request identity, handle-linearity, and
  lifecycle failure vectors.
  - Spec: acceptance criteria 1–4 and result non-transferability.
  - Plan: M3; Normative Encoding and Lifecycle Invariants.
  - Files/components: `tests/test_multimodal_model_runner_protocol.py`,
    `tests/test_generation_worker.py`, `tests/test_generation_worker_controllers.py`,
    and the request/context adapter owners in
    `src/dynamic_agent_runner/workflow_host/generation_worker.py`,
    `host.py`, `approvals.py`, `state.py`, and
    `reviewed_capability_execution.py`.
  - Depends on: T007.
  - Validation: `poetry run pytest tests/test_multimodal_model_runner_protocol.py tests/test_generation_worker.py tests/test_generation_worker_controllers.py -q` must fail before lifecycle integration.
  - Evidence: RED cases cover foreign/expired/replayed handles, package or
    revision drift, budget exhaustion, cancellation, deadline, runner failure,
    malformed result, and cleanup/reap failure with zero public handles.
  - Partial evidence: protocol-level replay, invocation-context drift,
    foreign-result, one-dispatch, cleanup ordering, and cleanup-failure
    vectors are green. Dispatch now produces bounded cancelled and
    deadline-exceeded terminal results before runner invocation; direct
    generation-worker controller integration remains.
  - Completed evidence: the focused lifecycle command passes after the
    generation-worker/host cleanup path landed; invalid requests dispatch zero
    times and no public output is exposed before confirmed cleanup.

- [x] T009 [implementation] Adapt sealed request/context admission to the
  existing generation worker and host state seams.
  - Spec: host ownership of staging, budgets, worker containment, cleanup, and
    receipt publication.
  - Plan: M3; Architecture and Data Flow.
  - Files/components: `src/dynamic_agent_runner/workflow_host/generation_worker.py`,
    `src/dynamic_agent_runner/workflow_host/host.py`,
    `src/dynamic_agent_runner/workflow_host/approvals.py`,
    `src/dynamic_agent_runner/workflow_host/state.py`,
    `src/dynamic_agent_runner/workflow_host/reviewed_capability_execution.py`,
    and `src/dynamic_agent_runner/multimodal_model_runner.py`.
  - Depends on: T008.
  - Validation: T008 focused command passes; `poetry run ruff check src tests`.
  - Evidence: only receiver-created opaque handles and effective budgets reach
    the runner; authoritative bindings are revalidated immediately before
    dispatch; no fallback, retry, sealed-input ingress, or output allocation
    occurs after drift.
  - Partial evidence: `MultimodalRunnerBinding.dispatch` now performs one
    admitted call and runs input-clear, reservation-release, and worker-reap
    callbacks before returning a result. `GenerationWorkerLauncher.cleanup`
    now exposes the existing terminate/kill/reap contract for adapters and
    requires confirmed reap. `dispatch_with_worker_cleanup` and
    `LocalWorkflowHost.dispatch_multimodal_runner` now route host calls through
    exact resolution and that cleanup path.
  - Completed evidence: the focused lifecycle and host suites pass; the
    request/context adapter, bounded worker cleanup, exact dispatch, and reap
    ordering are implemented.

- [x] T010 [tests, GREEN] Prove one bounded dispatch and terminal cleanup for
  every lifecycle outcome.
  - Spec: acceptance criteria 2 and 3.
  - Plan: M3 exit; Normative Encoding and Lifecycle Invariants.
  - Files/components: `tests/test_multimodal_model_runner_protocol.py`,
    `tests/test_generation_worker.py`, and controller/host tests from T001.
  - Depends on: T009.
  - Validation: `poetry run pytest tests/test_multimodal_model_runner_protocol.py tests/test_generation_worker.py tests/test_generation_worker_controllers.py -q`.
  - Evidence: valid requests dispatch exactly once; invalid/replayed requests
    dispatch zero times; every terminal result is redacted and emitted only
    after input clearing, reservation release, termination/kill as needed, and
    confirmed reap.
  - Completed evidence: protocol dispatch tests cover completed,
    budget-exhausted, cancelled, deadline-exceeded, runner-failed, malformed,
    replayed, and cleanup-failed outcomes; each valid terminal path proves
    cleanup ordering and zero output publication before cleanup. The existing
    worker-controller suite and `dispatch_with_worker_cleanup` verify
    terminate/kill/reap integration.

- [x] T010a [decision] Select Option 1 for the multimodal
  result-to-sealed-output bridge: a receiver-owned materializer resolves
  runner handles to private candidates, then the host stages and promotes them
  through `SealedArtifactOutputHandler`.
  - Spec: Result contract; Initial migration target; host ownership of output
    staging and publication.
  - Plan: M4; Architecture and Data Flow.
  - Depends on: T010.
  - Current gap: `MultimodalRunnerResult.output_handles` contains
    `SealedMultimodalHandle` values, while `SealedArtifactOutputHandler` needs
    receiver-owned role/media/bytes candidates in a
    `SealedArtifactOutputStageRequest`. The current
    `publish_result(MultimodalRunnerResult)` callback provides neither
    candidates nor a materializer.
  - Decision: public results replace multimodal output handles with
    `SealedArtifactOutputHandle` values only after private materialization,
    declaration validation, staging, cleanup/reap confirmation, and atomic
    promotion. Text results do not invoke the materializer.
  - Completed evidence: the user selected Option 1; the follow-on tasks below
    freeze and verify the host-owned materializer seam without adding a second
    publication registry or exposing candidate bytes.

- [x] T010b [tests, GREEN] Specify the Option 1 materializer and publication
  vectors before adding its host adapter.
  - Spec: Result contract; host ownership of staging and publication.
  - Plan: M4; Architecture and Data Flow.
  - Depends on: T010a.
  - Files/components: new focused cases in
    `tests/test_multimodal_model_runner_protocol.py` and
    `tests/test_sealed_artifact_output_handler.py`, using a deterministic fake
    materializer and the existing declaration resolver.
  - Materializer contract: one receiver-owned
    `resolve(handle, *, package_id, package_revision_digest, invocation_id,
    descriptor_digest, expires_at, now)` operation accepts only a
    `SealedMultimodalHandle` plus the authoritative binding and returns exactly
    `(role, media_type, bytes)`. It resolves each handle once, keeps bytes
    process-private, returns no path/native object, and maps foreign, expired,
    unsupported, and missing values to package-owned publication errors.
  - Validation: `poetry run pytest -q
    tests/test_multimodal_model_runner_protocol.py
    tests/test_sealed_artifact_output_handler.py -k
    'materializer or publication or sealed_output'` must fail before the
    adapter exists.
  - Evidence: vectors require each output handle to resolve exactly once to a
    private `(role, media_type, bytes)` candidate; declaration role/media and
    max-byte limits, package/revision/invocation/descriptor/expiry bindings,
    and output-count limits are enforced; text results bypass materialization;
    foreign, expired, unsupported, and materializer-failure cases produce no
    public handle.
  - Completed evidence: focused materializer/publication vectors pass — 4
    tests; the RED collection first failed on the missing host publication
    entry point, then passed after the adapter landed.

- [x] T010c [implementation] Add the receiver-owned Option 1 host adapter.
  - Spec: Result contract; initial migration target; no raw output leakage.
  - Plan: M4; Architecture and Data Flow.
  - Depends on: T010b.
  - Files/components: `src/dynamic_agent_runner/workflow_host/host.py`,
    `src/dynamic_agent_runner/workflow_host/sealed_artifact_output_handler.py`,
    and the protocol result/receipt owner. Add one named host entry point,
    `publish_multimodal_result`, with the materializer and handler injected by
    the receiver; do not leave callable-versus-protocol choice to each caller.
    The adapter must not create a registry, provider abstraction, or second
    publication service.
  - Validation: T010b focused cases pass; `poetry run ruff check src tests`.
  - Result handoff: keep `MultimodalRunnerResult` as the private normalized
    runner value; return a separate host-owned publication tuple of
    `SealedArtifactOutputHandle` values for receipts/workflow egress. Never
    place candidate bytes or the pre-publication multimodal handles in that
    public tuple.
  - Evidence: after the existing dispatch cleanup/reap gate, completed
    artifact results resolve privately, construct a
    `SealedArtifactOutputStageRequest`, call `stage_declared`, and call
    `promote` exactly once; any failure calls handler-owned discard as
    applicable and returns a redacted failure without public handles or
    candidate bytes.
  - Completed evidence: `LocalWorkflowHost.publish_multimodal_result` now
    enforces identity, invokes the injected materializer once per opaque
    output, stages through `SealedArtifactOutputHandler`, promotes only after
    the dispatch cleanup gate, and maps publication failures to one redacted
    host error.

- [x] T010d [tests, GREEN] Prove Option 1 publication ordering and redaction.
  - Spec: acceptance criteria 3–5 and cleanup ownership.
  - Plan: M4 exit; Verification Matrix.
  - Depends on: T010c.
  - Files/components: multimodal protocol, host, sealed-output handler, and
    receipt/tracing tests.
  - Validation: `poetry run pytest -q
    tests/test_multimodal_model_runner_protocol.py
    tests/test_sealed_artifact_output_handler.py
    tests/test_sealed_artifact_output_handles.py
    tests/test_sealed_artifact_runner_admission.py -k
    'materializer or publication or sealed_output or cleanup'`.
  - Evidence: deterministic event traces prove input clear/release/reap →
    materialize → stage → promote for success; failure paths prove discard or
    reap before any public handle; receipts contain only normalized text,
    opaque promoted handles, aggregate counters, and redacted classifications.
  - Completed evidence: the focused publication command passes — 11 tests;
    event traces prove cleanup/reap precedes materialization, stage, and
    promotion, and promotion failure discards the private set without leaking
    candidate bytes.

- [x] T011 [tests, GREEN] Add normalized result, sealed-output, accounting, and
  redaction vectors.
  - Spec: result contract and acceptance criteria 3–5.
  - Plan: M4; Planned Contract Surface.
  - Files/components: `tests/test_multimodal_model_runner_protocol.py`,
    `tests/test_sealed_artifact_output_handles.py`,
    `tests/test_sealed_artifact_runner_admission.py`, and result/receipt owners
    in `src/dynamic_agent_runner/workflow_host/sealed_artifact_runner.py`,
    `sealed_artifact_workflow_runner.py`, `reviewed_capability_outputs.py`,
    and `reviewed_capability_publication.py`.
  - Depends on: T010d.
  - Handler prerequisite: commit `570bd953` completed the
    `sealed-artifact-output-handler-interface`; use its four-operation handler
    and `SealedArtifactPrivateTransitionResult` seam for new publication flows
    rather than the legacy service `discard` path.
  - Validation: `poetry run pytest tests/test_multimodal_model_runner_protocol.py tests/test_sealed_artifact_output_handler.py tests/test_sealed_artifact_output_handles.py tests/test_sealed_artifact_runner_admission.py -q` must fail before result shaping.
  - Evidence: RED cases cover normalized text, opaque output handles,
    aggregate token/byte/coverage scalars, byte/handle limits, worker-reaped
    attestation, foreign results, and absence of raw sensitive values in
    receipts/traces.
  - Partial evidence: protocol tests cover normalized redacted mappings,
    output-byte and output-handle ceilings, worker-reaped attestation, and
    foreign-result rejection; binding now also enforces declared output
    modalities, input coverage keys, and effective generation budgets;
    sealed-artifact service vectors remain.
  - Readiness state: complete; the Option 1 bridge and normalized-result
    vectors are green.
  - Completed evidence: focused result/handler/admission command passes — 60
    tests; vectors cover promoted opaque handles, aggregate byte mismatch,
    declaration byte ceilings, foreign results, and redacted failures.

- [x] T012 [implementation] Implement result validation and redacted receipt
  shaping through existing sealed-artifact services.
  - Spec: result contract and workflow/host authority split.
  - Plan: M4; Architecture and Data Flow.
  - Files/components: `src/dynamic_agent_runner/multimodal_model_runner.py`,
    `src/dynamic_agent_runner/workflow_host/sealed_artifact_runner.py`,
    `src/dynamic_agent_runner/workflow_host/sealed_artifact_workflow_runner.py`,
    `src/dynamic_agent_runner/workflow_host/reviewed_capability_outputs.py`,
    `src/dynamic_agent_runner/workflow_host/reviewed_capability_publication.py`,
    and package-owned error mapping.
  - Depends on: T011.
  - Validation: T011 focused command passes; `poetry run ruff check src tests`.
  - Evidence: only normalized text, permitted opaque handles, aggregate
    counters, terminal classification, and confirmed attestation are exposed;
    raw images, prompts, paths, native objects, process IDs, credentials, and
    model bytes remain private.
  - Partial evidence: `MultimodalRunnerResult.to_redacted_mapping` exposes the
    normalized receipt shape and binding validation enforces identity and
    output/modality/budget limits; the T010c publication adapter still must
    replace private multimodal handles with promoted handler handles in the
    host-owned egress tuple.
  - Readiness state: complete for the current host-owned publication seam; the
    adapter validates identity and aggregate bytes, keeps candidate bytes
    private, and returns only promoted `SealedArtifactOutputHandle` values.
  - Completed evidence: `LocalWorkflowHost.publish_multimodal_result` and the
    focused result/handler suites provide the normalized, redacted handoff;
    no raw candidate bytes or multimodal handles enter the public tuple.

- [x] T013 [tests, GREEN] Prove result transfer, redaction, and cleanup
  compatibility.
  - Spec: acceptance criteria 3–5.
  - Plan: M4 exit; Verification Matrix.
  - Files/components: `tests/test_multimodal_model_runner_protocol.py`,
    sealed-artifact output/runner tests, and existing tracing/receipt tests
    identified by T001.
  - Depends on: T012.
  - Validation: `poetry run pytest tests/test_multimodal_model_runner_protocol.py tests/test_sealed_artifact_output_handler.py tests/test_sealed_artifact_output_handles.py tests/test_sealed_artifact_runner_admission.py tests/test_sealed_artifact_workflow_runner.py -q`.
  - Evidence: normalized valid results pass; foreign/replayed results, false
    attestation, counter mismatch, and cleanup failure fail closed without
    public output handles.
  - Partial evidence: protocol and host tests cover foreign/replayed results,
    false attestation, budget/limit mismatch, cleanup failure, and completed-
    only publication gating; sealed-artifact output-handle service integration
    remains. Host publication ordering is verified with a deterministic fake
    publisher and cleanup event trace.
  - Readiness state: complete for the current Option 1 publication seam; the
    composed suite proves result transfer, redaction, cleanup, and legacy
    compatibility.
  - Completed evidence: composed multimodal, handler, sealed-runner, and
    admission suites pass — 65 tests; foreign/replayed results, false
    attestation, counter mismatch, cleanup failure, and legacy direct-service
    behavior remain green.

- [x] T014 [tests, RED] Add floorplan host-composition compatibility vectors
  for the Option 1 sealed converter-input binding.
  - Spec: initial migration target and floorplan ownership acceptance criterion.
  - Plan: M5; Current-State Anchors for the Transformers/PEFT runner and
    converter.
  - Files/components: `tests/test_transformers_peft_model.py`,
    `tests/test_qwen25_vl_3b_grpo_converter.py`, `tests/test_dar_authoring_runner.py`,
    and the floorplan host composition in
    `src/dynamic_agent_runner/workflow_host/host.py`.
  - Depends on: T013.
  - Validation: `poetry run pytest tests/test_multimodal_model_runner_protocol.py tests/test_transformers_peft_model.py tests/test_qwen25_vl_3b_grpo_converter.py tests/test_dar_authoring_runner.py -q` must fail before migration.
  - Evidence: RED cases require one receiver-created `converter_input` handle,
    exact package/revision/invocation/descriptor/material/converter binding,
    one-shot materialization to private converter-owned canonical bytes,
    sealed image handling, the existing generation budget, and workflow-owned
    JSON/SVG validation. They also reject raw prompt/message fields and prove
    no canonical payload enters a result, receipt, or trace.
  - Baseline evidence: the existing floorplan/Transformer/converter/authoring
    compatibility command passes — 146 tests — but it does not exercise a
    protocol adapter. Option 1 now supplies the missing binding without adding
    a raw prompt channel to DAR.
  - Completed evidence: RED commits `b69c11dc` and `5442cc5f` first failed on
    the absent sealed-input capability and canonical-input adapter entry point;
    the focused protocol/Transformer/converter/authoring command now passes
    with 180 tests. The vectors prove one-shot converter-input resolution,
    exact identity forwarding, private canonical payload handling, and
    workflow-owned validation boundaries.

- [x] T015 [implementation] Move the floorplan Transformers/PEFT host
  composition behind the protocol adapter using Option 1.
  - Spec: initial migration target; no domain validation in DAR.
  - Plan: M5; Scope and Boundaries.
  - Files/components: `src/dynamic_agent_runner/workflow_host/host.py`,
    `src/dynamic_agent_runner/workflow_host/transformers_peft_model.py`,
    converter fixtures, and `src/dynamic_agent_runner/multimodal_model_runner.py`.
  - Depends on: T014.
  - Validation: T014 focused command passes; `poetry run ruff check src tests`.
  - Evidence: the receiver-owned materializer resolves only the bound
    `converter_input` handle to private converter-owned canonical bytes; no
    raw prompt/message channel is introduced. No model-loading, converter,
    material, generation-budget, floorplan JSON/SVG, or publication semantics
    change; a mismatched protocol or input binding fails before model
    materialization.
  - Completed evidence: `114e1676` adds the admitted
    `TransformersPeftMultimodalRunner`; `0216b323` and `ce69bb41` route both
    eager and deferred Transformers adapters through converter-owned canonical
    input without exposing protocol messages. The protocol and Transformer
    focused suites pass with 98 tests.

- [x] T016 [tests, GREEN] Prove floorplan behavior and legacy-path
  compatibility after migration.
  - Spec: initial migration target and acceptance criterion 6.
  - Plan: M5 exit; Rejected Alternatives.
  - Files/components: floorplan, converter, local-runner, and text-adapter
    focused tests from T014 plus `tests/test_local_model_runners.py`.
  - Depends on: T015.
  - Validation: `poetry run pytest tests/test_transformers_peft_model.py tests/test_qwen25_vl_3b_grpo_converter.py tests/test_dar_authoring_runner.py tests/test_local_model_runners.py -q`.
  - Evidence: the floorplan workflow retains its domain validation/publication
    ownership and existing local/text paths remain green. The protocol path
    uses exactly one sealed `converter_input` handle and does not expose its
    canonical payload.
  - Completed evidence: the migration command passes with 162 tests across
    Transformer, converter, authoring, and local-runner coverage; the concrete
    converter decoder is covered by `test_qwen_converter_decodes_its_private_canonical_input`.

- [x] T017 [validation] Run the complete compatibility gate and record
  acceptance evidence.
  - Spec: all acceptance criteria.
  - Plan: M6; Verification Matrix; Risks and Mitigations.
  - Files/components: all changed source/tests plus
    `specs/multimodal-model-runner-protocol/validation.md`.
  - Depends on: T004, T007, T010d, T013, and T016.
  - Validation: run the exact focused commands in `plan.md`, perform the
    static inspection checklist below, then
    `poetry run pytest -q`, `poetry run ruff check src tests`, `poetry build`,
    and `git diff --check`.
  - Evidence: every acceptance criterion maps to passing deterministic
    fake-runner evidence; no unit test uses a live model, provider, network, or
    external tool; validation records only redacted receipts and residual
    risks. Static inspection records that touched code has no package-selected
    paths, credentials, native runtime objects, unredacted traces/receipts,
    fallback provider selection, or domain validation in DAR.
  - Completed evidence: the focused Option 1 migration gate, full repository
    suite (`2813 passed, 1 skipped, 7 deselected`), Ruff, `poetry build`, and
    `git diff --check` all pass. Static review confirms that the protocol path
    has no package-selected paths, credentials, native runtime objects,
    unredacted traces/receipts, fallback provider selection, or workflow-domain
    validation in DAR.

## Checkpoints

- M1 complete after T004: contract values, canonical vectors, lifecycle/error
  invariants, and public/private boundary tests are green.
- M2 complete after T007: one exact receiver-admitted runner resolves and all
  admission drift fails before materialization or worker creation.
- M3 complete after T010: valid requests dispatch once; every invalid or
  terminal path is bounded, redacted, and reaped.
- M4 complete after T013: normalized results and sealed output handles are
  identity-bound and free of raw sensitive data.
- M5 complete after T016: floorplan composition migrates without changing
  converter/material/domain behavior or legacy paths.
- M6 complete after T017: full regression, lint, build, diff checks, and
  validation traceability are green.

## Validation

### T017 static inspection checklist

- `rg -n "Path|credential|prompt|process_id|native|provider|fallback|SVG|JSON"`
  over changed runtime files, followed by manual review of each match, shows
  no forbidden boundary value crossing into the protocol or receipt.
- `git diff --name-only` is reconciled against the task-owned source/test/docs
  paths; unrelated changes are excluded from the validation claim.
- `codegraph explore` on the final protocol entry point confirms all dispatch
  paths pass through admission, budget, lifecycle, redaction, and result
  shaping before the runner handler.

- `poetry run pytest tests/test_multimodal_model_runner_protocol.py -q` —
  protocol contract, admission, lifecycle, and result conformance.
- `poetry run pytest tests/test_local_model_runners.py tests/test_generation_worker.py tests/test_workflow_model_material_admission.py -q` —
  existing runner, worker, and material regressions.
- `poetry run pytest tests/test_transformers_peft_model.py tests/test_qwen25_vl_3b_grpo_converter.py tests/test_dar_authoring_runner.py -q` —
  floorplan migration and workflow ownership.
- `poetry run pytest -q` — repository regression gate.
- `poetry run ruff check src tests` — source/test lint gate.
- `poetry build` — package gate.
- `git diff --check` — whitespace/diff gate.

## Domain and Boundary Notes

- Domain assumptions verified: the floorplan workflow owns prompts, JSON/SVG
  validation, and publication; DAR owns generic sealed execution and result
  shaping.
- Bounded-context checks: provider/runtime translation stays inside the
  receiver-installed runner; material preparation stays with the existing
  material admission contract; workflow-domain artifacts do not enter DAR's
  protocol core.
- Security boundary: no task may introduce package-selected paths,
  credentials, native runtime objects, arbitrary material roots, fallback
  providers, or unredacted traces/receipts.

## Task Approval

- Status: approved
- Notes: The user approved the spec and plan. Council's system-design triad
  and Ponytail review found the task chain ready for implementation after the
  durable T001 route table and T017 static-inspection checklist were added.
