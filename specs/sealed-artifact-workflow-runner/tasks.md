# Sealed Artifact Workflow Runner Tasks

- [x] S1 [design] Approved canonical descriptor, handle lifecycle, asset ABI,
  authorization, and manifest binding after Council and Ponytail review.
- [ ] S2 [tests, RED] Add descriptor/ZIP/handle/authorization vectors and a
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
  - [ ] Extend sentinels to actual ZIP/manifest readers, handle-byte access,
    provider revalidation/material load, output sealing, publication, and
    egress rather than fake asset-execution internals.
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
