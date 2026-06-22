# Feature Request: First-Class OpenAI Responses Tool Loop Support

## Summary

Power Marimo currently carries a process-local compatibility patch for
`dynamic-agent-runner` when using the ChatGPT/Codex OpenAI Responses API backend.
The patch is intentionally local, but it is covering behavior that belongs in
`dynamic-agent-runner` itself:

- preserve streamed Responses API function-call output items during response
  normalization
- convert Chat Completions-style tool-result transcript messages into Responses
  API `function_call_output` input items
- avoid reusing `tool_choice: required` after at least one tool result has been
  returned to the model
- render `ToolResult.model_facing_output` inside top-level `{{tool_results}}`
  prompt context instead of passing raw `ToolResult` objects

This note is deliberately detailed so the upstream implementation can make a
deliberate choice rather than simply copying the downstream monkey patch.

## Context

Power Marimo is using `dynamic-agent-runner` as the ReAct/tool-loop runtime for
notebook chat. The notebook workflow exposes tools such as:

- `load_template_sld_json`
- `resolve_room_and_sld`
- `fetch_room_power_data`

The concrete live task that exposed the problem was:

1. load raw SLD JSON and rack positions from this workbook:

   ```text
   Directory: /Users/roschuma/Documents/Power Tetris/
   File: abl15.1-PowerTetris Configuration Template v1.06-kim.xlsm
   ```

2. resolve and fetch SLD data for room `aga4.1`
3. compare the device data structure fields in both JSON files
4. display the comparison

The final successful live result compared these fields:

- common fields:
  `alternate`, `alternate_swbd`, `budget`, `capacity`, `device_name`,
  `device_type`, `effective_capacity`, `electrical_lineup`, `positions`,
  `primary`, `primary_swbd`, `rooms`, `shared_dedicated`, `sts_name`,
  `swbd_capacity`, `swbd_name`
- template-only: `non-oci_capacity`
- room-only: `non_oci_capacity`

The only data-structure difference was hyphen versus underscore in
`non-oci_capacity` / `non_oci_capacity`.

## Observed Failure Sequence

### 1. Model saw tools but did not call them

The notebook workflow exposed all expected tools. A live prompt asking "what
tools are available?" succeeded after we added the datafile tools to the
manifest.

However, when asked to run the actual task, the `reason` node initially answered
in prose:

- it said it would use `load_template_sld_json`, `resolve_room_and_sld`, and
  `fetch_room_power_data`
- it did not emit any tool calls
- the trace showed only `model_request`, `model_response`, and no
  `model_tool_loop_*` events

Power Marimo then added `tool_choice: required` to the tool-capable `reason`
node. The actual model request object had `tool_choice == "required"` and 16
tools, but the runner still normalized no tool calls.

### 2. Streamed Responses API function calls were discarded

A minimal live probe through the same OpenAI adapter reproduced the issue:

- request: one toy function tool `echo_room`
- `tool_choice: required`
- model: `gpt-5.4`
- provider: ChatGPT/Codex Responses API path

The raw stream contained the tool call:

- `response.output_item.added` with item type `function_call`
- `response.function_call_arguments.delta`
- `response.function_call_arguments.done`
- `response.output_item.done` with a completed `ResponseFunctionToolCall`
- `response.completed`

But `response.completed.response.output` was empty. The existing normalizer only
called `normalize_openai_response(completed_response)` at completion time, so it
lost the function call item that had appeared earlier in the stream.

This made `tool_choice: required` look ineffective even though the provider had
actually emitted a function call.

### 3. Tool-result follow-up request used unsupported `role: tool`

After preserving the streamed tool call, the runner invoked the tool. The next
model turn failed with:

```text
Invalid value: 'tool'. Supported values are: 'assistant', 'system',
'developer', and 'user'.
```

The runner transcript was Chat Completions-shaped:

```json
{
  "role": "tool",
  "tool_call_id": "call_...",
  "name": "load_template_sld_json",
  "content": "{...}"
}
```

The ChatGPT/Codex Responses API path needs a Responses input item instead:

```json
{
  "type": "function_call_output",
  "call_id": "call_...",
  "output": "{...}"
}
```

### 4. Function-call output required a corresponding function-call item

After converting `role: tool` to `function_call_output`, the provider rejected
the request with:

```text
No tool call found for function call output with call_id call_...
```

The Responses API conversation also needed a matching prior function-call input
item:

```json
{
  "type": "function_call",
  "call_id": "call_...",
  "name": "load_template_sld_json",
  "arguments": "{}"
}
```

The local patch synthesizes that item from the tool result message. This is a
pragmatic compatibility move, not necessarily the ideal upstream representation.
A cleaner upstream design may preserve the original `ModelToolCall.arguments`
and emit that exact function-call item instead of synthesizing `{}`.

### 5. `tool_choice: required` should not be forced after a tool result

Once `tool_choice: required` was used to force the first tool call, subsequent
model turns after tool execution should be allowed to finish normally. Reusing
`tool_choice: required` on every loop turn risks forcing an extra tool call when
the model has enough observations to produce final text.

The local patch clears `tool_choice` when preparing a ChatGPT/Codex request that
contains at least one tool-result message and the original tool choice was
`required`.

An upstream implementation should decide whether this belongs in:

- generic tool-loop execution, e.g. first-turn-only forced tool choice
- provider request adaptation, as Power Marimo currently does locally
- a new explicit policy such as `tool_choice_scope: first_turn`

### 6. `{{tool_results}}` rendered raw `ToolResult` state

Power Marimo added `ToolResult.model_output` compaction for large tool outputs.
This is needed because the raw SLD JSON payloads are large:

- template loader output: about 165 KB
- room power/SLD fetch output: about 1.9 MB

The runner already uses `ToolResult.model_facing_output` for direct state alias
resolution and node output unwrapping. But top-level prompt context rendered:

```python
"tool_results": state.tool_results
```

That put raw `ToolResult` objects into `{{tool_results}}`, and the final response
node exceeded the prompt budget:

```text
llm_step node 'final_response' estimated prompt tokens 746239 exceeds budget 24000
```

After changing the formatted context to render:

```python
"tool_results": {
    key: value.model_facing_output for key, value in state.tool_results.items()
}
```

the final response prompt dropped to roughly 1,172 estimated tokens in the same
workflow.

## Downstream Local Monkey Patch

Power Marimo currently installs the patch from:

```text
src/power_marimo/llm/openai_responses_compat.py
```

The install hook is called before constructing the OpenAI adapter:

```python
install_openai_responses_tool_compatibility()
return create_async_openai_adapter_from_provider_config(...)
```

The patch replaces three private functions at process scope:

```python
runner_openai_client._normalize_openai_stream_events = _normalize_openai_stream_events
runner_openai_client._prepare_chatgpt_codex_request = _prepare_chatgpt_codex_request
runner_executor._format_context = _format_context
```

### Local patched stream normalization

The downstream normalizer:

- accumulates `response.output_item.done` items while streaming
- normalizes those items as a synthetic response output
- falls back to streamed output items when `response.completed.response.output`
  is empty

Important local behavior:

```python
if event_type == "response.output_item.done":
    item = _read_value(event, "item")
    if item is not None:
        output_items.append(item)
    continue
```

Then:

```python
streamed_response = (
    normalize_openai_response({"id": response_id, "output": output_items})
    if output_items
    else None
)
```

Final `ModelResponse.tool_calls` becomes:

```python
normalized.tool_calls or streamed_response.tool_calls
```

### Local patched ChatGPT/Codex request preparation

The downstream request preparation:

- hoists `system` and `developer` messages into `instructions`
- converts `role: tool` messages into Responses function-call input items
- synthesizes a matching `function_call` item before `function_call_output`
- clears `tool_choice` after a tool result when it was `required`
- keeps `store=False` and `stream=True`

The compatibility conversion is:

```python
{
    "type": "function_call",
    "call_id": call_id,
    "name": str(name),
    "arguments": "{}",
}
{
    "type": "function_call_output",
    "call_id": call_id,
    "output": str(content or ""),
}
```

Again, the `{}` arguments are a downstream compromise. Upstream can do better by
preserving the original tool call transcript item in a provider-neutral way.

### Local patched context formatting

The downstream `_format_context` replacement renders top-level tool results as:

```python
"tool_results": {
    key: _model_facing_output(value)
    for key, value in state.tool_results.items()
}
```

This keeps large raw outputs available in `ToolResult.output` while ensuring
prompt templates receive bounded model-facing summaries.

## Related Power Marimo Changes

Power Marimo also made application-specific changes that do not belong upstream,
but they explain why the upstream runner behavior matters:

- notebook chat manifest now exposes datafile tools:
  `inspect_datafile`, `preview_datafile_import`, `load_template_sld_json`,
  `apply_datafile_import`, `list_loaded_datafiles`, `remove_loaded_datafile`
- notebook `reason` node uses `tool_choice: required`
- prompts now explicitly instruct the model not to ask the user to run available
  tools
- runner-facing tool bridge compacts bulky Power Tetris outputs with
  `ToolResult.model_output`

The compaction is in:

```text
src/power_marimo/tools/runtime_registry.py
```

For `load_template_sld_json` and `fetch_room_power_data`, the model-facing output
keeps:

- status/provenance/caveats
- SLD top-level field names
- device table name
- device count
- union of device object fields
- rack-position field summary for template data

The raw output remains in `ToolResult.output`.

## Suggested Upstream Implementation Options

### Option A: Minimal parity with downstream patch

Implement the same three behaviors directly in `dynamic-agent-runner`:

1. preserve streamed `response.output_item.done` items in
   `_normalize_openai_stream_events`
2. translate `role: tool` messages to Responses function-call items in
   `_prepare_chatgpt_codex_request`
3. render top-level `tool_results` with `ToolResult.model_facing_output`

This is the quickest path and matches the validated downstream behavior.

### Option B: Cleaner provider-neutral transcript model

Instead of synthesizing a `function_call` item from a tool-result message,
preserve the original model tool call in the loop transcript as structured data.
Then provider adapters can render it into:

- Chat Completions: assistant message with `tool_calls`, followed by
  `role: tool`
- Responses API: `function_call`, followed by `function_call_output`

This is probably the better long-term design because it avoids losing original
arguments and avoids provider-specific assumptions in generic transcript
messages.

### Option C: Explicit forced-tool policy

Add a manifest/runtime policy for whether `tool_choice: required` applies:

- only on the first model turn
- on every turn
- until the first successful tool result
- never on follow-up turns

Power Marimo's current need is "force first tool call when the request requires
tool data, but let the model finish after it has observations."

## Suggested Regression Tests

Add tests for:

1. streamed Responses API tool call normalization where
   `response.output_item.done` contains a `function_call`, but
   `response.completed.response.output` is empty
2. ChatGPT/Codex request preparation with a `role: tool` message
3. follow-up tool loop behavior when `tool_choice == "required"` and a tool
   result is present
4. `_format_context` using `ToolResult.model_facing_output` for top-level
   `tool_results`
5. a small end-to-end tool loop through the ChatGPT/Codex provider adapter, if a
   live/opt-in test already exists

## Validation Performed Downstream

Power Marimo validated the local patch with:

- live OpenAI notebook workflow asking what tools are available
- live OpenAI workflow that loaded the Excel template, resolved `aga4.1`, fetched
  room SLD data, and compared device fields
- focused pytest coverage for:
  - stream function-call preservation
  - Responses tool-result translation
  - model-facing `tool_results`
  - bulky Power Tetris tool output compaction
  - notebook manifest tool exposure
- `pre-commit run --files ...`
- `graphify update .`

The important live success criteria were met: the model actually invoked
`load_template_sld_json`, `resolve_room_and_sld`, and `fetch_room_power_data`,
then produced the field comparison instead of asking the user to run tools
manually.

## Why This Should Be Upstream

The downstream monkey patch reaches into private functions:

- `_normalize_openai_stream_events`
- `_prepare_chatgpt_codex_request`
- `_format_context`

That is brittle. It is acceptable as a temporary unblocker for Power Marimo, but
the behavior is runtime/provider infrastructure, not Power Marimo domain logic.

Upstreaming the behavior would let Power Marimo remove the monkey patch and
would make the ChatGPT/Codex Responses API path reliable for any workflow that
uses streamed function calls and iterative tool loops.
