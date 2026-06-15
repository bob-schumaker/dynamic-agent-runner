# macOS MLX local-model adapter specification

## Metadata

- Feature slug: `mlx-local-model-adapter`
- Mode: `guided`
- Artifact type: authoritative SDD feature specification
- Status: implemented; public adapter helpers, path/Hub resolution,
  identity validation, executor coverage, docs, and focused validation complete
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Related feature specs:
  - `specs/llama-cpp-local-model/spec.md`
  - `specs/model-adapter-coverage/spec.md`
  - `specs/openai-compatible-provider-wrapper/spec.md`
- Related implementation surfaces:
  - `src/dynamic_agent_runner/executor.py`
  - `src/dynamic_agent_runner/context.py`
  - `src/dynamic_agent_runner/local_models.py`
  - `src/dynamic_agent_runner/mlx_models.py`
  - `src/dynamic_agent_runner/openai_client.py`
  - `src/dynamic_agent_runner/errors.py`
  - `src/dynamic_agent_runner/__init__.py`
  - `tests/test_executor.py`
  - `tests/test_local_models.py`
  - `tests/test_mlx_models.py`
- Local upstream references inspected:
  - `/Users/roschuma/Repos/github/mlx/`
  - `/Users/roschuma/Repos/github/mlx-examples/`

## Objective

Define a macOS-only MLX local-model adapter direction that follows the same
runtime principles as the llama.cpp local-model adapters: local model execution
must remain caller-controlled, fit the existing model-adapter boundary, support
strict local-only client intent through `model_adapter_coverage="strict"`, and
avoid introducing a parallel workflow execution path.

This spec is authoritative for continuing MLX local-model adapter work in the
current session. Implementation should proceed from
`specs/mlx-local-model-adapter/plan.md` and
`specs/mlx-local-model-adapter/tasks.md`.

## Problem Statement

`dynamic-agent-runner` now has explicit model-adapter coverage policy:

- `"augmented"` is the default and may create a default OpenAI adapter for
  eligible missing coverage
- `"strict"` makes the supplied adapter list authoritative
- `local_only` workflow metadata no longer filters adapter selection

The existing llama.cpp local-model feature covers caller-owned
OpenAI-compatible local endpoints and model-asset resolution. MLX is different:
the local source checkouts show MLX as an Apple-silicon-oriented array and model
framework, while the examples provide in-process generation scripts and point
LLM users toward converted checkpoints and the MLX Community on Hugging Face.
The checked-out MLX/MLX examples sources do not establish a built-in
OpenAI-compatible server surface equivalent to llama.cpp server mode.

The repository needs a clear specification for how an MLX-backed local adapter
should fit the current runtime without accidentally treating MLX as hosted
OpenAI, requiring non-macOS environments to import MLX, or making workflow
packages depend on machine-local model paths.

## Users

- Runtime maintainers adding a local MLX model adapter.
- macOS callers who want local Apple-silicon model execution.
- Downstream hosts that already manage MLX model assets and want the runner to
  call them through the normal adapter contract.
- Test authors who need deterministic fake MLX boundaries without importing or
  running MLX on CI.

## Existing Runtime Context

- Workflow execution selects model adapters through adapter metadata and the
  explicit `model_adapter_coverage` policy.
- Clients that require local-only behavior should pass only local adapters with
  `model_adapter_coverage="strict"`.
- The current local-model helper module owns local endpoint configuration,
  model reference resolution, Hugging Face file/snapshot references, and local
  failure taxonomy for endpoint-backed local providers.
- The OpenAI-compatible provider seam remains appropriate when a caller already
  exposes a local model through an OpenAI-compatible endpoint, but the MLX
  feature should not assume such an endpoint exists in MLX itself.

## Upstream MLX Discovery Notes

- `/Users/roschuma/Repos/github/mlx/README.md` describes MLX as an array
  framework for machine learning on Apple silicon, with Python, C++, C, and
  Swift APIs, lazy computation, dynamic graphs, CPU/GPU devices, and unified
  memory.
- The MLX README documents PyPI installation with `pip install mlx` on macOS.
  It also documents Linux CUDA and CPU packages, but this feature is explicitly
  macOS-only for `dynamic-agent-runner`.
- `/Users/roschuma/Repos/github/mlx-examples/README.md` points LLM users to
  `mlx-lm` as the fuller-featured Python package for LLMs with MLX, and to the
  MLX Community organization on Hugging Face for converted checkpoints.
- The local examples include minimal in-process generation flows for LLaMA,
  Mistral, Mixtral, LoRA, speculative decoding, and GGUF-backed generation.
- The local LLaMA example loads converted MLX assets from a model directory
  containing files such as `weights.npz`, `tokenizer.model`, and `config.json`,
  then generates tokens in process through MLX arrays and a tokenizer.
- The local GGUF example uses `huggingface_hub` download helpers and notes that
  MLX can read many GGUF quantization formats, with direct support called out
  for `Q4_0`, `Q4_1`, and `Q8_0`; unsupported quantizations are cast to
  `float16`.
- No checked-out source establishes a repository-ready MLX OpenAI-compatible
  local server contract. If a caller provides such a server, it should use the
  existing `LocalOpenAIEndpointConfig` path instead of this feature's in-process
  adapter path.

## Scope

This feature specification covers:

1. a macOS-only, caller-supplied MLX model adapter surface
2. adapter construction that advertises supported model aliases and reports
   local execution
3. in-process generation through documented or stable MLX/MLX LLM helper
   surfaces, with lazy imports
4. local model asset references for converted MLX directories, MLX Community
   Hugging Face snapshots, and selected GGUF files
5. repository-owned error translation for unsupported platform, missing
   dependencies, model resolution, load failures, generation failures, and model
   identity mismatch
6. deterministic tests that do not require macOS, MLX, Metal, Hugging Face
   network access, or live model assets

## Non-Goals

- No runtime-managed MLX server installation, launch, readiness checks, or
  shutdown.
- No new executor branch or workflow-node type for MLX.
- No ambient model discovery from local filesystems or Hugging Face.
- No automatic model conversion from PyTorch, safetensors, GGUF, or other
  formats unless a later spec explicitly schedules conversion behavior.
- No requirement that CI install or import MLX.
- No Linux or Windows support for this feature, even if upstream MLX has
  non-macOS packages.
- No embeddings, reranking, multimodal, Whisper, image, or audio runtime
  behavior in the first adapter feature.
- No OpenAI-compatible server wrapper unless the caller provides one through the
  existing local OpenAI-compatible endpoint helpers.

## Implementation Readiness Decisions

- The first implementation targets converted MLX model directories and
  injected fake backend tests. GGUF support remains documented but deferred.
- The public helper names for the first implementation are authoritative:
  `MLXLocalModelConfig`, `create_mlx_local_adapter(...)`, and
  `create_mlx_local_async_adapter(...)`.
- The first implementation may use a repository-owned internal backend
  protocol. A default backend may wrap `mlx-lm` after verifying its installed
  API at implementation time; tests must not require `mlx-lm` or `mlx`.
- MLX dependencies should be lazy imports. If dependency metadata changes are
  needed, prefer an optional Poetry dependency group or package extra rather
  than making MLX mandatory for all installs.
- Sync support and async support should ship together. The async adapter may
  dispatch blocking local generation through the executor-friendly thread path
  or an adapter-owned async wrapper; it must not block the event loop directly.
- Capability metadata for the first implementation is conservative: plain text
  generation only. Tool calling, structured output, embeddings, multimodal, and
  streaming public contracts are unsupported unless later specs add them.

## Proposed Public API

The exact names are not authoritative, but the first implementation should
prefer a small local-model helper surface parallel to the existing local
endpoint helpers:

```python
from dynamic_agent_runner import (
    MLXLocalModelConfig,
    create_mlx_local_adapter,
)

adapter = create_mlx_local_adapter(
    MLXLocalModelConfig(
        model_aliases=("mlx-local-chat",),
        model_path="path/to/mlx-model-directory",
        expected_model_id="mlx-community/example-model",
    )
)

result = run_agent_workflow(
    prompt="Run this workflow locally.",
    package_directory="path/to/agent-package",
    model_adapter=[adapter],
    model_adapter_coverage="strict",
)
```

Async callers should use `create_mlx_local_async_adapter(...)` with the same
configuration. The async adapter may wrap blocking generation in a non-blocking
executor path; it must not pretend MLX itself is a native async provider unless
the implementation uses a documented async MLX LLM surface.

## Functional Requirements

### FR-1: Fit the existing model-adapter contract

The MLX adapter must be a normal model adapter selected by the existing
executor.

Acceptance criteria:

- Given a caller supplies an MLX adapter advertising `("mlx-local-chat",)`,
  when an `llm_step` requests `mlx-local-chat`, then the executor may select
  that adapter without a new executor branch.
- Given a caller requires local-only behavior, when they pass only MLX adapters
  and set `model_adapter_coverage="strict"`, then missing coverage fails before
  any default OpenAI adapter is created.
- Given coverage is omitted or set to `"augmented"`, when the MLX adapter does
  not cover a selected eligible OpenAI model, then current augmented fallback
  behavior may still create the default OpenAI adapter.
- Given the adapter is MLX-backed, when it is constructed, then it advertises
  `is_local=True` or equivalent local metadata for diagnostics and future
  policy use.

### FR-2: Be macOS-only and fail clearly elsewhere

The MLX adapter must not make non-macOS environments fail at import time.

Acceptance criteria:

- Given the package is imported on Linux, Windows, or CI without MLX installed,
  then importing `dynamic_agent_runner` still succeeds.
- Given an MLX adapter is constructed on an unsupported platform, then
  construction still succeeds without importing MLX.
- Given an MLX adapter is used for generation on an unsupported platform, then
  the runtime raises a package-owned error that names the macOS-only MLX
  requirement before resolving model assets or loading dependencies.
- Given MLX is missing on macOS, then first generation raises a package-owned
  dependency error rather than an unwrapped `ImportError`.
- Given tests run on non-macOS, then fake MLX loaders/generators can validate
  adapter behavior without importing upstream MLX.

### FR-3: Support caller-controlled model assets

The MLX adapter must accept explicit model references and avoid ambient
filesystem discovery.

Acceptance criteria:

- Given an explicit converted MLX model directory, when the adapter loads the
  model, then it uses that directory as the authoritative local asset.
- Given a Hugging Face snapshot reference for an MLX Community model, when
  network access is allowed and the asset is missing locally, then a future
  implementation may reuse repository-owned Hugging Face snapshot mechanics.
- Given a GGUF model reference is supported, when the requested GGUF
  quantization is not directly supported by MLX, then the runtime reports or
  records the cast-to-`float16` behavior rather than silently treating it as
  native quantized execution.
- Given no explicit local path, cache hit, or configured Hub reference exists,
  then adapter construction or preflight raises a model-resolution error before
  generation.

### FR-4: Preserve model identity

The adapter must preserve a caller-specified authoritative model identity.

Acceptance criteria:

- Given `expected_model_id` is configured, when the loaded model metadata or
  configured asset reference resolves to a different identity, then the runtime
  raises a package-owned model-identity mismatch error.
- Given the adapter advertises model aliases, when the executor requests an
  alias, then trace or error output preserves both the requested alias and the
  authoritative underlying model identity when available.
- Given a model path is used as the only authoritative identity, when errors are
  reported, then the path is included only as local diagnostic context and not
  written into portable workflow artifacts.

### FR-5: Normalize MLX generation into the package response contract

The adapter must translate MLX generation output into the existing
`ModelResponse` shape.

Acceptance criteria:

- Given MLX generation returns text, when the adapter completes, then the
  executor receives a `ModelResponse` with `content`.
- Given streaming or token-by-token generation is used internally, when the
  adapter returns to the executor, then it still returns a final normalized
  response unless a later streaming spec defines a public streaming contract.
- Given tool calls or structured output are requested, when the MLX adapter
  cannot support those capabilities, then adapter selection or request handling
  fails clearly instead of producing malformed OpenAI-compatible structures.
- Given generation parameters such as temperature or max tokens are supported,
  when they are accepted, then the adapter maps only supported runtime request
  fields and ignores or rejects unsupported provider-specific fields explicitly.

### FR-6: Keep OpenAI-compatible MLX wrappers separate

The MLX in-process adapter must not duplicate the existing OpenAI-compatible
local endpoint path.

Acceptance criteria:

- Given a caller already has an OpenAI-compatible local server backed by MLX,
  when they want the runner to use it, then they should use
  `LocalOpenAIEndpointConfig` and `create_local_openai_adapter(...)` or
  `create_local_async_openai_adapter(...)`.
- Given the feature implements an in-process MLX adapter, when it handles a
  request, then it should not route through the OpenAI SDK facade unless a
  caller explicitly chose an OpenAI-compatible endpoint.
- Given future work adds an MLX server helper, then that helper requires a
  separate spec because server lifecycle ownership is currently out of scope.

## Design Notes

- Prefer lazy imports for `mlx`, tokenizer libraries, and optional MLX LLM
  helpers so package import remains portable.
- Prefer dependency injection around model loading and generation so tests can
  use fake MLX loaders.
- Prefer adding a dedicated MLX helper module instead of expanding
  `executor.py`.
- Reuse local-model error types where they match; add MLX-specific subclasses
  only when caller recovery needs a distinct category.
- Treat `mlx-lm` as the likely high-level LLM integration candidate, but verify
  its local API during implementation. The local `mlx-examples` checkout points
  to `mlx-lm` but does not contain it.
- Treat the older `mlx-examples/llms/*` scripts as useful behavior references,
  not as stable library APIs.
- Keep model conversion and benchmark/performance tuning outside the first
  adapter feature.

## Validation Checklist

- [x] Importing `dynamic_agent_runner` succeeds without MLX installed.
- [x] MLX adapter construction remains safe on unsupported platforms.
- [x] MLX generation fails clearly on unsupported platforms before model
      resolution or dependency loading.
- [x] MLX generation fails clearly when MLX dependencies are missing.
- [x] Fake MLX adapter tests prove advertised model aliases are selected by the
      existing executor path.
- [x] Strict coverage with only MLX adapters prevents default OpenAI fallback.
- [x] Augmented coverage continues to allow default OpenAI fallback for eligible
      missing coverage.
- [x] Explicit local model-path resolution succeeds and missing assets fail
      before generation.
- [x] Hugging Face snapshot/file reference behavior is tested without network
      by injected fake download functions.
- [x] Model identity mismatch failures preserve requested alias and
      authoritative identity.
- [x] MLX generation output is normalized to `ModelResponse`.
- [x] Unsupported tool-call or structured-output requests fail clearly.
- [x] Documentation explains macOS-only support, strict local-only usage, and
      the distinction between in-process MLX adapters and OpenAI-compatible
      endpoint adapters.

## Deferred Questions

- Whether GGUF support should become first-class after converted MLX directory
  support lands.
- Whether a future MLX-specific OpenAI-compatible server helper is useful.
- What capability metadata should be advertised for structured output, tool
  calling, embeddings, multimodal models, context length, and local memory
  limits after those capabilities are specified.
