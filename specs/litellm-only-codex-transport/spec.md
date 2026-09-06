# LiteLLM-Only Codex Transport Specification

## Metadata

- Feature slug: `litellm-only-codex-transport`
- Mode: guided
- Artifact type: authoritative feature specification
- Status: postponed pending LiteLLM upstream support
- Version: 1.0
- Date: 2026-09-05
- Owner: OpenAI adapter and LiteLLM provider boundaries
- Related artifacts:
  - `specs/default-openai-codex-auth/spec.md`
  - `specs/openai-compatible-provider-wrapper/spec.md`
  - `specs/litellm-provider-adapter/spec.md`
  - `src/dynamic_agent_runner/openai_client.py`
  - `src/dynamic_agent_runner/litellm_client.py`
  - `tests/test_openai_client.py`
  - `tests/test_litellm_provider_adapter.py`

## Objective

Make LiteLLM the only DAR model-request transport for default OpenAI and
ChatGPT/Codex execution, while retaining DAR-owned, read-only discovery of
ambient OpenAI and Codex credentials and DAR-owned Codex model-catalog lookup.

The result must remove the direct official-OpenAI-SDK ChatGPT/Codex transport
path. It must not make LiteLLM responsible for logging in to ChatGPT, refreshing
Codex credentials, or writing to Codex credential storage.

## Postponement

This feature is postponed. DAR retains its current direct official-SDK
ChatGPT/Codex transport and its DAR-owned credential discovery, account
forwarding, catalog behavior, and credential-lifecycle boundary.

Reopen this specification only when a specific upstream LiteLLM release or
configuration passes the Transport Feasibility Gate without a DAR fork,
subclass, or monkeypatch. The upstream-compatibility analysis and probe design
below remain the required re-entry evidence.

## Decision

DAR will preserve `_ResolvedDefaultOpenAIProvider`, the existing private
credential-resolution result in `src/dynamic_agent_runner/openai_client.py`.
It contains an effective provider configuration and a repr-redacted optional
ChatGPT/Codex token. The account identifier remains exclusively in
`config.chatgpt_account_id`; no duplicate result field will be added. This seam
will remain in `openai_client.py`, not a new top-level auth module: ChatGPT/
Codex discovery is an OpenAI-provider concern.

All resolved credentials will then be consumed through LiteLLM:

```text
explicit configuration or trusted ambient inputs
  -> DAR private OpenAI/Codex credential resolution
  -> generic LiteLLM provider OR LiteLLM Codex provider
  -> DAR request normalization and model-response normalization
```

DAR-owned Codex model-catalog lookup remains separate from model execution. A
private `openai_client.py` callable, backed by an injected HTTPS transport, will
issue the authenticated catalog request and be supplied to the LiteLLM Codex
provider as its `model_list` callable. It must use the resolved bearer token,
optional account ID, and existing `client_version` query; it must not cause
LiteLLM credential discovery or official-SDK client construction.

`ChatGPTCodexBackendOpenAIClientProvider` and
`ChatGPTCodexBackendAsyncOpenAIClientProvider` will be removed only after the
LiteLLM Codex path passes the required unit, provider-boundary, catalog, and
manually authorized live parity gates.

### Transport Feasibility Gate

The currently lockfile-resolved LiteLLM release is `1.98.0`; the dependency
constraint in `pyproject.toml` is broader (`^1.97.0`) and therefore does not
make an upstream behavior assumption stable. An offline inspection of the
installed `1.98.0` ChatGPT Responses transform found that it constructs an
upstream `Authenticator`, calls that authenticator for token and account data,
generates a session ID, injects its own originator/default instructions, and
can read, write, refresh, or initiate device authentication. Supplying DAR
`api_key`, `api_base`, or extra headers does not bypass those operations.

That behavior contradicts the DAR-only credential, header, and renderer policy
below. Consequently, no default or official-factory cutover is authorized yet.
The implementation may proceed only after one of these explicit decisions:

1. select and pin an upstream LiteLLM release/configuration that proves an
   injected DAR token/account bypasses ambient authentication, session and
   originator identity, and upstream default-instruction mutation; or
2. amend this specification to retain the direct SDK transport (or authorize a
   different transport boundary) with its resulting maintenance trade-off.

Do not patch or monkeypatch LiteLLM private authentication classes in DAR
production code. That would introduce a second, unsupported transport
implementation rather than make LiteLLM the sole client path.

## Problem Statement

The current default-provider factory has two distinct client paths:

1. For ordinary OpenAI or OpenAI-compatible configurations it constructs
   `LiteLLMClientProvider` / `AsyncLiteLLMClientProvider`.
2. When Codex `auth.json` supplies a ChatGPT token it constructs
   `ChatGPTCodexBackendOpenAIClientProvider` or its async counterpart, which
   construct the official `openai` SDK against
   `https://chatgpt.com/backend-api/codex`.

This makes the transport choice depend on credential type. It duplicates
ChatGPT/Codex request shaping between `openai_client.py` and
`litellm_client.py`, creates two client-construction implementations to test,
and makes the default path harder to reason about.

LiteLLM already has a repository-owned Codex provider adapter:

- `LiteLLMCodexClientProvider` and its async counterpart accept an already
  resolved token.
- `_codex_litellm_kwargs(...)` supplies `custom_llm_provider="chatgpt"`, the
  bearer token, optional `ChatGPT-Account-ID`, Codex base URL, `store=False`,
  and streaming behavior.
- `_bind_codex_responses(...)` normalizes model IDs and dispatches Responses
  requests through LiteLLM.

That provider is the correct single transport target. It must receive a
well-defined credential-resolution result rather than repeat ad hoc discovery.

## Relevant Analysis and Current Behavior

### Credential discovery and selection

`_resolve_default_openai_provider_defaults(...)` is the existing private
composition point.

- Explicit `OpenAIProviderConfig.api_key` takes precedence.
- If no explicit key exists, `OPENAI_API_KEY` takes precedence over Codex cache
  discovery.
- Only when neither is available does DAR resolve `CODEX_HOME` and read the
  host-owned `${CODEX_HOME}/auth.json`.
- The cache reader supports declared API-key and ChatGPT modes, detects
  unsupported modes, reads `tokens.access_token` or `tokens.id_token`, and
  reads `tokens.account_id` when present.
- Within the Codex cache, `codex_auth_preference` selects API key first by
  default or ChatGPT first when explicitly requested.
- A caller-provided base URL remains authoritative. When ChatGPT auth is
  selected with no explicit base URL, DAR uses the Codex backend base URL.

The resolver is already the cohesive policy boundary. The direct SDK-only
ChatGPT provider classes and `_prepare_chatgpt_codex_request(...)` are the
transport-specific code to eliminate, not a reason to create another auth
abstraction.

### Account selection and credential lifecycle

DAR does not select an account: it forwards the one cached `tokens.account_id`
value as `ChatGPT-Account-ID`. It does not enumerate accounts or expose an
account-selection UI.

DAR also does not own the ChatGPT/Codex credential lifecycle. It does not:

- initiate the browser login;
- refresh a ChatGPT token;
- write, rotate, revoke, or delete `auth.json`; or
- persist a DAR copy of Codex credentials.

It reads the currently cached token when constructing a default provider. Codex
CLI owns cached-credential reuse and token refresh. The repository's generic
MCP OAuth implementation is unrelated and is out of scope for this feature.

### Current transport-specific behavior

The direct SDK ChatGPT path currently:

- uses the Codex backend base URL and bearer token;
- forwards `ChatGPT-Account-ID` when available;
- validates the model against the ChatGPT/Codex catalog;
- converts system and developer messages to `instructions`;
- renders tool-loop transcript items as Codex Responses input;
- forces `store=False` and stream handling suitable for the runtime.

The LiteLLM Codex adapter already contains corresponding Responses-oriented
behavior. It also has its own potential authentication and session behavior.
Parity must be proven at its real provider-transform boundary before removing
the direct SDK path; no requirement may assume two independently implemented
renderers are equivalent merely because they appear similar.

### Required ownership decisions

| Concern | Owner after migration | Required policy |
| --- | --- | --- |
| Credential source, precedence, and unsupported modes | DAR resolver | Preserve current trusted-source and preference rules. |
| Account identifier | DAR resolver / `config.chatgpt_account_id` | A conflicting injected `ChatGPT-Account-ID` is rejected; it cannot override the resolved account. |
| Responses request rendering | LiteLLM integration | One renderer consumes raw `OpenAIModelRequest` messages, including instruction folding and DAR transcript conversion. |
| Model catalog | DAR-owned callable injected into LiteLLM Codex provider | Preserve account header, `client_version`, visible filtering, priority ordering, and redacted errors without LiteLLM auth discovery. |
| Authorization | LiteLLM serialization of DAR input | The only bearer credential is the DAR-resolved token. |
| `ChatGPT-Account-ID` | DAR resolver / LiteLLM serialization | Optional, exactly once, and equal to `config.chatgpt_account_id`. |
| Session and originator identity | Not permitted by default | No ambient or persisted LiteLLM identity/session state is permitted. A later approved slice may amend this after evidence establishes a required, ephemeral alternative. |
| User agent and ordinary HTTP headers | LiteLLM transport | Permitted only when they contain no credential or account identity. |

Caller-supplied `litellm_kwargs` may supply non-identity request options only.
DAR rejects case-insensitive conflicts for `api_key`, `api_base`,
`custom_llm_provider`, `Authorization`, and `ChatGPT-Account-ID`; the resolved
Codex token, base URL, provider marker, and account remain authoritative.

## Scope

This feature covers:

1. reusing the existing private credential-resolution result in
   `openai_client.py` as the one input to provider construction;
2. routing resolved API-key and ChatGPT/Codex credentials through LiteLLM
   providers only, for sync and async adapters;
3. eliminating the direct official-OpenAI-SDK ChatGPT/Codex provider classes;
4. consolidating ChatGPT/Codex request preparation so one canonical,
   repository-owned renderer feeds LiteLLM;
5. preserving model-catalog, account-header, error-redaction, and adapter
   behavior; and
6. test-first contract coverage using fakes and no live services.

## Non-Goals

This feature must not:

- implement a ChatGPT login, browser callback, device login, token refresh, or
  account picker;
- write to or modify `${CODEX_HOME}/auth.json` or `config.toml`;
- move default OpenAI/Codex discovery to a separate package or generic OAuth
  module;
- change explicit configuration precedence or default
  `api_key_first` behavior;
- support currently unsupported Codex credential modes, including personal
  access token and agent-identity modes;
- change executor adapter selection, workflow schema, or model-access policy;
- make live OpenAI, ChatGPT, Codex, or LiteLLM requests in unit tests; or
- remove LiteLLM's generic OpenAI-compatible provider path.

## Functional Requirements

### FR-1: Keep credential resolution DAR-owned and transport-neutral

DAR must retain `_ResolvedDefaultOpenAIProvider` and its resolver in
`openai_client.py` as the separation between trusted credential discovery and
model-client construction. Its `config` carries any account ID and its optional
ChatGPT token is excluded from ordinary representations.

Acceptance criteria:

- Given explicit API key, base URL, provider, or discovery settings, when
  resolution runs, then existing precedence and opt-out behavior are preserved.
- Given `OPENAI_API_KEY`, when no explicit key is supplied, then it remains
  preferred to Codex cache discovery.
- Given only supported ChatGPT auth in the trusted Codex cache, when resolution
  runs, then the result contains the token, account ID if present, and Codex
  backend base URL unless the caller supplied a base URL.
- Given an unsupported or malformed Codex auth record, when resolution runs,
  then it raises a package-owned error that contains no secret material.
- Given no applicable credential is found, when resolution runs, then the
  generic LiteLLM default behavior remains available rather than synthesizing
  a credential.
- Given a resolved ChatGPT token, when the result is represented or included in
  an error, then the token is absent and the account ID appears only through
  the existing provider configuration contract.

### FR-2: Make LiteLLM the only default model-request transport

Default sync and async provider factories must construct a LiteLLM-backed
provider for every resolved credential mode.

Acceptance criteria:

- Given a resolved ordinary OpenAI/API-key configuration, when a default sync
  or async adapter lazily creates its client, then it uses the existing generic
  LiteLLM provider path.
- Given a resolved ChatGPT/Codex token, when a default sync or async adapter
  lazily creates its client, then it uses the LiteLLM Codex provider path.
- Given a ChatGPT/Codex token, when client construction occurs, then DAR does
  not import or instantiate `openai.OpenAI` or `openai.AsyncOpenAI` for that
  request path.
- Given a caller injects a client or provider, when the adapter is used, then
  no default credential discovery or provider replacement occurs.
- Given `create_official_openai_provider(...)` or
  `create_official_async_openai_provider(...)` resolves a ChatGPT/Codex token,
  when it constructs a provider, then it delegates to the respective LiteLLM
  Codex provider and never instantiates a direct ChatGPT/Codex SDK provider.
  For non-ChatGPT credentials, these explicit official-provider factories retain
  their documented SDK compatibility behavior.

### FR-3: Preserve ChatGPT/Codex transport contract through LiteLLM

The LiteLLM Codex path must preserve the behavior DAR currently requires from
the direct backend path.

Acceptance criteria:

- Given a resolved ChatGPT account ID, when DAR lists models or sends a model
  request, then the resolved value is forwarded exactly once. A conflicting
  injected `ChatGPT-Account-ID` fails with a package-owned error rather than
  overriding it.
- Given caller-supplied `litellm_kwargs`, when they conflict case-insensitively
  with the resolved token, base URL, provider marker, authorization header, or
  account header, then DAR rejects them with a package-owned redacted error.
- Given a resolved ChatGPT token and no caller base URL, when LiteLLM is bound,
  then it receives the Codex backend base URL and the `chatgpt` provider marker.
- Given raw `OpenAIModelRequest` messages, when a ChatGPT/Codex request is
  rendered by the LiteLLM integration, then it alone performs system/developer
  instruction folding, existing-instructions ordering, and DAR transcript
  conversion. The adapter does not pre-render ChatGPT/Codex-only messages.
- Given a tool-call and matching tool-result follow-up transcript, when the
  canonical renderer runs, then LiteLLM receives matching `function_call` and
  `function_call_output` input items with the original call ID, tool name, and
  arguments.
- Given a ChatGPT/Codex request, when dispatch occurs, then `store=False`,
  model normalization, and required streaming semantics remain unchanged.
- Given a generic OpenAI-compatible provider, when dispatch occurs, then
  ChatGPT/Codex request rewriting does not apply.
- Given DAR supplies a Codex token, when LiteLLM transforms the actual
  ChatGPT Responses request, then its ambient authenticator is never invoked
  and the supplied token is the only bearer credential source.
- Given the final outbound request is observed at the provider boundary, when
  it is a Codex request, then its identity-bearing headers are exactly
  `Authorization: Bearer <DAR-resolved token>` and, when configured,
  `ChatGPT-Account-ID: <config.chatgpt_account_id>`. No session or originator
  identity header may appear.

### FR-4: Preserve catalog and error behavior

The change must retain existing ChatGPT/Codex model-list behavior and
runtime-facing errors. Model catalog lookup is a DAR-owned private HTTPS
callable, injected into the LiteLLM Codex provider; it is not a
LiteLLM-authenticated transport or an official-SDK client.

Its transport contract is:

- Sync providers receive a private `CatalogTransport` callable with the shape
  `Callable[[str, Mapping[str, str], Mapping[str, str], float], Mapping[str,
  Any]]`; async providers receive the equivalent awaitable callable. The
  arguments are URL, query parameters, headers, and timeout seconds.
- DAR calls `GET {base_url.rstrip('/')}/models` with exactly the current
  `client_version` query, `Authorization: Bearer <resolved token>`, and the
  optional resolved `ChatGPT-Account-ID`. It permits no caller-supplied
  identity headers, follows no redirects, uses a 10-second timeout, and makes
  no implicit retry.
- The production collaborator rejects non-2xx responses, response bodies over
  1 MiB, malformed JSON, and non-mapping JSON. It returns the decoded mapping
  only; DAR's existing catalog extraction/filtering helpers retain visible-model,
  priority, and default semantics.
- Each failure is the existing package-owned `ModelExecutionError` category
  without URL query secrets, authorization values, account values, or raw
  response bodies. Sync and async adapters use their respective transport;
  neither calls LiteLLM or the official SDK for catalog access.

Acceptance criteria:

- Given the ChatGPT/Codex model catalog, when DAR lists supported models, then
  the injected callable sends the resolved bearer token, optional account header,
  and current `client_version` query; it preserves visible-model filtering,
  priority ordering, and default selection behavior for sync and async adapters.
- Given a requested ChatGPT/Codex model is absent from the discovered catalog,
  when execution is attempted, then DAR raises the same package-owned
  unavailable-model error category.
- Given LiteLLM raises a provider exception, when DAR surfaces it, then the
  resulting `ModelExecutionError` is redacted and does not expose token values
  or authorization headers.
- Given catalog lookup fails, when DAR surfaces the failure, then it is
  package-owned and redacted, and no model-list request triggers LiteLLM's
  ambient authenticator.

### FR-5: Remove duplicate direct-SDK implementation only after parity proof

The direct ChatGPT/Codex SDK providers and their transport-only helpers may be
removed only after all gates in FR-6 pass for both sync and async paths.

Acceptance criteria:

- `ChatGPTCodexBackendOpenAIClientProvider` and
  `ChatGPTCodexBackendAsyncOpenAIClientProvider` no longer exist after the
  migration.
- No default-provider branch selects the official OpenAI SDK solely because the
  resolved credential is a ChatGPT/Codex token.
- `_prepare_chatgpt_codex_request(...)` and its adapter call sites no longer
  exist. The LiteLLM integration is the one canonical ChatGPT/Codex renderer.
- The provider-boundary test proves that LiteLLM never invokes an ambient
  authenticator with DAR-supplied credentials, and the catalog-isolation test
  proves that catalog lookup remains DAR-owned.
- Package exports remain compatible unless a public direct-provider symbol is
  demonstrably unused and its removal is explicitly documented in the final
  change summary.

### FR-6: Require test-first parity evidence

Implementation must follow test-driven development. Add every focused behavior
test below first, observe the transport-selection and rendering tests fail
against the direct-SDK implementation, then implement the LiteLLM-only path and
make them pass.

Required tests:

1. credential resolver precedence: explicit key, environment key, Codex API
   key, ChatGPT-only cache, configured auth preference, malformed cache, and
   unsupported mode;
2. default sync and async factory selection for generic versus ChatGPT/Codex
   credentials, asserting the provider type without real imports or requests;
3. LiteLLM Codex binding: token, base URL, provider marker, account header,
   model normalization, `store`, and stream arguments;
4. request-rendering parity for ordinary text, system/developer instructions,
   tool calls, tool outputs, and pre-existing `instructions` values;
5. model-catalog filtering, ordering, and unavailable-model failures on the
   DAR-owned injected catalog callable, including the exact `client_version`
   query, account header, and sync/async catalog isolation; and
6. exception redaction, including fake sentinel tokens that must not occur in
   returned errors, logs, or representations.

Provider-boundary gates, also required before default cutover:

7. an integration test against the pinned upstream LiteLLM version that spies
   on its ChatGPT authenticator and fails if it reads ambient auth or performs
   device login when DAR injects a token, base URL, and account ID;
8. a final-request test that captures outbound headers and proves the approved
   header allowlist, account collision behavior, instruction ordering, and
   multi-turn tool transcript rendering; and
9. a manually authorized, opt-in live Responses parity run against a disposable
   Codex account. It must record redacted evidence for authentication, catalog
   listing, text, tool call, and tool-result follow-up behavior. Unit tests
   remain entirely offline; this gate is not a unit-test prerequisite. Record
   the command, environment prerequisites, redacted request/response facts, and
   result in `specs/litellm-only-codex-transport/validation.md`; its absence
   blocks default cutover and deletion of the direct SDK providers.

All tests must use fake clients, fake LiteLLM callables, fake files, and patched
environment state. They must not read a developer's real Codex home or contact
external services.

Before those tests are written, run the offline feasibility probe against the
exact lockfile-resolved LiteLLM artifact. It must patch its authenticator,
filesystem writes, session-ID creation, and HTTP/device-login seams to fail,
then observe the provider transform with distinct sentinel DAR token/account
values. Record the release version, package artifact identity, exercised
upstream classes/methods, and pass/fail result in `validation.md`. A failure
blocks all factory rewiring; it is not an expected-RED test to commit.

## Design Alternatives Considered

### A. Keep the direct SDK ChatGPT/Codex path

Rejected. It preserves an already-working route but leaves credential-dependent
transport selection and two request renderers in place. It increases test and
maintenance surface without adding a runtime capability.

### B. Move discovery into a generic credential or OAuth module

Rejected. It conflates OpenAI/Codex cache interpretation with DAR's generic MCP
OAuth lifecycle. The latter owns separate remote-server credentials and has no
place in model-provider construction.

### C. Make LiteLLM discover Codex credentials directly

Rejected. DAR needs explicit precedence, trust boundaries, auth-mode rejection,
and secret-redaction behavior. Delegating those decisions to LiteLLM would leak
repository policy into a third-party library and make it harder to test.

### D. Keep DAR resolution private and use LiteLLM for all requests

Chosen. This gives one model-request transport while preserving a small, deep
DAR-owned boundary for policy-sensitive credential discovery.

## Migration Plan

1. Run and record the upstream feasibility probe. Stop if the installed
   LiteLLM transform consumes ambient state or emits disallowed identity.
2. After an approved conforming LiteLLM version/configuration is pinned, add
   the complete resolver, factory, renderer, catalog, header-collision, and
   redaction tests without changing behavior; observe the expected direct-path
   failures.
3. Make the existing resolved-default result the single input to generic and
   Codex LiteLLM factories.
4. Move the complete ChatGPT/Codex renderer into the LiteLLM integration and
   preserve raw adapter requests until that boundary.
5. Implement the DAR-owned injected Codex catalog callable and its sync/async
   isolation tests.
6. Route default and explicit official sync/async factories through LiteLLM for
   ChatGPT/Codex credentials.
7. Pass the provider-boundary gates, then run the manually authorized live
   parity suite.
8. Delete direct SDK ChatGPT/Codex providers and redundant helpers only after
   the live parity receipt is accepted.
9. Run the focused tests, then the full test suite and Ruff.

No runtime credential migration is required: DAR continues reading the Codex
CLI-owned cache in place and never persists a copy.

## Verification Commands

During iteration:

```bash
poetry run pytest tests/test_openai_client.py -q
poetry run pytest tests/test_litellm_provider_adapter.py -q
```

Before completion:

```bash
poetry run pytest -q
poetry run ruff check src tests
```

## Compatibility and Security Notes

- This feature preserves the current public `OpenAIClientAdapter` and
  `AsyncOpenAIClientAdapter` contract.
- It does not turn a ChatGPT login into a generic OpenAI Platform API
  credential. The ChatGPT/Codex backend remains a provider-specific route.
- Codex CLI remains the owner of login storage and refresh. Official OpenAI
  documentation describes Codex credential caching and automatic token refresh
  during active ChatGPT-authenticated sessions.
- Runtime errors, traces, and test output must continue to redact credential
  material.

## Supersession Relationship

Until this feature is implemented, `specs/default-openai-codex-auth/spec.md`
remains authoritative for default discovery and its direct ChatGPT/Codex backend
provider. On implementation, this spec supersedes only the direct-SDK transport
portions of that feature. Its credential precedence, trusted-source, and
security requirements remain in force and are incorporated here.
