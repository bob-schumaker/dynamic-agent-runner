
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

Hosts that generate manifests in memory can use
``inspect_agent_workflow_capabilities(...)`` instead of creating a temporary
package directory:

.. code-block:: python

   from dynamic_agent_runner import inspect_agent_workflow_capabilities

   report = inspect_agent_workflow_capabilities(
       runtime_manifest=generated_runtime_manifest,
       tool_registry=my_tool_registry,
       model_adapter=my_model_adapter,
   )

The same helper also accepts an already loaded ``LoadedAgentWorkflow`` through
the ``workflow`` argument.

The report marks implemented runtime surfaces as ``live``, preserved metadata as
``metadata_only``, missing collaborators as ``missing_collaborator``, and invalid
packages or inline workflows as ``invalid``. It is a readiness report, not an
execution trace. Tool capability details include host canonical ids,
model-facing ids, and aliases when the supplied registry was built from
``HostToolBinding``.

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
LiteLLM-backed OpenAI adapter. ChatGPT/Codex auth remains on the
repository-owned SDK backend until its separate Responses-aware LiteLLM slice
is implemented.

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

.. header2:: LiteLLM adapter

Use ``create_litellm_adapter(...)`` or
``create_async_litellm_adapter(...)`` for direct LiteLLM Chat Completions
transport. DAR owns request translation and response normalization; callers may
inject a completion callable or LiteLLM router for tests and host-managed
routing. The factory's ``model`` value is adapter metadata and does not
override an individual request model.

LiteLLM is installed as a DAR dependency.

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
           generation_kwargs={"max_tokens": 512, "temperature": 0.2},
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
``mlx-lm``. MLX helpers validate converted model directories, explicit ``.gguf``
files with ``model_format="gguf"``, and Hugging Face-resolved assets before
generation. They normalize generated text into the package ``ModelResponse``
contract. The default in-process backend remains text-only: it reports
``tool_calling=False`` and rejects tool-bearing requests before model resolution
or generation. An advanced caller can opt into tool calling only by injecting
both an ``MLXToolCodec`` and a version-compatible ``MLXToolCapableBackend``.
That does not claim tool support for arbitrary MLX models, tokenizers, or stock
``mlx-lm``; DAR still owns tool exposure and schema validation, approval,
coordinator dispatch, tracing, and tool-result continuation. Install the
``mlx`` extra before using the default in-process backend. Use strict coverage
for local-only execution. If a caller already exposes an MLX model through an
OpenAI-compatible local server, use ``LocalOpenAIEndpointConfig`` instead.
Structured output, embeddings, multimodal IO, streaming public APIs,
conversion, and server lifecycle helpers remain unsupported feature surfaces.

For the pinned ``mlx-community/Qwen3-4B-Instruct-2507-nvfp4`` artifact,
``create_qwen3_mlx_local_adapter(...)`` packages a strict native-envelope codec
with a compatible backend. The caller loads the exact local model and passes its
``(model, tokenizer)`` pair; ``expected_model_id`` must be
``PINNED_QWEN3_MLX_MODEL_ID``:

.. code-block:: python

   from mlx_lm import load

   from dynamic_agent_runner import (
       PINNED_QWEN3_MLX_MODEL_ID,
       MLXLocalModelConfig,
       create_qwen3_mlx_local_adapter,
   )

   model, tokenizer = load("path/to/Qwen3-4B-Instruct-2507-nvfp4")
   adapter = create_qwen3_mlx_local_adapter(
       MLXLocalModelConfig(
           model_aliases=("qwen3-local",),
           model_path="path/to/Qwen3-4B-Instruct-2507-nvfp4",
           expected_model_id=PINNED_QWEN3_MLX_MODEL_ID,
       ),
       model=model,
       tokenizer=tokenizer,
   )

It accepts only an omitted ``tool_choice`` and exactly one pure native
``<tool_call>…</tool_call>`` envelope. Mixed prose, malformed envelopes,
duplicate JSON keys, and non-object arguments fail before tool dispatch. This
is explicit opt-in, not Qwen-family detection; the generic MLX helpers remain
text-only unless a caller supplies their own compatible codec/backend pair.

.. header2:: Apple Foundation Models

Use ``AppleFoundationModelConfig`` with
``create_apple_foundation_model_async_adapter(...)`` to run a workflow on
Apple's system-managed on-device language model. The optional
``apple-foundation-models`` extra, macOS on eligible Apple silicon, Apple
Intelligence, and an available ``SystemLanguageModel`` are required for
generation:

.. code-block:: python

   from dynamic_agent_runner import (
       AppleFoundationModelConfig,
       create_apple_foundation_model_async_adapter,
       run_agent_workflow_async,
   )

   apple_adapter = create_apple_foundation_model_async_adapter(
       AppleFoundationModelConfig()
   )

   result = await run_agent_workflow_async(
       prompt="Run this workflow on Apple's system model.",
       package_directory="path/to/agent-package",
       tool_registry=my_tool_registry,
       model_adapter=[apple_adapter],
       model_adapter_coverage="strict",
   )

The default model alias is ``apple-system-language-model``. The adapter is
local and supports final text, structured JSON output, and tool calling; it
does not support streaming, multimodal input, embeddings, persistent sessions,
Private Cloud Compute, or external HTTP clients.

For tool calling, DAR creates one opaque Apple wrapper per tool exposed to the
active node. A callback becomes a DAR invocation request and enters the shared
tool coordinator rather than a handler or registry directly. Consequently,
DAR still owns exposure checks, normalized-argument validation, guardrails,
approval decisions, hooks, traces, result state, and the model-facing tool
result. The callback budget is derived from the active DAR tool-call limit.

An exact approved decision invokes the prepared tool once. Denied, cancelled,
or expired decisions do not run the handler, hooks, registry invocation, or
state writes. An unresolved decision becomes a DAR workflow interruption before
the handler runs; the Apple adapter does not implement durable approval resume.
Callbacks after cancellation or response completion fail closed.

Apple tool argument schemas are deliberately a strict subset of JSON Schema.
The root must be a finite object whose properties are all required with
``additionalProperties: false``; property names must be Python identifiers and
not Python keywords. Nested objects and arrays are allowed, as are ``string``,
``integer``, ``number``, and ``boolean`` values, string enums, numeric
``minimum``/``maximum``, and array ``minItems``/``maxItems``. DAR rejects a
schema before creating the Apple session when it contains caller-supplied
``$ref``, composition, map objects, optional properties, null types,
non-string enums, ``const``, patterns/formats, string-length constraints, or
unknown keywords. SDK-generated references for nested classes do not make
caller-supplied references admissible.

The standalone A1 release gate uses direct runtime calls rather than
pytest-native model generation. Run it on an eligible Mac outside the Codex
execution sandbox:

.. code-block:: bash

   poetry run python scripts/run_apple_live_release_gate.py

It emits a redacted receipt after text, structured-output, and strict-workflow
execution. The marked Apple pytest suite remains an opt-in diagnostic and A2
callback smoke:

.. code-block:: bash

   poetry run pytest -m apple_live -q

They skip when macOS, the optional SDK, or model availability is missing. A
historical native ``GenerationError`` with status 255 occurred inside the Codex
execution sandbox despite successful availability; the restored environment
has not reproduced it. In this Codex/macOS environment, run the native callback
sentinel from an elevated host terminal outside that sandbox. This is a local
harness constraint, not an Apple Foundation Models requirement on all hosts.
Pytest-native Apple results are diagnostic evidence, not the A1 release gate.
The current SDK also emits a known deprecation warning and ignored teardown
``TypeError`` after otherwise successful native tests.

.. header2:: Local model availability preflight

Use ``check_local_model_availability(...)`` to inspect one known local model
reference before constructing an adapter or triggering runtime model resolution:

.. code-block:: python

   from dynamic_agent_runner import (
       LocalModelAssetReference,
       LocalModelAvailabilityStatus,
       check_local_model_availability,
   )

   availability = check_local_model_availability(
       LocalModelAssetReference(
           provider="hugging_face",
           repo_id="Qwen/Qwen3-4B-GGUF",
           filename="chat-model.gguf",
           model_format="gguf",
           backend="llama_cpp",
       )
   )

   if availability.status is LocalModelAvailabilityStatus.AVAILABLE:
       model_path = availability.resolved_path

Availability checks are read-only. They check explicit local paths, explicit
cache roots, and the default local-model cache root without downloading,
constructing adapters, loading model weights, or executing generation. Results
include structured status, source, path, cache root, optional size metadata, a
message, and warnings.

When ``allow_network_metadata=True`` is supplied with an injected metadata
lookup, availability can report ``would_download`` for a valid remote asset
without downloading it. Use ``search_hugging_face_models(...)`` for remote
catalog discovery.

Use ``list_local_model_assets(...)`` when a host needs a narrow snapshot of the
local model assets already visible to DAR-owned cache roots:

.. code-block:: python

   from dynamic_agent_runner import list_local_model_assets

   inventory = list_local_model_assets(
       model_cache_roots=("path/to/project-model-cache",),
       include_default_cache_root=True,
   )

   for asset in inventory.assets:
       print(asset.path, asset.model_format, asset.source)

Cached inventory is also read-only. It scans only the default local-model cache
root and the current caller-provided roots passed to that call. It recognizes
direct ``.gguf`` files and converted MLX directories, returns bounded warnings
for missing or invalid roots, and does not persist roots, scan arbitrary sibling
directories, inspect native Hugging Face cache internals, download models,
construct adapters, load weights, or execute generation.

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

   from dynamic_agent_runner import (
       ContextSelection,
       WorkflowExecutionContext,
       load_agent_workflow,
   )
   from dynamic_agent_runner import run_agent_workflow

   workflow = load_agent_workflow(package_directory="path/to/agent-package")

   def select_context(query, candidates, metadata):
       return (
           ContextSelection(
               turn_id=candidates[0].turn_id,
               score=0.8,
               reason="caller_semantic_score",
           ),
       )

   context = WorkflowExecutionContext(
       workflow=workflow,
       tool_registry=my_tool_registry,
       model_adapter=my_model_adapter,
       model_adapter_coverage="strict",
       max_steps=20,
       trace_sink=my_trace_sink,
       context_selector=select_context,
   )

   result = run_agent_workflow(
       execution_context=context,
       prompt="Run this workflow with shared collaborators.",
   )

When ``execution_context`` is supplied to high-level APIs, do not also pass
artifact paths or runtime collaborators as separate keyword arguments.
Use direct execution for a single stateless run, ``WorkflowExecutionContext``
for stable collaborators across bounded runs, and ``AgentSession`` when retained
prompt history or restartable in-memory session state is required.
``context_selector`` is optional and only used by workflows that configure
``context_compression.selection.strategy: injected_semantic``. The runner passes
bounded older-turn candidates to the selector; it does not provide embeddings,
vector stores, memory stores, or retrievers.

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

   restored = AgentSession.from_snapshot(
       snapshot,
       execution_context=context,
       session_store=InMemorySessionStore(),
   )

Each ``accept(...)`` call remains a normal bounded workflow run. Input
guardrails, approval interruption, step limits, tracing, retry behavior, and
context preparation still run per prompt. The v1 store is process-local only;
callers own any external persistence and redaction before restart. Raw tool
arguments and raw tool outputs are not retained in chat history by default.

Callers that need progress events while a prompt runs can stream one bounded
session prompt:

.. code-block:: python

   async for event in session.accept_stream("Continue the analysis."):
       if event.event_type == "model_input_prepared":
           handle_context_status(event.payload)
       elif event.event_type == "run_completed":
           final_result = event.final_result
           workflow_result = event.workflow_result

Hosts can limit the stream surface with
``include_progress_events=False``, ``include_terminal_event=False``,
``include_terminal_session_result=False``, or
``progress_event_types=("model_input_prepared",)``.

``accept_stream(...)`` yields ``AgentSessionStreamEvent`` values with sequence,
event type, session ID, run ID, node ID, redacted payload, and terminal final
result fields. The terminal ``run_completed`` event also carries
``session_result``, matching ``AgentSession.accept(...)``, and
``event.workflow_result`` for callers that need full execution state such as
tool results. Intermediate stream events stay redacted. Session state is saved
only after successful completion. Provider-native token deltas, lower-level
executor stream APIs, and specialized model-tool loop progress events remain
future work.

.. header2:: Collaborative child sessions

Use ``CollaborativeAgentSessionManager`` when a host wants to keep explicit
parent/child session state while still owning child construction and execution:

.. code-block:: python

   from dynamic_agent_runner import (
       CollaborativeAgentPreset,
       CollaborativeAgentSessionManager,
   )

   manager = CollaborativeAgentSessionManager(
       parent_session_id="parent-1",
       presets={
           "reviewer": CollaborativeAgentPreset(
               id="reviewer",
               role="Review specialist",
               tool_ids=("workspace_data_read",),
           )
       },
       session_factory=create_child_session,
   )

   child = manager.spawn_agent(preset_id="reviewer", name="reviewer-1")
   result = await manager.send_input(child.agent_id, "Review this plan.")
   snapshot = manager.current_state().to_mapping()

The manager records child identity, role, status, last result, and child
session snapshots in memory. It does not schedule background work, create model
adapters, choose tools, persist external checkpoints, or provide an autonomous
multi-agent planner. Unknown presets and closed children return explicit child
states instead of silently creating work.

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
