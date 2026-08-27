<!-- markdownlint-disable MD013 -->
# Apple Foundation Models Adapter Tasks

Status: A1 and A2 implementation complete; standalone direct release gate established; pytest-native SDK checks remain diagnostic

## Prerequisites

- Authoritative spec: `specs/apple-foundation-model-adapter/spec.md`
- Plan: `specs/apple-foundation-model-adapter/plan.md`
- Existing adapter boundary: `AsyncOpenAIClientAdapter`
- Strict local-only selection uses `model_adapter_coverage="strict"`.
- Unit tests use fakes; live Apple tests are separate and eligibility-gated.

## Slice 1 — Contract and portability RED tests

- [x] T1.1 Add RED import tests proving package import and configuration
      construction do not import `apple_fm_sdk`.
- [x] T1.2 Add RED tests for `AppleFoundationModelConfig` and the async factory
      metadata, aliases, and existing adapter type.
- [x] T1.3 Add RED tests for unsupported platform, missing SDK, unavailable
      system model, and preserved exception causes.
- [x] T1.4 Add RED tests for unsupported tools, non-text content, streaming,
      schema-less JSON mode, conflicting token aliases, and unknown options.
      - Files: `tests/test_apple_foundation_models.py`, `tests/test_import.py`

## Slice 2 — Lazy provider and request translation

- [x] T2.1 Implement the package-owned Apple module with lazy SDK imports,
      injected availability/session/generation seams, and platform checks.
- [x] T2.2 Implement deterministic instruction and ordered text-history
      translation without hidden transcript reuse.
- [x] T2.3 Implement one fresh session per request and async cancellation
      propagation without provider-owned retries.
- [x] T2.4 Map supported temperature and token-limit options; reject ambiguous
      or unsupported options before SDK invocation.

## Slice 3 — Text, structured output, errors, and capabilities

- [x] T3.1 Add RED/GREEN fake-generation tests for final text and empty output,
      then return the existing normalized `ModelResponse` shape.
- [x] T3.2 Add RED/GREEN explicit JSON Schema tests, including malformed,
      unsupported, and schema-less response formats.
- [x] T3.3 Add error-translation tests for availability, session, guardrail,
      context, generation, cancellation, and opaque SDK failures.
- [x] T3.4 Add capability metadata tests proving only A1 capabilities are
      advertised and SDK-native extras remain unsupported.

## Slice 4 — Executor integration and strict coverage

- [x] T4.1 Add RED/GREEN executor tests for strict Apple alias selection,
      missing strict coverage failure, and unchanged augmented OpenAI fallback.
- [x] T4.2 Prove the Apple adapter uses existing request construction,
      normalization, tracing, and model-map capability paths without an
      executor-specific branch.
- [x] T4.3 Add package-root import/export coverage.

## Slice 5 — Eligible-Mac live verification and documentation

- [x] T5.1 Add marked live tests for real text and explicit JSON Schema output;
      skip cleanly with an actionable reason when prerequisites are absent.
- [x] T5.2 Add a live strict-coverage DAR workflow smoke test with structural
      assertions rather than exact prose matching.
- [x] T5.3 Document optional installation, macOS/Apple Intelligence
      prerequisites, strict usage, capabilities, limitations, and diagnostics.

## Slice 6 — Completion gate

- [x] T6.1 Run focused Apple, executor, and import tests.
- [x] T6.2 Run full tests, Ruff, `poetry check`, package build, and focused
      pre-commit.
- [x] T6.3 Run eligible-Mac standalone live text, structured-output, and strict-workflow verification; record the pytest-native SDK result.
- [x] T6.4 Check spec links/status consistency and update `specs/README.md`.
- [x] T6.5 Record the approved A2 handoff and the native SDK validation result.
- [x] T6.6 Replace pytest-native Apple SDK generation as the A1 release gate
      with the standalone direct-runtime runner. Keep marked pytest-native
      checks as diagnostic evidence only.
  - Evidence: `scripts/run_apple_live_release_gate.py` and
    `validation.md` (2026-08-27); the elevated eligible-Mac runner passed text,
    structured-output, and strict-workflow checks with a redacted receipt.
- [ ] T6.7 Decide the configured-host MCP ``tools/list`` contract and restore a
      green full-suite gate: either hide execution tools without an explicit
      host or update the stale empty-list expectation to the intended
      ``run_dar_workflow`` behavior. Record the decision, add focused coverage,
      and rerun the full suite.

## A2 handoff

Apple `Tool` wrappers, provider ingress, callback lifecycle tracing, and live
callback tests are governed by the approved `a2-plan.md` and `a2-tasks.md`.
Durable approval pause/resume remains outside A2 scope.
