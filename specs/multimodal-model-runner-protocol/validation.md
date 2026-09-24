# DAR Multimodal Model Runner Protocol Validation

Status: historical review — superseded by explicit spec approval; implementation
not started

The earlier Council/Ponytail review recorded the gaps that the approved plan
must close. Its findings remain implementation risks and are not a rejection
of the user's subsequent approval of `spec.md`.

## Plan readiness review

The amended `plan.md` was reviewed against the approved spec and current
repository seams.

### Council deliberation

The `system-design` triad (Ada, Feynman, Torvalds) ran three independent
passes followed by a challenge round. The triad agreed that the original
milestone order was sound but the handoff was not ready because it lacked
concrete source/test anchors, normative wire/state/error vectors, runnable
focused commands, and a separate floorplan migration gate.

The amended plan addresses those blockers by adding:

- a current-state anchor table naming the existing owners and focused tests;
- canonical JSON/digest, identity, handle-linearity, terminal-state,
  cleanup-ordering, attestation, and result-transfer rules;
- exact planned focused pytest commands; and
- a separate M5 floorplan migration after M1–M4 protocol conformance.

Council conclusion: **approved for task-list authoring**, contingent on M1
freezing the listed normative vectors before implementation.

### Ponytail review

Full Ponytail found no approved requirement to delete. It required the same
three simplifications now recorded in the plan: isolate floorplan migration,
remove placeholder commands, and reuse existing digest/catalog/worker/material/
reviewed-host seams instead of adding parallel infrastructure.

Ponytail conclusion: **lean enough to proceed** after those amendments.

## Task readiness review

The approved `tasks.md` was reviewed against the approved plan and spec.

### Council deliberation

The `system-design` triad (Ada, Feynman, Torvalds) ran independent passes and
a challenge round. The task chain was found dependency-correct and complete
across M1–M6, with two required handoff amendments:

- T001 now owns a durable Discovery Route Table in `tasks.md`, naming source
  symbols, focused tests, and the first guarded side effect for each milestone.
- T017 now includes a static-inspection checklist for forbidden paths,
  credentials, native objects, unredacted receipts/traces, fallback providers,
  and domain validation in DAR.

The review also clarified that T004 proves value-level contract invariants,
while T010 proves integrated worker cleanup/reap behavior, and replaced
conditional source-owner placeholders with concrete repository paths.

Council conclusion: **approved for implementation handoff**.

### Ponytail review

Full Ponytail found no task that should be deleted. The list reuses the
existing catalog, material, worker, sealed-artifact, and reviewed-host seams;
it adds no second registry, scheduler, provider abstraction, or lifecycle
coordinator. The T001 route table and T017 static checklist are the minimum
evidence needed to avoid speculative architecture during implementation.

Ponytail conclusion: **lean enough to execute**.

## Execution evidence

### M1 — contract and canonical identity slice

| Task | Command | Result |
| --- | --- | --- |
| T001 | `codegraph explore` over the route-table owners | pass — confirmed digest, catalog, material, worker, host, and Transformers symbols and focused tests |
| T002 | `poetry run pytest tests/test_multimodal_model_runner_protocol.py -q` before implementation | expected RED — module import failed because the protocol module did not yet exist |
| T003/T004 | `poetry run pytest tests/test_multimodal_model_runner_protocol.py -q` | pass: 12 tests |
| T003/T004 | `poetry run ruff check src/dynamic_agent_runner/multimodal_model_runner.py tests/test_multimodal_model_runner_protocol.py` | pass |
| T005/T006/T007 | `poetry run pytest tests/test_multimodal_model_runner_protocol.py tests/test_local_model_runners.py tests/test_workflow_model_material_admission.py tests/test_dar_authoring_host.py -q` | pass: 56 tests; exact catalog admission, host composition, drift refusal, and zero dispatch evidence |
| T005/T006/T007 | `poetry run ruff check src/dynamic_agent_runner/multimodal_model_runner.py src/dynamic_agent_runner/workflow_host/local_model_runners.py src/dynamic_agent_runner/workflow_host/host.py tests/test_multimodal_model_runner_protocol.py` | pass |
| T010 | `poetry run pytest tests/test_multimodal_model_runner_protocol.py tests/test_generation_worker.py tests/test_generation_worker_controllers.py -q` | pass: 103 tests; bounded lifecycle and cleanup matrix |
| T011 | `poetry run pytest tests/test_multimodal_model_runner_protocol.py tests/test_sealed_artifact_output_handles.py tests/test_sealed_artifact_runner_admission.py -q` | pass: 39 protocol/sealed-service tests; composed multimodal-to-handler publication was not exercised |
| T013 | `poetry run pytest tests/test_multimodal_model_runner_protocol.py tests/test_sealed_artifact_output_handles.py tests/test_sealed_artifact_runner_admission.py tests/test_sealed_artifact_workflow_runner.py -q` | pass: 44 protocol/sealed-service tests; composed handler transfer remains open |
| Floorplan baseline | `poetry run pytest tests/test_transformers_peft_model.py tests/test_qwen25_vl_3b_grpo_converter.py tests/test_dar_authoring_runner.py tests/test_local_model_runners.py -q` | pass: 160 tests; pre-migration floorplan and legacy compatibility baseline |
| Regression | `poetry run pytest -q` | pass: 2787 passed, 1 skipped, 7 deselected |
| Package | `poetry run ruff check src tests`; `poetry build`; `git diff --check` | pass |
| Static boundary review | `rg -n "Path|credential|prompt|process_id|native|provider|fallback|SVG|JSON"` over changed runtime owners | reviewed: matches are pre-existing host/workflow concerns or private provider-boundary labels; no raw value is added to protocol mappings or receipts |
| Contract hardening | `poetry run pytest tests/test_multimodal_model_runner_protocol.py -q` | pass: 21 tests; path-like invocation identifiers rejected at the sealed boundary |

The implementation now includes receiver-owned catalog registration and host
composition for one exact runner, plus protocol-level replay and foreign-result
guards. The binding now sequences input clearing, reservation release, and
worker reap before returning a normalized result and fails closed on cleanup
errors. Pre-dispatch cancellation and deadline gates return redacted terminal
results without runner calls. Direct generation-worker controller integration, sealed-output
publication is exposed through a completed-only host callback, and floorplan
migration remain pending later tasks.

## Historical proposal review (superseded)

### Review scope

This review covered `spec.md` and the existing host boundaries it names:

- `specs/local-model-runner-interface/spec.md`
- `specs/workflow-input-converter-plugin/spec.md`
- `specs/model-generation-resource-budgets/spec.md`
- `src/dynamic_agent_runner/workflow_host/local_model_runners.py`
- `src/dynamic_agent_runner/workflow_host/model_material_admission.py`

No runtime implementation, plan, task breakdown, or feature-specific test
artifact exists for this protocol. The repository's existing floorplan path is
already covered by the local-runner, sealed-material, converter, and
generation-budget contracts; no second protocol was inferred from that path.

### Council deliberation

#### Composition

The repository `system-design` triad was selected from the Council panel
metadata: Ada (formal systems), Feynman (first-principles verification), and
Torvalds (pragmatic engineering).

#### Execution mode

Three independent first-pass reviews were run in parallel, followed by a
challenge round. This is the standard independent-analysis plus
challenge/response mode, not a reduced-independence fallback.

#### Consensus

The triad agreed that the boundary ownership and non-goals are directionally
sound, but the proposal is not implementation-ready. The blocking omissions
are:

- normative fields and invariants for the descriptor, sealed request, context,
  health, result, limits, and cleanup attestation;
- canonical serialization, digest, identity, handle lifetime, and
  non-transferability rules;
- an admission/lifecycle state machine with ordering before worker creation and
  sealed-input ingress;
- terminal error classifications for rejection, cancellation, deadline,
  worker failure, and cleanup failure; and
- a deterministic plan/tasks/validation mapping with fake-runner conformance
  tests, including positive and negative digest/binding vectors.

The Council would accept references instead of duplicated schemas only if this
spec adds a field-level normative dependency matrix (source, version, and
binding rule) plus executable composed-contract tests.

### Ponytail review

Full Ponytail review found no need to add runtime code in this slice. The
existing local-model-runner and generation-budget seams already cover the
initial floorplan implementation target. Adding an unimplemented generic
protocol now would duplicate lifecycle and material authority before a second
concrete runner requires it.

The smallest viable next slice is documentation-only: freeze the wire
contracts/state machine, name normative dependencies, and add an implementation
plan with focused fake-runner tests. Defer protocol code, provider abstraction,
streaming, sessions, downloads, and broad registry work until a concrete second
runner needs the seam.

### Historical readiness decision

**Superseded.** The original review found the proposal not ready for
implementation. The user subsequently approved `spec.md`; the amended
`plan.md` now carries the contract/state/command gates required for task-list
authoring.

### Historical verification

- The original `rg` check found no implementation of
  `DARMultimodalModelRunnerProtocol` or its wire types in `src/` or `tests/`.
- Existing adjacent specifications define reusable host machinery but do not
  define this protocol's wire schemas or error contract.
- No live model, provider, network, or external tool call was made.

## Current task-list readiness review

This review was rerun after commit `570bd953` completed the sealed-artifact
output handler.

### Council deliberation

Ada, Feynman, and Torvalds agreed that the handler dependency is now available
and that T008/T009 evidence should be marked complete. They found the task
artifact not ready for final handoff because T010a has not yet frozen the
multimodal-result-to-sealed-output bridge, T011–T013 still lack composed
multimodal-to-sealed-output tests, and T014–T016 still lack the floorplan
migration and compatibility evidence. The stale T010 dependency state and the
old 2780-test count were corrected in `tasks.md`.

Council conclusion: **not yet ready; continue with M4/M5 implementation gates**.

### Ponytail review

Ponytail review found no task to delete. The smallest continuation is to use
the completed four-operation handler and its private transition seam in M4,
then perform one narrow floorplan host-composition migration. No second
publication registry, provider abstraction, or worker lifecycle authority is
needed.

Ponytail conclusion: **lean enough to continue, not yet ready to close**.

### Current evidence

- T008/T009 are now marked complete with focused lifecycle/cleanup evidence.
- Repository regression is currently **2800 passed, 1 skipped, 7 deselected**;
  Ruff and `git diff --check` pass.
- T010a–T013 and T014–T016 remain open; no readiness claim is made until the
  bridge contract is explicit, their focused tests and migration evidence pass,
  and the final package/static validation gate passes.
