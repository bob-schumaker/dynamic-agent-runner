# OpenAI-Compatible Provider Wrapper Task List

## Status

- State: Slices 1-4 implemented; `src/dynamic_agent_runner/openai_client.py`
  now exposes a repository-owned provider/client facade, provider
  configuration, SDK-backed default provider wrappers, provider-config-aware
  default sync/async client factories supporting `base_url` plus optional
  `api_key`, and adapters that lazily resolve their default clients through the
  provider seam while preserving `models` / `is_local` routing semantics;
  response dispatch now also flows through repository-owned sync/async helpers
  so transport calls, error translation, and normalization remain centralized
- Source spec: `specs/openai-compatible-provider-wrapper/spec.md`
- Technical plan: `specs/openai-compatible-provider-wrapper/plan.md`
- Primary implementation area: `src/dynamic_agent_runner/openai_client.py`
- Primary validation area: `tests/test_openai_client.py`

## Slice 1 — Repository-owned provider/client facade

- [x] T1.1 Define the repository-owned sync provider/client facade used by the
      runtime adapter boundary.
- [x] T1.2 Define the repository-owned async provider/client facade used by the
      async runtime adapter boundary.
- [x] T1.3 Introduce any small provider configuration structure needed for
      `base_url`, optional `api_key`, and optional provider diagnostics metadata.
- [x] T1.4 Keep the facade narrow enough for fake-client tests and future
      alternate implementations.

## Slice 2 — SDK-backed default wrapper isolation

- [x] T2.1 Move the direct `openai` SDK import and construction path behind the
      repository-owned wrapper implementation.
- [x] T2.2 Preserve project-specific `ModelExecutionError` behavior when the
      `openai` package is unavailable.
- [x] T2.3 Support default hosted OpenAI construction with no required new
      caller-facing provider object.
- [x] T2.4 Support optional `base_url` configuration for OpenAI-compatible
      endpoints.
- [x] T2.5 Support optional `api_key` passthrough for hosted or compatible
      providers.

## Slice 3 — Adapter refactor and routing preservation

- [x] T3.1 Refactor `OpenAIClientAdapter` to depend on the repository-owned
      wrapper/facade rather than raw SDK-construction assumptions.
- [x] T3.2 Refactor `AsyncOpenAIClientAdapter` to depend on the repository-owned
      async wrapper/facade rather than raw SDK-construction assumptions.
- [x] T3.3 Preserve existing adapter metadata fields `models` and `is_local`.
- [x] T3.4 Preserve existing executor compatibility so `executor.py` does not
      need a new provider-specific execution path.
- [x] T3.5 If provider diagnostics metadata is added, keep it optional and
      non-authoritative for executor routing.

## Slice 4 — Preserve repository-owned request and normalization logic

- [x] T4.1 Keep `build_openai_request(...)` or a directly equivalent
      repository-owned helper as the canonical request construction path.
- [x] T4.2 Keep `normalize_openai_response(...)` or a directly equivalent
      repository-owned helper as the canonical response normalization path.
- [x] T4.3 Ensure provider-specific transport changes do not move request or
      response semantics into executor logic.

## Slice 5 — Tests for wrapper behavior and compatible endpoints

- [x] T5.1 Update `tests/test_openai_client.py` to validate the refactored sync
      wrapper path using fake clients or monkeypatched construction.
- [x] T5.2 Update `tests/test_openai_client.py` to validate the refactored async
      wrapper path using fake clients or monkeypatched construction.
- [x] T5.3 Add coverage for default hosted OpenAI construction behavior without
      live network calls.
- [x] T5.4 Add coverage for custom `base_url` configuration targeting an
      OpenAI-compatible endpoint.
- [x] T5.5 Add coverage for optional `api_key` passthrough behavior.
- [x] T5.6 Add coverage proving `is_local=True` adapters remain compatible with
      existing runtime routing semantics.

## Slice 6 — Optional export and documentation follow-up

- [ ] T6.1 Update `src/dynamic_agent_runner/__init__.py` exports if the refactor
      introduces new public wrapper or configuration types that should be
      caller-visible.
- [ ] T6.2 Update `README.md` or adjacent docs only if public usage changes or a
      new OpenAI-compatible endpoint example materially improves clarity.

## Slice 7 — Validation evidence

- [x] T7.1 Run `poetry run pytest tests/test_openai_client.py -q` and record the
      result.
- [x] T7.2 If adapter integration behavior changed, run
      `poetry run pytest tests/test_executor.py -q` and record the result.
- [ ] T7.3 If exports changed, run `poetry run pytest tests/test_import.py -q`
      and record the result.

## Ordering Notes

- Slice 1 must land before Slice 2 because the SDK wrapper needs a repository-
  owned target interface.
- Slice 2 should land before Slice 3 so adapter refactors can target the final
  wrapper seam instead of temporary construction helpers.
- Slice 4 should be validated while Slice 3 is in progress so request and
  normalization ownership does not accidentally drift into transport code.
- Slice 5 should be executed before any optional naming or export cleanup so
  behavioral regressions are caught before public-surface polishing.
