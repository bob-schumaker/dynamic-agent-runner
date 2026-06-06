
.. header1:: Python API Usage

The public API supports loading, synchronous execution, asynchronous execution,
and lower-level execution-state inspection.

.. header2:: Loading without execution

Use ``load_agent_workflow(...)`` to parse and validate a canonical package
directory without model or tool calls:

.. code-block:: python

   from dynamic_agent_runner import load_agent_workflow

   workflow = load_agent_workflow(
       package_directory="path/to/agent-package",
       runtime_overrides="path/to/runtime-overrides.yaml",
       tool_registry=my_tool_registry,
   )

``package_directory`` is the canonical public input. Lower-level
``runtime_manifest``/``definition_yaml`` and related artifact arguments remain
available as compatibility seams when callers need file-by-file loading.

.. header2:: Synchronous execution

Use ``run_agent_workflow(...)`` for a direct final result:

.. code-block:: python

   from dynamic_agent_runner import run_agent_workflow

   result = run_agent_workflow(
       prompt="Run this workflow.",
       package_directory="path/to/agent-package",
       runtime_overrides="path/to/runtime-overrides.yaml",
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
       package_directory="path/to/agent-package",
       runtime_overrides="path/to/runtime-overrides.yaml",
       tool_registry=my_tool_registry,
       model_adapter=my_async_model_adapter,
   )

The async path awaits async model adapters, async tool handlers, and async
lifecycle hooks. Synchronous tool handlers are dispatched without blocking the
event loop.

.. header2:: Local OpenAI-compatible endpoints

Use ``LocalOpenAIEndpointConfig`` when a caller owns a local server that exposes
an OpenAI-compatible Responses API:

.. code-block:: python

   from dynamic_agent_runner import (
       LocalOpenAIEndpointConfig,
       create_local_async_openai_adapter,
   )

   adapter = create_local_async_openai_adapter(
       LocalOpenAIEndpointConfig(
           base_url="http://localhost:11434/v1",
           model_aliases=("local-chat",),
           provider_name="local-openai-compatible",
           expected_model_id="local-chat",
       )
   )

The local helpers reuse the package's OpenAI adapter boundary, mark the adapter
as local for capability routing, and translate local endpoint connectivity,
protocol, and model-identity failures into package-owned errors. They do not
start or supervise a local model server.

.. header2:: Reusable execution contexts

Use ``WorkflowExecutionContext`` or its alias ``RunContext`` when several runs
share a loaded workflow and runtime collaborators:

.. code-block:: python

   from dynamic_agent_runner import WorkflowExecutionContext, load_agent_workflow
   from dynamic_agent_runner import run_agent_workflow

   workflow = load_agent_workflow(package_directory="path/to/agent-package")
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

.. header2:: Lifecycle hooks and prompt-cache observations

``WorkflowLifecycleHooks`` provides trusted in-process callbacks around workflow,
node, model, and tool boundaries. Hooks may be synchronous or asynchronous and
may abort execution by raising a project error.

``prompt_cache=True`` can request provider-neutral prompt-cache observation for a
run when manifest metadata is absent. ``prompt_cache=False`` disables
prompt-cache observation for that run. The runtime records eligibility evidence
and provider cached-token telemetry in trace events when that data is available.
