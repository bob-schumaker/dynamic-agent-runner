# Apple Foundation Models A4 Gateway Fallback Plan

Status: implementation-ready; not started

## Spec trace and objective

- Governing requirement: `spec.md` FR-18.
- Continuation gate: `a3-tasks.md` C4.3–C4.5.
- Objective: execute an active read-only MCP tool whose ordinary JSON Schema is
  not directly generable by Apple, without changing the upstream contract or
  bypassing DAR's existing coordinator.

## Current state

`apple_foundation_models.py` creates one generated Apple wrapper per active DAR
tool. `_apple_generated_object_type(...)` admits only its proven, restrictive
schema subset, so schemas with optional fields or descriptive keywords reject
before Apple session construction. The existing schema preflight reports only
`admissible` or `blocked`; it does not provide an A4 fallback, issue capability
tokens, or perform full JSON Schema validation.

`jsonschema` is already a package dependency. `authorized_tools.py` already
uses its validator selection/error types, but that validation path is not a
substitute for the A4 boundary: A4 must validate the original active schema
before coordinator entry.

## Scope and fixed decisions

In scope:

- Direct wrapper selection remains unchanged for losslessly Apple-generable
  active tools.
- One private Apple gateway wrapper handles every otherwise valid fallback tool
  in one response-local active context.
- Initial fallback eligibility is limited to a current, reviewed, read-only MCP
  binding. Generic DAR tools and write/delete MCP bindings remain direct-only
  and block if not Apple-generable.
- Classification is total over the active context: every active tool must be
  direct or eligible gateway. One blocked active tool prevents all wrapper and
  Apple-session construction; DAR must not silently expose a partial surface.
- The gateway decodes a bounded JSON object and validates it against the exact
  active upstream schema before it creates a `context.request(...)`.
- C4 preflight reports only a digest-bound `direct`, `gateway`, or `blocked`
  mode; its receipt contains no raw schema, token, arguments, OAuth material,
  or tool result.

Out of scope:

- Changing an upstream MCP schema, adding Apple-visible optional fields, or
  weakening direct translation.
- Side-effecting fallback tools, provenance envelopes, a second Apple session,
  a new provider API, or a generic schema gateway usable outside the active
  Apple callback context.
- Live Fastmail/O7 invocation. That remains C4.4 after fake parity evidence,
  eligible-Mac evidence, and human review.

## Gateway contract

The sole Apple-visible fallback tool uses this fixed generated schema:

```json
{
  "type": "object",
  "properties": {
    "tool_token": {"type": "string"},
    "arguments_json": {"type": "string"}
  },
  "required": ["tool_token", "arguments_json"],
  "additionalProperties": false
}
```

For each `create_request(...)`, private wrapper preparation creates a new
response-local mapping from an opaque random capability token to exactly one
fallback `RegisteredTool`, its original `input_schema`, and its currentness
guard. Tokens must not encode a DAR tool id, remote name, schema, or sequence
number. The single gateway's Apple-visible description contains a catalog of
only those opaque tokens and each existing model-safe tool description. It has
one entry per active fallback tool and is capped at 16 KiB UTF-8; an over-limit
catalog blocks the active context rather than truncating or exposing identities.
Tokens, the catalog, and mapped metadata never enter traces, receipts, or
errors.

The mapping exists only until the callback session closes. Its lock-protected
resolve-and-consume transition rechecks session liveness and currentness, then
returns one target at most once. It is cleared on normal completion,
cancellation, provider interruption, and session-construction failure, so
unknown, inactive, stale, racing, and reused tokens fail closed.

The gateway accepts an `arguments_json` value only when all of the following
hold:

- Its UTF-8 encoding is at most 16 KiB.
- A duplicate-key-detecting parser yields one JSON object, contains no non-finite
  numeric constant, has nesting depth at most 16, and contains at most 64
  object keys in total.
- The outer Apple envelope is parsed with the same duplicate-key and non-finite
  rejection before token lookup; duplicate `tool_token` or `arguments_json`
  keys cannot become last-wins values.
- The selected tool is still in the exact active context and is still a
  read-only MCP binding.
- `jsonschema` accepts the original schema with `check_schema`, has no external
  or recursive reference/resource identifier (`$ref`, `$dynamicRef`,
  `$recursiveRef`, or `$id`), and uses only a built-in recognized meta-schema.
  It must not retrieve network or filesystem resources.
- Every declared `format` is supported by an explicit `FormatChecker`; an
  unknown or unavailable format blocks fallback eligibility. Full validation
  accepts the decoded object with that checker.

The response-local validator is prepared from the original schema before Apple
session construction. Each gateway callback claims the shared callback budget
immediately after its session-liveness check, before envelope/token/JSON work,
matching the direct wrapper path. It then validates its decoded object with the
prepared validator immediately before `context.request(...)`; every rejected
callback consumes one provider attempt but has zero coordinator entry,
underlying dispatch, handler, hook, state, or result effect.

## Architecture and data flow

```text
active trusted tool context
  -> classify each tool
       -> direct: existing per-tool generated wrapper
       -> fallback: read-only current MCP binding + valid JSON Schema
  -> one direct wrapper per direct tool, plus one gateway only if fallback exists
  -> Apple callback envelope
  -> response-local token lookup and consume
  -> bounded JSON decode
  -> exact original-schema validation
  -> existing context.request / coordinator / registry dispatch
```

The gateway callback must share the existing `_AppleCallbackSessionState`,
`ProviderCallbackBudget`, executor-loop handoff, guardrail runner, result
commit guard, and terminal-outcome translation. It must use the mapped DAR tool
id only after successful private lookup. It must never route a decoded payload
directly to a registry handler.

Direct and gateway wrappers share one callback budget. A rejected gateway
payload consumes one slot but never enters the coordinator; a valid gateway
callback consumes exactly one slot before entering it, matching the direct-wrapper
behavior.

## Implementation work packages

### A4.1 — Characterize selection and classify active tools

- Touch points: `src/dynamic_agent_runner/apple_foundation_models.py`,
  `tests/test_apple_foundation_models.py`.
- Start with RED tests for direct-only selection, a Fastmail-like optional or
  descriptive schema selecting gateway mode, invalid JSON Schema blocking, and
  non-read-only/generic tools remaining ineligible for fallback. Include mixed
  direct/gateway success and one blocked active tool preventing session
  construction for the entire context.
- Replace the binary direct-only preflight and update its callers in this slice
  to return `direct`, `gateway`, or `blocked` without exposing schemas.
- Done when wrapper preparation emits direct wrappers unchanged and exactly one
  generated gateway wrapper only when at least one eligible fallback tool is
  active. No fallback must create an Apple session for a blocked tool.

### A4.2 — Build the response-local capability and decode boundary

- Touch points: `src/dynamic_agent_runner/apple_foundation_models.py`,
  `tests/test_apple_foundation_models.py`.
- Start with RED callback tests for unknown, reused, inactive, stale, malformed,
  oversized, duplicate-key, non-object, non-finite, over-depth, and over-key
  payloads, including duplicate outer-envelope keys and two racing callbacks
  using one token. Cover token-table cleanup on normal completion, cancellation,
  provider interruption, and session-construction failure. Each rejected
  callback consumes its provider-budget attempt but asserts zero
  coordinator/handler/state dispatch.
- Implement a lock-protected private token table with response-close cleanup,
  a bounded duplicate-key-safe outer-envelope parser, and a bounded inner JSON
  decoder. Do not use raw `json.loads(...)` without duplicate-key and
  non-finite rejection.
- Done when the gateway accepts only the fixed envelope and token data cannot
  be recovered from the generated tool name, trace, exception, or receipt; its
  bounded Apple-visible catalog lets the model select only mapped active tools.

### A4.3 — Validate then reuse the existing coordinator ingress

- Touch points: `src/dynamic_agent_runner/apple_foundation_models.py`,
  `tests/test_apple_foundation_models.py`, and focused existing coordinator
  regression modules only if their assertions need extension.
- Start with RED tests showing `check_schema` occurs before session creation and
  decoded arguments receive full exact-schema validation before
  `context.request(...)`. Cover external/recursive-reference rejection,
  unsupported-format rejection, and invalid supported-format values without
  weakening optionality, descriptions, format/pattern, or any other schema
  constraint.
- Route only a validated, current mapped tool through the same callback path as
  direct wrappers.
- Done when valid gateway dispatches exactly once and preserves coordinator
  approvals, guardrails, lifecycle hooks, state, trace redaction, result
  shaping, cancellation, and terminal outcomes.

### A4.4 — Prove direct/gateway parity and regenerate C4 preflight

- Touch points: `tests/test_apple_foundation_models.py`,
  `tests/test_dar_authoring_mcp_surfaces.py`, and, only after the classifier is
  implemented, the host/CLI tests and surfaces needed for C4's redacted
  receipt.
- Start with RED parity tests for callback-budget races, cancellation and late
  callbacks, currentness drift, approval decisions, guardrails, lifecycle
  ordering, trace/result redaction, catalog redaction, and one underlying
  dispatch.
- Change the reviewed-surface preflight only after it can return the new
  `direct|gateway|blocked` classification. Its CLI bridge, if added, must be
  covered by host and CLI tests and emit only the mode and tool-set digest.
- Done when C4.3 can record a current reviewed Fastmail receipt without raw
  tool data. A `gateway` receipt does not authorize O7 by itself.

## Verification strategy

| Requirement | Deterministic evidence | Gate |
| --- | --- | --- |
| FR-18 direct preference | direct wrapper selection regression | focused Apple fake tests |
| FR-18 closed envelope and token bounds | malformed/replay/bounds RED→GREEN tests | focused Apple fake tests |
| FR-18 exact schema preservation | `check_schema` and full-validation ordering tests | focused Apple fake tests |
| Coordinator ownership | approval/currentness/guardrail/state/trace parity tests | focused Apple and sealed-host tests |
| C4.3 receipt | reviewed-surface and CLI redaction tests | focused MCP-surface/authoring CLI tests |
| Release readiness | full suite and package checks | commands below |

Run focused RED/GREEN tests for each package first, then:

```sh
poetry run pytest -q
poetry run ruff check src tests
poetry check
poetry build
```

Run the project’s focused pre-commit checks after the documentation/task update.
Unit tests must use fake Apple SDKs and fake MCP tools only; they must not call
Fastmail, OAuth, or a live Apple model. The human-authorized eligible-Mac
preflight occurs only after A4.1–A4.4 are green.

## Risks and stop conditions

| Risk | Mitigation | Blocks |
| --- | --- | --- |
| Gateway broadens an upstream contract | validate the exact original schema before coordinator entry | callback dispatch |
| Token leaks or replay | opaque random response-local single-use tokens; redacted errors/receipts | session construction and C4 evidence |
| Rejected callbacks consume budget or mutate state unexpectedly | test claim-before-parse parity and zero coordinator ingress | parity sign-off |
| Gateway becomes a side-effect bypass | accept fallback only for current reviewed read-only MCP bindings | A4 implementation |
| Apple envelope cannot be proven admissible | use only the A2-proven closed object schema | session construction |

If the fixed envelope cannot be generated by the installed Apple SDK, or direct/
gateway parity cannot be established with fakes, leave unsupported tools blocked
and do not run C4.4/O7. There is no compatibility fallback that weakens schema
validation or exposes raw upstream descriptors to Apple.
