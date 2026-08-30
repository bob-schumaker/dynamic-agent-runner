<!-- markdownlint-disable MD013 -->
# Apple Foundation Models A2 Task List

Status: B0--B4 implementation, documentation, and validation complete; B5
bridged-wrapper annotation regression open

This is the canonical task list for A2. `tasks.md` remains the completed A1
record and must not duplicate A2 implementation work. This list implements the
fixed decisions in `a2-plan.md`.

## B0 — Native harness diagnosis

- [x] B0.1 [tests] Capture a minimal standalone and pytest-native Apple
      generation comparison with redacted phase/status evidence.
  - Evidence: `validation.md` (2026-08-26); status 255 did not reproduce, but
    pytest emitted a repeatable SDK-native destructor error at process teardown.
- [x] B0.2 [analysis] Record the current status-255 non-reproduction, historical
      status-255 context, repeated teardown defect, and authoritative standalone
      gate; reconcile the validation record so its current conclusion is
      unambiguous.
- [x] B0.3 [spike] Pin and demonstrate the SDK `Tool`, `GenerationSchema`, and
      `GeneratedContent` APIs; record the admitted A2 schema capability matrix,
      Apple tool-name constraints, supported callback argument conversion, and
      rejected schema forms in `a2-plan.md`; then run a marked-live no-side-effect
      `LanguageModelSession.respond` sentinel that invokes one wrapper exactly
      once with parsed callback arguments. Record the observed callback
      thread/event-loop topology in the B0.3 evidence, but do not make its
      relationship a live-test invariant.
  - Construction evidence: `apple-fm-sdk` distribution `0.2.1` local probe,
    recorded in `a2-plan.md` (2026-08-26); no model generation was invoked.
    The package's `apple_fm_sdk.__version__` reports stale `0.1.0` metadata.
  - Live evidence: outside the Codex execution sandbox, the sentinel invoked
    exactly once with `{"token": "DAR_SENTINEL"}` on a different thread and
    event loop from its caller. Inside that sandbox, even bare native operations
    returned `GenerationError(status: 255)` despite successful availability.
  - Reproducible command (run from an elevated host terminal outside the Codex
    execution sandbox in this environment):
    `poetry run pytest -m apple_live tests/test_live_apple_foundation_models.py::test_live_apple_tool_callback_sentinel -q`.

## B1 — Provider ingress contract

- [x] B1.1 [tests] Add passing characterization tests before extracting the
      executor-private coordinator. Cover common direct/model-loop dispatch
      behavior plus direct result-key and model-loop continuation ownership,
      then preserve provider-origin model call-id correlation across multiple
      calls. Existing direct-retry and model-loop-failure tests remain coverage
      for their respective paths. The non-wire provider ingress request itself
      is B1.2 work; its wire exclusion is B1.3 RED coverage.
- [x] B1.2 [implementation] Extract a dependency-light internal coordinator,
      migrate existing callers, and define the non-wire active adapter context.
  - Evidence: `validation.md` (2026-08-26); the selected-tool snapshot and
    explicit retry policy are carried only in the non-wire adapter context.
- [x] B1.3 [tests] Prove non-Apple wire kwargs/traces contain no adapter context
      or registry/state reference; stale and raw descriptor contexts fail closed.
  - Evidence: `validation.md` (2026-08-26); constructor and factory paths both
    reject raw descriptors, and stale contexts fail before their closure runs.
- [x] B1.4 [implementation] Define typed provider interruption, synchronous
      exact-fingerprint decision collaborator, and atomic callback budget.
  - Evidence: `validation.md` (2026-08-26); no decision dispatch, outcome
    rendering, or callback/session lifecycle behavior is introduced before B1.5/B3.
- [x] B1.5 [tests] Prove approved dispatches once; denied/cancelled/expired and
      unresolved approvals prevent handler/hook/retry/registry/state effects;
      exposure and argument validation precede decision resolution and
      pre-invocation hooks for every outcome; exact approved normalized
      arguments dispatch once; mismatched, replayed, and unknown decisions fail
      closed; unresolved produces an executor-visible
      `WorkflowInterruptedResult`, not a model failure or retry.
  - Evidence: `validation.md` (2026-08-26); approved dispatches use the exact
    prepared invocation once, terminal decisions have no dispatch or approval
    pause, and only unresolved becomes `WorkflowInterruptedResult`.

## B2 — Schema-safe Apple wrappers

- [x] B2.1 [tests] Add RED schema/name-translation tests for the B0 capability
      matrix; prove session construction receives exactly the effective
      model-facing selected-tool allowlist, invalid or colliding names fail
      closed, and inactive, unexposed, stale-context, and raw-descriptor tools
      never reach Apple session creation.
  - Evidence: `validation.md` (2026-08-26); strict expected-failure coverage
    defines the B2.2 wrapper contract without enabling Apple tool use.
- [x] B2.2 [implementation] Generate one Apple wrapper per exposed active-node
      DAR tool and provide no wrapper for inactive or unexposed tools. Select
      wrappers solely from the typed active context, reject non-identifier and
      keyword property names until an SDK alias mechanism is proven, and keep
      wrapper callbacks inert until B3.
  - Evidence: `validation.md` (2026-08-26); the focused fake SDK suite passes
    with opaque wrapper names, active-context-only selection, strict schema
    rejection, and non-identifier/keyword property-name rejection before
    session setup.

## B3 — Callback execution

- [x] B3.1 [tests] Add RED callback tests proving coordinator validation,
      exactly-once approved dispatch, lifecycle/trace/state preservation, and
      `ToolResult.model_facing_output` serialization.
  - Evidence: `validation.md` (2026-08-26); strict expected-failure callback
    tests require two distinct wrapper-to-tool paths, coordinator ingress,
    unique callback identities/result keys, model-origin lifecycle traces, and
    validation before approval or dispatch. B3.2 turns them green.
- [x] B3.2 [implementation] Route Apple callbacks through the coordinator and
      convert unresolved approval to the provider-aware DAR interruption;
      denied, cancelled, and expired decisions remain non-dispatch outcomes.
  - Evidence: `validation.md` (2026-08-26); callbacks marshal coordinator work
    to the executor loop, preserve guardrails/state/traces/hooks, and terminate
    non-retryably for denied, cancelled, expired, guardrail, and failed-result
    outcomes.
- [x] B3.3 [tests] Prove the atomic provider-callback budget derives from the
      active DAR tool-call limit, translates zero and one correctly, caps N+1
      racing callbacks, emits the provider-origin exhaustion trace, and returns
      the declared DAR-controlled termination outcome.
  - Evidence: `validation.md` (2026-08-26); each Apple session shares one
    executor-traced atomic budget derived from `max_steps` with DAR's default
    fallback, and exhaustion is a non-retry terminal outcome.
- [x] B3.4 [tests] Prove cancellation before and during a callback prevents
      later dispatch, result writes, post-session state mutation, or re-entrant
      event-loop use; prove callbacks after session completion fail closed.
  - Evidence: `validation.md` (2026-08-26); callbacks recheck session liveness
    immediately before dispatch and atomically guard DAR result-state/trace
    finalization. Deterministic fake coverage proves pre-dispatch closure,
    cancellation, and late callbacks never reach a handler; a post-handler,
    pre-commit closure permits no result, trace, or after-hook effect.
- [x] B3.5 [tests] Prove unresolved interruption, callback-budget exhaustion,
      and cancellation abort and clean up the Apple session exactly once, with
      no later callback dispatch or state mutation.
  - Evidence: `validation.md` (2026-08-26); all three terminal paths stop the
    current `respond()` sequence before another scripted callback, close DAR's
    callback capability once, reject late callbacks, and prevent later result
    state or finalization traces. The installed Apple SDK owns native-task
    cancellation/reset and exposes no public session abort/close API.

## B4 — Live evidence and documentation

- [x] B4.1 [tests] Add a marked-live/manual eligible-Mac callback smoke using a
      safely observable no-side-effect sentinel to show callback entry into DAR
      before handler execution and denied approval prevents the handler; retain
      exactly-once approval proof in fakes. In this Codex/macOS environment,
      run the native callback portion elevated outside the execution sandbox as
      demonstrated by B0.3.
  - Evidence: `validation.md` (2026-08-26); elevated approved and denied DAR
    callback sentinels passed independently. The approved path proves
    `before_tool` precedes the handler; the denied path reaches DAR once without
    handler, result-state, or normal lifecycle effects.
- [x] B4.2 [docs] Document A2 capabilities, interruption behavior, schema
      limits, and the status-255 harness result.
  - Evidence: `README.md` and `docs/files/python-api.rst` (2026-08-26);
    published source describes the active-tool bridge, decision outcomes,
    admitted schema subset, and environment-specific native test constraint.
- [x] B4.3 [validation] Record RED/GREEN focused A2 test module results, then
      run and record `poetry run pytest -q`, `poetry run ruff check src tests`,
      `poetry check`, `poetry build`, and the opt-in eligible-Mac callback gate
      or its precise skip, with redacted evidence identifiers/outputs.
  - Evidence: `validation.md` (2026-08-27); the focused A2 suite, quality
    checks, build, and elevated live callback gate passed. The full suite's
    sole configured-host MCP expectation failure is recorded precisely.

## B5 — Bridged-wrapper annotation regression

- [ ] B5.1 [bug/tests/implementation] Reproduce and fix the eligible-Mac SDK
      wrapper-construction failure observed by the live interface matrix:
      `DarTool2Arguments contains undefined references: [Annotated]`.
  - Scope: the wrapper type generated by
    `src/dynamic_agent_runner/apple_foundation_models.py`; this is a bridge
    construction defect before model generation, not an Apple model
    tool-selection failure.
  - RED: add a focused test that builds the generated wrapper through the real
    installed `apple_fm_sdk` type-construction boundary without opening a model
    session, invoking generation, or dispatching a tool. It must reproduce the
    unresolved annotation reference on an eligible SDK/platform and skip with
    an actionable reason when that optional boundary is unavailable.
  - GREEN: resolve annotations in the generated wrapper's defining namespace
    using the smallest SDK-compatible construction change. Preserve the B2
    admitted-schema matrix, opaque wrapper names, and coordinator-only callback
    authority.
  - Regression proof: focused fake bridge tests plus the real construction test
    pass; then rerun the manually gated Apple S1 live row. Do not use external
    tools or approval interaction.
  - Files/components: `src/dynamic_agent_runner/apple_foundation_models.py`,
    `tests/test_apple_foundation_models.py`, and, if needed,
    `tests/test_live_apple_foundation_models.py`.
