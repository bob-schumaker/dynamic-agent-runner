# OpenAI-Compatible External Adapter Task List

## Status

- State: implementation complete; all required validation gates are green
- Source spec: `specs/openai-compatible-external-adapter/spec.md`
- Technical plan: `specs/openai-compatible-external-adapter/plan.md`
- Primary implementation area: `src/dynamic_agent_runner/openai_compatible_external.py`
- Primary validation area: `tests/test_openai_compatible_external.py`
- Unit tests remain fake-transport-only; no live model service or ambient
  credential is permitted.

## Slice 1 — RED boundary and façade-mode tests

- [ ] T1.1 [tests, RED] Add focused tests for the public configuration shape,
  required identity fields, bounded timeout, private API-key handling, and
  package-owned validation errors.
  - Primary file: `tests/test_openai_compatible_external.py`
  - Cover repr, equality/hash, descriptors, traces, diagnostics, and
    serialization without exposing the API key.
- [ ] T1.2 [tests, RED] Add URL-admission vectors for HTTPS, loopback-IP HTTP,
  non-loopback HTTP, unsupported schemes, userinfo, query, fragment, ports,
  IPv4/IPv6 loopback, redirect policy, and ambient proxy rejection.
- [ ] T1.3 [tests, RED] Add fake inventory tests for exact service-model
  admission, missing/duplicate/malformed IDs, bounded health timeout, and
  context-independent health semantics.
- [ ] T1.4 [tests, RED] Add separate sync and async mode tests covering façade
  dispatch compatibility, async task cancellation, sync late-result discard,
  bounded-worker occupancy, and health offload in async workflows.
- [ ] T1.5 [tests, RED] Add an executor/coordinator integration test in which a
  fake model returns a tool call, DAR performs approval/lifecycle/tracing and
  invokes the handler exactly once, then sends the follow-on request. Assert
  the adapter and transport receive no handler, approval, registry, or
  executor object.

Exit gate: the focused suite fails because the adapter and its explicit
transport boundary do not yet exist; failures identify the implementation
contracts without requiring a live service.

## Slice 2 — Admission, contracts, and error boundaries

- [ ] T2.1 [implementation] Add the immutable non-secret configuration,
  package-owned errors, identity validation, timeout bounds, and private API-key
  storage in `openai_compatible_external.py`.
  - Preserve the approved fields and never include the key in public or
    diagnostic values.
- [ ] T2.2 [implementation] Add one shared URL canonicalization/validation
  helper enforcing the approved scheme, loopback, userinfo/query/fragment,
  redirect, and proxy rules before client construction.
- [ ] T2.3a [design gate] Record the v1 execution-mode decision before
  defining transports: expose separate sync and async factories/adapters named
  `create_openai_compatible_external_adapter` and
  `create_async_openai_compatible_external_adapter`, keep sync health
  adapter-owned and config-timeout-bounded, and require the async adapter to
  own a separate synchronous bounded health probe (using the same configured
  timeout) because frozen v1 `health()` cannot await async `list_models`.
  Assign the required async façade health offload in T4.2. A single adapter
  object must not pretend to support both façade dispatch modes.
- [ ] T2.3 [implementation] Define narrow sync and async transport protocols
  with `list_models(timeout_seconds)` and `create_response(request,
  deadline_monotonic, cancellation)`; use a finite string-ID inventory shape.
- [ ] T2.4 [implementation] Add bounded health and exact service-model
  admission. Health uses only the configured timeout and returns redacted,
  package-owned unavailable/failed states; it never uses mutable per-call
  adapter state. The façade is the single bounded-worker owner for health in
  both sync and async dispatch, so a non-cooperative transport cannot block
  health indefinitely; document that late worker results are discarded and
  capacity remains occupied until return. Add a fake probe that blocks beyond
  the timeout and the synchronous health-probe fixture required by the async
  adapter mode.
- [ ] T2.5 [implementation] Add redacted translation for admission, health,
  timeout, cancellation, malformed-response, and transport failures with no
  fallback or retry.

Exit gate: configuration, URL, inventory, secret, and error tests pass with
injected fake transports; no default provider or environment credential is
consulted.

## Slice 3 — Explicit sync/async transport construction

- [ ] T3.1 [discovery] Inspect the existing `openai_client.py` seams and record
  whether they can provide explicit timeout, no-proxy, redirect, cancellation,
  and intentional no-key local-client controls without changing default
  OpenAI/LiteLLM behavior.
  - Create a dated preliminary record immediately in
    `specs/openai-compatible-external-adapter/validation.md`. The only
    acceptable outcomes are reuse with the required controls, a narrowly scoped
    explicit transport seam, or stop/escalate because the controls are
    unavailable. Do not modify the default provider path as part of discovery.
- [ ] T3.2 [implementation] Implement the selected explicit sync client
  factory. It must use caller-supplied endpoint/key or deliberate no-key local
  mode, disable ambient auth/proxy behavior, apply timeout/redirect controls,
  and never call `create_default_openai_provider(...)` or LiteLLM fallback.
- [ ] T3.3 [implementation] Implement the matching explicit async client
  factory, its task-cancellation bridge, and its separate synchronous bounded
  health probe. Keep sync and async adapter modes separate and
  façade-compatible.
- [ ] T3.4 [implementation] Translate the DAR request to the finite supported
  OpenAI-compatible wire subset, replace `model_alias` with the verified
  `service_model_id` exactly once, and return one normalized `ModelResponse`.
  - Do not forward DAR-only context/deadline fields as provider kwargs.
  - Keep raw removal, metadata allowlisting, JSON-schema validation, and
    tool-call capability validation in the external façade.
- [ ] T3.5 [tests, GREEN] Prove recorded client-factory settings for timeout,
  `trust_env=False`/no proxy, redirect behavior, no-key/no-environment-auth,
  exact service model, ordered messages, tool choice, and malformed response
  handling.

Exit gate: explicit transport tests pass and the discovery decision is
recorded; legacy OpenAI/LiteLLM construction tests remain green.

## Slice 4 — Protocol adapter and coordinator integration

- [ ] T4.1 [implementation] Add the sync and async protocol adapter variants
  with the configured descriptor: fixed provider ID, one model alias, canonical
  model ID, text-only modalities, structured-output capability, and explicit
  tool-calling capability.
- [ ] T4.2 [implementation] Wire adapter dispatch through the existing
  `ExternalModelAdapterFacade`, including health offload in both sync and async
  dispatch, request context, deadline/cancellation, single-use dispatch,
  redaction, and failure classification. Add the minimal façade change that
  routes synchronous health through its one bounded worker, plus a focused
  regression test; do not change `DARExternalAdapterProtocol` or its wire ID.
- [ ] T4.3 [tests, GREEN] Prove pre-dispatch rejection for invalid identity,
  disabled tools, unsupported response modes, and failed health; prove
  post-dispatch classification for timeout, cancellation, malformed response,
  and service rejection.
- [ ] T4.3a [tests, contract proof] Add a focused proof that the existing
  façade enforces
  requested JSON Schema semantics after transport normalization, including
  valid and invalid JSON responses. Run this proof before any conditional
  façade implementation change.
- [ ] T4.3b [implementation] If T4.3a exposes missing behavior, make only the
  minimal façade change required to enforce that contract; do not move schema
  validation into the adapter or transport.
- [ ] T4.4 [tests, GREEN] Run the actual executor/coordinator tool cycle from
  T1.5 and verify exactly-once handler execution, approval/lifecycle/tracing,
  follow-on model request, and no adapter-held callback references.

Exit gate: protocol conformance, façade compatibility, structured output, and
executor-level tool re-entry tests pass.

## Slice 5 — Public surface and migration documentation

- [ ] T5.1 [implementation] Export the approved config and sync/async factory
  helpers from `src/dynamic_agent_runner/__init__.py` without exporting the
  private API key or transport internals.
- [ ] T5.2 [docs] Add a concise README example showing direct BYOM construction
  and strict model-adapter coverage. State that service lifecycle, registry
  binding, CLI install/remove, and family certification remain caller-owned or
  deferred.
- [ ] T5.3 [tests, GREEN] Add import/API tests and verify existing local
  endpoint helpers and adapter-selection paths remain unchanged.

Exit gate: public imports and documentation hooks pass; no legacy endpoint or
OpenAI/LiteLLM default behavior changes.

## Slice 6 — Validation and handoff evidence

- [ ] T6.1 [validation] Create or finalize
  `specs/openai-compatible-external-adapter/validation.md` with the discovery
  decision, focused test result, redaction/security evidence, and any
  explicitly deferred service-compatibility claims.
- [ ] T6.2 [validation] Run focused tests:
  `poetry run pytest tests/test_openai_compatible_external.py -q`.
- [ ] T6.3 [validation] Run affected regressions:

  ```text
  poetry run pytest tests/test_external_adapter_protocol.py \
    tests/test_openai_client.py tests/test_executor.py tests/test_cli.py -q
  ```

- [ ] T6.4 [validation] Run repository gates:
  `poetry run pytest -q`, `poetry run ruff check src tests`, and
  `poetry build`.
- [ ] T6.5 [validation] Run concrete artifact hooks:

  ```text
  poetry run pre-commit run --files \
    specs/openai-compatible-external-adapter/spec.md \
    specs/openai-compatible-external-adapter/plan.md \
    specs/openai-compatible-external-adapter/tasks.md \
    specs/openai-compatible-external-adapter/validation.md \
    specs/README.md \
    README.md \
    src/dynamic_agent_runner/openai_compatible_external.py \
    src/dynamic_agent_runner/external_adapter.py \
    tests/test_openai_compatible_external.py
  ```

- [ ] T6.6 [review] Confirm spec, plan, tasks, implementation, and validation
  evidence agree; record exact outcomes before declaring the slice complete.
- [x] T6.7 [bug, tests RED/GREEN] Repair the M4.4 clean-Codex harness teardown
  race where a just-finished `uv` actor releases cache files after the scenario
  temporary directory begins cleanup. Add bounded retrying cleanup that still
  raises after exhaustion, then run the isolated failing harness test and the
  full suite.
  - Primary file: `scripts/run_m4_4_clean_codex.py`
  - Evidence: the isolated M4.4 actor test passes without masking leftover
    temporary files; the full pytest gate no longer reports the cleanup race.

Exit gate: all required commands pass, tests remain fake-only, no ambient
credentials or live service calls occur, and the legacy regression floor is
green.

## Review record

- 2026-09-23 Council architecture triad (Aristotle, Ada, Feynman): initial
  review **not ready**. Findings required an explicit execution-mode gate,
  bounded health ownership, durable discovery evidence, JSON-schema proof and
  conditional remediation, and concrete artifact-hook paths.
- 2026-09-23 Council challenge round: all three reviewers returned **ready for
  implementation handoff** after those findings were addressed. The final
  design uses separate sync/async factories, an async adapter's synchronous
  health probe, one façade-owned bounded health worker, and fake blocking-health
  evidence.
- 2026-09-23 Ponytail full review: removed ambiguous discovery sequencing and
  clarified one bounded-worker owner so the adapter and façade do not imply
  nested health workers. No task was removed because each remaining item maps
  to an approved plan deliverable or required verification gate.
- Current disposition: implementation complete for the adapter slice; focused
  and affected gates are green. The full-suite gate remains open only for the
  unrelated M4.4 cleanup race recorded in `validation.md`.

## Ordering and ownership notes

- Slice 1 is mandatory TDD RED work and must precede implementation.
- Slice 2 establishes the public and transport contracts before concrete HTTP
  construction.
- Slice 3's discovery decision controls whether `openai_client.py` changes;
  any change must preserve its default provider behavior.
- Slice 4 owns the only façade/executor integration changes. The adapter and
  transport never receive handlers, approvals, registries, or executors.
- Slice 5 is additive public-surface work. Slice 6 is the release gate.
- No `tasks.md` item authorizes registry configuration, CLI lifecycle, service
  startup/downloads, streaming, embeddings, multimodal output, or live tests.
