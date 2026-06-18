
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

.. header2:: Capability inspection

Use ``inspect_agent_package_capabilities(...)`` to preflight a package without
executing model, tool, or retriever calls:

.. code-block:: python

   from dynamic_agent_runner import inspect_agent_package_capabilities

   report = inspect_agent_package_capabilities(
       package_directory="path/to/agent-package",
       tool_registry=my_tool_registry,
       guardrail_registry=my_guardrail_registry,
       model_adapter=my_model_adapter,
       model_adapter_coverage="strict",
   )

   for item in report.items:
       print(item.id, item.state, item.summary)

The report marks implemented runtime surfaces as ``live``, preserved metadata as
``metadata_only``, missing collaborators as ``missing_collaborator``, and invalid
packages as ``invalid``. It is a readiness report, not an execution trace.

.. header2:: Input guardrails

Input guardrails declared under ``extensions.guardrails`` run before workflow
execution when a matching caller-owned registry is supplied to
``execute_workflow(...)``, ``execute_workflow_async(...)``, or
``WorkflowExecutionContext``:

.. code-block:: python

   from dynamic_agent_runner import (
       GuardrailDecision,
       GuardrailResult,
       InMemoryGuardrailRegistry,
       WorkflowExecutionContext,
       execute_workflow,
       load_agent_package_workflow,
   )

   guardrails = InMemoryGuardrailRegistry(
       {
           "no_secrets": lambda prompt: GuardrailResult(
               guardrail_id="no_secrets",
               decision=(
                   GuardrailDecision.ABORT
                   if "secret" in str(prompt).lower()
                   else GuardrailDecision.PASS
               ),
               reason_code="secret_detected",
           )
       }
   )

   context = WorkflowExecutionContext(
       workflow=load_agent_package_workflow("path/to/agent-package"),
       guardrail_registry=guardrails,
       model_adapter=my_model_adapter,
   )

   result = execute_workflow(context, prompt="Run this workflow.")

Missing declared input guardrail handlers fail closed. Non-input guardrail
phases are currently validated and preserved as metadata.

.. header2:: Model adapter coverage

Execution APIs accept ``model_adapter_coverage`` to define whether caller
provided adapters are authoritative or may be augmented by the package's default
OpenAI adapter.

``"augmented"`` is the default. Supplied adapters are tried first, and the
runtime may create a default OpenAI adapter when eligible model coverage is
missing:

.. code-block:: python

   result = run_agent_workflow(
       prompt="Run this workflow.",
       package_directory="path/to/agent-package",
       model_adapter=[local_adapter],
       model_adapter_coverage="augmented",
   )

``"strict"`` means the supplied adapter list must cover the selected model or
capability requirements. ``model_adapter=None``, ``model_adapter=[]``, or a
nonmatching supplied adapter raises ``WorkflowExecutionError`` before any
default OpenAI adapter is created:

.. code-block:: python

   result = run_agent_workflow(
       prompt="Run this workflow.",
       package_directory="path/to/agent-package",
       model_adapter=[local_adapter],
       model_adapter_coverage="strict",
   )

The same keyword is accepted by ``run_agent_workflow(...)``,
``run_agent_workflow_async(...)``, ``execute_workflow(...)``,
``execute_workflow_async(...)``, and ``WorkflowExecutionContext``. Clients that
require local-only execution should supply only local adapters with strict
coverage. ``llm_step.model_requirements`` metadata such as ``local_only`` no
longer filters adapter selection.

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

Local model asset resolution is available through the package-owned helpers in
``dynamic_agent_runner.local_models``. Those helpers resolve explicit paths,
configured cache roots, default local cache roots, and optional Hugging Face file
or snapshot references; they keep downloading and server supervision caller
controlled. Install with the ``huggingface`` extra before using Hugging
Face-backed discovery or downloads.

.. header2:: Direct llama.cpp local models

Use ``LlamaCppLocalModelConfig`` when a caller owns a GGUF model and wants
direct in-process llama.cpp text generation through the normal adapter contract:

.. code-block:: python

   from dynamic_agent_runner import (
       LlamaCppLocalModelConfig,
       create_llama_cpp_local_async_adapter,
   )

   adapter = create_llama_cpp_local_async_adapter(
       LlamaCppLocalModelConfig(
           model_aliases=("llama-local-chat",),
           model_path="path/to/model.gguf",
           expected_model_id="Qwen/Qwen3-4B-Instruct-2507",
       )
   )

   result = await run_agent_workflow_async(
       prompt="Run locally on llama.cpp.",
       package_directory="path/to/agent-package",
       model_adapter=[adapter],
       model_adapter_coverage="strict",
   )

The direct llama.cpp helpers lazily import ``llama-cpp-python`` for the default
in-process backend; install ``dynamic-agent-runner[llamacpp]`` before using that
backend. They resolve local model assets before generation, normalize generated
text into the package ``ModelResponse`` contract, and do not require a local
server. If a caller already exposes llama.cpp through an OpenAI-compatible local
server, use ``LocalOpenAIEndpointConfig`` instead.

Use ``profile_llama_cpp_model_memory_fit(...)`` when a caller wants an advisory
context-window fit check before constructing a llama.cpp backend:

.. code-block:: python

   from dynamic_agent_runner import profile_llama_cpp_model_memory_fit

   profile = profile_llama_cpp_model_memory_fit(
       config,
       requested_context_tokens=32768,
       memory_budget_bytes=24 * 1024 * 1024 * 1024,
       profiler=my_profiler,
   )

The profiler is caller-supplied. Without one, fail-open mode returns an
``unavailable`` result; strict mode raises ``LlamaCppMemoryFitProfileError``.

.. header2:: macOS MLX local models

Use ``MLXLocalModelConfig`` when a macOS caller owns a converted MLX model
directory and wants in-process local text generation through the normal adapter
contract:

.. code-block:: python

   from dynamic_agent_runner import (
       MLXLocalModelConfig,
       create_mlx_local_async_adapter,
   )

   adapter = create_mlx_local_async_adapter(
       MLXLocalModelConfig(
           model_aliases=("mlx-local-chat",),
           model_path="path/to/mlx-model-directory",
           expected_model_id="mlx-community/example-model",
       )
   )

   result = await run_agent_workflow_async(
       prompt="Run locally on MLX.",
       package_directory="path/to/agent-package",
       model_adapter=[adapter],
       model_adapter_coverage="strict",
   )

MLX helpers are macOS-only, but importing the package and constructing an adapter
remain safe on other platforms. Generation on non-macOS fails before model
resolution or dependency loading. The default in-process backend lazily imports
``mlx-lm``. MLX helpers validate converted model directories before generation,
normalize generated text into the package ``ModelResponse`` contract, and reject
unsupported tool-call or structured-output requests. Use strict coverage for
local-only execution. If a caller already exposes an MLX model through an
OpenAI-compatible local server, use ``LocalOpenAIEndpointConfig`` instead.

.. header2:: Hugging Face model discovery

Use ``search_hugging_face_models(...)`` to search Hugging Face models through a
read-only, repository-owned result contract:

.. code-block:: python

   from dynamic_agent_runner import search_hugging_face_models

   results = search_hugging_face_models(
       "qwen gguf",
       limit=5,
       task="text-generation",
       tags=("gguf",),
       sort="downloads",
       direction="desc",
   )

   first_repo_id = results[0].repo_id

Each result is a ``HuggingFaceModelSearchResult`` with normalized summary fields
such as ``repo_id``, ``display_name``, ``task``, ``tags``, ``likes``,
``downloads``, and ``last_modified``. Discovery is separate from execution: a
matching model is not automatically downloadable, runnable by a local endpoint,
or compatible with a workflow. Search failures raise
``HuggingFaceModelSearchError`` instead of exposing raw Hub SDK exceptions as
the public contract. Install with the ``huggingface`` extra before using this
Hub-backed search path.

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
       model_adapter_coverage="strict",
       max_steps=20,
       trace_sink=my_trace_sink,
   )

   result = run_agent_workflow(
       execution_context=context,
       prompt="Run this workflow with shared collaborators.",
   )

When ``execution_context`` is supplied to high-level APIs, do not also pass
artifact paths or runtime collaborators as separate keyword arguments.

.. header2:: Persistent agent sessions

Use ``AgentSession`` with ``InMemorySessionStore`` when several prompts should
reuse the same workflow context and retained user/assistant transcript:

.. code-block:: python

   from dynamic_agent_runner import (
       AgentSession,
       InMemorySessionStore,
       WorkflowExecutionContext,
       load_agent_package_workflow,
   )

   context = WorkflowExecutionContext(
       workflow=load_agent_package_workflow("path/to/agent-package"),
       tool_registry=my_tool_registry,
       model_adapter=my_model_adapter,
   )
   store = InMemorySessionStore()
   session = AgentSession.create(
       execution_context=context,
       session_store=store,
       session_id="thread-123",
   )

   first = await session.accept("Inspect the repository.")
   second = await session.accept("Now summarize the risky parts.")
   snapshot = session.current_state().to_mapping()

Each ``accept(...)`` call remains a normal bounded workflow run. Input
guardrails, approval interruption, step limits, tracing, retry behavior, and
context preparation still run per prompt. The v1 store is process-local only;
callers own any external persistence and redaction for snapshots. Raw tool
arguments and raw tool outputs are not retained in chat history by default.

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
