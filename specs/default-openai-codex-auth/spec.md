# Default OpenAI/Codex Auth Discovery Specification

## Metadata

- Feature slug: `default-openai-codex-auth`
- Mode: `light`
- Artifact type: authoritative feature specification
- Status: implemented authoritative feature spec
- Version: `1.3`
- Owner: repository maintainers and future implementers of the OpenAI adapter
  default-provider path
- Next gate: none; Slices 1-6 are complete
- Approval state: user-directed promotion of this spec as the authoritative
  continuation source for default OpenAI/Codex auth discovery
- Related artifacts:
  - `specs/dynamic-agent-runner/spec.md`
  - `specs/openai-compatible-provider-wrapper/spec.md`
  - `specs/model-adapter-coverage/spec.md`
  - `specs/default-openai-codex-auth/plan.md`
  - `specs/default-openai-codex-auth/tasks.md`
  - `cline-tasks/codex-auth-endpoint-resolution-analysis.md`
  - `src/dynamic_agent_runner/openai_client.py`
  - `src/dynamic_agent_runner/context.py`
  - `src/dynamic_agent_runner/api.py`
  - `tests/test_openai_client.py`
  - `tests/test_executor.py`

## Objective

Make OpenAI/Codex auth discovery part of the OpenAI adapter's default provider
path, so it triggers automatically only when the caller has not provided
overriding auth or endpoint configuration.

## Problem Statement

`dynamic-agent-runner` already supports caller-provided model adapters and
OpenAI-compatible provider configuration through `OpenAIProviderConfig`. That is
the right explicit path for callers that know which endpoint and credential to
use.

However, interactive host environments often already have usable OpenAI or
Codex configuration. Today, an OpenAI adapter that lazily constructs its default
provider relies on the official OpenAI SDK's default environment handling only.
The adapter does not have a repository-owned way to discover Codex-style
defaults such as `${CODEX_HOME}/config.toml` and `${CODEX_HOME}/auth.json`, nor
does it document which ambient auth sources are safe to use.

This feature should make the default path more useful while preserving the
security boundary from the Codex analysis: generated workflow packages must not
decide where user credentials are sent.

## Users

- Runtime users who have already authenticated with OpenAI or Codex locally.
- Host applications that want default model execution to work without duplicating
  Codex auth discovery logic.
- Runtime maintainers who need one tested boundary for ambient auth fallback.

## Existing Runtime Context

- `OpenAIProviderConfig` currently supports optional `base_url`, `api_key`,
  `provider_name`, `discover_default_auth`, and `codex_auth_preference`.
- `SDKBackedOpenAIClientProvider` and
  `SDKBackedAsyncOpenAIClientProvider` construct official SDK clients from
  `OpenAIProviderConfig`.
- `OpenAIClientAdapter` and `AsyncOpenAIClientAdapter` lazily construct default
  providers when no caller-provided client or provider exists. This lazy
  adapter-owned default-provider path is the intended integration point for this
  feature.
- `model_adapter_coverage="augmented"` may create the default OpenAI adapter when
  supplied adapters do not cover a requested model.
- `model_adapter_coverage="strict"` makes caller-supplied adapters
  authoritative.
- `cline-tasks/codex-auth-endpoint-resolution-analysis.md` records Codex's
  relevant auth/config behavior:
  - `CODEX_HOME` defaults to `~/.codex`
  - user config may define `openai_base_url`, `chatgpt_base_url`,
    `model_provider`, and `model_providers`
  - file-backed auth lives at `${CODEX_HOME}/auth.json`
  - endpoint and provider selection are security-sensitive
  - project-local config must not be allowed to redirect credentials

## Scope

This feature covers:

1. adapter-owned discovery of default OpenAI/Codex auth inputs during lazy
   default provider construction
2. safe conversion of supported discovered auth into `OpenAIProviderConfig`
3. preservation of explicit caller configuration precedence, especially caller
   auth overrides
4. clear failure behavior for discovered auth modes that cannot be safely used
   through the current OpenAI-compatible SDK seam
5. unit-test coverage with fake files, fake environment variables, and no live
   OpenAI, Codex, or network calls

This feature does not make ChatGPT session tokens part of
`OpenAIProviderConfig.api_key`. ChatGPT auth belongs to an explicit
ChatGPT/Codex backend provider boundary in `openai_client.py` because Codex
routes that auth mode to the ChatGPT/Codex backend rather than the public OpenAI
API default. The default OpenAI auth resolver may still select ChatGPT auth when
it is the only supported Codex auth method available, or when a caller-selected
auth preference asks for ChatGPT auth first.

## Authority and Continuation

This spec is authoritative for continuing default OpenAI/Codex auth discovery
work in `dynamic-agent-runner`.

Future implementation must derive behavior from this artifact before changing
`openai_client.py`, default provider construction, adapter lazy initialization,
or default OpenAI adapter creation. The companion Codex analysis remains
supporting background only; it does not override this spec's chosen repository
boundary.

If implementation expands beyond a focused OpenAI adapter/default-provider
slice, create companion `plan.md` and `tasks.md` artifacts under this feature
directory before coding the expanded scope.

## Functional Requirements

### FR-1: Trigger discovery only from the OpenAI adapter default path

Default auth discovery must be part of the OpenAI adapter's lazy default
provider construction path.

Acceptance criteria:

- Given `OpenAIClientAdapter` has no injected client and no injected provider,
  when its lazy `client` property constructs the default provider, then default
  auth discovery is eligible to run.
- Given `AsyncOpenAIClientAdapter` has no injected client and no injected
  provider, when its lazy `client` property constructs the default async
  provider, then default auth discovery is eligible to run.
- Given workflow execution creates a default OpenAI adapter because augmented
  adapter coverage needs one, when that adapter constructs its default provider,
  then the same default auth discovery path is used.
- Given any code path does not go through the OpenAI adapter default provider,
  when it constructs or uses another model adapter, then this feature does not
  run.

### FR-2: Preserve explicit caller configuration precedence

Explicit caller inputs must remain authoritative.

Acceptance criteria:

- Given a caller provides a concrete `OpenAIProviderConfig.api_key`, when default
  provider construction runs, then ambient OpenAI/Codex auth discovery must not
  replace that overriding auth.
- Given a caller provides a concrete `OpenAIProviderConfig.base_url`, when
  default provider construction runs, then ambient OpenAI/Codex endpoint
  discovery must not replace that URL.
- Given a caller provides a concrete provider with its own
  `OpenAIProviderConfig.api_key`, when the adapter uses that provider, then the
  adapter must not run default auth discovery.
- Given a caller provides a client, provider, or model adapter, when workflow
  execution runs, then default auth discovery must not be used for that supplied
  collaborator.
- Given `api_key` is absent but `base_url` is present, when default provider
  construction runs, then auth discovery may fill only missing auth and must not
  change the caller-specified endpoint.
- Given `base_url` is absent but `api_key` is present, when default provider
  construction runs, then auth discovery must not run; endpoint discovery may
  fill only missing endpoint config and must not change the caller-specified
  auth.

### FR-3: Discover OpenAI environment defaults without breaking SDK behavior

The runtime must preserve the official SDK's existing environment behavior while
making repository-owned default resolution observable and testable.

Acceptance criteria:

- Given no overriding caller auth is supplied and `OPENAI_API_KEY` is set, when
  the OpenAI adapter default provider is constructed, then the resolved provider
  config may carry that key explicitly or may intentionally leave SDK
  environment handling in place, but the behavior must be covered by unit tests.
- Given `OPENAI_ORGANIZATION` or `OPENAI_PROJECT` is set, when default provider
  config is resolved, then the feature must not silently drop SDK-supported
  environment behavior.
- Given no relevant environment variables exist, when the OpenAI adapter default
  provider is constructed, then discovery continues to Codex defaults rather
  than failing early.

### FR-4: Resolve `CODEX_HOME` safely

The runtime must resolve Codex home consistently enough to find user-level
Codex config and auth.

Acceptance criteria:

- Given `CODEX_HOME` is set to a non-empty path, when discovery runs, then that
  directory is used as the Codex home candidate.
- Given `CODEX_HOME` is unset or empty, when discovery runs, then the default
  Codex home candidate is `~/.codex`.
- Given `CODEX_HOME` is set but does not exist or is not a directory, when
  discovery runs, then the runtime fails with a project-specific configuration
  error or ignores that candidate according to an explicitly documented policy.
- Given Codex home is resolved, when file paths are built, then only files under
  that home are considered for Codex user config and auth discovery.

### FR-5: Read only trusted Codex user-level config

Default endpoint discovery must read only trusted host-owned Codex config, not
workflow-package or repository-local Codex config.

Acceptance criteria:

- Given `${CODEX_HOME}/config.toml` contains `openai_base_url`, when caller
  `base_url` is absent, then the OpenAI adapter default provider config may use
  that URL.
- Given `${CODEX_HOME}/config.toml` contains `chatgpt_base_url`, when a supported
  Codex backend auth mode requires a backend URL, then the resolver may use that
  value only for the relevant backend/control-plane behavior.
- Given a workflow package contains `.codex/config.toml`, `config.toml`, or other
  project-local endpoint settings, when the OpenAI adapter default provider is
  resolved, then those files must not be read for endpoint or auth fallback.
- Given full config parsing fails because of unrelated Codex config syntax, when
  a top-level `openai_base_url` can still be parsed safely or is absent before
  the first table header, then discovery must not fail solely because of the
  unrelated config shape.
- Given the top-level `openai_base_url` value itself is malformed, when
  discovery needs that value, then the runtime raises a project-specific error
  that names the bad config file without exposing secret values.

### FR-6: Support file-backed Codex API-key/auth-token auth first by default

The default Codex auth ordering must prefer file-backed API-key/auth-token auth
from `${CODEX_HOME}/auth.json` before ChatGPT auth when both supported methods
exist. API-key/auth-token auth maps directly to the current OpenAI-compatible
SDK provider seam.

Acceptance criteria:

- Given `${CODEX_HOME}/auth.json` has `auth_mode` resolving to API-key auth and
  contains `OPENAI_API_KEY`, when caller `api_key` is absent, then the OpenAI
  adapter default provider config uses that API key.
- Given only API-key/auth-token auth is available in Codex defaults, when
  caller auth is absent, then the OpenAI adapter default provider uses
  API-key/auth-token auth.
- Given `${CODEX_HOME}/auth.json` contains an API key but caller `api_key` is
  present, when default config is resolved, then the caller key wins.
- Given both API-key/auth-token auth and ChatGPT auth are available in Codex
  defaults and no caller preference overrides ordering, when caller auth is
  absent, then the resolver selects API-key/auth-token auth first.
- Given `${CODEX_HOME}/auth.json` declares `auth_mode` resolving to API-key
  auth, when ChatGPT token fields are also present, then the resolver treats
  API-key auth as the only eligible Codex auth method for that file.
- Given `${CODEX_HOME}/auth.json` is absent, when discovery runs, then that
  absence is not an error by itself.
- Given `${CODEX_HOME}/auth.json` is malformed, when discovery needs it, then
  the runtime raises a project-specific error without logging or echoing secret
  fields.

### FR-7: Treat non-supported Codex auth modes explicitly

Codex ChatGPT tokens, personal access tokens, and agent identity auth must not
be silently treated as ordinary public OpenAI API keys. ChatGPT token auth may
be supported only through the explicit ChatGPT/Codex backend provider boundary;
personal access token and agent identity auth remain unsupported until their
provider behavior is specified and tested.

Acceptance criteria:

- Given Codex auth resolves to ChatGPT token auth, when ChatGPT/Codex backend
  provider support is available and caller auth is absent, then discovery may
  select ChatGPT auth according to the configured auth ordering.
- Given `${CODEX_HOME}/auth.json` declares `auth_mode` resolving to ChatGPT auth,
  when public API-key fields are also present, then the resolver treats ChatGPT
  auth as the only eligible Codex auth method for that file.
- Given `${CODEX_HOME}/auth.json` declares `auth_mode` resolving to ChatGPT auth
  but has no usable token, when discovery needs Codex auth, then the runtime
  raises a project-specific error without falling through to another credential
  field or exposing secret values.
- Given Codex auth resolves to a personal access token, when the implementation
  has verified a compatible model-call base URL and bearer behavior, then the
  runtime may support it; otherwise it must report the mode as unsupported.
- Given Codex auth resolves to agent identity, when discovery runs, then the
  runtime must not expose private-key material as a bearer token and must report
  the mode as unsupported unless a dedicated signing provider has been designed.
- Given unsupported auth is reported, when the error is rendered, then it must
  include the auth mode and remediation guidance but no credential material.

### FR-8: Keep default discovery opt-out possible

Hosts that do not want ambient credential discovery must be able to disable it.

Acceptance criteria:

- Given a caller or host disables default auth discovery, when the OpenAI adapter
  default provider is constructed without explicit provider config, then the
  runtime behaves like the current default SDK path or fails according to the
  existing provider behavior.
- Given discovery is disabled and `model_adapter_coverage="strict"` is used,
  when no matching adapter exists, then the runtime must not create a discovered
  default provider.
- Given discovery is enabled by default, when documentation describes the
  behavior, then it must also describe the opt-out path.

### FR-9: Keep secrets out of logs, traces, errors, and tests

Auth discovery must not create new credential exposure paths.

Acceptance criteria:

- Given discovery reads environment variables or auth files, when errors,
  traces, debug strings, or validation messages are produced, then credential
  values must not appear.
- Given unit tests cover secret-bearing files, when fixtures are created, then
  test credentials must be fake sentinel values and must not require real local
  Codex or OpenAI auth.
- Given a provider config includes an API key, when `repr(...)` or dataclass
  output is considered, then the implementation must avoid exposing the key in
  ordinary logs or add a redacted representation before logging such objects.

### FR-10: Keep ChatGPT auth support explicit, provider-scoped, and orderable

ChatGPT auth support must be implemented as an explicit ChatGPT/Codex backend
provider path in `openai_client.py`, not as an expansion of
`OpenAIProviderConfig.api_key` or the public OpenAI API-key resolver. Auth
selection must use deterministic ordering when multiple supported Codex auth
methods are available.

Acceptance criteria:

- Given Codex auth resolves to ChatGPT `tokens`, when the current default
  OpenAI adapter resolver runs, then it must not treat token material as an
  OpenAI API key.
- Given only ChatGPT auth is available in Codex defaults, when ChatGPT/Codex
  backend provider support exists and caller auth is absent, then the resolver
  selects ChatGPT auth.
- Given both API-key/auth-token auth and ChatGPT auth are available in Codex
  defaults, when no auth-ordering option is supplied, then the resolver selects
  API-key/auth-token auth first.
- Given both API-key/auth-token auth and ChatGPT auth are available in Codex
  defaults, when the caller supplies the ChatGPT-first auth-ordering option,
  then the resolver selects ChatGPT auth if it exists.
- Given `auth_mode` declares one supported auth method in `${CODEX_HOME}/auth.json`,
  when fields for another supported auth method are also present, then
  `auth_mode` constrains the eligible auth method before
  `codex_auth_preference` ordering is applied.
- Given the caller supplies the ChatGPT-first auth-ordering option but ChatGPT
  auth is unavailable, when API-key/auth-token auth is available, then the
  resolver may fall back to API-key/auth-token auth unless a later spec adds a
  stricter "ChatGPT only" mode.
- Given a host uses ChatGPT/Codex backend auth, when provider
  construction occurs, then the host must choose an explicit provider/config
  path within the OpenAI adapter boundary rather than relying on
  workflow-package metadata.
- Given ChatGPT token auth is selected, when the provider chooses a default
  model-call endpoint, then it must use the ChatGPT/Codex backend endpoint
  shape documented by Codex analysis, not the public `https://api.openai.com/v1`
  default.
- Given personal-access-token auth is considered later, when implementation is
  planned, then bearer behavior and model-call base URL compatibility must be
  verified before support is enabled.
- Given agent-identity auth is considered later, when implementation is planned,
  then a signing provider must be designed; private-key or identity material
  must not be exposed as a bearer token.
- Given ChatGPT/Codex backend provider behavior is tested, when tests run, then
  they must use fake auth files and fake clients only, with no live ChatGPT,
  OpenAI, Codex backend, or network calls.

## Non-Goals

- No live OpenAI, ChatGPT, Codex backend, or network calls in unit tests.
- No support for repository-local or workflow-package endpoint overrides.
- No automatic migration or modification of `~/.codex/config.toml` or
  `~/.codex/auth.json`.
- No keyring-backed Codex auth support unless explicitly planned and tested
  later.
- No agent-identity signing provider in this feature's first slice.
- No ChatGPT token, personal-access-token, or agent-identity support through
  `OpenAIProviderConfig.api_key` or the default public OpenAI API-key provider
  path.
- No broad multi-provider router; this feature only improves the default
  OpenAI-compatible provider fallback.

## Design Constraints

- Discovery belongs to trusted host/runtime configuration, not generated package
  metadata.
- Caller-supplied adapters, providers, provider config, and auth values must
  remain higher precedence than ambient defaults.
- Parsing must use structured TOML and JSON APIs rather than ad hoc string
  matching when parsing credential-bearing data. The `openai_base_url` fallback
  parser may use a narrow line scan after full-file TOML parsing fails, but it
  must still parse the discovered value with `tomllib` and must stop at the
  first table header.
- The resolver should be independently unit-testable without importing the
  official OpenAI SDK or making network calls.
- Public API changes should be small and compatible with the existing
  `OpenAIProviderConfig` and default provider factory surface.
- Public OpenAI API auth and ChatGPT/Codex backend auth are separate provider
  modes inside the OpenAI auth/client boundary. The public OpenAI API-key path
  must not silently reuse ChatGPT session tokens, personal access tokens, or
  agent identity credentials.
- ChatGPT/Codex backend support must keep endpoint choice and credential choice
  coupled in one provider-scoped design so credentials are not sent to an
  incompatible or untrusted endpoint.
- When multiple supported Codex auth methods are available and `auth_mode` does
  not declare one method, resolver ordering must be explicit, deterministic,
  and caller-overridable.

## Proposed Integration Surface

This feature should integrate through `openai_client.py` rather than through a
new executor branch. Exact names may change during implementation, but the
internal shape should be equivalent to an adapter/default-provider resolver:

```python
from dynamic_agent_runner.openai_client import (
    OpenAIProviderConfig,
    resolve_default_openai_provider_config,
)

config = resolve_default_openai_provider_config(
    OpenAIProviderConfig(),
    discovery_enabled=True,
)
```

`create_default_openai_provider(...)` and
`create_default_async_openai_provider(...)` should call this resolver before
constructing SDK-backed providers. The resolver may stay private in the first
slice if tests cover the behavior through the adapter and default provider
factory helpers.

## Validation Checklist

- Add focused resolver tests in `tests/test_openai_client.py` or a new
  `tests/test_default_openai_auth.py`.
- Cover `OpenAIClientAdapter` lazy default-provider discovery when no client or
  provider is supplied.
- Cover `AsyncOpenAIClientAdapter` lazy default-provider discovery when no
  client or provider is supplied.
- Cover explicit caller precedence for `api_key` and `base_url`.
- Cover `OPENAI_API_KEY` environment behavior with monkeypatched environment.
- Cover `CODEX_HOME` resolution with temporary directories.
- Cover file-backed Codex API-key auth from fake `${CODEX_HOME}/auth.json`.
- Cover missing, malformed, and unsupported Codex auth modes.
- Cover explicit `auth_mode` precedence over conflicting credential fields.
- Cover no project-local config reads for endpoint/auth fallback.
- Cover unrelated Codex config parse incompatibilities without blocking auth
  discovery or a parseable top-level `openai_base_url`.
- Cover redaction or non-exposure of fake credential values in errors.
- Cover ChatGPT token selection without treating it as a public OpenAI API key.
- Cover the rejection path for personal-access-token and agent-identity auth so
  future changes cannot accidentally treat them as public OpenAI API keys.
- Run targeted tests:

```bash
poetry run pytest tests/test_openai_client.py -q
```

- Run final relevant validation:

```bash
poetry run pytest -q
poetry run ruff check src tests
```

## Open Questions

- Resolved for this implementation: default auth discovery is enabled by
  default only through the OpenAI adapter default-provider path and can be
  disabled with `OpenAIProviderConfig(discover_default_auth=False)`.
- Resolved for this implementation: `OPENAI_API_KEY` is copied into the resolved
  provider config when caller auth is absent; SDK-supported organization and
  project environment behavior is left intact.
- Resolved for this implementation: ChatGPT token auth is supported through an
  explicit ChatGPT/Codex backend provider path in `openai_client.py`;
  personal-access-token and agent-identity auth modes require dedicated
  provider/base-url/signing design before support.
- Resolved for this implementation: this feature reads existing OpenAI/Codex
  host state only and does not introduce package-owned auth/cache state.

## ChatGPT Auth Direction

Evaluation conclusion: support ChatGPT auth as an OpenAI auth pattern inside
`openai_client.py`, but do not add it by extending the current
`OpenAIProviderConfig(api_key=...)` path.

The public OpenAI API-key provider and the ChatGPT/Codex backend provider are
different auth and endpoint domains. The public OpenAI API uses API keys as
bearer credentials for `https://api.openai.com/v1`-style calls. Codex analysis
shows that ChatGPT token, ChatGPT auth token, personal-access-token, and
agent-identity modes select the ChatGPT/Codex backend default model-provider
endpoint, `https://chatgpt.com/backend-api/codex`, rather than the public
OpenAI API default.

Current support uses this shape:

1. Keep the public OpenAI API-key provider path limited to `OPENAI_API_KEY` and
   file-backed Codex API-key/auth-token auth.
2. Support ChatGPT tokens through an explicit provider boundary in
   `openai_client.py`, named by the current provider as `chatgpt-codex`.
3. If only one supported Codex auth method exists, use that method.
4. If API-key/auth-token auth and ChatGPT auth both exist, prefer
   API-key/auth-token auth by default.
5. Provide a caller option that reverses that ordering so ChatGPT auth is chosen
   when it exists.
6. Require trusted host-level Codex config for endpoint/provider selection;
   workflow package metadata must not enable this provider or redirect its
   endpoint.
7. Support file-backed Codex ChatGPT `tokens` before broader credential stores.
8. Treat personal access tokens as a later bearer-token backend slice only after
   endpoint and header behavior are verified.
9. Treat agent identity as a separate signing-provider feature, not a bearer
   token feature.
10. Preserve the no-live-network unit-test rule with fake auth files, fake
    clients, and secret-redaction assertions.

Supporting references:

- OpenAI public API authentication docs:
  `https://platform.openai.com/docs/api-reference/introduction`
- Codex auth and endpoint resolution analysis:
  `cline-tasks/codex-auth-endpoint-resolution-analysis.md`
