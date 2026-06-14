# Iterative Agent-Loop Runtime V1 Plan

## Objective

Implement the first bounded iterative loop inside an eligible `llm_step` without
changing the finite graph executor default. V1 should let a model request one or
more registered tools, receive model-facing tool results, and produce a final
answer under the existing tool-use completion policy metadata.

## Scope

- Activate only when `runtime.execution_policy.tool_use_completion.run_again` is
  `required`.
- Reuse existing `ModelResponse.tool_calls` and `ToolRegistry` primitives.
- Dispatch model-emitted tool calls serially through the registry.
- Restrict invocations to tools effectively exposed to the current node.
- Append model-facing tool result messages to the loop transcript.
- Stop on final/no-tool model response, `stop_on_tool: enabled`, max iteration
  exhaustion, tool failure, model failure, or approval interruption.
- Validate the selected final output with the existing output-contract path.
- Emit loop-specific trace events with sensitive payload fields marked.

## Non-Goals

- No parallel tool-call execution.
- No node-local loop policy overrides.
- No durable resume for model-emitted approval interruptions.
- No output/tool guardrail phases.
- No new live model, MCP, Hugging Face, llama.cpp, or external service calls in
  tests.
- No replacement of direct `tool_use_step` behavior.

## Design

Keep the loop local to `_execute_llm_step_async`. Build the first turn with the
existing `prepare_model_input`, exposed-tool collection, OpenAI request builder,
retry, hook, trace, prompt-cache telemetry, and output-contract helpers.

When a response contains tool calls and the policy requires run-again behavior:

1. validate each tool name against the node's exposed registry tools
2. parse JSON object arguments or accept mapping arguments
3. fail closed before invoking approval-required tools unless the current
   interruption contract can represent the model tool call safely
4. invoke the tool through the existing registry async path
5. record tool results in execution state under a loop-correlated key
6. append assistant/tool transcript messages using the tool-call id and
   `ToolResult.model_output`
7. reissue the model request until the stop policy resolves or max iterations is
   reached

The v1 helper should remain internal. A small internal dataclass for loop turn
state is acceptable if it keeps `_execute_llm_step_async` readable, but no public
API should be added for loop internals.

## Compatibility

- Workflows without `tool_use_completion.run_again: required` must behave
  exactly as they do today.
- Existing direct `tool_use_step` approval, retry, trace, and output behavior
  must remain unchanged.
- Existing metadata validation remains valid; any new runtime limit must use
  conservative defaults when absent.

## Validation Strategy

- Add RED executor tests for unchanged non-loop behavior with model tool calls.
- Add RED executor tests for a loop that dispatches a model-emitted tool and
  re-calls the model with model-facing tool output.
- Add RED tests for hidden/unexposed tool rejection and malformed arguments.
- Add RED tests for approval-required model tool calls stopping before
  invocation.
- Add trace assertions for loop start, turn, tool call/result, stop reason, and
  final output selection.
- Run focused executor, validation, capability, registry, and import tests.
- Run focused pre-commit on changed source, tests, and spec artifacts.
