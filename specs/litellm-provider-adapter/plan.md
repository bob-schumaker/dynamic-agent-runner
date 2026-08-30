# LiteLLM Provider Adapter Implementation Plan

## Metadata

- Feature slug: `litellm-provider-adapter`
- Status: Slices L1-L3.2 implementation plan; implementation complete
- Date: 2026-08-22
- Owning spec: `specs/litellm-provider-adapter/spec.md`

## Scope

Slice L1 makes LiteLLM the
default direct SDK transport for ordinary OpenAI-format chat-completions
dispatch while preserving the existing repository-owned adapter boundary.

Slice L1 originally did not implement LiteLLM Responses API dispatch,
ChatGPT/Codex helper replacement, live LiteLLM gateway calls, LiteLLM-managed
OAuth, live model listing, or workflow manifest schema changes. L3.2 adds only
an explicit caller-supplied generic Responses callable; all other exclusions
remain in force.

## L2 Codex Follow-Up Boundary

The L2.1 audit requires the Codex follow-up to use LiteLLM's Responses surface:
`aresponses(...)` is the async-first path and `responses(...)` provides sync
parity. DAR remains authoritative for Codex auth discovery and precedence,
resolved endpoint, account-id forwarding, client-version model listing, model
aliases, error normalization, and ambient-auth boundaries. L2 must explicitly
test LiteLLM session/default-instruction additions, streamed text, Responses
tool calls and follow-up transcript items, token-limit handling, and secret
redaction before replacing the SDK-backed provider. Chat Completions bridging
is only a capability-gated fallback and is not Codex-equivalent.

## Current Architecture Fit

The implementation should stay in `src/dynamic_agent_runner/openai_client.py`
unless the file becomes unwieldy during implementation. The existing seams are
already the right ones:

- `OpenAIModelRequest` remains the internal model-request contract.
- `ModelResponse` remains the executor-facing normalized response.
- `OpenAIClientAdapter` and `AsyncOpenAIClientAdapter` remain executor-facing.
- `OpenAIClientProvider` and `AsyncOpenAIClientProvider` remain the provider
  factory boundary.
- `create_default_openai_provider(...)` and
  `create_default_async_openai_provider(...)` remain the default construction
  points.

The main implementation challenge is translation: current request construction
is Responses-shaped, while Slice L1 dispatches through LiteLLM's
Chat Completions-shaped `completion(...)` / `acompletion(...)` APIs.

## Technical Approach

1. Make the required OpenAI-compatible transport available in every DAR install
   through the upstream LiteLLM dependency. The dependency constraint is
   `^1.97.0` and the resolved release is 1.98.0; the bundled fallback is retired.
2. Add small sync/async LiteLLM provider classes or client shims that satisfy
   the existing provider protocols.
3. Add package-owned request translation from `OpenAIModelRequest` to LiteLLM
   Chat Completions kwargs:
   - `messages` come from `OpenAIModelRequest.messages`
   - request model is authoritative
   - tool descriptors are converted only when compatible
   - unsupported fields fail with `ModelExecutionError`
   - caller-provided LiteLLM kwargs are merged deliberately, without overriding
     request-critical fields silently
4. Add package-owned Chat Completions response normalization into
   `ModelResponse`, including assistant text and tool calls.
5. Add public sync/async factory helpers and package exports.
6. Change ordinary default OpenAI-compatible provider construction to use
   LiteLLM, while retaining an explicit official OpenAI SDK compatibility
   provider/factory.
7. Preserve the existing SDK-backed ChatGPT/Codex backend provider until a
   dedicated follow-up slice handles LiteLLM Responses semantics for Codex.
8. Add focused fake tests before implementation behavior is completed.
9. Update README/API docs only after helper names are final.
10. Retire the legacy OCI checked-in wheel, copy step, and trigger separately;
    this is not required for the upstream dependency and shim-retirement slice.

## Public API Direction

Candidate public factories:

- `create_litellm_adapter(...)`
- `create_async_litellm_adapter(...)`
- `create_litellm_adapter_from_provider_config(...)`
- `create_async_litellm_adapter_from_provider_config(...)`
- explicit official SDK compatibility helpers, named so they cannot be confused
  with the default LiteLLM-backed path

If implementation discovers cleaner names that match existing local patterns,
update the spec before finalizing docs.

## Key Decisions

- Factory `model` values must not override `OpenAIModelRequest.model` in Slice
  L1.
- Explicit `models` metadata remains the model-selection mechanism; live
  LiteLLM/router model listing is deferred.
- ChatGPT/Codex auth discovery remains repository-owned and in
  `openai_client.py`.
- The existing ChatGPT/Codex SDK backend remains valid in Slice L1.
- PyInstaller hook work is deferred unless adding LiteLLM breaks existing hook
  validation.
- Unit tests must use fake LiteLLM callables, fake routers, or monkeypatched
  modules; no live provider, gateway, OAuth, or network calls.
- L3.1 uses only a caller-supplied `litellm.Router.get_model_list()` through
  the existing adapter `.models.list()` bridge. Convert its deployment
  `model_name` values to the existing OpenAI-compatible `{"data": [{"id": ...}]}`
  shape, so `OpenAIClientAdapter` and its async counterpart retain all catalog
  normalization, caching, refresh, and default-model ownership.
- L3.2 uses only a caller-supplied `responses` or `aresponses` callable through
  the existing native Responses resource. Generic Chat Completions remains the
  default; direct completion/Responses pairs fail before dispatch. The generic
  path forwards only ordinary provider config and deliberately excludes global
  loading, Router Responses inference, Codex shaping/auth, executor changes,
  and capability/status reporting.
- OCI packaging must run under Python 3.13 or newer. The legacy vendored-wheel
  cleanup remains separate from the completed runtime dependency change.

## Compatibility and Migration

The visible default transport changes from the official OpenAI SDK provider to
LiteLLM for ordinary OpenAI-compatible dispatch. To keep migration controlled:

- preserve existing `OpenAIClientAdapter` and `AsyncOpenAIClientAdapter`
  executor-facing behavior
- preserve caller-injected clients/providers as authoritative
- preserve `OpenAIProviderConfig` as the config object unless implementation
  proves a small LiteLLM-specific config object is necessary
- expose an explicit official SDK compatibility path
- keep existing tests for official SDK construction or update them to target the
  compatibility helper rather than the new default

## Risks

- LiteLLM Chat Completions semantics may not cover every current
  Responses-style request option.
- Tool descriptor shape may need translation between DAR's current OpenAI tool
  schema and the shape accepted by LiteLLM providers.
- Default transport changes can break assumptions in tests or downstream hosts.
- Adding LiteLLM as a required dependency may affect lock resolution and
  PyInstaller packaging.
- ChatGPT/Codex behavior can drift if folded into Slice L1; keep it out.

## Validation Strategy

Primary commands after implementation:

```bash
poetry run pytest tests/test_openai_client.py -q
poetry run pytest tests/test_executor.py -q
poetry run pytest -q
poetry run ruff check src tests
python -m py_compile python-build-system.py
poetry build --format wheel
pre-commit run --files \
  pyproject.toml poetry.lock README.md \
  src/dynamic_agent_runner/openai_client.py \
  src/dynamic_agent_runner/__init__.py \
  tests/test_openai_client.py tests/test_executor.py \
  specs/litellm-provider-adapter/spec.md \
  specs/litellm-provider-adapter/plan.md \
  specs/litellm-provider-adapter/tasks.md
```

Adjust the final file list to the actual changed files.

OCI artifact verification must additionally inspect the generated package tar:

```bash
tar -tf output_ocibuild_packagewheel/*.tar
shasum -a 256 vendor/wheels/litellm-1.92.0-py3-none-any.whl \
  <extracted-wheel-path>/litellm-1.92.0-py3-none-any.whl
```
