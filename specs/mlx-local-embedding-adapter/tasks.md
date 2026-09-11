# macOS Custom MLX GTE Tiny Embedding Adapter Tasks

## MLE0 — Generic embedding binding

- [x] MLE0.1 [spec/plan] Reconcile the generic model-material, capability, and
  embedding-index artifacts: a material declaration requires a declared runner
  capability named by `bindings.runner`, and `embedding.execute.v1` is a
  separate single-purpose requirement.
  - Evidence: `derive_model_execution_binding()` already derives the generic
    binding from `bindings.runner`; the three governing specs now match it.
  - Acceptance: a sealed package can bind an embedding provider without an
    MLX-specific manifest field, fake llama.cpp runner, or parallel ABI.
- [x] MLE0.2 [tests, RED/GREEN] Require the selected embedding provider to
  support the sealed runner/profile/material binding before provider entry;
  reject an embedding-capability-compatible but binding-incompatible provider.
  - Evidence: each provider now declares one exact `ModelExecutionBinding`;
    `EmbeddingProviderCatalog` rejects incompatible material and runner
    bindings before `embed()` and rejects malformed registrations.
    `poetry run pytest tests/test_embedding_execution.py
    tests/test_workflow_model_execution_binding.py -q` passed 22 tests.
  - Depends on: MLE0.1.

## MLE1 — GTE Tiny material and reference lock

- [x] MLE1.1 [discovery] Record `TaylorAI/gte-tiny` revision
  `4cc5e73d86a67c601897257b467187234aa3bca3`, `mlx==0.32.2`, BERT model
  configuration, source artifact list/SHA-256 values, tokenizer assets,
  512-token limit, 384 dimensions, masked-mean pooling, and
  `normalization: none`, closed role/path map, source-file SHA-256 values,
  byte ceilings, safe parser order, macOS/arm64 floor, and MLX distribution
  admission policy.
  - Evidence: `gte-tiny-material-profile.md` records the closed predicate,
    exact source table, 16,384-byte safetensors-header ceiling, allocation
    order, tokenizer behavior, and the separate `mlx-embedding` policy.
    the raw lock fixture produces canonical digest
    `c2fc8b91d1b4514f2411f30c4d81fa3a702e902b70ae8a7eb83567696a158c87`;
    the machine-readable profile proves changed role path, hash, or byte size
    is rejected;
    `poetry run pytest tests/test_mlx_gte_tiny_material_lock.py -q` passed.
  - Acceptance: no runtime behavior depends on an unpinned repository, file,
    package, pooling rule, or undocumented `mlx-lm` API.
- [ ] MLE1.2 [decision] Approve the synthetic reference-vector fixture,
  precision, and numerical tolerance.
  - Depends on: MLE1.1.
- [ ] MLE1.3 [release gate] Record an explicit source-license decision before
  offering `TaylorAI/gte-tiny` as a portable workflow material option.
  - Evidence: the pinned Hugging Face API/model card does not provide a
    machine-readable license. DAR does not bundle these materials; this gate
    applies to an approved receiver download option, not fixture testing.
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
  - Depends on: MLE0.2, MLE1.3, MLE4.1, and the approved embedding-index
    artifacts spec.
- [ ] MLE5.2 [implementation] Register `mlx-gte-tiny-v1` as an optional
  provider selected only by the capability catalog.
  - Depends on: MLE1.3 and MLE5.1.
- [ ] MLE5.3 [tests, GREEN] Prove unavailable/changed provider failure occurs
  before model load, embedding execution, builder import, or artifact egress.
  - Depends on: MLE5.2 and MLE0.2.
