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

## B1 — Provider ingress contract

- [ ] B1.1 [tests] Add RED tests for active-node allowlisting, callback request
      correlation, and no direct handler/registry path.
- [ ] B1.2 [implementation] Define the internal Apple callback request and
      provider-aware interruption contract over the shared coordinator.
- [ ] B1.3 [tests] Prove unresolved, denied, cancelled, and expired approvals
      produce interruption before hooks, registry dispatch, state writes, or a
      handler invocation.

## B2 — Schema-safe Apple wrappers

- [ ] B2.1 [tests] Add RED schema-translation tests for supported schemas and
      fail-closed rejection of unsupported constructs before session creation.
- [ ] B2.2 [implementation] Generate one Apple wrapper per exposed active-node
      DAR tool and provide no wrapper for inactive or unexposed tools.

## B3 — Callback execution

- [ ] B3.1 [tests] Add RED/GREEN callback tests proving coordinator validation,
      exactly-once approved dispatch, lifecycle/trace/state preservation, and
      `ToolResult.model_facing_output` serialization.
- [ ] B3.2 [implementation] Route Apple callbacks through the coordinator and
      convert approval interruptions to the provider-aware DAR interruption.
- [ ] B3.3 [tests] Prove tool iteration and completion limits stop further
      Apple callback dispatch.

## B4 — Live evidence and documentation

- [ ] B4.1 [tests] Add opt-in eligible-Mac live callback tests for an approved
      tool and a denied action with a no-handler assertion.
- [ ] B4.2 [docs] Document A2 capabilities, interruption behavior, schema
      limits, and the status-255 harness result.
- [ ] B4.3 [validation] Run focused tests, full suite, Ruff, metadata, package
      build, and the eligible-Mac live callback gate or record its exact skip.
