# LiteLLM-Only Codex Transport Implementation Plan

## Metadata

- Feature slug: `litellm-only-codex-transport`
- Status: postponed pending LiteLLM upstream support
- Owning spec: `spec.md`
- Tasks: `tasks.md`
- Validation record: `validation.md`
- Decision record: `decision-log.md`

## Objective

Replace the direct SDK ChatGPT/Codex execution path with LiteLLM Responses while
keeping credential resolution and catalog lookup inside DAR. The legacy path is
deleted only after the offline and opt-in live gates in the spec pass.

This plan is inactive while DAR retains the direct SDK ChatGPT/Codex transport.
Resume at M0 only after the re-entry condition in `spec.md` is met.

## Current State

- `create_default_openai_provider(...)` and its async counterpart resolve a
  ChatGPT token, then create direct SDK-backed Codex providers.
- `create_official_{,async}_openai_provider(...)` take the same direct SDK path
  for a resolved ChatGPT token.
- `LiteLLMCodexClientProvider` and its async counterpart already wrap injected
  `responses` / `aresponses` callables, accept a resolved token, and expose an
  optional `model_list` callable.
- DAR currently performs ChatGPT/Codex request rewriting in `openai_client.py`;
  LiteLLM also performs part of the rewriting. This must become one renderer.
- Existing model discovery depends on the current client's `models.list(...)`
  call and its `client_version` query. The LiteLLM Codex provider does not
  supply that catalog transport without an injected callable.

## Architecture and Ownership

```text
_resolve_default_openai_provider_defaults
  -> _ResolvedDefaultOpenAIProvider(config, redacted chatgpt_token)
  -> LiteLLM Codex provider
  -> canonical LiteLLM Codex renderer
  -> LiteLLM Responses callable

DAR-owned catalog callable
  -> authenticated HTTPS catalog request
  -> LiteLLMCodexClientProvider.model_list
  -> OpenAIClientAdapter list/default-model behavior
```

`_ResolvedDefaultOpenAIProvider` remains private in `openai_client.py`; do not
introduce a second resolver type or move Codex auth to generic OAuth code.

The installed LiteLLM `1.98.0` upstream transform is currently incompatible
with this architecture: it unconditionally invokes its own ChatGPT
authenticator, creates session/originator identity, and mutates instructions.
The factory cutover cannot start until an approved conforming upstream
version/configuration is pinned and proven at the transform boundary.

The private catalog callable must use an injected HTTPS collaborator. It must
send the resolved bearer token, optional account ID, and `client_version`; it
must not instantiate the official SDK or invoke LiteLLM credential discovery.
It has separate sync and async callables with URL, query, headers, and timeout
arguments; each calls `{base_url}/models` with a 10-second timeout, no redirect
or retry, and returns a decoded mapping. Non-2xx, >1 MiB, malformed JSON, and
non-mapping responses become redacted `ModelExecutionError` failures. Existing
DAR catalog filtering and ordering helpers retain semantic ownership.

The LiteLLM integration becomes the sole ChatGPT/Codex renderer. It receives
raw `OpenAIModelRequest` content and performs instruction folding and DAR
tool-loop transcript conversion. The adapter must no longer call
`_prepare_chatgpt_codex_request(...)`.

## Milestones

### M0: Prove LiteLLM transport feasibility

- Dependencies: none
- Deliverable: an offline, no-network probe against the exact lockfile-resolved
  LiteLLM artifact. It patches the upstream authenticator, filesystem writes,
  session-ID creation, HTTP, and device-login seams to fail and captures the
  transform with distinct DAR token/account sentinels.
- Exit criterion: a pinned upstream version/configuration proves that DAR input
  bypasses ambient auth, persistent/session identity, upstream instructions,
  and device login. Record version, artifact identity, classes/methods, and
  result in `validation.md`. The current `1.98.0` result is known blocking
  drift; do not rewire a factory.

### M1: Lock contracts with failing tests

- Dependencies: M0 and an approved dependency pin
- Deliverable: focused offline tests that describe resolver precedence, factory
  choice, renderer output, account conflict handling, catalog isolation, and
  error redaction.
- Exit criterion: existing resolver-regression tests pass; cutover, canonical
  renderer, and injected-catalog tests fail specifically because the direct SDK
  path or split renderer still exists. No external request occurs.

### M2: Route all ChatGPT/Codex execution through LiteLLM

- Dependencies: M1
- Deliverable: sync/async default and explicit official factories construct
  LiteLLM Codex providers; one canonical renderer is used.
- Exit criterion: focused unit suites pass and patched direct SDK constructors
  are never called for ChatGPT/Codex credentials.

### M3: Restore catalog parity without a second model client

- Dependencies: M1
- Deliverable: injected DAR-owned HTTPS catalog callable wired into sync and
  async LiteLLM Codex providers.
- Exit criterion: visible filtering, priority ordering, default selection,
  unavailable-model errors, and `client_version` forwarding pass offline.

### M4: Live cutover and cleanup

- Dependencies: M2, M3
- Deliverable: an opt-in, redacted live parity receipt in `validation.md`.
- Exit criterion: authenticated model execution uses only the DAR token and
  optional DAR account header; no ambient authenticator/session/originator
  identity is observed. Only then delete the direct SDK Codex providers.

## Work Packages

### WP1: Test contracts before rewiring

- Owner: runtime maintainer
- Touch points: `tests/test_openai_client.py`,
  `tests/test_litellm_provider_adapter.py`
- Depends on: M0
- Acceptance: existing resolver regressions stay green; changed factory,
  renderer, catalog, and redaction behaviors have focused RED tests, including
  both sync and async paths.
- Verification: focused pytest commands in `validation.md`.

### WP2: Default and official provider selection

- Owner: runtime maintainer
- Touch points: `src/dynamic_agent_runner/openai_client.py`,
  `src/dynamic_agent_runner/litellm_client.py`
- Depends on: WP1 and a conforming pinned provider-boundary result
- Acceptance: a resolved ChatGPT token selects LiteLLM for default and official
  factories; non-ChatGPT official factories preserve their explicit SDK role.
- Rollback: retain the direct providers until M4; revert factory selection if
  focused parity tests fail before deletion.

### WP3: Canonical LiteLLM Codex renderer and header policy

- Owner: runtime maintainer
- Touch points: `src/dynamic_agent_runner/openai_client.py`,
  `src/dynamic_agent_runner/litellm_client.py`
- Depends on: WP1 and a conforming pinned provider-boundary result
- Acceptance: final `responses` kwargs preserve instruction order, tool call
  IDs/names/arguments, tool outputs, `store=False`, stream behavior, model
  normalization, and the required identity-header policy.
- Rollback: restore the direct path if actual upstream transform behavior fails
  the provider-boundary gate.

### WP4: DAR-owned Codex catalog callable

- Owner: runtime maintainer
- Touch points: `src/dynamic_agent_runner/openai_client.py`,
  `src/dynamic_agent_runner/litellm_client.py`, focused tests
- Depends on: WP1
- Acceptance: catalog lookup uses injected HTTPS, not LiteLLM or official SDK;
  it preserves `client_version`, account header, catalog ordering/filtering, and
  redacted failures for both adapters.
- Rollback: do not delete the direct SDK provider while catalog parity is
  unproven.

### WP5: Cutover evidence and cleanup

- Owner: runtime maintainer with user authorization for live acceptance
- Touch points: direct provider classes, request helper call sites, tests,
  `validation.md`, optional public docs if factory behavior needs disclosure
- Depends on: WP2, WP3, WP4
- Acceptance: all offline gates pass; a manually authorized live run is
  recorded; direct provider classes and redundant renderer helpers are removed.
- Rollback: restore the direct provider selection from the immediately prior
  working commit if the live parity run fails.

## Risks and Gates

| Risk | Trigger | Mitigation | Blocks |
| --- | --- | --- | --- |
| LiteLLM invokes ambient auth | Provider transform calls its authenticator | Fail offline feasibility probe before factory changes | M0-M4 and deletion |
| LiteLLM emits identity/session headers | Final outbound header capture differs from spec | Fail offline feasibility probe before factory changes | M0-M4 and deletion |
| Split renderer loses tool-loop data | Final kwargs omit or alter transcript items | Test multi-turn `function_call` / `function_call_output` parity | M2 |
| Catalog regresses | Missing `client_version`, ordering, or account header | Inject and test a DAR catalog callable | M3 |
| Live behavior differs from fakes | Opt-in parity run fails | Keep legacy provider until an accepted redacted receipt exists | M4 and deletion |

## Validation Strategy

Run focused tests after each work package, then the full suite and Ruff before
the live gate. Do not run a live Codex request without an explicit user request
that authorizes the disposable-account acceptance run.

```bash
poetry run pytest tests/test_openai_client.py -q
poetry run pytest tests/test_litellm_provider_adapter.py -q
poetry run pytest -q
poetry run ruff check src tests
pre-commit run --files \
  specs/litellm-only-codex-transport/spec.md \
  specs/litellm-only-codex-transport/plan.md \
  specs/litellm-only-codex-transport/tasks.md \
  specs/litellm-only-codex-transport/validation.md \
  specs/litellm-only-codex-transport/decision-log.md
```

## Compatibility and Drift Policy

- Public adapter names and caller-injected client/provider behavior remain
  unchanged.
- Caller-injected clients/providers bypass default discovery. Caller-supplied
  LiteLLM identity options may not override DAR-resolved token, base URL,
  provider marker, authorization, or account values.
- The explicit official factories retain SDK behavior only for non-ChatGPT
  credentials; their ChatGPT behavior intentionally changes to LiteLLM.
- The approved LiteLLM release must be an exact dependency pin. Any dependency
  update reruns the M0 probe and the provider-boundary tests before merge.
- Any discovered need for LiteLLM session or originator identity is spec drift:
  stop and obtain approval before adding it.
- A failure of the live gate is blocking drift, not a reason to weaken or skip
  the gate.
- A failure of M0 is also blocking drift. Do not monkeypatch upstream private
  classes in production; obtain a dependency/configuration decision instead.
