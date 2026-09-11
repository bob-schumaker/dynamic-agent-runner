# macOS Custom MLX GTE Tiny Embedding Adapter Tasks

## MLE0 — Generic embedding binding

- [ ] MLE0.1 [spec/plan] Amend the generic model-material and capability
  requirements artifacts with a non-llama.cpp embedding runner/profile binding
  and a receiver-private verified-material composition path.
  - Acceptance: a sealed package can bind an embedding provider without an
    MLX-specific manifest field, fake llama.cpp runner, or parallel ABI.
- [ ] MLE0.2 [tests, RED/GREEN] Implement and test generic binding, selected
  provider identity, and immediate availability revalidation before provider
  entry.
  - Depends on: MLE0.1.

## MLE1 — GTE Tiny material and reference lock

- [ ] MLE1.1 [discovery] Record `TaylorAI/gte-tiny` revision
  `4cc5e73d86a67c601897257b467187234aa3bca3`, `mlx==0.32.2`, BERT model
  configuration, source artifact list/SHA-256 values, tokenizer assets,
  512-token limit, 384 dimensions, masked-mean pooling, and
  `normalization: none`, closed role/path map, source-file SHA-256 values,
  byte ceilings, safe parser order, macOS/arm64 floor, and MLX distribution
  admission policy.
  - Acceptance: no runtime behavior depends on an unpinned repository, file,
    package, pooling rule, or undocumented `mlx-lm` API.
- [ ] MLE1.2 [decision] Approve the synthetic reference-vector fixture,
  precision, and numerical tolerance.
  - Depends on: MLE1.1.

## MLE2 — Direct adapter admission

- [ ] MLE2.1 [tests, RED] Add fake-only tests for dedicated factory/import
  behavior, macOS-14+/arm64 lazy failure, exact MLX dependency admission,
  material role/hash/identity rejection, and injected backend admission.
  - Depends on: MLE1.2.
- [ ] MLE2.2 [implementation] Add separate sync/async configuration and
  factories with package-owned errors and no generation-adapter change.
  - Depends on: MLE2.1.
- [ ] MLE2.3 [tests, GREEN] Prove rejected platform, dependency, or material
  states make no backend/tokenizer/model call and preserve static versus
  receiver-resolved capability metadata.
  - Depends on: MLE2.2.

## MLE3 — Closed GTE Tiny MLX encoder

- [ ] MLE3.1 [tests, RED] Add fake-only pre-allocation parser-ceiling,
  configuration/tensor/tokenizer, truncation, padding, masked-mean,
  materialization, normalization, bounds, order, ID, finite-value, emptiness,
  and 384-dimension conformance tests.
  - Depends on: MLE2.3.
- [ ] MLE3.2 [implementation] Implement the private `mlx-gte-tiny-v1` BERT
  loader/encoder using only public `mlx` / `mlx.nn` APIs and locked assets.
  - Depends on: MLE3.1.
- [ ] MLE3.3 [tests, GREEN] Prove sync/async parity, conservative capability
  metadata, redaction, and no MLX/Metal/network import or use in unit tests.
  - Depends on: MLE3.2.

## MLE4 — Manual arithmetic conformance

- [ ] MLE4.1 [manual] With explicit authorization, run the locked GTE Tiny
  materials on a compatible Mac against the approved synthetic reference
  fixture; record redacted tolerance, shape, padding/truncation, duration, and
  memory evidence only.
  - Depends on: MLE3.3.

## MLE5 — Workflow capability provider

- [ ] MLE5.1 [tests, RED] Add fake-only `embedding.execute.v1` provider and
  locked-material binding conformance tests once the generic contract and
  sealed-runner prerequisites are complete.
  - Depends on: MLE0.2, MLE4.1, and the approved embedding-index artifacts
    spec.
- [ ] MLE5.2 [implementation] Register `mlx-gte-tiny-v1` as an optional
  provider selected only by the capability catalog.
  - Depends on: MLE5.1.
- [ ] MLE5.3 [tests, GREEN] Prove unavailable/changed provider failure occurs
  before model load, embedding execution, builder import, or artifact egress.
  - Depends on: MLE5.2 and MLE0.2.
