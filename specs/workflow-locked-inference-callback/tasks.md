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

- [ ] I2.1 [tests, RED] Add fake-only descriptor/policy/admission vectors for
  duplicate/noncanonical inference roles, schema/instruction asset mutation,
  unsupported dialect/value, material/capability mismatch, role/asset escape,
  and every staging/catalog/preflight/registration/preparation/ingress/runner
  route with import/load/provider/result-allocation sentinels.
- [x] I2.2 [implementation] Derive a private per-role inference binding and
  implement bounded canonical callback execution through a receiver-owned
  provider seam and bounded response reader.
  - Evidence: `LockedInferenceBinding` binds each declared role to its exact
    material and capability identity; the receiver-owned execution service
    applies canonical schema validation, host-minimum limits, quota reservation,
    revalidation, deadline disposal, and redacted provider failures.
- [ ] I2.3 [tests, GREEN] Prove exact role isolation, shared-capability
  cardinality, effective host ceilings, atomic quota reservation, cancellation,
  late-response disposal, revalidation, no fallback, and trace/receipt/error
  redaction.

## I3 — Sealed asset integration

- [ ] I3.1 [tests, RED] Add exact owner/package/asset authorization and
  versioned asset-ABI vectors for sealed inputs, allowed roles, declared slots,
  absent/extra/repeated slots, atomic rollback, and content-free receipts.
- [ ] I3.2 [implementation] Wire the callback only through the approved sealed
  asset runtime profile and the existing in-memory result collector.
- [ ] I3.3 [tests, GREEN] Prove deterministic ZIP import/invocation, declared
  result-slot sealing, and aggregate-only egress on a receiving fake host.
- [ ] I3.4 [verification] Run focused suites, full pytest, Ruff, diff checks,
  then a separately authorized manual acceptance under exact owner
  authorization or the approved isolation backend.
