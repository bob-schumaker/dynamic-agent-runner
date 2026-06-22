# LiteLLM Provider Adapter Validation

## Metadata

- Feature slug: `litellm-provider-adapter`
- Status: candidate readiness validation; implementation paused for Python
  3.14 dependency support
- Date: 2026-06-22

## Readiness Checks

- The spec has a narrow Slice L1 boundary.
- Slice L1 is paused until LiteLLM supports the package's Python 3.14 target.
- Slice L1 has no blocking `NEEDS CLARIFICATION` items.
- ChatGPT/Codex-on-LiteLLM is explicitly deferred to a follow-up slice.
- LiteLLM Responses API support is explicitly deferred from Slice L1.
- Unit-test strategy is fake-only and live-call-free.
- Request translation risk is identified as the main implementation risk.
- Default transport migration risk is identified and bounded by an explicit
  official SDK compatibility path.

## External Documentation Check

Official LiteLLM documentation was checked on 2026-06-22:

- `https://docs.litellm.ai/docs/` documents LiteLLM as a unified OpenAI-format
  interface, `completion(...)`, consistent Chat Completions-style response
  shape, exceptions mapped to OpenAI exception types, and the OpenAI-compatible
  proxy path.
- `https://docs.litellm.ai/docs/providers/chatgpt` documents the ChatGPT
  provider route as `chatgpt/`, supports `/responses` and `/chat/completions`,
  recommends Responses for Codex models, and notes token-limit and metadata
  handling. This is why ChatGPT/Codex replacement is deferred from Slice L1.

## Validation To Run During Implementation

```bash
poetry run pytest tests/test_openai_client.py -q
poetry run pytest tests/test_executor.py -q
poetry run pytest -q
poetry run ruff check src tests
```

Run targeted `pre-commit run --files ...` on the actual changed files before
committing implementation.

## Out-of-Scope Confirmation

The candidate preparation does not:

- add `litellm` to runtime dependencies yet
- change source behavior
- change default provider construction
- add live model, provider, gateway, or OAuth calls
- authorize ChatGPT/Codex-on-LiteLLM implementation in Slice L1
