# macOS MLX Local-Model Adapter Implementation Plan

Status: ready for implementation

## Goal

Implement the authoritative behavior in
`specs/mlx-local-model-adapter/spec.md`: add a macOS-only, in-process MLX local
model adapter surface that uses the existing model-adapter contract, supports
strict local-only execution through `model_adapter_coverage="strict"`, keeps MLX
dependencies optional and lazily imported, and avoids runtime-owned server
lifecycle behavior.

## Spec Trace

- Spec: `specs/mlx-local-model-adapter/spec.md`
- Primary runtime spec: `specs/dynamic-agent-runner/spec.md`
- Related adapter-coverage spec: `specs/model-adapter-coverage/spec.md`
- Related local-model spec: `specs/llama-cpp-local-model/spec.md`
- Related provider spec: `specs/openai-compatible-provider-wrapper/spec.md`

## Existing Implementation Context

- `executor.py` already selects caller-supplied adapters by advertised model
  aliases and `model_adapter_coverage`.
- `local_models.py` already contains local model reference types, local endpoint
  helpers, Hugging Face file/snapshot references, model identity validation, and
  package-owned local-model errors.
- `openai_client.py` owns `ModelResponse`, `ModelToolCall`, and OpenAI-compatible
  request/response normalization. The MLX adapter should return the same
  `ModelResponse` shape without routing through the OpenAI SDK.
- `errors.py` already has `LocalModelError`, `LocalModelResolutionError`,
  `LocalModelIdentityMismatchError`, and endpoint-specific local errors.
- `tests/test_local_models.py` covers local model path resolution and local
  endpoint failure behavior without live infrastructure.
- `tests/test_executor.py` covers strict and augmented model-adapter coverage.
- `pyproject.toml` currently has mandatory llama.cpp and Hugging Face
  dependencies; MLX should not become a mandatory dependency unless explicitly
  approved.

## Planning Decisions

- Public helper/config names:
  - `MLXLocalModelConfig`
  - `create_mlx_local_adapter(...)`
  - `create_mlx_local_async_adapter(...)`
- Add a dedicated `src/dynamic_agent_runner/mlx_models.py` module.
- Keep executor changes minimal. The MLX adapter must satisfy the existing
  adapter protocol rather than adding executor-specific MLX routing.
- Use a small internal backend protocol for model loading and generation so
  tests can inject fake loaders/generators.
- Implement converted MLX model directory support first. Defer GGUF as a
  follow-up unless a later user request explicitly moves it into scope.
- Preserve Hugging Face references through existing local-model reference types
  where possible, but test network behavior only with injected fake download
  callables.
- Fail closed for unsupported platform, missing dependency, unsupported request
  features, missing model assets, and identity mismatches.
- Conservative capability support: text generation only. Reject tool calls and
  structured output clearly.
- The default adapter should report local execution with `is_local=True` and
  advertise caller-provided model aliases.
- Async support should be implemented with an async adapter that does not block
  the event loop directly.

## Implementation Shape

### New MLX helper module

`mlx_models.py` should own:

- `MLXLocalModelConfig`
- sync and async adapter factories
- lazy platform/dependency checks
- backend protocol/type aliases for loading and generation
- model path/reference preflight
- identity validation integration
- request feature validation
- conversion from backend generation output to `ModelResponse`

The first implementation can keep the backend small:

1. fail clearly before model resolution when generation is attempted on a
   non-macOS platform
2. resolve or validate the configured local model path on supported platforms
3. lazy-load a backend model/generator on first request
4. convert the runtime's `OpenAIModelRequest`-style input or adapter request
   fields into the backend prompt text and generation parameters
5. return `ModelResponse(content=...)`

### Public exports

Export `MLXLocalModelConfig`, `create_mlx_local_adapter`, and
`create_mlx_local_async_adapter` from `dynamic_agent_runner.__init__`.

### Dependency policy

Do not import MLX at package import time. Add dependency metadata only if the
implementation needs it for supported installation. Prefer an optional
dependency group or extra and document the install path. If dependency metadata
is deferred, the lazy import error must clearly tell callers what package is
missing.

### Executor integration

No executor branch should be needed. Executor coverage tests should prove:

- strict mode with only MLX adapters prevents default OpenAI fallback
- augmented mode remains allowed to use default OpenAI fallback when MLX
  adapters do not cover the selected eligible OpenAI model

## Error Contract

Use package-owned errors:

- `LocalModelResolutionError` for missing model assets
- `LocalModelIdentityMismatchError` for identity mismatch
- `ModelExecutionError` or a local-model subclass for missing dependency,
  unsupported platform, unsupported request features, load failure, and
  generation failure
- `WorkflowExecutionError` only for executor-level adapter coverage failures

Messages should name:

- MLX or macOS when platform/dependency checks fail
- the requested model alias
- the expected model identity when configured
- the model path or Hub reference when relevant
- the unsupported request feature when rejecting tool calls or structured output

## Validation Plan

Focused validation:

```bash
poetry run pytest tests/test_mlx_models.py tests/test_executor.py -q
```

Import and local-model regression validation:

```bash
poetry run pytest tests/test_import.py tests/test_local_models.py \
  tests/test_mlx_models.py -q
```

Public API and adapter-coverage validation:

```bash
poetry run pytest tests/test_cli.py tests/test_executor.py \
  tests/test_model_capabilities.py tests/test_import.py -q
```

Final validation before commit:

```bash
pre-commit run --files <changed files>
```

## Non-Implementation Notes

- Do not run live MLX generation in unit tests.
- Do not require macOS-specific CI.
- Do not start or supervise model servers.
- Do not add workflow-manifest schema fields for MLX.
- Do not add provider discovery or ambient filesystem discovery.
- Do not implement embeddings, multimodal models, tool calling, structured
  output, streaming public APIs, or model conversion in the first pass.
