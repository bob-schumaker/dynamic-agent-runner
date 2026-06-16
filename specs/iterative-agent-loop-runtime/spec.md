# Iterative Agent-Loop Runtime Specification

## Metadata

- Feature slug: `iterative-agent-loop-runtime`
- Mode: `guided`
- Artifact type: planned feature specification
- Status: implemented v1 baseline; bounded opt-in `llm_step` model-tool loops
  execute through the registry with safety checks and trace events
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
`runtime.execution_policy.tool_use_completion` metadata. It supports bounded
opt-in model-tool loops for eligible `llm_step` nodes, model tool calls, and
direct tool steps. It does not implement an open-ended ReAct-style loop,
automatic run-again behavior outside explicit policy, durable approval resume,
or loop `state_field` final-output selection.

Current implementation facts that shape v1:

- `ModelResponse.tool_calls` is normalized by model adapters.
- `llm_step` already exposes registry tools to model requests when
  `available_tools` is configured.
- Direct `tool_use_step` execution can pause before approval-required tools.
- Input guardrails are live before the first runtime action; output and
  tool-phase guardrails remain deferred.
- `runtime.execution_policy.tool_use_completion` validates and preserves
  `run_again`, `stop_on_tool`, `final_output`, and
  `final_output_state_key`.

## V1 Slice Boundary

The next implementation slice is a bounded single-node loop for eligible
`llm_step` nodes. It turns model-emitted tool calls into serial registry
invocations, appends model-facing tool results to the loop transcript, and
re-calls the same model until the stop policy resolves.

V1 includes:

1. opt-in activation through existing
   `runtime.execution_policy.tool_use_completion`
2. serial handling of model-emitted tool calls from one `llm_step`
3. registry-authorized tool lookup and invocation only for tools exposed to the
   node
4. JSON-object argument parsing for model tool calls
5. model-facing tool result messages built from `ToolResult.model_output`
6. deterministic stop reasons for final model output, no tool calls,
   `stop_on_tool`, max iterations, tool failure, model failure, and approval
   interruption
7. trace events for loop start, model turn, tool call, tool result, stop reason,
   and final output selection
8. output-contract validation against the selected final output

V1 intentionally defers:

- parallel model tool-call execution
- approval resume for model-emitted tool calls
- output, tool-input, and tool-output guardrail phases
- token-budget aggregation beyond existing per-request accounting
- durable loop transcript persistence
- node-local policy overrides
- multi-node graph mutation or self-directed graph traversal

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
- Given loop policy is enabled for a workflow, preparation validates the
  existing metadata fields and execution validates v1 runtime constraints before
  entering the loop.
- Node-level overrides are deferred until precedence is specified.

### FR-2: Dispatch model-requested tools iteratively

The runtime must support repeated model/tool turns through registry authority.

Acceptance criteria:

- Model-emitted tool calls are validated against effective tool exposure and
  registry definitions.
- Tool calls dispatch through the existing registry invocation path.
- Tool results are normalized into model-facing messages before the next model
  call.
- Hidden or disabled tools cannot be invoked by the loop.
- Approval-required model-emitted tool calls pause before invocation or fail
  closed if the current interruption contract cannot represent them without
  losing correlation metadata.

### FR-3: Stop deterministically

Loop completion must be bounded and explainable.

Acceptance criteria:

- Supported v1 stop reasons include final model output, no tool call, explicit
  stop-on-tool policy, max iterations, tool failure, model failure, and approval
  interruption.
- Future stop reasons include max tokens, timeout, guardrail rejection, and
  cancellation.
- Final output selection follows declared policy: last model output, state
  field, or error.
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

- Approval-required tools produce approval interruptions before invocation, or
  fail closed until model-tool approval resume state is supported.
- Input guardrails keep running before the first runtime action; output,
  tool-input, and tool-output guardrails remain deferred for v1.
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

## V1 Decisions

- Policy location: use existing workflow-level
  `runtime.execution_policy.tool_use_completion`; node-local overrides are
  deferred.
- Activation: `run_again: required` enables loop execution for `llm_step` nodes
  with exposed tools.
- Stop-on-tool: `stop_on_tool: enabled` stops after the first successful model
  tool invocation and selects output through `final_output`.
- Tool-call mode: serial only; parallel tool calls are deferred.
- Tool-call ids: preserve model ids when present and generate deterministic
  per-turn fallback ids for trace correlation.
- Final output v1: support last model response content. Loop `state_field`,
  tool-result, and richer final selectors remain metadata-only until a separate
  slice defines the exact state key behavior.
- Loop state: record final node output as today, with loop transcript details in
  trace events rather than durable public state.
- Tool failures: follow existing tool failure behavior where available; abort by
  default for model-emitted calls without explicit continuation behavior.
- Redaction: mark model request/response content, tool arguments, and tool output
  as sensitive in loop trace events.

## NEEDS CLARIFICATION

- How should token budgets apply after v1: per turn, per node loop, or whole
  workflow?
- What serialized state is required to resume approval-required model tool calls?
- Should future loop transcripts become public state, exported artifacts, or
  trace-only diagnostics?

## Future Work

Lanham's `AI Agents in Action, Second Edition` distinguishes inner loops, task
loops, and meta loops, and highlights operational loop controls. Future approved
slices may add:

- layered termination gates that combine hard iteration limits, success
  criteria, no-progress detection, budget exhaustion, and human/host stop
  signals
- iteration body output contracts that separate sensed state, plan updates,
  tool actions, observations, and learned state from final model output
- stagnation detection that pivots strategy when repeated iterations produce no
  new evidence or state change
- confidence-gated final output and knowledge-boundary reporting before an
  answer is presented to the caller
- strategy-pivot metadata and trace events for loop diagnostics
- evaluation hooks that can score loop progress without making the loop
  unbounded or self-modifying

Those follow-ups must keep loops opt-in, bounded, registry-authoritative, and
fake-client testable.

## Validation Checklist

- [x] Ordinary `llm_step` behavior is unchanged without loop policy.
- [x] Loop policy validates max iterations, tools, and stop behavior.
- [x] Iterative tool calls dispatch through the registry.
- [x] Disabled/hidden tools cannot be invoked.
- [x] Max iteration exhaustion fails or returns partial output according to
      explicit policy.
- [x] Final model output is selected and output-contract validated.
- [x] Trace events expose iteration count and stop reason.
