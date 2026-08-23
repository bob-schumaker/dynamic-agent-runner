# DAR-Owned Tool Invocation Coordinator

## Metadata

- Feature slug: `tool-invocation-coordinator`
- Mode: guided implementation preparation
- Artifact type: cross-cutting internal runtime slice
- Status: implemented; shared direct/model tool-invocation coordinator validated
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Related specs:
  - `specs/approval-interruption-resume/spec.md`
  - `specs/live-guardrail-execution/spec.md`
  - `specs/apple-foundation-model-adapter/spec.md`
  - `specs/llm-step-interpreter-middleware/spec.md`
  - `specs/sandbox-workspace-runtime/spec.md`

## Objective

Extract the current executor-owned tool-dispatch behavior into one internal,
async DAR coordinator so each origin supported by this slice reaches the same
authority boundary before a handler can run.

The first slice supports only direct `tool_use_step` requests and normalized
model-tool-loop requests. It is an internal refactor plus a deliberate safety
tightening: registered-tool input validation must happen before an approval
interruption is created. It introduces neither a public coordinator API nor
new tool capabilities.

## Existing Baseline

Two executor paths currently duplicate parts of the boundary:

- `_execute_tool_step_async(...)` resolves direct-step arguments, pauses for
  approval, emits lifecycle and trace events, applies retry and failure policy,
  invokes the registry, records state, and shapes node output.
- `_invoke_model_tool_call_async(...)` verifies model-tool exposure, parses
  model arguments, pauses for approval, emits model-loop and tool lifecycle
  events, invokes the registry, and records the result.

The current model-loop approval behavior is covered by
`test_execute_workflow_pauses_approval_required_model_tool_before_invocation`.
The focused baseline passed on 2026-08-22. The approval feature record must be
reconciled to reflect that already-live behavior during this slice.

## Scope

The implementation slice MUST:

1. introduce an internal request/outcome contract owned by DAR, not a raw
   `ToolRegistry` or handler reference;
2. route direct-step and model-loop dispatch through one async coordinator;
3. resolve the registered tool and enforce model-loop effective exposure before
   any policy or handler action;
4. normalize a mapping of arguments and, for an approval-required request,
   prepare it against the registered tool before approval;
5. preserve approval interruptions, including no handler invocation before the
   unresolved decision;
6. preserve existing lifecycle ordering: approval before `before_tool`, then
   invocation, result tracing, `tool_finished`, and `after_tool`;
7. preserve direct-step retry/failure behavior, state-result keys, node-output
   recording, and compatibility trace events; and
8. return the existing `ToolResult` or structured `ApprovalInterruption` to
   executor callers; the executor alone wraps an interruption in
   `WorkflowInterruptedResult`, without widening package-root exports.

## Non-Goals

- No public `ToolInvocationCoordinator` API in this slice.
- No provider callbacks, interpreter bridges, MCP transports, or sandbox tool
  implementations.
- No approval decision/resume API, modified arguments, durable checkpoints, or
  parallel approvals.
- No live tool-input or tool-output guardrail adapter execution. A later
  guardrail slice must operate on validated arguments before approval; it must
  explicitly preserve or revise the established non-approval failure behavior.
- No changes to tool schemas, manifest syntax, retry policy vocabulary, model
  selection, or tool-result model-facing semantics.

## Coordinator Contract

The internal request must carry only DAR-normalized data: origin, run and node
identity, action/call identity, tool id, mapping arguments, effective exposure
when relevant, origin-specific retry policy, and a narrow retry-observation
callback. It must not carry executor state or node-output recording
responsibility.
It must not carry an unwrapped handler, provider callback, interpreter session,
or ambient registry access.

The coordinator returns a completed `ToolResult` or the existing structured
`ApprovalInterruption`; the executor wraps the latter in a
`WorkflowInterruptedResult`. Executor-specific state-result keys, node-output
recording, failure fallback, compatibility events, and model-loop continuation
remain in their callers. The executor records direct `node_inputs` before it
calls the coordinator; that existing input snapshot remains present on an
approval pause. The coordinator owns preparation, approval, lifecycle, retry
attempts, and common observation/dispatch behavior.

Required order:

1. resolve the registered tool and apply origin-specific exposure: direct
   requests require direct-callable exposure; model-loop requests require a
   matching tool in the caller's effective node exposure and model-exposable
   definition;
2. normalize mapping arguments; for a model-loop request, preserve the existing
   redacted `model_tool_loop_tool_call` observation before validation and
   approval;
3. for an approval-required request, perform registered-tool input validation
   without invoking the handler, then evaluate approval against the prepared
   arguments;
4. on an unresolved approval, emit redacted approval events and return an
   interruption without lifecycle hooks, retry attempts, tool-result/node-output
   state writes, or handler invocation;
5. otherwise emit the established invocation events, run `before_tool`, and
   invoke the prepared operation with the established origin-specific retry
   behavior. The coordinator emits retry observations through the supplied
   callback; the executor persists retry records. Non-approval failures retain
   their current registry validation, trace, state-result, hook, and
   failure-policy behavior;
6. trace the result, emit `tool_finished`, and run `after_tool` where the
   current origin does so; then leave caller-specific state, continuation, and
   output handling unchanged.

The `ToolRegistry` operational protocol must add a non-invoking
`prepare_tool_invocation(...)` operation that returns an opaque immutable
prepared invocation: one resolved `RegisteredTool` plus a copied, normalized,
registered-tool-input-valid argument mapping. A paired
`invoke_prepared_tool_async(...)` operation consumes that same opaque value for
one handler attempt. Only a registry creates or consumes the value; it is not a
package-root coordinator API. Built-in and fake registries must implement both
operations. Preparation validates registered-tool input only; direct-callability
and effective model exposure remain origin-specific coordinator checks. Prepared
invocation retains the registry's current direct-callability enforcement, so
model exposure—particularly `direct_model_only`—does not grant a new invocation
capability in this slice. Current validation is limited to input-schema shape
and required-field enforcement; this slice does not introduce full JSON Schema
semantics.

## Functional Requirements

### FR-1: Single authority boundary

Direct-step and model-loop tool requests MUST use the coordinator before a
registered handler is invoked.

Acceptance criteria:

- Given either supported origin, when a handler runs, then the coordinator has
  already completed exposure, preparation, approval, and lifecycle preparation
  using the same prepared invocation that it dispatches.
- Given an unavailable or model-unexposed tool, then the coordinator fails
  before policy hooks or handler invocation, with the current origin's
  package-owned result/error translation retained.
- This slice adds no provider or interpreter ingress. A future adopter spec
  MUST route any such ingress through this coordinator before handler dispatch.

### FR-2: Bind approval to validated arguments

Approval MUST apply to the final registered-tool-input-valid invocation envelope.

Acceptance criteria:

- Given malformed arguments for an approval-required tool, when a request is
  processed, then validation fails and no approval interruption is created.
- Given valid arguments for an approval-required tool, when no decision exists,
  then the returned interruption contains those arguments and no handler,
  lifecycle hook, retry attempt, tool-result/node-output state write, or
  failure-policy behavior occurs; a pre-existing direct `node_inputs` snapshot
  is retained.
- Given a later approved invocation would have different tool id or arguments,
  then it requires a new validation and approval pass in a future resume slice.

### FR-3: Preserve current observable behavior

The extraction MUST not silently change supported successful or failed tool
execution outside the deliberate validation-before-approval ordering.

Acceptance criteria:

- Direct tool steps retain retry records, failure fallback/error behavior,
  state-result keys, output recording, and `tool_invocation` compatibility
  events.
- Model-loop calls retain model-loop call events, call ids, loop limits, and
  transcript/result continuation behavior.
- `before_tool` and `after_tool` retain their current success/error context and
  execute only after approval permits dispatch.
- `ToolResult.model_facing_output`, sensitive-field redaction, and existing
  registry error translation remain unchanged.
- Invalid or unavailable non-approval requests retain their current
  lifecycle, registry-result, retry, state-result, tracing, and failure-policy
  behavior. Invalid approval-required requests instead fail before creating an
  interruption; a model-loop call retains its existing pre-approval
  `model_tool_loop_tool_call` observation.
- An effectively model-exposed `direct_model_only` tool retains its current
  registry invocation outcome; model exposure alone does not make it directly
  callable in this slice.

Model-loop observation compatibility:

| Case | Required events before return or failure |
| --- | --- |
| Unknown or not-effectively-exposed tool | No `model_tool_loop_tool_call`, approval, or tool lifecycle event |
| Malformed approval-required arguments | `model_tool_loop_tool_call`; no approval or tool lifecycle event |
| Valid unresolved approval | `model_tool_loop_tool_call`, then redacted approval events; no tool lifecycle event |
| Dispatchable call | `model_tool_loop_tool_call`, then existing tool lifecycle/result events |

### FR-4: Keep the slice internal and testable

The coordinator MUST be fake-testable without live models or external tools.

Acceptance criteria:

- Coordinator types are internal modules or internal names and are not added to
  the package-root public API in this slice.
- Unit tests use fake model adapters, registries, lifecycle hooks, and handlers.
- Existing direct-step and model-loop tests remain authoritative regression
  coverage while focused coordinator tests prove ordering and no-bypass rules.

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Extraction drops direct-only retry or failure behavior | Migrate one origin at a time and retain existing regression tests before deleting duplicated code. |
| Preparation diverges from registry invocation validation or dispatches a different tool | Use one registry-owned opaque prepared invocation for validation, approval, and dispatch; do not reimplement input checks in the coordinator. |
| Hooks or tracing move across the approval boundary | Add event-order and hook-spy tests for approved, rejected, malformed, and handler-failure paths. |
| Circular imports between executor state and coordinator types | Keep the first coordinator contract internal and dependency-light; move shared value types only when tests prove the need. |
| Scope expands into provider, interpreter, or guardrail features | Treat those as follow-up adopters after this slice is complete. |

## Validation Checklist

- [x] Direct and model-loop requests enter one coordinator before registry dispatch.
- [x] Invalid approval-required arguments fail before approval is recorded.
- [x] Unresolved approval invokes no handler, hooks, retry attempt, tool-result,
      node-output, or failure-policy state write; the direct node-input snapshot
      remains available.
- [x] The prepared invocation binds one resolved tool and copied argument mapping
      across validation, approval, and handler dispatch.
- [x] Model-loop unknown, malformed, paused, and dispatched calls preserve their
      specified event ordering.
- [x] Effectively exposed `direct_model_only` calls retain their current registry
      invocation outcome.
- [x] Approved non-retry direct and model-loop paths preserve trace and result
      compatibility.
- [x] Direct retry/failure paths preserve current behavior.
- [x] Handler failure emits the existing result/finished/after-hook sequence.
- [x] Focused tests, full tests, Ruff, docs build, and package build pass.
- [x] Related approval, guardrail, Apple, interpreter, and README records agree
      with the implemented boundary.
