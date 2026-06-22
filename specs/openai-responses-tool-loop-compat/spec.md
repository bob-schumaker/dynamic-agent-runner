# OpenAI Responses Tool Loop Compatibility Specification

## Metadata

- Feature slug: `openai-responses-tool-loop-compat`
- Mode: `guided`
- Artifact type: authoritative feature specification
- Status: implementation candidate; Slice R1 prepared
- Version: `0.2`
- Date: 2026-06-22
- Owner: OpenAI adapter boundary plus iterative agent-loop runtime
- Downstream feature request:
  - `cline-tasks/openai-responses-tool-loop-compat-feature-request.md`
- Downstream evidence:
  - `/Users/roschuma/Repos/roschuma/power-marimo/src/power_marimo/llm/openai_responses_compat.py`
  - `/Users/roschuma/Repos/roschuma/power-marimo/src/power_marimo/llm/model_selection.py`
  - `/Users/roschuma/Repos/roschuma/power-marimo/src/power_marimo/notebook/chat_workspace.py`
  - `/Users/roschuma/Repos/roschuma/power-marimo/src/power_marimo/tools/runtime_registry.py`
  - `/Users/roschuma/Repos/roschuma/power-marimo/tests/test_dynamic_agent_runner_openai_client.py`
- Related specs:
  - `specs/openai-compatible-provider-wrapper/spec.md`
  - `specs/default-openai-codex-auth/spec.md`
  - `specs/iterative-agent-loop-runtime/spec.md`
  - `specs/host-workflow-integration/spec.md`
  - `specs/context-management-prepare-stage/spec.md`

## Objective

Make DAR's OpenAI Responses and ChatGPT/Codex backend path compatible with
iterative model-tool loops, without requiring downstream applications to monkey
patch private runtime functions.

The feature should let a host such as Power Marimo use DAR's existing
`WorkflowExecutionContext`, `AgentSession`, host tool registry, model adapter
selection, tracing, token budgeting, context compaction, approval handling, and
`ToolResult.model_output` features as designed.

## Downstream Request Synopsis

This spec is a direct response to the downstream Power Marimo feature request
captured in
`cline-tasks/openai-responses-tool-loop-compat-feature-request.md`.

Power Marimo currently installs a process-local compatibility patch before
creating its OpenAI adapter. The patch replaces three DAR private functions:

- `_normalize_openai_stream_events`
- `_prepare_chatgpt_codex_request`
- `_format_context`

The patch is intentionally local, but the behavior it covers belongs in DAR
because it is generic runtime/provider compatibility, not Power Marimo domain
logic.

The driving issues are:

1. Streamed OpenAI Responses function-call output items can appear in
   `response.output_item.done`, while the completed response may have an empty
   `output` array. DAR currently normalizes only the completed response output
   for tool calls, so the tool loop can miss real model-emitted function calls.
2. DAR's iterative tool loop currently feeds follow-up turns a Chat
   Completions-style `role: tool` transcript message. The ChatGPT/Codex
   Responses path requires `function_call_output` input items, and those outputs
   must correspond to prior function-call items with the same `call_id`.
3. `tool_choice: required` is useful for forcing the first tool call on a
   tool-capable reasoning node, but reusing it after at least one tool result
   can force unnecessary follow-up tool calls when the model is ready to answer.
4. Top-level prompt context currently renders raw `ToolResult` objects in
   `{{tool_results}}`, even though direct output unwrapping already uses
   `ToolResult.model_facing_output`. Large downstream tool outputs can therefore
   exceed prompt budgets despite having compact model-facing summaries.

Power Marimo validates the need through notebook chat workflows that expose
project, room, SLD, datafile, analysis, plotting, and project-data tools from a
single dynamic `reason` node, then produce a `final_response` from
`{{tool_results}}`.

## Current Downstream Shape

Power Marimo generates a runtime manifest in memory and executes it through
DAR's host-facing surfaces:

- `WorkflowExecutionContext`
- async `AgentSession` streaming
- `ResolvedModelSelection` handoff
- host-owned `ToolService` adapted through DAR's host integration helpers
- `tool_use_completion.run_again: required`
- context compaction and context compression policy
- `tool_choice: required` on the tool-capable `reason` node
- `{{tool_results}}` in both the `reason` and `final_response` prompts

Power Marimo also correctly keeps domain compaction downstream:

- raw SLD, rack, and datafile payloads stay in `ToolResult.output`
- compact model-safe summaries are supplied through `ToolResult.model_output`
- DAR should render model-facing summaries where prompt context expects model
  input, while leaving raw output available to host application code

## Scope

This feature covers:

1. streaming OpenAI Responses function-call preservation
2. Responses-compatible tool-loop follow-up transcript rendering
3. a runtime `tool_choice_policy` contract for first-turn and post-tool
   behavior
4. top-level `tool_results` prompt-context rendering through
   `ToolResult.model_facing_output`
5. tests using fake providers, fake streams, fake model adapters, and fake tool
   registries
6. downstream migration guidance for removing Power Marimo's monkey patch

## Non-Goals

This feature must not introduce:

- Power Marimo, Marimo, Qt, notebook, Power Tetris, room-power, SLD, or
  datafile domain behavior into DAR
- live OpenAI, ChatGPT, Codex, Marimo, or external tool calls in unit tests
- runner-owned durable storage for raw tool transcripts
- runner-owned tool output compaction heuristics for downstream domains
- a new model provider abstraction that replaces the existing OpenAI adapter
  facade
- a separate ReAct engine outside the existing iterative `llm_step` loop
- silent changes to default workflows that do not configure tools or tool-loop
  policy

## Functional Requirements

### FR-1: Preserve streamed Responses function calls

DAR must normalize function calls emitted as streamed Responses output items.

Acceptance criteria:

- Given a streamed OpenAI Responses event sequence contains
  `response.output_item.done` with an item of type `function_call`, when the
  completed response output is empty, then the normalized `ModelResponse`
  includes the corresponding `ModelToolCall`.
- Given both completed response output and streamed output items contain tool
  calls, when completed output has tool calls, then completed output remains the
  authoritative source.
- Given streamed output items contain message text and tool calls, when the
  completed response omits either value, then normalization may fall back to the
  streamed items before falling back to accumulated text deltas.
- Given no streamed output item is present, existing streaming text behavior
  remains unchanged.
- Raw stream events remain available for diagnostics when no completed response
  object is available.

### FR-2: Preserve model tool-call transcript data through loop turns

DAR must retain enough model tool-call data to render provider-specific
follow-up requests correctly.

Acceptance criteria:

- Given a model emits `ModelToolCall(id, name, arguments)`, when the loop invokes
  the tool, then the follow-up transcript retains the same call id, tool name,
  and original arguments.
- Given a follow-up request is sent through a Chat Completions-compatible
  provider, then the transcript can still be rendered as an assistant tool-call
  item plus a `role: tool` result message.
- Given a follow-up request is sent through the ChatGPT/Codex Responses backend,
  then the transcript is rendered as a Responses `function_call` input item
  followed by a matching `function_call_output` input item.
- The implementation must not synthesize empty `{}` arguments when original
  arguments are available.
- Tool output sent back to the model must continue to use
  `ToolResult.model_facing_output`.

### FR-3: Convert ChatGPT/Codex follow-up input to Responses items

The ChatGPT/Codex request preparation path must translate tool-loop transcript
items into Responses-compatible input.

Acceptance criteria:

- System and developer messages continue to be hoisted into `instructions`.
- User and assistant text messages continue to be passed as ordinary input
  messages.
- Tool-call transcript items are converted to:

  ```json
  {
    "type": "function_call",
    "call_id": "call_...",
    "name": "tool_name",
    "arguments": "{\"key\":\"value\"}"
  }
  ```

- Tool-result transcript items are converted to:

  ```json
  {
    "type": "function_call_output",
    "call_id": "call_...",
    "output": "{\"status\":\"ok\"}"
  }
  ```

- `store: false` and `stream: true` behavior for ChatGPT/Codex requests remains
  unchanged.
- Translation remains provider-scoped; non-ChatGPT/Codex providers retain their
  existing request shape unless they explicitly opt into a compatible renderer.

### FR-4: Add `tool_choice_policy`

DAR must support an explicit policy that controls `tool_choice` across initial
and follow-up model turns.

Policy shape:

```yaml
runtime:
  execution_policy:
    tool_choice_policy:
      initial: required
      after_tool_result: auto
```

Optional node-local override:

```yaml
nodes:
  - id: reason
    kind: llm_step
    tool_choice_policy:
      initial: required
      after_tool_result: auto
```

Semantics:

- `initial` controls the first model request for the node.
- `after_tool_result` controls model requests after at least one successful tool
  result has been added to the loop transcript.
- `auto` means do not send a forced `tool_choice` value for that phase.
- `required` means send provider-compatible forced tool choice for that phase.
- Existing node-level `tool_choice` remains supported for backward
  compatibility and maps to `initial` when no `tool_choice_policy` is present.

Acceptance criteria:

- Given `tool_choice_policy.initial: required`, when an eligible tool-capable
  `llm_step` makes its first model request, then the request includes forced
  tool choice.
- Given `tool_choice_policy.after_tool_result: auto`, when the loop sends a
  follow-up request after a successful tool result, then the follow-up request
  does not include `tool_choice: required`.
- Given no `tool_choice_policy` is configured, existing behavior is preserved
  except where provider request adaptation must avoid invalid Responses input.
- Given both legacy `tool_choice` and `tool_choice_policy` are configured on the
  same node, validation fails clearly unless a migration rule is explicitly
  specified before implementation.
- Policy values outside the supported enum fail validation before execution.

### FR-5: Render top-level `tool_results` as model-facing output

DAR prompt formatting must expose model-facing tool output in top-level
`{{tool_results}}`.

Acceptance criteria:

- Given `state.tool_results` contains `ToolResult` values with `model_output`,
  when prompt templates render `{{tool_results}}`, then the rendered mapping
  uses each value's `model_facing_output`.
- Given downstream application code reads `WorkflowExecutionState.tool_results`,
  raw `ToolResult.output` remains available and unchanged.
- Given direct value resolution reads `tool_results.some_tool.output`, existing
  behavior remains compatible unless a separate contract change is approved.
- Given a prompt references node output aliases, existing `ModelResponse` and
  `ToolResult` unwrapping behavior remains unchanged.

### FR-6: Keep compatibility visible in diagnostics

Compatibility behavior should be inspectable through existing trace and test
surfaces without leaking sensitive prompt, tool output, or arguments.

Acceptance criteria:

- Model request traces show whether follow-up requests include or omit forced
  `tool_choice` without exposing sensitive content.
- Tool-loop traces preserve existing loop start, tool call, tool result, and
  stop reason events.
- Request payload redaction remains at least as strict as current model request
  trace behavior.
- Tests assert behavior through fake calls and redacted payloads rather than
  live provider calls.

## Proposed Runtime Behavior

### Tool Choice Resolution

Effective tool choice for a node should be resolved in phases:

1. Determine whether the request is the node's initial model turn or a
   post-tool-result follow-up turn.
2. If `tool_choice_policy` exists, use the phase-specific value.
3. If no policy exists, use legacy `node.tool_choice` for the initial turn.
4. For follow-up turns, preserve legacy behavior unless provider adaptation
   requires omitting invalid or counterproductive forced choice. The preferred
   migration path is for hosts to set `tool_choice_policy.after_tool_result:
   auto`.

Power Marimo should migrate from:

```yaml
nodes:
  - id: reason
    kind: llm_step
    tool_choice: required
```

to:

```yaml
nodes:
  - id: reason
    kind: llm_step
    tool_choice_policy:
      initial: required
      after_tool_result: auto
```

### Transcript Representation

The implementation should prefer an internal structured transcript over
provider-specific message dictionaries.

Minimum required internal fields:

- `call_id`
- `tool_name`
- original `arguments`
- model-facing `output`

This keeps provider rendering local to the adapter/request boundary and avoids
the downstream patch's temporary `{}` argument synthesis.

## Validation Plan

Focused fake tests should cover:

1. streamed Responses API tool call normalization where
   `response.output_item.done` contains a `function_call` and
   `response.completed.response.output` is empty
2. async stream parity for the same behavior
3. ChatGPT/Codex request preparation for structured tool-call plus tool-result
   transcript items
4. backward-compatible request preparation for ordinary user/system/developer
   messages
5. iterative tool loop follow-up requests with
   `tool_choice_policy.initial: required` and
   `tool_choice_policy.after_tool_result: auto`
6. validation failures for invalid `tool_choice_policy` values and ambiguous
   legacy `tool_choice` plus explicit policy combinations
7. top-level `{{tool_results}}` rendering with `ToolResult.model_output`
8. preservation of raw `ToolResult.output` in workflow state
9. no live OpenAI, ChatGPT, Codex, Marimo, Power Tetris, network, or GUI calls
   in unit tests

Suggested commands:

```bash
poetry run pytest \
  tests/test_openai_client.py \
  tests/test_executor.py \
  tests/test_validation.py \
  -q \
  -k "responses or tool_choice_policy or tool_results or model_tool_loop"
poetry run ruff check src tests
```

Run the full suite before completion:

```bash
poetry run pytest -q
```

## Downstream Migration Plan

After this feature is implemented and released, Power Marimo should:

1. remove `power_marimo.llm.openai_responses_compat`
2. stop calling `install_openai_responses_tool_compatibility()` from model
   selection
3. keep using `create_async_openai_adapter_from_provider_config(...)` with
   ChatGPT-first auth preference
4. change notebook chat manifests from legacy `tool_choice: required` to
   `tool_choice_policy.initial: required` plus
   `tool_choice_policy.after_tool_result: auto`
5. keep domain-specific `ToolResult.model_output` compaction in
   `power_marimo.tools.runtime_registry`
6. keep using DAR's `WorkflowExecutionContext`, `AgentSession`, host tool
   registry, trace sink, context compaction, token budget, and approval surfaces

## Resolved Implementation Decisions

Slice R1 resolves the implementation-blocking questions this way:

1. A node that configures both legacy `tool_choice` and explicit
   `tool_choice_policy` fails validation. This avoids hidden precedence rules.
2. Runtime-level defaults and node-local overrides are both in Slice R1 because
   the contract already names both and validation/plan plumbing is small.
3. The structured tool-loop transcript remains internal in Slice R1. Public
   transcript types are deferred until durable resume or public transcript
   inspection requires them.

## Completion Criteria

This feature is complete when:

- Power Marimo no longer needs to patch DAR private functions for OpenAI
  Responses tool loops.
- Streamed OpenAI Responses function calls trigger DAR's existing iterative
  model-tool loop.
- ChatGPT/Codex follow-up turns use Responses-compatible function-call output
  items.
- `tool_choice_policy` can force the first tool call and allow post-tool final
  answers.
- `{{tool_results}}` uses model-facing output without removing raw tool results
  from workflow state.
- Focused fake tests and the full repository test suite pass.
