<!-- markdownlint-disable MD013 -->
# Apple Foundation Models A2 Implementation Plan

Status: approved for implementation planning; no implementation started

## Scope and fixed decisions

A2 adds Apple Foundation Models tool use without transferring tool authority to
the Apple provider. This plan is governed by `spec.md` FR-12 and FR-16.

- Generate one Apple wrapper for each tool exposed to the active DAR node.
- Each `Apple Tool.call(...)` callback creates a DAR invocation request and
  dispatches it through the shared tool-invocation coordinator.
- A callback may never invoke a registered handler or registry directly.
- An unresolved approval returns a provider-aware DAR interruption before any
  handler runs; A2 does not wait for or implement durable approval resume.
- Preserve coordinator-owned argument validation, exposure, hooks, tracing,
  state, redaction, result shaping, and iteration/completion limits.
- Reject an untranslatable DAR tool schema before creating an Apple session.

Out of scope: streaming, multimodal input, persistent Apple sessions, PCC,
HTTP serving, direct callbacks, durable approval resume, and broad changes to
the executor model-selection path.

## Architecture

`apple_foundation_models.py` remains the provider adapter. A new internal
Apple-provider bridge receives the active run/node-scoped tool exposure and a
coordinator collaborator. It translates only the exposed tool schemas into
Apple wrappers. Each wrapper turns Apple arguments into a coordinator request
with run, node, tool, call, and correlation context. The coordinator returns a
model-facing tool result or an approval interruption. The latter is translated
to a provider-aware interruption that aborts Apple generation without calling a
handler; the executor renders the existing DAR interrupted-workflow result.

The bridge must not own approval policy, registry invocation, lifecycle hooks,
trace emission, state writes, or redaction. Those remain coordinator behavior.

## Milestones

### B0 — Native harness diagnosis

Create a minimal, redacted standalone/pytest comparison that captures Python,
SDK, macOS, availability, session-construction, and generation phase evidence.
Find a reproducible differentiator for native status 255, or record an
environment-limited result and retain standalone execution as the live gate.
No retry or pytest-specific production behavior is permitted.

### B1 — Provider-ingress and interruption contract

Define internal, dependency-light request/outcome types for Apple callback
ingress and provider-aware interruption. Extend the coordinator only where it
lacks data needed to preserve run/node/tool/call correlation. Add fake RED tests
that prove no handler, registry, hook, or state mutation happens before an
unresolved approval is surfaced.

### B2 — Schema-safe wrapper preparation

Implement one wrapper per active-node exposed tool. Translate DAR JSON Schema
to Apple `GenerationSchema` without loss, rejecting unsupported constructs
before session creation. Prove inactive-node and non-exposed tools never reach
the Apple session.

### B3 — Coordinator dispatch and response translation

Route callback arguments through the coordinator, serialize only
`ToolResult.model_facing_output` back to Apple, and preserve result redaction,
hooks, trace/state behavior, tool limits, and completion behavior. Translate an
approval interruption into the provider-aware executor interruption selected by
this plan.

### B4 — Evidence and live validation

Add fake tests for validation ordering, allowlist, single dispatch, approvals,
rejections/cancellation/expiry/unresolved outcomes, traces, redaction, limits,
and schema rejection. Add an opt-in eligible-Mac live callback test. Run the
native-harness result from B0 separately from deterministic test gates.

## Touch points

- `src/dynamic_agent_runner/apple_foundation_models.py`
- `src/dynamic_agent_runner/tool_invocation.py` and executor interruption seams
- `src/dynamic_agent_runner/openai_client.py` only if the provider-facing
  protocol needs a narrow callback context extension
- `tests/test_apple_foundation_models.py`, `tests/test_executor.py`, and focused
  coordinator tests
- `README.md`, `spec.md`, `tasks.md`, and `validation.md`

## Verification

Use fake-backed tests first, then `poetry run pytest -q`,
`poetry run ruff check src tests`, `poetry check`, and `poetry build`. Live Apple
callback checks are opt-in and must use the isolated harness validated in B0 or
record the precise status-255 limitation.
