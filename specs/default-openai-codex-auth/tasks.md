# Default OpenAI/Codex Auth Discovery Task List

Status: implemented; Slices 1-6 complete

## Prerequisites

- Spec: `specs/default-openai-codex-auth/spec.md`
- Plan: `specs/default-openai-codex-auth/plan.md`
- Supporting analysis:
  `cline-tasks/codex-auth-endpoint-resolution-analysis.md`

## Scope Rule

Keep this change limited to the OpenAI adapter/default-provider path. Do not add
executor-owned auth discovery, workflow-package auth settings, project-local
endpoint overlays, live network calls, keyring-backed Codex auth, or unsupported
Codex auth modes.

Follow-on rule: ChatGPT token, personal-access-token, and agent-identity support
must not be added by treating those credentials as `OpenAIProviderConfig.api_key`
values. ChatGPT support is implemented through an explicit ChatGPT/Codex backend
provider path in `openai_client.py`; personal-access-token and agent-identity
support remain deferred until separately specified.

## Slice 1 — Resolver Contract and Caller Precedence

- [x] T1.1 [tests] Add RED tests for default-provider resolver precedence.
  - Spec: FR-1, FR-2, FR-3, FR-9
  - Plan: Resolver Flow; Planning Decisions
  - Files/components: `tests/test_default_openai_auth.py`,
    `src/dynamic_agent_runner/openai_client.py`
  - Cases:
    - explicit `api_key` prevents ambient auth discovery
    - explicit `base_url` prevents endpoint replacement
    - explicit `api_key` plus missing `base_url` does not trigger auth discovery
    - resolver returns a new config without mutating caller input
    - provider config representation does not expose fake API keys
  - Validation:
    `poetry run pytest tests/test_default_openai_auth.py
    tests/test_openai_client.py -q`
  - Expected RED: resolver and opt-out/precedence behavior do not exist yet.
  - RED: targeted tests failed during collection with
    `ImportError: cannot import name '_resolve_default_openai_provider_config'`
    before the resolver existed.
  - GREEN: targeted tests passed with `38 passed in 0.17s`.

- [x] T1.2 [implementation] Add provider-config discovery controls and resolver
      skeleton.
  - Spec: FR-1, FR-2, FR-8, FR-9
  - Plan: Planning Decisions; Resolver Flow; Error Contract
  - Files/components: `src/dynamic_agent_runner/openai_client.py`
  - Depends on: T1.1
  - Required behavior:
    - add opt-out control to `OpenAIProviderConfig`
    - avoid exposing `api_key` in ordinary representation
    - return caller overrides unchanged
    - keep resolver independently testable
  - Validation:
    `poetry run pytest tests/test_default_openai_auth.py
    tests/test_openai_client.py -q`
  - GREEN: targeted tests passed with `38 passed in 0.17s`.

- [x] T1.3 [tests] Add RED tests for OpenAI environment fallback behavior.
  - Spec: FR-3, FR-9
  - Plan: Resolver Flow; Planning Decisions
  - Files/components: `tests/test_default_openai_auth.py`,
    `src/dynamic_agent_runner/openai_client.py`
  - Cases:
    - `OPENAI_API_KEY` is honored when no overriding auth is supplied
    - `OPENAI_ORGANIZATION` and `OPENAI_PROJECT` SDK behavior is not blocked
    - absence of OpenAI env vars proceeds to Codex discovery
  - Validation:
    `poetry run pytest tests/test_default_openai_auth.py
    tests/test_openai_client.py -q`
  - Expected RED: resolver does not yet make OpenAI env behavior explicit.
  - RED: covered by the missing-resolver failure in T1.1 before implementation.
  - GREEN: targeted tests passed with `38 passed in 0.17s`.

- [x] T1.4 [implementation] Implement OpenAI environment fallback semantics.
  - Spec: FR-3, FR-9
  - Plan: Resolver Flow
  - Files/components: `src/dynamic_agent_runner/openai_client.py`
  - Depends on: T1.3
  - Validation:
    `poetry run pytest tests/test_default_openai_auth.py
    tests/test_openai_client.py -q`
  - GREEN: targeted tests passed with `38 passed in 0.17s`.

## Slice 2 — Codex Home, Config, and API-Key Auth

- [x] T2.1 [tests] Add RED tests for `CODEX_HOME` resolution.
  - Spec: FR-4, FR-9
  - Plan: Resolver Flow; Error Contract
  - Files/components: `tests/test_default_openai_auth.py`,
    `src/dynamic_agent_runner/openai_client.py`
  - Cases:
    - non-empty `CODEX_HOME` is used
    - empty or missing `CODEX_HOME` falls back to `~/.codex`
    - missing or non-directory `CODEX_HOME` follows the documented policy
    - discovered file paths stay under Codex home
  - Validation:
    `poetry run pytest tests/test_default_openai_auth.py
    tests/test_openai_client.py -q`
  - Expected RED: Codex home resolution does not exist yet.
  - RED: targeted tests failed because Codex home resolution and auth/config
    parsing were not implemented.
  - GREEN: targeted tests passed with `52 passed in 0.21s`.

- [x] T2.2 [implementation] Implement Codex home resolution helpers.
  - Spec: FR-4, FR-9
  - Plan: Resolver Flow; Error Contract
  - Files/components: `src/dynamic_agent_runner/openai_client.py`
  - Depends on: T2.1
  - Validation:
    `poetry run pytest tests/test_default_openai_auth.py
    tests/test_openai_client.py -q`
  - GREEN: targeted tests passed with `52 passed in 0.21s`.

- [x] T2.3 [tests] Add RED tests for trusted Codex user config endpoint
      discovery.
  - Spec: FR-5, FR-9
  - Plan: Resolver Flow; Planning Decisions
  - Files/components: `tests/test_default_openai_auth.py`,
    `src/dynamic_agent_runner/openai_client.py`
  - Cases:
    - `${CODEX_HOME}/config.toml` `openai_base_url` fills missing `base_url`
    - caller `base_url` wins over Codex config
    - malformed `openai_base_url` fails without exposing secrets
    - unrelated Codex config TOML incompatibilities do not block auth discovery
      or a parseable top-level `openai_base_url`
    - package-local `.codex/config.toml` and `config.toml` are not read
  - Validation:
    `poetry run pytest tests/test_default_openai_auth.py
    tests/test_openai_client.py -q`
  - Expected RED: Codex config parsing does not exist yet.
  - RED: targeted tests failed because Codex config parsing was not implemented.
  - GREEN: targeted tests passed with `52 passed in 0.21s`.

- [x] T2.4 [implementation] Implement trusted Codex user config parsing.
  - Spec: FR-5, FR-9
  - Plan: Resolver Flow; Error Contract
  - Files/components: `src/dynamic_agent_runner/openai_client.py`
  - Depends on: T2.3
  - Validation:
    `poetry run pytest tests/test_default_openai_auth.py
    tests/test_openai_client.py -q`
  - GREEN: targeted tests passed with `52 passed in 0.21s`.

- [x] T2.5 [tests] Add RED tests for file-backed Codex API-key auth.
  - Spec: FR-6, FR-7, FR-9
  - Plan: Resolver Flow; Planning Decisions; Error Contract
  - Files/components: `tests/test_default_openai_auth.py`,
    `src/dynamic_agent_runner/openai_client.py`
  - Cases:
    - API-key `auth.json` fills missing `api_key`
    - caller `api_key` wins over Codex auth
    - absent `auth.json` is not an error
    - malformed `auth.json` fails without exposing credential fields
    - ChatGPT token, personal access token, and agent identity modes are
      explicitly unsupported in the first slice
  - Validation:
    `poetry run pytest tests/test_default_openai_auth.py
    tests/test_openai_client.py -q`
  - Expected RED: Codex auth parsing does not exist yet.
  - RED: targeted tests failed because Codex auth parsing and unsupported-mode
    handling were not implemented.
  - GREEN: targeted tests passed with `52 passed in 0.21s`.

- [x] T2.6 [implementation] Implement file-backed Codex API-key auth parsing
      and unsupported-mode handling.
  - Spec: FR-6, FR-7, FR-9
  - Plan: Resolver Flow; Error Contract; Non-Implementation Notes
  - Files/components: `src/dynamic_agent_runner/openai_client.py`
  - Depends on: T2.5
  - Validation:
    `poetry run pytest tests/test_default_openai_auth.py
    tests/test_openai_client.py -q`
  - GREEN: targeted tests passed with `52 passed in 0.21s`.

## Slice 3 — Adapter Integration, Opt-Out, and Regression

- [x] T3.1 [tests] Add RED tests for default provider factory integration.
  - Spec: FR-1, FR-2, FR-8
  - Plan: Default Provider Integration
  - Files/components: `tests/test_openai_client.py`,
    `src/dynamic_agent_runner/openai_client.py`
  - Cases:
    - `create_default_openai_provider(...)` resolves default auth/config before
      SDK-backed provider construction
    - `create_default_async_openai_provider(...)` uses the same resolver
    - `discover_default_auth=False` bypasses ambient discovery
  - Validation:
    `poetry run pytest tests/test_openai_client.py -q`
  - Expected RED: default provider factories do not call the resolver yet.
  - RED: not observed separately because Slice 1 had already wired the resolver
    into default provider factories.
  - GREEN: focused Slice 3 validation passed with `36 passed in 0.20s`.

- [x] T3.2 [implementation] Wire resolver into sync and async default provider
      factories.
  - Spec: FR-1, FR-2, FR-8
  - Plan: Default Provider Integration
  - Files/components: `src/dynamic_agent_runner/openai_client.py`
  - Depends on: T3.1
  - Validation:
    `poetry run pytest tests/test_openai_client.py -q`
  - GREEN: behavior was already present from Slice 1 resolver wiring; focused
    Slice 3 validation passed with `36 passed in 0.20s`.

- [x] T3.3 [tests] Add RED tests for adapter lazy default-provider discovery.
  - Spec: FR-1, FR-2, FR-8
  - Plan: Default Provider Integration
  - Files/components: `tests/test_openai_client.py`,
    `src/dynamic_agent_runner/openai_client.py`
  - Cases:
    - `OpenAIClientAdapter` with no client/provider triggers discovered default
      provider construction lazily
    - `AsyncOpenAIClientAdapter` with no client/provider triggers the same
      discovered default provider path lazily
    - injected client/provider paths do not run discovery
  - Validation:
    `poetry run pytest tests/test_openai_client.py -q`
  - Expected RED: adapter lazy path does not yet observe resolver behavior.
  - RED: not observed separately because Slice 1 default-provider wiring already
    made the adapter lazy path use resolved provider config.
  - GREEN: focused Slice 3 validation passed with `36 passed in 0.20s`.

- [x] T3.4 [implementation] Ensure adapter lazy default-provider paths use the
      resolved default provider behavior.
  - Spec: FR-1, FR-2
  - Plan: Default Provider Integration
  - Files/components: `src/dynamic_agent_runner/openai_client.py`
  - Depends on: T3.3
  - Validation:
    `poetry run pytest tests/test_openai_client.py -q`
  - GREEN: behavior was already present from Slice 1 resolver wiring; focused
    Slice 3 validation passed with `36 passed in 0.20s`.

- [x] T3.5 [tests] Add augmented default OpenAI adapter regression coverage.
  - Spec: FR-1, FR-2, FR-8
  - Plan: Current Repository State; Default Provider Integration
  - Files/components: `tests/test_executor.py`,
    `src/dynamic_agent_runner/executor.py`,
    `src/dynamic_agent_runner/openai_client.py`
  - Cases:
    - augmented coverage-created default adapter reaches the same discovered
      default-provider behavior
    - strict coverage with no matching adapter does not create a default
      discovered provider
  - Validation:
    `poetry run pytest tests/test_executor.py -q`
  - Expected RED: existing executor tests do not prove discovery integration.
  - RED: not observed separately because default-provider wiring was already in
    place before the regression assertion was added.
  - GREEN: focused Slice 3 validation passed with `36 passed in 0.20s`.
  - Note: full `poetry run pytest tests/test_executor.py -q` currently fails in
    unrelated token-budget tests because tiktoken attempts to fetch encoding data
    from `openaipublic.blob.core.windows.net` in this network-restricted
    environment.

- [x] T3.6 [implementation] Preserve executor behavior while relying on adapter
      default-provider integration.
  - Spec: FR-1, FR-2, FR-8
  - Plan: Default Provider Integration; Non-Implementation Notes
  - Files/components: `src/dynamic_agent_runner/executor.py`,
    `src/dynamic_agent_runner/openai_client.py`
  - Depends on: T3.5
  - Validation:
    `poetry run pytest tests/test_executor.py tests/test_openai_client.py -q`
  - GREEN: no executor implementation change was needed; focused Slice 3
    validation passed with `36 passed in 0.20s`.

## Slice 4 — Documentation, Spec Maintenance, and Final Validation

- [x] T4.1 [docs] Document default OpenAI/Codex auth discovery.
  - Spec: Objective, FR-2, FR-8, FR-9
  - Plan: Affected Areas
  - Files/components: `README.md`
  - Depends on: T3.6
  - Required documentation:
    - discovery only applies to the OpenAI adapter default-provider path
    - explicit `api_key` and `base_url` precedence
    - `CODEX_HOME` and supported Codex API-key auth fallback
    - non-API-key Codex auth unsupported in this slice
    - opt-out behavior
  - Validation:
    `poetry run pytest tests/test_openai_client.py tests/test_executor.py -q`
  - GREEN: README documents default OpenAI adapter discovery, precedence,
    Codex user-level config/auth sources, unsupported non-API-key Codex modes,
    and opt-out behavior. Focused Slice 4 validation passed with
    `60 passed in 0.25s`.

- [x] T4.2 [validation] Run focused feature regression validation.
  - Spec: Validation Checklist
  - Plan: Validation Plan
  - Files/components: implementation and docs changed in Slices 1-4
  - Depends on: T4.1
  - Validation:
    `poetry run pytest tests/test_default_openai_auth.py
    tests/test_openai_client.py tests/test_executor.py -q`
  - GREEN: focused feature regression validation passed with
    `60 passed in 0.25s` using the feature test files, the augmented/strict
    executor regressions, and the default-adapter concurrency regression.

- [x] T4.3 [validation] Run final repository validation.
  - Spec: Validation Checklist
  - Plan: Validation Plan
  - Files/components: implementation and docs changed in Slices 1-4
  - Depends on: T4.2
  - Validation:
    - `poetry run pytest -q`
    - `poetry run ruff check src tests`
  - RESULT: `poetry run ruff check src tests` passed.
  - RESULT: `poetry run pytest -q` was run in the network-restricted
    environment and reported `13 failed, 340 passed in 1.26s`. The relevant
    feature isolation issue in the default-adapter concurrency test was fixed;
    remaining failures are outside this feature's focused coverage, including
    tiktoken attempts to fetch encoding data from
    `openaipublic.blob.core.windows.net` and unrelated tracing expectation
    mismatches.

- [x] T4.4 [spec-maintenance] Record implementation evidence and update status.
  - Spec: Metadata, Authority and Continuation, Validation Checklist
  - Plan: Validation Plan
  - Files/components: `specs/default-openai-codex-auth/spec.md`,
    `specs/default-openai-codex-auth/plan.md`,
    `specs/default-openai-codex-auth/tasks.md`, `specs/README.md`
  - Depends on: T4.3
  - Validation: `pre-commit run --files <changed files>`
  - GREEN: feature spec, plan, task list, and spec index updated with
    implemented status and validation evidence.

## Slice 5 — Ordered ChatGPT/Codex Backend Auth Support

Status: implemented

- [x] T5.1 [spec] Finalize the explicit ChatGPT/Codex backend auth contract.
  - Spec: FR-7, FR-10
  - Plan: ChatGPT/Codex Backend Provider Shape
  - Files/components: `specs/default-openai-codex-auth/spec.md`,
    `src/dynamic_agent_runner/openai_client.py`
  - Required decisions:
    - provider name and public API surface
    - exact placement within `openai_client.py`
    - `OpenAIProviderConfig` option name for auth ordering, expected shape:
      API-key/auth-token first by default, ChatGPT first when requested
    - whether ChatGPT-first means "prefer ChatGPT if present, otherwise
      fallback" or whether a later stricter ChatGPT-only mode is needed
    - endpoint default and `chatgpt_base_url` handling
    - secret-redaction and trace behavior
  - Validation: spec review only; no code changes.
  - GREEN: contract finalized in spec/plan artifacts with
    `codex_auth_preference="chatgpt_first"` as the caller ordering option.

- [x] T5.2 [tests] Add RED tests for ordered supported Codex auth selection.
  - Spec: FR-7, FR-10
  - Plan: Resolver Flow; ChatGPT/Codex Backend Provider Shape
  - Files/components: `tests/test_default_openai_auth.py`,
    `src/dynamic_agent_runner/openai_client.py`
  - Cases:
    - only API-key/auth-token auth exists, so API-key/auth-token auth is used
    - only ChatGPT `tokens` auth exists, so ChatGPT/Codex backend auth is used
    - both API-key/auth-token auth and ChatGPT auth exist, so
      API-key/auth-token auth wins by default
    - both auth methods exist and ChatGPT-first ordering is selected, so
      ChatGPT auth wins
    - ChatGPT-first ordering is selected but ChatGPT auth is absent, so
      API-key/auth-token auth may be used unless a stricter ChatGPT-only mode is
      later specified
    - ChatGPT `tokens` are never passed as `OpenAIProviderConfig.api_key`
    - unsupported-mode errors do not expose token material
  - Validation:
    `poetry run pytest tests/test_default_openai_auth.py -q`
  - RED: focused auth tests failed before implementation because ChatGPT auth
    was still unsupported and `OpenAIProviderConfig.codex_auth_preference` did
    not exist.
  - GREEN: focused Slice 5 validation passed with `67 passed in 0.32s`.

- [x] T5.3 [implementation] Add the explicit ChatGPT/Codex backend provider
      boundary in `openai_client.py`.
  - Spec: FR-10
  - Plan: ChatGPT/Codex Backend Provider Shape
  - Files/components: `src/dynamic_agent_runner/openai_client.py`, tests,
    README
  - Required behavior:
    - ChatGPT auth selected when it is the only supported Codex auth method
    - API-key/auth-token auth selected before ChatGPT auth by default when both
      exist
    - ChatGPT-first option selects ChatGPT auth when it exists
    - ChatGPT token material is never copied into `OpenAIProviderConfig.api_key`
    - ChatGPT auth selects the ChatGPT/Codex backend endpoint path
    - no workflow-package or project-local endpoint/auth selection
    - endpoint and auth mode resolved together
    - fake-client unit tests only
    - no live ChatGPT, OpenAI, Codex backend, or network calls
  - Validation:
    `poetry run pytest tests/test_default_openai_auth.py
    tests/test_openai_client.py -q`
  - GREEN: `poetry run pytest tests/test_default_openai_auth.py
    tests/test_openai_client.py -q` passed with `60 passed in 0.21s`.
  - GREEN: `poetry run ruff check src/dynamic_agent_runner/openai_client.py
    tests/test_default_openai_auth.py tests/test_openai_client.py` passed.

- [x] T5.4 [tests] Add adapter and augmented-default regression coverage.
  - Spec: FR-10
  - Plan: ChatGPT/Codex Backend Provider Shape
  - Files/components: `tests/test_openai_client.py`, `tests/test_executor.py`,
    `src/dynamic_agent_runner/openai_client.py`
  - Cases:
    - sync and async default providers construct the ChatGPT/Codex backend
      provider when ordered selection chooses ChatGPT auth
    - augmented default OpenAI adapter uses the same ordered selection
    - strict supplied-adapter behavior still does not create a default provider
  - Depends on: T5.2, T5.3
  - Validation:
    - focused fake-client provider tests
    - current default OpenAI auth discovery regression tests
    - `poetry run ruff check src tests`
  - GREEN: focused Slice 5 validation passed with `67 passed in 0.32s`.
  - GREEN: `poetry run ruff check src tests/test_default_openai_auth.py
    tests/test_openai_client.py tests/test_executor.py` passed.

- [x] T5.5 [docs] Document ChatGPT/Codex backend provider opt-in and boundaries.
  - Spec: FR-7, FR-10
  - Plan: ChatGPT/Codex Backend Provider Shape
  - Files/components: `README.md`, provider spec artifacts
  - Required documentation:
    - ChatGPT auth is an OpenAI auth pattern but not public OpenAI API-key auth
    - if only one supported Codex auth method exists, that method is used
    - default ordering is API-key/auth-token auth before ChatGPT auth
    - caller option can prefer ChatGPT auth when it exists
    - supported and unsupported credential modes
    - endpoint trust boundary
    - no project-local endpoint redirection
  - Validation: `pre-commit run --files <changed files>`
  - GREEN: README documents ordered Codex auth selection, ChatGPT backend auth,
    `codex_auth_preference="chatgpt_first"`, and endpoint trust boundaries.

## Slice 6 — Current-State Spec Alignment and Auth-Mode Maintenance

Status: implemented

- [x] T6.1 [tests] Add regression tests for tolerant Codex config parsing.
  - Spec: FR-5, FR-9
  - Plan: Resolver Flow; Planning Decisions
  - Files/components: `tests/test_default_openai_auth.py`,
    `src/dynamic_agent_runner/openai_client.py`
  - Cases:
    - unrelated Codex config TOML incompatibility under a later table does not
      block auth discovery
    - top-level `openai_base_url` is still read when later config content is not
      compatible with Python `tomllib`
    - malformed top-level `openai_base_url` still fails without exposing secret
      values
  - Validation:
    `poetry run pytest tests/test_default_openai_auth.py -q`
  - GREEN: targeted tests passed with `28 passed in 0.15s` before the later
    auth-mode regressions were added.
  - Commit: `86c287c fix(openai): tolerate unrelated codex config parse issues`.

- [x] T6.2 [implementation] Tolerate unrelated Codex config parse issues while
      preserving strict parsing for `openai_base_url`.
  - Spec: FR-5, FR-9
  - Plan: Resolver Flow; Planning Decisions
  - Files/components: `src/dynamic_agent_runner/openai_client.py`
  - Required behavior:
    - use full-file `tomllib` parsing when possible
    - if full-file parsing fails, scan only top-level lines before the first
      table header for the exact `openai_base_url` key
    - parse the discovered `openai_base_url` line with `tomllib`
    - keep malformed `openai_base_url` errors non-secret
  - Validation:
    - `poetry run pytest tests/test_default_openai_auth.py -q`
    - `poetry run ruff check src/dynamic_agent_runner/openai_client.py
      tests/test_default_openai_auth.py`
    - smoke check against the real `/Users/roschuma/.codex/config.toml`
    - `pre-commit run --files src/dynamic_agent_runner/openai_client.py
      tests/test_default_openai_auth.py`
  - GREEN: all targeted checks passed before commit
    `86c287c fix(openai): tolerate unrelated codex config parse issues`.

- [x] T6.3 [implementation] Treat explicit Codex `auth_mode` as authoritative.
  - Spec: FR-6, FR-7, FR-10
  - Plan: Resolver Flow; ChatGPT/Codex Backend Provider Shape
  - Files/components: `src/dynamic_agent_runner/openai_client.py`
  - Required behavior:
    - normalize declared `auth_mode` independently from inferred auth mode
    - when `auth_mode` resolves to `api_key`, only API-key auth is eligible
    - when `auth_mode` resolves to `chatgpt`, only ChatGPT token auth is
      eligible
    - when `auth_mode` resolves to an unsupported mode, report unsupported auth
      without exposing credential material
    - when `auth_mode` is absent, preserve availability-based auth inference and
      `codex_auth_preference` ordering
  - Validation:
    - `poetry run pytest tests/test_default_openai_auth.py -q`
    - `poetry run ruff check src/dynamic_agent_runner/openai_client.py
      tests/test_default_openai_auth.py`
    - `pre-commit run --files src/dynamic_agent_runner/openai_client.py
      tests/test_default_openai_auth.py`
  - GREEN: focused tests passed with `31 passed in 0.16s`.
  - Commit: `f50262f fix(openai): honor declared codex auth mode`.

- [x] T6.4 [tests] Cover declared Codex `auth_mode` precedence.
  - Spec: FR-6, FR-7, FR-10
  - Plan: Resolver Flow; ChatGPT/Codex Backend Provider Shape
  - Files/components: `tests/test_default_openai_auth.py`
  - Cases:
    - `auth_mode="chatgpt"` wins over an `OPENAI_API_KEY` field in the same
      file
    - `auth_mode="api_key"` wins over
      `codex_auth_preference="chatgpt_first"` when ChatGPT token fields are also
      present
    - `auth_mode="chatgpt"` with no usable token fails without falling through
      to an API-key field or exposing secret values
  - Validation:
    - `poetry run pytest tests/test_default_openai_auth.py -q`
    - `poetry run ruff check src/dynamic_agent_runner/openai_client.py
      tests/test_default_openai_auth.py`
    - `pre-commit run --files src/dynamic_agent_runner/openai_client.py
      tests/test_default_openai_auth.py`
  - GREEN: focused tests passed with `31 passed in 0.16s`.
  - Commit: `1764bc2 test(openai): cover declared codex auth mode`.

- [x] T6.5 [spec-maintenance] Refresh spec artifacts for current repo state.
  - Spec: Metadata, FR-5, FR-6, FR-7, FR-10, Validation Checklist
  - Plan: Planning Decisions; Resolver Flow; Affected Areas
  - Files/components: `specs/default-openai-codex-auth/spec.md`,
    `specs/default-openai-codex-auth/plan.md`,
    `specs/default-openai-codex-auth/tasks.md`
  - Required updates:
    - record Slice 6 completion
    - make ChatGPT/Codex backend support current-state language, not future-only
      language
    - document tolerant top-level `openai_base_url` parsing after unrelated
      Codex config parse failures
    - document `auth_mode` as authoritative before auth ordering
  - Validation:
    - `poetry run pytest tests/test_default_openai_auth.py -q`
    - `pre-commit run --files specs/default-openai-codex-auth/spec.md
      specs/default-openai-codex-auth/plan.md
      specs/default-openai-codex-auth/tasks.md`
  - GREEN: focused auth tests passed with `31 passed in 0.17s`.
  - GREEN: pre-commit passed on the refreshed spec artifacts.
