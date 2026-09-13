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
  - Acceptance: the test fixtures alone name model materials; production
    support remains the generic descriptor-validator/backend registry.

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

- [x] MLE3.1 [tests, RED] Add fake-only parser-ceiling, tensor/tokenizer,
  truncation, padding, pooling, materialization, normalization, bounds, order,
  ID, finite-value, emptiness, and descriptor-defined dimension tests.
  - Depends on: MLE2.3.
- Evidence: `tests/test_mlx_bert_embedding_backend.py` uses a sealed
  zero/nonzero safetensors fixture and a NumPy-backed MLX stand-in; 26 focused
  tests cover all listed pre-execution and materialized-result paths without an
  MLX import, model download, Metal, or network call.
- [x] MLE3.2 [implementation] Implement the BERT-style ABI interpreter using
  public `mlx.core` APIs and only verified descriptor/material inputs.
  - Evidence: `BertEncoderMlxV1EmbeddingBackend` parses admitted WordPiece and
    safetensors bytes, lazy-loads `mlx.core`, executes the fixed ABI math, and
    returns only validated `EmbeddingBatchResult` values.
- [x] MLE3.3 [tests, GREEN] Prove sync/async parity, conservative metadata,
  redaction, and no MLX/Metal/network import or use in unit tests.
  - Evidence: the BERT backend fake runtime covers ordered results, padding,
    truncation, pooling, normalization, finite-value rejection, execution-error
    redaction, and sync/async adapter parity. `tests/test_mlx_local_embedding.py`
    retains static-versus-resolved conservative capability checks. These tests
    inject a NumPy stand-in and never import MLX, use Metal, or make network
    calls.

## MLE4 — Manual arithmetic conformance

- [x] MLE4.1 [manual] With explicit authorization, run one workflow-defined
  descriptor against its synthetic reference fixture on a compatible Mac;
  record redacted tolerance, shape, padding/truncation, duration, and memory
  evidence only.
  - Depends on: MLE1.4 and MLE3.3.
  - Evidence (2026-09-11): the normal sandbox cannot expose Metal, but the
    explicitly elevated Darwin/arm64 competency run completed with
    `mlx==0.32.2`. The sealed generic synthetic descriptor
    `a9b1…571f9` and fixture `aa87…63ed` produced a 2×2 finite result with
    `max_abs_error: 0.0`, one padding token, four truncation tokens,
    190.861 ms duration, and 71,450,624 bytes maximum RSS. No model material,
    network, user text, or workflow output was used. The real run also exposed
    and fixed the path-only `mlx.core.load` contract; admitted weights are now
    held in a scoped temporary safetensors file and removed before return.

## MLE5 — Workflow capability provider

- [x] MLE5.0 [tests, RED/GREEN] Define and prove the generic private
  embedding-limit projection from an admitted exact ABI descriptor, including
  receiver tightening and no material/MLX/provider use during projection.
  - Evidence: `EmbeddingLimitProjectorRegistry` dispatches only by the exact
    descriptor ABI and returns `EmbeddingBatchLimits` before a provider is
    resolved. The BERT MLX ABI projection validates only sealed descriptor
    fields and maps item/byte/vector bounds without an artifact read or MLX
    import; the existing embedding execution host ceiling remains the receiver
    tightening boundary.
- [x] MLE5.1 [tests, RED/GREEN] Add fake-only `embedding.execute.v1` provider and
  descriptor/material-binding conformance tests.
  - Depends on: MLE1.4, MLE4.1, and the approved embedding-index spec.
  - Evidence: `test_generic_mlx_adapter_registers_only_through_exact_embedding_capability`
    confirms the existing receiver-owned generic bridge: a sealed MLX adapter,
    exact material binding, exact `embedding.execute.v1` contract, capability
    selection, and bounded embedding execution compose without an MLX import or
    model identity. The test was immediately green because the generic bridge
    predates this adapter; no duplicate MLX-specific provider was added.
- [x] MLE5.2 [implementation] Register one generic MLX ABI provider through
  the capability catalog. The registration identifies only the capability and
  ABI contract; it must not name, fetch, or select an embedding model.
  - Evidence: `CapabilityCatalog` selects the receiver-private provider ID only
    after exact contract/conformance admission, while
    `LocalEmbeddingAdapterProvider` carries the sealed direct adapter into the
    existing `EmbeddingProviderCatalog`. Both components are generic and do not
    add an MLX-specific or model-specific public provider surface.
- [x] MLE5.3 [tests, GREEN] Prove unavailable/changed providers fail before
  model load, embedding execution, builder import, or artifact egress.
  - Evidence: `tests/test_embedding_execution.py` rejects changed,
    nondeterministic, and wrong-binding providers before their adapter is called;
    the MLE5.1 composition test verifies the generic MLX path uses that same
    catalog. The sealed-artifact callback tests retain unavailable-provider and
    pre-egress coverage.

## MLE6 — Sealed workflow onboarding

- [x] MLE6.1 [approval/design] Produce a bounded approval packet for one
      BERT-compatible embedding material closure: exact source revision and
      file list, license decision, expected descriptor ABI, package ID, and
      resource ceilings. Record the human decision in package-local artifacts;
      do not put the model identity in DAR production source or configuration.
  - Spec: Operational Completion Gate 1.
  - Depends on: MLE5.3.
  - Evidence: user approval on 2026-09-13 is recorded in
    `tests/fixtures/mlx-gte-tiny/mle6-approval.md`. The closure remains local
    internal conformance-only because upstream Hub metadata declares no license;
    it does not authorize redistribution or live material use.

- [x] MLE6.2 [tests, RED/GREEN] Add package-admission tests for the selected
      v2 `model-materials.json`, `bert-encoder-mlx-v1` descriptor, required
      `embedding.execute.v1` capability, and synthetic document fixture.
  - Spec: FR-2, FR-4, Operational Completion Gates 1 and 3.
  - Depends on: MLE6.1.
  - Validation: changed material, ABI, descriptor, or capability facts reject
    before MLX import, model load, or artifact egress.
  - Evidence: `tests/test_mlx_gte_tiny_mle6_package.py` was red before the
    `tests/fixtures/mlx-gte-tiny/mle6-package/` artifacts existed and is green
    after their v2 lock, canonical descriptor digest, capability declaration,
    and synthetic documents were sealed. It exercises only parsers and pure
    validators; no model artifact, MLX import, or provider is reached.

- [ ] MLE6.3 [manual fixture, RED/GREEN] Generate a package-bound synthetic
      reference-vector fixture from the exact locked material closure using a
      local trusted reference runtime with `trust_remote_code=False`. Add tests
      that reject an altered fixture or reference/runtime identity.
  - Spec: FR-5, Operational Completion Gate 2.
  - Depends on: MLE6.2 and separate authorization to use the selected material.
  - Evidence: canonical fixture digest, token/mask checks, and numeric tolerance
    only; no user document, raw production vector, credential, or model output.

- [ ] MLE6.4 [tests, RED/GREEN] Run the selected sealed package through the
      generic embedding/index workflow using injected MLX/provider facts. Prove
      opaque index results and redacted receipts, including provider/material
      mismatch rejection before execution.
  - Spec: FR-3, FR-6, Operational Completion Gate 3.
  - Depends on: MLE6.2 and MLE6.3.
  - Validation: focused embedding execution, sealed-artifact callback, and
    MLE6 fixture tests remain offline and fake-backed.

- [ ] MLE6.5 [manual competency gate] With explicit authorization, prepare the
      exact sealed package on Darwin arm64 with `mlx==0.32.2`, run the MLX
      embedding/index workflow, and compare against its locked reference
      fixture. Retain only package/material/descriptor digests, limits,
      duration, memory, vector count/dimension, opaque output IDs, and status.
  - Spec: FR-1, FR-3, FR-5, Operational Completion Gate 4.
  - Depends on: MLE6.4.

- [ ] MLE6.6 [tests/docs] Add the exact successful package/material identity to
      the workflow model support matrix, update MLX embedding status/validation,
      and prove a different package or changed material cannot inherit the row.
  - Spec: Operational Completion Gate 5.
  - Depends on: MLE6.5.
  - Validation: focused support-matrix tests, full pytest, Ruff, Markdown hooks,
    and `git diff --check`.
