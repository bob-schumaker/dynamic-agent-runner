# Sealed Artifact Workflow Runner Plan

## Objective

Deliver one host-owned, domain-neutral receiver that accepts only declared
opaque input-artifact handles, invokes one sealed package asset through a
bounded profile and exact callback bindings, and atomically returns only
declared opaque output-artifact handles.

## Current state and boundaries

The host has independently useful foundations for declared result sealing,
capability requirements, model-material bindings, locked-inference assets, and
partial descriptor/handle validation. They are not yet composed into a
receiving-host artifact invocation route. In particular, a generic ordered
admission callback chain is not proof that package access, authorization,
identity resolution, byte reads, collector allocation, provider entry, and
egress occur in the required order.

This work owns the outer descriptor, private handle lifecycle, admission
sequence, asset invocation, and output egress. Existing capability matching,
result collection, model material binding, and sandbox/profile enforcement
remain their owning subsystems. The runner must not introduce a plugin
registry, asset discovery, arbitrary callbacks, domain semantics, or a second
embedding/inference invocation route.

The implementation has one host-owned composition boundary. It may adapt
existing host services behind narrow receiver interfaces, but it must not make
those services or their private objects visible to the asset. Consumer child
contracts stay opaque to the generic runner except for their canonical common
envelope, digest, callback name, and capability identifier.

## Execution model and test seam

Build the receiver against an explicit fake-only host seam before binding real
host services. The seam records these observable operations separately:

1. registration/provenance lookup;
2. ZIP and package-manifest entry access;
3. descriptor, asset, schema, and child-contract verification;
4. exact receiver-owner-package-revision-asset-profile authorization;
5. capability-catalog, material, and provider *identity* resolution;
6. prepared-handle metadata validation and private-byte read;
7. collector allocation, write, abort, and atomic seal;
8. asset runtime creation/import/execution;
9. callback provider revalidation, material load, and provider entry; and
10. output-handle publication and egress.

The fake host records ordered events and returns controlled outcomes. Every
negative vector asserts both its stable redacted classification and that the
event log ends at the specified boundary. It is a test fixture only, not a
second production abstraction or plugin API.

The production composition maps each seam operation to the existing owning
service. It must expose no fallback provider selection. Material loading is a
callback-entry operation; identity resolution alone is side-effect free.

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

### 2. Complete descriptor, package, and admission sentinels (S2)

Add the fake host described above, with one selected failure at each observable
boundary. Cover provenance/owner rejection; duplicate, noncanonical, missing,
unknown, or mismatched package entries; descriptor, schema, asset, and child
contract failures; authorization rejection; identity-resolution rejection;
handle metadata rejection; and collector-allocation failure. For each rejection
assert that every later effect has zero calls, including input-byte reads, asset
runtime creation/import, material load, provider entry, collector write/seal,
output-handle publication, and egress.

Complete descriptor and ZIP vectors: canonicalization, duplicate/unknown/
missing fields, digest mismatch, role/order errors, schema/media correspondence,
manifest entry type and digest binding, child-contract uniqueness and envelope
binding, and exact callback capability membership in the bound
capability-requirements record. A descriptor reference alone is insufficient:
the ZIP manifest must contain exactly the corresponding regular-file record.

Replace the direct arbitrary-byte handle preparation test seam with a
preparation service fixture that first performs package/descriptor verification,
authorization, side-effect-free identity resolution, role/media/byte/digest/
schema validation, and only then seals private bytes. Add lifecycle vectors for
`prepared -> reserved -> consumed`, replay, expiry, revocation, and terminal
invocation failure. These tests are the executable definition of admission and
preparation order, not implementation-specific mocks.

Exit criteria: descriptor, package, child-contract, and preparation tests pass
where their components already exist. Receiver-path tests fail only because the
receiver composition and runner do not yet exist; none requires a live model,
network, or external tool.

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

Replace the generic ordered admission-callback class with the concrete receiver
composition. The order belongs in one receiver method and is tested through the
event-recording fake host; do not retain the generic chain as a second runtime
route. The preparation service and invocation service share the same verified
registration tuple but have separate effects: preparation may seal input bytes
but may not load material, enter a provider, allocate a collector, or import an
asset.

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

### 6. Prove lifecycle, cancellation, and receiver portability (S4)

Complete green tests for ordered atomic output sealing; provider revalidation
immediately before each callback; handle single use, expiry, reservation, and
revocation; cancellation; late-result disposal; and redacted receipts. Verify
that a terminal failure revokes reserved inputs and destroys the private
collector, while a seal that wins the race returns only sealed handles.

Add a deterministic receiving-host test that imports a ZIP with the exact
registered manifest, satisfies only declared requirements, executes a fake
asset, and returns declared sealed output handles. Add negative ABI tests for
undeclared role reads, repeated reads, unknown callbacks, callback budget
overages, out-of-order/repeated/missing output writes, and asset failure. No
test reads a raw output candidate or observes provider identity.

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

## Work-package dependency and acceptance matrix

| Package | Depends on | Deliverable | Done check |
| --- | --- | --- | --- |
| S2a descriptor/package vectors | S1 | strict parser and ZIP/manifest/child-contract tests | all malformed and binding vectors reject before identity resolution |
| S2b preparation/handle vectors | S2a | preparation-boundary and handle-state tests | unverified or mismatched input is never sealed or read |
| S2c admission sentinel matrix | S2a, S2b | event-recording fake host and boundary tests | every rejection has zero later events |
| S3a receiver composition | S2c | one concrete host composition root | fake host completes a successful invocation in specified order |
| S3b asset/context/callback path | S3a | fixed ABI, callback adapter, collector integration | only declared inputs, callbacks, and output slots are usable |
| S4 lifecycle/portability proof | S3a, S3b | deterministic receiving-host and race/error tests | sealing is atomic; failures publish nothing and receipts are redacted |
| S5 consumer migration | S4 | sealed embedding and locked-inference package assets | no consumer bypass remains |

No packages are marked parallel: S2c depends on the shared test fixture and
state model established by S2a/S2b, and all later packages consume their
contracts.

## Risks and controls

| Risk | Trigger | Control | Fallback |
| --- | --- | --- | --- |
| A partial test double hides a forbidden side effect | a negative test passes with a generic pipeline | require the event-recording host and assert the complete suffix of zero events | keep S2 open and add the missing observable seam |
| A package reference is not actually ZIP-bound | a descriptor digest resolves from an unlisted or duplicate entry | verify manifest record type, path, and digest before identity resolution | reject the package; do not infer a path |
| Preparation becomes an execution bypass | byte sealing loads material or enters a provider | split preparation from invocation and record their effects independently | reject preparation and revoke its invocation |
| Consumer migration reintroduces a special route | a consumer calls asset/runtime or egress services directly | source-level bypass tests and deletion criteria in S5 | retain the old route only while its sealed replacement is not yet admitted |
| Experimental personal profile is mistaken for isolation | a foreign package is admitted as personal | require locally selected owner plus exact authorization tuple | keep foreign assets behind `local-tool-sandbox-hardening` |

## Verification and rollback

Use fake assets, handles, providers, and receivers exclusively for unit and
integration coverage. No test may contact a live model, Hugging Face, network,
or local tool service. During implementation run the relevant focused pytest
files first; at S4 and S5 run:

```text
poetry run pytest -q
poetry run ruff check src tests
poetry build
```

A failed admission sentinel, any raw-data receipt, any output allocation before
atomic sealing, or any consumer bypass blocks the migration gate.

Each milestone is additive until its old consumer route is removed. If a
consumer migration exposes a missing generic contract field, restore that
consumer's previously passing host-private route, retain the new runner code
behind no public selection path, revise S1, and repeat the red admission
vectors before attempting migration again. Do not relax the default-deny
profile or introduce a consumer-specific escape hatch.
