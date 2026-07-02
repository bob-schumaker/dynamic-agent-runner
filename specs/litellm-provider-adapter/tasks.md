# LiteLLM Provider Adapter Tasks

## Metadata

- Feature slug: `litellm-provider-adapter`
- Status: implementation-ready TDD tasks for Slice L1
- Date: 2026-07-02
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
- [ ] L1.8 Publish or otherwise make the LiteLLM package available from the
      configured package source, then add a portable versioned runtime
      dependency and refresh `poetry.lock`. Current attempt is blocked because
      Artifactory has no matching LiteLLM release and a local file dependency
      emits a non-portable wheel URL.
- [x] L1.8a Verify the checked-in
      `vendor/wheels/litellm-1.92.0-py3-none-any.whl` is present, pure Python,
      and compatible with Python `<3.15`.
- [x] L1.8b Preserve the standard build-runner copy step that places the
      checked-in LiteLLM wheel in `dist/` before `python -m build`; retain OCI
      trigger coverage for the vendored wheel.
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

## Deferred Follow-Up: ChatGPT/Codex Through LiteLLM

- [ ] L2.1 Compare current `ChatGPTCodexBackendOpenAIClientProvider` request
      shaping with LiteLLM ChatGPT provider behavior.
- [ ] L2.2 Decide whether the Codex path should use `litellm.responses(...)`,
      `litellm.aresponses(...)`, or Chat Completions bridged to Responses.
- [ ] L2.3 Define explicit model alias behavior for unprefixed repository model
      ids and LiteLLM `chatgpt/` model ids.
- [ ] L2.4 Add fake tests for token-limit stripping, metadata handling,
      streaming behavior, model listing, and secret redaction.
- [ ] L2.5 Replace or wrap the SDK-backed ChatGPT/Codex provider only after the
      drift review is complete.

## Deferred Follow-Up: Provider Breadth Polish

- [ ] L3.1 Add live-router model listing only if a caller needs it.
- [ ] L3.2 Add LiteLLM Responses API dispatch only if a caller needs
      Responses-specific behavior outside Codex.
- [ ] L3.3 Add provider-specific capability/status reporting only after the
      default transport is stable.
- [ ] L3.4 Add PyInstaller hooks only when a concrete freeze validation fails or
      a downstream frozen client requires them.
