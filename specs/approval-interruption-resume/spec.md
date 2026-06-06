# Approval Interruption and Resume Specification

## Metadata

- Feature slug: `approval-interruption-resume`
- Mode: `light`
- Artifact type: future feature specification
- Status: proposed future feature; metadata baseline exists, live pause/resume is
  not implemented
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Related runtime surfaces:
  - `runtime.execution_policy.approval_interruption`
  - tool policy metadata: `approval_required`, `side_effect`, `sandbox`,
    `timeout`, `retry_policy`, and `failure_behavior`
  - lifecycle hooks for permission-boundary observations
  - trace events for node, model, tool, workflow, and status observations

## Objective

Define the future live approval-interruption runtime that can pause a workflow
before approval-required actions, serialize enough state for safe inspection, and
resume or reject the pending action without mutating the immutable workflow
package.

## Existing Baseline

The primary runtime already preserves and validates approval-interruption
metadata under `runtime.execution_policy.approval_interruption`. That metadata
is intentionally declarative. It does not currently implement live pause/resume,
durable checkpoints, approval UIs, or approval engines.

The current executor also has tool policy metadata, trace events, lifecycle
hooks, async execution, cancellation behavior, and per-run state isolation. Those
are useful foundations, but none of them is sufficient by itself to resume a
partially executed workflow after an approval decision.

## Scope

This feature covers:

1. approval interruption records
2. resumable workflow run-state serialization
3. caller-mediated approval, rejection, and cancellation decisions
4. safe resume from a pending tool boundary
5. trace and lifecycle behavior for approval pauses and outcomes
6. validation rules for approval-capable workflows

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

### FR-2: Produce stable interruption records

The runtime must expose a structured interruption record that callers can inspect
or persist.

Acceptance criteria:

- An interruption record includes a stable interruption id, run id, workflow id,
  node id, tool id or action id, requested arguments, policy metadata, trace
  correlation ids, and human-readable reason.
- Sensitive fields are redacted or separated according to a declared redaction
  policy before the record is exposed outside trusted runtime memory.
- The record distinguishes pending approval, approved, rejected, cancelled,
  expired, and failed states.
- The record carries schema version metadata so persisted records can be
  validated on resume.

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
- Given an approval modifies arguments, when the feature supports argument
  modification, then the modified arguments are validated against the same tool
  schema and policy before invocation.
- Given a rejected interruption, when resume runs, then the runtime applies the
  configured rejection behavior: abort workflow, return model-visible rejection
  content, or continue through an explicit fallback edge if supported.
- Given a cancelled or expired interruption, when resume runs, then execution
  fails or exits with a clear approval-state error.

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

## NEEDS CLARIFICATION

- What exact public API should represent an interrupted workflow result?
- Should resume be a new API such as `resume_agent_workflow_async(...)` or an
  option on `run_agent_workflow_async(...)`?
- Which approval outcomes are required in v1: approve, reject, cancel, expire,
  modify arguments, or request more information?
- Is argument modification allowed, or must approval be approve/reject only?
- What storage abstraction is acceptable for persisted resume state, if any?
- What redaction policy applies to pending tool arguments and raw model output?
- Should model-visible rejection content be generated by the runtime, supplied by
  the approver, or specified in manifest policy?
- How should parallel tool calls and multiple simultaneous approvals be modeled?
- What compatibility checks are required between serialized state and the
  current package, overrides, registry, and model adapter?
- How long may a pending approval remain resumable before it expires?

## Validation Checklist

- [ ] Approval-required direct tool step pauses before invocation.
- [ ] Approval-required model-emitted tool call pauses before invocation.
- [ ] Serialized state excludes live process resources.
- [ ] Resume with approval invokes exactly the pending action once.
- [ ] Resume with rejection follows configured rejection behavior.
- [ ] Stale or incompatible resume state fails closed.
- [ ] Trace events cover requested, paused, resumed, rejected, expired, and failed
      outcomes.
- [ ] Async cancellation cannot accidentally dispatch a pending approval action.
