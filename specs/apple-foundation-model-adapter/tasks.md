# Apple Foundation Models Adapter Tasks

Status: A1 implementation-ready; not started

## Prerequisites

- Authoritative spec: `specs/apple-foundation-model-adapter/spec.md`
- Plan: `specs/apple-foundation-model-adapter/plan.md`
- Existing adapter boundary: `AsyncOpenAIClientAdapter`
- Strict local-only selection uses `model_adapter_coverage="strict"`.
- Unit tests use fakes; live Apple tests are separate and eligibility-gated.

## Slice 1 — Contract and portability RED tests

- [ ] T1.1 Add RED import tests proving package import and configuration
      construction do not import `apple_fm_sdk`.
- [ ] T1.2 Add RED tests for `AppleFoundationModelConfig` and the async factory
      metadata, aliases, and existing adapter type.
- [ ] T1.3 Add RED tests for unsupported platform, missing SDK, unavailable
      system model, and preserved exception causes.
- [ ] T1.4 Add RED tests for unsupported tools, non-text content, streaming,
      schema-less JSON mode, conflicting token aliases, and unknown options.
      - Files: `tests/test_apple_foundation_models.py`, `tests/test_import.py`

## Slice 2 — Lazy provider and request translation

- [ ] T2.1 Implement the package-owned Apple module with lazy SDK imports,
      injected availability/session/generation seams, and platform checks.
- [ ] T2.2 Implement deterministic instruction and ordered text-history
      translation without hidden transcript reuse.
- [ ] T2.3 Implement one fresh session per request and async cancellation
      propagation without provider-owned retries.
- [ ] T2.4 Map supported temperature and token-limit options; reject ambiguous
      or unsupported options before SDK invocation.

## Slice 3 — Text, structured output, errors, and capabilities

- [ ] T3.1 Add RED/GREEN fake-generation tests for final text and empty output,
      then return the existing normalized `ModelResponse` shape.
- [ ] T3.2 Add RED/GREEN explicit JSON Schema tests, including malformed,
      unsupported, and schema-less response formats.
- [ ] T3.3 Add error-translation tests for availability, session, guardrail,
      context, generation, cancellation, and opaque SDK failures.
- [ ] T3.4 Add capability metadata tests proving only A1 capabilities are
      advertised and SDK-native extras remain unsupported.

## Slice 4 — Executor integration and strict coverage

- [ ] T4.1 Add RED/GREEN executor tests for strict Apple alias selection,
      missing strict coverage failure, and unchanged augmented OpenAI fallback.
- [ ] T4.2 Prove the Apple adapter uses existing request construction,
      normalization, tracing, and model-map capability paths without an
      executor-specific branch.
- [ ] T4.3 Add package-root import/export coverage.

## Slice 5 — Eligible-Mac live verification and documentation

- [ ] T5.1 Add marked live tests for real text and explicit JSON Schema output;
      skip cleanly with an actionable reason when prerequisites are absent.
- [ ] T5.2 Add a live strict-coverage DAR workflow smoke test with structural
      assertions rather than exact prose matching.
- [ ] T5.3 Document optional installation, macOS/Apple Intelligence
      prerequisites, strict usage, capabilities, limitations, and diagnostics.

## Slice 6 — Completion gate

- [ ] T6.1 Run focused Apple, executor, and import tests.
- [ ] T6.2 Run full tests, Ruff, `poetry check`, package build, and focused
      pre-commit.
- [ ] T6.3 Run eligible-Mac live tests and record skip/pass evidence.
- [ ] T6.4 Check spec links/status consistency and update `specs/README.md`.
- [ ] T6.5 Confirm A2 remains deferred; do not mark the feature complete until
      all A1 evidence and documentation checks pass.

## Deferred A2 tasks

Apple `Tool` wrappers, the DAR-owned invocation coordinator, approval pause /
resume, callback lifecycle tracing, and live callback tests require a separate
approved plan and are not tasks in this A1 list.
