<!-- rumdl-disable MD013 -->

# Reviewed Vector-Index Host Extension Implementation Plan

## Status

In-progress implementation plan derived from `spec.md`. The reviewed contract
is the entry criterion; T001 established the exact test-fixture shape. The plan
does not authorize an MLX, vault, index, or publication implementation.

## Goal

Provide DAR primitives that let a deployment host register an exact reviewed
`vector_index.build.v1` template and execute one approval-gated,
host-created `sealed:vector-index-job` per workflow run. DAR must own generic
separate host-template discovery, admission, approval/action consumption,
sealed artifact retention, and recoverable completion; the host extension must
retain all corpus, model, index, and publication authority.

## Delivery Rules

- Every slice begins with focused fake-only RED tests, then the smallest GREEN
  implementation and focused regression run.
- Reuse the existing capability catalog, action ledger, approved-tool
  coordination, sealed-artifact, and private-state seams. Do not introduce a
  second coordinator, plugin manager, index runtime, or model registry.
- No test invokes MLX, downloads material, accesses a real vault, calls a
  network service, starts a vector database, or writes a real published index.
- A package never supplies source data, prior generation, profile, model,
  provider, retry controls, destination, or publication policy. Test doubles
  construct jobs and extensions entirely in memory or a temporary private
  state root.
- Preserve existing capability requirements, reviewed artifact tools, and
  embedding-index artifact behavior. This work adds a reviewed host-template
  path; it must not reinterpret legacy package contracts.
- No implementation slice exposes a candidate handle, manifest, coverage
  report, receipt, or success result before the completion state is durable.

## Current-State Anchors

| Concern | Current owner | Planned change |
| --- | --- | --- |
| Exact DAR capability contracts | `workflow_host/capabilities.py` | Add host-reviewed template identity/discovery values without changing ordinary capability-provider selection. |
| Reviewed host bindings and discovery API | `workflow_host/reviewed_tool_packages.py` | Reuse durable host-owned binding records for template registration and expose the separate authoring discovery API; do not overload package allowlists with index semantics. |
| Authoring contract | External authoring client, descriptor/parser, and `workflow_host/workflow_authoring_registration.py` boundary | The client calls the host API before package output and binds the returned exact version/digest; do not inject vector-template behavior into `WorkflowAuthoringHost`. |
| Policy/admission | `workflow_host/policy.py`, registration, preflight, and `workflow_host/host.py` | Bind and revalidate the template identity before ingress, execution, or output allocation. |
| Approval and idempotency | `workflow_host/authorized_tools.py` and `workflow_host/action_ledger.py` | Bind the one-time approval tuple, one-call-per-run budget, one-job reservation, and recovery state. |
| Sealed input/output artifacts | `workflow_host/sealed_artifact_preparation.py`, `workflow_host/sealed_artifact_runner.py`, and artifact services | Add generic staged candidate retention and atomic public-handle promotion without parsing index bytes. |
| Existing index precedent | `workflow_host/embedding_index_artifacts.py` and `embedding_sealed_artifact_callback.py` | Preserve as a concrete legacy contract; use it only for regression and provenance/receipt precedent. |

## Design Decisions

1. A reviewed template is distinct from a capability provider. The template is
   a host-owned, immutable registration record containing the exact capability
   ID, version, digest, closed input/output contract, success-receipt schema
   digest, receipt bounds, finite failure classifications, approval
   classification, mandatory dependency declaration, recovery operations, and
   extension binding. Provider selection remains DAR-private.
2. Before writing a package, an authoring client calls a separate host
   template-discovery API for `vector_index.build.v1`. It returns one exact
   available identity and its closed declaration contract, or a stable
   unavailable/ambiguous result. It creates neither a package nor a job and
   grants no approval or dispatch authority. The selected identity is bound
   into package policy. Runtime never chooses among multiple templates, and
   package admission and execution admission revalidate the discovery result.
3. The vector-index job is a host-created sealed envelope. Its opaque handle is
   the package's only argument. Job revision/digest, issuer, principal, expiry,
   template identity, extension binding, sealed members, and embedding binding
   remain private admission facts.
4. The existing DAR action ledger is extended, not replaced. A new durable,
   single-store reservation record atomically consumes the approval tuple,
   one-call-per-run budget, and job reservation before dispatch. Its identity
   includes the run, package registration and revision, call site, template
   identity, job issuer and opaque ID, job revision and digest, principal, and
   approval nonce. It supplies replay lookup and is the recovery idempotency
   key; recoverable attempt resumption is introduced only with the completion
   state machine in S4.
5. Candidate outputs progress through `prepared`, `commit_intent`,
   `host_pending`, `dar_promoted`, `host_visible`, and `completed`. Public
   handles and the published receipt exist only at `completed`. Nonterminal
   recovery uses the same idempotency key and either completes or compensates;
   a host that cannot provide reversible pending publication cannot register
   this template.
6. Output byte/media/retention limits, a closed receipt-schema digest,
   generation/handle byte limits, a count ceiling, and stable failure
   classifications are template data. The referenced schema defines the closed
   receipt structure and identifier grammars. DAR enforces the generic limits;
   it does not inspect index bytes. The manifest may hold safe canonical
   provenance and digest bindings; coverage is aggregate-only.

## Delivery Order

### S1 — Reviewed template contracts and host registry

1. Add RED tests for immutable template canonicalization, digest validation,
   one/multiple/zero registry matches, disabled registrations, exact
   `{job_handle}` input schema, `vector_index.build.v1`'s required output
   triple, per-role media/byte/retention limits, maximum receipt size, bounded
   handle/generation-ID grammars, count ceiling, closed receipt schema, stable
   classifications, required `embedding.execute.v1` dependency/binding, and
   required reversible pending-publication/idempotent-recovery operations.
2. Add narrow immutable template and registry-resolution values adjacent to the current
   capability/host-binding primitives. Persist template registration in the
   existing private state store and verify its current host binding, closed
   input contract, mandatory dependency declaration, and recovery capability
   on every resolution; reject an extension that cannot meet this template's
   pending-publication and recovery contract.
3. Keep `vector_index.build.v1` template-specific rules out of ordinary
   capability-provider catalog semantics.

Exit: a host can register and resolve exactly one reviewed template candidate
identity without loading a package, job, embedding material, or extension
implementation. The separate authoring API is delivered in S2.

### S2 — Separate authoring discovery, declaration, policy binding, and admission

1. Write RED host-API and descriptor/policy tests. Prove that the separate
   discovery API returns only ID, version, digest, and closed input-field
   contract; that zero/multiple matches return the specified redacted result;
   and that either result writes no package, creates no job, and grants no
   approval or dispatch authority. Prove a successful package binds the
   returned ID, version, template digest, and one-field call contract exactly.
   Reject zero or multiple `vector_index.build.v1` call sites and declaration
   fields for host implementation/module/path/endpoint, source, job members,
   profile, prior generation, model/material/provider, retry controls,
   destination, or publish/delete policy. Use one closed `tools` entry of kind
   `reviewed_capability`; it carries only the reviewed template ID, version,
   digest, canonical `job_handle` input, write side effect, and required
   approval.
2. Add the separate host template-discovery API beside the reviewed
   registration/control-plane seam. The external authoring client calls it
   before writing the descriptor; it must not be implemented as a
   vector-template-specific `WorkflowAuthoringHost` injection. Extend the
   workflow descriptor/parser, policy digest, registration record, and
   preflight path to carry the exact reviewed-template requirement. Reject
   changed, disabled, digest-mismatched, input-schema, or mandatory-dependency
   registrations, non-singular call-site declarations, or package-provided
   host authority before job ingress, package code, or output allocation.
3. Preserve legacy packages and all existing `capability_requirements`
   behavior unchanged; add compatibility fixtures for both paths.

Exit: separate discovery writes no package and grants no authority; authoring
and package admission fail closed against the same immutable template identity,
while legacy packages retain their existing admission path.

### S3 — Sealed vector-index job and exact approval consumption

1. Add RED fake-host tests for canonical one-field invocation, issuer/principal
   binding, expiry, revision/digest mismatch, template/extension/dependency
   mismatch, altered sealed members, foreign handles, and no-side-effect
   rejection sentinels. After approval, mutate each extension or dependency
   binding and prove the grant is invalidated and a new approval is required.
2. Add a generic host job-envelope interface and private resolver. The host
   extension constructs and validates the envelope; DAR transports only its
   opaque handle and verifies the extension's exact registration binding.
3. Add one durable, single-store reservation record adjacent to the current
   authorization/action ledger. It atomically binds and consumes `run_id`,
   package registration/revision, call-site ID, template ID/version/digest,
   job issuer ID, job opaque ID, job revision, job digest, principal, and
   approval nonce. Use that durable record identity as the completion and
   recovery idempotency key. Enforce one call per run, one dispatch per job,
   concurrent reservation exclusion, and replay lookup across a restart
   between approval consumption, reservation, and dispatch. Do not add
   completion recovery states in this slice.
4. Revalidate the sealed job, reviewed template, extension binding, and the
   template-declared host-selected `embedding.execute.v1` binding immediately
   before dispatch, without fallback selection. Add a host-dispatch failure
   vector that durably reaches `aborted`, publishes no generation, creates no
   public handle, and returns only the closed redacted failure receipt.

Exit: every invalid/replayed/concurrent attempt makes zero host dispatches and
no output handles; a valid attempt can dispatch exactly once.

### S4 — Staged egress and recoverable publication completion

1. Add RED state-machine tests with injected failures and restarts at every
   transition: candidate validation, commit intent, host dispatch, pending
   publication, private DAR promotion, host visibility acknowledgement, public
   completion, and response-delivery replay. For every terminal failure before
   `completed`, assert staged artifacts and inaccessible handles are destroyed
   or revoked, pending/newly visible publication is compensated, and the prior
   visible generation remains unchanged. For crashes after `host_pending`,
   assert recovery reconciles the same attempt without a fresh build before it
   completes or reaches a terminal compensated outcome.
2. Extend generic sealed artifact retention with private candidate staging and
   inaccessible promotion for the registered template's declared output roles.
   Before `host_pending`, enforce role, media type, size, retention, and a
   closed host-result contribution containing only `generation_id` and
   aggregate counts; reject host-supplied status, artifact handles, timestamps,
   or any other receipt field. Validate the complete closed receipt only after
   DAR writes `published_at` from its fake host clock at `completed`. Add RED
   rejection cases for manifest source identifiers, content, vectors, paths, or
   profile contents, and for non-aggregate coverage fields, before
   `host_pending`. The vector template supplies the required output triple.
3. Add a narrow host-extension recovery protocol keyed by the durable
   reservation-record identity: begin pending publication, query current
   outcome, acknowledge visibility, and compensate. DAR durably records
   `prepared` and `commit_intent` before their next external effect;
   `host_pending` after the pending acknowledgement; `dar_promoted` before
   requesting visibility; `host_visible` after the visibility acknowledgement;
   and `completed` before publishing handles or a receipt. The host durably
   records pending publication, visibility, and compensation before their
   respective acknowledgements. DAR records `aborted` or `recovery_required`
   before compensation or reconciliation. Test crashes immediately before and
   after every host call. Recovery resumes only this attempt.
4. Enforce current-generation retention by having DAR invoke a host resolution
   assertion before revocation. When it asserts a generation is current, defer
   revocation and retain its artifacts. Otherwise, require successful atomic
   unpublication before revocation. On assertion or unpublication failure,
   retain artifacts and leave the current generation unchanged. Add fake-clock
   expiry tests for each outcome, plus cross-principal/run retrieval-denial
   tests proving that all three artifact roles share the generation handle's
   access, retention, and revocation policy.

Exit: an attempt either produces one durable, internally consistent published
receipt and three handles, or remains redacted and non-public while recovery
uses the same attempt; it never creates a second build.

### S5 — Host composition and regression boundary

1. Wire an explicit reviewed vector-index host extension into
   `LocalWorkflowHost` composition. The default DAR host registers none, so
   discovery and admission fail closed when the deployment did not install one.
2. Add fake-only end-to-end tests from authoring through approval, host job
   dispatch, staged completion, and receipt retrieval. Assert that package
   arguments and public traces contain no sealed members, index bytes, vectors,
   source identifiers, model/material identity, or host policy.
3. Run the existing embedding-index, reviewed-tool-package, action-ledger,
   sealed-artifact, authoring, and workflow-host tests to prove no legacy path
   now gains template-specific behavior. Add an explicit regression that
   `EmbeddingSealedArtifactCallbackResolver` remains composed for its existing
   embedding workflow when no vector-index extension is installed.

Exit: a deployment can compose this reviewed extension deliberately, while a
default host and all legacy workflows remain unchanged.

## Validation Strategy

Run focused RED/GREEN suites in the changed test modules after each slice. The
implementation handoff must determine the exact focused file names as S1
creates the new host-template test seams. Final verification is:

```text
poetry run pytest -q
poetry run ruff check src tests
poetry run pre-commit run --files <changed files>
git diff --check
```

The implementation is blocked if any test uses a live model, network, vault,
vector database, external tool, or published-index destination. Failed
admission, failed dispatch, and nonterminal recovery must all prove their
corresponding side-effect sentinels remain at zero.

## Risks and Compatibility

| Risk | Trigger | Mitigation and rollback |
| --- | --- | --- |
| Cross-store completion is treated as a transaction | Crash between host publication and DAR promotion | Use durable recovery states and the original idempotency key; do not claim simultaneous distributed atomicity. |
| New registry changes legacy admissions | A generic catalog path starts requiring a vector template | Keep template resolution opt-in and add legacy regression fixtures. |
| Approval leaks across jobs or runs | Run-scoped approval bypasses the bound tuple | Atomically consume the exact approval/call/job tuple and test replay/concurrency. |
| Published generation outlives retained artifacts | DAR expiry revokes an artifact still needed by the host | Require private host resolution while current or atomic unpublication first. |
| Scope expands into an index implementation | A slice adds MLX, vault, ANN, or publication code | Reject it as host-extension work; DAR only receives fake implementations in tests. |
