# Provider-Backed Context Compaction Plan

## Objective

Add an opt-in, caller-owned provider compactor for validated replacement history
at pre-turn and one-shot overflow-retry boundaries without adding a provider
transport, persistence, or mid-turn tool-loop behavior to DAR.

## Existing Seams

- `prepare_model_input(...)` is synchronous and already routes thresholded
  pre-turn compaction through an injected callback.
- `_retry_model_after_context_overflow_async(...)` has a one-shot retry seam
  using the same prepared-input callback.
- `WorkflowExecutionContext` groups reusable collaborators, but currently has
  no compactor field; direct execution accepts an untyped callback separately.
- Capability reporting currently labels declared compaction metadata only.

## Architecture

1. Add `context_compaction.py` with the public typed request, result, and
   caller-owned compactor protocol specified in `spec.md`.
2. Thread `provider_context_compactor` through `WorkflowExecutionContext`,
   sync/async execution entry points, normalization, preparation, and the
   retained `PreparedModelInput` state. Preserve the existing rejection of
   extra execution keywords when a context object is supplied.
3. Extend manifest validation for the narrow `implementation: provider` /
   `strategy: provider_remote` policy and its `remote` mapping. Preserve all
   existing injected, metadata-only, basic, and model-summary behavior.
4. At pre-turn and overflow-retry only, check policy, collaborator capability,
   token threshold, and protected message boundaries before invoking the
   collaborator. Validate bounded replacement history before installing it.
5. Emit redacted metadata and capability status only. Never emit replacement
   messages, provider payloads, credentials, or a raw provider window id.

## Replacement Invariants

- Replacement is a non-empty ordered tuple of supported `OpenAIMessage` roles.
- The caller cannot remove or reorder system/developer hierarchy messages when
  `preserve_system_messages` is true.
- The active user message remains the final user message for pre-turn
  replacement.
- Replacement count is at most `max_replacement_messages`.
- A replacement must reduce estimated tokens unless the request was an
  overflow retry; the retry may retain size only when the provider supplies a
  lower baseline, which is recorded as metadata.
- Tool-call/result transcript pairs and iterative-loop mid-turn state are not
  eligible in this slice.

## Error and Fallback Policy

| Condition | `fallback: basic` | `fallback: error` |
| --- | --- | --- |
| collaborator absent or capability absent | existing deterministic basic compaction | `WorkflowExecutionError` before the model request |
| collaborator raises or returns malformed replacement | existing deterministic basic compaction with redacted error category | `WorkflowExecutionError` with redacted category |
| protected-boundary invariant fails | existing deterministic basic compaction with redacted error category | `WorkflowExecutionError` with redacted category |

`basic` means DAR's existing deterministic compaction only; it never calls a
model summarizer or a second provider collaborator.

## Delivery Boundaries

- No live provider, LiteLLM, or OpenAI calls in tests.
- No endpoint, credential, or provider-specific request model in DAR.
- No persistent window state; window/baseline metadata belongs to the current
  prepared input and trace only.
- No mid-turn, tool-loop, session-resume, or concurrent compaction behavior.
- No new dependency.

## Verification Strategy

Use fake compactor implementations to prove capability gating, success,
replacement validation, fallback/error behavior, redaction, and unmodified
legacy compaction paths. Run focused validation/executor/capability/import
tests, full pytest, Ruff, package build, and docs build before delivery.
