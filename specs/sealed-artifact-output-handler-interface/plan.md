# Sealed Artifact Output Handler Interface Implementation Plan

Status: Implemented; validation recorded in `validation.md`

## Spec trace

- Spec: `specs/sealed-artifact-output-handler-interface/spec.md`
- Existing service: `src/dynamic_agent_runner/workflow_host/sealed_artifact_runner.py`
- Focused tests: `tests/test_sealed_artifact_output_handles.py`
- Related migration: `specs/multimodal-model-runner-protocol/spec.md`

## Goal

Add a host-owned `SealedArtifactOutputHandler` adapter with immutable request
and read-binding values. It must reuse the existing private-state store and
`SealedArtifactOutputHandleService`, expose stable redacted error classes, and
support deferred publication without changing existing atomic `publish`
callers.

## Current-state anchors

| Concern | Existing owner | Planned change | Evidence |
| --- | --- | --- | --- |
| Private/public state transitions | `SealedArtifactOutputHandleService` in `workflow_host/sealed_artifact_runner.py` | Reuse `stage_declared`, `promote`, and `read`; add one service-owned atomic terminal-outcome seam if required to make discard/replay races correct. | `tests/test_sealed_artifact_output_handles.py` (`test_private_output_promotion_replays_its_existing_output_set`, `test_output_set_revocation_denies_all_bound_output_roles`) |
| Declared output validation | `_declared_output_values` and `SealedArtifactOutput` in `sealed_artifact_runner.py` | Keep role, media, schema, byte-count, digest, and ordering authority in the service/declaration values. | `tests/test_sealed_artifact_output_handles.py` |
| Workflow-host publication | `reviewed_capability_publication.py:119-880`, `reviewed_capability_outputs.py:102-156`, and `sealed_artifact_workflow_runner.py` | Add the adapter at the host boundary; migrate only callers that need cleanup-before-publication. | `test_publication_records_all_states_before_exposing_handles`, `test_pending_recovery_promotes_the_same_staged_set_without_rebuild`, `test_validated_reviewed_candidates_stage_as_a_private_output_set` |
| Multimodal result handoff | `workflow_host/host.py:1365-1399` (`dispatch_multimodal_runner`) and `multimodal_model_runner.py` value contracts | Call `stage_declared` only after cleanup/reap and promote only after terminal publication checks; the protocol module remains the value-contract owner. | `test_host_dispatch_publishes_only_after_completed_cleanup`, `test_dispatch_maps_cleanup_failure_without_returning_output` |
| Redacted package errors | `dynamic_agent_runner.errors` and workflow-host error mappings | Translate `SealedArtifactHandleError` without exposing storage or candidate details. | Focused adapter tests plus existing redaction tests |

The first implementation task must confirm these symbols and callers before
editing. If discovery identifies a nearer host owner, record the substitution
in the task evidence instead of adding a parallel service.

## Scope and boundaries

### In scope

1. Immutable `SealedArtifactOutputStageRequest` and
   `SealedArtifactOutputReadBinding` values with runtime validation.
2. A four-operation handler adapter: `stage_declared`, `promote`, `discard`,
   and `read`.
3. Handler-owned workflow/package/producer admission checks and stable error
   classification.
4. Strict expiry, replay, promotion/discard linearization, and redaction
   tests.
5. Multimodal migration wiring and regression coverage for unchanged legacy
   `publish`, `stage_declared`, `promote`, `discard`, and `read` callers.

### Out of scope

- A second persistence store, output registry, event bus, scheduler, or
  producer abstraction.
- Model/provider-specific methods, streaming, partial public outputs, mutable
  output sets, or cross-invocation handles.
- Changes to workflow-domain JSON/SVG/document validation.
- Changes to the existing public `publish` convenience path unless a focused
  compatibility failure requires them.

## Normative implementation decisions

| Surface | Rule to freeze in code/tests |
| --- | --- |
| Stage seam | `stage_declared` is canonical; the adapter resolves the admitted declaration and calls the existing service method. |
| Request values | IDs are non-empty strings; revision and declaration digests are 64 lowercase hex; expiry is aware UTC; candidates are immutable ordered `(role, media_type, bytes)` tuples. |
| Private receipt | Only opaque `private_set_id`, declaration digest, receiver/revision/invocation binding, and expiry are retained or handed across the lifecycle. Candidate bytes never enter receipts, traces, or exceptions. |
| Promotion | One atomic consume-and-issue transition; only promotion returns public handles. A replay returns handles only for exactly one matching successor; zero or multiple matches classify as `output_conflict`. |
| Discard | Only unpromoted private sets are revoked. A second discard is a handler no-op. A late discard must not revoke a promoted successor. |
| Expiry | `now >= expires_at` is expired; staging and promotion after expiry fail, and reads use the public record expiry. |
| Error precedence | Map conclusively expired state first, then replay/concurrency conflict, then invalid contract, then unavailable state; persistence failures become `output_storage_failed`. |
| Read binding | Read accepts only the opaque handle plus immutable receiver/revision/invocation binding; no path, output-set ID, owner, or storage key is caller-supplied. |
| Private-ID boundary | The opaque `private_set_id` may cross only the host-private staged lifecycle. It is retained in the private receipt for replay/discard, but never appears in workflow/public receipts, traces, protocol results, exceptions, or candidate serialization. |

## Delivery milestones

### M1 — Freeze values and error surface

Dependencies: none.

1. Write RED tests for request/read-binding construction, digest grammar,
   aware-UTC expiry, immutable candidate tuples, and forbidden serialization of
   candidate bytes or storage details. A host-private receipt may retain the
   opaque `private_set_id` required for replay and discard.
2. Add the smallest package-owned value types and handler error taxonomy in
   the existing workflow-host package/module location.
3. Verify that invalid values fail before any state-store call and that error
   messages are redacted.

Exit: contract values and classifications have deterministic positive and
negative vectors, with no new storage authority.

### M2 — Implement the adapter over the existing service

Dependencies: M1.

1. Write RED adapter tests for valid stage → promote → read and for stage
   failures that create no public handle.
2. Implement the four handler operations in the new module
   `src/dynamic_agent_runner/workflow_host/sealed_artifact_output_handler.py`
   (`SealedArtifactOutputHandler`, request/read-binding values, and package-
   owned errors) by delegating to
   `SealedArtifactOutputHandleService`; keep workflow/package/producer
   admission in the handler/caller context rather than the service.
3. Add stable mapping from `SealedArtifactHandleError` and persistence
   failures to the package-owned classifications.
4. Ensure the adapter never returns candidate bytes, storage details, or
   service exception text in workflow-visible values; only the host-private
   staged receipt may retain its opaque `private_set_id`.

Exit: a valid request produces opaque handles only after promotion, and the
adapter contains no duplicate persistence or registry logic.

### M3 — Prove lifecycle, replay, expiry, and concurrency

Dependencies: M2.

1. Add RED tests for second discard, discard-after-promote, concurrent
   promote/discard, concurrent duplicate promotion, strict boundary expiry,
   expired private records, and zero/multiple replay successors.
2. Add one service-owned atomic lifecycle seam (or equivalent change to the
   existing service transition) that returns a terminal outcome for a private
   ID: `promoted` with exactly one successor, `discarded`, `missing/foreign`,
   or `conflict`. The adapter must consume this result rather than maintain a
   second in-memory lifecycle authority. The seam must make a late discard a
   no-op after promotion and must never revoke a promoted successor.

   The required transition table is:

   | Current private state | Operation | Result |
   | --- | --- | --- |
   | staged | promote | atomically create one public successor and return handles |
   | promoted with one successor | promote | replay the same handles |
   | promoted with zero or multiple successors | promote | `output_conflict` |
   | staged | discard | revoke private state and return success |
   | discarded/expired | discard | terminal no-op |
   | promoted | discard | terminal no-op; never revoke public state |
   | foreign/missing | either operation | `output_unavailable` unless a replay query proves conflict |

   If the current store cannot distinguish `discarded` from foreign/missing
   after revocation, the service may retain a minimal host-private terminal
   marker in the same store; it must not introduce a second lifecycle store or
   expose that marker outside the handler.

3. Verify that replay never creates a second public set, that second discard
   is distinguishable from foreign/missing state, and that the losing
   transition reports the specified terminal classification.

Exit: lifecycle linearization and replay behavior are deterministic under the
  existing `PrivateStateStore` semantics.

### M4 — Migrate the multimodal publication seam

Dependencies: M2 and M3; multimodal protocol conformance remains a prerequisite.

1. Run the prerequisite protocol gate
   `poetry run pytest tests/test_multimodal_model_runner_protocol.py -q` and
   require it to pass before migration edits.
2. Write RED integration tests around
   `LocalWorkflowHost.dispatch_multimodal_runner` in
   `src/dynamic_agent_runner/workflow_host/host.py`, showing that the
   multimodal host stages only after identity/accounting/cleanup/reap checks
   and promotes only after all terminal publication checks pass.
3. Replace direct deferred-publication logic behind the host's
   `publish_result` callback with the handler port while retaining `publish`
   for callers that need atomic output.
4. Add failure vectors for malformed results, cancellation, timeout, cleanup
   failure, producer failure, and foreign admission facts; each must discard
   private state and return no public handle.

Exit: the multimodal result contains only handler-issued opaque handles and
never publishes before worker reap or leaks raw output data.

### M5 — Regression, compatibility, and handoff evidence

Dependencies: M1–M4.

1. Run the focused sealed-artifact, reviewed-capability, workflow-runner, host
   dispatch, and multimodal protocol suites.
2. Run `poetry run ruff check src tests` and `git diff --check`.
3. Confirm unchanged behavior for existing `publish`, `stage_declared`,
   `promote`, `discard`, `read`, and expiry-extension callers.
4. Record RED-before-implementation and final test results in
   `validation.md`, including any compatibility exceptions.

Exit: the implementation is ready for delivery only when all normative tests,
redaction checks, legacy regressions, and migration gates pass.

## Verification commands

During implementation, prefer focused runs:

```text
poetry run pytest tests/test_sealed_artifact_output_handles.py -q
poetry run pytest tests/test_sealed_artifact_output_handles.py tests/test_sealed_artifact_workflow_runner.py tests/test_dar_authoring_reviewed_capability_publication.py tests/test_dar_authoring_reviewed_capability_outputs.py -q
poetry run pytest tests/test_multimodal_model_runner_protocol.py tests/test_sealed_artifact_output_handles.py -q
poetry run ruff check src tests
git diff --check
```

No live model, provider, network, or external tool call is required for this
plan.

## Handoff gate

Implementation is TDD-first: each milestone begins with focused RED tests,
then the minimum adapter/value change, then a passing rerun. The plan is ready
for task-list authoring once M1–M5 ownership, test paths, and the migration
caller are confirmed against the repository at implementation time.
