<!-- markdownlint-disable MD013 -->
# Apple Foundation Models A2 Task List

Status: B0--B5.1 implementation, documentation, and validation complete; B5.2
tool-choice capability spike open

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

- [x] B5.1 [bug/tests/implementation] Prove the existing fix for the eligible-Mac
      SDK wrapper-construction failure observed by the live interface matrix:
      `DarTool2Arguments contains undefined references: [Annotated]`.
  - Scope: the wrapper type generated by
    `src/dynamic_agent_runner/apple_foundation_models.py`; this is a bridge
    construction defect before model generation, not an Apple model
    tool-selection failure.
  - RED/characterization: the production field-guide fix is already present;
    do not revert it to reproduce the historical failure. Add the focused
    real-SDK construction regression test instead, preserving the original
    error string as its historical reason.
  - GREEN: keep `Annotated` out of the dynamic class's `__annotations__` and
    attach the SDK field guide as the corresponding class attribute. Preserve
    the B2 admitted-schema matrix, opaque wrapper names, and coordinator-only
    callback authority.
  - Test contract: add one `@pytest.mark.apple_live` test to
    `tests/test_live_apple_foundation_models.py`, runnable as
    `poetry run pytest -m apple_live tests/test_live_apple_foundation_models.py::test_live_apple_bridged_tool_construction -q`.
    Use a separate construction-only prerequisite helper: skip only on
    non-macOS or unavailable `apple_fm_sdk`/native FFI prerequisites, with an
    actionable recorded reason; it must not construct `SystemLanguageModel` or
    check model availability. Once `_apple_tool_wrapper` starts real SDK
    construction, every construction exception must fail the test rather than
    skip it, including the historical unresolved-`Annotated` error.
    Build one fixed admitted schema with a guide-producing constraint, call
    `_apple_generated_object_type`, then `_apple_tool_wrapper` with the
    existing fake callback context, budgets, and session state so the real
    `apple_fm_sdk.Tool` construction reaches `FMBridgedToolCreate`. Assert a
    wrapper and its arguments schema are constructed. Do not create a
    `LanguageModelSession`, call `respond` or any generation API, or invoke a
    callback/handler.
  - Regression proof: focused fake bridge tests and this real construction
    test pass. The previous Apple S1 receipt may be retained as B5.2 evidence,
    but is not B5.1 proof and no matrix rerun is required.
  - Files/components: `src/dynamic_agent_runner/apple_foundation_models.py`,
    `tests/test_apple_foundation_models.py`, and
    `tests/test_live_apple_foundation_models.py`.
  - Evidence: `validation.md` (2026-08-30); the real construction test and
    focused fake bridge suite passed. The earlier matrix rerun remains B5.2
    evidence only.

- [ ] B5.2 [spike/tests] Establish whether Apple tool-choice control is both
      available through the current Python/Swift bridge and causally relevant
      to DAR's required-first scenarios before authorizing a production binding.
  - Evidence to explain: the earlier post-wrapper-fix receipt
    `ed567b59e6244eff9ef02ef851cb414d` has no `adapter_error`, but its S1--S4
    rows contain neither a native callback nor final text and S5 also lacks
    final text. The later receipt `457e6abd88a14409a39f2027137abd8b` confirms
    native callbacks and controlled invocations in every async S1--S5 row, but
    no qualifying final completion; S5 selected tools despite its no-tool
    instruction. Follow-up S1 wording can suppress surplus calls but not
    restore final text; no-tool plain text succeeds, while prompt-only JSON
    does not conform. This does not isolate a tool-choice cause.
  - RED: write a focused, no-model-session binding characterization for the
    exact Swift `GenerationOptions.ToolCallingMode` API, its macOS/Xcode
    availability floor, enum cases, and JSON/C/Python path. The installed
    bridge currently exposes only sampling, temperature, and response-token
    fields. When the native symbol is unavailable, the characterization must
    record that fact without a fallback or invented option.
  - Test-only route: use an isolated Swift Foundation Models probe under
    `/private/tmp`, compiled and run outside the Codex sandbox. It may exercise
    the native API directly but must not modify DAR or the vendored bridge.
    The Python/C inspection and this probe together establish the current
    missing-binding boundary and the native-control result.
  - Manual gate: run the temporary probe and native controls only with current
    explicit authorization that names the no-op tool, eligible host, modes,
    S5 control, and out-of-sandbox execution. Record only the approved
    authorization/evidence reference in `validation.md`, never credentials or
    raw model output.
  - Manual control: on an eligible Mac and outside the Codex sandbox when
    required, compare an approval-free no-op native tool under default
    `allowed` and under `required`, holding model, wrapper, prompt, and
    generation settings fixed. If the API supports a required-to-allowed
    transition, exercise that transition and record whether it yields exactly
    one callback followed by final text. Run the no-tool S5 control in the
    same environment to distinguish a final-response failure from selection.
  - Acceptance: record one bounded outcome in `validation.md`: unavailable
    API; no selection-policy delta; selection changes but no supported
    required-to-allowed exit or final text; or a reproducible
    required-to-allowed native result with the exact availability and bridge
    facts. Only the last outcome authorizes a separate test-first production
    task for a private DAR mapping of initial `required` and post-callback
    `allowed`. Do not add `disallowed`, public configuration, or a general
    binding API under B5.2.
  - Boundary: no DAR production code, approval interaction, external tool,
    package release, or claim that tool choice explains S5. The spike must not
    change callback authority, admitted schemas, or existing default `allowed`
    behavior.
