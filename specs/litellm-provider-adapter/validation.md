# LiteLLM Provider Adapter Validation

## Metadata

- Feature slug: `litellm-provider-adapter`
- Status: L2 opt-in Codex wrapper validated; upstream dependency adopted and
  shim retired
- Date: 2026-08-22

## Readiness Checks

- The spec has a narrow Slice L1 boundary.
- LiteLLM is a declared runtime dependency (`^1.97.0`, resolved to 1.97.0) with
  Python 3.14 support.
- Slice L1 has no blocking `NEEDS CLARIFICATION` items.
- ChatGPT/Codex-on-LiteLLM wrapper slices are implemented; global replacement
  remains deferred pending drift gates.
- LiteLLM Responses API support is implemented only through the opt-in wrapper.
- Unit-test strategy is fake-only and live-call-free.
- Request translation risk is identified as the main implementation risk.
- Default transport migration risk is identified and bounded by an explicit
  official SDK compatibility path.
- The manual Python 3.13 OCI package run completed successfully and produced a
  package tar containing the root artifacts and the checked-in LiteLLM wheel.
- The packaged LiteLLM wheel SHA-256 matched the checked-in wheel exactly.
- The full DAR suite passes after excluding the nested upstream LiteLLM test
  tree and preserved OCI input/output trees: `676 passed, 4 skipped`.
- The focused LiteLLM/OpenAI/auth integration set passes: `113 passed`.
- The upstream dependency is installed successfully and exposes callable
  `completion(...)` and `acompletion(...)` APIs. The removed fallback is covered
  by focused tests that require package-owned missing-transport errors.
- L2.1 compatibility audit completed in
  `specs/litellm-provider-adapter/l2-codex-compatibility.md`: LiteLLM Responses
  is compatible enough for a guarded follow-up, while Chat Completions
  bridging is not Codex-equivalent.
- The post-L2 drift review confirms the opt-in wrapper's tested request parity
  but blocks global migration on LiteLLM ambient ChatGPT auth and missing native
  DAR-compatible model listing. Full evidence is in `l2-codex-compatibility.md`.
- The retirement change passed `680 passed, 4 skipped`, `poetry run ruff check
  src tests`, and `make -C docs html`.

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

The completed upstream-dependency and shim-retirement slice does not:

- remove the separate legacy OCI checked-in wheel, copy step, or trigger
- add live model, provider, gateway, or OAuth calls
- authorize ChatGPT/Codex-on-LiteLLM implementation in Slice L1

## Consistency Analysis

- FR-1 through FR-6 map to L1.1-L1.15 and the focused provider tests.
- FR-10 maps to L1.8 and L1.22. The legacy OCI wheel cleanup is deferred
  packaging work, not the runtime distribution boundary.
- FR-11 maps to L1.1-L1.7 and the repository's fake-only unit-test policy.
- Deferred L2 and L3 tasks do not appear in the L1 acceptance boundary.
- No blocking clarification remains for Slice L1; implementation preserved the
  existing OpenAI/Codex auth boundary and used RED/GREEN tests.
- L1.8 is complete. The vendored wheelhouse path is legacy packaging cleanup,
  not the current runtime distribution boundary.
