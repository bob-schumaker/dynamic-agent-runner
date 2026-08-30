# LiteLLM Provider Adapter Tasks

## Metadata

- Feature slug: `litellm-provider-adapter`
- Status: Slices L1-L3.2 TDD tasks complete; upstream dependency adopted and
  shim retired
- Date: 2026-08-22
- Owning spec: `specs/litellm-provider-adapter/spec.md`
- Plan: `specs/litellm-provider-adapter/plan.md`

## Slice L1: Core LiteLLM Direct SDK Transport

- [x] L1.1 Add RED tests in `tests/test_openai_client.py` for sync LiteLLM
      completion dispatch using an injected fake completion callable.
- [x] L1.2 Add RED tests for async LiteLLM completion dispatch using an injected
      fake async completion callable.
- [x] L1.3 Add RED tests proving `OpenAIModelRequest.messages` are translated to
      LiteLLM `messages`, request model remains authoritative, and factory
      `model` metadata does not override the request model.
- [x] L1.4 Add RED tests for supported tool descriptor translation and tool-call
      normalization from Chat Completions-style LiteLLM responses.
- [x] L1.5 Add RED tests proving unsupported request fields fail with
      `ModelExecutionError` before calling the fake LiteLLM dispatcher.
- [x] L1.6 Add RED tests for redacted LiteLLM error translation, including a
      token-shaped value in the fake provider exception.
- [x] L1.7 Add RED tests for public factory exports and explicit official
      OpenAI SDK compatibility factory behavior.
- [x] L1.8 Add the portable `litellm = "^1.97.0"` runtime dependency and refresh
      `poetry.lock` (resolved to 1.98.0).
- [x] L1.8a Verify the checked-in
      `vendor/wheels/litellm-1.92.0-py3-none-any.whl` is present, pure Python,
      and compatible with Python `<3.15`.
- [x] L1.8b Preserve the standard build-runner copy step that places the
      checked-in LiteLLM wheel in `dist/` before `python -m build`; retain OCI
      trigger coverage for the vendored wheel.
- [x] L1.8c Add the minimal bundled `dynamic_agent_runner.litellm` transport and
      make it the fallback when the full upstream package is unavailable
      (historical; retired by L1.22).
- [x] L1.9 Implement sync and async LiteLLM provider/client shims behind the
      existing provider protocols.
- [x] L1.10 Implement package-owned request translation from
      `OpenAIModelRequest` to LiteLLM Chat Completions kwargs.
- [x] L1.11 Implement Chat Completions response normalization into
      `ModelResponse`, including assistant text and model-emitted tool calls.
- [x] L1.12 Implement public LiteLLM factory helpers and package exports.
- [x] L1.13 Change ordinary default OpenAI-compatible provider construction to
      LiteLLM while preserving caller-injected clients/providers and the
      existing ChatGPT/Codex SDK backend.
- [x] L1.14 Add or preserve explicit official OpenAI SDK compatibility helpers.
- [x] L1.15 Update README/API docs only after public helper names are final.
- [x] L1.16 Assess PyInstaller impact. Add hook work only if existing package
      hook tests or build checks fail because of LiteLLM.
- [x] L1.17 Run focused validation:
      `poetry run pytest tests/test_openai_client.py -q`.
- [x] L1.18 Run executor validation:
      `poetry run pytest tests/test_executor.py -q`.
- [x] L1.19 Run final validation:
      `poetry run pytest -q` and `poetry run ruff check src tests`.
- [x] L1.20 Update this task list, `validation.md`, and the spec index with
      completion evidence after implementation.
- [x] L1.21 Run the standard package build under Python 3.13 and verify the OCI
      package tar contains both package wheels and the LiteLLM wheel hash
      matches the checked-in artifact.
- [x] L1.22 Retire `dynamic_agent_runner.litellm` after upstream LiteLLM gained
      Python 3.14 support: require the installed sync/async Chat Completions
      callables, add package-owned missing-transport errors, update docs, and
      verify `680 passed, 4 skipped`, Ruff, and the Sphinx HTML build.

## Deferred Follow-Up: ChatGPT/Codex Through LiteLLM

- [x] L2.1 Compare current `ChatGPTCodexBackendOpenAIClientProvider` request
      shaping with LiteLLM ChatGPT provider behavior; record the compatibility
      matrix and transport requirements in `l2-codex-compatibility.md`.
- [x] L2.2 Select LiteLLM Responses as the Codex transport, with
      `aresponses(...)` async-first and `responses(...)` sync parity; permit a
      Chat Completions bridge only behind explicit capability detection and
      fail-closed semantics. The public injected sync/async Responses adapter
      seam is implemented; default Codex-provider replacement remains deferred.
- [x] L2.3 Define explicit model alias behavior for unprefixed repository model
      ids and LiteLLM `chatgpt/` model ids without changing executor-facing
      model matching. Outbound normalization is implemented while adapter
      metadata retains the caller-facing model id.
- [x] L2.4 Define the auth/configuration handoff: DAR remains authoritative for
      token precedence, endpoint, account id, client-version model listing, and
      ambient-auth boundaries; LiteLLM may add only approved session/header
      defaults. Public sync/async auth-factory seams now resolve DAR auth before
      selecting ChatGPT Responses or ordinary LiteLLM transport.
- [x] L2.5 Add fake tests for token-limit stripping, metadata and instruction
      handling, generated-session policy, streamed text, Responses tool calls
      and follow-up transcript items, model-listing isolation, and secret
      redaction. The first parity slice covers instruction folding, preserved
      tool messages, stream/store defaults, and the existing redaction path;
      provider-specific token/session tests remain part of L2.6 validation.
- [x] L2.6 Wrap the SDK-backed ChatGPT/Codex provider only after the drift
      review is complete, with a rollback path to the existing provider when a
      required semantic contract is unsupported. Explicit sync/async auth
      factories now provide the opt-in wrapper; the global SDK-backed default
      remains unchanged.

## Deferred Follow-Up: Provider Breadth Polish

- [x] L3.1 [tests/implementation] Add caller-requested live-router model
      listing through the existing adapter discovery API.
  - Scope: only `litellm.Router.get_model_list(model_name=None, team_id=None)`
    on an explicitly supplied router. Convert nonblank deployment `model_name`
    values to the existing OpenAI-compatible catalog bridge; do not add a new
    public listing API or a generic provider catalog.
  - Files/components: `src/dynamic_agent_runner/litellm_client.py`,
    `tests/test_litellm_provider_adapter.py`, and these artifacts.
  - Contract: sync and async `create_*_litellm_adapter(..., router=...)`
    continue to expose listing only via `list_supported_models()` /
    `default_model()`. Explicit adapter `models` metadata remains authoritative
    except on `refresh=True`; discovery is lazy, cached, refreshable, deduped,
    and version-sorted by existing adapter behavior. An absent router method
    uses the existing unavailable-listing error; router exceptions use the
    existing listing-failure error.
  - Tests: fake-only sync/async router list success, cache and refresh,
    explicit-model bypass, malformed/empty values, missing method, and raised
    listing failure. No LiteLLM import, gateway, OAuth, network, or live model.
  - Exclusions: direct LiteLLM global or gateway catalogs, Codex listing/auth,
    aliases, executor routing, capability/status reporting, and manifest work.
  - Readiness: implementation-ready. This plan is ready to execute under its
    stated gates.
  - GREEN: `poetry run pytest tests/test_litellm_provider_adapter.py -q` — 48
    passed; combined with `tests/test_openai_client.py` — 134 passed; scoped
    Ruff passed. Final validation: `poetry run pytest -q` — 1592 passed, 1
    skipped, 6 deselected; targeted pre-commit passed. Council and Ponytail
    approved the delivered boundary.
- [x] L3.2 [tests/implementation] Add caller-requested LiteLLM Responses API
      dispatch outside Codex.
  - Scope: explicit generic `responses` / `aresponses` factory injection only.
    The existing generic Chat Completions route remains the default.
  - Contract: reuse the existing native Responses resource; forward ordinary
    provider config and DAR's Responses-shaped request unchanged. A direct
    completion/Responses callable pair is rejected before dispatch.
  - Tests: fake-only sync/async native dispatch, generic provider-config
    forwarding, Responses-only `parallel_tool_calls`, native normalization, and
    conflicting direct transport callables. Existing Chat and Codex regression
    tests remain the proof of unchanged default and Codex routes.
  - Exclusions: global LiteLLM Responses loading, Router Responses inference,
    Codex shaping/auth/aliases, executor changes, capability/status reporting,
    live provider calls, and new dependencies.
- [ ] L3.3 Add provider-specific capability/status reporting only after the
      default transport is stable.
  - Readiness: deferred. The generic OpenAI adapters expose only baseline
    `text_generation`; existing capability preflight consumes model coverage,
    not adapter capability metadata, and no host currently consumes a LiteLLM
    provider-status value.
  - Reopen only when a host names one admission, preflight, or execution
    decision; supplies the closed fields/states and their authority; and defines
    unknown, stale, failure, precedence, and no-network behavior. Prove that
    consumer outcome with fake sync/async inputs before adding adapter metadata.
  - Exclusions while deferred: static provider/transport labels, LiteLLM probes
    or catalogs, Router Responses inference, and a new generic status registry.
- [ ] L3.4 Add PyInstaller hooks only when a concrete freeze validation fails or
      a downstream frozen client requires them.
