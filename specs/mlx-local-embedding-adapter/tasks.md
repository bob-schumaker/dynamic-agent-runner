# macOS Generalized MLX Embedding Execution Tasks

## MLE0 — Retire the model-specific experiment from DAR runtime

- [x] MLE0.1 [tests, RED] Add production-boundary tests proving DAR source and
  distributable artifacts contain no named embedding model, repository,
  revision, role table, fixed dimension, or model-specific loader identity.
  - Evidence: `tests/test_embedding_model_cleanup.py` failed red before
    production cleanup and now scans every production Python module.
- [x] MLE0.2 [implementation] Replace the current model-named MLX adapter,
  hard-coded material digest/roles, and public exports with generic descriptor
  and ABI names; retain any named experiment only below `tests/` or manual
  harness assets.
  - Evidence: `MLXPreparedEmbeddingArtifacts` carries only generic execution
    ABI, descriptor, and material identities; the model-named source helper and
    its production-only tests are removed.
- [x] MLE0.3 [tests, GREEN] Prove the experimental fixture cannot affect
  production import, adapter selection, package construction, or provider
  registration.
  - Evidence: focused regressions passed; `poetry build` followed by a wheel
    byte scan found no named experimental-model content; `poetry run pytest -q`
    passed with 2,203 passed, 1 skipped, and 7 deselected on 2026-09-10.

## MLE1 — Sealed generalized descriptor and ABI registry

- [x] MLE1.1 [spec/design] Define ABI-neutral `execution-descriptor.json`, its
  canonical digest, non-circular material-lock binding, and initial BERT-style
  ABI identity (ID, version, contract digest) with one closed finite
  `abi_fields` grammar.
  - Acceptance: the descriptor has no executable code, model registry key,
    source endpoint, path, device setting, runtime version, or provider
    selector; tensor grammar is ABI-owned rather than descriptor-provided.
- [x] MLE1.2 [tests, RED] Add fake canonical-byte and rejection vectors for
  non-circular lock/descriptor construction, descriptor/lock mismatch, unknown
  or wrong ABI ID/version/digest, ABI-schema mismatch, invalid roles/tensor
  rules, invalid limits, malformed conformance records, and generic
  source-or-preparation-output role closure.
  - Acceptance: vectors cover exact nested keys; JSON integers rather than
    booleans; distinct non-negative token IDs below vocabulary size; head-size
    divisibility; token/position ordering; all byte and allocation ceilings;
    literal fixture asset path, declaration, size, and digest; and missing,
    extra, malformed, or wrong-shaped ABI-owned tensor entries before material,
    framework, or MLX work. Vectors also prove output dimension equals hidden
    size and each fixed BERT operation (embedding order, mask, attention,
    LayerNorm, GELU, pooling, and normalization) has one interpretation.
- [x] MLE1.3 [implementation] Resolve the exact ABI through a pure
  receiver-installed validator registry, then parse, validate, and bind the
  descriptor through generic model-material and embedding execution bindings.
  The registry is architecture-ABI based and contains no named-model entries.
- [x] MLE1.4 [tests, GREEN] Prove two distinct model descriptors accepted by
  the same ABI remain isolated and that no model identity is compiled into DAR.

## MLE2 — Direct adapter admission

- [x] MLE2.1 [tests, RED] Add fake-only tests for dedicated factory/import
  behavior, macOS-14+/arm64 lazy failure, exact MLX dependency admission,
  descriptor/material rejection, and injected backend admission.
  - Depends on: MLE1.4.
- [x] MLE2.2 [implementation] Add generic sync/async factories with
  package-owned errors and no generation-adapter change.
- [x] MLE2.3 [tests, GREEN] Prove rejected platform, dependency, descriptor,
  or material states make no backend/tokenizer/model call and preserve static
  versus receiver-resolved capability metadata.

## MLE3 — Generic BERT-style encoder

- [ ] MLE3.1 [tests, RED] Add fake-only parser-ceiling, tensor/tokenizer,
  truncation, padding, pooling, materialization, normalization, bounds, order,
  ID, finite-value, emptiness, and descriptor-defined dimension tests.
  - Depends on: MLE2.3.
- [ ] MLE3.2 [implementation] Implement the BERT-style ABI interpreter using
  public `mlx.core` APIs and only verified descriptor/material inputs.
- [ ] MLE3.3 [tests, GREEN] Prove sync/async parity, conservative metadata,
  redaction, and no MLX/Metal/network import or use in unit tests.

## MLE4 — Manual arithmetic conformance

- [ ] MLE4.1 [manual] With explicit authorization, run one workflow-defined
  descriptor against its synthetic reference fixture on a compatible Mac;
  record redacted tolerance, shape, padding/truncation, duration, and memory
  evidence only.
  - Depends on: MLE1.4 and MLE3.3.

## MLE5 — Workflow capability provider

- [ ] MLE5.1 [tests, RED] Add fake-only `embedding.execute.v1` provider and
  descriptor/material-binding conformance tests.
  - Depends on: MLE1.4, MLE4.1, and the approved embedding-index spec.
- [ ] MLE5.2 [implementation] Register one generic MLX ABI provider through
  the capability catalog.
- [ ] MLE5.3 [tests, GREEN] Prove unavailable/changed providers fail before
  model load, embedding execution, builder import, or artifact egress.
