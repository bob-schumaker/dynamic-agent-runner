# Sealed Artifact Workflow Runner Tasks

- [x] S1 [design] Approved canonical descriptor, handle lifecycle, asset ABI,
  authorization, and manifest binding after Council and Ponytail review.
- [ ] S2 [tests, RED] Add descriptor/ZIP/handle/authorization vectors and a
  complete zero-side-effect admission sentinel matrix.
  - [x] Validate canonical descriptor assets, schemas, child contracts, and
    callback capability membership at staging and export.
  - [x] Require descriptor-declared input role/media/schema identity/byte
    ceilings and reserve handles before a single byte is returned.
  - [x] Replace the generic admission loop with an observable receiver-order
    sentinel through collector allocation and asset import.
  - [ ] Bind preparation to package provenance, exact owner authorization,
    side-effect-free identity resolution, and Draft 2020-12 input validation.
  - [ ] Extend sentinels to actual ZIP/manifest readers, handle-byte access,
    provider revalidation/material load, output sealing, publication, and
    egress rather than fake asset-execution internals.
- [ ] S3 [implementation] Add receiver composition and sealed artifact runner.
- [ ] S4 [tests, GREEN] Prove atomic outputs, provider revalidation, revocation,
  cancellation/late-result disposal, redacted receipts, and deterministic
  receiving-host execution.
- [ ] S5 [migration] Route embedding-index and locked-inference package assets
  through the generic runner; remove parallel invocation paths.
