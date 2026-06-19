# Model Event Streaming Feature Specification

## Metadata

- Feature slug: `model-event-streaming`
- Mode: `light`
- Artifact type: implemented-baseline plus future expansion specification
- Status: implemented v1 session event-stream baseline; provider-native text
  deltas, model-tool-loop progress specialization, cancellation/backpressure
  expansion, and capability/status reporting remain deferred
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
`AgentSession.accept_stream(...)`. Lower-level executor event iterator APIs
remain deferred.

## Problem Statement

The current OpenAI adapter can request provider streaming and normalize streamed
text into a final `ModelResponse`, but the executor receives only the completed
response. The v1 session event stream exposes redacted execution lifecycle and
prepared-input events while a run is active; callers still cannot observe
provider-native assistant text deltas, tool-call deltas, or specialized loop
progress events until future expansion work is approved.

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

## Implemented V1 Boundary

The implemented v1 baseline adds session-level event streaming through
`AgentSession.accept_stream(...)`.

V1 behavior:

- streams redacted execution events while a session accepts one prompt
- correlates events with `session_id`, `run_id`, sequence, and `node_id`
- maps `workflow_started` to caller-facing `run_started`
- emits existing prepared-input diagnostics, including pruning-context and
  graph-mutation metadata, through redacted event payloads
- emits a terminal `run_completed` event carrying the authoritative final result,
  the same `AgentSessionResult` shape returned by `accept(...)`, and convenient
  `workflow_result` access for callers that need full execution state such as
  structured tool results
- lets callers choose progress events, terminal events, terminal session-result
  attachment, and progress event-type filters
- updates `AgentSessionState` only after successful bounded-run completion
- preserves same-session concurrency rejection

V1 does not add provider-native token deltas, raw provider event passthrough,
tool-progress specialization, sync streaming wrappers, durable partial-delta
storage, or streaming capability/status reporting.

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

Implementing streaming first would have forced ad hoc run/session semantics into
the streaming API. `persistent-agent-sessions` now provides the required
in-memory session baseline, and v1 streaming is implemented on that surface.

## Users and User Stories

- As an application host, I can render assistant text as it arrives during a
  session prompt.
- As an application host, I can show structured tool progress without exposing
  raw tool arguments or raw tool outputs by default.
- As a workflow caller, I can still receive the same final result after
  streaming completes.
- As an application host, I can optionally receive the terminal
  `AgentSessionResult`/`WorkflowResult` when structured run state is needed, or
  omit that attachment when only scalar final output is needed.
- As a safety reviewer, I can verify partial events do not bypass output
  contracts, approval checks, guardrails, or redaction policy.
- As a model-adapter implementer, I can support streaming where the provider
  supports it and cleanly fall back when it does not.

## Implemented Public Shape

The implemented v1 surface is:

```python
async for event in session.accept_stream("Continue the analysis."):
    if event.event_type == "model_input_prepared":
        ui.show_context_status(event.payload)
    elif event.event_type == "run_completed":
        result = event.final_result
        workflow_result = event.workflow_result
```

Callers can use `include_progress_events`, `include_terminal_event`,
`include_terminal_session_result`, and `progress_event_types` to reduce the
surface they consume.

A lower-level executor surface may exist as:

```python
async for event in execute_workflow_events_async(
    execution_context,
    prompt="Continue the analysis.",
):
    ...
```

The session API is the primary product surface for v1. The lower-level executor
API should be added only if a future slice proves it avoids special-case
plumbing in sessions.

## Event Contract

The public event contract is provider-neutral and structured.

Implemented v1 fields:

- event id or sequence
- event type
- session id
- run id
- node id
- redacted metadata
- terminal final result on `run_completed`
- terminal `session_result` and `workflow_result` access on completed or
  interrupted runs
- caller-controlled stream flags for progress events, terminal events,
  terminal result attachment, and progress event-type filters

Future candidate fields:

- schema version
- model id, when relevant
- iteration number for model-tool loops
- text delta for assistant output
- tool id/name for tool progress
- interruption metadata, when relevant
- error metadata for terminal failures

Implemented v1 event types include existing redacted execution events plus:

- `run_started`
- `model_input_prepared`
- `run_completed`

Future candidate event types:

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

Future runtime expansion should be able to emit incremental model events from
`llm_step` nodes when streaming is requested and the selected adapter supports
streaming. The implemented v1 baseline streams redacted execution events and
prepared-input diagnostics, not provider-native token deltas.

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

Future streaming expansion should expose useful progress for bounded model-tool
loops without weakening loop safety.

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
- Redacted progress-event payloads must be serializable using ordinary Python
  data structures.
- Terminal `AgentSessionResult`/`WorkflowResult` attachments are in-process
  result handoffs, not redacted external telemetry payloads; callers can omit
  them with `include_terminal_session_result=False`.
- Progress-event payloads must avoid raw sensitive tool data by default.
- Unit tests must use fake streaming adapters and fake tool registries.
- Tests must not make live OpenAI, MCP, Hugging Face, Marimo, or local model
  calls.

## In Scope

- Provider-neutral `AgentSessionStreamEvent` event contract.
- Session-level `AgentSession.accept_stream(...)` API after persistent sessions
  exist.
- Redacted execution-event streaming from the existing trace seam.
- Terminal final-result authority through a `run_completed` event, with optional
  terminal `AgentSessionResult`/`WorkflowResult` access.
- Caller controls for progress events, terminal events, terminal session-result
  attachment, and progress event-type filtering.
- Session-state commit only after successful bounded-run completion.
- Future optional adapter streaming protocol.
- Future text delta events from model output.
- Future structured tool-progress events for model-tool loops.
- Future fallback behavior for non-streaming adapters.
- Future cancellation/backpressure semantics.
- Future capability/status reporting for streaming support.

## Out of Scope

- Implementing streaming before persistent sessions have an approved plan or
  baseline.
- Raw provider event passthrough as the public API.
- Streaming raw tool arguments/results in progress-event payloads by default.
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
private source context. They must not appear in redacted progress-event payloads
by default. Tool-progress events should use ids, names, status, and
redacted/summarized metadata unless a future explicit policy enables raw
payloads. Terminal `WorkflowResult` access can expose ordinary execution state,
including `tool_results`; that is an in-process result handoff for trusted
callers and can be disabled per stream.

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

Implementation provides focused tests for the v1 baseline:

- session `accept_stream(...)` correlation with session id and run id
- no session history update before terminal success
- final result remains authoritative on `run_completed`
- redacted context-preparation diagnostics are streamed without transcript text
- pruning-context and graph-mutation diagnostics compose with the stream

Future streaming expansion slices should provide focused tests for:

- non-streaming execution remains unchanged
- text deltas emit in provider order and final result remains authoritative
- non-streaming adapter fallback behavior
- model-tool loop progress event ordering
- approval interruption event emission without tool invocation
- cancellation behavior for a fake async stream
- no raw tool arguments/results in default stream events
- capability/status reporting for supported, fallback, and missing streaming

### Completed Client-Requested Follow-Up: Terminal Results and Stream Filters

Power Marimo reported that consuming `AgentSession.accept_stream(...)` would
regress notebook analysis rendering because terminal events previously exposed
only redacted stream events plus `final_result`, while its renderer needs
`WorkflowResult.state.tool_results` for structured tables and project-data
payloads. In response, the implemented v1 stream contract now:

- attaches terminal `session_result` and `workflow_result` access by default
- keeps intermediate progress events redacted
- supports terminal-only, progress-only, no-terminal-session-result, and
  progress-event-type-filtered consumption through `accept_stream(...)` flags

The client-requested regression coverage lives in `tests/test_agent_sessions.py`
and verifies terminal workflow-result access, terminal-only streaming,
omitting terminal session-result attachment, and progress event-type filtering.

Validation commands should include at least:

```bash
poetry run pytest tests/test_agent_sessions.py -q -k accept_stream
poetry run pytest tests/test_agent_sessions.py tests/test_executor.py -q
poetry run ruff check src tests
```

## Open Questions

- Should the lower-level executor expose an async event iterator, a stream sink,
  or both?
- Should text deltas be emitted before or after any redaction/filtering layer
  once output guardrails exist?
- How should structured output streaming interact with final JSON validation?

## Settled V1 Decisions

- Session event streams include redacted prepared-input diagnostics, including
  pruning-context metadata, rather than leaving those diagnostics trace-only.
- Terminal `run_completed` and `approval_interrupted` events carry the
  authoritative final result when available and, by default, the same
  `AgentSessionResult` shape returned by `accept(...)`; intermediate progress
  events remain redacted.

## Approval State

The v1 session event-stream baseline and the Power Marimo client-requested
terminal-result/filter follow-up are implemented by explicit user request.
Further provider-native streaming, model-tool-loop progress events,
capability/status reporting, and cancellation/backpressure expansion require a
new approved plan/tasks slice before implementation.
