<!-- markdownlint-disable MD013 -->
# Apple Foundation Models A2 Task List

Status: approved; implementation not started

## B0 — Native harness diagnosis

- [x] B0.1 [tests] Capture a minimal standalone and pytest-native Apple
      generation comparison with redacted phase/status evidence.
  - Evidence: `validation.md` (2026-08-26); status 255 did not reproduce, but
    pytest emitted a repeatable SDK-native destructor error at process teardown.
- [ ] B0.2 [analysis] Identify the status-255 differentiator or document the
      bounded environmental limitation and authoritative standalone gate.
- [ ] B0.3 [spike] Pin and demonstrate the SDK `Tool`, `GenerationSchema`, and
      `GeneratedContent` APIs for every admitted A2 schema shape and callback
      argument conversion.

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
      unresolved produces `WorkflowInterruptedResult`, not model failure.

## B2 — Schema-safe Apple wrappers

- [ ] B2.1 [tests] Add RED schema/name-translation tests for the admitted B0
      subset and fail-closed rejection before session creation.
- [ ] B2.2 [implementation] Generate one Apple wrapper per exposed active-node
      DAR tool and provide no wrapper for inactive or unexposed tools.

## B3 — Callback execution

- [ ] B3.1 [tests] Add RED/GREEN callback tests proving coordinator validation,
      exactly-once approved dispatch, lifecycle/trace/state preservation, and
      `ToolResult.model_facing_output` serialization.
- [ ] B3.2 [implementation] Route Apple callbacks through the coordinator and
      convert approval interruptions to the provider-aware DAR interruption.
- [ ] B3.3 [tests] Prove the atomic provider-callback budget caps N+1 calls,
      emits the provider-origin exhaustion trace, and aborts the session.
- [ ] B3.4 [tests] Prove cancellation before and during a callback prevents
      later dispatch, result writes, or post-session state mutation.

## B4 — Live evidence and documentation

- [ ] B4.1 [tests] Add an opt-in/manual eligible-Mac callback smoke using a
      no-side-effect sentinel; retain exactly-once approval proof in fakes.
- [ ] B4.2 [docs] Document A2 capabilities, interruption behavior, schema
      limits, and the status-255 harness result.
- [ ] B4.3 [validation] Run focused tests, full suite, Ruff, metadata, package
      build, and the eligible-Mac live callback gate or record its exact skip.
