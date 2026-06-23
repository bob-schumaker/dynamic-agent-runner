---
name: dynamic-agent-runner
description: Use when consuming dynamic-agent-runner as a client library or CLI to load, validate, and run generated dynamic-agent workflow packages, provide callable tool registries, choose OpenAI or OpenAI-compatible model adapters, inspect execution state, and avoid unsupported runtime assumptions.
---

# dynamic-agent-runner Client Usage

Use this skill when an agent needs to call `dynamic-agent-runner` correctly from
another application, script, test, or automation flow. This is client guidance,
not package-maintenance guidance.

## Client Mental Model

- A workflow package is source data: `agent-runtime.yaml`, `agent-design.md`,
  and `agent-graph.mmd`.
- `package_directory` is the normal public input. File-by-file artifact loading
  is a compatibility path, not the default integration style.
- Manifest tool declarations are metadata. Tool execution requires a callable
  registry supplied by the client.
- Model execution goes through a model adapter. The default path uses the
  official OpenAI SDK; clients can inject fake, remote, or local-compatible
  adapters.
- High-risk surfaces may be validated or preserved as metadata without being
  live runtime engines.

## Choose the Entry Point

Use `load_agent_workflow(...)` when you only need to parse and validate a
package:

```python
from dynamic_agent_runner import load_agent_workflow

workflow = load_agent_workflow(
    package_directory="path/to/agent-package",
    runtime_overrides="path/to/runtime-overrides.yaml",
    tool_registry=registry,
)
```

Use `run_agent_workflow(...)` for a simple synchronous final result:

```python
from dynamic_agent_runner import run_agent_workflow

result = run_agent_workflow(
    prompt="Run this workflow.",
    package_directory="path/to/agent-package",
    tool_registry=registry,
    model_adapter=model_adapter,
    max_steps=20,
)
```

Use `run_agent_workflow_async(...)` inside async applications. Do not call the
sync API from an already-running event loop.

Use `execute_workflow(...)` or `execute_workflow_async(...)` when the client
needs a `WorkflowResult` with execution state, trace events, retry records,
token usage, node inputs, node outputs, tool results, and errors.

Use `WorkflowExecutionContext` or `RunContext` when several runs should share a
loaded workflow, registry, adapter set, hooks, max-step policy, or trace sink.
When passing an execution context, do not also pass artifact paths or runtime
collaborators as separate keyword arguments.

Use `AgentSession` with `InMemorySessionStore` when several bounded prompts
should reuse a retained user/assistant transcript. `accept(...)` returns
`AgentSessionResult`, including the bounded `WorkflowResult` or
`WorkflowInterruptedResult` plus current session state.

Use `accept_stream(...)` when the host needs live progress events for one
bounded prompt. Progress events are redacted. Terminal `run_completed` and
`approval_interrupted` events carry `session_result` by default, and
`event.workflow_result` is available when the host needs full execution state
such as `workflow_result.state.tool_results`. Control stream volume with
`include_progress_events`, `include_terminal_event`,
`include_terminal_session_result`, and `progress_event_types`.

## CLI Usage

For shell integration, use the console script:

```bash
dynamic-agent-runner \
  --package path/to/agent-package \
  --prompt "Run the workflow for this user request."
```

Prompt input may come from `--prompt`, `--prompt-file`, or stdin. Use
`--max-steps` to cap node execution. Use repeated `--workspace-root` values only
to enable the opt-in read-only `local_workspace` registry pack.

The CLI prints the final result to stdout. Loading, validation, registry, model,
and execution failures are printed to stderr with a non-zero exit code.

## Supplying Tools

If a workflow has `tool_use_step` nodes, provide callable tools by registry.
Manifest or `tool-index.yaml` entries alone are not executable.

```python
from dynamic_agent_runner import InMemoryToolRegistry, RegisteredTool
from dynamic_agent_runner.models import ToolDefinition

registry = InMemoryToolRegistry(
    [
        RegisteredTool(
            ToolDefinition.from_mapping(
                {
                    "id": "search_repo",
                    "description_for_llm": "Search repository text.",
                    "input_schema": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                    "side_effect": "read",
                    "approval_required": False,
                }
            ),
            lambda arguments: {"message": arguments["query"]},
        )
    ]
)
```

Tool handlers receive resolved argument mappings. They may return raw values or
`ToolResult`. Async execution awaits async handlers directly and dispatches sync
handlers without blocking the event loop.

Use the CLI `--workspace-root` option only for the built-in read-only local
workspace pack. Do not assume write tools, shell tools, or ambient tool
discovery are available.

## Supplying Models

Default hosted OpenAI clients can omit `model_adapter`. With normal OpenAI SDK
configuration and credentials, the runner creates the package-owned default
OpenAI adapter for eligible OpenAI models.

For tests, examples, and deterministic automation, inject fake model adapters
instead of making live model calls.

Choose adapter coverage explicitly when the client's adapter boundary matters:

- Use `model_adapter_coverage="augmented"` or omit the argument when supplied
  adapters should be tried first and the default OpenAI adapter may fill
  eligible missing coverage.
- Use `model_adapter_coverage="strict"` when the supplied adapter list is
  authoritative. `model_adapter=None`, `model_adapter=[]`, or nonmatching
  adapters fail before a default OpenAI adapter is created.
- For local-only client intent, pass only local adapters and set strict
  coverage. Do not rely on workflow `local_only` metadata to filter adapters.

If the caller already has a local llama.cpp server exposing an OpenAI-compatible
API, use the OpenAI-compatible adapter helpers against that already-running
server:

```python
from dynamic_agent_runner import (
    LocalOpenAIEndpointConfig,
    create_local_async_openai_adapter,
)

adapter = create_local_async_openai_adapter(
    LocalOpenAIEndpointConfig(
        base_url="http://localhost:8080/v1",
        model_aliases=("local-chat",),
        provider_name="llama-cpp-local",
        expected_model_id="local-chat",
    )
)
```

Pass that adapter with `model_adapter_coverage="strict"` when the workflow must
stay within that local server boundary. Use augmented coverage only when it is
acceptable for missing eligible coverage to fall back to the default OpenAI
adapter.

Local endpoint helpers wrap an already-running compatible server, including
llama.cpp servers exposing an OpenAI-compatible API. They do not start, stop, or
supervise model-server processes.

For direct in-process llama.cpp local models, use the llama.cpp adapter helpers:

```python
from dynamic_agent_runner import (
    LlamaCppLocalModelConfig,
    create_llama_cpp_local_adapter,
)

adapter = create_llama_cpp_local_adapter(
    LlamaCppLocalModelConfig(
        model_aliases=("llama-local-chat",),
        model_path="path/to/model.gguf",
        expected_model_id="Qwen/Qwen3-4B-Instruct-2507",
    )
)
```

Pass direct llama.cpp adapters as a list with
`model_adapter_coverage="strict"` when the run must stay local. The helpers
lazily use `llama-cpp-python`; install `dynamic-agent-runner[llamacpp]` before
using the default in-process backend. They resolve local model assets before
generation, normalize generated text into the runner response contract, and do
not require a local server.

For macOS in-process MLX local models, use the MLX adapter helpers:

```python
from dynamic_agent_runner import MLXLocalModelConfig, create_mlx_local_adapter

adapter = create_mlx_local_adapter(
    MLXLocalModelConfig(
        model_aliases=("mlx-local-chat",),
        model_path="path/to/mlx-model-directory",
        expected_model_id="mlx-community/example-model",
        generation_kwargs={"max_tokens": 512, "temperature": 0.2},
    )
)
```

Pass MLX adapters as a list with `model_adapter_coverage="strict"` when the run
must stay local. MLX helpers are macOS-only, but importing the package and
constructing adapters remain safe on other platforms; generation on non-macOS
fails before model resolution or dependency loading. They validate converted
model directories, explicit `.gguf` files with `model_format="gguf"`, and
Hugging Face-resolved assets before generation. They normalize plain generated
text into the runner response contract. The default in-process backend lazily
uses `mlx-lm` when installed; tests and hosts can inject a fake or custom
backend. The helpers do not start a server, and they are distinct from the
OpenAI-compatible endpoint helpers. Tool calling, structured output,
embeddings, multimodal IO, streaming, conversion, and server lifecycle remain
separate feature surfaces.

Use `check_local_model_availability(...)` to preflight one known local model
reference before adapter construction or runtime model resolution:

```python
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
```

Availability checks are read-only. They inspect explicit local paths, explicit
cache roots, and the default local-model cache root without downloads, adapter
construction, model loading, or generation. Optional injected remote metadata can
return `would_download` without downloading. Use `search_hugging_face_models(...)`
for remote catalog discovery; this preflight API does not provide broad local
inventory or native Hugging Face cache enumeration.

`search_hugging_face_models(...)` is read-only discovery. A matching result does
not mean the model is downloaded, runnable, or compatible with the workflow.
Install the package with the `huggingface` extra before using Hub-backed model
discovery or Hub-backed local asset downloads.

Built-in tool packs are opt-in and require injected collaborators:

- `create_web_registry(...)` exposes `web_search` and `web_fetch` through
  caller-provided search/fetch clients.
- `create_workspace_data_registry(...)` exposes JSON-compatible
  `workspace_data_*` tools through a caller-provided store.
- `create_subagent_registry(...)` exposes `run_subagent` and `run_subagents`
  through a caller-provided bounded child runner and presets.
- `create_host_tool_registry(...)` adapts host-owned tool bindings with
  provider-safe model-facing ids; `summarize_trace_events(...)`,
  `summarize_capability_report(...)`, and `ResolvedModelSelection` support
  bounded host handoff payloads.

## Runtime Metadata the Client Should Not Overinterpret

The runtime preserves and validates metadata such as:

- `runtime.execution_policy.model_map`
- `runtime.execution_policy.model_capabilities`
- `runtime.execution_policy.async_session`
- `runtime.execution_policy.approval_interruption`
- `runtime.execution_policy.sandbox_runtime`
- `llm_step.model_requirements`
- `metadata.patterns_present`
- `metadata.rag_pipeline`

Do not pass these fields directly as OpenAI API parameters. Do not infer live
durable session storage, approval pause/resume, sandbox execution, MCP
discovery, or guardrail enforcement from metadata alone.

## Observability and Failure Handling

Use trace sinks when the host needs live observation:

```python
result = run_agent_workflow(
    prompt="Run this workflow.",
    package_directory="path/to/agent-package",
    model_adapter=model_adapter,
    tool_registry=registry,
    trace_sink=trace_sink,
    run_id="host-run-123",
)
```

Trace payloads can include sensitive prompt, response, tool argument, tool
output, node output, and final-result fields. Redact before external emission
with `TraceEvent.redacted()` or `TraceEvent.redacted_payload()`.

Catch package-owned errors at integration boundaries:

- `ArtifactLoadError`
- `WorkflowValidationError`
- `ToolRegistryError`
- `ModelExecutionError`
- `WorkflowExecutionError`
- `HuggingFaceModelSearchError`

Let unexpected exceptions fail visibly unless the host has a specific recovery
policy.

## Client-Side Validation

Before running a real workflow:

- confirm the package directory contains `agent-runtime.yaml`,
  `agent-design.md`, and `agent-graph.mmd`
- call `load_agent_workflow(...)` with the intended registry to validate
  package and tool references
- provide `max_steps` for untrusted or experimental workflows
- use fake adapters/tools in unit tests
- use trace output or `WorkflowResult.state` for debugging instead of scraping
  stdout

Useful repository-local docs:

- `docs/files/quickstart.rst`
- `docs/files/python-api.rst`
- `docs/files/cli.rst`
- `docs/files/tool-registry.rst`
- `docs/files/runtime-policies.rst`
- `docs/files/tracing-and-observability.rst`

## Boundaries

The client should not expect these capabilities unless a later package version
documents them as implemented:

- automatic prompt truncation
- model-assisted repair of malformed outputs
- durable external transcript/session storage
- live approval interruption/resume
- writable workspace or sandbox command execution
- live MCP lifecycle management and tool discovery
- arbitrary external `SKILL.md` loading
- Power-Marimo host automation
