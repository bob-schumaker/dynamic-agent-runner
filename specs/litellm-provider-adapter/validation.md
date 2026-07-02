# LiteLLM Provider Adapter Validation

## Metadata

- Feature slug: `litellm-provider-adapter`
- Status: Slice L1 implementation validation; upstream publication remains deferred
- Date: 2026-07-02

## Readiness Checks

- The spec has a narrow Slice L1 boundary.
- LiteLLM Python 3.14 support is handled temporarily by the checked-in pure
  Python wheel and the OCI wheelhouse copy step.
- Slice L1 has no blocking `NEEDS CLARIFICATION` items.
- ChatGPT/Codex-on-LiteLLM is explicitly deferred to a follow-up slice.
- LiteLLM Responses API support is explicitly deferred from Slice L1.
- Unit-test strategy is fake-only and live-call-free.
- Request translation risk is identified as the main implementation risk.
- Default transport migration risk is identified and bounded by an explicit
  official SDK compatibility path.
- The manual Python 3.13 OCI package run completed successfully and produced a
  package tar containing the root artifacts and the checked-in LiteLLM wheel.
- The packaged LiteLLM wheel SHA-256 matched the checked-in wheel exactly.
- The full DAR suite passes after excluding the nested upstream LiteLLM test
  tree and preserved OCI input/output trees: `668 passed, 4 skipped`.
- The focused LiteLLM/OpenAI/executor integration set passes: `202 passed`.
- A portable Poetry dependency remains blocked: the configured Artifactory does
  not publish LiteLLM, while a local wheel dependency produces a non-portable
  `file://` requirement in the root wheel metadata.

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
python -m py_compile python-build-system.py
poetry build --format wheel
```

The OCI packaging validation is:

```bash
tar -tf output_ocibuild_packagewheel/*.tar
shasum -a 256 vendor/wheels/litellm-1.92.0-py3-none-any.whl \
  <extracted-wheel-path>/litellm-1.92.0-py3-none-any.whl
```

Run targeted `pre-commit run --files ...` on the actual changed files before
committing implementation.

## Out-of-Scope Confirmation

The implemented Slice L1 does not:

- add the full upstream `litellm` distribution to runtime dependencies yet;
  the bundled `dynamic_agent_runner.litellm` transport is included in DAR
- add live model, provider, gateway, or OAuth calls
- authorize ChatGPT/Codex-on-LiteLLM implementation in Slice L1

## Consistency Analysis

- FR-1 through FR-6 map to L1.1-L1.15 and the focused provider tests.
- FR-10 maps to L1.8-L1.8c and L1.21; the checked-in wheel and Python 3.13
  OCI result are explicit implementation constraints, not deferred assumptions.
- FR-11 maps to L1.1-L1.7 and the repository's fake-only unit-test policy.
- Deferred L2 and L3 tasks do not appear in the L1 acceptance boundary.
- No blocking clarification remains for Slice L1; implementation preserved the
  existing OpenAI/Codex auth boundary and used RED/GREEN tests.
- L1.8 is an external publication blocker, not an unresolved design question;
  the vendored wheelhouse path is the current approved runtime distribution
  boundary.
