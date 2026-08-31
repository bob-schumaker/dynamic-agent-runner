# Tool Invocation Coordinator Implementation Plan

## Objective

Replace the executor's duplicated direct-step and model-loop pre-handler paths
with one internal async coordinator, preserving established behavior while
validating approval-required arguments before approval.

## Current State

`executor.py` currently owns two partially overlapping paths. Direct steps add
retry, fallback, output recording, and `tool_invocation` compatibility events;
model loops add exposure checks, call ids, and loop continuation. Both own
approval, tracing, lifecycle hooks, and registry dispatch. The coordinator must
centralize only the shared safety boundary without absorbing caller-specific
continuation behavior prematurely.

## Technical Approach

1. Add a narrow registry-owned prepared-invocation pair to the `ToolRegistry`
   operational protocol: prepare one resolved tool plus copied validated
   arguments without a handler side effect, then invoke that exact opaque value.
   Preparation does not apply origin exposure; prepared dispatch retains the
   registry's current direct-callability behavior.
2. Define dependency-light internal request/outcome values: `ToolResult` or
   `ApprovalInterruption`, which the executor wraps as its workflow result. Do
   not import executor implementation details into registry code or expose the
   types from `dynamic_agent_runner.__init__`.
3. Move origin-specific exposure validation, prepared-argument approval
   interruption creation, shared tool lifecycle events, hooks, and registry
   dispatch into the coordinator. The coordinator owns direct retry attempts and
   emits them through a narrow executor-supplied retry observer; the executor
   persists retry records and retains state keys, compatibility events, failure
   fallback, and node output.
4. Migrate model-loop dispatch first, because it has no retry/fallback policy.
   Then migrate direct-step dispatch, retaining its retry and output behavior.
5. Delete only the duplicated pre-handler code after focused parity tests pass.

## Boundaries

- The registry remains the sole handler dispatcher and registered-tool input
  validation owner; its narrow validation-protocol addition requires built-in
  and fake registry implementations to migrate together.
- The executor remains the workflow-control-flow, model-loop, node-output, and
  final-result authority. It records direct node input before coordinator entry
  and persists state results, retry records, errors, and output afterward.
- Lifecycle hooks remain observational and cannot rewrite the invocation.
- Approval outcomes, provider callbacks, interpreters, sandbox tooling, and
  tool guardrails are not implemented in this slice.

## Compatibility and Rollout

This is an internal extraction plus one narrow `ToolRegistry` operational
protocol addition for non-invoking input validation. Existing package-root
result classes, trace event names, and workflow manifest fields remain
unchanged. The only intentional behavioral tightening is that malformed
approval-required arguments fail before an approval interruption is emitted;
non-approval failure behavior remains unchanged. Rollback is a source-level
revert of the coordinator migration; no persisted state or migration is
introduced.

## Work Packages

### WP1 — Freeze current behavior

- Dependency: none
- Deliverables: focused regression tests for direct and model-loop approved,
  malformed approval-required, paused, non-approval failure, handler-failure,
  `direct_model_only`, and direct-node-input-snapshot behavior; approval
  documentation drift reconciled to the verified model-loop pause baseline.
- Exit criteria: tests describe the required ordering without relying on private
  executor helper names, including the preserved model-loop observation before
  approval and the unchanged non-approval direct failure path.

### WP2 — Add internal validation and coordinator contracts

- Dependency: WP1
- Deliverables: opaque registry-owned prepared-invocation operations and
  internal request/outcome/coordinator types, where an interruption remains an
  `ApprovalInterruption` until executor wrapping.
- Exit criteria: a RED test proves preparation has no handler side effect; a
  GREEN test proves preparation and dispatch use one resolved tool and copied
  argument mapping without conflating origin-specific exposure policy.

### WP3 — Migrate model-loop dispatch

- Dependency: WP2
- Deliverables: model-loop callers use the coordinator and retain call-id,
  model-loop tracing, approval interruption, and transcript behavior.
- Exit criteria: existing model-loop tests plus new event/hook ordering tests
  pass; the executor model-loop path delegates registry dispatch only through
  the coordinator.

### WP4 — Migrate direct-step dispatch

- Dependency: WP3
- Deliverables: direct steps use the coordinator while preserving retry,
  fallback/error, state, output, and compatibility-event behavior.
- Exit criteria: direct-step success, retry, fallback, failure, and approval
  tests pass; duplicated dispatch code is removed only after parity is proven.

### WP5 — Verify and document the boundary

- Dependency: WP4
- Deliverables: related specs/status records, validation log, and focused/full
  verification evidence.
- Exit criteria: the corpus names the coordinator as the only supported future
  bridge; no provider/interpreter implementation is implied.

## Validation Strategy

Run test-first work in each work package. Required focused commands:

```bash
poetry run pytest tests/test_registry.py tests/test_executor.py \
  tests/test_hooks.py tests/test_tracing.py -q
poetry run ruff check src tests
```

Final gates:

```bash
poetry run pytest -q
poetry build
make -C docs html
```

Any changed event ordering, hook timing, retry record, model-tool transcript, or
non-approval failure behavior is a blocking regression unless explicitly covered
by the approval-required validation-before-approval tightening.
