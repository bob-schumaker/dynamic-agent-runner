<!-- rumdl-disable MD013 -->

# Reviewed Vector-Index Host Extension Specification

## Metadata

- Feature slug: `reviewed-vector-index-host-extension`
- Status: in progress
- Owner: dynamic-agent-runner host-extension, capability, sealed-artifact, and workflow-package boundaries
- Related specifications:
  - `specs/workflow-capability-requirements/spec.md`
  - `specs/workflow-embedding-index-artifacts/spec.md`
  - `specs/authored-workflow-runtime-v1/spec.md`

## Objective

Allow a deployment host to register one reviewed, reusable `vector_index.build.v1` capability template with DAR. A DAR workflow package can declare and invoke that template exactly once through one approved, host-created sealed vector-index job handle. DAR retains generic registration, discovery, approval, sealed-artifact execution, bounded egress, and artifact retention responsibilities. The registered host extension retains every indexing and deployment-specific authority.

## Problem Statement

The installed embedding-index implementation demonstrates useful sealed artifact and aggregate-receipt patterns, but it is not a general DAR primitive: it fixes a document-snapshot encoding, embedding-material binding, prior-bundle form, output roles, and index-builder identity. Treating that implementation as built-in DAR behavior would make DAR own vault selection, material admission, indexing format, and publication decisions that belong to the deployment host.

DAR needs a generic reviewed host-extension seam instead. The seam must retain the non-recombinable authority boundary: a package cannot compose a corpus, a prior generation, and an index profile from independently supplied arguments.

## Scope

This feature defines:

1. reviewed registration and discovery of an exact host capability template;
2. a one-field, approval-gated package invocation contract;
3. sealed-job and capability revalidation at authoring, package admission, and execution admission;
4. generic bounded artifact-handle egress and aggregate-only receipts; and
5. fail-closed behavior when the reviewed template or its host dependencies are unavailable or changed.

## Non-Goals

This feature does not:

- implement `build_vector_index`, MLX, an embedding backend, a vector store, an ANN format, or a document parser in DAR;
- define vault, filesystem, ticket, export, or source-record semantics;
- let a package create a vector-index job, choose its members, or inspect its sealed content;
- let package data select a model/material, provider, network endpoint, resource limit, retry policy, destination, publish operation, or deletion policy;
- define hybrid search, multimodal indexing, query APIs, ACL behavior, or index-profile contents; or
- migrate or reinterpret the existing `workflow-embedding-index-artifacts` contract as this generic extension contract.

## Terms and Trust Boundary

### Reviewed template

A reviewed template is an immutable host-registration record with a capability
ID, contract version, immutable template digest, input schema, output-limit
contract, success-receipt schema digest, receipt bounds, finite failure
classifications, approval classification, and host extension binding. The
output-limit contract fixes three required roles (`index_generation`,
`index_manifest`, and `coverage_report`), each role's media type, positive
maximum bytes, and retention lifetime. The receipt contract fixes a maximum
receipt size, bounded grammars for generation IDs and opaque artifact handles,
and a finite count ceiling. The template digest covers all of those fields and
the recovery-operation and dependency bindings. A template identifies reviewed
behavior, not a package-selected implementation. The host controls registration
and removal; a workflow package may only require an exact registered identity.

For this feature, the template capability ID is `vector_index.build.v1`. An
authoring discovery request names that ID. It succeeds only when the registry
returns exactly one available reviewed identity; zero matches return
`authoring_runtime_unavailable` and multiple matches return
`authoring_runtime_ambiguous`. The resulting version and digest are bound into
the package declaration and admission record. A package never selects an
arbitrary registry result at runtime.

The registered `vector_index.build.v1` template has the closed one-field input
schema defined below and declares one required host-selected
`embedding.execute.v1` dependency/binding. A registration missing either is
unavailable; these constraints are template data, not general catalog rules.

### Vector-index job

A vector-index job is a host-created sealed artifact whose opaque public reference has this form:

```text
sealed:vector-index-job:<opaque-id>
```

The job has three non-recombinable sealed members:

- `corpus_snapshot`, required and host-authoritative;
- `prior_generation`, optional and host-authoritative; and
- `index_profile`, a reviewed immutable identifier and digest.

The host seals an immutable job envelope containing its issuer, opaque ID,
revision and digest, authorized local principal, expiry, exact template
identity, extension-registration binding, member binding, and host-selected
dependency binding. Every `vector_index.build.v1` job binds one host-selected
`embedding.execute.v1` dependency and encoder/material identity inside its
private execution state. Neither the envelope, members, nor dependency become
package arguments, trace data, ordinary results, or independently callable
handles.

One job envelope permits at most one host build dispatch. DAR atomically
reserves its host-issued job identity and revision before dispatch, records the
terminal or recoverable action outcome durably, and rejects concurrent or later
attempts to consume the same job. Recovery may resume only that same idempotent
host operation; it must never create a fresh build for the job.

One declared call site permits exactly one invocation per workflow run. DAR
atomically consumes that per-run call-site budget with the approval and job
reservation, so a second distinct valid job is rejected in the same run as is
a replay of the first job.

The one-invocation budget, mandatory embedding dependency, and three required
output roles are constraints of this `vector_index.build.v1` template. They are
not universal DAR runtime rules; other reviewed host templates may declare
their own bounded cardinality, dependency, and artifact contracts.

### Public invocation

The package declares exactly one approval-gated write invocation for the exact reviewed template. Its input schema has exactly one field:

```json
{"job_handle":"sealed:vector-index-job:<opaque-id>"}
```

No alternate public input shape is permitted. In particular, `corpus_snapshot`, `prior_generation`, `index_profile`, paths, destinations, provider choices, material identities, retry controls, and publication options are invalid package arguments.

### Authority split

DAR owns generic capability/template verification, approval gating, sealed
handle transport, workflow execution, the existing durable action ledger and
single-store reservation record, generic template-declared output limits,
artifact retention, and redacted result shaping.

The registered host extension owns job creation and validation; source extraction
and snapshot authority; material and embedding-provider admission; chunking;
index format; resource, network, and retry policy; private candidate-output
storage before DAR accepts egress; prior-generation semantics; atomic
publication; and deletion semantics. DAR owns retention, lifetime, and opaque
handle access for accepted sealed output artifacts. Before revocation, DAR
shall invoke the host resolution assertion. If it asserts that a generation is
current, DAR shall retain the artifacts and defer revocation. Otherwise, DAR
shall require successful atomic unpublication before revocation. If assertion
or unpublication fails, DAR shall retain the artifacts and leave the current
generation unchanged. DAR must prevent a package from overriding these
host-owned choices.

## Functional Requirements

### FR-1: Reviewed registration and shared discovery

DAR shall provide one host-controlled registry for reviewed capability
templates. The registry shall expose the discovery operation defined above and
shall return its exact contract version and template digest. Discovery is an
availability fact only; it is not approval or execution authorization.

### FR-2: Exact package declaration and admission

A package declaration shall bind exactly one required template identity:
`vector_index.build.v1`, its contract version, and its immutable template
digest. DAR shall revalidate that exact identity and its current availability at
package admission. Missing, disabled, changed, or nonmatching templates shall
fail closed before job ingress, package execution, extension dispatch, or
artifact allocation.

The package declaration shall not contain a host implementation name, module, path, endpoint, model, provider, job-member value, or host-policy override.

### FR-3: One sealed-handle invocation and approval

DAR shall expose the template to the package as one declared write-side-effect
tool requiring human approval. The tool shall accept only the canonical
one-field public invocation shape. DAR shall reject malformed, foreign,
expired, unauthorized, or template-mismatched job handles before extension
dispatch.

One durable single-store reservation record shall bind and atomically consume
the immutable tuple `(run_id, package_registration_and_revision,
declared_call_site_id, template_id_version_and_digest, job_issuer_id,
job_opaque_id, job_revision, job_digest, principal, approval_nonce)` while
reserving the job. Its durable record identity is the completion and recovery
idempotency key and supplies replay lookup across a restart between approval,
reservation, and dispatch.
Run-scoped approval grants cannot authorize this capability unless they bind
that exact tuple. Any changed job, template, extension, or dependency binding
invalidates approval and requires a new approval. The package has one declared
call site; each workflow run can invoke it once, and each accepted job can
produce at most one dispatch attempt through it.

### FR-4: Execution-admission revalidation

Immediately before dispatch, DAR and the host extension shall revalidate the
sealed job envelope, reviewed template identity, extension-registration binding,
and host-selected dependency binding. A changed or unavailable embedding
dependency, material binding, job member, or extension binding shall fail
closed without dispatch, publication, or output handle creation. This
revalidation must not select a fallback provider or allow the package to supply
a replacement.

### FR-5: Bounded opaque egress

DAR shall extend its generic staged-artifact and durable action-ledger
mechanisms with one idempotent completion attempt keyed by the durable
reservation-record identity. Its legal forward path is:

```text
approved -> prepared -> commit_intent -> host_pending -> dar_promoted
                                                     -> host_visible -> completed
```

Failure before `host_pending` transitions to `aborted`. Failure at or after
`host_pending` transitions to `recovery_required`; recovery may resume only the
same attempt at its last durable state or transition to `aborted` after
successful compensation.

`prepared` means all three candidate artifacts were validated privately.
`host_pending` means the host completed an idempotent, non-visible, reversible
pending publication. `dar_promoted` means DAR created all three handles but
kept them inaccessible. `host_visible` is the durable acknowledgment that the
host made that same generation visible. Only `completed` exposes the three
handles and stores the success receipt. Candidate artifacts have no public
opaque handles before `completed`. DAR shall not parse index bytes or require a
shared index format.

For the success receipt, the host supplies only aggregate counts and an opaque
generation ID. DAR writes `published_at` from its host clock at completion,
creates the artifact handles, then validates and stores this closed success
receipt with
`additionalProperties: false` at every object level:

```json
{
  "status": "published",
  "generation_id": "opaque host-generated identifier",
  "published_at": "host-clock timestamp",
  "artifacts": {
    "index_generation": "opaque handle",
    "index_manifest": "opaque handle",
    "coverage_report": "opaque handle"
  },
  "counts": {
    "source_records": 0,
    "embedding_units": 0,
    "indexed": 0,
    "skipped": 0,
    "deleted": 0,
    "errored": 0
  }
}
```

`status` is the literal `published`. `generation_id` and every artifact handle
are nonempty bounded opaque strings with template-defined grammars;
`published_at` is a bounded RFC 3339 timestamp; and every count is a finite
non-negative integer no greater than the template-defined ceiling. The receipt
shall not contain paths, raw bytes, vectors, source identifiers, model or
material identity, profile contents, retry history, host policy, or internal
artifact metadata. The `index_manifest` contains only canonical provenance,
digest bindings, and aggregate counts; it contains no source identifiers,
content, vectors, paths, or profile contents. The `coverage_report` is
aggregate-only. Both artifacts have the same principal/run-bound access,
retention, and revocation policy as the generation handle.

### FR-6: Failure and publication atomicity

Before `completed`, a terminal failed attempt shall destroy or revoke staged
artifacts and inaccessible handles, compensate a pending or newly visible
publication, and leave the prior visible generation unchanged. A crash or
`recovery_required` attempt remains nonterminal and shall first reconcile the
same attempt as defined below. A host that cannot provide pending/reversible
publication and idempotent recovery cannot register this template.

The host extension shall provide four recovery operations keyed by the durable
reservation-record identity: begin pending publication, query the current
outcome, acknowledge visibility, and compensate. DAR shall durably record
`prepared` and `commit_intent` before their next external effect;
`host_pending` after the host has returned a pending acknowledgement;
`dar_promoted` before requesting visibility; `host_visible` after the host has
acknowledged visibility; and `completed` before exposing handles or the success
receipt. The host shall durably record pending publication before returning its
pending acknowledgement, visibility before acknowledging it, and compensation
before reporting it. DAR shall durably record `aborted` or `recovery_required`
before starting compensation or reconciliation. Recovery may resume only the
original attempt.

After `host_pending`, a crash or promotion/visibility failure enters
`recovery_required`. DAR shall reconcile the same attempt using its idempotency
key and never rebuild or republish. If reconciliation reaches `completed`,
response delivery may be retried by returning the stored receipt for the same
opaque correlation ID. If reconciliation cannot complete, DAR shall return this
closed failure receipt with no artifact handles:

```json
{
  "status": "failed",
  "classification": "stable_redacted_classification",
  "receipt_id": "opaque identifier"
}
```

The failure receipt has `additionalProperties: false`; `classification` is one
of the finite template-registered classifications; and `receipt_id` is a
bounded opaque string. DAR shall not expose a partial candidate generation as a
successful result.

## Required Verification

Implementation begins with focused RED tests, followed by the smallest implementation required to make them GREEN. All tests use fake registries, host extensions, dependencies, clocks, and artifact stores; no test may make a live model, network, MLX, vector-store, or external-tool call.

The verification suite shall prove:

1. authoring emits no package and returns `authoring_runtime_unavailable` for
   zero template matches or `authoring_runtime_ambiguous` for multiple matches;
2. package admission rejects a changed, disabled, or digest-mismatched template
   before sealed-job ingress or extension execution;
3. the public tool accepts only the canonical `job_handle` field; its exact
   approval tuple and per-run call-site budget are consumed once; and a second
   distinct job, job replay, approval replay, concurrent call, or retry cannot
   cause another dispatch;
4. malformed, foreign, expired, unauthorized, envelope-mismatched, or
   member-mismatched jobs cause zero extension dispatches and zero output
   handles;
5. a changed host-selected embedding/material dependency immediately before
   dispatch causes zero publication and no fallback selection;
6. every transition and crash boundary, including immediately before and after
   every host recovery call, is durably recovered using the same reservation
   identity, never a fresh build, and exposes no success receipt or handle
   before `completed`;
7. a successful extension result retains exactly three opaque artifact handles
   and one schema-valid, bounded aggregate-only receipt;
8. missing roles, invalid role media type, oversized artifacts, invalid receipt
   counts, unknown receipt fields, sensitive receipt fields, manifest source
   identifiers/content/vectors/paths/profile contents, or non-aggregate
   coverage fields are rejected before `host_pending`;
9. an unrecoverable completion attempt returns only the closed redacted failure
   receipt, has no handles, and leaves the prior visible generation unchanged;
   and
10. the package cannot specify a source, profile, prior generation, model,
    provider, retry policy, destination, or publish/delete behavior.
11. fake-clock expiry proves that DAR defers revocation when the host asserts a
    current generation; otherwise DAR revokes only after atomic unpublication.
    An assertion or unpublication error retains artifacts and leaves the prior
    visible generation unchanged.

Run the focused suites, `poetry run pytest -q`, `poetry run ruff check src tests`, and `git diff --check` before declaring an implementation complete.

## Acceptance Criteria

The feature is complete when a host can register an exact reviewed
`vector_index.build.v1` template and a package can discover, declare, admit,
approve, and invoke it using only one host-created sealed job handle. DAR must
fail closed at authoring, package admission, and execution admission; enforce
one invocation per workflow run and one dispatch attempt per job; recover
completion idempotently; preserve host ownership of all indexing and
publication behavior; and return only the bounded opaque artifacts and
aggregate receipt defined above.
