# llama.cpp Local-Model Adapter Task List

Status: active feature record; Slices 1-3 complete, optional embedding follow-up
unscheduled

## Prerequisites

- Spec: `specs/llama-cpp-local-model/spec.md`
- Plan: `specs/llama-cpp-local-model/plan.md`
- Data model: none
- Contracts: none

## Status

- State: T1.1 RED helper-contract tests are complete in commit `a5798cc`
  (`test(local-models): add RED tests for local endpoint helpers`) and T1.2 RED
  executor-routing tests are complete in commit `b79f124`
  (`test(local-models): add RED executor routing coverage`); T1.3 helper
  implementation is complete in commit `6d269ad`
  (`feat(local-models): add local openai endpoint helpers`); T1.4 provider-seam
  wiring is complete in commit `ee0bf33`
  (`refactor(local-models): route helpers through adapter factories`); T1.5
  package-root exports are complete in commit `dd37c62`
  (`feat(local-models): export local endpoint helpers`); T2.1 RED
  model-resolution precedence tests are complete in commit `f564caa`
  (`test(local-models): add RED resolution precedence coverage`); T2.2 RED
  failure-taxonomy tests are complete in commit `cdc1b00`
  (`test(local-models): add RED failure taxonomy coverage`); T2.3
  model-reference resolution implementation is complete in commit `7a11464`
  (`feat(local-models): add runtime model path resolution`); T2.4
  endpoint-failure translation is complete in commit `f4bcb0e`
  (`feat(local-models): translate local endpoint failures`); T2.5 default
  Hugging Face download wiring is complete in commit `d5857dd`
  (`feat(local-models): wire default hub downloads`); T2.6 authoritative
  model-identity preservation is complete in commit `9b7078f`
  (`feat(local-models): preserve authoritative model identity`); the Slice 2
  validation checkpoint is complete through T4.4 and the first validation pass
  remains complete through T4.5
- Current execution gate: direct in-process llama.cpp chat is implemented
  through T3.5; optional embedding follow-up remains unscheduled
- Scope rule: keep completed endpoint-wrapper work separate from the next direct
  in-process llama.cpp chat slice; do not merge graph-mutation or
  runtime-managed server work into these tasks

## Slice 1 — Endpoint-backed local chat through the existing provider seam

- [x] T1.1 [tests] Add failing tests in `tests/test_openai_client.py` for a
      caller-facing local endpoint helper that builds a local adapter through the
      existing provider seam.
  - Spec: FR-1, FR-2, FR-3, FR-6
  - Plan: Technical Summary; Architecture and Data Flow
  - Files/components: `tests/test_openai_client.py`,
    `src/dynamic_agent_runner/local_models.py`
  - Domain context: local endpoint config must translate into existing adapter
    metadata instead of creating a new executor path
  - Depends on: none
  - Validation: `poetry run pytest tests/test_openai_client.py -q`
  - Evidence: tests fail before the helper exists and pass once the helper
    returns correctly configured adapters
  - Completed in commit `a5798cc` (`test(local-models): add RED tests for local
    endpoint helpers`)
  - RED: `poetry run pytest tests/test_openai_client.py -q 2>&1` — failed with
    `ModuleNotFoundError: No module named 'dynamic_agent_runner.local_models'`
    after adding helper-contract coverage for `LocalOpenAIEndpointConfig`,
    `create_local_openai_adapter(...)`, and
    `create_local_async_openai_adapter(...)`

- [x] T1.2 [tests] Add failing executor coverage in `tests/test_executor.py`
      proving the then-current `local_only` routing worked for the caller-built
      local adapter. Later model-adapter coverage work replaced this routing
      metadata with `model_adapter_coverage="strict"` for local-only client
      intent.
  - Spec: FR-1, FR-6
  - Plan: Current Repository State; Architecture and Data Flow
  - Files/components: `tests/test_executor.py`,
    `src/dynamic_agent_runner/executor.py`
  - Domain context: local routing depended on adapter `models` plus `is_local`
    at the time; current client intent uses strict adapter coverage.
  - Depends on: none
  - Validation: `poetry run pytest tests/test_executor.py -q`
  - Evidence: a historical `local_only` request selected the local adapter
    without any new executor-specific branch
  - Completed in commit `b79f124` (`test(local-models): add RED executor
    routing coverage`)
  - RED: `poetry run pytest tests/test_executor.py -q 2>&1` — failed with
    `ModuleNotFoundError: No module named 'dynamic_agent_runner.local_models'`
    after adding
    `test_prepare_model_input_routes_local_only_requests_to_helper_built_local_adapter`
    to prove helper-built local adapters satisfied the then-current
    `local_only` routing via adapter `models` plus `is_local`

- [x] T1.3 [implementation] Add `src/dynamic_agent_runner/local_models.py` with
      the first-slice local endpoint config and helper factory.
  - Spec: FR-1, FR-2, FR-3, FR-6
  - Plan: Chosen approach; Caller-facing local endpoint helper contract
  - Files/components: `src/dynamic_agent_runner/local_models.py`
  - Depends on: T1.1
  - Validation: `poetry run pytest tests/test_openai_client.py -q`
  - Evidence: the helper builds `OpenAIClientAdapter` /
    `AsyncOpenAIClientAdapter` with caller aliases and `is_local=True`
  - Completed in commit `6d269ad` (`feat(local-models): add local openai
    endpoint helpers`)
  - GREEN:
    - `poetry run pytest tests/test_openai_client.py -q 2>&1` — `27 passed in
      0.17s`
    - `poetry run pytest tests/test_executor.py -q 2>&1` — `50 passed in
      0.41s`

- [x] T1.4 [implementation] Wire the new helper into the existing provider seam
      without changing request construction or response normalization ownership.
  - Spec: FR-2, FR-4, FR-6
  - Plan: Affected Areas; Architecture and Data Flow
  - Files/components: `src/dynamic_agent_runner/openai_client.py`,
    `src/dynamic_agent_runner/local_models.py`
  - Depends on: T1.3
  - Validation: `poetry run pytest tests/test_openai_client.py -q`
  - Evidence: local helper output still uses `build_openai_request(...)` and
    `normalize_openai_response(...)` through the existing adapter path
  - Completed in commit `ee0bf33` (`refactor(local-models): route helpers
    through adapter factories`)
  - GREEN:
    - `poetry run pytest tests/test_openai_client.py -q 2>&1` — `29 passed in
      0.15s`
    - `poetry run pytest tests/test_executor.py -q 2>&1` — `50 passed in
      0.38s`

- [x] T1.5 [implementation] Export any approved caller-visible local helper or
      config type from the package root.
  - Spec: FR-1, FR-3
  - Plan: Affected Areas; Caller-facing local endpoint helper contract
  - Files/components: `src/dynamic_agent_runner/__init__.py`,
    `tests/test_import.py`
  - Depends on: T1.3
  - Validation: `poetry run pytest tests/test_import.py -q`
  - Evidence: import-level tests can load the approved public helper surface
  - Completed in commit `dd37c62` (`feat(local-models): export local endpoint
    helpers`)
  - GREEN:
    - `poetry run pytest tests/test_import.py -q 2>&1` — `1 passed in 0.19s`

## Slice 2 — Runtime-owned model reference resolution and failure taxonomy

- [x] T2.1 [tests] Add failing tests in `tests/test_local_models.py` for the
      approved model-resolution precedence order.
  - Spec: FR-5, FR-5b
  - Plan: Slice 2 — Runtime-owned model reference resolution and failure
    taxonomy
  - Files/components: `tests/test_local_models.py`,
    `src/dynamic_agent_runner/local_models.py`
  - Depends on: T1.3
  - Validation: `poetry run pytest tests/test_local_models.py -q`
  - Evidence: coverage proves precedence across explicit local path, explicit
    cache root, default cache root, and explicit Hub reference
  - Completed in commit `f564caa` (`test(local-models): add RED resolution
    precedence coverage`)
  - RED: `poetry run pytest tests/test_local_models.py -q 2>&1` — failed with
    `ImportError: cannot import name 'HuggingFaceModelFileReference' from
    'dynamic_agent_runner.local_models'` after adding precedence coverage for
    explicit local path, explicit cache root, default cache root, and explicit
    Hub-file fallback resolution

- [x] T2.2 [tests] Add failing tests in `tests/test_local_models.py` for offline
      policy blocks, invalid Hub references, cache misses, and model-mismatch
      classification.
  - Spec: FR-5b, FR-5c
  - Plan: Later model-reference contract
  - Files/components: `tests/test_local_models.py`,
    `src/dynamic_agent_runner/errors.py`,
    `src/dynamic_agent_runner/local_models.py`
  - Depends on: T2.1
  - Validation: `poetry run pytest tests/test_local_models.py -q`
  - Evidence: each failure mode maps to a clear runtime-facing category
  - Completed in commit `cdc1b00` (`test(local-models): add RED failure taxonomy
    coverage`)
  - RED: `poetry run pytest tests/test_local_models.py -q 2>&1` — failed with
    import boundaries in both `dynamic_agent_runner.local_models` and
    `dynamic_agent_runner.errors`, confirming the missing Slice 2
    model-reference and failure-taxonomy surfaces after adding offline-policy,
    invalid Hub-reference, cache-miss, and model-mismatch coverage

- [x] T2.3 [implementation] Extend `src/dynamic_agent_runner/local_models.py`
      with explicit model-reference types and resolution helpers.
  - Spec: FR-5, FR-5b
  - Plan: Slice 2 — Runtime-owned model reference resolution and failure
    taxonomy
  - Files/components: `src/dynamic_agent_runner/local_models.py`,
    `src/dynamic_agent_runner/errors.py`
  - Depends on: T2.1, T2.2
  - Validation: `poetry run pytest tests/test_local_models.py -q`
  - Evidence: runtime-owned helpers resolve assets using the approved precedence
    order without taking over server lifecycle
  - Completed in commit `7a11464` (`feat(local-models): add runtime model path
    resolution`)
  - GREEN:
    - `poetry run pytest tests/test_local_models.py -q 2>&1` — `8 passed in
      0.16s`
    - `poetry run pre-commit run --files
      src/dynamic_agent_runner/local_models.py src/dynamic_agent_runner/errors.py`
      `tests/test_local_models.py 2>&1` — Ruff Check passed; Ruff Format passed

- [x] T2.4 [implementation] Add runtime-facing error translation for
      model-resolution, endpoint-connectivity, endpoint-protocol, and
      model-mismatch failures.
  - Spec: FR-5c
  - Plan: Later model-reference contract; Risks and Mitigations
  - Files/components: `src/dynamic_agent_runner/errors.py`,
    `src/dynamic_agent_runner/local_models.py`,
    `src/dynamic_agent_runner/openai_client.py`
  - Depends on: T2.2, T2.3
  - Validation: `poetry run pytest tests/test_local_models.py -q`
  - Evidence: callers can distinguish resolution failures from endpoint failures
    without reading provider-specific raw exceptions
  - Completed in commit `f4bcb0e` (`feat(local-models): translate local endpoint
    failures`)
  - GREEN:
    - `poetry run pytest tests/test_local_models.py -q 2>&1` — `10 passed in
      0.12s`
    - `poetry run pre-commit run --files src/dynamic_agent_runner/errors.py
      src/dynamic_agent_runner/openai_client.py
      src/dynamic_agent_runner/local_models.py tests/test_local_models.py 2>&1`
      — Ruff Check passed; Ruff Format passed

- [x] T2.5 [implementation] Add `huggingface_hub` dependency wiring only when
      the resolution slice is actively implemented.
  - Spec: FR-5b
  - Plan: Affected Areas; Risks and Mitigations
  - Files/components: `pyproject.toml`, `poetry.lock`
  - Depends on: T2.3
  - Validation: `poetry run pytest tests/test_local_models.py -q`
  - Evidence: explicit Hub file and snapshot references can be exercised through
    isolated tests without live-network requirements
  - Completed in commit `d5857dd` (`feat(local-models): wire default hub
    downloads`)
  - GREEN:
    - `poetry run pytest tests/test_local_models.py -q 2>&1` — `12 passed in
      0.19s`
    - `poetry run pre-commit run --files src/dynamic_agent_runner/local_models.py
      tests/test_local_models.py pyproject.toml poetry.lock 2>&1` — Ruff Check
      passed; Ruff Format passed

- [x] T2.6 [implementation] Preserve authoritative model identity metadata for
      mismatch reporting when aliases, local paths, or Hub references are used.
  - Spec: FR-3, FR-5c
  - Plan: Caller-facing local endpoint helper contract; Later model-reference
    contract
  - Files/components: `src/dynamic_agent_runner/local_models.py`,
    `src/dynamic_agent_runner/openai_client.py`,
    `tests/test_local_models.py`
  - Depends on: T2.2, T2.3
  - Validation: `poetry run pytest tests/test_local_models.py -q`
  - Evidence: mismatch errors report the runtime-owned intended identity rather
    than a guessed provider response
  - Completed in commit `9b7078f` (`feat(local-models): preserve authoritative
    model identity`)
  - GREEN:
    - `poetry run pytest tests/test_local_models.py -q 2>&1` — `15 passed in
      0.14s`
    - `poetry run pytest tests/test_local_models.py tests/test_openai_client.py
      -q 2>&1` — `44 passed in 0.18s`
    - `poetry run pre-commit run --files
      src/dynamic_agent_runner/local_models.py
      src/dynamic_agent_runner/openai_client.py tests/test_local_models.py 2>&1`
      — Ruff Check passed; Ruff Format passed

## Slice 3 — Direct in-process llama.cpp chat

- [x] T3.1 [tests] Add RED tests for direct llama.cpp config and package-root
      factory exports without importing `llama_cpp` at package import time.
  - Spec: FR-1, FR-2, FR-6
  - Plan: Slice 3 — Direct in-process llama.cpp chat
  - Files/components: `tests/test_local_models.py`,
    `tests/test_import.py`, `src/dynamic_agent_runner/local_models.py`,
    `src/dynamic_agent_runner/__init__.py`
  - Validation: `poetry run pytest tests/test_local_models.py -q`
  - Expected RED: direct llama.cpp config/factories do not exist yet.
  - Evidence: package import remains lightweight and direct llama.cpp helpers
    are caller-visible.
  - RED:
    - `poetry run pytest tests/test_local_models.py tests/test_import.py -q`
      — failed with missing `LlamaCppLocalModelConfig`,
      `create_llama_cpp_local_adapter(...)`, and
      `create_llama_cpp_local_async_adapter(...)`
  - GREEN:
    - `poetry run pytest tests/test_local_models.py tests/test_import.py -q`
      — `23 passed in 0.15s`

- [x] T3.2 [tests] Add RED tests for direct in-process model resolution,
      dependency loading, and local backend failure translation.
  - Spec: FR-2, FR-5, FR-5b, FR-5c, FR-6
  - Plan: Slice 3 — Direct in-process llama.cpp chat
  - Files/components: `src/dynamic_agent_runner/local_models.py`,
    `tests/test_local_models.py`
  - Depends on: T3.1
  - Validation: `poetry run pytest tests/test_local_models.py -q`
  - Expected RED: no direct in-process llama.cpp adapter loads resolved model
    assets or translates backend failures.
  - Evidence: missing `llama_cpp`, model-load failures, and generation failures
    fail through package-owned errors without trying to start a server.
  - RED:
    - Covered by the same T3.1 RED run because the direct adapter surface did not
      exist yet.
  - GREEN:
    - `poetry run pytest tests/test_local_models.py tests/test_import.py -q`
      — `23 passed in 0.15s`

- [x] T3.3 [implementation] Add direct sync llama.cpp adapter construction using
      documented `llama_cpp.Llama` chat APIs and existing model-resolution
      helpers.
  - Spec: FR-1, FR-2, FR-4, FR-5, FR-5b, FR-5c, FR-6
  - Plan: Slice 3 — Direct in-process llama.cpp chat
  - Files/components: `src/dynamic_agent_runner/local_models.py`,
    `tests/test_local_models.py`
  - Depends on: T3.2
  - Validation: `poetry run pytest tests/test_local_models.py -q`
  - Evidence: direct local chat works through fake llama.cpp backends, advertises
    model aliases, resolves assets, and normalizes generated text into the
    runtime response contract.
  - GREEN:
    - `poetry run pytest tests/test_local_models.py tests/test_import.py -q`
      — `23 passed in 0.15s`

- [x] T3.4 [implementation] Add async direct llama.cpp adapter wrapper without
      requiring an undocumented native async llama.cpp API.
  - Spec: FR-1, FR-2, FR-4
  - Plan: Slice 3 — Direct in-process llama.cpp chat
  - Files/components: `src/dynamic_agent_runner/local_models.py`,
    `tests/test_local_models.py`, `tests/test_executor.py`
  - Depends on: T3.3
  - Validation:
    `poetry run pytest tests/test_local_models.py tests/test_executor.py -q`
  - Evidence: async workflows can use direct llama.cpp adapters without blocking
    the event loop directly in adapter code.
  - GREEN:
    - `poetry run pytest tests/test_local_models.py tests/test_executor.py
      tests/test_import.py -q` — `92 passed in 0.45s`

- [x] T3.5 [tests/implementation] Prove strict and augmented adapter coverage
      behavior with direct llama.cpp adapters.
  - Spec: FR-1
  - Plan: Slice 3 — Direct in-process llama.cpp chat
  - Files/components: `tests/test_executor.py`,
    `src/dynamic_agent_runner/local_models.py`
  - Depends on: T3.4
  - Validation: `poetry run pytest tests/test_executor.py -q`
  - Evidence: strict mode keeps direct llama.cpp adapters authoritative, while
    augmented mode may still use default OpenAI coverage for eligible misses.
  - GREEN:
    - `poetry run pytest tests/test_local_models.py tests/test_executor.py
      tests/test_import.py -q` — `92 passed in 0.45s`

## Slice 5 — Optional embedding follow-up

- [ ] T5.0 [planning] Add a focused embedding task breakdown before implementing
      separate local embedding configuration.
  - Spec: FR-3
  - Plan: optional embedding follow-up
  - Files/components: `specs/llama-cpp-local-model/tasks.md`,
    `src/dynamic_agent_runner/local_models.py`, `tests/test_local_models.py`
  - Depends on: Slice 3
  - Validation: spec/task review
  - Evidence: chat and embedding configuration can remain related but distinct

## Slice 4 — Validation and artifact completion

- [x] T4.1 [validation] Run `poetry run pytest tests/test_openai_client.py -q`
      after Slice 1 changes.
  - Spec: FR-1, FR-2, FR-3, FR-4, FR-6
  - Plan: Verification Strategy
  - Files/components: `tests/test_openai_client.py`
  - Depends on: T1.4
  - Validation: `poetry run pytest tests/test_openai_client.py -q`
  - Evidence: adapter/provider behavior remains green with fake-client coverage
  - Completed during the post-T1.5 Slice 1 checkpoint refresh
  - GREEN:
    - `poetry run pytest tests/test_openai_client.py tests/test_executor.py`
      `tests/test_import.py -q 2>&1` — `80 passed in 0.47s`

- [x] T4.2 [validation] Run `poetry run pytest tests/test_executor.py -q` after
      local routing changes.
  - Spec: FR-1, FR-6
  - Plan: Verification Strategy
  - Files/components: `tests/test_executor.py`
  - Depends on: T1.4
  - Validation: `poetry run pytest tests/test_executor.py -q`
  - Evidence: executor local routing worked through adapter metadata at the
    Slice 1 checkpoint
  - Completed during the post-T1.5 Slice 1 checkpoint refresh
  - GREEN:
    - `poetry run pytest tests/test_openai_client.py tests/test_executor.py`
      `tests/test_import.py -q 2>&1` — `80 passed in 0.47s`

- [x] T4.3 [validation] Run `poetry run pytest tests/test_import.py -q` if new
      caller-visible exports are added.
  - Spec: FR-1, FR-3
  - Plan: Verification Strategy
  - Files/components: `tests/test_import.py`
  - Depends on: T1.5
  - Validation: `poetry run pytest tests/test_import.py -q`
  - Evidence: package-root imports remain stable
  - Completed during T1.5 export validation in commit `dd37c62`
  - GREEN:
    - `poetry run pytest tests/test_import.py -q 2>&1` — `1 passed in 0.19s`

- [x] T4.4 [validation] Run `poetry run pytest tests/test_local_models.py -q`
      when the local-model helper module and resolution logic exist.
  - Spec: FR-5, FR-5b, FR-5c
  - Plan: Verification Strategy
  - Files/components: `tests/test_local_models.py`
  - Depends on: T2.6
  - Validation: `poetry run pytest tests/test_local_models.py -q`
  - Evidence: local config, resolution, and error taxonomy checks pass without
    live-network requirements
  - Completed during T2.6 validation in commit `9b7078f`
  - GREEN:
    - `poetry run pytest tests/test_local_models.py -q 2>&1` — `15 passed in
      0.14s`

- [x] T4.5 [validation/docs] Run focused `pre-commit` and create
      `specs/llama-cpp-local-model/validation.md` when implementation begins.
  - Spec: Validation Status
  - Plan: Verification Strategy
  - Files/components: `specs/llama-cpp-local-model/validation.md`,
    `src/dynamic_agent_runner/local_models.py`,
    `src/dynamic_agent_runner/openai_client.py`,
    `src/dynamic_agent_runner/__init__.py`, `src/dynamic_agent_runner/errors.py`,
    `tests/test_local_models.py`, `tests/test_openai_client.py`,
    `tests/test_executor.py`, `tests/test_import.py`
  - Depends on: T4.1, T4.2
  - Validation: `pre-commit run --files src/dynamic_agent_runner/local_models.py`
    `src/dynamic_agent_runner/openai_client.py`
    `src/dynamic_agent_runner/__init__.py`
    `src/dynamic_agent_runner/errors.py` `tests/test_local_models.py`
    `tests/test_openai_client.py` `tests/test_executor.py`
    `tests/test_import.py` `2>&1`
  - Evidence: validation commands and outcomes are recorded in the feature's
    validation artifact
  - Completed during the post-T1.5 Slice 1 checkpoint refresh
  - GREEN:
    - `poetry run pre-commit run --files
      src/dynamic_agent_runner/local_models.py
      src/dynamic_agent_runner/openai_client.py
      src/dynamic_agent_runner/__init__.py tests/test_openai_client.py
      tests/test_executor.py tests/test_import.py 2>&1` — Ruff Check passed;
      Ruff Format passed

## Ordering Notes

- Slice 1 must land before any model-resolution or embedding work.
- T1.1 and T1.2 should establish the first executable checks before the helper
  surface is implemented.
- Slice 2 should not begin until the endpoint-backed local chat checkpoint is
  stable.
- Slice 3 is the next direct in-process llama.cpp chat slice.
- Slice 5 embedding follow-up remains optional and should not block direct local
  chat delivery.

## Checkpoints

- Checkpoint 1 — caller-owned endpoint-backed local chat adapter works through
  the existing provider seam and satisfied the then-current local routing tests.
- Checkpoint 2 — runtime-owned model reference resolution and failure taxonomy
  work without taking ownership of server lifecycle.
- Checkpoint 3 — direct in-process llama.cpp chat works without requiring a
  server.
- Checkpoint 4 — optional embedding follow-up remains separate from
  graph-mutation delivery.

## Validation Commands

- `poetry run pytest tests/test_openai_client.py -q` — adapter/provider coverage
- `poetry run pytest tests/test_executor.py -q` — adapter coverage and selection
  coverage
- `poetry run pytest tests/test_import.py -q` — package export coverage when
  needed
- `poetry run pytest tests/test_local_models.py -q` — local-model helper and
  resolution coverage once the module exists

## Domain and Boundary Notes

- Domain assumptions verified: local execution continues to reuse the current
  adapter/provider seam; server lifecycle remains caller-owned or
  deployer-owned.
- Bounded-context or translation checks: local-model config must translate into
  provider config and adapter metadata rather than into executor-specific logic.
