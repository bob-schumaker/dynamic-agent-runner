# MLX Local-Model Tool-Use Specification

## Metadata

- Feature slug: `mlx-local-model-tool-use`
- Mode: guided
- Artifact type: authoritative SDD follow-up specification
- Status: M6.1 delivered; M6.2 is implementation-ready
- Parent feature: `specs/mlx-local-model-adapter/spec.md`
- Related feature specs:
  - `specs/model-interface-parity/spec.md`
  - `specs/iterative-agent-loop-runtime/spec.md`
  - `specs/tool-invocation-coordinator/spec.md`

## Objective

Make an explicitly configured, in-process MLX backend capable of producing
DAR-normalized tool calls while preserving DAR as the only owner of tool
selection validation, schema validation, approval, invocation, lifecycle,
tracing, and result continuation.

## Problem Statement

The completed MLX adapter is deliberately text-only. It rejects
`OpenAIModelRequest.tools`, renders a plain prompt, and returns only
`ModelResponse(content=...)`. Removing that rejection would not create a tool
contract: the current `mlx_lm` backend has no declared renderer or parser for
tool descriptors, assistant tool calls, or tool results.

MLX needs a small adapter-owned seam that can accept a selected model family's
native template and response syntax, but emits only DAR's strict
`ModelResponse(tool_calls=...)` contract. It must not add another agent loop or
make a generic assumption about every `mlx-lm` tokenizer.

## Scope

This follow-up covers:

1. a caller-injected, versioned `MLXToolCodec` contract for rendering tool-aware
   prompts and parsing model output;
2. adapter gating that enables tool calling only for an explicitly compatible
   codec/backend pair;
3. bounded normalization of a codec's candidate into `ModelToolCall`;
4. transcript rendering for DAR's existing assistant-tool-call and
   `model_tool_result` continuation messages; and
5. deterministic fake-only tests for the codec, sync/async adapter behavior,
   and the existing executor loop.

## Non-Goals

- No MLX server, OpenAI-compatible endpoint, process lifecycle, or scheduler.
- No executor branch, second tool loop, direct handler invocation, approval
  policy, trace policy, or tool-schema policy.
- No tool support for the current stock `_MLXLMBackend` until it explicitly
  supplies a compatible codec/template implementation.
- No live MLX model, Metal, Hugging Face, network, or external-tool call in
  pytest.
- No multi-call/parallel-call support in the first codec slice.
- No structured-output, streaming, embeddings, multimodal, or model-conversion
  expansion.

## Authoritative Contract Decisions

### Codec and backend boundary

`MLXToolCodec` is a caller-injected, versioned protocol. It owns only two
model-family-specific translations:

- render the normalized request messages, exposed tool schemas, and tool choice
  into the selected template; and
- parse one generated model response into either ordinary text or one typed tool
  call candidate.

The adapter owns the safety envelope around that protocol. A codec is not a
tool dispatcher and receives no registry, approval, handler, credential, or
trace collaborator. A backend may advertise tool capability only when it is
paired with the configured codec; otherwise it remains text-only.

The implementation must verify the pinned `mlx-lm` and tokenizer API before
adding a default codec. If no selected tokenizer/template can meet this
contract, the default backend remains unsupported rather than falling back to a
generic text prompt.

### Rendered transcript

The codec receives the complete existing `OpenAIModelRequest`: system,
developer, user, assistant, assistant tool-call, and `model_tool_result`
messages. It must render only the tools supplied on that request and preserve
message order. The codec must structurally serialize the normalized tool-call
ID, name, arguments, and matching tool result on continuation; it must not
interpolate raw handler output into an unrelated prompt string.

### Parse and normalization boundary

The codec returns either text or exactly one tool-call candidate. The adapter
must reject a response that attempts multiple calls, combines a call with
uncontracted trailing prose, uses an unavailable name, repeats a supplied call
ID, exceeds a configured bound, or cannot be parsed unambiguously.

For a call candidate, arguments must decode to a JSON object. The adapter must
reject duplicate JSON object keys, non-finite numbers, excess nesting, excess
members, and byte-limit violations before returning a `ModelResponse`. It must
serialize accepted arguments canonically (sorted keys, compact separators,
finite JSON only) and return them as the normalized `ModelToolCall.arguments`.
Registry schema validation remains the executor/coordinator's responsibility.

A codec-supplied call ID must be non-empty and unique within its response. When
the selected codec permits an omitted ID, the adapter creates a response-scoped
opaque ID from its response ID plus the call ordinal; the continuation renderer
must preserve that same ID. Duplicate supplied IDs are errors. All rejected
model output raises `ModelExecutionError` and returns zero normalized calls.

### Capability truthfulness

`tool_calling` is `False` unless both a configured codec and a backend that
declares compatibility are present. In that state, tool-bearing requests fail
closed before model generation. When both are present, the sync and async
factories report `tool_calling=True` and share the same render/parse path; the
async adapter continues to run that blocking work through `asyncio.to_thread`.

## Functional Requirements

### FR-1: Explicit tool capability

- Given the stock MLX backend and no compatible codec, when a request contains
  tools, then generation fails before the backend is called and capability
  metadata reports `tool_calling=False`.
- Given a compatible injected codec/backend pair, when a request contains
  tools, then the adapter renders through that codec rather than the legacy
  plain-text prompt path.

### FR-2: Strict DAR emission

- Given a valid codec tool-call candidate, when normalization completes, then
  the adapter returns one `ModelToolCall` in `ModelResponse` and invokes no
  handler itself.
- Given malformed, oversized, duplicate, unavailable, or ambiguous candidate
  data, then the adapter raises `ModelExecutionError` before the executor can
  dispatch a tool.

### FR-3: Continuation parity

- Given the executor appends an assistant call and matching tool result, when it
  asks MLX for the next response, then the codec receives and renders those
  normalized transcript messages in order with their same call ID.
- Given that continuation response is text, then the existing executor returns
  it through its ordinary final-response path without an MLX-specific loop.

### FR-4: First-slice bounds

- The first codec supports at most one call per model response.
- Limits for generated response bytes, candidate bytes, argument bytes,
  argument nesting, and argument member count are required configuration or
  fixed documented constants; every limit has a deterministic test.
- The first codec accepts either a text response or a tool call, not both.

## Acceptance and Validation

- Fake codec tests prove initial rendering includes only the exposed schemas and
  preserves request message order.
- Fake codec tests prove continuation rendering contains the canonical call ID,
  name, arguments, and matching `model_tool_result`.
- Parser tests cover valid text, one valid call, invalid JSON, duplicate keys,
  non-finite values, invalid root, unavailable names, duplicate IDs, multiple
  calls, trailing prose, and each bound.
- Sync and async tests prove identical normalization, capability reporting, and
  zero backend call on rejected requests.
- An executor integration test proves one fake MLX call reaches the existing
  coordinator/registry, then the second rendered request contains the result;
  malformed output invokes no handler.
- Focused tests remain fake-only and require no optional MLX import.

## Implementation Readiness

M6.1 delivered this plan and its handoff under the stated gates. M6.2 must
first inspect the installed/pinned `mlx-lm` tokenizer/template API before
claiming a default codec; a missing compatible upstream template is an
implementation result that keeps the default backend unsupported, not authority
to weaken this contract.
