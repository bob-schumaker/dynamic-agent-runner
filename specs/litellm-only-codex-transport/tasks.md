# LiteLLM-Only Codex Transport Tasks

## Metadata

- Feature slug: `litellm-only-codex-transport`
- Status: postponed pending LiteLLM upstream support
- Spec: `spec.md`
- Plan: `plan.md`
- Validation: `validation.md`

## Prerequisites

All tasks are inactive until the specification's re-entry condition is met.

- [ ] P1 Preserve unrelated working-tree changes before coding.
- [ ] P2 Read the spec, plan, and task list before the first source edit. This
      task list does not authorize the live gate.
- [ ] P3 Approve either a pinned conforming LiteLLM version/configuration or a
      specification amendment. Do not ship a private upstream monkeypatch.

## M0: Upstream feasibility gate

- [ ] T000 [probe] Against the exact lockfile-resolved LiteLLM artifact, run an
      offline no-network probe that replaces its `Authenticator`, filesystem
      writes, session-ID creation, HTTP, and device-login seams with failures.
      Capture transform headers/body using distinct DAR token/account sentinels.
  - Spec: Transport Feasibility Gate, FR-3, FR-6
  - Depends on: P1, P2
  - Validation: record version, package artifact identity, upstream
    class/method names, and result in `validation.md`.
  - Evidence: current `1.98.0` is expected to block; a passing result is
    required after P3 before source edits or factory tests.

## M1: RED contract tests

- [ ] T001 [tests] Add resolver-regression tests in `tests/test_openai_client.py`
      for explicit key, environment key, Codex API-key, ChatGPT-only cache,
      preference, malformed cache, unsupported mode, and repr redaction.
  - Spec: FR-1, FR-6
  - Depends on: P3, T000
  - Validation: `poetry run pytest tests/test_openai_client.py -q`
  - Evidence: precedence remains green; sentinels never appear in errors,
    representations, or captured logs.

- [ ] T002 [tests] Add default and explicit-official sync/async factory tests
      that inject a ChatGPT cache and fake LiteLLM Responses callable, patch
      `openai.OpenAI` / `openai.AsyncOpenAI` to fail, and capture final kwargs.
      Patch discovery to fail for caller-injected client/provider paths.
  - Spec: FR-2, FR-3
  - Depends on: T001
  - Validation: both focused suites
  - Evidence: RED before cutover because factories select direct SDK; local
    renderer tests are regression coverage, not cutover evidence.

- [ ] T003 [tests] Add canonical-renderer regressions for raw
      `OpenAIModelRequest`: instruction ordering, existing instructions, model
      normalization, `store`, stream behavior, and multi-turn matching
      `function_call` / `function_call_output` ID, name, and arguments.
  - Spec: FR-3
  - Depends on: T001
  - Validation: `poetry run pytest tests/test_litellm_provider_adapter.py -q`
  - Evidence: renderer receives raw DAR markers before generic `to_kwargs()`
    conversion and is the sole producer of Responses transcript items.

- [ ] T004 [tests] Add sync/async identity-conflict tests for case-insensitive
      `api_key`, `api_base`, `custom_llm_provider`, `Authorization`, and
      `ChatGPT-Account-ID`, covering absent and matching resolved values.
  - Spec: FR-3, FR-6
  - Depends on: T003
  - Validation: LiteLLM-adapter focused suite
  - Evidence: conflicts raise package-owned redacted errors.

- [ ] T005 [tests] Define and test sync and async injected catalog transports:
      `GET {base_url}/models`, exact `client_version`, 10-second timeout, no
      redirect/retry, bearer/account headers, mapping response, and no LiteLLM
      or official SDK call. Cover non-2xx, >1 MiB, malformed JSON, and
      non-mapping response failures.
  - Spec: FR-4, FR-6
  - Depends on: T001
  - Validation: OpenAI-client focused suite
  - Evidence: existing helpers preserve filtering, priority, default and
    unavailable-model semantics with redacted failures.

- [ ] T006 [tests] Add a sentinel-token redaction matrix across resolver
      repr/error/logging, LiteLLM execution failure, and catalog failure for
      sync and async paths.
  - Spec: FR-1, FR-4, FR-6
  - Depends on: T001, T004, T005
  - Validation: both focused suites
  - Evidence: token, authorization/account values, raw body, and secret query
    values are absent from surfaced failures and logs.

## M2: GREEN LiteLLM-only execution

- [ ] T007 [implementation] Reuse `_ResolvedDefaultOpenAIProvider` in
      `openai_client.py` to route resolved ChatGPT credentials to LiteLLM Codex
      providers from default and explicit official sync/async factories.
  - Spec: FR-1, FR-2
  - Depends on: T002, T000, P3
  - Validation: OpenAI-client focused suite
  - Evidence: T002 passes; non-ChatGPT official tests remain unchanged.

- [ ] T008 [implementation] Make `litellm_client.py` the canonical
      ChatGPT/Codex renderer. Preserve raw DAR messages, then remove adapter
      pre-rendering only after T003/T004 pass.
  - Spec: FR-3, FR-5
  - Depends on: T003, T004, T007
  - Validation: LiteLLM-adapter focused suite
  - Evidence: final kwargs satisfy T002-T004 for sync and async.

- [ ] T009 [implementation] Add private sync and async injected HTTPS Codex
      catalog transports in `openai_client.py` and wire them as `model_list`.
  - Spec: FR-4
  - Depends on: T005, T006, T007
  - Validation: OpenAI-client focused suite
  - Evidence: T005/T006 pass without official SDK or LiteLLM catalog discovery.

- [ ] T010 [tests] Against the approved pinned LiteLLM version, retain
      provider-transform interception tests that prove ambient authentication,
      device login, session/originator identity, and upstream instruction
      mutation remain absent after integration wiring.
  - Spec: FR-3, FR-6
  - Depends on: T000, P3, T008
  - Validation: LiteLLM-adapter focused suite
  - Evidence: provider-boundary gate passes offline.

- [ ] T011 [tests] Capture final outbound identity headers through the approved
      provider transform and prove header allowlist, account collision,
      instruction ordering, and tool-transcript parity.
  - Spec: FR-3, FR-6
  - Depends on: T010
  - Validation: LiteLLM-adapter focused suite
  - Evidence: only DAR bearer auth and optional DAR account are present.

## M3: Offline evidence, live gate, and cleanup

- [ ] T012 [validation] Run focused tests, full suite, Ruff, changed-file
      pre-commit, and `git diff --check`; record exact output in validation.
  - Spec: FR-6
  - Depends on: T007-T011

- [ ] T013 [manual gate] Obtain explicit user authorization, then run the
      disposable-account live parity acceptance. Record expected model/default,
      tool-call/output correlation, request cap, timeout, failure taxonomy, and
      reviewer signoff, all redacted.
  - Spec: FR-6
  - Depends on: T012

- [ ] T014 [implementation] After T013 acceptance, remove direct SDK Codex
      providers and `_prepare_chatgpt_codex_request(...)`; update public docs
      only if documented behavior changes.
  - Spec: FR-5
  - Depends on: T013
  - Validation: all focused/full/lint/pre-commit/diff checks rerun
  - Evidence: source plus exports/imports and all four factory branches contain
    no direct SDK Codex path.

## Checkpoints

- M0: approved exact upstream version/configuration has passed; otherwise block.
- M1: resolver regressions green and changed behavior has RED tests.
- M2: fake-only execution/catalog parity green; direct SDK remains rollback.
- M3: accepted live receipt permits direct-provider cleanup.
