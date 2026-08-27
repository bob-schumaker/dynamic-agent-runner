<!-- markdownlint-disable MD013 -->
# Apple Foundation Models A2 Task List

Status: approved; implementation not started

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
- [ ] B0.3 [spike] Pin and demonstrate the SDK `Tool`, `GenerationSchema`, and
      `GeneratedContent` APIs; record the admitted A2 schema capability matrix,
      Apple tool-name constraints, supported callback argument conversion, and
      rejected schema forms in `a2-plan.md`.

## B1 — Provider ingress contract

- [ ] B1.1 [tests] Add RED parity tests before extracting the executor-private
      coordinator, including direct/model-loop behavior and provider-origin
      request correlation.
- [ ] B1.2 [implementation] Extract a dependency-light internal coordinator,
      migrate existing callers, and define the non-wire active adapter context.
- [ ] B1.3 [tests] Prove non-Apple wire kwargs/traces contain no adapter context
      or registry/state reference; stale and raw descriptor contexts fail closed.
- [ ] B1.4 [implementation] Define typed provider interruption, synchronous
      exact-fingerprint decision collaborator, and atomic callback budget.
- [ ] B1.5 [tests] Prove approved dispatches once; denied/cancelled/expired and
      unresolved approvals prevent handler/hook/retry/registry/state effects;
      exposure and argument validation precede decision resolution and
      pre-invocation hooks for every outcome; exact approved normalized
      arguments dispatch once; mismatched, replayed, and unknown decisions fail
      closed; unresolved produces an executor-visible
      `WorkflowInterruptedResult`, not a model failure or retry.

## B2 — Schema-safe Apple wrappers

- [ ] B2.1 [tests] Add RED schema/name-translation tests for the B0 capability
      matrix; prove session construction receives exactly the effective
      model-facing selected-tool allowlist, invalid or colliding names fail
      closed, and inactive, unexposed, stale-context, and raw-descriptor tools
      never reach Apple session creation.
- [ ] B2.2 [implementation] Generate one Apple wrapper per exposed active-node
      DAR tool and provide no wrapper for inactive or unexposed tools.

## B3 — Callback execution

- [ ] B3.1 [tests] Add RED/GREEN callback tests proving coordinator validation,
      exactly-once approved dispatch, lifecycle/trace/state preservation, and
      `ToolResult.model_facing_output` serialization.
- [ ] B3.2 [implementation] Route Apple callbacks through the coordinator and
      convert unresolved approval to the provider-aware DAR interruption;
      denied, cancelled, and expired decisions remain non-dispatch outcomes.
- [ ] B3.3 [tests] Prove the atomic provider-callback budget derives from the
      active DAR tool-call limit, translates zero and one correctly, caps N+1
      racing callbacks, emits the provider-origin exhaustion trace, and returns
      the declared DAR-controlled termination outcome.
- [ ] B3.4 [tests] Prove cancellation before and during a callback prevents
      later dispatch, result writes, post-session state mutation, or re-entrant
      event-loop use; prove callbacks after session completion fail closed.
- [ ] B3.5 [tests] Prove unresolved interruption, callback-budget exhaustion,
      and cancellation abort and clean up the Apple session exactly once, with
      no later callback dispatch or state mutation.

## B4 — Live evidence and documentation

- [ ] B4.1 [tests] Add an opt-in/manual eligible-Mac callback smoke using a
      safely observable no-side-effect sentinel to show callback entry into DAR
      before handler execution and denied approval prevents the handler; retain
      exactly-once approval proof in fakes.
- [ ] B4.2 [docs] Document A2 capabilities, interruption behavior, schema
      limits, and the status-255 harness result.
- [ ] B4.3 [validation] Record RED/GREEN focused A2 test module results, then
      run and record `poetry run pytest -q`, `poetry run ruff check src tests`,
      `poetry check`, `poetry build`, and the opt-in eligible-Mac callback gate
      or its precise skip, with redacted evidence identifiers/outputs.
