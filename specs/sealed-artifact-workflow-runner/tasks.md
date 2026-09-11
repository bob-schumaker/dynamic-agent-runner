# Sealed Artifact Workflow Runner Tasks

- [x] S1 [design] Approved canonical descriptor, handle lifecycle, asset ABI,
  authorization, and manifest binding after Council and Ponytail review.
- [x] S2 [tests, RED] Add descriptor/ZIP/handle/authorization vectors and a
  complete zero-side-effect admission sentinel matrix.
  - [x] Validate canonical descriptor assets, schemas, child contracts, and
    callback capability membership at staging and export.
  - [x] Require descriptor-declared input role/media/schema identity/byte
    ceilings, strict Draft 2020-12 JSON validation, and reserve handles before
    a single byte is returned.
  - [x] Replace the generic admission loop with an observable receiver-order
    sentinel through collector allocation and asset import.
  - [x] Bind preparation to package provenance, exact owner authorization, and
    side-effect-free identity resolution.
  - [x] Extend sentinels to actual ZIP/manifest readers, handle-byte access,
    provider revalidation/material load, output sealing, publication, and
    egress rather than fake asset-execution internals.
    - Partial evidence: `tests/test_dar_authoring_host.py` now stages and
      registers a real ZIP, then records the actual registration, catalog,
      policy, descriptor/manifest verification, callback-resolution, handle,
      collector, asset-read, and output-publication collaborators. Tampered
      assets stop before callback resolution or handle access; a missing handle
      stops before collector allocation, asset read, input-byte consumption, or
      publication. Provider-entry/material-load and caller egress sentinels
      remain pending the generic provider composition in C6.
      A callback-enabled ZIP now also crosses the real locked-inference material
      binding and provider-entry path. Its receiver event log proves initial
      exact-provider revalidation, role-asset reread, handle reservation,
      input consumption, immediate pre-entry revalidation, provider entry, and
      output publication in order. The receiver API has no output read, export,
      persistence, or caller-egress method: publication of opaque handles is
      its only caller-visible boundary, and the real ZIP test asserts those
      handles and the receipt contain no raw provider response bytes.
- [x] S3 [implementation] Add receiver composition and sealed artifact runner.
  - [x] Retain declared output slots and add an ordered atomic private collector
    that destroys candidates on invalid or incomplete execution.
  - [x] Bind the receiver to real host registration, package, authorization,
    identity, handle, runtime-profile, callback-provider, and output-handle
    collaborators.
  - [x] Implement the fixed import-disabled `run(context) -> None` asset ABI,
    narrow input/output context, and atomic collector seal.
  - [x] Enforce declared callback call-count and per/aggregate request/response
    byte limits in the fixed ABI.
  - [x] Enforce aggregate descriptor I/O limits across input reads, callbacks,
    and collector writes.
  - [x] Revalidate the exact declared callback provider immediately before entry.
  - [x] Add callback concurrency/deadline enforcement, cancellation, and
    aggregate runtime limits.
  - [x] Add redacted receipts.
- [x] S4 [tests, GREEN] Prove atomic outputs, provider revalidation, revocation,
  cancellation/late-result disposal, redacted receipts, and deterministic
  receiving-host execution.
- [ ] S5 [migration] Route embedding-index and locked-inference package assets
  through the generic runner; remove parallel invocation paths.
  - Partial evidence: the abandoned standalone locked-inference ABI/runtime and
    its tests were removed after the 2026-09-10 Council/Ponytail review. The
    generic sealed runner is now the sole locked-inference callback path;
    embedding migration remains open.
