# Tool-Input Guardrail V2 Plan

## Objective

Execute caller-registered pass-or-abort tool-input guardrails through DAR's
shared invocation coordinator.

## Ordering Contract

For direct steps and model-loop calls:

1. resolve effective tool exposure and normalize arguments;
2. validate registered-tool input;
3. run declared `tool_input` guardrails in manifest order on a copied subject
   mapping containing phase, tool id, node id, optional call id, and recursively
   copied validated arguments;
4. emit `guardrail_started`, then exactly one redacted pass, abort, or error
   observation; on abort or error, raise `GuardrailExecutionError` without
   approval, tool lifecycle hooks, retry, state-result writes, or handler use;
5. on pass, continue existing approval, lifecycle, retry, registry, trace, and
   result behavior unchanged.

## Boundaries

- Reuse `InMemoryGuardrailRegistry`, `GuardrailDecision`, and
  `GuardrailResult`; do not add provider adapters or public coordinator APIs.
- The executor selects declarations and supplies one private guardrail-runner
  callback to the coordinator. The callback receives declarations and the
  copied subject; it owns adapter lookup, result id/phase validation, redacted
  observations, and `GuardrailExecutionError` normalization. Error observations
  carry declaration id, phase, node/tool ids, optional call id, and reason
  category only; a terminal `workflow_error` follows.
- Only `pass` and `abort` are live for tool input.
- Every V2 `tool_input` declaration is required and must have a nonblank id;
  empty and whitespace-only ids fail runtime-manifest validation during
  preparation. Optional/degraded tool-input policy is deferred.
- `behavior_on_tripwire` is omitted (which means `abort`) or `abort`; other
  values fail runtime-manifest validation during preparation rather than being
  interpreted as an unsupported decision.
- A result must match its declaration id and `tool_input` phase. Missing
  adapters, handler errors, malformed results, and mismatches fail closed.
- Multiple declarations stop at the first abort or error; unguarded requests
  retain their current validation timing.
- Do not mutate validated arguments. Any future mutation must restart
  validation, guardrails, and approval in a separately approved slice.
- The coordinator remains the only route to the handler.

## Work Packages

### WP1 — Characterize and test the boundary

- Add RED executor/tracing tests for direct and model tool-input pass, abort,
  missing-adapter, missing/whitespace-id, unsupported behavior policy,
  result-mismatch, malformed guarded input, and ordered multi-declaration
  behavior.
- Assert no approval, tool lifecycle hook, retry, registry invocation, or
  handler side effect
  follows an abort or error; node/workflow hooks that precede tool dispatch are
  preserved, while `before_tool`/`after_tool` do not run.
- Assert direct and model-loop missing-adapter, handler-error, malformed-result,
  and id/phase-mismatch paths emit `guardrail_started`, `guardrail_errored`, and
  redacted terminal `workflow_error` in order.
- Assert nested mutation of the guardrail subject cannot alter an approval
  interruption or handler arguments.

### WP2 — Coordinator adoption

- Add a narrow private callback seam for executor-owned declaration selection
  and tool-input guardrail execution after guarded-path validation, for both
  approval-required and non-approval requests.
- Preserve existing input-guardrail behavior and all non-tool guardrail phases.

### WP3 — Validation and records

- Run focused guardrail/executor/tracing/capability tests, full tests, Ruff,
  package build, and docs build.
- Update the feature spec, validation record, capability status if live
  tool-input coverage is exposed, and corpus index only from observed evidence.

## Delivery Readiness

- Delivery target: `src/dynamic_agent_runner/`, `tests/`, and this spec package.
- Primary implementation surfaces: `executor.py`, `guardrails.py`,
  `validation.py`, `tests/test_executor.py`, `tests/test_tracing.py`, and
  `tests/test_validation.py`; capability reporting is conditional on exposing
  V2 coverage.
- Implementation route: TDD in the work-package order above.
- Acceptance: abort, missing-adapter, and invalid policy behavior fail closed
  before approval or handler invocation; pass behavior remains compatible for
  direct and model origins.
- Status: implemented; observed command evidence is recorded in
  [`tool-input-validation.md`](tool-input-validation.md).
