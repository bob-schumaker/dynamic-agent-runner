# Local Model Preparation Tasks

## Status

Historical host-catalog implementation record. Its completed tasks remain
evidence for DAR preparation mechanics, but its recipe-ownership direction is
superseded by [`../workflow-model-materials/spec.md`](../workflow-model-materials/spec.md).
Any successor implementation requires a new TDD task list. No unit test may
call Hugging Face, load a live model, or run a real converter.

The plugin-regeneration blocker recorded here is resolved in `validation.md`.
T5.2 remains an unexecuted historical llama.cpp acceptance record and must not
be run as current evidence: successor reconciliation is
`../workflow-model-materials/tasks.md` M9.1--M9.6, followed by the separate
authorized MPS receipt gate `../workflow-model-support-matrix/tasks.md` WMS3.3.

## S1 — Recipe and Prepared-Set Contracts

- [x] T1.1 [tests] Add fake-only RED tests for immutable recipe values, exact
  model-and-adapter lookup, unknown-recipe rejection, no similar-name fallback,
  and path-free public readiness/failure results.
- [x] T1.2 [implementation] Add host-owned recipe and prepared-artifact-set
  value objects, then encode the pinned floorplan base, projector, LoRA,
  metadata, converter identity, F16 output, and digest contract.
- [x] T1.3 [validation] Run the focused recipe-contract tests and record the
  observed RED-to-GREEN transition.

## S2 — Deterministic Preparation and Cache Validation

- [x] T2.1 [tests] Add fake-only RED coverage for verified cache hits, partial
  sets, missing sources, denied download authority, source/output digest
  mismatches, disallowed cache roots, and failed conversion cleanup.
- [x] T2.2 [implementation] Add the preparation service with approved-root
  lookup, per-file download through the existing Hub seam, private staging, and
  revalidation before readiness.
- [x] T2.3 [implementation] Add the injected reviewed converter collaborator;
  it accepts only the recipe’s declared LoRA and metadata inputs and promotes
  output only after format and digest validation.
- [x] T2.4 [validation] Run the focused preparation and Hugging Face support
  tests, proving cache-complete preparation makes no network call.

## S3 — Verified llama.cpp Vision Composition

- [x] T3.1 [tests] Add RED tests that reject placeholder, stale, mismatched, or
  arbitrary base/projector/LoRA paths and prove only a verified floorplan set
  reaches the vision adapter.
- [x] T3.2 [implementation] Refactor the floorplan config/factory to consume a
  host-private prepared set and pass its base GGUF, projector, and LoRA to the
  existing llama.cpp configuration.
- [x] T3.3 [implementation] Resolve the prepared set through the exact profile
  and host adapter factory before construction; preserve sealed-image handling
  and fail closed on any profile or artifact mismatch.
- [x] T3.4 [validation] Run focused floorplan, profile, host, and local-model
  regressions, including unchanged text-only and Fastmail behavior.

## S4 — Preparation and Invocation Surfaces

- [x] T4.1 [tests] Add RED host and `dar-package` tests for unknown recipes,
  denied preparation, cache-only success, verified preparation, redacted
  failures, and rejection of artifact paths or generated handoff identifiers.
- [x] T4.2 [implementation] Add the host preparation operation and its narrow
  package command accepting only a logical model requirement.
- [x] T4.3 [implementation] Make saved-workflow invocation resolve only ready
  prepared sets, return ready-to-prepare/unavailable when absent, and make no
  network call.
- [x] T4.4 [tests] Add a RED Agent Engineering guidance/plugin test for a
  host-preparation request. It must require the logical model name and
  authorized preparation action while rejecting exposed paths, converter
  commands, and prepared-artifact identifiers.
- [x] T4.5 [integration] Update Agent Engineering DAR guidance to request the
  host preparation operation only through an authorized composition; regenerate
  and validate the plugin payload so the T4.4 test passes.
- [x] T4.6 [validation] Run focused host, package-CLI, authoring, and plugin
  tests, including output/trace redaction checks.

## S5 — Completion Evidence and Release Gate

T5.2 and T5.4 are retained for historical traceability. They cannot close this
superseded host-catalog feature until the successor tasks above establish the
current package-bound contract and its manual receipt.

- [x] T5.1 [validation] Run every focused suite from S1–S4, then the full
  repository test suite and configured formatter/lint gates.
- [ ] T5.2 [superseded historical record — do not execute] After explicit
  authorization, prepare or reuse the
  pinned floorplan set, execute the saved workflow with one sealed image, admit
  its structured JSON model output, and validate the resulting SVG terminal
  artifact. JSON-to-SVG rendering and SVG validation are downstream
  workflow-local tooling. Record only redacted artifact identities and
  verification outcomes.
- [x] T5.3 [validation] Inspect user-facing results, traces, workflow metadata,
  and generated plugin guidance for paths, cache roots, converter commands, and
  opaque handoff identifiers.
- [ ] T5.4 [superseded historical record — do not execute] Record exact
  validation evidence, update feature status, and prepare release/package
  artifacts only after every prior task is complete.

T5.2 and T5.4 remain unchecked to preserve their historical non-completion;
they are not open implementation or release work. The completed successor
M9.1--M9.6 and WMS3.3 records are authoritative for current material and MPS
acceptance evidence.

## Deferred

- [ ] Recipes for additional models require separately reviewed additions.
- [ ] Converter sandboxing and arbitrary-model recipe authoring remain outside
  this feature.
