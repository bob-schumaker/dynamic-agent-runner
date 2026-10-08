# Core LiteLLM OpenAI-Compatible Adapter Specification

## Metadata

- Feature slug: `litellm-provider-adapter`
- Mode: `light`
- Artifact type: authoritative feature specification
- Status: Slices L1-L3.2 implemented and validated; ChatGPT subscription OAuth
  support specified as follow-up
- Version: `0.8`
- Owner: repository maintainers and future implementers of model-provider
  runtime integrations
- Date: 2026-08-22
- Next gate: deferred provider-breadth follow-ups and OCI wheel cleanup
- Related artifacts:
  - `specs/dynamic-agent-runner/spec.md`
  - `specs/openai-compatible-provider-wrapper/spec.md`
  - `specs/default-openai-codex-auth/spec.md`
  - `specs/model-adapter-coverage/spec.md`
  - `src/dynamic_agent_runner/openai_client.py`
  - `src/dynamic_agent_runner/executor.py`
  - `tests/test_openai_client.py`
  - `litellm/README.md`
  - `https://docs.litellm.ai/docs/`
  - `https://docs.litellm.ai/docs/providers/chatgpt`
  - `https://docs.litellm.ai/docs/routing`
  - `litellm/litellm/responses/main.py`
  - `litellm/litellm/main.py`
  - `specs/litellm-provider-adapter/l2-codex-compatibility.md`

## Objective

Update `dynamic-agent-runner` so LiteLLM becomes the package's core
OpenAI-compatible model transport while preserving the package-owned
model-adapter contract, fake-client unit-test discipline, and existing
OpenAI/Codex default-auth behavior.

## Implementation Candidate Decision

This spec records the implemented high-ROI Slice L1. The slice stays narrower
than the full future surface described below:

- **Slice L1** uses the installed upstream LiteLLM package as the default direct
  SDK transport for ordinary
  OpenAI-format chat-completions dispatch.
- Slice L1 preserves repository-owned request construction, response
  normalization, model-adapter selection, error translation, redaction, and
  fake-test discipline.
- Slice L1 may keep the official OpenAI SDK provider as an explicit
  compatibility path.
- Slice L1 must not move ChatGPT/Codex auth discovery into LiteLLM and must not
  require live LiteLLM gateway, ChatGPT OAuth, or provider calls.
- LiteLLM is a required runtime dependency (`^1.97.0`; resolved to 1.98.0 for
  this change). The temporary `dynamic_agent_runner.litellm` fallback is
  retired. The separate checked-in OCI wheel cleanup remains follow-up work.
- ChatGPT/Codex-on-LiteLLM is a follow-up slice because current LiteLLM docs
  recommend the Responses endpoint for Codex models while the first direct SDK
  slice is intentionally Chat Completions-shaped.
- LiteLLM-managed ChatGPT subscription OAuth is specified as a separate
  follow-up route for the OpenAI-with-ChatGPT-auth requirement; it does not
  replace DAR's existing Codex credential discovery or backend route.

## Problem Statement

The current runtime is centered on `OpenAIClientAdapter` and
`AsyncOpenAIClientAdapter`, which dispatch `OpenAIModelRequest` objects through
a repository-owned client/provider facade and normalize Responses API-like
results into `ModelResponse`. That is already the right integration boundary
for OpenAI-compatible model transports.

LiteLLM is explicitly documented as a Python SDK that calls many providers using
the OpenAI format, returns consistent OpenAI Chat Completions-style responses,
maps provider errors to OpenAI exception types, and can run a proxy that any
OpenAI-compatible client can call. The local LiteLLM checkout also shows
`litellm.completion(...)`, `litellm.acompletion(...)`, `litellm.responses(...)`,
`litellm.aresponses(...)`, and router dispatch surfaces.

LiteLLM also documents a ChatGPT subscription provider under the `chatgpt/`
route. That provider uses OAuth device-flow authentication, supports
`/responses` and `/chat/completions` with Chat Completions bridged to Responses
for supported models, and exposes configuration such as `CHATGPT_TOKEN_DIR`,
`CHATGPT_AUTH_FILE`, and `CHATGPT_API_BASE`.

This feature should therefore promote LiteLLM to the default
OpenAI-compatible transport behind the existing repository-owned adapter
surface. The first implementation should adapt the runtime's current
request/response boundary to LiteLLM's OpenAI-format SDK, not invent a parallel
provider model. It should not replace the runtime's normalization ownership,
Codex auth resolver, local model adapters, or executor routing semantics.

The current ChatGPT/Codex backend behavior should move behind a helper shaped
like `create_litellm_codex_adapter_from_codex_auth(...)`: this package still
owns Codex home discovery, auth precedence, trusted config parsing, model
selection semantics, and request shaping, while LiteLLM owns the ChatGPT/Codex
transport.

For Slice L1, the existing SDK-backed ChatGPT/Codex backend may remain in place.
Replacing it with LiteLLM must wait for the follow-up Codex slice because it
needs explicit Responses-path request shaping and drift analysis.

## Users

- Runtime users who want one package-level integration path for OpenAI,
  Anthropic, Gemini, Bedrock, local servers, and other LiteLLM-supported
  providers.
- Host applications that already configure LiteLLM model strings, routers, or
  OpenAI-compatible LiteLLM proxy endpoints and want to supply that
  configuration to `dynamic-agent-runner`.
- Runtime maintainers who need provider breadth without spreading
  provider-specific SDK logic through executor code.

## Existing Runtime Context

- `openai_client.py` owns `OpenAIModelRequest`, `ModelResponse`,
  `build_openai_request(...)`, `normalize_openai_response(...)`, sync/async
  provider protocols, and sync/async adapter classes.
- `create_openai_response(...)` and `create_async_openai_response(...)` call
  `client.responses.create(**request.to_kwargs())` and translate provider
  failures into `ModelExecutionError`.
- The default OpenAI/Codex auth resolver lives in `openai_client.py` and must
  remain there; ChatGPT/Codex auth is an OpenAI auth pattern, not LiteLLM
  provider behavior.
- Executor model selection already uses adapter metadata such as `models` and
  `is_local`.
- Unit tests use fake clients, fake providers, and fake tool registries; they
  must not make live OpenAI, LiteLLM gateway, Hugging Face, Marimo, or model
  server calls.

## Scope

This feature covers:

1. making LiteLLM available as a required core runtime dependency
2. adding sync and async LiteLLM-backed clients or providers that conform to the
   runtime's OpenAI-compatible adapter expectations
3. using LiteLLM's OpenAI-format `completion(...)` / `acompletion(...)` SDK
   surface as the primary direct-SDK integration path
4. supporting caller-supplied LiteLLM routers where they preserve the same
   OpenAI-format request and response contract
5. supporting LiteLLM proxy endpoints through the existing
   `OpenAIProviderConfig.base_url` path rather than new runtime concepts
6. mapping the package's default OpenAI/Codex auth behavior onto
   `create_litellm_codex_adapter_from_codex_auth(...)` style helpers
7. preserving the current ChatGPT/Codex request semantics through a LiteLLM
   `chatgpt/` provider transport where behavior can be matched
8. preserving existing request construction and `ModelResponse` normalization
   boundaries
9. exposing public factory helpers through the package API
10. unit-test coverage with fake LiteLLM modules/routers and no live network or
    model calls

## Slice L1 Scope

The implemented Slice L1 covers only:

1. adding the upstream LiteLLM runtime dependency and requiring its transport
2. adding sync and async LiteLLM completion providers that satisfy the existing
   adapter/provider boundary
3. translating `OpenAIModelRequest` into LiteLLM Chat Completions kwargs without
   changing executor behavior
4. normalizing LiteLLM Chat Completions responses into `ModelResponse`
5. exposing public sync/async LiteLLM adapter factories
6. making ordinary default OpenAI-compatible provider creation use LiteLLM
   when no ChatGPT/Codex backend auth is selected
7. keeping the official OpenAI SDK compatibility provider/factory available
8. covering behavior with fake LiteLLM callables, fake routers, and no live
   network or provider calls

Slice L1 explicitly defers:

- LiteLLM `responses(...)` / `aresponses(...)`
- ChatGPT/Codex helper replacement
- LiteLLM-managed ChatGPT OAuth/device flow
- live model listing from LiteLLM routers or providers
- PyInstaller hook work unless the dependency addition breaks existing package
  hook tests

## Non-Goals

- Do not require implementation to remove the existing official OpenAI
  SDK-backed provider in the first slice; it may remain as an explicit
  compatibility/fallback path.
- Do not move Codex/OpenAI default-auth discovery out of `openai_client.py`.
- Do not move Codex auth precedence, trusted Codex config parsing, or
  unsupported-auth-mode policy into LiteLLM.
- Do not let LiteLLM's ChatGPT OAuth/device-flow state replace existing Codex
  auth discovery for the default package path.
- Do not treat the separately specified LiteLLM ChatGPT subscription provider
  as Codex `auth.json` auth; the caller must select that provider route
  explicitly, and LiteLLM owns its OAuth credential lifecycle.
- Do not require a LiteLLM gateway server for unit tests or default package
  import.
- Do not require LiteLLM Responses API support for the first direct-SDK slice
  when the documented Python SDK contract is Chat Completions-style
  `completion(...)`.
- Do not implement provider-specific credential discovery beyond what LiteLLM
  itself already supports through its SDK configuration and environment
  conventions.
- Do not add live model, gateway, or external provider calls to unit tests.
- Do not change workflow manifest schema for provider selection in the first
  slice.
- Do not replace the existing ChatGPT/Codex backend provider in Slice L1.
- Do not use LiteLLM's gateway, agent platform, MCP gateway, observability,
  guardrail, cache, or budget features in Slice L1.

## Functional Requirements

### FR-1: Make LiteLLM the core OpenAI-compatible transport

The runtime must define repository-owned sync and async LiteLLM-backed clients
or providers that satisfy the existing OpenAI-compatible adapter expectations,
and default runtime provider creation must prefer that transport.

Acceptance criteria:

- Given LiteLLM is installed, when a caller constructs a LiteLLM sync adapter,
  then the adapter can send a package-owned model request through
  `litellm.completion(...)` or an equivalent injected LiteLLM-compatible
  callable and return a `ModelResponse`.
- Given LiteLLM is installed, when a caller constructs a LiteLLM async adapter,
  then the adapter can send the same request shape through
  `litellm.acompletion(...)` or an equivalent injected LiteLLM-compatible
  callable and return a `ModelResponse`.
- Given default OpenAI-compatible adapter construction occurs, when LiteLLM is
  installed, then the default provider path is LiteLLM-backed rather than
  official-OpenAI-SDK-backed.
- Given LiteLLM is unavailable in an environment where it is declared as a core
  dependency, when default provider construction runs, then the runtime raises
  `ModelExecutionError` with a package-owned message naming the missing
  dependency.
- Given ChatGPT/Codex backend auth is selected before the follow-up Codex slice,
  when default provider construction runs, then the runtime may continue to use
  the existing SDK-backed ChatGPT/Codex provider rather than silently routing
  Codex tokens through LiteLLM's Chat Completions path.

### FR-2: Preserve current default auth and routing behavior

LiteLLM must take over transport without changing default auth precedence or
adapter routing semantics.

Acceptance criteria:

- Given an existing caller uses `OpenAIClientAdapter()` with no explicit
  provider, when the LiteLLM feature is implemented, then the adapter still uses
  repository-owned default OpenAI/Codex auth discovery before constructing the
  transport.
- Given an existing caller uses `create_openai_adapter_from_provider_config(...)`,
  when the LiteLLM feature is implemented, then the helper constructs a
  LiteLLM-backed OpenAI-compatible provider from that config by default.
- Given `model_adapter_coverage="augmented"` creates a default OpenAI adapter,
  when the LiteLLM feature is implemented, then that augmented default behavior
  uses the same repository-owned default auth discovery and LiteLLM transport.
- Given a caller explicitly requests the official OpenAI SDK compatibility path,
  when that path remains available, then it must use a clearly named helper and
  must not be the implicit default.

### FR-3: Keep request construction repository-owned

The runtime must continue to build model requests through package-owned helpers
before dispatching through LiteLLM.

Acceptance criteria:

- Given model execution renders messages, tools, tool choice, response format,
  and extra request options, when a LiteLLM adapter dispatches the request, then
  `build_openai_request(...)` or its directly equivalent package-owned path is
  still the source of request data.
- Given provider-specific LiteLLM kwargs are required, when callers configure a
  LiteLLM adapter, then those kwargs are passed through explicitly as adapter or
  provider configuration instead of being inferred from workflow manifests.
- Given the request includes unsupported options for a selected LiteLLM call
  type, when dispatch begins, then the runtime either raises `ModelExecutionError`
  before a provider call or documents and tests a deterministic translation.

### FR-4: Map requests to LiteLLM's OpenAI-format SDK surface

LiteLLM dispatch must target the documented OpenAI-format Python SDK surface as
the first implementation path.

Acceptance criteria:

- Given a runtime request contains messages and ordinary chat options, when a
  sync LiteLLM adapter dispatches it, then the adapter calls an OpenAI-format
  LiteLLM completion function with `model`, `messages`, and supported options.
- Given a runtime request contains messages and ordinary chat options, when an
  async LiteLLM adapter dispatches it, then the adapter calls an OpenAI-format
  LiteLLM async completion function with `model`, `messages`, and supported
  options.
- Given a caller supplies a LiteLLM `Router` with `completion` / `acompletion`,
  when dispatch occurs, then the runtime can route through that router without
  executor changes.
- Given a request uses runtime features that cannot be represented through
  LiteLLM's Chat Completions-style SDK surface, when dispatch would otherwise
  drop behavior, then the runtime raises `ModelExecutionError` instead of
  silently degrading the request.
- Given a later implementation adds `litellm.responses(...)` /
  `litellm.aresponses(...)` support, when that path is used, then it must be
  covered by separate tests and must not break the documented
  `completion(...)` path.

Slice L1 must explicitly translate:

- `OpenAIModelRequest.messages` to LiteLLM `messages`
- supported tool descriptors to the LiteLLM/OpenAI Chat Completions tool shape
- `tool_choice`, `response_format`, and supported `extra` values only when they
  can be represented without silent semantic loss

Unsupported request fields must fail with `ModelExecutionError` before a
provider call.

### FR-5: Normalize LiteLLM results through package-owned logic

LiteLLM responses must be converted to `ModelResponse` by repository code.

Acceptance criteria:

- Given LiteLLM returns chat-completions-style choices, when dispatch completes,
  then package-owned normalization extracts assistant text and tool calls into
  `ModelResponse` without leaking LiteLLM response objects into executor logic.
- Given LiteLLM returns a Responses API-like object from an explicitly supported
  future path, when dispatch completes, then `normalize_openai_response(...)` or
  a small package-owned LiteLLM normalization wrapper returns a `ModelResponse`.
- Given LiteLLM raises an exception, when the adapter handles it, then the
  runtime raises `ModelExecutionError` and redacts credential-like values from
  the message.

### FR-6: Provide explicit public factories

Callers must have a clear package-owned entry point for LiteLLM without reaching
into private modules.

Acceptance criteria:

- Given a caller wants sync LiteLLM execution, when they import from
  `dynamic_agent_runner`, then a public helper such as
  `create_litellm_adapter(...)` is available.
- Given a caller wants async LiteLLM execution, when they import from
  `dynamic_agent_runner`, then a public helper such as
  `create_async_litellm_adapter(...)` is available.
- Given a caller wants LiteLLM to model the package's OpenAI/ChatGPT-facing
  interface, when they import from `dynamic_agent_runner`, then a public helper
  such as `create_litellm_chatgpt_adapter(...)` is available and defaults to a
  `chatgpt/` model route.
- Given a caller wants the async version of that helper, when they import from
  `dynamic_agent_runner`, then a public helper such as
  `create_async_litellm_chatgpt_adapter(...)` is available and defaults to a
  `chatgpt/` model route.
- Given a caller wants to pass a LiteLLM router, completion callable, model list,
  local flag, or provider-specific kwargs, when they construct the adapter, then
  the public helper exposes those options intentionally and documents their
  behavior.
- Given a caller wants the package's existing default Codex auth behavior through
  LiteLLM, when they import from `dynamic_agent_runner`, then a public helper
  such as `create_litellm_codex_adapter_from_codex_auth(...)` is available.
- Given a caller wants the async version of that Codex helper, when they import
  from `dynamic_agent_runner`, then a public helper such as
  `create_async_litellm_codex_adapter_from_codex_auth(...)` is available.
- Given a caller wants to use the LiteLLM proxy, when they can reach it through
  an OpenAI-compatible base URL, then the existing
  `create_openai_adapter_from_provider_config(...)` path remains the preferred
  integration rather than a separate proxy-specific factory.
- Given future implementation chooses different helper names, when it lands,
  then the final names must be documented in README examples and tests.

### FR-7: Map Codex auth discovery onto LiteLLM ChatGPT/Codex transport

The runtime must map the existing ChatGPT/Codex backend behavior onto a
LiteLLM-backed Codex adapter without delegating repository auth policy to
LiteLLM.

Acceptance criteria:

- Given `${CODEX_HOME}/auth.json` contains file-backed API-key auth and caller
  auth is absent, when default LiteLLM provider construction runs, then the
  provider uses that key according to the existing `api_key_first` default
  ordering.
- Given `${CODEX_HOME}/auth.json` contains ChatGPT tokens and ChatGPT auth is
  selected by existing auth-preference rules, when
  `create_litellm_codex_adapter_from_codex_auth(...)` constructs an adapter,
  then the adapter routes through LiteLLM's `chatgpt/` provider rather than the
  public OpenAI API route.
- Given both API-key/auth-token auth and ChatGPT token auth exist, when caller
  preference is absent, then API-key/auth-token auth still wins before ChatGPT
  auth.
- Given both auth methods exist and `codex_auth_preference="chatgpt_first"`, when
  the Codex helper resolves auth, then ChatGPT token auth is selected.
- Given Codex ChatGPT auth is selected, when LiteLLM requires token-file,
  environment, or explicit-token configuration, then repository code adapts the
  already-trusted Codex auth result into LiteLLM configuration without reading
  workflow-package-local auth files.
- Given Codex ChatGPT auth is selected, when the LiteLLM adapter dispatches a
  Responses request, then it passes the DAR-resolved token, base URL, and
  account id explicitly and does not allow LiteLLM ambient auth discovery to
  override them.
- Given LiteLLM adds session, originator, user-agent, or default-instruction
  values, when the Codex adapter dispatches, then those values are either
  explicitly accepted as compatible or are bounded by DAR-owned configuration;
  no new ambient credential or auth-file source is read.
- Given a request names an unprefixed Codex model such as
  `codex-mini-latest`, when the LiteLLM Codex helper dispatches it, then the
  helper maps it to the provider route expected by LiteLLM, such as
  `chatgpt/codex-mini-latest`, without changing executor-facing model matching.
- Given LiteLLM's ChatGPT provider rejects token-limit fields or metadata, when
  a request includes those options, then the helper either lets LiteLLM strip the
  documented fields or fails with `ModelExecutionError` according to a tested
  policy.
- Given ChatGPT Chat Completions are bridged to Responses by LiteLLM for
  supported models, when the helper normalizes the result, then executor-facing
  behavior still returns `ModelResponse` without exposing bridge details.

### FR-8: Preserve current ChatGPT/Codex request semantics

The LiteLLM Codex adapter must intentionally preserve or document any drift from
the current `ChatGPTCodexBackendOpenAIClientProvider` request behavior.

Acceptance criteria:

- Given a request includes system or developer messages, when the LiteLLM Codex
  helper dispatches the request, then it preserves the current behavior of
  moving those messages into an `instructions` field or documents a tested
  LiteLLM-equivalent mapping.
- Given a request has no system/developer instructions, when the LiteLLM Codex
  helper dispatches it, then it preserves the current default instruction
  behavior or documents a tested LiteLLM-equivalent policy.
- Given a request contains Responses transcript items for a prior model tool
  call and tool result, when the LiteLLM Codex helper dispatches it, then the
  items and call identifiers remain intact for the follow-up request.
- Given LiteLLM emits streamed Responses text, function calls, or completion
  events, when DAR normalizes the result, then text, tool-call ids, arguments,
  response id, and terminal errors retain the existing `ModelResponse`
  semantics.
- Given ChatGPT/Codex dispatch occurs, when request options are prepared, then
  current `store=False` behavior is preserved unless LiteLLM guarantees the same
  behavior or the implementation records an approved spec update.
- Given current ChatGPT/Codex dispatch forces `stream=True`, when LiteLLM Codex
  dispatch is implemented, then streaming behavior is preserved or explicitly
  changed with test coverage and an approved spec update.
- Given supported-model discovery is needed, when the LiteLLM Codex adapter
  lists models, then it either preserves the current `client_version`-aware
  listing behavior or documents why LiteLLM has taken over that compatibility
  responsibility.
- Given the LiteLLM Codex adapter does not expose DAR's model-listing contract,
  when authenticated model discovery runs, then model listing remains on the
  DAR-owned client path and is not silently replaced by an unordered or
  visibility-blind LiteLLM list.

### FR-9: Preserve adapter metadata and executor selection

LiteLLM adapters must participate in existing executor routing without new
primitive node kinds.

Acceptance criteria:

- Given a LiteLLM adapter advertises `models`, when executor model matching runs,
  then it follows the same matching behavior as other model adapters.
- Given a LiteLLM adapter is configured for a local LiteLLM gateway or local
  model provider, when callers set `is_local=True`, then existing local-only
  adapter selection behavior is preserved.
- Given no model list is supplied, when default-model discovery is requested,
  then the implementation either uses an explicit LiteLLM/router model-listing
  capability or raises `ModelExecutionError` with a clear message.

### FR-10: Make dependency and packaging behavior explicit

The DAR-required OpenAI-compatible transport must be present in every install
as a declared upstream LiteLLM dependency, not as an accidental optional import
or frozen-binary dependency.

Acceptance criteria:

- Given package distribution is updated, when LiteLLM support is installed,
  then `litellm = "^1.97.0"` is resolved in `poetry.lock` and ordinary
  OpenAI-compatible requests use the upstream package.
- Given PyInstaller support exists for the current package, when LiteLLM support
  is added, then implementation notes must identify whether LiteLLM needs
  package hooks or whether frozen-app support is deferred.
- Given LiteLLM is missing or does not expose its required Chat Completions
  callable, when the default ordinary provider is constructed, then DAR raises
  a package-owned `ModelExecutionError` rather than using a local fallback.
- The existing checked-in OCI wheel is no longer the runtime distribution
  boundary. Removing its copy step and trigger is separate follow-up work.
- Given the OCI package step runs, when its Python interpreter is selected, then
  it uses Python 3.13 or newer to match the root package's `Requires-Python`
  metadata.

### Current migration decision

The implemented L2 Codex wrapper is opt-in. The SDK-backed ChatGPT/Codex
provider remains the global default until the drift review demonstrates all of
the following:

- LiteLLM's ChatGPT Responses path uses the DAR-resolved token and account
  identity without reading LiteLLM-owned auth files or initiating device auth;
- DAR's `client_version`-aware model listing, priority ordering, and visibility
  semantics remain intact; and
- the upstream LiteLLM Responses distribution remains installed and available
  to the target Python runtime (satisfied by the runtime dependency change).

The evidence and current decision are recorded in
`l2-codex-compatibility.md`. Until those gates pass, switching the global
default would be a semantic and authentication regression.

### FR-11: Keep tests fake and live-call-free

The implementation must prove behavior without contacting LiteLLM gateways or
external providers.

Acceptance criteria:

- Given LiteLLM adapter unit tests run, when they cover sync and async dispatch,
  then they use fake LiteLLM modules, fake routers, or injected callable
  dispatchers.
- Given tests cover broken core-dependency behavior, when LiteLLM import fails,
  then no network, gateway, or provider calls are attempted and the package
  raises a project-owned error from the relevant provider construction path.
- Given tests cover error translation, when fake LiteLLM raises a provider-like
  exception containing a token-shaped value, then the exposed
  `ModelExecutionError` does not include the secret.
- Given full repository tests run, when LiteLLM is installed, then core tests use
  fake LiteLLM dispatchers and do not require live credentials or providers.

### FR-12: Support LiteLLM ChatGPT subscription auth as a separate route

LiteLLM's `chatgpt/` provider and ChatGPT subscription OAuth flow are a
follow-up implementation route for DAR's OpenAI-with-ChatGPT-auth requirement.
This route is separate from FR-7's mapping of DAR-discovered Codex credentials
to the ChatGPT/Codex backend.

Acceptance criteria:

- Given a caller explicitly selects LiteLLM's ChatGPT subscription provider,
  when DAR dispatches a request, then it routes the model through LiteLLM's
  `chatgpt/` provider without using public OpenAI API-key or Codex backend auth.
- Given LiteLLM ChatGPT OAuth has not been completed, when the route is first
  used, then authentication follows LiteLLM's documented login flow and makes
  any required interaction clear to the caller.
- Given DAR has discovered Codex credentials, when the LiteLLM subscription
  route is selected, then DAR does not transfer those credentials into
  LiteLLM's OAuth store or use them as fallback credentials.
- Given route behavior is tested, when tests run, then they use fake or injected
  LiteLLM calls and auth state; they do not invoke live OAuth, providers, or
  model endpoints.
- Given the provider only supports a subset of DAR request semantics, when an
  unsupported request is submitted, then DAR fails explicitly rather than
  silently changing request behavior.

The route must use the `chatgpt/` provider documented at
`https://docs.litellm.ai/docs/providers/chatgpt`; availability, eligible plans,
and provider behavior must be checked against the supported LiteLLM version
when implementation is scheduled.

## Candidate API Shape

The implementation may adjust names after reading the final code context, but
the first planned public surface should be close to:

```python
create_litellm_adapter(
    *,
    model: str | None = None,
    completion: Callable[..., Any] | None = None,
    router: object | None = None,
    models: Sequence[str] | None = None,
    is_local: bool = False,
    litellm_kwargs: Mapping[str, Any] | None = None,
) -> OpenAIClientAdapter

create_async_litellm_adapter(
    *,
    model: str | None = None,
    acompletion: Callable[..., Awaitable[Any]] | None = None,
    router: object | None = None,
    models: Sequence[str] | None = None,
    is_local: bool = False,
    litellm_kwargs: Mapping[str, Any] | None = None,
) -> AsyncOpenAIClientAdapter

create_litellm_chatgpt_adapter(
    *,
    model: str = "chatgpt/gpt-5.3-codex",
    completion: Callable[..., Any] | None = None,
    models: Sequence[str] | None = None,
    litellm_kwargs: Mapping[str, Any] | None = None,
) -> OpenAIClientAdapter

create_async_litellm_chatgpt_adapter(
    *,
    model: str = "chatgpt/gpt-5.3-codex",
    acompletion: Callable[..., Awaitable[Any]] | None = None,
    models: Sequence[str] | None = None,
    litellm_kwargs: Mapping[str, Any] | None = None,
) -> AsyncOpenAIClientAdapter

create_litellm_codex_adapter_from_codex_auth(
    config: OpenAIProviderConfig | None = None,
    *,
    completion: Callable[..., Any] | None = None,
    models: Sequence[str] | None = None,
    litellm_kwargs: Mapping[str, Any] | None = None,
) -> OpenAIClientAdapter

create_async_litellm_codex_adapter_from_codex_auth(
    config: OpenAIProviderConfig | None = None,
    *,
    acompletion: Callable[..., Awaitable[Any]] | None = None,
    models: Sequence[str] | None = None,
    litellm_kwargs: Mapping[str, Any] | None = None,
) -> AsyncOpenAIClientAdapter
```

If `model` is supplied, it may override the request model or act only as a
default when the request does not specify one. The implementation plan must
choose one behavior before coding because silent model replacement affects
runtime correctness.

Slice L1 chooses this behavior: request model is authoritative. A factory
`model` value is adapter metadata or a default for future APIs only; it must not
silently override an `OpenAIModelRequest.model`.

## Design Constraints

- Keep executor logic provider-agnostic.
- Prefer composition around LiteLLM completion functions or routers over
  subclassing LiteLLM internals.
- Keep LiteLLM imports lazy and inside LiteLLM-specific provider code.
- Keep `OpenAIModelRequest` and `ModelResponse` as the first implementation's
  internal request/response contract unless a later approved spec creates a
  more generic model contract.
- Keep Codex/OpenAI default auth discovery in `openai_client.py`; LiteLLM should
  receive the resolved, trusted auth/config result rather than owning repository
  auth precedence.
- Use LiteLLM's ChatGPT provider for transport, but keep the default package
  path based on existing Codex auth discovery rather than LiteLLM-managed OAuth
  unless the caller explicitly chooses a LiteLLM-owned OAuth helper.
- Avoid new workflow manifest schema until a concrete caller needs declarative
  LiteLLM provider selection.

## Security and Privacy Requirements

- Secrets in LiteLLM kwargs, environment-derived values, provider exceptions,
  traces, or validation messages must not be logged or returned verbatim.
- LiteLLM ChatGPT token directories, auth filenames, API bases, and device-flow
  details must not be echoed into traces unless explicitly redacted.
- Provider-specific kwargs must be caller supplied or LiteLLM supplied; workflow
  packages must not be allowed to redirect ambient user credentials to arbitrary
  endpoints through this first slice.
- Codex auth files, selected tokens, token directories, and adapted LiteLLM auth
  kwargs must not be exposed in traces, reprs, exceptions, or test failure
  messages.
- Unit tests must include at least one redaction case for LiteLLM error
  translation.

## Compatibility Notes

- The existing OpenAI-compatible provider wrapper remains the owner for hosted
  OpenAI and OpenAI-compatible base-url configuration.
- LiteLLM direct SDK support is the new core OpenAI-format transport path. The
  official OpenAI SDK may remain only as an explicit compatibility path.
- LiteLLM proxy support can already fit the current
  `OpenAIProviderConfig(base_url=...)` model because the proxy is
  OpenAI-compatible.
- LiteLLM ChatGPT subscription support can model ChatGPT/Codex access, but the
  package's default behavior must preserve repository-owned Codex auth discovery
  and precedence before handing transport to LiteLLM.
- Some LiteLLM providers may not support Responses API semantics, tool calls,
  structured output, streaming, or model listing uniformly. The first
  implementation should fail visibly for unsupported semantics rather than
  pretending all providers are equivalent.

## Resolved Candidate Decisions

- **Model override:** factory `model` values do not override request models in
  Slice L1.
- **Model listing:** Slice L1 does not require router or provider model listing.
  Callers should pass explicit `models` metadata when model-aware executor
  selection needs it.
- **PyInstaller:** Slice L1 records packaging implications, but new LiteLLM
  hooks are deferred unless existing package-hook validation breaks.
- **L3.2 generic Responses dispatch:** callers opt in only by supplying a
  `responses` or `aresponses` callable to the generic LiteLLM adapter factory.
  The default remains Chat Completions; direct completion/Responses callable
  pairs are rejected before dispatch. Generic Responses calls reuse DAR's
  native Responses client boundary and forward only ordinary provider config.
  They do not load a global transport, infer Router Responses support, apply
  Codex request shaping or auth, change executor routing, or claim a provider
  capability catalog.
- **Codex aliases:** follow-up ChatGPT/Codex work should support both
  unprefixed repository-facing model ids and LiteLLM `chatgpt/` model ids
  through explicit alias rules.
- **Temporary packaging boundary:** the shim is retired now that LiteLLM is a
  portable runtime dependency. The checked-in OCI wheel, copy step, and trigger
  remain separately tracked cleanup work.
- **L3.1 router listing:** the requested caller need is bounded to a supplied
  `litellm.Router`. Its installed `get_model_list(model_name=None, team_id=None)`
  method is the only native discovery seam. The generic sync/async factories
  expose no new top-level listing API: their existing adapters continue to use
  `list_supported_models()` and `default_model()`. A supplied router contributes
  only nonblank deployment `model_name` values; the adapter keeps its existing
  caching, refresh, deduplication, and version-ordering behavior. Explicit
  `models` metadata remains authoritative until a caller requests refresh.
  Missing router discovery fails through the existing unavailable-listing error;
  router exceptions use the existing listing-failure error. L3.1 excludes
  gateway or network discovery, direct LiteLLM global catalogs, Codex listing,
  auth, aliases, executor routing, and capability/status reporting.

## Validation Checklist

- [x] `poetry run pytest tests/test_openai_client.py -q`
- [x] Targeted LiteLLM adapter tests covering sync completion dispatch, async
      completion dispatch, router dispatch, missing-upstream errors, unsupported
      option handling, tool-call normalization, and redacted errors.
- [ ] Targeted LiteLLM Codex helper tests covering Codex API-key auth,
      ChatGPT-token auth, `api_key_first` ordering, `chatgpt_first` ordering,
      unprefixed-to-`chatgpt/` model mapping, request shaping, documented
      unsupported option handling, fake LiteLLM dispatch, and secret redaction.
- [x] `poetry run pytest -q` after implementation.
- [x] `poetry run ruff check src tests` after implementation.
- [x] README or docs example added only after public helper names are final.
- [x] `python -m py_compile python-build-system.py`
- [x] Standard OCI package output contains the root artifacts and the exact
      checked-in LiteLLM wheel; compare SHA-256 hashes.

## Open Questions

- None blocking Slice L1.
- Follow-up Codex slice still needs a focused drift review for
  ChatGPT/Codex-specific request shaping, streaming, token-limit stripping,
  model aliases, and model-listing behavior.
