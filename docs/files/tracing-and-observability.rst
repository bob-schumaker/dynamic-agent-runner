
.. header1:: Tracing and Observability

The runtime provides package-owned trace events without requiring external
observability dependencies.

.. header2:: Capturing trace events

``execute_workflow(...)`` and ``execute_workflow_async(...)`` return a
``WorkflowResult`` with detailed state:

.. code-block:: python

   result = execute_workflow(
       workflow,
       prompt="Run with traces.",
       tool_registry=registry,
       model_adapter=model_adapter,
   )

   for event in result.state.trace_events:
       print(event.event_type, event.node_id, event.payload)

High-level ``run_agent_workflow(...)`` returns only the final result, but accepts
an optional ``trace_sink`` so callers can receive events as they are emitted.

.. header2:: Session event streaming

``AgentSession.accept_stream(...)`` exposes a session-level event stream for one
bounded prompt. The stream forwards redacted trace-derived events with session
and run correlation, maps ``workflow_started`` to ``run_started``, and emits a
terminal ``run_completed`` event with the authoritative final result after
successful state persistence. The terminal event also carries
``session_result`` and ``workflow_result`` access for callers that need the full
``WorkflowResult`` state, including structured tool results. Approval
interruptions emit ``approval_interrupted`` with the interruption reason and the
interrupted session result.

Callers can choose how much of the stream to consume with
``include_progress_events``, ``include_terminal_event``,
``include_terminal_session_result``, and ``progress_event_types``. This supports
terminal-only callers, progress-only observers, and renderers that want only a
small subset of redacted lifecycle events.

This is provider-neutral event streaming, not provider-native token streaming.
Token deltas, lower-level executor iterators, and specialized model-tool loop
progress events remain future work.

.. header2:: Event coverage

Current trace events cover:

- workflow start, completion, and error
- node start, completion, and error
- model request and response
- prompt-cache eligibility checks and provider cached-token telemetry
- token-budget checks
- tool start, invocation, result, and finish
- retry attempts and outcomes
- decision routes
- fallback status notices

.. header2:: Redaction

Trace payloads identify prompt, request, response-content, tool-argument,
tool-output, node-output, and final-result fields as sensitive where applicable.
Use ``TraceEvent.redacted_payload()`` or ``TraceEvent.redacted()`` before sending
trace data to external systems.

Redaction is intentionally shallow today. Deep recursive redaction and external
Logfire/OpenTelemetry integrations remain future extension areas.

.. header2:: Run correlation

Each workflow run has a ``run_id``. Callers may provide one explicitly or let the
runtime generate it. Trace events and lifecycle hook contexts carry the run ID so
concurrent executions sharing a workflow or context can be distinguished.

.. header2:: Lifecycle hooks

Trusted in-process lifecycle hooks can observe workflow, node, model, and tool
boundaries. Hook implementations can be synchronous or asynchronous. Trusted
hooks may raise project errors to abort execution. Shell hooks, plugin loading,
and untrusted hook sources are out of scope.
