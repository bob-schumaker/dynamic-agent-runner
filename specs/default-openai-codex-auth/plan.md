# Default OpenAI/Codex Auth Discovery Implementation Plan

Status: implemented; Slices 1-4 complete

## Goal

Implement the authoritative behavior in
`specs/default-openai-codex-auth/spec.md`: make default OpenAI/Codex auth
discovery part of the OpenAI adapter's lazy default-provider path, triggered
only when no overriding caller auth is supplied.

Implementation status: complete. The OpenAI adapter default-provider resolver,
Codex user-level config/auth parsing, unsupported-auth handling, opt-out
behavior, documentation, and feature validation evidence are recorded in
`specs/default-openai-codex-auth/tasks.md`.

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
- The default adapter path currently constructs SDK-backed OpenAI clients with
  only caller-provided `OpenAIProviderConfig` values and the official SDK's own
  environment behavior.
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
  - `tomllib` for `${CODEX_HOME}/config.toml`
  - `json` for `${CODEX_HOME}/auth.json`
- Support file-backed Codex API-key auth first. Non-API-key Codex auth modes are
  explicitly unsupported in the first implementation slice.
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
4. If `api_key` is missing, resolve auth fallback:
   - prefer explicit SDK-compatible environment handling for `OPENAI_API_KEY`
     according to the implementation decision made in tests
   - otherwise read supported Codex API-key auth from `${CODEX_HOME}/auth.json`
5. If `base_url` is missing, resolve endpoint fallback:
   - read `${CODEX_HOME}/config.toml`
   - use `openai_base_url` when present and non-empty
6. Return a new `OpenAIProviderConfig` without mutating caller input.

The resolver may also parse `chatgpt_base_url` for future unsupported-auth
diagnostics, but the first implementation should not route ChatGPT/PAT/agent
identity auth through the public OpenAI API provider as if it were API-key auth.

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
- Do not support ChatGPT token, personal access token, or agent identity auth
  until a dedicated provider/base-url/signing design is specified and tested.
- Do not add a broad multi-provider router.
