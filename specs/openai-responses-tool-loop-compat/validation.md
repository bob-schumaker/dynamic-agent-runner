# OpenAI Responses Tool Loop Compatibility Validation

## Metadata

- Feature slug: `openai-responses-tool-loop-compat`
- Slice: R1 core compatibility
- Status: candidate readiness validation
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

## Current Implementation Baseline

The preparation pass observed these current facts:

- `_normalize_openai_stream_events(...)` tracks text deltas and completed
  response objects, but not `response.output_item.done` items.
- `_prepare_chatgpt_codex_request(...)` hoists instructions and sets
  `store=False` / `stream=True`, but does not translate tool-loop transcript
  entries into Responses input items.
- `_model_tool_result_messages(...)` emits assistant text plus `role: tool`
  messages and does not preserve original tool-call arguments in a
  provider-neutral transcript entry.
- `_request_loop_model_response_async(...)` reuses
  `prepared_input.tool_choice` on follow-up turns.
- `_format_context(...)` exposes raw `state.tool_results` at the top-level
  `tool_results` prompt key.
- `PreparedNode` currently preserves legacy `tool_choice` but has no
  `tool_choice_policy`.

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
