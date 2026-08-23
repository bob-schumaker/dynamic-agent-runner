# Tool-Input Guardrail V2 Plan

## Objective

Execute caller-registered pass-or-abort tool-input guardrails through DAR's
shared invocation coordinator.

## Ordering Contract

For direct steps and model-loop calls:

1. resolve effective tool exposure and normalize arguments;
2. validate registered-tool input;
3. run declared `tool_input` guardrails in manifest order on a copied subject
   mapping containing phase, tool id, node id, optional call id, and validated
   arguments;
4. on abort, emit redacted guardrail observations and raise
   `GuardrailExecutionError` without approval, hooks, retry, or handler use;
5. on pass, continue existing approval, lifecycle, retry, registry, trace, and
   result behavior unchanged.

## Boundaries

- Reuse `InMemoryGuardrailRegistry`, `GuardrailDecision`, and
  `GuardrailResult`; do not add provider adapters or public coordinator APIs.
- Only `pass` and `abort` are live for tool input.
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
  missing-adapter, result-mismatch, and ordered multi-declaration behavior.
- Assert no approval, hook, retry, registry invocation, or handler side effect
  follows an abort.

### WP2 — Coordinator adoption

- Add a narrow coordinator collaborator seam for tool-input guardrail lookup
  and execution after guarded-path validation.
- Preserve existing input-guardrail behavior and all non-tool guardrail phases.

### WP3 — Validation and records

- Run focused guardrail/executor/tracing/capability tests, full tests, Ruff,
  package build, and docs build.
- Update the feature spec, validation record, capability status if live
  tool-input coverage is exposed, and corpus index only from observed evidence.

## Delivery Readiness

- Delivery target: `src/dynamic_agent_runner/`, `tests/`, and this spec package.
- Primary implementation surfaces: `executor.py`, `guardrails.py`,
  `tests/test_executor.py`, and `tests/test_tracing.py`; capability reporting is
  conditional on exposing V2 coverage.
- Implementation route: TDD in the work-package order above.
- Acceptance: abort and missing-adapter behavior fail closed before approval or
  handler invocation; pass behavior remains compatible for direct and model
  origins.
- Status: implementation-ready; this plan is ready to execute under its stated
  gates.
