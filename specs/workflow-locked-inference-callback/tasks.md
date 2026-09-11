# Workflow Locked Inference Callback Tasks

## I0 — Readiness review

- [x] I0.1 [review] Run a reduced-independence architecture Council and Ponytail
  review. Resolve schema-asset, sealed-instruction, role authority, lifecycle,
  egress ABI, cardinality, and descriptor-digest gaps before implementation.
  - Evidence: 2026-09-10 Council (Aristotle, Ada, Feynman) and Ponytail agreed
    the original proposal was not ready; I1–I3 now cover the repaired contract.

## I1 — Contract and multi-material prerequisites

- [x] I1.1 [design] Approve the canonical `inference_roles` v1 descriptor:
  role grammar/order, canonical bytes/digest, instruction/schema asset
  locations and digests, restricted structured-value-v1 dialect, explicit
  ceilings, callback-enabled asset entitlement, and result-slot ABI.
  - Evidence: the strict canonical descriptor contract is recorded in the spec
    and implemented as fake-only parser vectors; the asset ABI remains I3.
- [x] I1.2 [design] Approve one package-level `model.generate.v1` requirement
  shared by roles, exact material-set role mapping, private executable binding,
  and legacy single-material/older-receiver behavior.
  - Evidence: one exact structured generation requirement is shared by roles;
    each role maps to a distinct material-set role, while legacy packages retain
    the existing single-lock path.

## I2 — Admission and callback

- [x] I2.1 [tests, RED] Add fake-only descriptor/policy/admission vectors for
  duplicate/noncanonical inference roles, schema/instruction asset mutation,
  unsupported dialect/value, material/capability mismatch, role/asset escape,
  and every staging/catalog/preflight/registration/preparation/ingress/runner
  route with import/load/provider/result-allocation sentinels.
  - Evidence: parser and asset-dialect vectors live in
    `tests/test_workflow_locked_inference.py`; a catalog-revision policy test
    proves tampered role assets and a material-role mismatch stop before the
    runtime manifest loader. `tests/test_sealed_artifact_preparation.py` also
    proves policy recompilation failure and real staged-catalog tampering stop
    before sealed-handle issuance or caller-byte copying.
    `test_local_host_runs_locked_inference_from_a_staged_zip` now also proves
    that a real provider failure after receiver entry seals no collector output
    and publishes no additional output handle. Staging rejects malformed roles
    before registration/model preparation; catalog tampering stops at policy
    recompilation before descriptor verification, callback resolution, handle
    reservation, collector allocation, asset/input reads, or provider entry.
    `tests/test_locked_inference_sealed_artifact_callback.py`
    proves a selected provider that becomes unavailable prevents role-asset
    reading before the preparation resolver could copy caller bytes.
    `test_locked_inference_registration_rejects_tampered_role_before_preparation`
    proves a malformed role stops at staging, before registration or model
    preparation.
  - Route matrix: staging and registration are covered by the tampered-role
    host test; catalog and runner by the staged-ZIP asset-tamper test; preflight
    by `test_factory_rejects_an_unavailable_provider_before_reading_role_assets`;
    preparation and sealed input ingress by the preparation-service rejection
    tests, which prove no caller-byte copy or handle issue. Every route uses
    import/load/provider/result-allocation sentinels appropriate to its boundary.
- [x] I2.2 [implementation] Derive a private per-role inference binding and
  implement bounded canonical callback execution through a receiver-owned
  provider seam and bounded response reader.
  - Evidence: `LockedInferenceBinding` binds each declared role to its exact
    material and capability identity; the receiver-owned execution service
    applies canonical schema validation, host-minimum limits, quota reservation,
    revalidation, deadline disposal, and redacted provider failures.
- [x] I2.3 [tests, GREEN] Prove exact role isolation, shared-capability
  cardinality, effective host ceilings, atomic quota reservation, cancellation,
  late-response disposal, revalidation, no fallback, and trace/receipt/error
  redaction.
  - Evidence: `tests/test_locked_inference_execution.py` proves role isolation,
    host-minimum ceilings, atomic concurrent quota reservation, timeout/late
    response disposal, revalidation without fallback, and redacted provider
    errors. `tests/test_workflow_locked_inference.py` proves two roles bind
    independently while sharing the single exact `model.generate.v1`
    requirement. Focused tests passed on 2026-09-10.

## I3 — Sealed asset integration

- [x] I3.1 [tests, RED] Add exact owner/package/asset authorization and
  versioned asset-ABI vectors for sealed inputs, callback-name-to-role binding,
  allowed roles, declared slots, absent/extra/repeated slots, atomic rollback,
  and content-free receipts.
  - Evidence: `tests/test_dar_authoring_host.py` uses a staged/exported ZIP and
    proves tampered assets and missing handles stop before later boundaries.
    The descriptor, handle, callback, asset-runtime, collector, and output
    publication suites cover v1 ABI, sealed inputs, role binding, allowed
    roles, ordered slots, rollback, and redacted receipts. A foreign owner
    stops after registration resolution and before catalog/ZIP, callback, asset,
    or handle access; new registrations bind owner into their digest while
    ownerless legacy registrations cannot enter the sealed runner. The complete
    focused matrix passed (87 tests) on 2026-09-10.
- [x] I3.2 [implementation] Wire the callback only through the approved sealed
  asset runtime profile and the existing in-memory result collector.
  - Evidence: Council (Aristotle, Ada, Feynman) and Ponytail reviewed the
    duplicate standalone ABI on 2026-09-10 and rejected integration. Its
    unreferenced source and tests were removed. The existing
    `SealedArtifactRunnerDescriptor`, `SealedArtifactExecutionContext`, and
    `SealedArtifactOutputCollector` remain the single callback/slot/collector
    path; `sandbox_result_location` remains because embedding code owns its
    separate use.
- [x] I3.3 [tests, GREEN] Prove deterministic ZIP import/invocation, declared
  result-slot sealing, and aggregate-only egress on a receiving fake host.
  - Evidence: `test_local_host_runs_locked_inference_from_a_staged_zip` stages
    a package, deterministically exports/reimports its ZIP, binds exact model
    materials and the receiver provider, prepares a sealed JSON handle, and
    invokes the callback-enabled sealed asset. It proves one provider entry,
    one declared opaque `result` handle, and only aggregate receipt fields.
- [ ] I3.4 [verification] Run focused suites, full pytest, Ruff, diff checks,
  then a separately authorized manual acceptance under exact owner
  authorization or the approved isolation backend.
  - Automated evidence: focused receiver suites and the full repository suite
    passed on 2026-09-10 (`2169 passed, 1 skipped, 7 deselected`); Ruff and
    `git diff --check` passed; `poetry build` produced the `0.1.17` sdist and
    wheel. The final manual acceptance remains awaiting explicit authorization.
