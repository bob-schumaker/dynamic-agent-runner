# DAR External Adapter Protocol Specification

## Metadata

- Feature slug: `external-model-adapter-protocol`
- Artifact type: first-slice interface and implementation specification
- Status: approved
- Owner: dynamic-agent-runner model-provider boundary

## Objective

Define the smallest exported, fail-closed adapter contract needed to run the
Chrome Built-in AI/Gemini Nano model through DAR. The same contract is the
public seam for a future BYOM adapter, but v1 implements only the Chrome path.

The normative name is `DARExternalAdapterProtocol`; its wire ID is
`dar.external-model.v1`. “Custom” and “Magic” are product labels, not protocol
variants.

## Scope and design

The first slice is one receiver-approved Chrome plugin and one model call path:

```text
workflow -> existing DAR model path -> installed external adapter -> Chrome bridge
```

DAR owns model admission, request/response normalization, deadlines,
cancellation, redaction, tracing, and the tool boundary. The plugin owns
Chrome discovery, browser/extension lifecycle, readiness/download state, and
the JavaScript Built-in AI call. DAR does not scan for Chrome or access
Chrome-managed model files.

The protocol is intentionally text-only and final-response-only in v1. A
second runtime, multimodal result type, streaming, or native callback contract
requires a later version rather than more v1 switches.

## Public contract

```python
class DARExternalAdapterProtocol(Protocol):
    adapter_id: str
    protocol_id: Literal["dar.external-model.v1"]
    protocol_version: Literal["1.0"]

    def describe(self) -> ExternalModelAdapterDescriptor: ...
    def health(self) -> ExternalModelAdapterHealth: ...
    def create_response(
        self, request: OpenAIModelRequest
    ) -> ModelResponse | Awaitable[ModelResponse]: ...
```

`create_response` is the only execution method. DAR uses its existing async
executor: an adapter called in sync mode must return a non-awaitable result;
an adapter called in async mode may return an awaitable. A sync call from an
async workflow runs in DAR's bounded worker executor, never on the event loop.

### Descriptor

```python
@dataclass(frozen=True)
class ExternalModelAdapterDescriptor:
    adapter_id: str
    provider_id: str
    protocol_id: Literal["dar.external-model.v1"]
    protocol_version: Literal["1.0"]
    model_alias: str
    canonical_model_id: str
    execution_location: Literal["local", "remote"]
    execution_modes: frozenset[Literal["sync", "async"]]
    input_modalities: frozenset[Literal["text"]]
    output_modalities: frozenset[Literal["text"]]
    response_formats: frozenset[Literal["text", "json_schema"]]
    capabilities: frozenset[
        Literal["text_generation", "structured_output", "tool_calling"]
    ]
    limits: Mapping[str, int]
    contract_digest: str
```

V1 accepts exactly one model alias, exactly `{ "text" }` for input and output
modalities, and response formats `text` and `json_schema`. Streaming,
multimodal input/output, persistent sessions, native callbacks, and
provider-specific capabilities are not v1 features and have no v1 descriptor
fields. An enabled capability is present in `capabilities`; omission means
false, so Chrome omits `tool_calling`. Limits may contain
`max_context_tokens` and `max_output_tokens`.

The digest is a SHA-256 over the canonical JSON descriptor with
`contract_digest` omitted. It covers the fields above and excludes health,
credentials, transport endpoints, and runtime state. The receiver freezes the
descriptor after installation; a changed descriptor requires reinstalling the
adapter.

### Admission and request context

```python
@dataclass(frozen=True)
class ExternalModelAdapterHealth:
    status: Literal["ready", "unavailable", "failed"]
    error_code: str | None = None

class CancellationHandle(Protocol):
    @property
    def cancelled(self) -> bool: ...
    def raise_if_cancelled(self) -> None: ...
```

Health is advisory until the registry checks it immediately before dispatch.
Vendor exceptions, prompts, credentials, and transport payloads never appear
in `error_code`.

The receiver registry resolves an exact tuple:
`(adapter_id, contract_digest, model_alias, canonical_model_id)`. There is no
alias guessing, first-match behavior, model fallback, or OpenAI fallback once
an external adapter is selected.

The registry checks protocol version, descriptor digest, model alias,
capabilities, limits, and health before dispatch. It creates a per-call
deadline/cancellation context:

```python
@dataclass(frozen=True)
class DARExternalRequestContext:
    correlation_id: str
    deadline_monotonic: float | None
    cancellation: CancellationHandle
```

The context is DAR-owned and contains no tool registry, approval object, or
private executor state. Any prior internal context remains in DAR-private state
and is never exposed to the adapter.

If the adapter is removed before dispatch, the pending call is rejected;
already-dispatched work may finish until its deadline. A call cannot be
replayed after completion.

The receiver never auto-scans installed adapters. It selects one by explicit
receiver-owned ID, derives the exact descriptor tuple, and passes a validated
DAR `ModelAdapter` façade through the existing `model_adapter` surface. Once
selected, every workflow model node must use that descriptor's sole alias;
another alias fails before default-provider construction or dispatch. A node
without an explicit model resolves to that sole alias; ambiguous selection
fails closed. Raw BYOM protocol objects are normalized into the same façade
before legacy adapter selection.

### Request and response

The adapter consumes DAR's existing `OpenAIModelRequest` and returns the
existing `ModelResponse`/`ModelToolCall` shapes. DAR preserves ordered
messages, the selected model identity, and the declared generation controls.
Unknown fields, unsupported content, unavailable structured output, timeout,
cancellation, and malformed responses fail before or during dispatch with
package-owned errors. External responses set `raw=None`; metadata is
allowlisted and redacted.

For `json_schema`, DAR validates and canonicalizes the returned JSON before
returning it. V1 never returns binary/media results.

### Tool boundary

V1 supports model-returned tool calls only. The adapter receives tool
descriptors as model-visible data but never a handler callback. Returned
`ModelToolCall` values re-enter DAR's existing exposure, approval, lifecycle,
tracing, registry, and result-shaping coordinator. An adapter that only has
native browser/provider callbacks must omit `tool_calling` from its enabled
capabilities; DAR rejects workflows requiring model tool calls.

## Installation and removal

The receiver exposes:

```text
dynamic-agent-runner adapter install <approved-local-plugin>
dynamic-agent-runner adapter remove <adapter-id>
dynamic-agent-runner adapter list
```

For v1, installation accepts only an explicitly approved local package or
already-installed plugin ID. The receiver verifies the package artifact (or
trusted signer), validates its static protocol metadata before import, then
loads and validates the live descriptor. Unapproved URLs, workflow-package
code, duplicate IDs, and protocol mismatches are rejected. Installation is
visible to model selection only after validation.

The static receipt contains the adapter ID, protocol/version, descriptor
digest, artifact digest or trusted signer/origin, factory reference, immutable
`artifact_locator`, and distribution name/version. It is stored under the
receiver's DAR state root with owner-only permissions and atomically replaced.
On process reload, the receiver validates the receipt, locator, exact artifact
bytes, and trust metadata before importing the factory; it then validates the
live descriptor. Any changed, missing, moved, deleted, replaced, or
factory-mismatched artifact disables the registration. Failed installation
leaves no partially trusted receipt.

Removal unregisters the adapter for future calls and does not delete Chrome
profiles, model assets, caches, or external runtime state.

## BYOM surface

Export these names from the top-level package:

- `DARExternalAdapterProtocol`
- `ExternalModelAdapterDescriptor` and `ExternalModelAdapterHealth`
- `DARExternalRequestContext` and `CancellationHandle`
- normalized DAR request/response types
- package-owned adapter and model-execution errors

BYOM callers provide an adapter through the existing `model_adapter` execution
surface. DAR always performs the same descriptor, health, capability, context,
tool-boundary, and response validation; callers cannot bypass those checks.
The receiver registry is an internal installation mechanism, not a second
public execution protocol.

## Existing providers

OpenAI, LiteLLM, AFM, MLX, llama.cpp, and existing local runners remain on
their current paths. No compatibility wrapper or second model-selection engine
is required for the Chrome slice. A later adapter may project this descriptor
into the existing selector only when a concrete caller needs it.

## Chrome implementation

The optional Chrome plugin must:

- use supported Chrome Built-in AI JavaScript APIs
- own browser/extension/bridge lifecycle and origin/session policy
- report readiness/download state through `health()`
- translate text and supported structured results
- omit `tool_calling` from its enabled capabilities and reject streaming or
  native-callback requests as unsupported v1 semantics
- fail closed when Chrome, the API, the model, or the bridge is unavailable

The bridge authenticates its extension/origin identity, binds each request to
the DAR call context, enforces size/deadline limits, and rejects replayed or
disconnected requests.

## Implementation handoff

First implementation surfaces:

- `src/dynamic_agent_runner/external_adapter.py` — exported protocol, types,
  validation, and errors
- `src/dynamic_agent_runner/workflow_host/external_adapter_registry.py` —
  receiver-owned install, remove, list, persistence, and exact resolution
- existing API/context/executor modules — one `model_adapter` dispatch path
- `src/dynamic_agent_runner/cli.py` — adapter lifecycle commands
- `src/dynamic_agent_runner/__init__.py` — top-level exports
- `tests/test_external_adapter_protocol.py` — fake adapter and fake Chrome
  bridge conformance tests

The first Chrome artifact is a separately packaged
`plugins/dar-chrome-external-adapter/` distribution named
`dar-chrome-external-adapter`, with static manifest
`dar_external_adapter.json` and factory entrypoint
`dar_chrome_external_adapter:create_adapter`. Its built artifact must expose
an immutable locator and digest to the receiver installer.

Tests cover install validation, exact resolution, health failure, timeout,
cancellation, malformed/redacted responses, tool-call re-entry, removal,
replay rejection, and unchanged OpenAI/LiteLLM behavior. Live Chrome testing
is a separately authorized integration gate.

## Deferred work

These are separate future slices, not Chrome prerequisites:

1. Add multimodal, streaming, persistent-session, or native-callback protocol
   versions only when a concrete adapter requires them.
2. Rewrite AFM and add Ollama/vLLM/MLX/llama.cpp service adapters only when a
   caller needs a shared external lifecycle.
3. Add multi-model bindings, richer provider registries, compatibility wrappers,
   and a BYOM conformance suite after a second implementation exists.

## Non-goals

- marketplace or automatic third-party code execution
- browser automation API
- direct Chrome model-file access
- automatic Chrome, extension, asset, or sidecar installation
- forced migration of existing providers
- live external-provider calls in unit tests

## Readiness

This plan is ready to execute under its stated gates. The first slice is the
small exported protocol, receiver-controlled Chrome plugin lifecycle, existing
DAR dispatch integration, and fake-backed conformance tests.
