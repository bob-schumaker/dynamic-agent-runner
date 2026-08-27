<!-- markdownlint-disable MD013 -->
# Apple Foundation Models A2 Implementation Plan

Status: approved for implementation planning; no implementation started

## Scope and fixed decisions

A2 adds Apple Foundation Models tool use without transferring tool authority to
the Apple provider. This plan is governed by `spec.md` FR-12 and FR-16.

- Generate one Apple wrapper for each tool exposed to the active DAR node.
- Each `Apple Tool.call(...)` callback creates a DAR invocation request and
  dispatches it through the shared tool-invocation coordinator.
- A callback may never invoke a registered handler or registry directly.
- A synchronous, trusted decision collaborator may return an exact approved,
  denied, cancelled, or expired decision before dispatch. An unresolved decision
  returns a provider-aware DAR interruption before any handler runs; A2 does
  not wait for or implement durable approval resume.
- Preserve coordinator-owned argument validation, exposure, hooks, tracing,
  state, redaction, result shaping, and iteration/completion limits.
- Reject an untranslatable DAR tool schema before creating an Apple session.

Out of scope: streaming, multimodal input, persistent Apple sessions, PCC,
HTTP serving, direct callbacks, durable approval resume, and broad changes to
the executor model-selection path.

## Architecture

`apple_foundation_models.py` remains the provider adapter. Before Apple adoption,
extract the existing executor-private coordinator into a dependency-light
internal module. Its provider-origin request must carry the active execution
plan, prepared node, effective model-facing selected-tool allowlist, mutable
run state, tracer/hooks, retry policy, result key, run/node/tool/call
correlation, and an invocation closure. The executor continues to own node
output and control-flow recording; the coordinator owns only prepared dispatch.

The executor supplies this context through a non-wire adapter invocation
context. It is stripped before `OpenAIModelRequest.to_kwargs()` and trace
serialization, and all non-Apple providers receive byte-for-byte unchanged
wire kwargs. A stale or raw OpenAI tool descriptor is insufficient to construct
a wrapper.

The Apple bridge translates only that active allowlist into wrappers. Each
wrapper converts Apple arguments into the extracted coordinator request. A
typed internal provider interruption carries the original DAR approval
interruption without raw arguments, aborts and cleans up the Apple session, and
is recognized by `AsyncOpenAIClientAdapter` and the executor as a
`WorkflowInterruptedResult`, not a model failure or retry.

The bridge must not own approval policy, registry invocation, lifecycle hooks,
trace emission, state writes, or redaction. Those remain coordinator behavior.

For approval-required callbacks, the coordinator receives a synchronous trusted
decision collaborator bound to the final normalized invocation fingerprint. It
may return `approved`, `denied`, `cancelled`, `expired`, or `unresolved`.
Approved dispatches once; every other status prevents hooks, retries, registry
dispatch, state writes, and handler execution. `unresolved` becomes the typed
provider interruption. This is a per-callback decision, not durable resume.

Each Apple session also owns an atomic callback budget derived from the DAR
tool-call limit. It claims before dispatch, emits a provider-origin trace event,
and aborts generation on exhaustion. One `respond` call is one provider turn;
the plan does not claim executor model-loop iteration parity beyond the bounded
callback budget.

## Milestones

### B0 — Native harness diagnosis

Create a minimal, redacted standalone/pytest comparison that captures Python,
SDK, macOS, availability, session-construction, and generation phase evidence.
In the version-pinned SDK spike, demonstrate `Tool`, `GenerationSchema`, and
`GeneratedContent` construction/callback argument extraction for every admitted
schema shape. Find a reproducible differentiator for native status 255, or
record an environment-limited result and retain standalone execution as the
live gate. No retry or pytest-specific production behavior is permitted.

### B1 — Provider-ingress and interruption contract

Extract the executor-private coordinator into a dependency-light request/outcome
module, migrate direct/model-loop callers under parity tests, and define the
non-wire Apple adapter context plus typed provider interruption propagation.
Define the synchronous exact-fingerprint decision collaborator and atomic
per-session callback budget. Add fake RED tests that prove no handler, registry,
hook, retry, or state mutation happens for a denied/cancelled/expired/unresolved
decision or after cancellation/budget exhaustion.

### B2 — Schema-safe wrapper preparation

Implement one wrapper per active-node exposed tool. The B0 spike defines the
admitted schema subset: object `properties`/`required`/`additionalProperties`,
nested arrays and objects, scalar types, enum, nullability, and supported
numeric/string constraints. Reject `$ref`, composition, patterns/formats, and
unknown or semantically unrepresentable keywords before session creation.
Define injective DAR-tool-id to Apple-wrapper-name mapping and reject invalid or
colliding names. Prove inactive, unexposed, stale-context, and raw-descriptor
tools never reach the Apple session.

### B3 — Coordinator dispatch and response translation

Route callback arguments through the coordinator, serialize only
`ToolResult.model_facing_output` back to Apple, and preserve result redaction,
hooks, trace/state behavior, and the callback budget. Translate an unresolved
approval into the provider-aware executor interruption selected by this plan.
The bridge must define async/cancellation behavior: callbacks cannot re-enter an
event loop, dispatch after session cancellation, or mutate state after session
completion.

### B4 — Evidence and live validation

Add fake tests for validation ordering, allowlist, stale-context/replay, single
dispatch, all decision outcomes, cancellation, traces, redaction, callback
budget, and schema/name rejection. Add an opt-in/manual eligible-Mac smoke with
a no-side-effect sentinel; exactly-once behavior is deterministic fake evidence,
not a nondeterministic live-model assertion. Run the native-harness result from
B0 separately from deterministic test gates.

## Touch points

- `src/dynamic_agent_runner/apple_foundation_models.py`
- `src/dynamic_agent_runner/executor.py`, with a new internal coordinator module
  extracted from its current private coordinator seam
- `src/dynamic_agent_runner/openai_client.py` for the non-wire adapter context
  and typed interruption propagation
- `tests/test_apple_foundation_models.py`, `tests/test_executor.py`, and focused
  coordinator tests
- `README.md`, `spec.md`, `tasks.md`, and `validation.md`

## Verification

Use fake-backed tests first, then `poetry run pytest -q`,
`poetry run ruff check src tests`, `poetry check`, and `poetry build`. Live Apple
callback checks are opt-in and must use the isolated harness validated in B0 or
record the precise status-255 limitation.
