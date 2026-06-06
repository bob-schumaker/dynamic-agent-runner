# Live Guardrail Execution Specification

## Metadata

- Feature slug: `live-guardrail-execution`
- Mode: `light`
- Artifact type: future feature specification
- Status: proposed future feature; guardrail metadata baseline exists, live
  guardrail execution is not implemented
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Related runtime surfaces:
  - `extensions.guardrails.declarations`
  - model input preparation
  - output-contract validation
  - tool input and tool output handling
  - trace events and lifecycle hooks

## Objective

Define a live guardrail execution layer for input, output, tool-input, and
tool-output phases that can abort execution, provide model-visible rejection
content, or fail closed according to explicit runtime policy.

## Existing Baseline

The runtime currently preserves and validates deferred guardrail declarations.
It does not execute guardrail checks, call guardrail models, run guardrail tools,
modify model prompts based on guardrail outcomes, or enforce live tripwires.

## Scope

This feature covers:

1. guardrail declaration resolution
2. guardrail adapter registration
3. phase-specific execution points
4. abort versus reject-content behavior
5. guardrail result models
6. trace, redaction, and diagnostics
7. retry and timeout policy for guardrail checks

## Functional Requirements

### FR-1: Execute guardrails at declared phases

Guardrails must run only at explicit phase boundaries.

Acceptance criteria:

- Input guardrails run before the first model call or tool invocation that
  consumes user-provided prompt content.
- Output guardrails run after model output normalization and before output is
  trusted as node state or final result.
- Tool-input guardrails run after tool input rendering/validation and before
  callable invocation.
- Tool-output guardrails run after tool result normalization and before result
  content is shown to a model or stored as trusted state.

### FR-2: Use registered guardrail adapters

Manifest metadata alone must not execute guardrail logic.

Acceptance criteria:

- A guardrail declaration references a guardrail id or policy id.
- The caller supplies a guardrail registry or approved guardrail source.
- Missing required guardrail adapters fail during preparation.
- Optional guardrails may be omitted only when policy explicitly allows
  degraded execution.

### FR-3: Support structured guardrail results

Guardrail adapters must return structured decisions.

Acceptance criteria:

- Result decisions include pass, abort, reject content, warn, and error when
  supported by policy.
- Results include guardrail id, phase, subject summary, reason code, human
  message, optional model-visible message, and redacted diagnostic details.
- Guardrail errors are distinct from guardrail rejections.
- Malformed guardrail results fail closed.

### FR-4: Enforce abort and reject-content behavior

The runtime must apply declared behavior consistently.

Acceptance criteria:

- Abort behavior stops execution with a project-specific guardrail error.
- Reject-content behavior returns configured model-visible rejection content to
  the next model step or final result only when the declaration explicitly
  permits it.
- Tool-input rejection prevents tool invocation.
- Tool-output rejection prevents rejected output from entering model-visible
  context.

### FR-5: Preserve output-contract and policy ordering

Guardrails must compose with existing validation.

Acceptance criteria:

- Output-contract validation remains separate from guardrail execution.
- The spec defines whether output guardrails run before or after schema
  validation for each supported output mode.
- Tool schema validation still runs before tool-input guardrails unless a later
  policy explicitly changes that order.
- Guardrail-generated rejection content is validated when it becomes a node
  output or final result.

### FR-6: Trace guardrail execution

Guardrails must be observable and redacted.

Acceptance criteria:

- Trace events identify guardrail started, passed, warned, rejected, aborted,
  errored, and timed out states.
- Trace payloads include phase, guardrail id, node id, tool id when applicable,
  reason code, and redacted subject preview.
- Raw inspected content is excluded unless explicitly allowed.

## Non-Goals

- No built-in safety policy taxonomy in v1.
- No automatic external moderation provider dependency.
- No model-assisted repair unless separately specified.
- No replacement for JSON-schema output-contract validation.
- No implicit execution of guardrails declared only as metadata.

## Design Constraints

- Guardrails must be opt-in and fail closed when required adapters are missing.
- Keep guardrail adapters caller-registered or separately approved.
- Keep guardrail policy separate from lifecycle hooks.
- Avoid leaking sensitive inspected content into traces or model prompts.
- Preserve fake-adapter unit testing without live external safety services.

## NEEDS CLARIFICATION

- What public guardrail adapter protocol should v1 expose?
- Which phases are required in v1: input, output, tool_input, tool_output?
- Should guardrail execution be sync, async, or async-canonical like model
  execution?
- Should output guardrails run before or after output-contract validation?
- Who authors model-visible rejection content: manifest, adapter, caller, or
  runtime default?
- Are warning-only guardrails supported, or only pass/reject/abort?
- What retry policy applies to guardrail adapter failures?
- What timeout defaults apply per phase?
- How should multiple guardrails at the same phase compose?
- Can guardrails inspect raw tool output, sensitive trace fields, or only
  model-facing output?

## Validation Checklist

- [ ] Missing required guardrail adapter fails during preparation.
- [ ] Input guardrail abort prevents model/tool execution.
- [ ] Tool-input guardrail rejection prevents callable invocation.
- [ ] Tool-output guardrail rejection prevents model-visible leakage.
- [ ] Output guardrail composes with output-contract validation.
- [ ] Multiple guardrails compose deterministically.
- [ ] Trace payloads are redacted by default.
