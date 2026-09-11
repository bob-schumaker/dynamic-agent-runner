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
- S3 and S4 use an explicit owner-authorized experimental profile while DAR is
  evaluating personal-use scenarios. It runs only the exact sealed builder
  digest, requires a local host-owner opt-in, makes no isolation claim, and
  cannot admit a package received from another party. General-release and
  untrusted-package execution remain gated on the approved isolation backend
  from `local-tool-sandbox-hardening`.

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

1. Reuse the existing locked material execution binding's exact runner/profile
   identity and derive a private embedding binding from exactly one required
   `embedding.execute.v1` capability. This single-purpose capability does not
   add a descriptor `bindings` entry or expose a provider selector.
2. Define `embedding.execute.v1` with strict batch input/result models, host
   ceilings, deterministic-execution conformance, and receiver-owned provider
   validation. Existing direct local embedding adapters may appear only behind
   that generic provider seam.
3. Add RED fake-provider tests for unavailable, changed, wrong-contract,
   malformed-vector, dimensionality, ordering, finite-value, host-ceiling, and
   nondeterministic-provider failures.
4. Bind exact selected provider and material digests before every deferred side
   effect; rerun the existing capability admission matrix.

Exit: a sealed package can name an embedding material set and exact capability;
the host fails closed before provider execution, model preparation, package
import, sealed document ingress, or builder execution.

## S3 — Bounded index-builder execution

1. Define the owner-authorized experimental profile: a local host owner opts in
   to one exact sealed package digest and builder asset digest; it exposes no
   directory, network, subprocess, or persistent storage API and makes no
   isolation claim. Keep ordinary/untrusted-package execution unavailable until
   the `local-tool-sandbox-hardening` release gate is met.
2. Define the narrow sandbox tool ABI and sealed builder descriptor for
   snapshot records, optional prior bundle, bounded embedding batches, empty
   result location, and manifests. This completed experimental bridge accepts
   a bare prior bundle; E6's portable path replaces it with the validated
   bundle/manifest pair. The descriptor binds the exact builder asset and all
   chunking/index configuration into `index_builder_digest`.
3. Add RED sentinels proving malformed inputs or unsatisfied requirements never
   import or execute the index builder, invoke embeddings, or create output.
4. Implement the smallest host bridge through the existing sandbox/result
   artifact path; do not add filesystem, network, subprocess, or storage APIs.
5. Add fake-only end-to-end tests with injected deterministic toy builder and
   embedder doubles, asserting aggregate-only report egress and no raw artifact
   content in ordinary results or traces.

Exit: a personal experimental workflow can produce a validated opaque bundle
through the reviewed artifact and capability paths; general-release execution
remains gated on approved untrusted-asset isolation.

## S4 — Incremental bundles and package fixture

1. Add paired prior-bundle/prior-index-manifest admission, manifest
   compatibility, bundle-checksum, and identical-byte determinism tests.
2. Implement generic rebuild-boundary validation and coverage-report binding
   for snapshot, material, capability, builder, and prior-bundle identities.
3. Create one package fixture with a toy document syntax and index
   representation, run only through the sandbox fake runtime, to prove that
   DAR owns none of those semantics.
4. Run focused suites, full pytest, Ruff, and `git diff --check`.

Exit: an owner-authorized personal example package demonstrates initial and
incremental index artifact production without a live model or a persistent
external store. General-release distribution remains separately gated.

## Manual Acceptance

Only after S1–S4 and explicit authorization, run one approved sealed package
against a non-sensitive, host-prepared snapshot and locked local embedding
material. Retain package/material/provider/bundle digests and aggregate counts
only. Verify that export is an explicit caller action and that no source bytes,
vectors, paths, or non-aggregate report content appear in standard traces or
diagnostics.

The manually maintained test harness selects its own pinned material and uses
the standard Hugging Face cache. No scenario model identifier, revision, file,
or file digest is a DAR package or generic-contract value.

## S5 — Portable package runtime

1. Add a generic descriptor section for sealed snapshot ingress, paired
   optional prior-bundle/prior-index-manifest ingress, builder
   asset/configuration, embedding material role, and the required
   `coverage_report`/`index_bundle`/`index_manifest` output triple.
2. Route ZIP admission and invocation through descriptor-only material and
   capability resolution before builder asset loading or input ingress.
3. Add fake-only ZIP round-trip and owner-authorization vectors, including a
   bundle/manifest checksum mismatch that publishes no output; preserve the
   experimental/untrusted-package isolation distinction.

Exit: an owner-authorized external ZIP can execute the same generic contract
without test-fixture injection or caller-supplied model configuration.
