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
    it does not authorize redistribution or independently authorize a live
    material run.

- [x] MLE6.2 [tests, RED/GREEN] Add package-admission tests for the selected
      v2 `model-materials.json`, `bert-encoder-mlx-v3` descriptor, required
      `embedding.execute.v1` capability, and synthetic document fixture.
  - Spec: FR-2, FR-4, Operational Completion Gates 1 and 3.
  - Depends on: MLE6.1.
  - Validation: changed material, ABI, descriptor, or capability facts reject
    before MLX import, model load, or artifact egress.
  - Evidence: `tests/test_mlx_gte_tiny_mle6_package.py` was red before the
    `tests/fixtures/mlx-gte-tiny/mle6-package/` artifacts existed and is green
    after their v2 lock seals the approved ten-file closure, canonical descriptor
    digest, capability declaration, and synthetic documents. It exercises only
    parsers and pure validators; no model artifact, MLX import, or provider is
    reached.

- [x] MLE6.3 [manual fixture, RED/GREEN] Generate a package-bound synthetic
      reference-vector fixture from the exact locked material closure using a
      local trusted reference runtime with `trust_remote_code=False`. Add tests
      that reject an altered fixture or reference/runtime identity.
  - Spec: FR-5, Operational Completion Gate 2.
  - Depends on: MLE6.2 and separate authorization to use the selected material.
  - Evidence: canonical fixture digest, token/mask checks, and numeric tolerance
    only; no user document, raw production vector, credential, or model output.
  - Evidence: the verified cached closure generated
    `tests/fixtures/mlx-gte-tiny/mle6-package/conformance-fixture.json` through
    `tests/manual/generate_mlx_gte_tiny_mle6_conformance.py` with local-only
    Transformers 5.16.1 and Torch 2.13.0. The fixture retains only synthetic
    vector evidence and token/mask digests; its binding and altered-runtime
    rejection are covered by `tests/test_mlx_gte_tiny_mle6_conformance.py`.

- [x] MLE6.4 [tests, RED/GREEN] Run the selected sealed package through the
      generic embedding/index workflow using injected MLX/provider facts. Prove
      opaque index results and redacted receipts, including provider/material
      mismatch rejection before execution.
  - Spec: FR-3, FR-6, Operational Completion Gate 3.
  - Depends on: MLE6.2 and MLE6.3.
  - Validation: focused embedding execution, sealed-artifact callback, and
    MLE6 fixture tests remain offline and fake-backed.
  - Evidence: `tests/test_mlx_gte_tiny_mle6_execution.py` binds the selected
    package's exact material and capability digests to the existing generic
    provider/index path. It was immediately green because that generic bridge
    already composes sealed bindings; no MLX import occurs. A changed material
    digest rejects before the fake provider receives an execution call.

- [x] MLE6.4a [bug, tests RED/GREEN] Repair the default MLX dependency probe
      when `mlx.__version__` is absent but `mlx.core.__version__` carries the
      installed version. Preserve lazy import and the exact `mlx==0.32.2` gate.
  - Discovered: MLE6.5 preflight on 2026-09-13 found the installed 0.32.2
    package exposes its version only from `mlx.core`, causing false dependency
    rejection before material admission.
  - Depends on: MLE6.4.
  - Evidence: `test_mlx_dependency_probe_uses_core_version_when_top_level_lacks_one`
    failed before the probe used `mlx.core.__version__`, then passed with the
    existing lazy-admission regression suite.

- [x] MLE6.4b [bug, tests RED/GREEN] Permit one bounded standard safetensors
      `__metadata__` string mapping while preserving exact BERT tensor names,
      shapes, dtypes, and contiguous data-span validation.
  - Discovered: MLE6.5 preflight on 2026-09-13 reached the backend but rejected
    the verified GTE Tiny header solely because it contains
    `{"__metadata__":{"format":"pt"}}`.
  - Depends on: MLE6.4a.
  - Evidence: metadata-bearing fake safetensors was red before the reserved
    string-only mapping was excluded from the tensor set, then green; malformed
    metadata still rejects before the MLX loader is called.

- [x] MLE6.4c [bug, tests RED/GREEN] Admit the optional BERT pooler tensor pair
      only when its exact descriptor-derived dtype, shapes, and contiguous spans
      validate; do not execute it or accept any other surplus tensor.
  - Discovered: MLE6.5 preflight on 2026-09-13 found the verified GTE Tiny
    closure includes the standard unused `pooler.dense.{weight,bias}` pair.
  - Depends on: MLE6.4b.
  - Evidence: a fake complete pair was red before admission and green after;
    a malformed pooler shape rejects before the MLX loader is called.

- [x] MLE6.4d [bug, tests RED/GREEN] Add a versioned closed BERT descriptor
      grammar that permits only F32 LayerNorm affine tensors alongside a
      declared F16 base dtype; retain the uniform v1 grammar unchanged.
  - Discovered: MLE6.5 preflight on 2026-09-13 found the verified GTE Tiny
    closure stores its 26 `*.LayerNorm.{weight,bias}` tensors as F32 while its
    other encoder and optional pooler tensors are F16.
  - Depends on: MLE6.4c.
  - Evidence: v2 acceptance and incompatible precision-pattern rejection were
    red before the closed v2 validator was added, then green with package
    identity and generic execution-binding tests.

- [x] MLE6.4e [bug, tests RED/GREEN] Pad every admitted BERT input to the
      descriptor's exact `max_tokens` width, matching the sealed reference
      tokenizer contract rather than the longest item in the invocation.
  - Discovered: MLE6.5 real execution on 2026-09-13 reached conformance but
    differed by up to `0.6290122419595718`; DAR emitted variable-width token
    arrays while the locked CPU reference used `padding="max_length"` at 512.
  - Depends on: MLE6.4d.
  - Evidence: a descriptor width greater than the longest item was red before
    the repair and green after; focused backend, descriptor, package, and
    execution-binding suites pass.

- [x] MLE6.4f [bug, tests RED/GREEN] Add a versioned closed tokenizer grammar
      for lowercase accent-stripping BERT normalization and execute that exact
      Unicode transform before WordPiece segmentation.
  - Discovered: MLE6.5 real execution on 2026-09-13 proved empty and ASCII
    token IDs match the reference, while `Café naïve` became unknown tokens
    instead of the reference's accent-stripped WordPiece IDs.
  - Depends on: MLE6.4e.
  - Evidence: the closed v3 descriptor and Unicode WordPiece test were red
    before implementation and green after; all three selected document token
    IDs and attention masks exactly match their locked reference digests.

- [x] MLE6.4g [bug, tests RED/GREEN] Apply the v2 closed F32 LayerNorm tensor
      rule to its v3 tokenizer-normalization successor during safetensors
      admission and memory accounting.
  - Discovered: MLE6.5 rerun on 2026-09-13 admitted the v3 descriptor but
    rejected its verified F32 LayerNorm header because the runtime predicate
    named only v2.
  - Depends on: MLE6.4f.
  - Evidence: a v3 LayerNorm dtype assertion was red under the v2-only
    predicate and green after the shared exact rule covered both ABIs.

- [x] MLE6.4h [bug, manual RED/GREEN] Canonically order the competency
      harness's private snapshot documents before opaque index validation.
  - Discovered: MLE6.5 on 2026-09-13 passed real embedding conformance and
    then rejected the intentionally listed `empty`, `ascii`, `unicode` inputs
    because index snapshots require lexicographically sorted IDs.
  - Depends on: MLE6.4g.
  - Evidence: the manual gate failed at the opaque-index stage before sorting
    and passed after canonical ordering without changing vector input order.

- [x] MLE6.4i [bug, tests RED/GREEN] Keep the MLE6.3 locked-reference
      regression aligned with the package's versioned v3 descriptor contract.
  - Discovered: MLE6.6 focused validation on 2026-09-13 found the conformance
    regression still instantiated the v1 validator after the package migrated
    through the closed v2 and v3 extensions.
  - Depends on: MLE6.4h.
  - Evidence: the focused MLE6 conformance suite failed under the retired v1
    validator and passed after asserting the exact v3 descriptor contract.

- [x] MLE6.5 [manual competency gate] With explicit authorization, prepare the
      exact sealed package on Darwin arm64 with `mlx==0.32.2`, run the MLX
      embedding/index workflow, and compare against its locked reference
      fixture. Retain only package/material/descriptor digests, limits,
      duration, memory, vector count/dimension, opaque output IDs, and status.
  - Spec: FR-1, FR-3, FR-5, Operational Completion Gate 4.
  - Depends on: MLE6.4h.
  - Evidence: `mle6.5-receipt.json` records Darwin arm64 `mlx==0.32.2`, the
    exact v3 descriptor/material/fixture digests, 3×384 vectors, passed opaque
    index artifacts, `0.00022599101066589355` maximum absolute error, bounded
    limits, duration, and maximum RSS without retaining inputs or vectors.

- [x] MLE6.6 [tests/docs] Add the exact successful package/material identity to
      the workflow model support matrix, update MLX embedding status/validation,
      and prove a different package or changed material cannot inherit the row.
  - Spec: Operational Completion Gate 5.
  - Depends on: MLE6.5.
  - Validation: focused support-matrix tests, full pytest, Ruff, Markdown hooks,
    and `git diff --check`.
  - Evidence: the package-local machine-readable row binds its package ID,
    material lock, descriptor/ABI, capability, and receipt SHA. Focused tests
    reject a different package ID or changed material lock from inheriting it.

## MLE7 — SentencePiece-BPE BERT package expansion

- [ ] MLE7.1 [spec/design] Register a new closed BERT successor ABI for the
      exact SentencePiece-BPE tokenizer grammar required by
      `intfloat/multilingual-e5-small`; record its canonical identity/digest,
      roles, tokenizer-byte and resource ceilings, special IDs, normalization,
      boundary behavior, truncation, and padding semantics.
  - Spec: planned `bert-encoder-mlx-v4` expansion, FR-2 and FR-3.
  - Depends on: MLE6.6.
  - Acceptance: it reuses BERT execution only after declaring a finite
    tokenizer grammar; it accepts neither arbitrary SentencePiece models,
    tokenizer packages/plugins, callbacks, remote code, nor an invocation path.

- [ ] MLE7.2 [tests, RED/GREEN] Add fake-only tokenizer admission and execution
      vectors for valid SentencePiece-BPE bytes plus malformed/truncated assets,
      changed normalizer, unknown pieces, special IDs, leading/adjacent
      whitespace, Unicode boundaries, truncation, and exact-width padding.
  - Spec: FR-2, FR-3, FR-5.
  - Depends on: MLE7.1.
  - Files/components: `mlx_embedding_abi.py`, MLX embedding backend tests, and
    sealed synthetic tokenizer fixtures.
  - Validation: focused pytest remains offline and never imports MLX or a
    SentencePiece runtime.

- [ ] MLE7.3 [implementation] Implement only the registered tokenizer grammar
      and bind it to the existing BERT arithmetic path; preserve v1--v3
      WordPiece behavior and reject all unregistered tokenizer formats.
  - Spec: planned BERT SentencePiece-BPE ABI.
  - Depends on: MLE7.2.

- [ ] MLE7.4 [approval/package, tests RED/GREEN] With a recorded license and
      material decision, create a package-local lock and exact descriptor for
      `intfloat/multilingual-e5-small`; prove changed material, ABI, tokenizer,
      descriptor, or capability facts reject before MLX import or egress.
  - Spec: Operational Completion Gates 1 and 3.
  - Depends on: MLE7.3 and explicit material-use authorization.

- [ ] MLE7.5 [manual fixture, RED/GREEN] Generate a synthetic reference fixture
      from the exact locked MLE7 closure using a local trusted
      `trust_remote_code=False` runtime; lock tokenizer IDs/masks and vector
      tolerance without retaining user content or arbitrary model output.
  - Spec: FR-5, Operational Completion Gate 2.
  - Depends on: MLE7.4 and separate authorization.

- [ ] MLE7.6 [tests, RED/GREEN] Exercise the MLE7 package through
      `embedding.execute.v1` and the sealed index path with injected facts;
      prove opaque output and non-transferability before provider execution.
  - Spec: FR-6, Operational Completion Gate 3.
  - Depends on: MLE7.4 and MLE7.5.

- [ ] MLE7.7 [manual] With explicit authorization, run the locked MLE7 package
      on Darwin arm64, compare its vectors to the fixture, and retain only the
      redacted receipt fields required by the operational gate.
  - Spec: FR-1, FR-3, FR-5, Operational Completion Gate 4.
  - Depends on: MLE7.6.

- [ ] MLE7.8 [tests/docs] Add the successful MLE7 package/material receipt as
      a non-transferable embedding support row and update validation status.
  - Spec: Operational Completion Gate 5.
  - Depends on: MLE7.7.

## MLE8 — RoBERTa byte-level-BPE execution ABI

- [ ] MLE8.1 [spec/design] Register a new closed `roberta-encoder-mlx-v1` ABI
      for `sentence-transformers/all-distilroberta-v1`: exact byte-level BPE
      grammar, RoBERTa tensor names/shapes/dtypes, padding-index position-ID
      derivation, LayerNorm epsilon, attention/activation/residual order,
      pooling, normalization, resource ceilings, and canonical contract digest.
  - Spec: planned RoBERTa ABI, FR-2 and FR-3.
  - Depends on: MLE6.6.
  - Acceptance: the descriptor cannot select a generic transformer interpreter,
    tokenizer code, unbounded merge/vocabulary asset, unknown tensor, or an
    alternate position-ID rule.

- [ ] MLE8.2 [tests, RED/GREEN] Add fake-only ABI vectors for byte-level BPE
      vocabulary/merge admission, Unicode byte and leading-space behavior,
      special tokens, malformed merges, RoBERTa position IDs around padding,
      tensor/header rejection, attention/pooling/normalization, and exact
      conformance fixture binding.
  - Spec: FR-2, FR-3, FR-5.
  - Depends on: MLE8.1.
  - Files/components: `mlx_embedding_abi.py`, a dedicated RoBERTa backend,
    fake MLX tests, and sealed synthetic fixtures.
  - Validation: tests do not import MLX, download model files, or invoke a
    tokenizer package.

- [ ] MLE8.3 [implementation] Implement the closed RoBERTa tokenizer and
      executor behind the registry without changing BERT ABI behavior, generic
      provider selection, or generation adapters.
  - Spec: planned `roberta-encoder-mlx-v1` ABI.
  - Depends on: MLE8.2.

- [ ] MLE8.4 [approval/package, tests RED/GREEN] With a recorded license and
      material decision, create the package-local lock and descriptor for
      `sentence-transformers/all-distilroberta-v1`; reject changed roles,
      weights, tokenizer, ABI, descriptor, and capability facts pre-execution.
  - Spec: Operational Completion Gates 1 and 3.
  - Depends on: MLE8.3 and explicit material-use authorization.

- [ ] MLE8.5 [manual fixture, RED/GREEN] Generate and bind synthetic local
      reference vectors for the exact MLE8 closure with `trust_remote_code=False`,
      including byte-level tokenizer IDs/masks and padding-position vectors.
  - Spec: FR-5, Operational Completion Gate 2.
  - Depends on: MLE8.4 and separate authorization.

- [ ] MLE8.6 [tests, RED/GREEN] Run the MLE8 package through generic embedding
      execution and index-artifact paths with injected facts; prove changed
      package/material facts reject before execution and no MLE7 evidence
      transfers to this ABI.
  - Spec: FR-6, Operational Completion Gate 3.
  - Depends on: MLE8.4 and MLE8.5.

- [ ] MLE8.7 [manual] With explicit authorization, run the locked MLE8 package
      on Darwin arm64 and retain a redacted package-bound competency receipt.
  - Spec: FR-1, FR-3, FR-5, Operational Completion Gate 4.
  - Depends on: MLE8.6.

- [ ] MLE8.8 [tests/docs] Add the successful MLE8 package/material receipt as
      a non-transferable embedding support row and update validation status.
  - Spec: Operational Completion Gate 5.
  - Depends on: MLE8.7.
