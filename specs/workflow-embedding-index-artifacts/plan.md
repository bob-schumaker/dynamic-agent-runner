# Workflow Embedding and Index Artifacts Plan

## Delivery Rules

- Each implementation slice begins with focused fake-only RED tests, then the
  smallest GREEN implementation and focused regression run.
- No test downloads a model, calls an embedding service, reads a real source
  directory, or starts a vector database. Unit tests use injected fake builders
  rather than executing a package-local asset.
- DAR validates generic artifact, capability, model-binding, and resource
  contracts only. Chunking and index semantics remain workflow-local.
- No slice introduces an automatic persistent destination write.
- Version 1 admits only deterministic embedding providers: identical locked
  inputs and execution parameters must produce identical bundle and report
  bytes.

## S1 — Snapshot and bundle contracts

1. Define canonical snapshot, index-bundle, and generic coverage-report
   manifests, serializers, digest functions, and package-policy declarations.
2. Add RED tests for canonical ordering, duplicate IDs, hashes, media types,
   byte/count limits, malformed manifests, aggregate-only report fields, and
   sensitive-data redaction.
3. Implement host-only sealed snapshot ingress and opaque bundle/report egress
   validation.
4. Verify focused tests, then the relevant authored-workflow and artifact suites.

Exit: DAR can seal one bounded multi-document input and return bounded opaque
bundle and generic-report artifacts without importing workflow-local code.

## S2 — Embedding capability and material binding

1. Extend the model-material and execution-binding contracts with an embedding
   runner/profile category, without changing existing generation bindings.
2. Define `embedding.execute.v1` in the capability catalog with strict batch
   input/result models, host ceilings, deterministic-execution conformance, and
   provider validation.
3. Add RED fake-provider tests for unavailable, changed, wrong-contract,
   malformed-vector, dimensionality, ordering, finite-value, host-ceiling, and
   nondeterministic-provider failures.
4. Bind exact selected provider and material digests before every deferred side
   effect; rerun the existing capability admission matrix.

Exit: a sealed package can name an embedding material set and DAR capability,
and admission fails closed before model or package-local side effects.

## S3 — Bounded index-builder execution

1. Define the narrow sandbox tool ABI and sealed builder descriptor for snapshot
   records, optional prior bundle, bounded embedding batches, empty result
   location, and manifests. The descriptor binds the exact builder asset and
   all chunking/index configuration into `index_builder_digest`.
2. Add RED sentinels proving malformed inputs or unsatisfied requirements never
   import or execute the index builder, invoke embeddings, or create output.
3. Implement the smallest host bridge through the existing sandbox/result
   artifact path; do not add filesystem, network, subprocess, or storage APIs.
4. Add fake-only end-to-end tests with injected deterministic toy builder and
   embedder doubles, asserting aggregate-only report egress and no raw artifact
   content in ordinary results or traces.

Exit: a sealed workflow can produce a validated opaque bundle entirely through
the reviewed artifact and capability paths.

## S4 — Incremental bundles and package fixture

1. Add prior-bundle admission, manifest compatibility, and identical-byte
   determinism tests.
2. Implement generic rebuild-boundary validation and coverage-report binding
   for snapshot, material, capability, builder, and prior-bundle identities.
3. Create one package fixture with a toy document syntax and index
   representation, run only through the sandbox fake runtime, to prove that
   DAR owns none of those semantics.
4. Run focused suites, full pytest, Ruff, and `git diff --check`.

Exit: an example portable package demonstrates initial and incremental index
artifact production without a live model or a persistent external store.

## Manual Acceptance

Only after S1–S4 and explicit authorization, run one approved sealed package
against a non-sensitive, host-prepared snapshot and locked local embedding
material. Retain package/material/provider/bundle digests and aggregate counts
only. Verify that export is an explicit caller action and that no source bytes,
vectors, paths, or non-aggregate report content appear in standard traces or
diagnostics.
