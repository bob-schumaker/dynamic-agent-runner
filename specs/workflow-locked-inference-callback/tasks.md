# Workflow Locked Inference Callback Tasks

## I1 — Contract and multi-material prerequisites

- [ ] I1.1 [design] Approve the canonical inference-role descriptor and
  `model.generate.v1` contract, including schemas, limits, and redaction.
- [ ] I1.2 [design] Approve the model-material-set and capability-binding
  amendments; preserve legacy single-material packages.

## I2 — Admission and callback

- [ ] I2.1 [tests, RED] Add fake-only role/material/capability/provider failure
  vectors with package-import, model-load, callback, and result-write sentinels.
- [ ] I2.2 [implementation] Derive a private inference binding and implement
  bounded canonical callback execution through a receiver-owned provider seam.
- [ ] I2.3 [tests, GREEN] Prove exact role isolation, revalidation, no fallback,
  and ordinary trace/receipt redaction.

## I3 — Sealed asset integration

- [ ] I3.1 [tests, RED] Add exact owner/package/asset authorization and result
  collector vectors for callback-enabled assets.
- [ ] I3.2 [implementation] Wire the callback only through the approved sealed
  asset runtime profile.
- [ ] I3.3 [verification] Run focused suites, full pytest, Ruff, diff checks,
  and a separately authorized manual acceptance.
