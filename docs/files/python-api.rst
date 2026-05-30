
.. header1:: Python API Usage

The public API supports loading, synchronous execution, asynchronous execution,
and lower-level execution-state inspection.

.. header2:: Loading without execution

Use ``load_agent_workflow(...)`` to parse and validate a package without model or
tool calls:

.. code-block:: python

   from dynamic_agent_runner import load_agent_workflow

   workflow = load_agent_workflow(
       runtime_manifest="path/to/agent-runtime.yaml",
       agent_design="path/to/agent-design.md",
       mermaid_graph="path/to/agent-graph.mmd",
       tool_index="path/to/tool-index.yaml",
       runtime_overrides="path/to/runtime-overrides.yaml",
       tool_registry=my_tool_registry,
   )

``runtime_manifest`` is the preferred argument name. ``definition_yaml`` remains a
compatibility alias. ``mermaid_diagram`` is accepted as an alias for
``mermaid_graph``.

.. header2:: Synchronous execution

Use ``run_agent_workflow(...)`` for a direct final result:

.. code-block:: python

   from dynamic_agent_runner import run_agent_workflow

   result = run_agent_workflow(
       prompt="Run this workflow.",
       runtime_manifest="path/to/agent-runtime.yaml",
       agent_design="path/to/agent-design.md",
       tool_registry=my_tool_registry,
       model_adapter=my_model_adapter,
       max_steps=20,
       run_id="example-run-1",
   )

The synchronous API wraps the async implementation. It raises a project error if
called from an already-running event loop; event-loop callers should use the async
API instead.

.. header2:: Asynchronous execution

Use ``run_agent_workflow_async(...)`` in async applications:

.. code-block:: python

   from dynamic_agent_runner import run_agent_workflow_async

   result = await run_agent_workflow_async(
       prompt="Run this workflow.",
       runtime_manifest="path/to/agent-runtime.yaml",
       agent_design="path/to/agent-design.md",
       tool_registry=my_tool_registry,
       model_adapter=my_async_model_adapter,
   )

The async path awaits async model adapters, async tool handlers, and async
lifecycle hooks. Synchronous tool handlers are dispatched without blocking the
event loop.

.. header2:: Reusable execution contexts

Use ``WorkflowExecutionContext`` or its alias ``RunContext`` when several runs
share a loaded workflow and runtime collaborators:

.. code-block:: python

   from dynamic_agent_runner import WorkflowExecutionContext, load_agent_workflow
   from dynamic_agent_runner import run_agent_workflow

   workflow = load_agent_workflow(
       runtime_manifest="path/to/agent-runtime.yaml",
       agent_design="path/to/agent-design.md",
       tool_registry=my_tool_registry,
   )
   context = WorkflowExecutionContext(
       workflow=workflow,
       tool_registry=my_tool_registry,
       model_adapter=my_model_adapter,
       max_steps=20,
       trace_sink=my_trace_sink,
   )

   result = run_agent_workflow(
       execution_context=context,
       prompt="Run this workflow with shared collaborators.",
   )

When ``execution_context`` is supplied to high-level APIs, do not also pass
artifact paths or runtime collaborators as separate keyword arguments.

.. header2:: Inspecting detailed execution state

Use ``execute_workflow(...)`` or ``execute_workflow_async(...)`` when you need the
``WorkflowResult`` object:

.. code-block:: python

   from dynamic_agent_runner import execute_workflow

   workflow_result = execute_workflow(
       workflow,
       prompt="Run and keep state.",
       tool_registry=my_tool_registry,
       model_adapter=my_model_adapter,
   )

   final_result = workflow_result.final_result
   trace_events = workflow_result.state.trace_events
   retry_records = workflow_result.state.retry_records
   token_usage = workflow_result.state.token_usage

The execution state records node inputs, node outputs, tool results, completed
node executions, retry records, token usage, trace events, errors, run ID, and
final result.
