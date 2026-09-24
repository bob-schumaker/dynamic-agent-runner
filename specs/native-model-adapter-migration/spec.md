# Native Model Adapter Migration Specification

## Metadata

- Feature slug: `native-model-adapter-migration`
- Artifact type: cross-provider migration specification
- Status: approved
- Owner: dynamic-agent-runner model-provider boundary
- Related artifacts:
  - [`external-model-adapter-protocol`](../external-model-adapter-protocol/spec.md)
  - [`openai-compatible-external-adapter`](../openai-compatible-external-adapter/spec.md)
  - [`apple-foundation-model-adapter`](../apple-foundation-model-adapter/spec.md)
  - [`mlx-local-model-adapter`](../mlx-local-model-adapter/spec.md)
  - [`llama-cpp-local-model`](../llama-cpp-local-model/spec.md)

## Objective

Move DAR's native text-generation providers behind the exported
`DARExternalAdapterProtocol` without replacing their provider-specific
implementations. The migration covers Apple Foundation Models, direct
llama.cpp, and MLX local generation. Existing provider specifications remain
authoritative for loading, model identity, native templates, resource policy,
and provider behavior.

## Decision and boundary

The generic protocol is the runtime-facing anti-corruption layer. Each provider
keeps a native implementation and receives a small protocol adapter that owns
descriptor construction, health projection, request translation, cancellation
and deadline propagation, response normalization, and redacted errors.

The three wrappers share one DAR-facing text-generation contract but retain
separate provider implementations. Each wrapper is constructed through an
explicit caller-owned BYOM factory with its already-resolved native
configuration. This slice does
not use the v1 zero-argument installed-plugin factory or add receiver-owned
configuration binding.

The public factories are `create_apple_foundation_external_adapter`,
`create_llama_cpp_external_adapter`, `create_mlx_external_adapter`, and
`create_mlx_async_external_adapter`. They accept already-constructed native
adapters, derive identity and capabilities from those bindings, and never
reload materials or take ownership of provider lifecycle.

## In scope

- A protocol adapter for Apple Foundation Models' existing async client path.
- A protocol adapter for direct in-process llama.cpp generation.
- A protocol adapter for MLX text generation, with tool capability advertised
  only when a compatible `MLXToolCodec` is explicitly supplied.
- Stable descriptor identities for each provider/model/material binding.
- Health states that reflect native availability without leaking paths,
  credentials, prompts, or model output.
- Sync/async `create_response(request)` mapping to the existing native
  adapters.
- Fail-closed capability mapping for structured output and tool calling.
- Migration tests proving parity with the existing native `ModelAdapter` path.

## Non-goals

- No change to `dar.external-model.v1`.
- No removal of the existing native provider factories in this slice.
- No automatic model download, endpoint discovery, process management, or
  arbitrary model-directory scanning.
- No embedding, multimodal, streaming, persistent-session, or native callback
  support through this text protocol.
- No provider-specific SDK dependency added solely for the wrapper.
- No live model calls in unit tests.

## Provider requirements

### Apple Foundation Models

The adapter must preserve macOS and SDK availability preflight and
Apple-specific pre-dispatch schema checks. The existing callback-based Apple
tool bridge remains on the native path unless the wrapper can translate a
provider result into DAR `ModelToolCall` values without receiving handlers,
approval objects, or callbacks; until then the wrapper omits `tool_calling`.
It must not expose the Apple SDK client, callback session, or gateway details
through the generic descriptor. If a request requires a capability the Apple
path cannot prove, the adapter refuses before `create_response`.

### Direct llama.cpp

The adapter must bind the exact prepared model identity and configuration
fingerprint already enforced by the native adapter. Memory-fit checks,
material resolution, loading, cleanup, and local execution policy remain native
or host-owned. The protocol wrapper may project only the capabilities actually
supported by the selected chat/template configuration.

### MLX

The adapter must retain caller-controlled model resolution and MLX runtime
availability checks. Plain text generation is the default capability. Tool
calling is enabled only for an explicitly compatible, versioned
`MLXToolCodec`; arbitrary MLX models and tokenizers must remain text-only.

## Common contract

For every provider adapter, the wrapper implements the exact v1 operation:

```python
create_response(
    request: OpenAIModelRequest,
) -> ModelResponse | Awaitable[ModelResponse]
```

The request carries `DARExternalRequestContext` in `request.adapter_context`.
The wrapper never adds a second `dispatch` operation. Provider execution modes
are explicit and must match the descriptor: Apple exposes an `async def`
variant with `execution_modes={"async"}`; llama.cpp exposes a synchronous
variant with `{"sync"}` and may be worker-offloaded by the existing facade for
async workflows; MLX exposes matching sync and async variants. A sync native
call that outlives its deadline may continue occupying the bounded facade
worker until it returns; the wrapper emits no late result, retry, or fallback.

For every provider adapter:

- `describe()` returns one stable provider ID, model alias, canonical model
  identity, execution location, modalities, response formats, capabilities,
  limits, and contract digest.
- `health()` is bounded, redacted, and side-effect free with respect to model
  generation.
- `create_response()` receives only the normalized request and its DAR context;
  it never receives a tool registry, approval object, or handler callback.
- Native errors are translated into package-owned external-adapter errors.
- Cancellation and deadlines are checked before and after native dispatch. An
  async provider task is cancelled where the native API supports it; a
  blocking sync provider is bounded by the facade worker and its late result is
  discarded.
- The receiver facade remains the sole owner of admission, tool re-entry,
  generic JSON-schema validation, tracing, and removal. Provider-native schema
  checks may occur before dispatch; wrappers only normalize returned tool calls
  and never execute them.
- The old native adapter remains available until parity evidence and an explicit
  removal decision exist.

## Identity and health rules

Each BYOM factory must produce a deterministic descriptor from non-secret
inputs. The descriptor uses the existing v1 fields: `adapter_id`,
`model_alias`, `canonical_model_id`, execution location, capabilities, limits,
and contract digest. Native binding identity is encoded into existing identity
fields before the v1 canonical descriptor digest is computed; the protocol
digest algorithm is not changed:

- Apple: `canonical_model_id` includes a digest of system-model identity, SDK
  major/minor compatibility, and capability profile; no user or device
  identifiers.
- llama.cpp: `canonical_model_id` includes the prepared material-lock digest
  and configuration fingerprint.
- MLX: `canonical_model_id` includes resolved model/material identity and
  configuration; a tool-enabled adapter also includes codec ID and version.

Changing any bound input creates a different canonical model identity and thus
a different descriptor digest. The BYOM factory captures the resolved binding
at construction and the facade freezes that descriptor for its lifetime;
re-resolution creates a new wrapper rather than mutating an admitted one. For
installed adapters, the existing registry `resolve()` operation compares the
caller-supplied (`adapter_id`, `canonical_model_id`, `contract_digest`, and
model alias) tuple. Direct BYOM callers have construction-time immutability,
not registry-style re-resolution guarantees.

Health uses a non-secret factory `health_timeout_seconds` in `(0, 120]`; it is
the sole health-probe timeout and is enforced by the facade before provider
dispatch. Blocking probes run on the existing bounded facade worker; a full
worker pool fails closed as unavailable, and a late probe is reported as
unavailable while it may continue occupying that worker until return. The
existing async facade uses the same bounded health worker before generation.
Health is non-generative: Apple checks OS/SDK/model availability; llama.cpp
checks prepared material, ABI, and memory-fit state; MLX checks resolved
material, runtime availability, and codec admission. A missing or not-ready
prerequisite reports `unavailable`; an unexpected probe failure reports
`failed`; raw native errors and paths are redacted.

## Capability matrix

| Variant | Execution modes | `structured_output` | `tool_calling` |
| --- | --- | --- | --- |
| Apple async | async | only after Apple pre-dispatch schema checks pass | omitted unless normalized `ModelToolCall` output is proven without callbacks |
| llama.cpp sync/worker-offloaded | sync | only for a chat/template configuration with normalized JSON proof | only for a configuration with normalized tool-call proof |
| MLX sync | sync | text-only unless the native adapter proves JSON normalization | only with the exact versioned `MLXToolCodec` |
| MLX async | async | same rule as MLX sync | same rule as MLX sync |

Each advertised capability has positive and negative fake-backed tests;
intentionally omitted or conditional capabilities have denial tests. Omission
of a capability is the default. The table describes factory-time immutable
descriptor capabilities; request-time schema/tool checks may refuse a request
but never change the descriptor.

## Acceptance criteria

- Given an eligible provider configuration, constructing its BYOM wrapper
  produces a descriptor whose identity and capabilities match the native
  binding.
- Given unavailable SDK/runtime/materials, health reports unavailable or failed
  without exposing raw native errors or paths.
- Given a supported text request, wrapper and native paths produce equivalent
  normalized responses under controlled fakes. Parity compares canonical
  content, ordered normalized tool calls, response-format behavior, and
  package-owned error class/code; it excludes raw provider payloads, unstable
  response IDs, timestamps, and provider metadata.
- Given unsupported tools or structured output, the wrapper refuses before
  native dispatch.
- Given cancellation or an expired deadline, no second request or fallback is
  attempted.
- Given a changed model/material/configuration identity, a new wrapper has a
  different canonical identity and descriptor digest; installed-adapter
  resolution rejects a stale identity tuple, while direct BYOM wrappers remain
  immutable snapshots.
- Existing provider-specific tests remain green and no live provider is
  required for ordinary validation.

## Migration and removal gates

Migration proceeds provider by provider: wrapper RED tests, native parity,
support-matrix coverage, documentation, then opt-in BYOM selection. Native
factories are removable only after named parity/provenance evidence and an
explicit compatibility decision; no registry or default-path migration is
implied. A provider may remain native if its behavior cannot be represented
without weakening the generic contract.
