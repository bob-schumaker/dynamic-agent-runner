# llama.cpp Local-Model Adapter Validation Log

Status: in progress

## Scope

- Feature: `specs/llama-cpp-local-model/spec.md`
- Plan: `specs/llama-cpp-local-model/plan.md`
- Tasks: `specs/llama-cpp-local-model/tasks.md`
- Current checkpoint: T1.1 and T1.2 RED tests are committed, T1.3 helper
  implementation landed in commit `6d269ad`, T1.4 provider-seam wiring landed
  in commit `ee0bf33`, and the targeted Slice 1 checks are GREEN; T1.5 is the
  next pending step

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

## Pending Follow-up

- T1.5 — export any approved caller-visible local helper or config type from the
  package root
- T4.1 / T4.2 — rerun targeted pytest commands after later Slice 1 follow-up
  changes when additional implementation lands
