# OpenAI Responses Tool Loop Compatibility Validation

## Metadata

- Feature slug: `openai-responses-tool-loop-compat`
- Slice: R1 core compatibility
- Status: Slice R1 implementation validation
- Date: 2026-06-22

## Readiness Checks

- The downstream feature request is captured in
  `cline-tasks/openai-responses-tool-loop-compat-feature-request.md`.
- The authoritative feature spec is present in [`spec.md`](spec.md).
- Slice R1 has an implementation plan in [`plan.md`](plan.md).
- Slice R1 has a concrete task checklist in [`tasks.md`](tasks.md).
- No blocking `NEEDS CLARIFICATION` items remain.
- Runtime-level and node-local `tool_choice_policy` are both included in R1.
- Node-local legacy `tool_choice` plus explicit `tool_choice_policy` is a
  validation error in R1.
- Structured tool-loop transcript data remains internal in R1.
- Tests are fake-only; no live OpenAI, ChatGPT, Codex, Marimo, network, GUI, or
  Power Tetris calls are required.
- Power Marimo domain compaction remains downstream-owned through
  `ToolResult.model_output`.

## Spec-To-Task Traceability

| Requirement | Planned tests/tasks |
| --- | --- |
| FR-1 streamed Responses function-call preservation | R1.1, R1.2 |
| FR-2 preserve model tool-call transcript data | R1.3, R1.4, R1.5 |
| FR-3 ChatGPT/Codex Responses input conversion | R1.3, R1.5 |
| FR-4 `tool_choice_policy` | R1.6, R1.7, R1.8, R1.9, R1.10, R1.13 |
| FR-5 model-facing top-level `tool_results` | R1.11, R1.12 |
| FR-6 bounded diagnostics and trace safety | R1.9, R1.10, R1.15, R1.16 |

## Validation To Run During Implementation

Focused checks:

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

Final checks:

```bash
poetry run pytest -q
poetry run ruff check src tests
```

Run targeted pre-commit on actual changed files before committing.

## Commands Run During Preparation

| Command | Result | Notes |
| --- | --- | --- |
| `graphify query "OpenAI Responses streaming function_call tool loop tool_choice ToolResult model_facing_output validation"` | pass | Used for navigation; output was broad but confirmed relevant source/test areas |
| `rg "tool_choice_policy\|tool_choice\|function_call_output\|response.output_item.done\|role\\\": \\\"tool\|_normalize_openai_stream_events\|_prepare_chatgpt_codex_request\|_model_tool_result_messages\|_format_context\|ToolResult.model_facing_output" -n src tests specs/openai-responses-tool-loop-compat` | pass | Confirmed current source touch points and absence of existing `tool_choice_policy` |
| `poetry run pytest tests/test_openai_client.py -q -k "stream or responses"` | fail, then pass | R1.1 RED failed on dropped streamed function-call output items; R1.2 GREEN passed with 5 tests after `_normalize_openai_stream_events(...)` collected `response.output_item.done` items |
| `pre-commit run --files src/dynamic_agent_runner/openai_client.py tests/test_openai_client.py` | pass | R1.1/R1.2 source and test files passed Ruff and formatting after hook rewrite |
| `poetry run pytest tests/test_openai_client.py -q -k "chatgpt or codex"` | fail, then pass | R1.3 RED failed before ChatGPT/Codex transcript conversion; R1.5 GREEN passed with 10 focused adapter tests |
| `poetry run pytest tests/test_executor.py -q -k "model_tool_loop or chatgpt_codex"` | fail, then pass | R1.4 RED failed before structured loop transcript rendering; R1.5 GREEN passed with 4 focused executor tests |
| `poetry run pytest tests/test_validation.py -q -k "tool_choice_policy or tool_choice"` | fail, then pass | R1.6 RED failed before policy validation; R1.8 GREEN passed with runtime, node, invalid-value, and conflict coverage |
| `poetry run pytest tests/test_executor.py -q -k "tool_choice_policy or prepare_execution_plan or model_tool_loop"` | fail, then pass | R1.7/R1.9 RED failed before plan/runtime policy plumbing; R1.10 GREEN passed with 8 focused executor tests |
| `poetry run pytest tests/test_executor.py -q -k "tool_results or model_facing_output"` | fail, then pass | R1.11 RED failed before top-level `tool_results` used model-facing output; R1.12 GREEN passed with state raw output preserved |
| `poetry run pytest tests/test_openai_client.py -q -k "stream or chatgpt or codex or responses"` | pass | R1.15 focused adapter validation passed with 15 tests |
| `poetry run pytest tests/test_executor.py -q -k "model_tool_loop or tool_choice_policy or tool_results"` | pass | R1.15 focused executor validation passed with 6 tests |
| `poetry run pytest tests/test_validation.py -q -k "tool_choice_policy or tool_choice"` | pass | R1.15 focused validation passed with 2 tests |
| `poetry run pytest -q` | pass | R1.16 full test suite passed with 573 tests |
| `poetry run ruff check src tests` | pass | R1.16 source and test lint passed |

## Slice R1 Implementation Outcome

The Slice R1 implementation changed the baseline as follows:

- `_normalize_openai_stream_events(...)` collects
  `response.output_item.done` items and uses them when completed output omits
  text or tool calls.
- `_prepare_chatgpt_codex_request(...)` translates internal tool-loop
  transcript entries into Responses `function_call` and
  `function_call_output` input items while preserving instruction hoisting,
  `store=False`, and `stream=True`.
- `_model_tool_result_messages(...)` keeps Chat Completions-compatible
  assistant/tool messages for normal providers and adds internal transcript
  metadata with call id, tool name, original arguments, and model-facing output.
- `_request_loop_model_response_async(...)` resolves `tool_choice` by phase
  through node-local policy, runtime policy, and legacy fallback.
- `_format_context(...)` renders top-level `tool_results` as model-facing output
  while preserving raw `WorkflowExecutionState.tool_results`.
- `PreparedNode` and `ExecutionPlan` preserve `tool_choice_policy`.

## Out-of-Scope Confirmation

The prepared R1 slice does not:

- add live provider calls
- add a new model provider abstraction
- add Power Marimo domain behavior
- add public durable transcript APIs
- add runner-owned tool-output compaction
- change workflows that do not configure tools or tool-loop behavior

## Residual Risks

- ChatGPT/Codex provider request details may have edge cases not represented by
  fake tests. Mitigation: keep conversion local to `_prepare_chatgpt_codex_request`
  and preserve raw request kwargs in fake assertions.
- Existing downstream prompts might have depended on raw top-level
  `ToolResult` repr. Mitigation: raw state remains available, and the feature
  aligns top-level prompt context with existing `model_facing_output` semantics.
- Runtime-level and node-local policy precedence may need future expansion.
  Mitigation: R1 implements only `initial` and `after_tool_result` with
  fail-fast conflict validation.
