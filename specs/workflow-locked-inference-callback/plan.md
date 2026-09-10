# Workflow Locked Inference Callback Plan

## Delivery order

1. Extend the model-material set and capability-requirement contracts first;
   preserve single-lock packages unchanged.
2. Add RED parser/policy/admission vectors for role declarations and exact
   private inference bindings.
3. Implement the host callback with receiver-owned provider selection,
   canonical structured request/result validation, and host ceilings.
4. Wire it only into the approved sealed-asset runtime after owner/package/asset
   authorization; do not add a generic Python callback escape hatch.
5. Validate a fake-only package fixture, then manually test only after explicit
   authorization and the applicable sandbox gate.

## Constraints

- No scenario vocabulary, note schema, cluster representation, or tag rule may
  enter DAR source or these generic contracts.
- Unit tests use fake materials, providers, and assets only.
- The first implementation must make no claim of untrusted asset isolation.
