# Workflow Embedding and Index Artifacts Tasks

## E0 — Readiness review

- [x] E0.1 [review] Run Council architecture deliberation and Ponytail review
  before approval. The sequential-fallback Council (Aristotle, Ada, Feynman)
  found and the spec now resolves: bundle-checksum versus nondeterministic
  vectors, redundant chunker identity, and an unconstrained coverage report.
  Ponytail accepted one builder identity covering sealed chunker configuration,
  generic aggregate-only coverage, and no new DAR vector-store abstraction.
  - Evidence: 2026-09-09 review; sequential execution has reduced independence.
- [x] E0.2 [review] Reconcile the implementation plan with the reviewed spec.
  The sequential-fallback Council (Aristotle, Ada, Feynman) confirmed the
  slice ordering preserves ingress-before-builder execution and exact provider
  admission; the plan now names bundle/report egress, host ceilings,
  deterministic-provider rejection, sealed builder configuration, and
  identical-byte incremental verification. Ponytail found no further scope to
  cut.
  - Evidence: 2026-09-09 review; sequential execution has reduced independence.
- [x] E0.3 [review] Verify task ordering and acceptance coverage against the
  reviewed plan. The sandbox result-location decision belongs before E4
  (builder execution), not E3 (embedding capability binding); host-ceiling,
  deterministic-provider, byte-identity, and aggregate-report checks now have
  explicit task coverage. Ponytail found no task to remove.
  - Evidence: 2026-09-09 review; sequential execution has reduced independence.

## E1 — Contract readiness

- [x] E1.1 [design] Approve the canonical document-snapshot, index-bundle,
  builder-descriptor, and generic coverage-report manifest shapes, all
  package-declared limits, and their sensitive-field classification.
  - Depends on: approval of this spec.
  - Acceptance: no manifest contains a source path, destination path,
    credential, provider choice, or invocation-time model selector.
  - Evidence: approved 2026-09-09; host-only contracts are implemented in
    `workflow_host.embedding_index_artifacts` and expose only digests, bounds,
    counts, and redacted classifications.
- [x] E1.2 [design] Reconcile `embedding.execute.v1` with
  `workflow-model-materials` and `workflow-capability-requirements`, including
  the exact embedding runner-ABI/descriptor binding and conformance vectors.
  - Depends on: E1.1.
  - Acceptance: a receiving DAR installation can decide compatibility before
    package import, model download, or input ingress.
  - Evidence: the exact embedding requirement is single-purpose rather than a
    new descriptor binding; the existing material-lock runner-ABI/descriptor binding
    plus the requirement derive a host-private `EmbeddingExecutionBinding`.
- [x] E1.3 [design] Confirm the sandbox result-location primitive can enforce
  index-builder egress without arbitrary package-local filesystem writes.
  - Depends on: E1.1.
  - Acceptance: document whether `sandbox-workspace-runtime` implementation is
    required before E4 can begin.
  - Evidence: `sandbox-workspace-runtime` now has a host-only bounded in-memory
    result collector, but `local-tool-sandbox-hardening` admits no OS/runtime
    isolation backend for untrusted executable assets. That is a general-release
    gate; E4 may use the explicit owner-authorized experimental profile while
    DAR evaluates personal-use scenarios.

## E2 — Sealed artifacts

- [x] E2.1 [tests, RED] Add fake-only snapshot/bundle/report canonicalization
  and admission tests covering ordering, hashes, media types, bounds,
  redaction, malformed input, and no-side-effect sentinels.
  - Depends on: E1.1.
  - Evidence: `tests/test_embedding_index_artifacts.py` failed with the
    expected missing-module error before implementation.
- [x] E2.2 [implementation] Implement the minimal host-only artifact models,
  digest binding, sealed ingress, and opaque result validation required by E2.1.
  - Depends on: E2.1.
  - Evidence: `workflow_host.embedding_index_artifacts` seals bounded ordered
    snapshots and validates opaque bundle/report identities without external
    execution or persistence.
- [x] E2.3 [tests, GREEN] Run focused artifact/workflow tests and prove invalid
  snapshots load no package code, model, provider, or index builder.
  - Depends on: E2.2.
  - Evidence: `poetry run pytest tests/test_embedding_index_artifacts.py -q`
    (8 passed) and focused Ruff passed on 2026-09-09. The pure host-only
    validation path has no package, model, provider, or builder dependency.

## E3 — Embedding capability binding

- [x] E3.1 [tests, RED] Add fake-only material/capability/provider tests for
  exact binding, unavailable/changed providers, package and host batch bounds,
  nonfinite values, ordering, duplicate IDs, vector-dimension violations, and
  nondeterministic-provider rejection.
  - Depends on: E1.2.
  - Evidence: `tests/test_embedding_execution.py` failed with the expected
    missing-module error before the host execution seam existed.
- [x] E3.2 [implementation] Add the embedding runner ABI and
  `embedding.execute.v1` capability contract, reusing the existing local
  embedding adapter only behind the generic provider seam.
  - Depends on: E3.1.
  - Evidence: `workflow_host.embedding_execution` derives a private binding
    from the existing sealed material runner-ABI/descriptor binding and exact
    `embedding.execute.v1` requirement; its receiver-owned adapter bridge
    wraps the existing direct local embedding interface without exposing loader
    configuration to package data.
- [x] E3.3 [tests, GREEN] Prove every failed embedding binding leaves model
  materialization, embedding execution, package import, and egress at zero.
  - Depends on: E3.2.
  - Evidence: policy compilation resolves and derives the exact embedding
    binding before package import. Focused sentinels prove an unavailable
    embedding requirement performs no runtime-manifest load or model-material
    admission; provider/batch failures make zero provider calls. No builder or
    egress surface exists before E4's sandbox gate.

## E4 — Workflow-local builder

- [x] E4.1 [tests, RED] Add sentinelled fake-builder tests for the sealed
  builder descriptor, narrow snapshot/prior-bundle/embedding/result-location
  ABI, and no arbitrary writes.
  - Depends on: E1.3, E2.3, E3.3.
  - Evidence: `tests/test_embedding_index_builder.py` failed with the expected
    missing-module error before the experimental bridge existed; it now proves
    exact owner authorization, data-only ABI, declared output slots, and zero
    builder calls for rejected admission.
- [x] E4.2 [implementation] Route the builder through the approved sandbox and
  artifact boundary; expose no directory, network, subprocess, or storage API.
  - Depends on: E4.1.
  - Evidence: the owner-authorized experimental bridge passes only the sealed
    snapshot, optional bounded prior bundle, exact binding, embedding callback,
    and in-memory declared result collector. It parses and validates the bundle
    manifest/report before returning a host-private receipt; the profile makes
    no untrusted-package isolation claim.
- [x] E4.3 [tests, GREEN] Add a deterministic toy package fixture proving
  initial and incremental identical-byte bundle/report identity, rebuild
  boundaries, aggregate-only report egress, and redaction.
  - Depends on: E4.2.
  - Evidence: `tests/fixtures/embedding-index-toy-builder/toy_builder.py` is
    injected only by the fake host. Focused tests prove repeat initial and
    incremental byte identity, prior-bundle report binding, changed-builder
    rejection, and absence of source/vector values from host result reprs.

## E5 — Verification and manual gate

- [x] E5.1 [verification] Run focused suites, `poetry run pytest -q`,
  `poetry run ruff check src tests`, and `git diff --check`.
  - Depends on: E4.3.
  - Evidence: 2026-09-10 focused embedding-index suites passed; full
    `poetry run pytest -q` passed (2040 passed, 1 skipped, 7 deselected), full
    `poetry run ruff check src tests` passed, and `git diff --check` passed.
- [x] E5.2 [manual gate] With explicit authorization, execute one approved
  package on a non-sensitive host-prepared snapshot and locked embedding model.
  Retain only digest identities and aggregate coverage counts; verify the
  returned coverage report has no per-document or raw-content fields.
  - Depends on: E5.1.
  - The manually maintained test harness supplies and verifies its scenario
    material pin; no scenario material identity belongs in this task contract.
  - Evidence: on 2026-09-10, the owner-authorized host-private E5.2 fixture
    ran through
    llama.cpp on local Metal. Its retained test-harness receipt contains only
    bundle/report/binding/package digests and aggregate counts: one document,
    one chunk, one indexed, and zero skipped/deleted/errors. The harness checks
    that no document, path, content, text, vector, or bundle field can enter
    the coverage-report receipt.

## E6 — Portable package runtime

- [x] E6.1 [design] Define the sealed descriptor/package-manifest binding for
  snapshot ingress, optional paired prior bundle/index manifest, builder
  asset/configuration, embedding material role, exact capability, and declared
  outputs.
  - Evidence: the portable-runtime section requires generic `snapshot`, paired
    optional `prior_bundle`/`prior_index_manifest`, the lexical
    `coverage_report`/`index_bundle`/`index_manifest` output triple, and one
    exact `embed` callback. Its child-contract digest plus asset digest binds
    `index_builder_digest`; the standard manifest commits all assets and
    schemas. The 2026-09-10 Council (Aristotle, Ada, Feynman) independently
    rejected a two-output design because the opaque bundle needs an external
    checksum-binding manifest. Ponytail accepted the existing three roles with
    no new DAR container or consumer-specific runner field.
- [ ] E6.2 [tests, RED] Add ZIP receiver-admission vectors proving malformed,
  unbound, or unauthorized packages load no asset, model, provider, ingress, or
  result collector.
- [ ] E6.3 [implementation] Route authorized portable package invocation
  through descriptor-only admission and the sealed builder runtime; eliminate
  test-fixture injection from the portable path.
- [ ] E6.4 [tests, GREEN] Prove deterministic ZIP import/invocation and
  aggregate-only result egress on a receiving host.
