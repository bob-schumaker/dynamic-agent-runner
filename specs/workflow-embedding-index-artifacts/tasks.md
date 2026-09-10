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

- [ ] E1.1 [design] Approve the canonical document-snapshot, index-bundle,
  builder-descriptor, and generic coverage-report manifest shapes, all
  package-declared limits, and their sensitive-field classification.
  - Depends on: approval of this spec.
  - Acceptance: no manifest contains a source path, destination path,
    credential, provider choice, or invocation-time model selector.
- [ ] E1.2 [design] Reconcile `embedding.execute.v1` with
  `workflow-model-materials` and `workflow-capability-requirements`, including
  the exact embedding runner/profile binding and conformance vectors.
  - Depends on: E1.1.
  - Acceptance: a receiving DAR installation can decide compatibility before
    package import, model download, or input ingress.
- [ ] E1.3 [design] Confirm the sandbox result-location primitive can enforce
  index-builder egress without arbitrary package-local filesystem writes.
  - Depends on: E1.1.
  - Acceptance: document whether `sandbox-workspace-runtime` implementation is
    required before E4 can begin.

## E2 — Sealed artifacts

- [ ] E2.1 [tests, RED] Add fake-only snapshot/bundle/report canonicalization
  and admission tests covering ordering, hashes, media types, bounds,
  redaction, malformed input, and no-side-effect sentinels.
  - Depends on: E1.1.
- [ ] E2.2 [implementation] Implement the minimal host-only artifact models,
  digest binding, sealed ingress, and opaque result validation required by E2.1.
  - Depends on: E2.1.
- [ ] E2.3 [tests, GREEN] Run focused artifact/workflow tests and prove invalid
  snapshots load no package code, model, provider, or index builder.
  - Depends on: E2.2.

## E3 — Embedding capability binding

- [ ] E3.1 [tests, RED] Add fake-only material/capability/provider tests for
  exact binding, unavailable/changed providers, package and host batch bounds,
  nonfinite values, ordering, duplicate IDs, vector-dimension violations, and
  nondeterministic-provider rejection.
  - Depends on: E1.2.
- [ ] E3.2 [implementation] Add the embedding runner/profile and
  `embedding.execute.v1` capability contract, reusing the existing local
  embedding adapter only behind the generic provider seam.
  - Depends on: E3.1.
- [ ] E3.3 [tests, GREEN] Prove every failed embedding binding leaves model
  materialization, embedding execution, package import, and egress at zero.
  - Depends on: E3.2.

## E4 — Workflow-local builder

- [ ] E4.1 [tests, RED] Add sentinelled fake-builder tests for the sealed
  builder descriptor, narrow snapshot/prior-bundle/embedding/result-location
  ABI, and no arbitrary writes.
  - Depends on: E1.3, E2.3, E3.3.
- [ ] E4.2 [implementation] Route the builder through the approved sandbox and
  artifact boundary; expose no directory, network, subprocess, or storage API.
  - Depends on: E4.1.
- [ ] E4.3 [tests, GREEN] Add a deterministic toy package fixture proving
  initial and incremental identical-byte bundle/report identity, rebuild
  boundaries, aggregate-only report egress, and redaction.
  - Depends on: E4.2.

## E5 — Verification and manual gate

- [ ] E5.1 [verification] Run focused suites, `poetry run pytest -q`,
  `poetry run ruff check src tests`, and `git diff --check`.
  - Depends on: E4.3.
- [ ] E5.2 [manual gate] With explicit authorization, execute one approved
  package on a non-sensitive host-prepared snapshot and locked embedding model.
  Retain only digest identities and aggregate coverage counts; verify the
  returned coverage report has no per-document or raw-content fields.
  - Depends on: E5.1.
