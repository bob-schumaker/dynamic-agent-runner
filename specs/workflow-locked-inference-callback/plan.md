# Workflow Locked Inference Callback Plan

## Delivery order

1. Define `inference_roles` v1 canonical bytes, sealed schema/instruction asset
   references, shared generation capability cardinality, and material-set role
   mappings; preserve single-lock packages unchanged.
2. Add RED parser/policy/admission vectors for duplicate keys, schema dialect
   and canonical-value failures, cross-role/asset substitution, and exact
   private inference bindings across every descriptor-only admission route.
3. Implement the host callback with receiver-owned provider selection, bounded
   reader/writer interfaces, atomic quota reservation, cancellation, and host
   ceilings. Keep the executable provider handle private.
4. Define the versioned callback-enabled asset ABI and its declared result-slot
   atomic sealing behavior. Wire it only into the approved sealed-asset runtime
   after owner/package/asset authorization; do not add a generic Python callback
   escape hatch.
5. Validate a fake-only ZIP fixture, then manually test only with exact owner
   authorization for the experimental profile or an approved isolation backend
   for foreign/general-release execution.

## Constraints

- No scenario vocabulary, note schema, cluster representation, or tag rule may
  enter DAR source or these generic contracts.
- Unit tests use fake materials, providers, and assets only.
- The first implementation must make no claim of untrusted asset isolation.
