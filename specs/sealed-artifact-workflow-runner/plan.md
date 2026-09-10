# Sealed Artifact Workflow Runner Plan

## Objective

Deliver one host-owned, domain-neutral receiver that accepts only declared
opaque input-artifact handles, invokes one sealed package asset through a
bounded profile and exact callback bindings, and atomically returns only
declared opaque output-artifact handles.

## Current state and boundaries

The host has independently useful foundations for declared result sealing,
capability requirements, model-material bindings, and locked-inference assets.
They are not yet composed into a receiving-host artifact invocation route.

This work owns the outer descriptor, private handle lifecycle, admission
sequence, asset invocation, and output egress. Existing capability matching,
result collection, model material binding, and sandbox/profile enforcement
remain their owning subsystems. The runner must not introduce a plugin
registry, asset discovery, arbitrary callbacks, domain semantics, or a second
embedding/inference invocation route.

## Delivery sequence

### 1. Freeze the v1 artifact contract (S1)

Specify and approve the exact canonical JSON representation of
`sealed-artifact-runner.json`, its self-excluding digest computation, and its
binding into package registration and the signed ZIP manifest. Record the
private handle record and its state transitions: issuance, receiver-only
resolution, single use, expiry, cancellation, revocation, and post-seal output
publication. Define the asset ABI as role-addressed read-only input bytes, a
fixed callback namespace, and the existing bounded result collector.

Exit criteria: the descriptor, handle lifecycle, authorization tuple, runtime
profile, callback budget fields, and child-consumer digest binding have one
unambiguous representation. S1 is a design gate; no runtime implementation
starts until it is approved.

### 2. Build admission sentinels before runtime code (S2)

Add fake-only tests and fakes for the manifest reader, artifact-handle store,
owner authorization check, material/provider resolver, asset importer,
callback provider, and result collector. Exercise every fixed admission
boundary independently. For each rejection, assert that every later boundary
has zero calls, including byte reads, asset import, model materialization,
provider access, collector allocation or write, output-handle creation, and
egress.

Add canonicalization, duplicate/unknown/missing-field, digest mismatch,
role/order, ZIP binding, handle receiver/revision/invocation/role/media/schema/
digest/expiry, and authorization-vector cases. These tests are the executable
definition of the admission order, not implementation-specific mocks.

Exit criteria: all S2 tests fail only because the receiver composition and
runner do not yet exist; they must not require a live model, network, or
external tool.

### 3. Compose host-owned dependencies (S3)

Add a narrow receiver composition root that injects the existing capability
catalog and result-sealing service together with private handle resolution,
owner authorization, ZIP/descriptor verification, material/provider binding,
and one approved asset runtime profile. Keep handle records and raw artifact
bytes private to the host; assets receive neither host paths nor capability
objects.

Define only interfaces required by the contract. Provider resolution must be
exact and revalidated at callback entry, with no fallback or provider identity
disclosure. The composition root must reject missing dependencies at startup
rather than silently selecting defaults.

Exit criteria: a fake receiver can be constructed entirely from explicit host
collaborators, and an asset cannot obtain ambient filesystem, network,
subprocess, environment, credentials, import escape, or introspection access.

### 4. Implement the sealed invocation path (S3)

Implement a `SealedArtifactWorkflowRunner` that performs the required order:
provenance and owner authorization; manifest, descriptor, and asset-digest
verification; requirements, material, and provider binding; handle metadata
validation; collector allocation; then asset import and execution. Each
failure returns a stable redacted classification and performs no later action.

Present input bytes only through the ABI after their metadata is accepted.
Create output handles only after the collector has validated every declared
slot and atomically sealed all results. Cancellation, timeout, or an exception
revokes callbacks, destroys the collector, discards late callback results, and
returns no output handles or raw-data receipt.

Exit criteria: the S2 failure vectors pass and a deterministic fake asset can
perform one successful sealed input-to-output transformation.

### 5. Bind bounded capabilities without creating parallel paths (S3)

Adapt the locked-inference callback as a callback provider for the fixed asset
ABI. Its existing role, material-set, provider, quota, deadline, and result
validation checks remain in force immediately before every invocation. Do not
let an asset supply a model, endpoint, provider, executable, or callback
implementation.

The embedding consumer is represented as a sealed asset with declared
artifacts and capability requirements. It may use only the same receiver and
ABI; it gets no dedicated runner or host-private filesystem path.

Exit criteria: both consumers can be expressed as child descriptors bound into
the outer descriptor, and neither has a direct asset-import or output-egress
path outside the generic runner.

### 6. Prove lifecycle and receiver portability (S4)

Complete green tests for ordered atomic output sealing; provider revalidation;
handle single use, expiry, and revocation; cancellation; late-result disposal;
and redacted receipts. Add a deterministic receiving-host test that imports a
ZIP with the exact registered manifest, satisfies only declared requirements,
executes a fake asset, and returns declared sealed output handles.

Run focused unit tests during development, then the full pytest suite, Ruff,
and package build. A failed admission sentinel, any raw-data receipt, any
output allocation before atomic sealing, or any consumer bypass blocks the
migration gate.

### 7. Migrate consumers and remove bypasses (S5)

Move the embedding-index asset first and the locked-inference asset second to
the receiver, preserving their declared child contracts and test fixtures.
Keep each old route only until the corresponding sealed route passes its
consumer regression tests; then delete that route and its tests or fixtures
that encode its bypass behavior. Do not retain a compatibility switch that can
select an unsealed route.

Exit criteria: package export, registration, and a receiving fake host use the
same descriptor digest and invocation path for both consumers; source-level
tests demonstrate that no parallel invocation path remains.

## Verification and rollback

Use fake assets, handles, providers, and receivers exclusively for unit and
integration coverage. No test may contact a live model, Hugging Face, network,
or local tool service. Verify the final implementation with the repository
test, lint, and build commands recorded in `AGENTS.md`.

Each milestone is additive until its old consumer route is removed. If a
consumer migration exposes a missing generic contract field, restore that
consumer's previously passing host-private route, retain the new runner code
behind no public selection path, revise S1, and repeat the red admission
vectors before attempting migration again. Do not relax the default-deny
profile or introduce a consumer-specific escape hatch.
