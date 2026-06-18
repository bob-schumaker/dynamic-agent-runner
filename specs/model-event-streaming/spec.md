# Model Event Streaming Feature Specification

## Metadata

- Feature slug: `model-event-streaming`
- Mode: `light`
- Artifact type: future feature specification
- Status: proposed post-`persistent-agent-sessions` feature; not implemented
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Required predecessor:
  - `specs/persistent-agent-sessions/spec.md`
- Related feature packages:
  - `specs/iterative-agent-loop-runtime/spec.md`
  - `specs/context-management-prepare-stage/spec.md`
  - `specs/approval-interruption-resume/spec.md`
  - `specs/capability-status-report/spec.md`

## Objective

Add optional caller-facing streaming of model and tool-progress events produced
during `llm_step` execution, without changing the existing final-result contract
or treating partial deltas as authoritative workflow output.

This feature is explicitly post-`persistent-agent-sessions`. The first intended
public composition is a session-level streaming call such as
`AgentSession.accept_stream(...)`, with lower-level executor support defined only
as needed to implement that session API cleanly.

## Problem Statement

The current OpenAI adapter can request provider streaming and normalize streamed
text into a final `ModelResponse`, but the executor receives only the completed
response. Callers who build UI or interactive agent hosts cannot observe
assistant text deltas, tool-call progress, or loop progress until the workflow
run finishes.

This is especially limiting for persistent agent sessions: a caller may want to
keep a session alive across prompts while rendering the current prompt's
assistant output and tool progress incrementally. That should be possible
without weakening bounded-run semantics, output-contract validation, guardrail
behavior, approval boundaries, or session transcript correctness.

## Design Position

Model event streaming is an **observational, caller-facing event stream**.

It is not:

- the final workflow result
- a trace sink replacement
- a lifecycle hook replacement
- a durable transcript format
- a raw provider event passthrough

The final workflow result remains authoritative. Session history must be updated
only after the run completes successfully and the final output is selected and
validated.

## Why This Is Post-Persistent-Session

Streaming can be useful at the lower executor level, but the most coherent first
caller API is session-oriented:

```python
async for event in session.accept_stream("Inspect the failure."):
    ...
```

That API depends on the session feature owning:

- session id and run correlation
- current session-state retrieval
- restart/snapshot behavior
- per-prompt bounded run ownership
- final transcript update rules

Implementing streaming first would force ad hoc run/session semantics into the
streaming API. Therefore this spec must not be scheduled before
`persistent-agent-sessions` has an approved plan or implementation baseline.

## Users and User Stories

- As an application host, I can render assistant text as it arrives during a
  session prompt.
- As an application host, I can show structured tool progress without exposing
  raw tool arguments or raw tool outputs by default.
- As a workflow caller, I can still receive the same final result after
  streaming completes.
- As a safety reviewer, I can verify partial events do not bypass output
  contracts, approval checks, guardrails, or redaction policy.
- As a model-adapter implementer, I can support streaming where the provider
  supports it and cleanly fall back when it does not.

## Proposed Public Shape

Names are subject to implementation planning, but the v1 target should be close
to:

```python
async for event in session.accept_stream("Continue the analysis."):
    if event.event_type == "output_text_delta":
        ui.append(event.text_delta)
    elif event.event_type == "tool_call_started":
        ui.show_tool(event.tool_name)

result = event.final_result  # only on terminal event, if exposed that way
```

A lower-level executor surface may exist as:

```python
async for event in execute_workflow_events_async(
    execution_context,
    prompt="Continue the analysis.",
):
    ...
```

The session API is the primary product surface for v1. The lower-level executor
API should be added only if it avoids special-case plumbing in sessions.

## Event Contract

The implementation plan should define concrete dataclasses, but the public event
contract must be provider-neutral and structured.

Candidate fields:

- schema version
- event id or sequence
- event type
- session id, when available
- run id
- node id
- model id, when relevant
- iteration number for model-tool loops
- text delta for assistant output
- tool id/name for tool progress
- redacted metadata
- terminal final result or interruption metadata, when relevant
- error metadata for terminal failures

Candidate event types:

- `run_started`
- `model_request_started`
- `message_started`
- `output_text_delta`
- `tool_call_started`
- `tool_call_delta`
- `tool_result_available`
- `model_response_completed`
- `model_tool_loop_turn_started`
- `approval_interrupted`
- `run_completed`
- `run_failed`
- `stream_fallback`

Provider-native event types may be retained in metadata for diagnostics, but
the public event type must be normalized.

## Functional Requirements

### FR-1: Stream optional model events from `llm_step`

The runtime must be able to emit incremental model events from `llm_step` nodes
when streaming is requested and the selected adapter supports streaming.

Acceptance criteria:

- Given streaming is disabled, current workflow execution behavior is unchanged.
- Given streaming is enabled and the adapter supports it, text deltas are
  emitted in order before the final response event.
- Given streaming is enabled and the adapter does not support it, the runtime
  either emits a `stream_fallback` event and returns the ordinary final response
  or fails clearly according to declared policy.
- Given a model returns tool calls, tool-call progress is emitted as structured
  events without exposing raw arguments by default.

### FR-2: Preserve final-result authority

Partial stream events must not replace the existing final workflow result.

Acceptance criteria:

- Final output selection and output-contract validation happen only after the
  model response is complete.
- Session transcript state is updated only from validated final output, not from
  partial text deltas.
- If a run fails or is interrupted, partial emitted text remains observational
  and is not recorded as a successful assistant turn.
- Callers can still obtain the same final result they would have received
  through non-streaming execution.

### FR-3: Compose with persistent sessions

Streaming must integrate with `AgentSession` without creating a separate session
state model.

Acceptance criteria:

- `AgentSession.accept_stream(...)` correlates all events with the active
  session id and run id.
- Current session state remains retrievable during or after a streaming run.
- Snapshot/restart behavior remains based on committed session state, not
  uncommitted partial deltas.
- Same-session concurrency behavior follows the persistent-session policy:
  streaming accept calls serialize or fail clearly rather than interleaving
  turns.

### FR-4: Stream model-tool loop progress

Streaming must expose useful progress for bounded model-tool loops without
weakening loop safety.

Acceptance criteria:

- Loop turn start, tool-call start, tool-result availability, and loop stop
  events are emitted in order.
- Max-iteration, tool-failure, model-failure, and approval-interruption stop
  reasons remain visible.
- Approval-required model-emitted tool calls still pause before invocation.
- Tool results are redacted or summarized by default; raw payload streaming is
  deferred to a separate explicit policy.

### FR-5: Keep tracing and lifecycle hooks separate

Streaming must not overload the existing trace or lifecycle-hook APIs.

Acceptance criteria:

- Trace events remain observability/audit events with existing redaction
  behavior.
- Lifecycle hooks remain trusted callback checkpoints around node, model, tool,
  and workflow boundaries.
- Streaming events are delivered through a distinct stream API or stream sink.
- Implementations may emit matching trace events, but callers must not depend on
  trace sinks for user-facing streaming.

### FR-6: Handle cancellation and backpressure honestly

The stream API must define what happens when a caller stops consuming events.

Acceptance criteria:

- If the caller cancels stream consumption, the active model request or workflow
  run is cancelled where the provider/runtime supports cancellation.
- If cancellation cannot stop an in-flight provider request, the runtime reports
  that limitation clearly.
- Event delivery preserves ordering for one run.
- The implementation plan must choose either iterator backpressure or explicit
  bounded buffering; unbounded event queues are not allowed.

### FR-7: Report streaming capability

Capability/status reporting should distinguish non-streaming adapters,
fallback-only behavior, and live streaming support.

Acceptance criteria:

- Given a package or caller requests streaming, when the selected adapter cannot
  stream, capability/status reports missing or fallback support.
- Given the adapter can stream text but not structured tool deltas, status
  reports partial streaming capability.
- Given streaming is disabled, status does not imply streaming is active.

## Non-Functional Requirements

- Streaming APIs must be async-first.
- Sync wrappers for streaming are out of scope unless a later plan proves a
  clean iterator-safe design.
- Event objects must be serializable using ordinary Python data structures.
- Event payloads must avoid raw sensitive tool data by default.
- Unit tests must use fake streaming adapters and fake tool registries.
- Tests must not make live OpenAI, MCP, Hugging Face, Marimo, or local model
  calls.

## In Scope

- Provider-neutral `ModelStreamEvent` or equivalent event contract.
- Optional adapter streaming protocol.
- Session-level `accept_stream(...)` API after persistent sessions exist.
- Lower-level executor stream API only if needed for session implementation.
- Text delta events from model output.
- Structured tool-progress events for model-tool loops.
- Fallback behavior for non-streaming adapters.
- Cancellation/backpressure semantics.
- Capability/status reporting for streaming support.

## Out of Scope

- Implementing streaming before persistent sessions have an approved plan or
  baseline.
- Raw provider event passthrough as the public API.
- Streaming raw tool arguments/results by default.
- Durable storage of partial deltas.
- UI rendering components.
- WebSocket, SSE, HTTP server, or CLI-specific streaming transports.
- Sync streaming wrappers in v1.
- Changing output-contract validation to operate on partial deltas.

## Error Behavior

- Unsupported streaming requests should fail clearly or emit explicit fallback
  events according to policy.
- Provider stream errors should produce terminal error events and package-owned
  exceptions consistent with existing model failure behavior.
- Cancellation should produce a terminal cancellation/error event when possible.
- Partial text emitted before a failure must not be reported as a successful
  final result.

## Security and Privacy Considerations

Streaming exposes sensitive model output earlier than final-result handling.
Callers own user-facing display and persistence of streamed content.

Raw tool arguments and raw tool outputs may contain secrets, workspace data, or
private source context. They must not be streamed by default. Tool-progress
events should use ids, names, status, and redacted/summarized metadata unless a
future explicit policy enables raw payloads.

## Relationship to Existing Specs

- `persistent-agent-sessions` is the required predecessor and owns the primary
  session-level API surface.
- `iterative-agent-loop-runtime` owns bounded model-tool loop execution and loop
  stop semantics; this spec owns caller-facing progress events for those loops.
- `context-management-prepare-stage` owns prompt preparation and compaction;
  this spec must not stream uncommitted compaction internals unless they are
  exposed as explicit diagnostics.
- `approval-interruption-resume` owns approval pause/resume behavior; this spec
  may emit approval-interrupted events but must not implement durable approval
  resume.
- `capability-status-report` owns capability/status vocabulary for live,
  fallback, missing, and metadata-only streaming support.

## Validation Checklist

Implementation should provide focused tests for:

- non-streaming execution remains unchanged
- text deltas emit in provider order and final result remains authoritative
- non-streaming adapter fallback behavior
- model-tool loop progress event ordering
- approval interruption event emission without tool invocation
- cancellation behavior for a fake async stream
- session `accept_stream(...)` correlation with session id and run id
- no session history update from partial deltas before final success
- no raw tool arguments/results in default stream events
- capability/status reporting for supported, fallback, and missing streaming

Validation commands should include at least:

```bash
poetry run pytest tests/test_model_event_streaming.py -q
poetry run pytest tests/test_openai_client.py -q
poetry run pytest tests/test_executor.py -q
poetry run ruff check src tests
```

## Open Questions

- Should the lower-level executor expose an async event iterator, a stream sink,
  or both?
- Should event streams include prepared-input diagnostics, or should those
  remain trace-only?
- Should text deltas be emitted before or after any redaction/filtering layer
  once output guardrails exist?
- How should structured output streaming interact with final JSON validation?
- Should terminal events carry the full `WorkflowResult`, a session-specific
  result wrapper, or only a result reference?

## Approval State

This is a proposed post-`persistent-agent-sessions` feature spec. It is not
implementation authorization. Do not implement this feature until persistent
agent sessions have an approved plan or baseline and this spec has its own
approved implementation plan/tasks or explicit user waiver.
