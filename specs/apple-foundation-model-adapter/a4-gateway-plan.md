# Apple Foundation Models A4 Gateway Fallback Plan

Status: planned

## Objective

Support active upstream MCP tools whose JSON Schema cannot be generated as an
Apple type, without changing their contract or bypassing DAR policy.

## Fixed decisions

- Direct wrappers remain the preferred fast path.
- Unsupported schemas select a single Apple-admissible gateway only when the
  gateway eligibility and exact-validation contract below are available;
  otherwise they reject before Apple session creation.
- Gateway payloads carry only a per-response opaque capability token and bounded
  JSON arguments; DAR ids, remote names, and model-supplied schemas are rejected.
- DAR validates decoded arguments against the exact original schema before
  coordinator entry. It preserves currentness, approval, hooks, tracing, state,
  result shaping, and callback budgets.
- Raw schemas, payloads, OAuth material, and results are never retained in
  receipts or checked-in evidence.
- The fixed envelope is the closed, fully-required object `{tool_token,
  arguments_json}`. Tokens are per-response capabilities for fallback tools
  only. The parser rejects payloads over 16 KiB UTF-8, depth 16, or 64 object
  keys; it also rejects duplicate keys, non-object JSON, and non-finite values.
- Full JSON Schema validation against the original active schema occurs before
  `context.request`; registry preparation alone is insufficient. Initial A4
  scope is read-only MCP bindings. Side-effect/provenance envelopes require a
  separate design.

## Implementation plan

1. Write RED selection and payload-boundary tests: direct schemas retain direct
   wrappers; Fastmail-like optional/descriptive schemas select the gateway;
   malformed, oversized, duplicate-key, unknown, inactive, and stale payloads
   fail before validation or dispatch.
2. Implement the private gateway wrapper and active-tool mapping using only
   A2-proven Apple schema features. Do not add a second session or provider API.
3. Decode with bounded, duplicate-key-safe JSON; resolve only the current
   fallback token; run `check_schema` plus full validation against the original
   active schema; then enter the existing coordinator for the mapped tool ID.
4. Add RED/GREEN parity tests for upstream validation failures, approvals,
   guardrails, lifecycle ordering, trace redaction, cancellation, currentness,
   and callback-budget races. Assert zero dispatch on every rejected payload.
5. Re-run fake sealed-host coverage and the human-authorized Fastmail preflight.
   Require direct/gateway parity for budget claims, currentness, approval,
   guardrails, hooks, state, trace/result shaping, cancellation, and one
   underlying dispatch. Record only the surface digest, selected mode, status,
   and dispatch count;
   require human review before O7.

## Verification

Use focused RED/GREEN tests for every step, then `poetry run pytest -q`,
`poetry run ruff check src tests`, `poetry check`, package checks, and focused
pre-commit. Unit tests must not call Fastmail, OAuth, or a live Apple model.
