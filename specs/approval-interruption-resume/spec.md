# Approval Interruption and Resume Specification

## Metadata

- Feature slug: `approval-interruption-resume`
- Mode: `light`
- Artifact type: authoritative SDD feature specification
- Status: implemented v1 live-action baseline; durable resume remains deferred
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Related runtime surfaces:
  - `runtime.execution_policy.approval_interruption`
  - tool policy metadata: `approval_required`, `side_effect`, `sandbox`,
    `timeout`, `retry_policy`, and `failure_behavior`
  - lifecycle hooks for permission-boundary observations
  - trace events for node, model, tool, workflow, and status observations
  - `specs/tool-invocation-coordinator/spec.md` for the prepared shared
    direct/model-loop implementation boundary
- Evaluated supporting reference:
  - `https://www.marktechpost.com/2026/06/26/build-a-nanobot-style-ai-agent-in-google-colab-with-tool-calling-session-memory-skills-and-mcp-servers/`
    demonstrates a pre-tool observation hook but not an enforceable approval
    boundary
  - `https://github.com/MARKTECHPOST-AI-MEDIA-INC/AI-Agents-Projects-Tutorials`
    demonstrates why approval must bind the final invocation: its OpenHarness
    tutorial checks permissions before a pre-tool hook may replace arguments

## Objective

Define the live approval-interruption runtime that can pause a workflow before
approval-required actions, expose enough state for safe inspection, and later
resume or reject the pending action without mutating the immutable workflow
package.

## Existing Baseline

The primary runtime preserves and validates approval-interruption metadata under
`runtime.execution_policy.approval_interruption` and pauses direct `tool_use_step`
and model-tool-loop calls before an approval-required handler invocation. Durable
checkpoints, approval UIs, approval engines, and resume/reject decisions remain
deferred.

The current executor also has tool policy metadata, trace events, lifecycle
hooks, async execution, cancellation behavior, and per-run state isolation. Those
are useful foundations, but none of them is sufficient by itself for durable
resume after an approval decision.

## Scope

This feature covers:

1. approval interruption records
2. resumable workflow run-state serialization
3. caller-mediated approval, rejection, and cancellation decisions
4. safe resume from a pending tool boundary
5. trace and lifecycle behavior for approval pauses and outcomes
6. validation rules for approval-capable workflows

## Council Roadmap Note

The council review recommends treating this feature and
`sandbox-workspace-runtime` as the next live-action vertical slice. A first slice
should be intentionally narrow: pause before one approved mutating action, expose
a stable interruption/result shape, redact arguments in traces, and prove that no
side effect occurs before approval.

## V1 Live Slice Boundary

The first implementation slice began with direct `tool_use_step` approval
interruption and now also covers normalized model-tool-loop calls. It adds a
typed interrupted workflow result and approval record before any registered
handler is invoked. The high-level
`run_agent_workflow*` convenience APIs continue to represent completed workflows;
if a workflow pauses, callers should use `execute_workflow*` to inspect the
structured interruption.

V1 includes:

- package-root exports for approval interruption state types
- direct `tool_use_step` pause before invocation when the effective tool policy
  has `approval_required` set to a yes/true value
- model-tool-loop pause before invocation when the effective exposed tool policy
  has `approval_required` set to a yes/true value
- stable run id, workflow/package id, node id, tool id, requested arguments,
  policy metadata, and redacted trace events
- no tool side effect before the caller makes an approval decision

V1 defers:

- durable resume and serialized run-state compatibility checks
- argument modification
- parallel or multi-approval handling
- built-in write, patch, delete, shell, or package-install workspace tools

## Implementation Status

- Implemented `ApprovalInterruptionState`, `ApprovalInterruption`, and
  `WorkflowInterruptedResult`.
- Implemented direct `tool_use_step` interruption before lifecycle hooks, retry,
  registry invocation, output recording, or edge traversal.
- Implemented model-tool-loop interruption before lifecycle hooks, registry
  invocation, or handler execution; focused executor coverage proves no handler
  invocation before the pause.
- Implemented redacted `approval_requested` and `approval_paused` trace events.
- Implemented high-level `run_agent_workflow*` guardrails that raise
  `WorkflowExecutionError` when a workflow pauses for approval.
- Implemented capability-status reporting for the live direct-tool approval
  boundary when an approval-required registered tool is present.
- Deferred durable resume, approval decisions, argument modification, and
  parallel approvals.

## Functional Requirements

### FR-1: Pause before approval-required actions

The runtime must stop before invoking any tool or runtime action that requires
approval.

Acceptance criteria:

- Given an effective tool policy has `approval_required: true`, when execution
  reaches that tool invocation, then the runtime creates an approval interruption
  instead of invoking the tool.
- Given approval is required for a direct `tool_use_step`, when the workflow
  pauses, then no tool handler side effects have occurred.
- Given approval is required for a model-emitted tool call from an `llm_step`,
  when the workflow pauses, then the pending model tool call is preserved without
  dispatching the callable handler.
- Given multiple pending tool calls are possible, when policy does not authorize
  parallel approval, then the runtime pauses at the first unresolved approval
  boundary.
- Given a tool originated from an explicit registry entry, a function adapter,
  an MCP binding, model output, or interpreter bridging, when its effective
  policy requires approval, then origin does not change the interruption
  requirement and no origin-specific path may dispatch the handler directly.
- Given any origin adapter, interpreter, guardrail, lifecycle hook, or host
  middleware may normalize or replace tool arguments, when approval policy is
  evaluated, then it evaluates the final schema-valid invocation envelope that
  would be sent to the registry handler.
- Given an approved invocation envelope changes after approval, when execution
  continues, then the prior decision is invalid and the runtime must repeat
  schema validation, applicable guardrails, and approval before invocation.

### FR-2: Produce stable interruption records

The runtime must expose a structured interruption record that callers can inspect
or persist.

Acceptance criteria:

- An interruption record includes a stable interruption id, run id, workflow id,
  node id, tool id or action id, requested arguments, policy metadata, trace
  correlation ids, and human-readable reason.
- Sensitive fields are redacted or separated according to a declared redaction
  policy before the record is exposed outside trusted runtime memory.
- The record distinguishes pending approval, approved, modified, rejected,
  cancelled, expired, and failed states.
- The record carries schema version metadata so persisted records can be
  validated on resume.
- State-specific fields are validated together: `approved` requires an approver
  identity/source and final invocation fingerprint; `modified` requires a
  deterministic resultant argument set and a new fingerprint; rejected,
  cancelled, and expired outcomes cannot carry an executable authorization.
- Unknown decision values, contradictory fields, and partial modification
  payloads fail closed rather than falling through to a default action.

### FR-3: Serialize resumable run state

The runtime must be able to serialize enough state to resume exactly at a safe
approval boundary.

Acceptance criteria:

- Serialized state includes the loaded package identity, effective overrides,
  execution plan identity, current node, completed node outputs, tool results,
  relevant model response ids or messages, pending approval records, retry state,
  and trace correlation metadata.
- Serialized state does not include live Python callables, open file handles,
  network clients, event loops, or other non-portable process resources.
- Resume requires callers to supply runtime collaborators again, including tool
  registry, model adapter, lifecycle hooks, and trace sink when needed.
- If the package, overrides, or runtime collaborators are incompatible with the
  serialized state, resume fails before tool invocation.

### FR-4: Resume with approval outcomes

The runtime must accept explicit approval outcomes and continue from the paused
boundary.

Acceptance criteria:

- Given an approved interruption, when resume runs, then the runtime invokes only
  the approved pending action with the approved arguments.
- The approval outcome binds the tool identity, effective policy identity, and
  final invocation fingerprint; it cannot authorize a different handler or
  argument set through a mutable hook or callback.
- Given an approval modifies arguments, when the feature supports argument
  modification, then the modified arguments are validated against the same tool
  schema and policy before invocation.
- Given a rejected interruption, when resume runs, then the runtime applies the
  configured rejection behavior: abort workflow, return model-visible rejection
  content, or continue through an explicit fallback edge if supported.
- Given a cancelled or expired interruption, when resume runs, then execution
  fails or exits with a clear approval-state error.
- Given an approval outcome was already consumed, targets another interruption,
  or carries a mismatched invocation fingerprint, when resume runs, then the
  outcome is rejected without invoking a handler.

### FR-5: Preserve async and cancellation semantics

Approval interruption must fit the async-first runtime.

Acceptance criteria:

- Async workflow execution can return a paused/interrupted result without
  blocking an event loop.
- Sync wrappers expose the same semantic result or error while preserving the
  existing already-running-event-loop guard.
- Cancellation while waiting to produce or persist an interruption does not
  invoke the pending tool.
- Cancellation during post-approval tool invocation follows existing
  best-effort cancellation behavior.

### FR-6: Trace approval lifecycle

Approval interruption must be observable without leaking secrets by default.

Acceptance criteria:

- Trace events identify approval requested, approval paused, approval resumed,
  approval rejected, approval expired, and approval failed states.
- Trace payloads distinguish model-facing content, raw arguments, redacted
  argument previews, and sensitive fields.
- Lifecycle hooks can observe approval boundaries but cannot silently approve
  actions unless explicitly registered as a trusted approval source.

## Non-Goals

- No built-in UI for approval review.
- No production storage backend requirement in the first implementation.
- No automatic approval of write, shell, network, or external mutation actions.
- No mutation of base workflow package artifacts.
- No implicit approval by lifecycle hooks or trace sinks.

## Design Constraints

- Preserve package-directory-first workflow loading.
- Treat approvals as runtime-owned state, not generated package edits.
- Fail closed for missing, stale, malformed, or incompatible resume state.
- Keep approval enforcement separate from portable approval metadata.
- Keep approval state schema-versioned from the first live implementation.
- Treat lifecycle hooks as observation or explicitly trusted resolution inputs,
  never as implicit authorization merely because they run before tool execution.
- Apply approval policy after origin-specific normalization and before the one
  registry invocation boundary so function-adapted, MCP-origin, model-origin,
  and interpreter-origin calls cannot diverge semantically.
- Complete every policy-relevant argument transformation before approval. If a
  trusted post-approval component must transform the invocation, treat the
  result as a new invocation and re-enter validation, guardrails, and approval.
- Keep lifecycle hooks observational at the approval boundary unless a future
  contract explicitly makes a hook a trusted invocation transformer and
  subjects its output to reauthorization.

## NEEDS CLARIFICATION

- RESOLVED for v1: expose `ApprovalInterruption` and
  `WorkflowInterruptedResult`, returned by `execute_workflow*` when execution
  pauses before an approval-required direct or model-tool-loop call.
- RESOLVED for v1: do not add resume APIs yet; interruption records are stable
  inspection surfaces only in the first slice.
- RESOLVED for v1: approval outcomes remain deferred because v1 does not resume.
- RESOLVED for v1: argument modification is deferred.
- What storage abstraction is acceptable for persisted resume state, if any?
- RESOLVED for v1: trace events mark requested tool arguments as sensitive and
  expose only structured identifiers plus policy metadata by default.
- Should model-visible rejection content be generated by the runtime, supplied by
  the approver, or specified in manifest policy?
- How should parallel tool calls and multiple simultaneous approvals be modeled?
- What compatibility checks are required between serialized state and the
  current package, overrides, registry, and model adapter?
- How long may a pending approval remain resumable before it expires?

## Validation Checklist

- [x] Approval-required direct tool step pauses before invocation.
- [x] Approval-required model-emitted tool call pauses before invocation.
- [ ] Serialized state excludes live process resources.
- [ ] Resume with approval invokes exactly the pending action once.
- [ ] Resume with rejection follows configured rejection behavior.
- [ ] Stale or incompatible resume state fails closed.
- [ ] Trace events cover requested, paused, resumed, rejected, expired, and failed
      outcomes.
- [ ] Async cancellation cannot accidentally dispatch a pending approval action.
- [ ] Approval behavior is identical for function-adapted, MCP-origin,
      model-origin, and interpreter-origin tool requests.
- [ ] A pre-tool hook cannot redirect an approved invocation to different
      arguments without invalidating the approval and causing reauthorization.
- [ ] Unknown, contradictory, replayed, cross-interruption, and
      fingerprint-mismatched approval outcomes fail before invocation.
- [ ] Modified outcomes are schema-valid and reauthorized as the complete
      resultant invocation rather than trusted as an unchecked patch.
