# OpenAI Responses Tool Loop Compatibility Implementation Plan

## Metadata

- Feature slug: `openai-responses-tool-loop-compat`
- Slice: R1 core compatibility
- Status: prepared implementation candidate
- Date: 2026-06-22
- Owning spec: [`spec.md`](spec.md)

## Objective

Implement the smallest upstream DAR slice that lets Responses-backed
ChatGPT/Codex tool loops work without Power Marimo's private monkey patch.

Slice R1 should:

- preserve streamed Responses function-call items
- preserve model tool-call transcript data across loop turns
- render ChatGPT/Codex follow-up input with Responses `function_call` and
  `function_call_output` items
- add explicit `tool_choice_policy` for initial and post-tool model turns
- render top-level prompt `tool_results` through `ToolResult.model_facing_output`

## Current Architecture Fit

The existing code already has the right seams:

- `src/dynamic_agent_runner/openai_client.py` owns OpenAI-compatible request
  construction, streaming normalization, ChatGPT/Codex request adaptation, and
  normalized `ModelResponse` / `ModelToolCall` contracts.
- `src/dynamic_agent_runner/executor.py` owns the iterative `llm_step` model
  tool loop, loop transcript construction, model request traces, prepared input,
  and prompt formatting.
- `src/dynamic_agent_runner/models.py` owns `PreparedNode` and
  `ExecutionPlan` runtime preparation.
- `src/dynamic_agent_runner/validation.py` owns manifest validation for runtime
  policy and node-local fields.
- `tests/test_openai_client.py`, `tests/test_executor.py`, and
  `tests/test_validation.py` already contain fake-only coverage for the
  affected surfaces.

Slice R1 should extend these seams instead of adding a parallel ReAct engine or
provider stack.

## Technical Approach

### 1. Streaming Responses normalization

Update `_normalize_openai_stream_events(...)` to collect
`response.output_item.done` items.

Implementation notes:

- Normalize collected output items through `normalize_openai_response(...)` by
  constructing a synthetic response mapping with `id` and `output`.
- Preserve current completed-response precedence when completed output contains
  tool calls or text.
- Fall back to streamed output items only when completed output omits the value.
- Preserve current text-delta fallback behavior.
- Keep sync and async stream paths sharing `_normalize_openai_stream_events(...)`.

### 2. Internal structured loop transcript

Replace the current lossy transcript entries from `_model_tool_result_messages`
with internal mapping entries that preserve:

- marker/type identifying a DAR model-tool-call transcript item
- `call_id`
- tool name
- original arguments
- model-facing output

The first implementation can use internal dictionaries rather than a public
dataclass. The marker must be unlikely to collide with provider message fields,
for example `"_dar_transcript_type": "model_tool_call"` and
`"_dar_transcript_type": "model_tool_result"`.

Chat Completions-compatible rendering should keep the existing assistant/text
plus `role: tool` request shape for injected fake adapters and non-Codex
providers.

ChatGPT/Codex request preparation should recognize the structured transcript
items and render Responses-compatible input items.

### 3. ChatGPT/Codex Responses request adaptation

Extend `_prepare_chatgpt_codex_request(...)` so provider-specific translation
happens at the adapter boundary.

Behavior:

- Continue hoisting `system` and `developer` content into `instructions`.
- Continue setting `store=False` and `stream=True`.
- Convert structured model-tool-call transcript entries into Responses
  `function_call` input items.
- Convert structured model-tool-result transcript entries into Responses
  `function_call_output` input items.
- Keep support for legacy `role: tool` input conversion only if needed for
  backward compatibility with existing internal tests; new loop code should use
  structured transcript entries.
- Do not synthesize `{}` arguments when original `ModelToolCall.arguments` are
  available.

### 4. Tool choice policy

Add a manifest/runtime policy:

```yaml
runtime:
  execution_policy:
    tool_choice_policy:
      initial: required
      after_tool_result: auto
```

Add an optional node-local override:

```yaml
nodes:
  - id: reason
    kind: llm_step
    tool_choice_policy:
      initial: required
      after_tool_result: auto
```

Implementation notes:

- Add `tool_choice_policy` to `PreparedNode`.
- Store the runtime-level policy on `ExecutionPlan` either as a small mapping or
  a dataclass if that matches nearby policy style during implementation.
- Validate supported values: `auto` and `required`.
- Fail validation when a node sets both legacy `tool_choice` and
  `tool_choice_policy`.
- Initial model requests use node-local policy first, then runtime policy, then
  legacy `tool_choice`.
- Follow-up loop requests use node-local `after_tool_result`, then runtime
  `after_tool_result`, then legacy behavior.
- For Slice R1, `auto` means pass `None` as request `tool_choice`.

### 5. Prompt context tool results

Update `_format_context(...)` so top-level `tool_results` maps each stored
result to `model_facing_output` when available.

This must not mutate `WorkflowExecutionState.tool_results`; raw
`ToolResult.output` remains available to host code.

## Affected Areas

- `src/dynamic_agent_runner/openai_client.py`
  - stream output-item normalization
  - ChatGPT/Codex request adaptation for structured tool transcript input
- `src/dynamic_agent_runner/executor.py`
  - tool-loop transcript construction
  - phase-aware `tool_choice` resolution
  - top-level prompt context formatting
- `src/dynamic_agent_runner/models.py`
  - `PreparedNode.tool_choice_policy`
  - `ExecutionPlan` runtime policy storage if useful
- `src/dynamic_agent_runner/validation.py`
  - runtime and node-local policy validation
  - conflict validation for legacy `tool_choice` plus explicit policy
- `tests/test_openai_client.py`
  - stream and ChatGPT/Codex request translation tests
- `tests/test_executor.py`
  - loop transcript, policy, and `tool_results` rendering tests
- `tests/test_validation.py`
  - invalid policy values and conflict tests
- `README.md` and `docs/files/runtime-policies.rst`
  - update only if implementation exposes manifest policy documentation in the
    same slice

## Compatibility and Migration

Existing behavior must remain compatible for workflows that do not configure
`tool_choice_policy`.

Explicit compatibility points:

- Existing `tool_choice` remains valid when no explicit policy is configured.
- Existing fake adapters should keep receiving the Chat Completions-shaped tool
  transcript unless they use the ChatGPT/Codex provider path.
- Existing `ToolResult.output` remains unchanged in workflow state.
- Existing prompt aliases that unwrap a `ToolResult` directly continue to use
  `model_facing_output`.
- Power Marimo can migrate from `tool_choice: required` to:

  ```yaml
  tool_choice_policy:
    initial: required
    after_tool_result: auto
  ```

Rollback strategy:

- The implementation is additive except for provider-specific request rendering
  and top-level prompt formatting.
- If structured transcript rendering causes incompatibility, keep the internal
  transcript representation but adjust provider renderers; do not expose it as
  public API in R1.

## Validation Strategy

Primary focused checks:

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
pre-commit run --files \
  src/dynamic_agent_runner/openai_client.py \
  src/dynamic_agent_runner/executor.py \
  src/dynamic_agent_runner/models.py \
  src/dynamic_agent_runner/validation.py \
  tests/test_openai_client.py \
  tests/test_executor.py \
  tests/test_validation.py \
  specs/openai-responses-tool-loop-compat/spec.md \
  specs/openai-responses-tool-loop-compat/plan.md \
  specs/openai-responses-tool-loop-compat/tasks.md \
  specs/openai-responses-tool-loop-compat/validation.md
```

Adjust the final `pre-commit` file list to the actual changed files.

## Risks and Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Provider transcript conversion drifts from Responses semantics | ChatGPT/Codex follow-up requests still fail | Keep conversion provider-scoped and verify exact fake request kwargs |
| Structured transcript breaks existing fake adapter assertions | Existing loop tests fail unexpectedly | Preserve Chat Completions-shaped rendering outside ChatGPT/Codex |
| `tool_choice_policy` precedence is unclear | Hidden behavior changes | Fail node-local legacy/policy conflicts and test runtime vs node precedence |
| Top-level `tool_results` formatting changes downstream prompt text | Some prompts may rely on raw `ToolResult` repr | Limit change to top-level prompt context and preserve raw state |
| Stream fallback chooses stale streamed output over completed output | Incorrect normalized response | Completed output remains authoritative when present |

## Rejected Alternatives

- Copy Power Marimo's monkey patch directly. Rejected because it preserves the
  `{}` argument synthesis compromise and keeps provider behavior outside DAR.
- Add a public transcript type in R1. Rejected because durable transcript
  inspection and resume are not part of this feature.
- Make `tool_choice: required` automatically first-turn-only without a policy.
  Rejected because it hides behavior behind legacy configuration and makes
  migration less explicit.

## Readiness

Slice R1 has no blocking `NEEDS CLARIFICATION` items.

The implementation should start with tests, then source changes, then docs/spec
status updates after behavior is passing.
