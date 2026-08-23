# Tool Invocation Coordinator Task List

Status: implemented and validated

## Slice 0 — Baseline and Contract

- [x] T0.1 [tests] Add focused regression tests for direct and model-loop
      approval, malformed approval-required arguments, hook order, preserved
      model-loop observation, non-approval failure behavior, handler failure,
      `direct_model_only` behavior, and direct node-input snapshots on pauses.
  - Spec: FR-1 through FR-3
  - Files/components: `tests/test_executor.py`, `tests/test_hooks.py`,
    `tests/test_tracing.py`
  - RED: malformed approval-required model arguments currently pause before
    registered-tool input validation.

- [x] T0.2 [docs] Reconcile approval-interruption records with the already
      verified model-loop pause baseline and link dependent specs to this slice.
  - Spec: Existing Baseline
  - Files/components: `specs/approval-interruption-resume/`, `specs/README.md`

## Slice 1 — Prepared Registry Invocation

- [x] T1.1 [tests] Add RED registry tests for non-invoking preparation of a
      registered tool and malformed arguments, plus dispatch through the exact
      prepared value.
  - Spec: Coordinator Contract, FR-2
  - Files/components: `tests/test_registry.py`
  - Verify: preparation has no handler side effect, retains one resolved tool
    and copied validated argument mapping for dispatch, and does not apply
    direct/model exposure policy.

- [x] T1.2 [implementation] Factor registry preparation and prepared dispatch
      so the coordinator can validate one resolved tool and normalized copied
      arguments before approval, then invoke that same value without applying
      origin-specific exposure policy during preparation.
  - Spec: Coordinator Contract, FR-2
  - Files/components: `src/dynamic_agent_runner/registry.py`

## Slice 2 — Internal Coordinator and Model-Loop Migration

- [x] T2.1 [tests] Add RED tests proving an approval-required coordinator
      request validates before approval; an unresolved approval runs no hooks,
      retry attempt, tool-result/node-output/failure-policy state write, or
      handler; direct node-input snapshot remains; and model-loop unknown,
      malformed, paused, and dispatched observation order is preserved.
  - Spec: FR-1, FR-2, FR-4
  - Files/components: new focused coordinator test module or
    `tests/test_executor.py`

- [x] T2.2 [implementation] Add dependency-light internal coordinator request
      and outcome types plus the async dispatch operation. Return a `ToolResult`
      or `ApprovalInterruption`; leave `WorkflowInterruptedResult` wrapping to
      the executor. Keep direct retry attempts inside the coordinator and report
      them through the executor-provided retry observer.
  - Spec: Coordinator Contract, FR-1 through FR-4
  - Files/components: new `src/dynamic_agent_runner/tool_invocation.py` or an
    equivalent internal module selected to avoid circular imports

- [x] T2.3 [implementation] Route normalized model-loop requests through the
      coordinator and remove the executor model-loop path's direct registry
      dispatch.
  - Spec: FR-1, FR-3
  - Files/components: `src/dynamic_agent_runner/executor.py`

## Slice 3 — Direct-Step Migration

- [x] T3.1 [tests] Add RED parity tests for direct retries, fallback/error and
      non-approval invalid-input behavior, output/state recording, trace
      compatibility, hooks, and `direct_model_only` error translation after
      coordinator migration.
  - Spec: FR-3
  - Files/components: `tests/test_executor.py`, `tests/test_tracing.py`,
    `tests/test_hooks.py`

- [x] T3.2 [implementation] Route direct `tool_use_step` dispatch through the
      coordinator while retaining executor-owned node-output and control-flow
      behavior.
  - Spec: FR-1, FR-3
  - Files/components: `src/dynamic_agent_runner/executor.py`

- [x] T3.3 [implementation] Delete only duplicated executor dispatch branches
      that are covered by coordinator parity tests.
  - Spec: FR-3
  - Files/components: `src/dynamic_agent_runner/executor.py`

## Slice 4 — Completion Evidence

- [x] T4.1 [validation] Run focused regression, full test, lint, docs, and
      package-build gates from `plan.md`.
- [x] T4.2 [docs] Update this feature's validation record and dependent future
      specs to show the completed coordinator boundary without enabling
      provider, interpreter, guardrail, or sandbox capabilities.
