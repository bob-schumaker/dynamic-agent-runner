# Live Guardrail Execution Specification

## Metadata

- Feature slug: `live-guardrail-execution`
- Mode: `light`
- Artifact type: authoritative SDD feature specification
- Status: implemented v1 input-guardrail baseline; output/tool phases remain
  deferred
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Related runtime surfaces:
  - `extensions.guardrails.declarations`
  - model input preparation
  - output-contract validation
  - tool input and tool output handling
  - trace events and lifecycle hooks
- Evaluated supporting reference:
  - `https://github.com/MARKTECHPOST-AI-MEDIA-INC/AI-Agents-Projects-Tutorials`
    includes useful preflight/postflight examples but also direct handler
    dispatch that DAR must continue to reject

## Objective

Define a live guardrail execution layer for input, output, tool-input, and
tool-output phases that can abort execution, provide model-visible rejection
content, or fail closed according to explicit runtime policy.

## Existing Baseline

The runtime preserves and validates guardrail declarations and implements the v1
caller-registered input-guardrail abort boundary. Output guardrails, tool
guardrails, reject-content behavior, retries, timeouts, and external adapters
remain deferred.

## Scope

This feature covers:

1. guardrail declaration resolution
2. guardrail adapter registration
3. phase-specific execution points
4. abort versus reject-content behavior
5. guardrail result models
6. trace, redaction, and diagnostics
7. retry and timeout policy for guardrail checks

## Council Roadmap Note

The council review recommends keeping live guardrails behind caller-registered
adapters and explicit status reporting. Metadata declarations should remain
visible as metadata-only until the runtime can report required adapters,
execution phase coverage, redaction policy, and fail-closed behavior before
workflow execution.

## V1 Slice Boundary

The first implementation slice is intentionally narrow: caller-registered input
guardrails that can pass or abort before the first model call or tool invocation.
This creates the live enforcement boundary without introducing tool-output
redaction, model-visible rejection repair, or external provider dependencies.

V1 includes:

- public guardrail decision/result dataclasses
- caller-supplied guardrail registry
- input-phase guardrail execution before the first runtime action
- fail-closed behavior when a declared input guardrail adapter is missing
- abort behavior with a package-owned guardrail execution error
- redacted guardrail trace events
- capability status for live input guardrail coverage

V1 defers:

- output, tool-input, and tool-output phase enforcement
- reject-content behavior
- warning-only behavior
- retries, timeout policy, and external provider adapters
- model-assisted repair or rewriting

## Implementation Status

- Implemented `GuardrailDecision`, `GuardrailResult`, and
  `InMemoryGuardrailRegistry`.
- Implemented input guardrail execution before the first model call or tool
  invocation.
- Implemented fail-closed behavior for missing input guardrail adapters.
- Implemented abort behavior through `GuardrailExecutionError`.
- Implemented redacted guardrail trace events.
- Implemented capability-status reporting for missing and live input guardrail
  adapter coverage.
- Deferred output, tool-input, tool-output, reject-content, warning-only,
  retries, timeouts, and external guardrail provider adapters.

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
- Tool-input guardrails inspect the normalized, schema-valid invocation that is
  eligible for approval and registry dispatch, not an earlier provider-native
  or interpreter-native representation.
- Any guardrail or trusted middleware transformation that changes the tool id or
  arguments must occur before approval. A change after approval invalidates the
  approval and re-enters validation, applicable guardrails, and approval.
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
- Keep tool invocation behind the registry authority after guardrails pass;
  guardrail adapters must never call the selected tool handler directly.

## Future Work

Lanham's `AI Agents in Action, Second Edition` frames robust agents around
test-driven agent development, grounding, rubrics, critic agents, and traceable
feedback. Future approved slices may add:

- rubric-based evaluation contracts that can score workflow outputs without
  replacing output-contract validation
- grounding checks as guardrails for RAG and retrieved-context workflows
- caller-registered critic or evaluator agents as guardrail adapters, with the
  same approval, timeout, redaction, and fake-adapter requirements as other
  guardrails
- trace-linked evaluation metadata, annotations, and feedback records that do
  not expose raw inspected content by default
- deterministic composition rules for multiple evaluators or guardrails in the
  same phase

These follow-ups should remain separate from the v1 input-guardrail baseline and
should not introduce a built-in external evaluation provider.

## NEEDS CLARIFICATION

- RESOLVED for v1: expose a small caller-supplied registry of Python guardrail
  handlers keyed by guardrail id.
- RESOLVED for v1: implement input phase only.
- RESOLVED for v1: execution is async-canonical with sync handlers accepted
  through the same event-loop-safe pattern used for tools.
- DEFERRED: output guardrail ordering relative to output-contract validation.
- DEFERRED: model-visible rejection content.
- RESOLVED for v1: support pass and abort only.
- What retry policy applies to guardrail adapter failures?
- What timeout defaults apply per phase?
- How should multiple guardrails at the same phase compose?
- RESOLVED for v1: input guardrails inspect the initial user prompt only; raw
  tool output and sensitive trace fields remain out of scope.

## Validation Checklist

- [x] Missing required input guardrail adapter fails before execution.
- [x] Input guardrail abort prevents model/tool execution.
- [ ] Tool-input guardrail rejection prevents callable invocation.
- [ ] Tool-output guardrail rejection prevents model-visible leakage.
- [ ] Output guardrail composes with output-contract validation.
- [ ] Multiple guardrails compose deterministically.
- [x] Input guardrail trace payloads are redacted by default.
- [ ] Tool-input guardrail tests prove argument replacement cannot bypass final
      approval or registry dispatch.
