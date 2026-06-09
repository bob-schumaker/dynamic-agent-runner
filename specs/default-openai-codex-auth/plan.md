# Default OpenAI/Codex Auth Discovery Implementation Plan

Status: implemented; Slices 1-7 complete

## Goal

Implement the authoritative behavior in
`specs/default-openai-codex-auth/spec.md`: make default OpenAI/Codex auth
discovery part of the OpenAI adapter's lazy default-provider path, triggered
only when no overriding caller auth is supplied.

Implementation status: complete. The OpenAI adapter default-provider resolver,
Codex user-level config/auth parsing, ordered ChatGPT/Codex backend auth,
unsupported-auth handling, opt-out behavior, documentation, and feature
validation evidence are recorded in
`specs/default-openai-codex-auth/tasks.md`.

Follow-on evaluation status: ChatGPT token auth should be supported as an
OpenAI auth pattern through an explicit ChatGPT/Codex backend provider boundary
in `openai_client.py`, not as `OpenAIProviderConfig.api_key`. If only one
supported Codex auth method exists, the resolver should use it. If both
API-key/auth-token auth and ChatGPT auth exist, the default order should prefer
API-key/auth-token auth, with a caller option to prefer ChatGPT auth when it
exists.

Slice 5 implementation status: complete. The resolver now supports ordered
Codex auth selection, including ChatGPT/Codex backend auth when it is the only
supported Codex auth method or when `codex_auth_preference="chatgpt_first"` is
set and ChatGPT auth exists.

Slice 6 maintenance status: complete. The resolver now tolerates unrelated
Codex config TOML incompatibilities when only top-level `openai_base_url`
discovery is needed, and it treats an explicit `auth_mode` in `auth.json` as
authoritative before applying auth ordering.

Slice 7 implementation status: complete. ChatGPT/Codex adapters now list
authenticated available models before request dispatch and reject unadvertised
models before `responses.create`.

Slice 8 implementation status: complete. ChatGPT/Codex adapters now pass the
Codex client version from `${CODEX_HOME}/version.json` to model listing, accept
Codex backend model slugs, translate prompt instructions into the backend's
required `instructions` field, force `store=false` and `stream=true`, and
normalize streamed response text.

Slice 9 implementation status: complete. OpenAI adapters now expose
`list_supported_models()` so upstream callers can inspect configured or
authenticated model ids without reaching into the raw SDK client.

## Spec Trace

- Spec: `specs/default-openai-codex-auth/spec.md`
- Supporting analysis:
  `cline-tasks/codex-auth-endpoint-resolution-analysis.md`
- Related provider spec: `specs/openai-compatible-provider-wrapper/spec.md`
- Related adapter coverage spec: `specs/model-adapter-coverage/spec.md`

## Current Repository State

- `src/dynamic_agent_runner/openai_client.py` owns:
  - `OpenAIProviderConfig`
  - sync and async SDK-backed provider facades
  - `OpenAIClientAdapter` and `AsyncOpenAIClientAdapter`
  - default provider factories
  - request dispatch and response normalization
- The default adapter path resolves caller-provided `OpenAIProviderConfig`
  values, `OPENAI_API_KEY`, trusted Codex user config/auth, and ordered
  ChatGPT/Codex backend auth before constructing the selected provider.
- `model_adapter_coverage="augmented"` can create a default async OpenAI
  adapter when supplied adapters do not cover a requested model. That synthetic
  adapter must use the same default-provider discovery behavior as direct
  adapter construction.
- Unit tests already use fake clients/providers and monkeypatching in
  `tests/test_openai_client.py` and `tests/test_executor.py`; this feature must
  keep that no-live-network pattern.

## Planning Decisions

- Keep implementation inside the OpenAI adapter/provider boundary. Do not add
  executor-specific auth discovery logic.
- Add a small repository-owned resolver that accepts an `OpenAIProviderConfig`
  and returns a new resolved `OpenAIProviderConfig`.
- Keep the resolver private at first unless implementation pressure clearly
  justifies a public export.
- Add an opt-out flag to `OpenAIProviderConfig`, tentatively named
  `discover_default_auth: bool = True`, so callers can disable ambient
  discovery without changing executor APIs.
- Treat `OpenAIProviderConfig.api_key` as overriding auth. When it is present,
  auth discovery must not read ambient OpenAI/Codex auth.
- Treat `OpenAIProviderConfig.base_url` as overriding endpoint configuration.
  When it is present, endpoint discovery must not replace it.
- Preserve official SDK environment behavior for `OPENAI_ORGANIZATION` and
  `OPENAI_PROJECT` by not intercepting or clearing those values.
- Use structured parsers:
  - `tomllib` for `${CODEX_HOME}/config.toml`; if full-file parsing fails,
    fall back only to a narrow top-level `openai_base_url` scan whose value is
    still parsed with `tomllib`
  - `json` for `${CODEX_HOME}/auth.json`
- Treat explicit `auth_mode` in `${CODEX_HOME}/auth.json` as authoritative
  when it resolves to a supported or unsupported mode. If it declares
  `api_key`, only the API-key field is eligible. If it declares `chatgpt`, only
  ChatGPT token fields are eligible.
- Support file-backed Codex API-key/auth-token auth first by default.
- Support ChatGPT token auth through an explicit ChatGPT/Codex backend provider
  boundary in `openai_client.py`.
- If only one supported Codex auth method exists, use that method.
- If both API-key/auth-token auth and ChatGPT auth exist, prefer
  API-key/auth-token auth by default.
- Add a caller option to reverse that order so ChatGPT auth is selected when it
  exists.
- Do not treat ChatGPT tokens, personal access tokens, or agent identity
  credentials as `OpenAIProviderConfig.api_key` values.
- ChatGPT auth support must keep provider selection, endpoint selection, and
  auth selection coupled in a dedicated provider boundary inside
  `openai_client.py`.
- Do not read project-local `.codex/config.toml`, package-local `config.toml`,
  or workflow artifact metadata for endpoint/auth fallback.
- Redact secret-bearing fields in ordinary representation and errors. At
  minimum, set `OpenAIProviderConfig.api_key` to `repr=False` and avoid echoing
  credential values in new exception messages.

## Implementation Shape

### Resolver Flow

The default-provider resolver should follow this shape:

1. Accept an `OpenAIProviderConfig`.
2. Return the input config unchanged when `discover_default_auth` is false.
3. Copy caller-specified `api_key`, `base_url`, and `provider_name` into a
   mutable resolved configuration.
4. If caller auth is missing, resolve supported auth fallbacks:
   - prefer explicit SDK-compatible environment handling for `OPENAI_API_KEY`
     according to the implementation decision made in tests
   - otherwise read supported Codex auth from `${CODEX_HOME}/auth.json`
   - if `auth_mode` declares a supported mode, consider only credentials for
     that mode and fail if the declared mode's required credential is absent
   - if exactly one supported Codex auth method is present, use it
   - if API-key/auth-token and ChatGPT auth are both present, use
     API-key/auth-token auth unless the caller selected ChatGPT-first ordering
   - if ChatGPT-first ordering is selected and ChatGPT auth exists, use ChatGPT
     auth
5. If `base_url` is missing, resolve endpoint fallback:
   - read `${CODEX_HOME}/config.toml`
   - use `openai_base_url` for API-key/auth-token auth when present and
     non-empty
   - use the ChatGPT/Codex backend endpoint for ChatGPT auth, with trusted
     `chatgpt_base_url` handling defined by the provider boundary
6. Return a new `OpenAIProviderConfig` without mutating caller input.

The resolver may also parse `chatgpt_base_url` for future unsupported-auth
diagnostics and ChatGPT provider construction, but it must not route ChatGPT/PAT
or agent identity auth through the public OpenAI API provider as if it were
API-key auth.

### ChatGPT/Codex Backend Provider Shape

ChatGPT auth is implemented as an explicit provider boundary inside
`openai_client.py`, integrated with the default OpenAI auth resolver's supported
auth-method ordering.

The implementation shape is:

1. Use an explicit provider or adapter boundary in `openai_client.py` for
   ChatGPT/Codex backend model calls.
2. Resolve only trusted host-level Codex config and auth inputs:
   `${CODEX_HOME}/config.toml` and `${CODEX_HOME}/auth.json`.
3. Support file-backed ChatGPT `tokens` first, using fake-file unit tests.
4. Use ChatGPT auth when it is the only supported Codex auth method available.
5. Prefer API-key/auth-token auth over ChatGPT auth by default when both exist.
6. Use `OpenAIProviderConfig.codex_auth_preference="chatgpt_first"` to reverse
   discovery ordering so ChatGPT auth is selected when it exists.
7. Couple ChatGPT token auth to the ChatGPT/Codex backend model-call endpoint,
   defaulting to the Codex backend endpoint shape captured in the supporting
   analysis.
8. List authenticated available models before dispatching ChatGPT/Codex model
   requests. If the requested model is not advertised, fail before
   `responses.create` with the requested model and available ids.
9. Pass `client_version` for ChatGPT/Codex model listing, using
   `${CODEX_HOME}/version.json` `latest_version` when present, and normalize
   Codex backend model catalog slugs as model ids.
10. Translate ChatGPT/Codex Responses requests to the backend-required shape:
    request-level `instructions`, `store=false`, `stream=true`, and streamed
    text normalization back to `ModelResponse`.
11. Expose supported models through the adapter boundary:
    `OpenAIClientAdapter.list_supported_models()` for sync callers and
    `AsyncOpenAIClientAdapter.list_supported_models()` for async callers.
12. Preserve caller-supplied provider precedence; injected clients/providers must
    stay authoritative.
13. Keep workflow packages and project-local `.codex/config.toml` unable to
    select or redirect the provider.
14. Leave personal access token support to a later slice after bearer behavior
    and endpoint compatibility are verified.
15. Leave agent identity support to a later signing-provider design.

This provider remains part of the OpenAI auth/client module for now, but
it should not be named or modeled as an OpenAI API-key provider even if some
request/response wire details are OpenAI-compatible.

### Default Provider Integration

`create_default_openai_provider(...)` and
`create_default_async_openai_provider(...)` should call the resolver before
constructing `SDKBackedOpenAIClientProvider` or
`SDKBackedAsyncOpenAIClientProvider`.

`OpenAIClientAdapter` and `AsyncOpenAIClientAdapter` should continue to lazily
construct default providers the way they do now; the resolver belongs inside the
default provider factory rather than in the adapter property itself.

### Error Contract

Use package-owned errors from `dynamic_agent_runner.errors` for discovery
failures. Prefer `ModelExecutionError` unless implementation introduces a more
specific configuration error already established in the package.

Error messages should name:

- the discovery source, such as `CODEX_HOME`, `config.toml`, or `auth.json`
- unsupported Codex auth mode when relevant
- remediation, such as providing `OpenAIProviderConfig(api_key=...)` or disabling
  discovery

Error messages must not include:

- API keys
- access tokens
- refresh tokens
- personal access tokens
- agent identity private-key material

## Affected Areas

- `src/dynamic_agent_runner/openai_client.py` — resolver, config opt-out flag,
  SDK-backed default provider integration, redacted provider config
- `src/dynamic_agent_runner/errors.py` — only if a new package-owned error type
  is needed
- `tests/test_default_openai_auth.py` — focused resolver coverage
- `tests/test_openai_client.py` — default provider and adapter integration
  coverage
- `tests/test_executor.py` — augmented default OpenAI adapter regression, only
  if existing coverage cannot observe the new default-provider path
- `README.md` — document default auth discovery, precedence, and opt-out
- `specs/default-openai-codex-auth/spec.md`,
  `specs/default-openai-codex-auth/tasks.md`, and `specs/README.md` — status and
  evidence updates after implementation

Implemented ChatGPT/Codex backend provider work affects:

- `src/dynamic_agent_runner/openai_client.py` for the explicit ChatGPT/Codex
  backend provider boundary and resolver selection
- `tests/test_default_openai_auth.py` and `tests/test_openai_client.py` for fake
  ChatGPT token auth fixtures and provider construction coverage
- `README.md` for ordered auth selection and unsupported-mode guidance

## Validation Plan

Targeted tests during implementation:

```bash
poetry run pytest tests/test_default_openai_auth.py \
  tests/test_openai_client.py -q
```

If no new test file is created:

```bash
poetry run pytest tests/test_openai_client.py -q
```

Executor regression for augmented default adapter behavior:

```bash
poetry run pytest tests/test_executor.py -q
```

Final relevant validation:

```bash
poetry run pytest -q
poetry run ruff check src tests
```

## Non-Implementation Notes

- Do not make workflow packages a source of auth or endpoint settings.
- Do not add live calls to OpenAI, ChatGPT, Codex, or local model servers.
- Do not implement keyring-backed Codex auth in the first slice.
- Do not support ChatGPT token auth through `OpenAIProviderConfig.api_key`; use
  the explicit ChatGPT/Codex backend provider boundary in `openai_client.py`.
- Do not add ChatGPT token support by passing ChatGPT tokens as
  `OpenAIProviderConfig.api_key`.
- Do not support personal access token auth until bearer behavior and endpoint
  compatibility are specified and tested.
- Do not support agent identity until a signing provider exists.
- Do not add a broad multi-provider router.
