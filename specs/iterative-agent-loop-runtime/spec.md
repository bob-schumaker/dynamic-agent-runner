# Iterative Agent-Loop Runtime Specification

## Metadata

- Feature slug: `iterative-agent-loop-runtime`
- Mode: `light`
- Artifact type: future feature specification
- Status: proposed future feature; tool-use completion metadata baseline exists,
  live iterative loop execution is not implemented
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Related runtime surfaces:
  - `runtime.execution_policy.tool_use_completion`
  - `llm_step` model tool calls
  - `tool_use_step`
  - output contracts
  - retry and max-step policy
  - trace events

## Objective

Define a future iterative agent-loop runtime that can repeatedly call a model,
dispatch model-requested tools, feed tool results back to the model, and stop
according to explicit completion policy while preserving the finite graph
executor's package and safety boundaries.

## Existing Baseline

The current runtime executes finite workflow graph nodes and preserves
`runtime.execution_policy.tool_use_completion` metadata. It supports model tool
calls and direct tool steps, but it does not implement an open-ended ReAct-style
loop, automatic run-again behavior, or loop-specific final-output selection.

## Scope

This feature covers:

1. iterative model/tool turn execution within an eligible `llm_step`
2. loop completion policy
3. tool-result message construction
4. max iteration, token, timeout, and retry limits
5. output-contract validation at final output
6. trace vocabulary for loop turns
7. interaction with approval, guardrails, and sandbox policy

## Council Roadmap Note

The council review recommends deferring live iterative loops until approval,
sandbox, guardrail, and capability/status reporting boundaries are ready. Loops
multiply tool-use risk and observability needs; they should not be the first
feature to make deferred tool policy live.

## Functional Requirements

### FR-1: Enable loops only through explicit policy

The runtime must not convert ordinary `llm_step` nodes into iterative loops
implicitly.

Acceptance criteria:

- Given no loop policy, `llm_step` behavior remains single model call plus
  current tool-call handling semantics.
- Given loop policy is enabled for a node or workflow, preparation validates max
  iterations, allowed tools, final-output policy, and stop conditions.
- Loop policy can be workflow-level default with node-level overrides only when
  precedence is explicit.

### FR-2: Dispatch model-requested tools iteratively

The runtime must support repeated model/tool turns through registry authority.

Acceptance criteria:

- Model-emitted tool calls are validated against effective tool exposure and
  registry definitions.
- Tool calls dispatch through the existing registry invocation path.
- Tool results are normalized into model-facing messages before the next model
  call.
- Hidden or disabled tools cannot be invoked by the loop.

### FR-3: Stop deterministically

Loop completion must be bounded and explainable.

Acceptance criteria:

- Supported stop reasons include final model output, no tool call, explicit
  stop-on-tool policy, max iterations, max tokens, timeout, tool failure, model
  failure, approval interruption, guardrail rejection, and cancellation.
- Final output selection follows declared policy: last model output, specific
  tool result, state field, structured output, or error.
- Max iteration exhaustion fails clearly unless policy explicitly allows partial
  output.

### FR-4: Preserve output contracts

Output validation must remain explicit.

Acceptance criteria:

- Final loop output is validated against the node output contract.
- Tool results are not treated as final output unless policy declares that.
- Structured output requirements are applied to the final selected output, not
  every intermediate message unless separately configured.

### FR-5: Compose with safety features

Loops must not bypass approval, guardrails, or sandbox policy.

Acceptance criteria:

- Approval-required tools produce approval interruptions before invocation.
- Guardrails, when implemented, run at configured input, output, tool-input, and
  tool-output phases.
- Sandbox/write/shell tools require the same grants and approvals as direct
  tool steps.
- Interpreter middleware, if present, cannot expose loop tools beyond effective
  loop allowlists.

### FR-6: Trace loop turns

Loops must be observable at turn granularity.

Acceptance criteria:

- Trace events identify loop started, model turn started/finished, tool calls,
  tool results, stop reason, iteration count, and final output selection.
- Token usage is aggregated across model turns.
- Trace payloads preserve run id, node id, iteration number, tool call id, and
  redacted message previews.

## Non-Goals

- No replacement of finite graph execution as the default runtime model.
- No autonomous unbounded agent execution.
- No multi-agent team runtime in v1.
- No automatic tool discovery or broad tool exposure.
- No model-assisted output repair unless separately specified.

## Design Constraints

- Loops must be opt-in and bounded.
- The tool registry remains authoritative.
- Current package manifests remain immutable.
- Stop policy must be explicit enough to test with fake clients and tools.
- Unit validation must not require live model calls.

## NEEDS CLARIFICATION

- Should loop policy live only under `runtime.execution_policy.tool_use_completion`
  or also as node-local metadata?
- What exact stop policy vocabulary should v1 support?
- Should parallel model tool calls be supported in v1?
- How should tool-call ids be generated and correlated across turns?
- What final-output policies are required initially?
- Should loop state be visible in `WorkflowExecutionState` or hidden inside node
  execution records?
- How should token budgets apply: per turn, per node loop, or whole workflow?
- How do loops interact with approval-resume serialized state?
- Should tool failures be model-visible by default, abort by default, or follow
  per-tool failure behavior?
- How should loop transcripts be redacted in traces?

## Validation Checklist

- [ ] Ordinary `llm_step` behavior is unchanged without loop policy.
- [ ] Loop policy validates max iterations, tools, and stop behavior.
- [ ] Iterative tool calls dispatch through the registry.
- [ ] Disabled/hidden tools cannot be invoked.
- [ ] Max iteration exhaustion fails or returns partial output according to
      explicit policy.
- [ ] Final output is selected and output-contract validated.
- [ ] Trace events expose iteration count and stop reason.
