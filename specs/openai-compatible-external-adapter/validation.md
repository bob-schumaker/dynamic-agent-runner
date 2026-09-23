# OpenAI-Compatible External Adapter Validation

## Discovery decision

Preliminary record (2026-09-23):

The existing repository provider seam can carry explicit endpoint, API-key,
timeout, proxy-environment, and redirect settings after the additive
`OpenAIProviderConfig` transport-control fields are applied. The default
OpenAI/LiteLLM provider path remains unchanged because the new adapter calls
only the explicit official-SDK factories with `discover_default_auth=False`.

No live endpoint or ambient credential is used by the unit-test path. A missing
API key uses the explicit no-auth client mode, which strips the SDK's generated
authorization header while retaining the caller-supplied endpoint.

## Validation status

- Implementation status: adapter, explicit transports, façade health bridge,
  exports, docs, and executor tool-loop coverage are implemented.
- Focused adapter tests: `13 passed` via
  `poetry run pytest tests/test_openai_compatible_external.py -q`.
- Affected external/OpenAI/executor/CLI regressions: `355 passed`.
- Ruff: passed for `src` and `tests`.
- Package build: `dynamic-agent-runner` 0.1.20 wheel and sdist built.
- Full pytest: `2749 passed, 1 skipped, 7 deselected`.
- M4.4 isolated actor test: passed after T6.7 added bounded retrying cleanup
  for late uv cache-file release; cleanup still raises after retry exhaustion.
- Markdown and repository pre-commit hooks: passed for changed artifacts.

## Deferred claims

Compatibility with Ollama, vLLM, LM Studio, and llama.cpp is wire-level only
until separately authorized live service certification. Service lifecycle,
registry configuration, streaming, embeddings, multimodal output, and native
callbacks remain outside this slice.
