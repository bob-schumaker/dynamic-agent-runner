# LiteLLM-Only Codex Transport Validation

## Metadata

- Feature slug: `litellm-only-codex-transport`
- Status: postponed; implementation must not start before upstream support
- Spec: `spec.md`
- Plan: `plan.md`
- Tasks: `tasks.md`

## Commands

| Command | Result | Notes |
| --- | --- | --- |
| `pre-commit run rumdl --files specs/litellm-only-codex-transport/spec.md specs/litellm-only-codex-transport/plan.md specs/litellm-only-codex-transport/tasks.md specs/litellm-only-codex-transport/validation.md specs/litellm-only-codex-transport/decision-log.md specs/README.md` | pass | 2026-09-05 readiness review. |
| `poetry run pytest tests/test_openai_client.py -q` | not run | T001, T002, T005-T007, T009. |
| `poetry run pytest tests/test_litellm_provider_adapter.py -q` | not run | T002-T004, T006, T008, T010-T011. |
| `poetry run pytest -q` | not run | Required before live acceptance. |
| `poetry run ruff check src tests` | not run | Required before live acceptance. |

## Traceability Matrix

| Requirement | Task(s) | Test/Check | Result |
| --- | --- | --- | --- |
| Transport feasibility gate | T000, P3 | exact-artifact offline probe | blocked on LiteLLM 1.98.0 |
| FR-1 resolver ownership and precedence | T001, T006, T007 | focused OpenAI-client tests | not run |
| FR-2 LiteLLM factory selection | T002, T007 | patched SDK-constructor tests | not run |
| FR-3 renderer, conflicts, auth, and headers | T002-T004, T008, T010-T011 | factory/final-callable/transform tests | not run |
| FR-4 catalog and redaction | T005-T006, T009 | injected HTTPS catalog tests | not run |
| FR-5 legacy-path removal | T014 | source/export/factory search plus regression suite | not run |
| FR-6 offline and live gates | T000, T006, T010-T013 | command results and redacted receipt | blocked |

## Contract Conformance

The implementation validation gates are inactive. The Feasibility Receipt is
preserved as the required re-entry evidence for any future revival.

- Credential discovery: not run; preserve DAR's existing precedence and secret
  redaction.
- Model execution: not run; LiteLLM must be the only ChatGPT/Codex request path.
- Model catalog: not run; DAR private HTTPS callable only.
- Header policy: blocked; bearer plus optional account ID only, with
  case-insensitive rejection of conflicting caller identity options.
- MCP OAuth: out of scope; no shared credential lifecycle changes allowed.

## Live Acceptance Gate

This is a manual, opt-in acceptance. Do not run it from CI or without explicit
user authorization. Before running, add the exact disposable-account command,
environment prerequisites, redaction plan, and expected checks here. Record no
token, account ID, raw headers, or raw model output.

Required receipt facts:

- resolved credential source and selected provider, without secret values;
- catalog listing result and visible/default-model outcome;
- text completion result classification;
- function-call and matching tool-result follow-up classification;
- confirmation that no unauthorized ambient auth/session/originator identity
  was observed; and
- date, LiteLLM version, command exit status, and reviewer acceptance.

The receipt must also name expected visible model IDs/default, verify each tool
call/result correlation, state request-count cap and timeout, classify any
non-secret failure, and include reviewer pass/fail signoff.

## Feasibility Receipt

- Date: 2026-09-05
- Lockfile-resolved package: LiteLLM `1.98.0`; `pyproject.toml` currently
  permits `^1.97.0`, so it is not a runtime pin.
- Inspected upstream boundary: `ChatGPTResponsesAPIConfig.__init__`,
  `validate_environment`, and `transform_responses_api_request`; the ChatGPT
  `Authenticator` and default-header/instruction helpers.
- Result: blocked. The transform constructs/calls its authenticator, obtains
  ambient token/account values, creates session/originator identity, and adds
  upstream instructions despite DAR token/header input. Its authenticator can
  read/write state, refresh, and invoke device login.
- Upstream-release research: blocked. The current upstream `main` source still
  constructs the authenticator, calls `get_access_token()` and
  `get_account_id()`, creates a session ID, and prepends default instructions.
  No conforming released or current-main configuration was identified.
- Required next evidence: P3 selects a version/configuration, then T000 records
  a passing no-network probe against that exact package artifact.

## Out-of-Scope Check

- No login, refresh, account picker, or Codex credential writes.
- No generic OAuth refactor or MCP OAuth behavior change.
- No workflow schema, executor-routing, or generic-provider change.
- No live network access in unit tests.

## Residual Risks

| Risk | Owner | Gate or follow-up |
| --- | --- | --- |
| LiteLLM upstream transform changes | runtime maintainer | exact-version probe, transform tests, and live receipt |
| Required unknown identity header | user and runtime maintainer | spec amendment before cutover |
| Catalog protocol differs from current client | runtime maintainer | T005/T008 and live receipt |
