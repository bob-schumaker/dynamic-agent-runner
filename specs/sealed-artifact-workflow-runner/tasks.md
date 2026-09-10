# Sealed Artifact Workflow Runner Tasks

- [ ] S1 [design] Approve canonical descriptor, handle lifecycle, asset ABI,
  authorization, and manifest binding.
- [ ] S2 [tests, RED] Add descriptor/ZIP/handle/authorization vectors and a
  complete zero-side-effect admission sentinel matrix.
- [ ] S3 [implementation] Add receiver composition and sealed artifact runner.
- [ ] S4 [tests, GREEN] Prove atomic outputs, provider revalidation, revocation,
  cancellation/late-result disposal, redacted receipts, and deterministic
  receiving-host execution.
- [ ] S5 [migration] Route embedding-index and locked-inference package assets
  through the generic runner; remove parallel invocation paths.
