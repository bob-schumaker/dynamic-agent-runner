
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
