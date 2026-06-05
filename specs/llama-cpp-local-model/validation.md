# llama.cpp Local-Model Adapter Validation Log

Status: in progress

## Scope

- Feature: `specs/llama-cpp-local-model/spec.md`
- Plan: `specs/llama-cpp-local-model/plan.md`
- Tasks: `specs/llama-cpp-local-model/tasks.md`
- Current checkpoint: T1.1 and T1.2 RED tests are committed, T1.3 helper
  implementation landed in commit `6d269ad`, T1.4 provider-seam wiring landed
  in commit `ee0bf33`, T1.5 package-root exports landed in commit `dd37c62`, and
  the targeted Slice 1 checks are GREEN; T2.1 RED precedence tests are now
  committed in `f564caa`, and T2.2 is the next pending step

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

## Pending Follow-up

- T2.2 — add failing tests in `tests/test_local_models.py` for offline-policy
  blocks, invalid Hub references, cache misses, and model-mismatch
  classification
- T4.4 — run `poetry run pytest tests/test_local_models.py -q` when the
  local-model helper module and resolution logic exist
