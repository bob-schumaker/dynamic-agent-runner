# OpenAI-Compatible External Adapter Specification

## Metadata

- Feature slug: `openai-compatible-external-adapter`
- Mode: `guided`
- Artifact type: proposed SDD feature specification
- Status: approved; Council and Ponytail findings addressed
- Owner: dynamic-agent-runner model-provider boundary
- Related artifacts:
  - [`external-model-adapter-protocol`](../external-model-adapter-protocol/spec.md)
  - [`openai-compatible-provider-wrapper`](../openai-compatible-provider-wrapper/spec.md)
  - [`llama-cpp-local-model`](../llama-cpp-local-model/spec.md)
  - `src/dynamic_agent_runner/external_adapter.py`
  - `src/dynamic_agent_runner/openai_client.py`
  - `src/dynamic_agent_runner/local_models.py`

## Objective

Add one thin, provider-neutral `DARExternalAdapterProtocol` implementation for
one caller-owned OpenAI-compatible model service. Ollama, vLLM, LM Studio, and
the llama.cpp server are compatibility labels for the same generic wire
contract, not separate provider implementations or universal support claims.
The adapter reuses DAR's existing request construction and response
normalization.

The first slice is a direct BYOM adapter constructed by the caller. It does not
change `DARExternalAdapterProtocol`, the receiver registry, or the existing
OpenAI/LiteLLM default path.

## Decision and boundary

This is a single coherent component: one caller-bound, single-endpoint,
single-model adapter with a provider-neutral transport boundary. The component
does not own service installation, process startup, model downloads, or model
file discovery.

Protocol v1's installed-plugin factory is zero-argument and its static
descriptor binds one model identity. It therefore cannot safely represent an
arbitrary endpoint, credential, and model selected by the receiver. The first
slice must use the exported BYOM path with an explicit caller-supplied config.
Adding receiver-owned configuration binding or dynamic multi-model plugin
manifests is a separate protocol decision, not an implicit extension of this
feature.

## Users

- Hosts that already run Ollama, vLLM, LM Studio, or a llama.cpp OpenAI server.
- BYOM clients that need the external-adapter safety envelope without writing a
  provider-specific `ModelAdapter` wrapper.
- Runtime maintainers who want one tool-capable second implementation of the
  external protocol beyond Chrome's final-response-only adapter.

## Problem statement

DAR already has an OpenAI-compatible endpoint adapter and a separate external
adapter protocol. The endpoint adapter is useful for execution but does not
provide the external protocol's descriptor, health, cancellation context,
single-use dispatch, redacted error, and exact identity envelope. Conversely,
the external protocol currently has no configured service adapter.

Duplicating Ollama, vLLM, LM Studio, and llama.cpp-server integrations would
spread the same HTTP/request-shaping behavior across several provider names.
The feature should instead adapt the existing repository-owned OpenAI boundary
once and expose it through `DARExternalAdapterProtocol`.

## Scope

The first slice covers:

1. an explicit immutable configuration for one endpoint, one adapter ID, one
   DAR model alias, and one service model ID;
2. `https://` endpoints, plus `http://` only for loopback IP literals;
3. optional caller-supplied API-key authentication held in a private adapter
   field and never exposed through configuration serialization or diagnostics;
4. a bounded `/models`-equivalent readiness/model-identity check through an
   explicit injected transport boundary;
5. text requests, JSON Schema structured output, and model-returned tool calls;
6. sync and async construction through the existing transport helpers;
7. exact model identity binding using `(adapter_id, model alias, service model
   ID, canonical model ID)`, with the service model ID verified by health and
   used on every generation request;
8. package-owned error translation, cancellation/deadline propagation, and
   redacted metadata through `DARExternalAdapterProtocol`;
9. deterministic fake-transport tests for all service families; and
10. migration guidance showing how a caller replaces a direct local endpoint
    adapter with the external facade.

The service-family value is test-only descriptive metadata (`ollama`, `vllm`,
`lm-studio`, or `llama-cpp-server`); it does not select a code path or create a
support promise.

## Non-goals

- No change to `DARExternalAdapterProtocol` wire ID or v1 descriptor shape.
- No receiver-registry install/remove/list support for dynamically configured
  endpoints in this slice.
- No automatic endpoint discovery, port scanning, proxy-derived routing, or
  environment-based endpoint selection.
- No process lifecycle, server startup/shutdown, model download, or model-file
  management.
- No provider-specific SDK dependency for Ollama, vLLM, LM Studio, or llama.cpp.
- No OpenAI or LiteLLM default-path migration.
- No streaming, multimodal output, persistent sessions, embeddings, or native
  provider callbacks.
- No live service calls in unit tests.

## Configuration and transport contract

The public factory must accept an immutable non-secret configuration equivalent
to:

```python
@dataclass(frozen=True)
class OpenAICompatibleExternalConfig:
    adapter_id: str
    base_url: str
    model_alias: str
    service_model_id: str
    canonical_model_id: str
    tool_calling: bool = False
    timeout_seconds: float = 30.0
```

The factory accepts the optional API key as a separate constructor argument, not
as a readable field on this config object. The exact public names may be refined
during planning, but the implementation must preserve these semantics:

- `adapter_id`, `base_url`, `model_alias`, `service_model_id`, and
  `canonical_model_id` are required, validated, and never inferred;
- `adapter_id` is an opaque stable caller value, independent of URL, model
  credentials, and process randomness;
- the service model inventory must contain exactly `service_model_id` before
  health reports ready, and every generation request sends that same ID;
- the `canonical_model_id` is DAR-facing provenance and need not equal the
  service model ID; the relationship is fixed by the configuration;
- the API key is accepted only at construction and excluded from `repr`,
  equality/hash, descriptors, receipts, traces, errors, diagnostics, and
  serialization;
- `tool_calling=True` is an explicit caller assertion that the selected model
  and service support model-returned tools; it is not inferred from a model
  name;
- `timeout_seconds` must be greater than zero and no greater than 120 seconds,
  and has one documented precedence: the
  per-call DAR deadline is authoritative, then the configured transport
  timeout, then the transport's own lower bound; and
- plain HTTP is accepted only for loopback IP literals. URLs with userinfo,
  query, or fragment components are rejected. Redirects are disabled or must
  remain same-origin, and the transport must not use an ambient proxy.

The adapter consumes an explicit injected transport. Health is a synchronous,
adapter-owned operation because protocol v1 supplies no request context to
`health()`:

```python
list_models(*, timeout_seconds) -> ModelInventory
create_response(request, *, deadline_monotonic, cancellation) -> ModelResponse
```

The health inventory uses the configured timeout and has no caller deadline or
per-call cancellation; it must remain bounded and report timeout/unavailable
without leaking a raw payload. Generation receives the DAR request deadline and
cancellation. Async cancellation cancels the transport task. Synchronous
generation may be abandoned after its deadline, but in-flight I/O is not
claimed to be forcibly terminated; the bounded façade worker remains occupied
until it returns, and no fallback or second request is allowed.

The implementation provides separate sync and async adapter/transport variants
whose `create_response` methods match the façade dispatch mode. A sync variant
is offloaded by the façade for async workflows; an async variant is only used
through async dispatch and is rejected by sync dispatch.

The transport owns HTTP details and returns the normalized `ModelResponse`
boundary. The adapter replaces the DAR-facing `model_alias` with the verified
`service_model_id` exactly once. DAR's façade remains the sole owner of raw
removal, metadata allowlisting, JSON-schema validation, and tool-call capability
validation.
The adapter never constructs DAR's default OpenAI/LiteLLM provider.

## Adapter behavior

### Descriptor and health

The adapter exposes one descriptor with:

- the configured `adapter_id`;
- provider ID `openai-compatible-external`;
- exactly one `model_alias` and its caller-supplied `canonical_model_id`;
- local execution only when the caller explicitly identifies a loopback
  endpoint; otherwise remote execution;
- text input/output and `text`/`json_schema` response formats; and
- `structured_output` enabled because DAR validates returned JSON against the
  requested schema; this does not claim provider-native schema enforcement;
- `tool_calling` enabled only when the config explicitly enables it.

Health is one bounded explicit `list_models` operation using the configured
timeout; it is independent of the caller's request context. The only accepted
inventory shape is a finite sequence of model records with string `id` values;
the configured `service_model_id` must be present exactly. The adapter does not
select from the inventory, cache readiness beyond the current dispatch, or
enumerate other endpoints. Unavailable, mismatched, or malformed health
responses produce a package-owned unavailable state with no raw server payload.

### Request and response

The adapter converts `OpenAIModelRequest` through DAR's existing
OpenAI-compatible request path, preserving ordered messages, tools, tool
choice, response format, and bounded generation controls. It normalizes the
service response into DAR's existing `ModelResponse` and `ModelToolCall` types.

For `json_schema`, DAR validates the normalized returned content after
transport dispatch. A service may reject or ignore provider-native schema
controls; that is a post-dispatch transport/normalization outcome, not a claim
that the service enforces the schema.

When `tool_calling` is false, a request containing tools fails before transport
dispatch. When it is true, returned tool calls re-enter DAR's existing tool
coordinator; the service adapter never receives a handler, registry, approval
object, or executor callback.

The adapter must not silently retry a request with another endpoint, model,
provider, or OpenAI/LiteLLM fallback. Pre-dispatch admission failures include
invalid URL/configuration, failed health, disabled capabilities, cancellation,
and identity mismatch. Post-dispatch failures include transport timeout,
cancellation, and malformed response normalization. Both remain package-owned
and redacted; neither is a provider fallback signal.

### Service-family compatibility

| Compatibility label | Expected boundary | Evidence required |
| --- | --- | --- |
| Ollama | OpenAI-compatible `/v1` endpoint | fake generic-wire coverage; live certification deferred |
| vLLM | OpenAI-compatible `/v1` endpoint | fake generic-wire coverage; live certification deferred |
| LM Studio | OpenAI-compatible `/v1` endpoint | fake generic-wire coverage; live certification deferred |
| llama.cpp server | OpenAI-compatible `/v1` endpoint | fake generic-wire coverage; live certification deferred |

The matrix proves only that the generic adapter is invariant to a descriptive
label. It does not certify every model or service family. Certification
requires a separately authorized compatibility run against a pinned service
configuration.

## Functional requirements

### FR-1: Public BYOM factory

Given a valid explicit configuration, the package must construct an object
conforming to `DARExternalAdapterProtocol` without installing a plugin or
discovering a service.

### FR-2: Exact admission and identity

The adapter must reject invalid schemes, non-loopback plain HTTP, URL
userinfo/query/fragment, empty identity fields, unsupported capability
combinations, and a service inventory that does not contain the configured
`service_model_id` before generation. The request model sent to the service must
equal that verified ID.

### FR-3: Explicit transport safety

Every request must use the explicit transport and existing external-adapter
façade semantics: bounded context-independent health, generation
deadline/cancellation context, response normalization, redaction, single-use
dispatch, and package-owned errors. No default provider constructor or
ambient configuration is reachable.

### FR-4: Tool boundary

When explicitly enabled, model-returned tool calls must be normalized and
returned to DAR for ordinary coordinator handling. The adapter must never
invoke a tool handler directly.

### FR-5: No fallback or ambient discovery

A failed or unavailable service must fail closed. The adapter must not inspect
Ollama directories, enumerate local ports, read arbitrary environment
configuration, or fall back to OpenAI, LiteLLM, Chrome, or another model.

### FR-6: Deterministic testability

All unit tests must use injected fake transports and must cover sync/async
dispatch, health, identity mismatch, structured output, tool-call return,
timeouts, cancellation, malformed responses, redaction, and all four
non-normative compatibility labels. Tool-call tests must use a black-box
recording coordinator/approval seam and prove the adapter has no handler or
executor reference.

## Acceptance criteria

The feature is ready for implementation handoff when:

1. one configured generic adapter serves the declared OpenAI-compatible wire
   subset without provider-specific runtime branches; the four labels remain
   non-normative test metadata;
2. the adapter conforms to `DARExternalAdapterProtocol` and can be wrapped by
   the existing external façade;
3. a non-loopback HTTPS endpoint and a loopback HTTP endpoint are admitted,
   while non-loopback HTTP and unsupported schemes are rejected;
4. an explicit model mismatch, unavailable health state, invalid URL, or
   disabled capability fails before dispatch, while timeout, cancellation, and
   malformed response normalization are classified as post-dispatch failures;
5. structured output and model-returned tool calls preserve existing DAR
   normalization and coordinator behavior;
6. no credential, prompt, raw response, URL credential, or endpoint secret
   appears in receipts, exceptions, traces, or test evidence;
7. all tests are fake-transport-only and existing OpenAI/LiteLLM behavior is
   unchanged; and
8. the feature documentation states that service lifecycle remains caller-owned,
   family certification is separate, and packaged dynamic configuration
   requires a later protocol slice.

## Migration and future work

The first migration example should replace a caller's direct
`create_local_openai_adapter(...)` construction with the explicit external
factory plus strict model-adapter coverage. It must not remove or deprecate the
existing local endpoint helper.

Future slices may add receiver-owned configuration binding, packaged service
adapters, streaming, embeddings, richer model inventories, or native provider
callbacks. Each requires a separate protocol/spec decision; none is implied by
this feature.

## Review record

- 2026-09-23 Council architecture triad (Aristotle, Ada, Feynman): initial
  verdict **not ready**. The triad required stable adapter identity, mandatory
  service-model verification, an explicit transport and cancellation contract,
  testable URL/redirect rules, realizable secret handling, and a narrower
  generic compatibility claim.
- 2026-09-23 Ponytail full review: removed normative four-provider branching,
  ambient provider fallback, dynamic registry configuration, and the literal
  write-only config-secret claim; retained only the minimum generic endpoint
  contract needed for the protocol boundary.
- 2026-09-23 implementation clarification: protocol v1 health has no request
  context, so health uses the configured bounded timeout; sync and async
  adapter variants are separate façade-compatible modes, with sync late-result
  semantics explicitly non-abortable. This clarifies execution against the
  existing façade without changing the public protocol or approved config.
- Current disposition: approved; `plan.md` is the next reviewable artifact and
  `tasks.md` remains gated on plan approval.

## Approval gate

Approval confirmed the following before `plan.md` work began:

- direct BYOM construction is the correct first slice;
- one generic service adapter is preferred over separate Ollama/vLLM/LM Studio/
  llama.cpp implementations;
- the explicit transport, URL, identity, health, and cancellation rules are
  acceptable; and
- dynamic endpoint configuration remains out of the current receiver registry.
