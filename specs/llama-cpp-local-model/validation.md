# llama.cpp Local-Model Adapter Validation Log

Status: in progress

## Scope

- Feature: `specs/llama-cpp-local-model/spec.md`
- Plan: `specs/llama-cpp-local-model/plan.md`
- Tasks: `specs/llama-cpp-local-model/tasks.md`
- Current checkpoint: T1.1 and T1.2 RED tests are committed; no production
  `src/dynamic_agent_runner/local_models.py` implementation exists yet

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

## Pending Follow-up

- T1.3 — implement `src/dynamic_agent_runner/local_models.py`
- T4.1 / T4.2 — rerun targeted pytest commands once Slice 1 implementation turns
  GREEN
