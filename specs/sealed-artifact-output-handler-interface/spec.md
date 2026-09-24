# Sealed Artifact Output Handler Interface Specification

## Metadata

- Feature slug: `sealed-artifact-output-handler-interface`
- Status: implemented; validation recorded in `validation.md`
- Owner: dynamic-agent-runner workflow-host sealed-artifact boundary
- Related specifications:
  - `specs/sealed-artifact-workflow-runner/spec.md`
  - `specs/multimodal-model-runner-protocol/spec.md`
  - `specs/workflow-capability-requirements/spec.md`

## Objective

Define the host-owned handler interface that turns validated private output
candidates into opaque `SealedArtifactOutputHandle` values. The interface must
support the multimodal model-runner migration without adding model-specific
logic to `SealedArtifactOutputHandleService`, and must remain useful for other
sealed producers such as artifact assets, embedding jobs, and reviewed
capabilities.

## Design pressure

`SealedArtifactOutputHandleService` currently owns state records, byte
validation, atomic publication, promotion, reads, discard, and expiry. Its
callers also need orchestration concerns: deciding when a producer is allowed
to publish, delaying public handles until cleanup and receipt validation finish,
and mapping producer failures to redacted terminal outcomes. The multimodal
runner needs that orchestration, but the output service must not learn about
models, workers, providers, prompts, or modality-specific semantics.

The boundary therefore separates:

- the output service's existing persistence and artifact-contract authority; and
- a small handler port that coordinates stage, promote, discard, and read for
  any already-admitted producer.

## Scope

This specification defines:

1. the handler port and its immutable request/value contracts;
2. stage, promote, discard, read, expiry, replay, and failure semantics;
3. ownership and validation boundaries between the handler and output service;
4. compatibility mapping from the current service methods; and
5. contract-test and migration requirements for the multimodal runner.

It does not define output media taxonomies, JSON/SVG or document semantics,
model-runner behavior, artifact contents, persistence implementation, or a new
registry/coordinator.

## Recommended interface

The recommended shape is a narrow command-oriented port implemented by the
receiver host. The v1 port deliberately mirrors the existing service rather
than adding a second generic storage abstraction:

```python
class SealedArtifactOutputHandler(Protocol):
    def stage_declared(
        self,
        request: SealedArtifactOutputStageRequest,
        *,
        now: datetime,
    ) -> SealedArtifactPrivateOutputSet: ...

    def promote(
        self,
        private: SealedArtifactPrivateOutputSet,
        *,
        now: datetime,
    ) -> tuple[SealedArtifactOutputHandle, ...]: ...

    def discard(
        self,
        private: SealedArtifactPrivateOutputSet,
        *,
        now: datetime,
    ) -> None: ...

    def read(
        self,
        handle: SealedArtifactOutputHandle,
        *,
        binding: SealedArtifactOutputReadBinding,
        now: datetime,
    ) -> bytes: ...
```

`SealedArtifactOutputHandleService` remains the default implementation and
retains the private state store. The handler is an orchestration port, not a
second store and not a producer registry. The v1 implementation calls
`stage_declared`; the existing `stage` method is not sufficient because it
hard-codes `application/octet-stream` at its outer binding.

### Stage request

`SealedArtifactOutputStageRequest` is immutable and contains only receiver-
owned, already-admitted values:

```text
receiver_id             exact host principal
workflow_id             registered workflow identity
package_id              registered package identity
revision_digest         exact registered revision
invocation_id           one non-replayed invocation
descriptor_digest       exact output declaration identity
outputs                 ordered (role, media_type, content) candidates
expires_at              receiver-selected expiry
```

The `outputs` member is private process data. It is never serialized into a
workflow receipt, trace, protocol result, or exception. A producer may supply
only candidates that the host has already validated as belonging to the
request; the handler still revalidates them before staging.

The concrete v1 field types are: non-empty identifier strings for receiver,
workflow, package, and invocation IDs; exactly 64 lowercase hexadecimal
characters for revision and descriptor digests; an aware UTC `datetime` for
expiry; and an immutable tuple of `(role, media_type, bytes)` candidates. Roles
and media types are validated by the declaration owner; candidate bytes are
copied or otherwise treated as immutable for the duration of staging.
`workflow_id`, `package_id`, and `descriptor_digest` are handler-owned
admission facts. The output service binds only the receiver, revision,
invocation, declaration digest, and candidate contract that it owns.

`SealedArtifactOutputReadBinding` contains only `receiver_id`,
`revision_digest`, and `invocation_id`. It is the immutable binding required to
read a published handle; callers do not provide a path, output-set ID, owner,
or storage key separately.

## Lifecycle contract

The handler owns this state sequence:

```text
eligible -> staged -> promoted
       \-> discarded
       \-> expired/revoked
```

Promotion and discard linearize on the private-set state transition. If
promotion wins, public handles remain valid and a later discard request is a
terminal no-op; if discard wins, promotion returns `output_unavailable` and no
public handle exists. The handler must not attempt to revoke a promoted output
set as compensation for a late discard.

- `stage_declared` validates the exact descriptor/output declaration, receiver,
  workflow revision, invocation, output order, media types, schemas, byte
  ceilings, expiry, and aggregate output limits before creating a private
  state record.
- `stage_declared` creates no public output handle and does not make candidate bytes
  readable through a public API.
- `promote` atomically consumes one private set and creates the public output
  set. It is the only transition that returns public output handles.
- `discard` irrevocably destroys an unpromoted private set. It is not a
  publication-revocation operation: callers must never discard after a
  successful promotion. A second discard is classified as an already-terminal
  no-op by the handler, even though the current service raises for a missing
  record; the adapter must normalize that behavior without revoking a promoted
  successor.
- `read` validates the handle's receiver, revision, invocation, role, media
  type, byte count, content digest, expiry, and owner before returning bytes.
- A private set is identified by its opaque `private_set_id`; its staged
  receipt binds that ID to declaration digest, receiver, revision, invocation,
  and expiry. A second `promote` of the same private set is a replay. It may
  return the already-published handles only when the underlying service proves
  exactly one promoted successor whose `private_set_id` matches; zero or
  multiple matches are `output_conflict`, never a new publication.
- Expiry is strict: `now >= expires_at` is expired. Promotion after staging
  expiry is rejected, and reads use the public record/handle expiry. Expired
  private records are unavailable and must not be recreated or promoted.
- Any validation, cancellation, timeout, cleanup, or producer failure before
  promotion must call `discard` and publish no output handle.

The handler does not decide whether a producer is authorized to run. That
decision belongs to package/capability admission and the caller's lifecycle
coordinator. The handler is called only after those checks and before public
egress.

## Error contract

The handler exposes package-owned, redacted error classifications:

| Classification | Meaning | Retryability |
| --- | --- | --- |
| `output_invalid` | Candidate or binding violates the declared output contract | no |
| `output_unavailable` | Private/public state is missing, expired, revoked, or foreign | no, except a caller may start a new invocation |
| `output_conflict` | Replay or concurrent promotion conflicts with an existing terminal state, including zero/multiple promoted successors for one private ID | no |
| `output_expired` | The requested state or handle has passed expiry | no |
| `output_storage_failed` | Receiver persistence failed without exposing storage details | only through a new invocation after host recovery |

Messages must not include paths, credentials, prompts, model bytes, native
objects, process IDs, storage keys, provider exceptions, or candidate content.
The current service's `SealedArtifactHandleError` is an implementation error;
the handler adapter owns this classification mapping. It must preserve the
precedence `output_expired` (when expiry is conclusively known), then
`output_conflict` (when a terminal/replay race is detected), then
`output_invalid` for contract failures, and `output_unavailable` otherwise.

## Ownership and validation boundaries

The handler owns:

- translating a lifecycle command into the existing output-service calls;
- validating workflow/package/producer admission facts that the output
  service does not know;
- enforcing stage-before-promote ordering;
- suppressing public handles until promotion succeeds; and
- mapping service failures to the stable error classifications above.

`SealedArtifactOutputHandleService` owns:

- private state records and atomic transitions;
- descriptor-declared output role/media/schema/byte validation;
- content digests and byte counts;
- expiry, owner, receiver, revision, and invocation binding; and
- public-handle creation and read authorization.

The producer owns only private candidate generation. It cannot choose
`output_set_id`, extend expiry, bypass descriptor validation, publish directly,
read its own output through a public handle, or call `promote` after cleanup
has failed.

Workflow domains remain responsible for interpreting output bytes. The handler
must not parse floorplan JSON, validate SVG, inspect model output semantics, or
select a media type on the producer's behalf.

## Compatibility with the current service

The existing service maps to the port without a parallel implementation:

| Handler operation | Existing implementation seam |
| --- | --- |
| `stage_declared` | `SealedArtifactOutputHandleService.stage_declared` after the handler resolves the declared output contract |
| `promote` | `SealedArtifactOutputHandleService.promote` |
| `discard` | `SealedArtifactOutputHandleService.discard`, wrapped to make a second discard a no-op and to forbid discard-after-promote |
| `read` | `SealedArtifactOutputHandleService.read` |
| atomic convenience path | existing `publish`, retained as an internal optimization for callers that do not need a deferred promotion |

Existing callers may continue using `publish` during migration. New callers
that have cleanup, approval, receipt, or publication decisions must use the
stage/promote/discard lifecycle. No second public service version is needed.

## Multimodal migration binding

The multimodal host invokes the handler only after:

1. exact runner, material, converter, ABI, output-contract, and resource
   identities are admitted;
2. sealed input handles are consumed or otherwise cleared according to the
   worker lifecycle contract;
3. the normalized result has passed identity, accounting, modality, limit, and
   `worker_reaped` validation; and
4. cleanup and reservation release have completed successfully.

The normalized multimodal result may carry only handler-issued opaque output
handles, normalized text permitted by its result contract, aggregate counters,
and redacted identity fields. A runner must never manufacture a public output
handle or write directly to the output service.

For a result containing private output candidates, the host calls `stage_declared`,
records the private receipt, and calls `promote` only after all terminal
publication checks succeed. If any check fails, it calls `discard`; the result
is terminal and no public handle is returned.

## Future generalization

The interface is intentionally producer-neutral but not content-generic. A
future producer can use the same port when it can supply:

- one registered output declaration;
- one receiver-bound workflow/revision/invocation identity;
- ordered candidates with declared role/media type and private bytes; and
- a receiver-selected expiry and lifecycle decision.

The following are explicitly out of the generalized port: streaming chunks,
partial public outputs, mutable output sets, producer-selected storage,
cross-invocation handles, arbitrary metadata bags, and model/provider-specific
callbacks. Those require separate specifications rather than widening this
handler.

## Alternatives considered

### Extend `SealedArtifactOutputHandleService` with multimodal methods

Rejected. It couples a generic artifact store to model-runner lifecycle and
would make future producers add more domain-specific methods to the service.

### One `publish(request)` method only

Rejected for migration callers. It cannot represent cleanup-before-publication,
approval, receipt validation, or recovery between staging and promotion. It
remains as a convenience implementation for existing atomic callers.

### A generic event bus or output registry

Rejected. It introduces a second coordinator/state authority, weakens ordering,
and makes replay and ownership harder to prove. The handler is a narrow port
over the existing service instead.

## Contract tests and migration gates

Before implementation is declared ready, deterministic tests must prove:

- valid stage → promote returns only opaque handles;
- invalid role, media type, schema, byte count, descriptor, receiver,
  revision, invocation, or expiry fails before public-handle creation;
- cancellation, cleanup failure, producer failure, and malformed results call
  discard and return no handle;
- promotion is atomic and replay-safe;
- read rejects foreign, expired, revoked, or mutated handles;
- existing `publish`, `stage_declared`, `promote`, `discard`, and `read`
  callers retain their current behavior; and
- the multimodal runner cannot publish before worker reap or leak raw bytes,
  paths, prompts, credentials, native objects, or provider errors.

The implementation should be delivered TDD-first: add focused handler contract
tests and observe RED before changing the service or migration adapter. The
existing sealed-artifact and multimodal protocol suites remain regression gates.

## Implementation route and readiness gate

The first implementation will add the concrete request/read-binding values and
handler adapter beside the workflow-host sealed-artifact service. It will reuse
`stage_declared`, `promote`, `read`, and the service's private state store; it
will not add a registry, event bus, producer abstraction, or second persistence
layer. The handler owns the workflow/package/producer admission check and
stable error mapping. The service remains the authority for declaration,
digest, byte, expiry, and state-record invariants.

The staged receipt is host-private and contains only the opaque
`private_set_id`, declaration digest, receiver/revision/invocation identity,
and expiry. It is never returned to a workflow or serialized into a model
result. `stage_declared` is the canonical v1 service seam; `stage` and `publish`
remain compatibility conveniences for existing callers.

Readiness is established when deterministic tests prove the lifecycle,
linearization, strict expiry, replay classification, error mapping, redaction,
and unchanged legacy callers listed above. This specification is ready to
execute under those gates.

## Review disposition

- Council findings on discard linearization, private-set replay identity,
  expiry boundaries, concrete field types, and error precedence were resolved
  in the lifecycle and contract sections above.
- Ponytail review found that a four-operation adapter over the existing service
  is the minimum viable seam; speculative registries, event buses, streaming,
  and producer-specific methods were removed or explicitly deferred.
