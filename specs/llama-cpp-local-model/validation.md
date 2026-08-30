# llama.cpp Local-Model Adapter Validation Log

Status: complete through Slice 3 and T5.0 embedding planning; standalone
embedding contract, T5.2 RED suite, and T5.3 implementation complete; T5.4
validation/docs complete; T5.5 terminal workflow integration is next

## Scope

- Feature: `specs/llama-cpp-local-model/spec.md`
- Plan: `specs/llama-cpp-local-model/plan.md`
- Tasks: `specs/llama-cpp-local-model/tasks.md`
- Current checkpoint: T1.1 and T1.2 RED tests are committed, T1.3 helper
  implementation landed in commit `6d269ad`, T1.4 provider-seam wiring landed
  in commit `ee0bf33`, T1.5 package-root exports landed in commit `dd37c62`, and
  the targeted Slice 1 checks are GREEN; T2.1 RED precedence tests are now
  committed in `f564caa`, T2.2 RED failure-taxonomy tests are now committed in
  `cdc1b00`, T2.3 resolution helpers are now implemented in `7a11464`, T2.4
  endpoint-failure translation is now implemented in `f4bcb0e`, T2.5 default
  Hub download wiring is now implemented in `d5857dd`, T2.6 authoritative
  model-identity preservation is now implemented in `9b7078f`, and Slice 3
  direct in-process llama.cpp chat is implemented in `58136d9`; the feature is
  complete through T3.5 and T4.5, with optional embedding follow-up unscheduled

## Executed Checks

### T1.1 RED — local endpoint helper contract

- Commit: `a5798cc` (`test(local-models): add RED tests for local endpoint
  helpers`)
- Command: `poetry run pytest tests/test_openai_client.py -q 2>&1`
- Expected result: fail before the local helper module exists
- Observed result: `3 failed, 24 passed in 0.24s`
- Failure boundary:
  - `ModuleNotFoundError: No module named 'dynamic_agent_runner.local_models'`
  - affected tests:
    - `test_local_openai_endpoint_config_preserves_aliases_and_expected_identity`
    - `test_create_local_openai_adapter_builds_local_provider_backed_adapter`
    - `test_create_local_async_openai_adapter_builds_local_provider_backed_adapter`
- Interpretation: the RED checkpoint confirms the new caller-facing contract is
  now specified in tests and that the missing `local_models` module is the next
  implementation boundary for Slice 1.

### T1.2 RED — executor routing for helper-built local adapters

- Commit: `b79f124` (`test(local-models): add RED executor routing coverage`)
- Command: `poetry run pytest tests/test_executor.py -q 2>&1`
- Expected result: fail before the local helper module exists
- Observed result: `1 failed, 49 passed in 0.51s`
- Failure boundary:
  - `ModuleNotFoundError: No module named 'dynamic_agent_runner.local_models'`
  - affected test:
    - `test_prepare_model_input_routes_local_only_requests_to_helper_built_local_adapter`
- Interpretation: the RED checkpoint confirms `local_only` routing expectations
  are now captured against the planned helper-built local adapter contract and
  still fail only at the missing `local_models` implementation boundary.

### T1.3 GREEN — local endpoint helper implementation

- Commit: `6d269ad` (`feat(local-models): add local openai endpoint helpers`)
- Commands:
  - `poetry run pytest tests/test_openai_client.py -q 2>&1`
  - `poetry run pytest tests/test_executor.py -q 2>&1`
- Expected result: the new helper module satisfies both the helper-contract and
  executor-routing checks without adding a new executor branch
- Observed result:
  - `27 passed in 0.17s`
  - `50 passed in 0.41s`
- Interpretation: the first-slice local endpoint helper now exists at
  `src/dynamic_agent_runner/local_models.py`, builds provider-backed sync/async
  adapters with caller aliases plus `is_local=True`, and preserves the existing
  metadata-based `local_only` routing seam.

### T1.4 GREEN — provider-seam adapter factory wiring

- Commit: `ee0bf33` (`refactor(local-models): route helpers through adapter factories`)
- Commands:
  - `poetry run pytest tests/test_openai_client.py -q 2>&1`
  - `poetry run pytest tests/test_executor.py -q 2>&1`
- Expected result: local helper construction routes through explicit
  repository-owned adapter factories in `openai_client.py` while preserving the
  existing request-construction and response-normalization boundary
- Observed result:
  - `29 passed in 0.15s`
  - `50 passed in 0.38s`
- Interpretation: `local_models.py` now translates local endpoint config into
  `OpenAIProviderConfig`, while adapter construction from provider config lives
  under repository-owned `openai_client.py` helper factories and keeps the same
  metadata-based executor routing behavior.

### T1.5 GREEN — package-root export surface

- Commit: `dd37c62` (`feat(local-models): export local endpoint helpers`)
- Commands:
  - `poetry run pytest tests/test_import.py -q 2>&1`
  - `poetry run pytest tests/test_openai_client.py`
    `tests/test_executor.py tests/test_import.py -q 2>&1`
  - `poetry run pre-commit run --files
    src/dynamic_agent_runner/local_models.py
    src/dynamic_agent_runner/openai_client.py
    src/dynamic_agent_runner/__init__.py
    tests/test_openai_client.py tests/test_executor.py`
    `tests/test_import.py 2>&1`
- Expected result: the approved local endpoint config and helper functions are
  importable from `dynamic_agent_runner`, and the completed Slice 1 surface
  remains green under focused test and formatting/lint coverage
- Observed result:
  - `1 passed in 0.19s`
  - `80 passed in 0.47s`
  - Ruff Check passed; Ruff Format passed
- Interpretation: `dynamic_agent_runner` now re-exports
  `LocalOpenAIEndpointConfig`, `create_local_openai_adapter(...)`, and
  `create_local_async_openai_adapter(...)`, keeping the caller-visible local
  helper surface additive while preserving the existing executor-facing adapter
  boundary and the focused Slice 1 validation checkpoint.

### T2.1 RED — model-resolution precedence contract

- Commit: `f564caa` (`test(local-models): add RED resolution precedence coverage`)
- Commands:
  - `poetry run pytest tests/test_local_models.py -q 2>&1`
  - `poetry run pre-commit run --files tests/test_local_models.py 2>&1`
- Expected result: fail before the Slice 2 model-reference types and resolution
  helper exist, while formatting/lint checks pass for the new focused test file
- Observed result:
  - `4 failed in 0.20s`
  - Ruff Check passed; Ruff Format passed
- Failure boundary:
  - `ImportError: cannot import name 'HuggingFaceModelFileReference' from
    'dynamic_agent_runner.local_models'`
  - affected tests:
    - `test_resolve_local_model_path_prefers_explicit_local_path_over_cache_and_hub`
    - `test_resolve_local_model_path_prefers_explicit_cache_root_over_default_cache`
    - `test_resolve_local_model_path_prefers_default_cache_root_over_hub_download`
    - `test_resolve_local_model_path_falls_back_to_hub_reference_after_local_misses`
- Interpretation: the RED checkpoint now fixes the approved T2.1 precedence
  order in `tests/test_local_models.py` and confirms the next implementation
  boundary is the missing Slice 2 resolution surface in
  `dynamic_agent_runner.local_models`.

### T2.2 RED — failure taxonomy contract

- Commit: `cdc1b00` (`test(local-models): add RED failure taxonomy coverage`)
- Commands:
  - `poetry run pytest tests/test_local_models.py -q 2>&1`
  - `poetry run pre-commit run --files tests/test_local_models.py 2>&1`
- Expected result: fail before the Slice 2 model-reference and runtime-facing
  failure-taxonomy surfaces exist, while the focused test file remains clean
  under formatting/lint checks
- Observed result:
  - `8 failed in 0.17s`
  - Ruff Check passed; Ruff Format passed
- Failure boundary:
  - `ImportError: cannot import name 'HuggingFaceModelFileReference' from
    'dynamic_agent_runner.local_models'`
  - `ImportError: cannot import name 'LocalModelOfflinePolicyError' from
    'dynamic_agent_runner.errors'`
  - `ImportError: cannot import name 'LocalModelResolutionError' from
    'dynamic_agent_runner.errors'`
  - `ImportError: cannot import name 'LocalModelIdentityMismatchError' from
    'dynamic_agent_runner.errors'`
  - affected tests:
    - `test_resolve_local_model_path_prefers_explicit_local_path_over_cache_and_hub`
    - `test_resolve_local_model_path_prefers_explicit_cache_root_over_default_cache`
    - `test_resolve_local_model_path_prefers_default_cache_root_over_hub_download`
    - `test_resolve_local_model_path_falls_back_to_hub_reference_after_local_misses`
    - `test_resolve_local_model_path_blocks_hub_download_when_offline_policy_disallows_network`
    - `test_resolve_local_model_path_classifies_invalid_hub_reference_as_resolution_error`
    - `test_resolve_local_model_path_classifies_cache_miss_without_remote_reference_as_resolution_error`
    - `test_validate_local_model_identity_classifies_model_mismatch_with_runtime_owned_identity`
- Interpretation: the RED checkpoint now fixes the approved T2.2 failure
  categories in `tests/test_local_models.py` and confirms the next
  implementation boundaries are the missing Slice 2 model-reference helpers in
  `dynamic_agent_runner.local_models` plus the runtime-facing local-model error
  classes in `dynamic_agent_runner.errors`.

### T2.3 GREEN — model-reference resolution helpers

- Commit: `7a11464` (`feat(local-models): add runtime model path resolution`)
- Commands:
  - `poetry run pytest tests/test_local_models.py -q 2>&1`
  - `poetry run pre-commit run --files
    src/dynamic_agent_runner/local_models.py src/dynamic_agent_runner/errors.py`
    `tests/test_local_models.py 2>&1`
- Expected result: the Slice 2 local-model helper module exposes the approved
  model-reference types, resolution precedence helpers, and minimal
  runtime-facing local-model error classes needed to satisfy the committed T2.1
  and T2.2 contracts
- Observed result:
  - `8 passed in 0.16s`
  - Ruff Check passed; Ruff Format passed
- Interpretation: `dynamic_agent_runner.local_models` now resolves explicit
  local paths, explicit cache roots, the default `~/.ollama/models` cache root,
  and explicit Hugging Face file references in the approved precedence order,
  while `dynamic_agent_runner.errors` now exposes the minimal offline,
  resolution, and identity-mismatch error classes used by the focused Slice 2
  unit surface.

### T2.4 GREEN — local endpoint failure translation

- Commit: `f4bcb0e` (`feat(local-models): translate local endpoint failures`)
- Commands:
  - `poetry run pytest tests/test_local_models.py -q 2>&1`
  - `poetry run pre-commit run --files
    src/dynamic_agent_runner/errors.py src/dynamic_agent_runner/openai_client.py`
    `src/dynamic_agent_runner/local_models.py tests/test_local_models.py 2>&1`
- Expected result: local adapters preserve model-resolution and mismatch
  boundaries while translating provider-facing local endpoint failures into
  runtime-facing connectivity vs protocol categories
- Observed result:
  - `10 passed in 0.12s`
  - Ruff Check passed; Ruff Format passed
- Interpretation: `dynamic_agent_runner.openai_client` now supports an optional
  adapter-scoped error-translation seam, and `dynamic_agent_runner.local_models`
  uses it to convert local endpoint execution failures into runtime-facing
  connectivity and protocol errors without changing the generic provider path
  for non-local callers.

### T2.5 GREEN — default Hugging Face download wiring

- Commit: `d5857dd` (`feat(local-models): wire default hub downloads`)
- Commands:
  - `poetry run pytest tests/test_local_models.py -q 2>&1`
  - `poetry run pre-commit run --files src/dynamic_agent_runner/local_models.py`
    `tests/test_local_models.py pyproject.toml poetry.lock 2>&1`
- Expected result: explicit Hub file and snapshot references can use runtime-
  owned default `huggingface_hub` wiring without live-network requirements in
  focused tests
- Observed result:
  - `12 passed in 0.19s`
  - Ruff Check passed; Ruff Format passed
- Interpretation: `dynamic_agent_runner.local_models` now lazily loads default
  `hf_hub_download(...)` and `snapshot_download(...)` helpers when caller-
  supplied download functions are absent, while `pyproject.toml` and
  `poetry.lock` now record the corresponding runtime dependency surface.

### T2.6 GREEN — authoritative model identity preservation

- Commit: `9b7078f` (`feat(local-models): preserve authoritative model
  identity`)
- Commands:
  - `poetry run pytest tests/test_local_models.py -q 2>&1`
  - `poetry run pytest tests/test_local_models.py tests/test_openai_client.py -q
    2>&1`
  - `poetry run pre-commit run --files src/dynamic_agent_runner/local_models.py`
    `src/dynamic_agent_runner/openai_client.py tests/test_local_models.py 2>&1`
- Expected result: mismatch errors preserve runtime-owned intended identity
  metadata across expected model IDs, explicit local paths, explicit Hub
  references, and endpoint-observed model names without changing the generic
  provider path for non-local callers
- Observed result:
  - `15 passed in 0.14s`
  - `44 passed in 0.18s`
  - Ruff Check passed; Ruff Format passed
- Interpretation: `dynamic_agent_runner.local_models` now preserves
  authoritative mismatch identity details in runtime-facing errors, and
  `dynamic_agent_runner.openai_client` now supports local response validation so
  endpoint-backed adapters can reject mismatched observed model names while
  keeping the generic OpenAI-compatible adapter seam intact.

### T3.1-T3.5 GREEN — direct in-process llama.cpp chat

- Commit: `58136d9` (`feat(local-models): add direct llama cpp adapter`)
- Command: `poetry run pytest tests/test_local_models.py tests/test_import.py -q`
- Observed result: `23 passed in 0.15s`
- Command:
  `poetry run pytest tests/test_local_models.py tests/test_executor.py`
  `tests/test_import.py -q`
- Observed result: `92 passed in 0.45s`
- Interpretation: direct sync and async llama.cpp adapters are package-visible,
  resolve model assets through existing local-model helpers, lazily load
  llama.cpp dependencies, translate backend failures through package-owned
  errors, normalize chat responses, and preserve strict/augmented adapter
  coverage behavior without requiring live GGUF models or a llama.cpp server.

## Pending Follow-up

### T5.0 — Separate local embedding planning

- Date: 2026-08-29
- Scope: planning-only. No source, dependency, model, network, endpoint, or
  external-tool change was made.
- Evidence: the refreshed spec, plan, and task breakdown isolate embedding
  configuration from chat adapters, executor routing, workflow metadata,
  server lifecycle, graph/RAG, and vector-store concerns.
- Council/Ponytail: Council required a named internal consumer and a
  source-inspected upstream method before execution. Ponytail accepted the
  smallest outcome: do not add a generic embedding API before a consumer exists.
- Next gate: T5.1 must resolve the consumer/output contract; it may stop for a
  user decision when no consumer is available.

### T5.1 — Standalone surface and contract readiness review

- Date: 2026-08-29
- Source inspection: installed `llama-cpp-python` is `0.3.35`.
  `llama_cpp.Llama.embed(input, normalize=False, truncate=True,
  return_count=False)` and `create_embedding(input, model=None)` are both
  available upstream candidates. `create_embedding` delegates to batched
  `embed`, returns indexed entries plus a model field, and is selected for the
  standalone contract's exact ID correlation.
- Consumer discovery: current DAR source has no `.embed(...)` or
  `.create_embedding(...)` runtime caller and no local embedding protocol.
  Context preparation keeps semantic/vector retrieval behind an injected
  selector boundary; the RAG contract keeps embedding generation and retrieval
  infrastructure caller-owned; graph-mutation explicitly defers local-embedding
  transport.
- Review: Council unanimously found no legitimate internal consumer. Ponytail
  agrees that adding a generic embedding configuration or choosing an upstream
  method now would be speculative package surface.
- Scope decision: the user authorized a standalone embedding surface as new
  scope. T5.1 remains unchecked until it specifies the caller-visible contract;
  T5.2--T5.4, model loading, networking, and public exports remain unauthorized
  until then. Graph/RAG, vector-store, executor, and chat-adapter work remain
  excluded from this authorization.
- Contract direction: the user requires batch-only `{id, string}` input and
  `EmbeddingBatchResult(model, items)` output with `{id, vector}` items,
  including a terminal one-node workflow use and
  an optional model-selectable tool use. These are two later consumers, not one
  shared implementation path: T5.5 owns the new terminal workflow node and
  T5.6 owns the existing-registry tool exposure. The model selects invocation,
  never embedding-model identity.
- Limits decision: the user selected split transport limits. The producer and
  terminal node admit 128 entries / 64 KiB each / 1 MiB total / 8,192
  dimensions / 1,048,576 scalars / 16 MiB output. The model tool admits eight
  entries / 8 KiB each / 64 KiB total / 2,048 dimensions / 16,384 scalars /
  256 KiB output. Its structured result is `{model, items: [{id, vector}]}`.
- Model identity decision: DAR supplies the resolved host-bound identity to
  `create_embedding`; a returned model mismatch raises the existing
  `LocalModelIdentityMismatchError` before output.
- Error decision: the user approved `EmbeddingError(LocalModelError)` with
  `EmbeddingInputError`, `EmbeddingResultError`, and
  `EmbeddingExecutionError`; existing local resolution, offline, and identity
  errors retain their current meanings. A failed batch has no partial result.
- Public API decision: use frozen `EmbeddingInputItem` and
  `EmbeddingVectorItem` dataclasses, `EmbeddingBatchResult`, dedicated
  `LlamaCppLocalEmbeddingConfig` and sync/async embedding adapters with
  `.embed(items)`, plus
  `create_llama_cpp_local_embedding_adapter` /
  `create_llama_cpp_local_async_embedding_adapter` factories. This is separate
  from chat configuration and `ModelAdapter`.
- Delivery review: Council unanimously approved the completed contract after
  its result-shape, host-identity, and exact public-entry-point corrections.
  Ponytail confirms one shared producer plus the existing coordinator is the
  smallest design. T5.1 is implementation-ready and delivered as a
  documentation-only decision slice; T5.2 is the next executable task.
- Council/Ponytail: both integrations require separate manifest/executor and
  registry/coordinator contracts. Reuse one host-bound batch producer; do not
  add a second embedding path, remote fallback, model-selected profile, or
  approval bypass. T5.1 remains the gate for fixed resource bounds and typed
  error/result contracts.

### T5.2 RED — standalone embedding configuration and execution contract

- Date: 2026-08-29
- Command: `poetry run pytest tests/test_local_models.py tests/test_import.py -q`
- Observed result: `30 failed, 106 passed`; every failure is the intentionally
  absent T5.3 embedding public API or error taxonomy.
- Lint: `poetry run ruff check tests/test_local_models.py tests/test_import.py`
  passed.
- Coverage: immutable public values; sync/async factories; zero-I/O preflight;
  explicit/caller-cache/default-Hub/download resolution order; offline policy;
  UTF-8 and batch bounds; indexed response normalization; result/input/provider
  errors; no partial output; and raw text/vector redaction.
- Council/Ponytail: Council approved after checking resolver-path observation,
  offline/download ordering, byte boundaries, and malformed-result coverage.
  Ponytail retained the deliberately small test-local embedding fake and no
  production-only test protocol. T5.3 is now the sole GREEN implementation
  boundary.

### T5.3 GREEN — standalone llama.cpp embedding producer

- Date: 2026-08-29
- Commands:
  - `poetry run pytest tests/test_local_models.py tests/test_import.py -q`
  - `poetry run pytest -q`
- Observed result: `141 passed` for the focused local-model/import suite and
  `1534 passed, 1 skipped, 6 deselected` for the full suite.
- Scope: a distinct immutable embedding config and typed result/input values;
  sync/async standalone adapters; lazy caller-controlled resolution and
  embedding-only backend construction; strict bounded indexed-result
  normalization; package-owned embedding errors; and package-root exports.
- Boundaries: no chat adapter change, executor routing, workflow node, tool,
  endpoint, capability, network, or live model use. Raw input/vector data is
  excluded from errors, including malformed Unicode and oversized numeric cases.
- Council/Ponytail: Council approved the final forced-loader, byte-vector,
  huge-integer, and Unicode validation corrections. Ponytail confirms reuse of
  the existing resolver and a private normalizer without a generic provider or
  consumer abstraction. T5.4 is the next validation/docs checkpoint.

### T5.4 GREEN — producer boundary and fake-only validation receipt

- Implementation: commit `27826d8` exposes only frozen embedding input/vector/
  batch-result values, the immutable host-bound embedding config, typed
  embedding errors, sync/async standalone factories, and adapters. It is not a
  chat `ModelAdapter`.
- Commands and results:
  - `poetry run pytest tests/test_local_models.py tests/test_import.py -q`:
    `141 passed in 2.15s`.
  - `poetry run pytest -q`: `1535 passed, 1 skipped, 6 deselected, 66 warnings`
    in 13.15s.
  - `poetry run ruff check src/dynamic_agent_runner/local_models.py
    src/dynamic_agent_runner/errors.py src/dynamic_agent_runner/__init__.py
    tests/test_local_models.py tests/test_import.py`: passed.
  - `poetry run ruff format --check src/dynamic_agent_runner/local_models.py
    src/dynamic_agent_runner/errors.py src/dynamic_agent_runner/__init__.py
    tests/test_local_models.py tests/test_import.py`: `5 files already formatted`.
  - `poetry run pre-commit run --files
    specs/llama-cpp-local-model/spec.md specs/llama-cpp-local-model/plan.md
    specs/llama-cpp-local-model/tasks.md specs/llama-cpp-local-model/validation.md
    src/dynamic_agent_runner/local_models.py src/dynamic_agent_runner/errors.py
    src/dynamic_agent_runner/__init__.py tests/test_local_models.py
    tests/test_import.py`: passed.
- Fake-only evidence: tests cover frozen exports, no-I/O factory construction,
  input rejection before resolution, local/cache/Hub/offline/download ordering,
  forced separate `embedding=True` loader construction, sync/async one-call
  execution, host identity and indexed bounded normalization, malformed Unicode
  and scalar/vector cases, raw-data redaction, and no partial result.
- Explicit exclusions: no chat adapter, executor/workflow node, registry tool,
  approval path, capability advertisement, endpoint, RAG/vector store, live
  llama.cpp/Hugging Face/model/network/server, Fastmail, OAuth, or manual
  acceptance ran. T5.5 and T5.6 remain separate; a live embedding is a
  separately human-authorized manual step.
