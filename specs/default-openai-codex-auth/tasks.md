# Default OpenAI/Codex Auth Discovery Task List

Status: active implementation; Slices 1-2 complete

## Prerequisites

- Spec: `specs/default-openai-codex-auth/spec.md`
- Plan: `specs/default-openai-codex-auth/plan.md`
- Supporting analysis:
  `cline-tasks/codex-auth-endpoint-resolution-analysis.md`

## Scope Rule

Keep this change limited to the OpenAI adapter/default-provider path. Do not add
executor-owned auth discovery, workflow-package auth settings, project-local
endpoint overlays, live network calls, keyring-backed Codex auth, or non-API-key
Codex backend auth support.

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
    - malformed Codex TOML fails without exposing secrets
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

- [ ] T3.1 [tests] Add RED tests for default provider factory integration.
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

- [ ] T3.2 [implementation] Wire resolver into sync and async default provider
      factories.
  - Spec: FR-1, FR-2, FR-8
  - Plan: Default Provider Integration
  - Files/components: `src/dynamic_agent_runner/openai_client.py`
  - Depends on: T3.1
  - Validation:
    `poetry run pytest tests/test_openai_client.py -q`

- [ ] T3.3 [tests] Add RED tests for adapter lazy default-provider discovery.
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

- [ ] T3.4 [implementation] Ensure adapter lazy default-provider paths use the
      resolved default provider behavior.
  - Spec: FR-1, FR-2
  - Plan: Default Provider Integration
  - Files/components: `src/dynamic_agent_runner/openai_client.py`
  - Depends on: T3.3
  - Validation:
    `poetry run pytest tests/test_openai_client.py -q`

- [ ] T3.5 [tests] Add augmented default OpenAI adapter regression coverage.
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

- [ ] T3.6 [implementation] Preserve executor behavior while relying on adapter
      default-provider integration.
  - Spec: FR-1, FR-2, FR-8
  - Plan: Default Provider Integration; Non-Implementation Notes
  - Files/components: `src/dynamic_agent_runner/executor.py`,
    `src/dynamic_agent_runner/openai_client.py`
  - Depends on: T3.5
  - Validation:
    `poetry run pytest tests/test_executor.py tests/test_openai_client.py -q`

## Slice 4 — Documentation, Spec Maintenance, and Final Validation

- [ ] T4.1 [docs] Document default OpenAI/Codex auth discovery.
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

- [ ] T4.2 [validation] Run focused feature regression validation.
  - Spec: Validation Checklist
  - Plan: Validation Plan
  - Files/components: implementation and docs changed in Slices 1-4
  - Depends on: T4.1
  - Validation:
    `poetry run pytest tests/test_default_openai_auth.py
    tests/test_openai_client.py tests/test_executor.py -q`

- [ ] T4.3 [validation] Run final repository validation.
  - Spec: Validation Checklist
  - Plan: Validation Plan
  - Files/components: implementation and docs changed in Slices 1-4
  - Depends on: T4.2
  - Validation:
    - `poetry run pytest -q`
    - `poetry run ruff check src tests`

- [ ] T4.4 [spec-maintenance] Record implementation evidence and update status.
  - Spec: Metadata, Authority and Continuation, Validation Checklist
  - Plan: Validation Plan
  - Files/components: `specs/default-openai-codex-auth/spec.md`,
    `specs/default-openai-codex-auth/plan.md`,
    `specs/default-openai-codex-auth/tasks.md`, `specs/README.md`
  - Depends on: T4.3
  - Validation: `pre-commit run --files <changed files>`
