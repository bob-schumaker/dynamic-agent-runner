# Live Guardrail Execution V1 Plan

## Objective

Add the first live guardrail enforcement point without introducing external
moderation dependencies or broad phase coverage. V1 runs caller-registered input
guardrails before the workflow reaches its first model call or tool invocation.

## Scope

- Add public guardrail decision/result dataclasses.
- Add a caller-owned guardrail registry keyed by guardrail id.
- Execute input-phase guardrails once at workflow start.
- Abort before model/tool execution when an input guardrail trips.
- Fail closed when a declared input guardrail has no registered adapter.
- Emit redacted guardrail trace events.
- Report live input guardrail coverage in capability status.

## Non-Goals

- No output, tool-input, or tool-output guardrails in v1.
- No reject-content behavior.
- No warning-only behavior.
- No retries, timeout policy, external provider adapters, or model repair.
- No inspection of raw tool outputs or sensitive trace fields.

## Design

Guardrails should be a caller-supplied runtime collaborator, similar to tool
registries and model adapters. Manifest declarations remain metadata until the
caller supplies matching guardrail handlers.

The executor should run input guardrails after workflow start tracing and before
the first node starts. If a guardrail aborts, execution stops with a
package-owned guardrail error and no model/tool handler is invoked.

The v1 subject is the initial user prompt. Trace events must include guardrail
id, phase, decision, reason code, and redacted subject preview, without raw
prompt leakage unless a later explicit policy permits it.

## Validation Strategy

- RED import/shape tests for guardrail result and registry types.
- RED executor tests proving missing input guardrail adapters fail before
  model/tool execution.
- RED executor tests proving abort decisions prevent model/tool execution.
- Trace tests proving guardrail events are emitted with sensitive subject fields.
- Capability-status tests proving live input guardrail coverage is reported only
  when matching adapters are supplied.
