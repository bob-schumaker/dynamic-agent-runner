# macOS MLX Local Embedding Adapter Tasks

## MLE1 — Characterization gate

- [ ] MLE1.1 [discovery] Record the selected upstream MLX/MLX-LM release and
  public embedding API contract from approved evidence.
  - Acceptance: loader, batch input, result, pooling/normalization, identity,
    error, and supported model-format facts are explicit; no private API is
    assumed.
- [ ] MLE1.2 [decision] Approve the initial supported artifact format(s) and
  reject unsupported formats rather than casting or adapting implicitly.
  - Depends on: MLE1.1.

## MLE2 — Direct adapter

- [ ] MLE2.1 [tests, RED] Add fake-only import/factory/platform/dependency and
  backend-injection tests for a dedicated MLX embedding adapter.
  - Depends on: MLE1.2.
- [ ] MLE2.2 [implementation] Add separate sync/async config and factories
  with lazy imports and package-owned failures.
  - Depends on: MLE2.1.
- [ ] MLE2.3 [tests, RED/GREEN] Add explicit asset-resolution and model-identity
  tests with injected doubles; preserve the generation adapter unchanged.
  - Depends on: MLE2.2.

## MLE3 — Embedding conformance

- [ ] MLE3.1 [tests, RED] Add batch/vector result tests for bounds, ordering,
  identifiers, numeric/finite values, emptiness, and dimension consistency.
  - Depends on: MLE2.3.
- [ ] MLE3.2 [implementation] Implement the characterized default backend
  loader and bounded normalization path.
  - Depends on: MLE3.1.
- [ ] MLE3.3 [tests, GREEN] Prove sync/async parity, conservative metadata,
  and no MLX/Metal/network dependency in unit tests.
  - Depends on: MLE3.2.

## MLE4 — Workflow capability provider

- [ ] MLE4.1 [tests, RED] Add fake-only `embedding.execute.v1` provider and
  locked material-binding conformance tests after the generic contract exists.
  - Depends on: MLE3.3 and the approved embedding-index artifacts spec.
- [ ] MLE4.2 [implementation] Register the MLX embedding runner/profile as an
  optional DAR provider selected only by the capability catalog.
  - Depends on: MLE4.1.
- [ ] MLE4.3 [tests, GREEN] Prove unavailable/changed provider failure occurs
  before model load, embedding execution, builder import, or artifact egress.
  - Depends on: MLE4.2.

## MLE5 — Manual gate

- [ ] MLE5.1 [manual] With explicit authorization, run the approved fixed-model
  Mac competency protocol and retain redacted shape/performance evidence only.
  - Depends on: MLE4.3.
