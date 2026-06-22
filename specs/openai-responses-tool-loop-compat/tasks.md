# OpenAI Responses Tool Loop Compatibility Tasks

## Metadata

- Feature slug: `openai-responses-tool-loop-compat`
- Slice: R1 core compatibility
- Status: implementation candidate tasks
- Date: 2026-06-22
- Spec: [`spec.md`](spec.md)
- Plan: [`plan.md`](plan.md)

## Slice R1: Core Responses Tool-Loop Compatibility

- [x] R1.1 RED: Add stream normalization tests in
      `tests/test_openai_client.py`.
  - Spec: FR-1
  - Files/components: `tests/test_openai_client.py`,
    `src/dynamic_agent_runner/openai_client.py`
  - Cases: sync stream with `response.output_item.done` function call and empty
    completed output; completed output precedence; async stream parity.
  - Validation:
    `poetry run pytest tests/test_openai_client.py -q -k "stream or responses"`
  - Evidence: `poetry run pytest tests/test_openai_client.py -q -k
    "stream or responses"` failed with the new streamed function-call cases
    before implementation.

- [x] R1.2 GREEN: Preserve streamed Responses output items in
      `_normalize_openai_stream_events(...)`.
  - Spec: FR-1
  - Files/components: `src/dynamic_agent_runner/openai_client.py`
  - Depends on: R1.1
  - Validation:
    `poetry run pytest tests/test_openai_client.py -q -k "stream or responses"`
  - Evidence: `poetry run pytest tests/test_openai_client.py -q -k
    "stream or responses"` passed with 5 tests after implementation.

- [x] R1.3 RED: Add ChatGPT/Codex request-preparation tests for structured
      tool-loop transcript items.
  - Spec: FR-2, FR-3
  - Files/components: `tests/test_openai_client.py`,
    `src/dynamic_agent_runner/openai_client.py`
  - Cases: structured tool call becomes Responses `function_call`; structured
    tool result becomes matching `function_call_output`; original arguments are
    preserved; system/developer instructions still hoist.
  - Validation:
    `poetry run pytest tests/test_openai_client.py -q -k "chatgpt or codex"`
  - Evidence: `poetry run pytest tests/test_openai_client.py -q -k
    "chatgpt or codex"` failed before implementation because structured
    transcript items were passed through unchanged.

- [x] R1.4 RED: Add executor loop transcript tests that preserve original tool
      call data while keeping non-Codex fake adapter compatibility.
  - Spec: FR-2
  - Files/components: `tests/test_executor.py`,
    `src/dynamic_agent_runner/executor.py`
  - Cases: follow-up request through the existing fake adapter still receives a
    Chat Completions-style assistant/tool transcript; model-facing output is
    used; original tool-call arguments are available to provider rendering.
  - Validation:
    `poetry run pytest tests/test_executor.py -q -k "model_tool_loop"`
  - Evidence: `poetry run pytest tests/test_executor.py -q -k
    "model_tool_loop or chatgpt_codex"` failed before implementation because
    ChatGPT/Codex follow-up input still used assistant/tool messages.

- [x] R1.5 GREEN: Implement internal structured tool-loop transcript rendering.
  - Spec: FR-2, FR-3
  - Files/components: `src/dynamic_agent_runner/executor.py`,
    `src/dynamic_agent_runner/openai_client.py`
  - Depends on: R1.3, R1.4
  - Validation:

    ```bash
    poetry run pytest \
      tests/test_openai_client.py \
      tests/test_executor.py \
      -q \
      -k "chatgpt or codex or model_tool_loop"
    ```

  - Evidence: provider-specific request preparation and non-Codex loop tests
    pass together with 10 OpenAI adapter tests and 4 executor tests.

- [x] R1.6 RED: Add validation tests for `tool_choice_policy`.
  - Spec: FR-4
  - Files/components: `tests/test_validation.py`,
    `src/dynamic_agent_runner/validation.py`
  - Cases: valid runtime policy; valid node-local policy; invalid enum values;
    node-local `tool_choice` plus `tool_choice_policy` conflict.
  - Validation:
    `poetry run pytest tests/test_validation.py -q -k "tool_choice_policy or tool_choice"`
  - Evidence: `poetry run pytest tests/test_validation.py -q -k
    "tool_choice_policy or tool_choice"` failed before validation rejected bad
    policy values and legacy node conflicts.

- [x] R1.7 RED: Add plan/prepared-node tests for `tool_choice_policy`.
  - Spec: FR-4
  - Files/components: `tests/test_executor.py`,
    `src/dynamic_agent_runner/models.py`
  - Cases: runtime policy is present on `ExecutionPlan`; node-local policy is
    present on `PreparedNode`; legacy `tool_choice` remains present when no
    policy is configured.
  - Validation:
    `poetry run pytest tests/test_executor.py -q -k "tool_choice_policy or prepare_execution_plan"`
  - Evidence: `poetry run pytest tests/test_executor.py -q -k
    "tool_choice_policy or prepare_execution_plan"` failed before
    `ExecutionPlan` and `PreparedNode` preserved the policy.

- [x] R1.8 GREEN: Add `tool_choice_policy` parsing and validation.
  - Spec: FR-4
  - Files/components: `src/dynamic_agent_runner/models.py`,
    `src/dynamic_agent_runner/validation.py`
  - Depends on: R1.6, R1.7
  - Validation:

    ```bash
    poetry run pytest \
      tests/test_validation.py \
      tests/test_executor.py \
      -q \
      -k "tool_choice_policy or tool_choice or prepare_execution_plan"
    ```

  - Evidence: validation and plan-preparation tests pass with runtime policy,
    node policy, invalid enum, and conflict coverage.

- [x] R1.9 RED: Add executor tests for phase-aware `tool_choice_policy`.
  - Spec: FR-4, FR-6
  - Files/components: `tests/test_executor.py`,
    `src/dynamic_agent_runner/executor.py`
  - Cases: initial request sends `tool_choice: required`; post-tool request
    omits forced `tool_choice` when `after_tool_result: auto`; node-local policy
    overrides runtime policy; legacy `tool_choice` behavior remains unchanged
    without explicit policy.
  - Validation:
    `poetry run pytest tests/test_executor.py -q -k "tool_choice_policy or model_tool_loop"`
  - Evidence: executor tests failed before initial and post-tool requests used
    phase-aware policy resolution.

- [x] R1.10 GREEN: Implement phase-aware tool choice resolution.
  - Spec: FR-4, FR-6
  - Files/components: `src/dynamic_agent_runner/executor.py`
  - Depends on: R1.8, R1.9
  - Validation:
    `poetry run pytest tests/test_executor.py -q -k "tool_choice_policy or model_tool_loop"`
  - Evidence: initial, follow-up, node override, and legacy fallback request
    assertions pass.

- [x] R1.11 RED: Add prompt-formatting tests for top-level `tool_results`.
  - Spec: FR-5
  - Files/components: `tests/test_executor.py`,
    `src/dynamic_agent_runner/executor.py`
  - Cases: `{{tool_results}}` renders model-facing output; raw
    `WorkflowExecutionState.tool_results` still stores raw `ToolResult.output`;
    existing direct output unwrapping remains compatible.
  - Validation:
    `poetry run pytest tests/test_executor.py -q -k "tool_results or model_facing_output"`
  - Evidence: `poetry run pytest tests/test_executor.py -q -k
    "tool_results or model_facing_output"` failed before implementation because
    top-level `tool_results` rendered raw `ToolResult` reprs.

- [x] R1.12 GREEN: Render top-level `tool_results` with model-facing output.
  - Spec: FR-5
  - Files/components: `src/dynamic_agent_runner/executor.py`
  - Depends on: R1.11
  - Validation:
    `poetry run pytest tests/test_executor.py -q -k "tool_results or model_facing_output"`
  - Evidence: prompt-formatting tests pass without mutating workflow state.

- [x] R1.13 Update docs only for public manifest policy.
  - Spec: FR-4, downstream migration plan
  - Files/components: `README.md`, `docs/files/runtime-policies.rst` if needed
  - Depends on: R1.10
  - Validation:
    `pre-commit run --files README.md docs/files/runtime-policies.rst`
  - Evidence: `README.md` and `docs/files/runtime-policies.rst` document
    runtime and node-local `tool_choice_policy` behavior.

- [ ] R1.14 Update spec status and validation evidence.
  - Spec: completion criteria
  - Files/components: `specs/openai-responses-tool-loop-compat/spec.md`,
    `specs/openai-responses-tool-loop-compat/tasks.md`,
    `specs/openai-responses-tool-loop-compat/validation.md`,
    `specs/README.md`
  - Depends on: R1.1-R1.13
  - Validation:

    ```bash
    pre-commit run --files \
      specs/openai-responses-tool-loop-compat/spec.md \
      specs/openai-responses-tool-loop-compat/tasks.md \
      specs/openai-responses-tool-loop-compat/validation.md \
      specs/README.md
    ```

  - Evidence: artifacts match implemented behavior and completion state.

- [ ] R1.15 Run focused implementation validation.
  - Spec: validation plan
  - Files/components: test suite
  - Depends on: R1.1-R1.14
  - Validation:

    ```bash
    poetry run pytest \
      tests/test_openai_client.py \
      -q \
      -k "stream or chatgpt or codex or responses"
    poetry run pytest \
      tests/test_executor.py \
      -q \
      -k "model_tool_loop or tool_choice_policy or tool_results"
    poetry run pytest \
      tests/test_validation.py \
      -q \
      -k "tool_choice_policy or tool_choice"
    ```

  - Evidence: all focused tests pass.

- [ ] R1.16 Run final validation.
  - Spec: completion criteria
  - Files/components: full repository
  - Depends on: R1.15
  - Validation:
    - `poetry run pytest -q`
    - `poetry run ruff check src tests`
    - targeted `pre-commit run --files ...` on actual changed files
  - Evidence: full test/lint checks pass.

## Checkpoints

- Checkpoint A: Streamed Responses function calls normalize correctly.
- Checkpoint B: Tool-loop transcript is structured internally and rendered
  correctly for both non-Codex fake adapters and ChatGPT/Codex request
  preparation.
- Checkpoint C: `tool_choice_policy` validates and controls initial vs
  post-tool turns.
- Checkpoint D: `{{tool_results}}` uses model-facing output without losing raw
  state.
- Checkpoint E: focused and full validation pass, then downstream Power Marimo
  can remove its monkey patch after upgrading.

## Stop Conditions

- Stop and rescope if implementation requires live OpenAI/ChatGPT/Codex calls.
- Stop and rescope if a public durable transcript type becomes necessary.
- Stop and rescope if non-Codex providers require Responses-specific input
  rendering.
- Stop and rescope if `tool_choice_policy` changes output semantics for
  workflows that do not configure it.
