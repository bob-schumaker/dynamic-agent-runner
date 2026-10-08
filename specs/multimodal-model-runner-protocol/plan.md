# DAR Multimodal Model Runner Protocol Implementation Plan

Status: Implemented; validation recorded in `validation.md`

## Spec Trace

- Spec: `specs/multimodal-model-runner-protocol/spec.md`
- Related contracts:
  - `specs/local-model-runner-interface/spec.md`
  - `specs/workflow-input-converter-plugin/spec.md`
  - `specs/workflow-model-materials/spec.md`
  - `specs/model-generation-resource-budgets/spec.md`
  - `specs/sealed-artifact-workflow-runner/spec.md`
- Component disposition: single coherent host-boundary component. The
  protocol owns one admission and lifecycle seam; material preparation,
  generation containment, and workflow validation remain existing or
  caller-owned components.

## Goal

Deliver `DARMultimodalModelRunnerProtocol` v1 as a receiver-admitted,
sealed-artifact host extension. A valid invocation must reach exactly one
admitted runner with opaque inputs, bounded generation context, normalized
redacted results, and confirmed cleanup. Invalid identity, material,
converter, ABI, output-contract, resource, package, or revision facts must
fail before worker creation or sealed-input ingress.

## Current State

- `LocalModelRunnerCatalog` already performs exact runner registration and
  worker-binding checks.
- `ModelMaterialAdmission` already materializes verified artifacts for an
  exact lock and preparation-provider binding.
- `generation-worker-v1` already provides private pack/authorize/result
  transcripts, aggregate accounting, and worker lifecycle primitives.
- Reviewed host extensions already reuse the approval ledger, private state,
  sealed output handles, and publication/recovery coordinators.
- The floorplan Transformers/PEFT runner and its input converter are covered by
  existing local-runner, material, converter, and generation-budget contracts.
  This plan moves host composition behind the new protocol; it does not create
  a second implementation of those responsibilities.

## Current-State Anchors

| Concern | Existing owner | Planned change | Focused evidence |
| --- | --- | --- | --- |
| Canonical descriptor digests | `src/dynamic_agent_runner/external_adapter.py` (`canonical_descriptor_digest`) and workflow-host canonical JSON helpers | Reuse the established sorted-key, compact-JSON, UTF-8 SHA-256 convention; do not invent a second digest format. | `tests/test_external_adapter_protocol.py` plus new protocol contract tests |
| Runner registration and worker binding | `src/dynamic_agent_runner/workflow_host/local_model_runners.py` (`LocalModelRunnerCatalog`) | Add the multimodal protocol adapter at the existing catalog/host boundary; preserve reserved IDs and worker binding checks. | `tests/test_local_model_runners.py` plus new admission tests |
| Material identity and preparation | `src/dynamic_agent_runner/workflow_host/model_material_admission.py` and `model_materials.py` | Bind the exact material-lock and preparation-provider digests into the request identity; do not duplicate material loading. | `tests/test_workflow_model_material_admission.py` and new binding vectors |
| Bounded lifecycle and accounting | `src/dynamic_agent_runner/workflow_host/generation_worker.py` (`GenerationWorkerSession`, `GenerationWorkerResult`) | Adapt the protocol context/result to the existing worker transcript and reap contract. | `tests/test_generation_worker.py` plus new lifecycle vectors |
| Reviewed host composition | `src/dynamic_agent_runner/workflow_host/reviewed_capability_host_extension.py` and `host.py` | Reuse receiver admission, private state, redaction, and sealed-output seams; do not create a second coordinator or registry. | `tests/test_dar_authoring_host.py` and reviewed-capability execution tests |
| Floorplan runner and converter | `src/dynamic_agent_runner/workflow_host/transformers_peft_model.py` and converter fixtures | Migrate composition only after protocol conformance passes; keep workflow JSON/SVG validation outside DAR. | `tests/test_transformers_peft_model.py`, converter tests, and floorplan runner tests |

The first task must confirm these anchors and record any symbol-level changes
before implementation. A new protocol module is expected at
`src/dynamic_agent_runner/multimodal_model_runner.py` with focused coverage in
`tests/test_multimodal_model_runner_protocol.py`; if discovery finds a nearer
existing owner, the task record must explain the substitution rather than add a
parallel abstraction.

## Scope and Boundaries

### In scope

1. Frozen v1 protocol values and canonical wire contracts for descriptor,
   health, request, context, result, sealed handles, limits, attestation, and
   terminal error classifications.
2. Exact receiver admission and installation binding for
   `dar.multimodal-runner.v1`.
3. Host-owned request staging, identity revalidation, approval/lifecycle
   coordination, generation-budget binding, result shaping, and cleanup.
4. Migration of the existing prepared Transformers/PEFT floorplan composition
   to the protocol without changing its material or converter contracts.
5. Deterministic fake-runner tests and redacted validation evidence.

### Out of scope

- Changes to `DARExternalAdapterProtocol` or its registry.
- A generic provider SDK abstraction, model download/discovery, or fallback
  provider selection.
- Workflow-owned prompts, JSON/SVG/image validators, or publication policy.
- Streaming, persistent sessions, multi-runner fan-out, or a model scheduler.
- Arbitrary package-supplied code, paths, credentials, native runtime objects,
  or host-policy overrides.

## Architecture and Data Flow

1. The receiver registers one immutable runner descriptor and verifies its
   protocol ID/version, contract digest, material-lock, execution ABI,
   converter, modality, output-contract, and resource bindings.
2. Package admission binds the exact descriptor and package/revision identity;
   runtime revalidates the same tuple immediately before dispatch.
3. Host-owned staging resolves receiver-created sealed handles and logical
   roles. For multimodal packing, the workflow supplies a converter-owned
   canonical payload through one `converter_input` handle; the receiver's
   input materializer resolves it privately after binding checks. Raw paths,
   credentials, prompts/messages, native objects, and model bytes stay
   private to the receiver/worker.
4. The existing generation-budget resolver and `generation-worker-v1` (or a
   reviewed cancellation-capable runner) contain packing, loading, generation,
   deadline, memory, cancellation, and reap behavior.
5. The admitted runner translates sealed logical inputs to its provider call and
   returns only the frozen normalized result shape.
6. DAR validates aggregate counters and attestation, redacts terminal output,
   publishes only permitted opaque sealed artifacts, records cleanup/reap, and
   hands domain validation back to the floorplan workflow.

## Planned Contract Surface

The v1 contract module must define immutable, runtime-validated values for:

- `MultimodalRunnerDescriptor`: runner/protocol identity, provider-runtime
  label, material-lock and execution-ABI digests, modality set, converter and
  output-contract digests, canonical resource limits, and contract digest.
- `MultimodalRunnerHealth`: bounded, redacted readiness state with no material
  loading or private locator disclosure.
- `SealedMultimodalRequest`: receiver-created opaque handles, logical roles
  including the one-shot `converter_input` role when packed input is needed,
  package/revision/invocation bindings, and no raw material, prompt/message, or
  runtime objects.
- `SealedMultimodalInputMaterializer`: receiver-owned capability that resolves
  a bound `converter_input` handle to private converter-owned canonical bytes;
  it returns no path, native object, or workflow-visible value.
- `DARGenerationRequestContext`: effective budget, deadline/cancellation
  bindings, selected execution device, and private invocation identity.
- `MultimodalRunnerResult`: normalized text or sealed output handles, aggregate
  token/byte/coverage counters, terminal classification, and worker-reaped
  attestation.
- Canonical serialization/digest helpers, handle lifetime/linearity rules,
  finite terminal errors, and redacted receipt mappings.

Any field delegated to an existing specification must have an explicit
field-level dependency and binding rule; no implementation may reconstruct the
wire contract from prose across unrelated documents.

## Normative Encoding and Lifecycle Invariants

These are implementation-plan decisions that make the approved acceptance
criteria executable. M1 must freeze them in the contract module and test
vectors.

| Surface | Normative rule |
| --- | --- |
| Canonical bytes | Encode a closed mapping as UTF-8 JSON with `ensure_ascii=True`, `sort_keys=True`, and compact separators `(',', ':')`; arrays are already canonicalized by the owning value. |
| Digest | SHA-256 of canonical bytes, rendered as exactly 64 lowercase hexadecimal characters; a declared digest is accepted only when it equals the recomputed digest. |
| Identity tuple | `(protocol_id, protocol_version, runner_id, contract_digest, material_lock_digest, execution_abi_digest, converter_digest, output_contract_digest, package_id, package_revision_digest, invocation_id)`; any change invalidates admission or a pending dispatch. |
| Input-handle linearity | A receiver-created input handle is bound to one invocation and logical role, consumed at most once, cleared on every terminal path, and never serialized into a workflow-visible result. The `converter_input` handle additionally binds the descriptor, material lock, converter digest, issuer, and expiry. |
| Terminal states | `rejected` (pre-worker), `completed`, `budget_exhausted`, `cancelled`, `deadline_exceeded`, `runner_failed`, and `cleanup_failed`; only `completed` may publish an output handle. |
| Cleanup ordering | A terminal result is constructed only after private input clearing, reservation release, worker terminate/kill as needed, and confirmed reap. Cleanup failure produces `cleanup_failed`, no output handle, and a redacted receipt. |
| Attestation | `worker_reaped` is true only after the existing worker controller confirms reap; a missing, false, or foreign attestation rejects the result. Aggregate token/byte counters must equal the host-side recomputation. |
| Result transfer | Every output handle and aggregate receipt binds the same package/revision, material, converter, and contract identity as the request; foreign or replayed results are rejected. |

The finite error values are package-owned and redacted: `admission_rejected`,
`budget_exhausted`, `cancelled`, `deadline_exceeded`, `runner_failed`, and
`cleanup_failed`. Vendor exception text, paths, prompts, credentials, process
IDs, and native response objects never appear in these values.

## Delivery Milestones

### M1 — Freeze contracts and canonical identity

Dependencies: none.

Touch points: new protocol contract module under
`src/dynamic_agent_runner/`, existing digest/validation helpers, and
`tests/` protocol-contract coverage.

1. Write RED tests for every descriptor/request/context/health/result field,
   closed mappings, type/range/grammar constraints, canonical serialization,
   digest vectors, protocol/version mismatch, and forbidden raw values.
2. Implement the smallest immutable contract values and package-owned errors;
   reuse existing digest and redaction conventions.
3. Add negative vectors for changed package/revision, material lock, converter,
   ABI, output contract, resource limit, handle issuer, and modality facts.

Exit: two independent implementations cannot interpret the v1 wire values,
identity tuple, or terminal classifications differently.

### M2 — Register and admit one exact runner

Dependencies: M1.

Touch points: reviewed host-extension registration/control-plane modules,
`workflow_host/host.py`, runner catalog integration, and focused host tests.

1. Write RED fake-runner tests for install, reload, duplicate/reserved IDs,
   malformed descriptors, health without material load, exact descriptor
   resolution, and package-admission refusal.
2. Add receiver-owned registration and exact lookup for the new protocol;
   preserve the existing external-adapter and local-runner paths.
3. Bind material-lock, execution ABI, converter, output-contract, resource,
   extension, and dependency identities before request ingress.

Exit: only one currently admitted descriptor can resolve, and all mismatches
fail closed without loading material or creating a worker.

### M3 — Stage sealed requests and enforce lifecycle

Dependencies: M1, M2; reuse `generation-worker-v1` and the existing approval/
state seams.

1. Write RED tests for opaque-handle role binding, package/revision
   non-transferability, one-runner dispatch, budget exhaustion, cancellation,
   deadline, worker failure, malformed result, and confirmed reap.
2. Add the host-owned request/context adapter. It must resolve only
   receiver-created handles and pass no workflow-supplied native objects.
3. Revalidate authoritative bindings immediately before dispatch and reject
   drift without fallback, retry, sealed-input ingress, or output allocation.
4. Map runner and worker outcomes to the finite package-owned terminal errors;
   release private inputs and reservations only after cleanup/reap confirmation.

Exit: every invalid or replayed request has zero runner dispatches and no
public output handle; every valid request has one bounded dispatch.

### M4 — Normalize results and preserve workflow ownership

Dependencies: M3.

Touch points: result/receipt shaping, sealed-artifact output services, and
tracing.

1. Write RED tests for text and sealed-artifact results, aggregate accounting,
   coverage scalars, worker-reaped attestation, byte/handle limits, redaction,
   and foreign result rejection.
2. Implement result validation and normalized receipt shaping using existing
   sealed-artifact and redaction paths. Raw images, prompts, paths, native
   responses, process IDs, credentials, and model bytes must never enter
   receipts or workflow-visible results.
Exit: protocol results are normalized, redacted, identity-bound, and cleanup
attested without changing any floorplan composition.

### M5 — Migrate the floorplan host composition

Dependencies: M1–M4.

Touch points: `src/dynamic_agent_runner/workflow_host/transformers_peft_model.py`,
the floorplan host composition in `workflow_host/host.py`, existing converter
fixtures, and their focused tests.

1. Write RED compatibility tests proving the existing prepared
   Transformers/PEFT runner enters through the protocol adapter with one
   bound `converter_input` handle and the same material lock, converter digest,
   generation budget, and workflow-owned output validation. Include negative
   vectors for raw prompt/message fields and mismatched input bindings.
2. Move only host composition behind the protocol. Resolve the sealed,
   converter-owned canonical payload through the receiver materializer; do not
   change model loading, converter semantics, floorplan JSON/SVG validation,
   or publication policy.
3. Prove legacy local-runner and text-adapter paths remain unchanged and that a
   mismatched protocol or converter-input identity fails before model
   materialization.

Exit: the floorplan path uses the protocol without changing its domain output
or sealed-material behavior; protocol conformance remains independently green.

### M6 — Compatibility and validation gate

Dependencies: M1–M5.

1. Run focused protocol, registry, material, converter, generation-worker,
   floorplan, and reviewed-host tests with only fake runners and controlled
   collaborators.
2. Run the repository suite, Ruff, package build, and `git diff --check`.
3. Verify legacy text adapters, ordinary local runners, and workflow-owned
   validators are unchanged except for the deliberate host-composition seam.
4. Record acceptance-criterion evidence and residual risks in
   `specs/multimodal-model-runner-protocol/validation.md`; do not record live
   model/provider/network calls as unit-test evidence.

Exit: all acceptance criteria in `spec.md` map to passing deterministic tests,
compatibility gates are green, and the validation artifact contains no raw
model, prompt, path, credential, process, or worker-handle data.

## Verification Matrix

| Spec requirement | Verification | Command / evidence |
| --- | --- | --- |
| Exact descriptor and request admission | Contract, registry, and negative binding tests | `poetry run pytest tests/test_multimodal_model_runner_protocol.py tests/test_local_model_runners.py -q` |
| No raw paths/material/runtime objects | Request-shape, trace, and receipt redaction tests | `poetry run pytest tests/test_multimodal_model_runner_protocol.py -q -k 'redact or opaque or forbidden'` |
| One admitted runner and bounded lifecycle | Fake dispatch, budget, cancellation, deadline, failure, and reap tests | `poetry run pytest tests/test_multimodal_model_runner_protocol.py tests/test_generation_worker.py -q` |
| Non-transferable package/revision/material results | Changed-identity and foreign-result vectors | `poetry run pytest tests/test_multimodal_model_runner_protocol.py tests/test_workflow_model_material_admission.py -q` |
| Floorplan ownership boundary | Existing floorplan fixture, converter, and runner tests | `poetry run pytest tests/test_transformers_peft_model.py tests/test_qwen25_vl_3b_grpo_converter.py tests/test_dar_authoring_runner.py -q` |
| Repository compatibility | Full regression, lint, build, diff check | `poetry run pytest -q`; `poetry run ruff check src tests`; `poetry build`; `git diff --check` |

## Risks and Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Duplicate lifecycle semantics with existing generation workers | Divergent cleanup or budget behavior | Reuse `generation-worker-v1`; add only a protocol adapter and contract validation. |
| Cross-document contract drift | Different hosts accept different wire values | Freeze field-level dependencies, canonical digests, and test vectors in M1. |
| Leakage through receipts/traces | Sensitive prompt/material/runtime data escapes the boundary | Centralize result shaping and assert redaction on every terminal path. |
| Floorplan migration widens domain scope | DAR starts owning SVG/JSON semantics | Keep validators and publication in the workflow; test the ownership boundary. |
| Protocol is implemented before a second concrete runner needs it | Unused abstraction and maintenance cost | Keep v1 narrow; do not add streaming, sessions, provider abstraction, or discovery. |

## Rejected Alternatives

- Widen `DARExternalAdapterProtocol`: rejected because multimodal sealed
  materials, converter identity, lifecycle, and artifact results are not a
  text-only adapter contract.
- Replace the existing local-runner and generation-worker systems: rejected;
  the protocol must compose their reviewed boundaries.
- Let packages provide paths, native objects, providers, or material roots:
  rejected because receiver admission and sealed artifacts are the trust
  boundary.
- Add workflow-domain image/SVG/JSON validation to DAR: rejected because the
  workflow owns those semantics.

## Ponytail Scope Decision

The full Ponytail review found three actionable simplifications:

- M1–M4 must not also carry floorplan migration; that work is isolated in M5.
- Placeholder focused-test commands are replaced with exact planned test paths
  and selectors in the verification matrix.
- New protocol code must reuse the existing digest, runner catalog, worker,
  material, and reviewed-host seams; no second registry, scheduler, or provider
  abstraction is authorized.

No approved protocol requirement was deleted. Generalized modality and
receiver-runner support remain contract-level v1 behavior; only the first
implementation/migration gate is staged around the concrete floorplan runner.

## Plan Approval

- Status: approved
- Notes: The user approved `spec.md`. Council's system-design triad and the
  full Ponytail review accepted this amended plan for task-list authoring,
  contingent on M1 freezing the normative vectors above before implementation.
