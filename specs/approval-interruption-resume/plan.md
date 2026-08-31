# Approval Interruption and Sandbox V1 Plan

> Historical v1 plan. The iterative model-tool-loop slice subsequently added a
> model-emitted approval pause; the current feature boundary is authoritative in
> [`spec.md`](spec.md).

## Objective

Ship the first live approval boundary before moving into broader sandbox, MCP,
guardrail, loop, or skill execution work.

The v1 slice originally paused a direct `tool_use_step` before invoking a
registered tool when effective policy requires approval. It proves the core
safety property: no side effect occurs before approval.

## Scope

- Add public approval-interruption dataclasses and state enum.
- Return a structured interrupted workflow result from `execute_workflow*`.
- Preserve existing successful `WorkflowResult` behavior.
- Emit redacted approval trace events before the pause.
- Use existing `ToolDefinition.policy` and manifest tool metadata for
  `approval_required`.
- Keep sandbox/write tool implementation deferred.

## Non-Goals

- No durable resume API.
- No approval decision API.
- No argument modification.
- No model-emitted tool-call approval pause in this historical v1 plan; that
  behavior was added later by the iterative model-tool-loop slice.
- No write, patch, delete, shell, or package-install built-in tools.
- No storage backend.

## Design

The executor is the authority for live interruption because it is the last safe
point before `registry.invoke_tool_async(...)`.

For direct `tool_use_step` nodes:

1. Resolve tool arguments using the existing `_tool_arguments(...)` path.
2. Resolve effective policy from the registered tool first, falling back to the
   manifest/prepared node policy where needed.
3. If approval is required, emit approval-requested and approval-paused trace
   events with arguments marked sensitive.
4. Return `WorkflowInterruptedResult` with `final_result=None`, current state,
   and an `ApprovalInterruption`.
5. Do not call lifecycle `before_tool`, retry, registry invocation, result
   recording, `after_tool`, output recording, or edge traversal.

The high-level `run_agent_workflow*` APIs should raise a clear
`WorkflowExecutionError` if a workflow pauses, because their contract returns a
final result rather than structured execution state.

## Validation Strategy

- RED unit test proving an approval-required direct tool step invokes the handler
  today.
- GREEN unit test proving the handler is not invoked and the result is
  interrupted.
- Trace assertion proving requested arguments are sensitive.
- Import test for public approval state exports.
- Focused executor, tracing, and import tests after implementation.
