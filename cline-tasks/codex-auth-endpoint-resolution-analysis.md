# Codex auth and endpoint resolution analysis

<!-- markdownlint-disable MD013 -->

## Goal

Capture how the locally installed Codex VS Code extension and the local Codex
source tree discover configured authentication material and API endpoints.

This note is intended as background for `dynamic-agent-runner`, especially for
future work around provider configuration, agent host integration, auth storage,
endpoint override safety, and compatibility with Codex-style execution
environments.

The investigation was read-only. I intentionally did not inspect or quote
secret-bearing credential values such as `~/.codex/auth.json`.

## Local context reviewed

Codex source tree:

- `/Users/roschuma/Repos/github/codex`

Installed VS Code extension:

- `/Users/roschuma/.vscode/extensions/openai.chatgpt-26.602.40724-darwin-arm64`

Especially relevant files:

- `/Users/roschuma/Repos/github/codex/codex-rs/utils/home-dir/src/lib.rs`
- `/Users/roschuma/Repos/github/codex/codex-rs/config/src/config_toml.rs`
- `/Users/roschuma/Repos/github/codex/codex-rs/config/src/loader/mod.rs`
- `/Users/roschuma/Repos/github/codex/codex-rs/login/src/auth/storage.rs`
- `/Users/roschuma/Repos/github/codex/codex-rs/login/src/auth/manager.rs`
- `/Users/roschuma/Repos/github/codex/codex-rs/model-provider-info/src/lib.rs`
- `/Users/roschuma/Repos/github/codex/codex-rs/model-provider/src/auth.rs`
- `/Users/roschuma/Repos/github/codex/codex-rs/core/src/config/mod.rs`
- `/Users/roschuma/.vscode/extensions/openai.chatgpt-26.602.40724-darwin-arm64/package.json`
- `/Users/roschuma/.vscode/extensions/openai.chatgpt-26.602.40724-darwin-arm64/out/extension.js`

## Executive summary

The VS Code extension does not appear to be the component that resolves auth
files or endpoint configuration. It is primarily a launcher/webview integration
around the Codex executable/app process. The extension has a development-only
setting for overriding the Codex CLI path, starts a Codex process during
activation, and communicates with it through the extension/webview machinery.

The Rust Codex code owns the actual resolution logic:

1. Resolve `CODEX_HOME`, defaulting to `~/.codex`.
2. Build a layered config stack from managed, system, cloud, user, profile,
   project, and runtime sources.
3. Deny project-local config the ability to redirect credentials or endpoints.
4. Load auth from environment, ephemeral external auth, access-token
   environment variables, or configured persistent storage.
5. Resolve the active model provider and endpoint from built-ins plus configured
   provider overrides.
6. Resolve request authentication from provider-specific auth first, then the
   shared Codex auth manager.

The practical default locations are:

```text
~/.codex/config.toml
~/.codex/auth.json
```

unless the launched Codex process has `CODEX_HOME` set.

## VS Code extension behavior

The installed extension package is:

```text
/Users/roschuma/.vscode/extensions/openai.chatgpt-26.602.40724-darwin-arm64
```

Its `package.json` identifies the extension as `Codex - OpenAI's coding agent`,
with bundled extension entrypoint:

```json
"main": "./out/extension.js"
```

The package includes a setting named `chatgpt.cliExecutable`:

```json
"chatgpt.cliExecutable": {
  "description": "DEVELOPMENT ONLY: Path to the Codex CLI executable. You do NOT need to set this unless you are actively developing the Codex CLI. If set this manually, parts of the extension may not work as expected.",
  "type": ["string", "null"],
  "default": null,
  "scope": "application",
  "restricted": true
}
```

I did not find VS Code settings for:

- `CODEX_HOME`
- `openai_base_url`
- `chatgpt_base_url`
- auth file path
- provider auth settings

The installed `out/extension.js` is bundled and minified, but the activation
path clearly constructs a Codex process wrapper and calls:

```text
startCodexProcess()
```

The same bundled file also contains the LSP MCP helper integration. It resolves
a Codex executable and constructs a command equivalent to:

```text
codex --config mcp_servers.codex-lsp-mcp={...}
```

for the local LSP MCP socket bridge.

The important conclusion is that VS Code delegates the auth and endpoint
question to the Codex process it launches. If that process inherits the normal
environment, it follows the same `CODEX_HOME` and config/auth behavior as the
CLI. If `chatgpt.cliExecutable` points at a different binary during
development, that alternate binary owns the resolution behavior.

## `CODEX_HOME` resolution

`codex-rs/utils/home-dir/src/lib.rs` contains the home directory resolver.

The behavior is:

1. If environment variable `CODEX_HOME` is present and non-empty, use it.
2. Otherwise use the user's home directory plus `.codex`.

When `CODEX_HOME` is explicitly set, Codex verifies that the path exists, is a
directory, and canonicalizes it. When `CODEX_HOME` is not set, Codex simply
constructs the default `~/.codex` path.

This is the root for user-level config and file-backed auth:

```text
${CODEX_HOME}/config.toml
${CODEX_HOME}/auth.json
${CODEX_HOME}/<profile>.config.toml
```

## Config sources and precedence

`codex-rs/config/src/loader/mod.rs` documents and implements the config stack.
Configuration is built from multiple layers in this order:

```text
admin
system
cloud
user
profile
cwd
tree
repo
runtime
```

The documented locations include:

- admin: macOS managed preferences
- system: `/etc/codex/config.toml` on Unix or
  `%ProgramData%\OpenAI\Codex\config.toml` on Windows
- cloud: enterprise-managed cloud config bundle fragments
- user: `${CODEX_HOME}/config.toml`
- profile: `${CODEX_HOME}/<name>.config.toml`, when selected
- cwd: `${PWD}/config.toml`, disabled when the directory is untrusted
- tree: parent directories looking for `./.codex/config.toml`, disabled when
  untrusted
- repo: `$(git rev-parse --show-toplevel)/.codex/config.toml`, disabled when
  untrusted
- runtime: `--config` flags and model selector overrides

Runtime `--config` values are parsed as a config layer as well. Relative paths
from runtime overrides are resolved against either the current working directory
or `codex_home`, depending on the field.

### Project-local config denylist

Codex treats repository-local config as untrusted because it comes from checked
out repository contents. The loader has an explicit denylist for project-local
config. It includes:

```text
openai_base_url
chatgpt_base_url
apps_mcp_product_sku
model_provider
model_providers
notify
profile
profiles
experimental_realtime_ws_base_url
otel
```

The comment in the source explains the reason: repository contents should not
get to choose where a user's credentials are sent or which local commands are
run.

This is one of the most important design points for `dynamic-agent-runner`.
Endpoint and provider selection are security-sensitive, not just convenience
configuration. If a generated agent package is loaded from a repo, the runner
should not automatically trust that package to decide where user credentials are
sent.

## Top-level Codex config fields relevant to auth and endpoints

`codex-rs/config/src/config_toml.rs` defines the TOML shape for user-facing
config.

Relevant fields include:

```rust
model_provider: Option<String>
forced_chatgpt_workspace_id: Option<String>
forced_login_method: Option<String>
cli_auth_credentials_store: Option<AuthCredentialsStoreMode>
mcp_servers: HashMap<String, McpServerConfig>
mcp_oauth: HashMap<String, McpOAuthConfig>
model_providers: HashMap<String, ModelProviderInfo>
chatgpt_base_url: Option<String>
openai_base_url: Option<String>
```

The two most direct endpoint knobs are:

```toml
openai_base_url = "..."
chatgpt_base_url = "..."
```

Provider-specific configuration lives under `model_providers` and uses
`ModelProviderInfo`, which supports fields such as:

- `base_url`
- `env_key`
- `env_key_instructions`
- `experimental_bearer_token`
- command-backed `auth`
- `aws`
- `wire_api`
- `query_params`
- `http_headers`
- `env_http_headers`
- retry and timeout settings
- `requires_openai_auth`

## Built-in provider endpoint resolution

`codex-rs/core/src/config/mod.rs` takes the parsed top-level config and builds
the active provider map.

The important sequence is:

1. Read `cfg.openai_base_url`.
2. Drop it if it is empty.
3. Build built-in model providers with that optional OpenAI base URL.
4. Merge configured `model_providers` into the built-ins.
5. Select `model_provider` from runtime/model selector, config, or default
   `"openai"`.

The built-in OpenAI provider is created in
`codex-rs/model-provider-info/src/lib.rs`.

OpenAI provider defaults:

- base URL: configured `openai_base_url`, if present; otherwise provider-level
  default later
- wire API: Responses
- static headers include an OpenAI beta/version header
- environment-driven headers:
  - `OpenAI-Organization` from `OPENAI_ORGANIZATION`
  - `OpenAI-Project` from `OPENAI_PROJECT`
- `requires_openai_auth = true`
- supports websockets

Built-in provider IDs include:

- `openai`
- `amazon-bedrock`
- `ollama`
- `lmstudio`

Configured providers can extend the provider map. The merge code generally does
not allow arbitrary overriding of built-in providers, with limited special
handling for Amazon Bedrock AWS settings.

### Default base URL depends on auth mode

`ModelProviderInfo::to_api_provider(auth_mode)` decides the final base URL when
the provider did not explicitly set one.

If auth mode is one of:

- ChatGPT
- ChatGPT auth tokens
- Agent identity
- Personal access token

then the default model-provider base URL is:

```text
https://chatgpt.com/backend-api/codex
```

Otherwise, the default base URL is:

```text
https://api.openai.com/v1
```

This means Codex's default endpoint is not just a provider property. It is also
conditioned by the active auth mode. API-key style auth points at the public
OpenAI API default, while ChatGPT/Codex-backend auth points at the ChatGPT Codex
backend default.

## `chatgpt_base_url` versus model provider base URL

There are two related but distinct ChatGPT URLs:

```text
https://chatgpt.com/backend-api/
https://chatgpt.com/backend-api/codex
```

`chatgpt_base_url` is the backend base URL used by auth/account/backend-facing
logic. In core config it defaults to:

```text
https://chatgpt.com/backend-api/
```

The model provider default for Codex backend model calls is:

```text
https://chatgpt.com/backend-api/codex
```

The auth manager has its own constant:

```text
https://chatgpt.com/backend-api
```

and trims trailing slashes when building some account/auth URLs.

This distinction matters when debugging endpoint behavior. A configured
`chatgpt_base_url` affects ChatGPT backend/auth flows. A configured provider
`base_url` or `openai_base_url` affects model-provider request routing.

## Auth storage shape

`codex-rs/login/src/auth/storage.rs` defines `AuthDotJson`, the file-backed auth
structure for:

```text
${CODEX_HOME}/auth.json
```

The structure can contain:

```rust
auth_mode
OPENAI_API_KEY
tokens
last_refresh
agent_identity
personal_access_token
```

The storage module:

- reads `${CODEX_HOME}/auth.json`
- parses it as JSON
- writes pretty JSON
- creates the parent directory when needed
- writes with Unix file mode `0600` on Unix

I did not read local secret values from the installed `auth.json`.

## Auth manager load order

`codex-rs/login/src/auth/manager.rs` owns the main auth resolution logic.

The private `load_auth(...)` helper takes:

- `codex_home`
- `enable_codex_api_key_env`
- `auth_credentials_store_mode`
- optional `chatgpt_base_url`

The surrounding `AuthManager` stores additional auth state and policy such as:

- optional `forced_chatgpt_workspace_id`
- optional external auth provider
- cached auth snapshots and explicit reload behavior

The load order is:

1. If `enable_codex_api_key_env` is true and `CODEX_API_KEY` is set, use it as
   API key auth.
2. Check ephemeral external auth storage, which supports externally supplied
   ChatGPT auth tokens.
3. If `CODEX_ACCESS_TOKEN` is set, classify it as either:
   - personal access token, or
   - agent identity JWT
4. If auth store mode is `Ephemeral`, stop without persistent fallback.
5. Otherwise load from the configured persistent store.

Persistent storage is controlled by `cli_auth_credentials_store`. Supported
modes include file/keyring/auto-style behavior in the surrounding code. The
file-backed path is `${CODEX_HOME}/auth.json`.

The manager loads auth once and caches it. External changes to `auth.json` are
not observed until the manager reloads.

## Auth mode interpretation

When loading from `auth.json`, `CodexAuth::from_auth_dot_json(...)` resolves the
mode and then selects the matching credential material:

- `ApiKey` requires `OPENAI_API_KEY` in the auth file.
- `AgentIdentity` requires `agent_identity` and uses the ChatGPT backend URL to
  validate/resolve identity material.
- `PersonalAccessToken` requires `personal_access_token`.
- ChatGPT auth requires `tokens`.

The auth manager can report whether an auth mode uses the Codex backend. These
backend modes include:

- ChatGPT
- ChatGPT auth tokens
- Agent identity
- Personal access token

API-key auth does not use the Codex backend by default.

## Environment variables observed in the auth/provider path

Auth manager environment variables:

- `CODEX_API_KEY`
- `CODEX_ACCESS_TOKEN`
- `OPENAI_API_KEY`

Provider/header environment variables:

- provider-specific `env_key`, if configured
- `OPENAI_ORGANIZATION`
- `OPENAI_PROJECT`

Open-source/local provider helper environment variables:

- `CODEX_OSS_PORT`
- `CODEX_OSS_BASE_URL`

Important nuance: `OPENAI_API_KEY` appears in the auth-file structure and helper
code, but the main early environment override path is `CODEX_API_KEY` when that
feature is enabled by the caller. Provider-specific `env_key` can independently
read arbitrary environment variables for configured providers.

## Provider auth resolution

`codex-rs/model-provider/src/auth.rs` resolves auth for a concrete provider.

There are two adjacent steps:

1. `auth_manager_for_provider(...)` selects a provider-scoped auth manager when
   command-backed provider auth is configured. Providers without command-backed
   auth keep using the caller-supplied shared auth manager.
2. `resolve_provider_auth(...)` builds the request auth provider from either a
   provider-specific bearer credential or the current shared `CodexAuth`.

Within `resolve_provider_auth(...)`, the order is:

1. If the provider has an API key from `provider.api_key()`, use bearer auth
   from that provider-specific key.
2. If the provider has `experimental_bearer_token`, use it.
3. Otherwise use the shared `CodexAuth`, when present.
4. If no auth is available, return an unauthenticated auth provider.

The `requires_openai_auth` provider flag is important, but it is not enforced
inside `resolve_provider_auth(...)`; surrounding account/login paths use it to
decide whether OpenAI/ChatGPT auth is required.

For shared `CodexAuth`:

- API key, ChatGPT tokens, ChatGPT auth tokens, and personal access tokens are
  converted to bearer auth.
- Agent identity does not simply expose a bearer token. It signs agent-task auth
  headers.

This split is a good model: provider-specific auth should win over ambient
process auth, while ambient auth remains available for default providers.

## Safety model

The most interesting safety property is not a single API. It is the layered
boundary:

- User/system/cloud/runtime config can define endpoints and providers.
- Project-local config can define safe project-level behavior.
- Project-local config cannot redirect endpoint/provider/auth-sensitive fields.
- Provider auth can be explicit and provider-scoped.
- Shared auth is loaded from a controlled home directory or environment.

This avoids a common agent-host failure mode: checking out a repo that contains
configuration which silently exfiltrates user auth to a malicious base URL.

## Implications for `dynamic-agent-runner`

### 1. Separate trusted host config from package config

Generated agent packages should not be allowed to decide where user credentials
are sent. The runner should distinguish:

- package-declared provider requirements
- host-approved provider bindings
- host-owned auth sources
- runtime overrides from an explicitly trusted caller

A package can say "I need an OpenAI-compatible provider with tool calling".
The host should decide "that maps to provider X, base URL Y, auth source Z".

### 2. Treat endpoint selection as security-sensitive

Endpoint values should live in a trusted layer, not in arbitrary package
metadata. If package metadata includes suggested endpoints, they should be
treated as documentation or untrusted hints until explicitly approved.

### 3. Use provider-scoped auth before ambient auth

Codex's provider auth order is useful:

1. provider-specific credential
2. provider-specific bearer token
3. shared host auth
4. unauthenticated only when allowed

`dynamic-agent-runner` can use the same shape for OpenAI-compatible providers,
local models, MCP providers, and future hosted backends.

### 4. Keep `HOME`-style state explicit

Codex has a single `CODEX_HOME`. A runner could similarly have a
`DYNAMIC_AGENT_RUNNER_HOME` or an explicit host state directory. That makes it
easier to reason about:

- config files
- auth files
- caches
- cloud/managed policy bundles
- machine-local provider bindings

### 5. Preserve a denylist or allowlist for package-local config

If `dynamic-agent-runner` grows package-local config overlays, use an allowlist
or denylist similar to Codex. Endpoint, auth, command execution, notification,
and telemetry settings should not be package-controlled by default.

### 6. Distinguish backend auth URLs from model-call URLs

Codex has both `chatgpt_base_url` and provider `base_url`/`openai_base_url`.
That distinction is worth keeping:

- auth/account/control-plane base URL
- model inference/data-plane base URL

Those values may be the same for simple providers, but the configuration model
should not require them to be the same.

### 7. Make auth cache behavior visible

Codex caches loaded auth and requires reload to observe external file changes.
If `dynamic-agent-runner` caches auth, document it and provide an explicit
reload path. Silent stale auth is hard to debug.

## Debugging checklist for installed Codex endpoint/auth behavior

When debugging what local Codex will use:

1. Check whether the VS Code setting `chatgpt.cliExecutable` is set.
2. Check whether the Codex process has `CODEX_HOME` set.
3. Inspect `${CODEX_HOME}/config.toml` for:
   - `openai_base_url`
   - `chatgpt_base_url`
   - `model_provider`
   - `[model_providers.*]`
   - `cli_auth_credentials_store`
   - `forced_login_method`
   - `forced_chatgpt_workspace_id`
4. Check trusted runtime flags, especially `--config`.
5. Check relevant environment variables:
   - `CODEX_API_KEY`
   - `CODEX_ACCESS_TOKEN`
   - `OPENAI_API_KEY`
   - provider-specific env vars
   - `OPENAI_ORGANIZATION`
   - `OPENAI_PROJECT`
6. Determine active auth mode:
   - API key
   - ChatGPT tokens
   - personal access token
   - agent identity
7. Determine active provider:
   - explicit runtime model/provider selection
   - configured `model_provider`
   - default `openai`
8. Resolve final model endpoint:
   - provider `base_url`, if set
   - `openai_base_url` for built-in OpenAI provider
   - ChatGPT Codex backend default for ChatGPT/PAT/agent identity modes
   - OpenAI API default for API-key mode

## Key source references

Source paths and relevant responsibilities:

- `codex-rs/utils/home-dir/src/lib.rs`
  - resolves `CODEX_HOME`
  - defaults to `~/.codex`
- `codex-rs/config/src/config_toml.rs`
  - defines user-facing TOML config shape
  - includes `openai_base_url`, `chatgpt_base_url`, `model_provider`,
    `model_providers`, and auth-store fields
- `codex-rs/config/src/loader/mod.rs`
  - builds layered config stack
  - applies project-local denylist
- `codex-rs/login/src/auth/storage.rs`
  - defines `${CODEX_HOME}/auth.json`
  - reads/writes auth JSON
- `codex-rs/login/src/auth/manager.rs`
  - loads auth from env, ephemeral external auth, access tokens, and persistent
    storage
  - caches auth and supports reload
- `codex-rs/model-provider-info/src/lib.rs`
  - defines provider metadata
  - defines built-in providers
  - selects default base URL based on auth mode
- `codex-rs/model-provider/src/auth.rs`
  - resolves provider-specific auth versus shared Codex auth
- `codex-rs/core/src/config/mod.rs`
  - wires parsed config into active provider map and final `chatgpt_base_url`
- VS Code extension `package.json`
  - defines `chatgpt.cliExecutable`
  - does not expose auth/endpoint settings
- VS Code extension `out/extension.js`
  - bundled/minified activation code starts Codex process with
    `startCodexProcess()`
  - builds Codex CLI command snippets for LSP MCP integration

## Design takeaway

Codex treats auth and endpoints as host-owned concerns, not project-owned
concerns. It still allows rich provider customization, but only from trusted
layers or explicit runtime inputs. That is the central design lesson for
`dynamic-agent-runner`: generated packages should declare capabilities and
requirements, while the host decides which credentials and endpoints satisfy
them.
