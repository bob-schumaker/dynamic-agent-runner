# Async Session Memory Pipeline Future Feature Specification

## Metadata

- Feature slug: `async-session-memory-pipeline`
- Mode: `light`
- Artifact type: implemented-baseline plus future expansion specification /
  first-customer readiness analysis
- Status: documents an implemented metadata-only async-session baseline and
  proposes future expansion; live in-memory session behavior is now implemented
  separately by `specs/persistent-agent-sessions/spec.md`
- Source context:
  - `specs/dynamic-agent-runner/spec.md`
  - `specs/dynamic-agent-runner/plan.md`
  - `specs/dynamic-agent-runner/tasks.md`
  - `src/dynamic_agent_runner/api.py`
  - `src/dynamic_agent_runner/context.py`
  - `src/dynamic_agent_runner/validation.py`
  - `tests/fixtures/power-marimo/agent-runtime.yaml`
  - `cline-tasks/power-marimo-analysis.md`
  - `specs/async-session-memory-pipeline/references/multi-turn-memory-architecture-summary.md`
  - `specs/context-management-prepare-stage/spec.md`
  - `specs/async-session-memory-pipeline/references/multi-turn-agent-evals-summary.md`
  - `specs/async-session-memory-pipeline/decision-memo.md`
  - `specs/async-session-memory-pipeline/power-marimo-host-integration.md`

## References

- `specs/async-session-memory-pipeline/references/multi-turn-memory-architecture-summary.md`
  — supporting; packaged summary of the most relevant multi-turn agent-memory
  reference notes
- `specs/context-management-prepare-stage/spec.md`
  — adjacent; owns live session pruning, context compaction, and hierarchical
  prompt-context injection
- `specs/async-session-memory-pipeline/references/multi-turn-agent-evals-summary.md`
  — supporting; packaged summary of evaluation guidance relevant to future
  transcript/session validation
- `specs/async-session-memory-pipeline/decision-memo.md`
  — supporting; first-customer readiness memo for `power-marimo`
- `specs/async-session-memory-pipeline/power-marimo-host-integration.md`
  — supporting; concrete host-managed multi-call continuity sketch using the
  current runner API
- `cline-tasks/power-marimo-analysis.md` — supporting; earlier Power-Marimo fit
  analysis used as repository-local context

## Objective

Record the currently implemented metadata-only async-session seam under
`runtime.execution_policy.async_session` and define the next future expansion
layer for a broader async session memory pipeline, so the runner can later
support richer multi-turn or resumable async workflows without prematurely
introducing runner-owned durable memory, automatic history replay, or broader
runtime behavior changes.

The first live runner-owned in-memory session object and store are implemented
separately in `specs/persistent-agent-sessions/spec.md`. This OA8 package
continues to own the metadata protocol seam and future broader memory-pipeline
analysis, not the `AgentSession` v1 API.

This spec also records whether the current API surface is already sufficient for
the first expected customer, `power-marimo`, when continuity is managed by the
host across repeated runner calls.

## Next Work Target

The next work target that depends on this package is **pruning-context graph
injection for `llm_step` interactions**. That target is intentionally routed to
adjacent owners rather than implemented inside OA8:

- `async-session-memory-pipeline` owns the declarative session identity and
  history-retention metadata that can describe which session material may feed a
  future pruning pass.
- `persistent-agent-sessions` owns the live in-memory session state and saved
  snapshots that can provide cross-prompt messages to a run.
- `context-management-prepare-stage` owns pruning, compaction, prompt-context
  assembly, and diagnostics for model input preparation.
- `internal-graph-mutation` owns the graph-injection mechanics that can attach
  or later insert context-management behavior around selected `llm_step`
  interactions, including loopback-style ReAct flows.

For the next implementation stream, use this spec as the async-session boundary
reference only. The executable TDD plan should live in the context-management or
graph-mutation artifact set and should consume existing session messages rather
than adding durable storage or a new runner-owned memory backend here.

## Problem Statement

The repository now has an implemented metadata-only OA8 baseline plus an open
question about how far to expand it later.

The implemented baseline is:

- preserve deferred `runtime.execution_policy.async_session` metadata on
  `RuntimeManifest` and `ExecutionPlan`
- validate the metadata fail-closed
- keep durable session storage and broader memory behavior out of OA8 scope

The remaining design question is how future session-memory work should grow from
that baseline without collapsing into an oversized memory/runtime feature.

The current planning notes already identify the narrow desired capability:

- preserve a compact deferred `runtime.execution_policy.async_session` protocol
- include session-id persistence and optional history-retention metadata
- do **not** add durable session storage in OA8
- do **not** broaden executor-owned durable memory/runtime behavior in OA8

That narrow protocol seam is useful because the current runtime executes one
bounded workflow per call, while likely first-customer use cases such as
`power-marimo` may still need:

- continuity across multiple user turns
- continuity across notebook-oriented analysis steps
- resumable host-side identity for a notebook or analysis thread
- a future path toward context pruning or summary-style continuity

Without a portable spec, later session work could drift into a larger memory
system, or introduce field names that are too narrow for future pruning,
retention, or evaluation needs.

## Current Architecture Fit

The current runner already exposes strong building blocks that should remain the
boundary for a first implementation:

- `src/dynamic_agent_runner/context.py` defines `WorkflowExecutionContext` as a
  reusable execution envelope that intentionally excludes the per-run prompt.
- `src/dynamic_agent_runner/api.py` exposes `run_agent_workflow_async(...)`,
  `run_agent_workflow(...)`, reusable `execution_context`, and caller-supplied
  `run_id`.
- `tests/fixtures/power-marimo/agent-runtime.yaml` already models bounded
  workflow state via explicit `runtime.state` artifacts and `state_key` updates.
- `src/dynamic_agent_runner/validation.py` already defines enum scaffolding for
  async session policies:
  - `mode`: `metadata_only`, `reuse_existing`, `create_or_resume`
  - `persist`: `none`, `in_memory`, `external_checkpoint`
  - `history`: `none`, `last_turn`, `full`, `summary`

These surfaces suggest that OA8 should stay declarative in the first pass and
avoid introducing a new execution abstraction.

## Proposed Capability Shape

### Implemented baseline shape

```yaml
runtime:
  execution_policy:
    async_session:
      mode: metadata_only | reuse_existing | create_or_resume
      persist: none | in_memory | external_checkpoint
      history: none | last_turn | full | summary
      session_id_state_key: session.id
      session_messages_state_key: session.messages
```

### Implemented field intent

- `mode`
  - behavior class metadata; live in-memory behavior is implemented by
    `persistent-agent-sessions`, while durable/broader memory behavior remains
    future work for a separate slice
- `persist`
  - declares where future continuity state would live
- `history`
  - declares retained-history intent without requiring replay behavior today
- `session_id_state_key`
  - state field for future host/runtime session identity
- `session_messages_state_key`
  - state field for retained session messages when history is not `none`

### Future expansion candidates

The newer OA8 feature package also evaluates possible later expansion beyond the
implemented baseline, such as:

- explicit summary-backed continuity keys
- richer retention metadata
- stronger host/runtime session contracts for first-customer integrations

Those are design candidates only, not part of the currently implemented seam.

## Functional Requirements

### FR1 — Preserve the implemented declarative async-session metadata seam

The runtime manifest must be able to preserve a compact
`runtime.execution_policy.async_session` mapping as future-oriented metadata
without changing current execution semantics.

### FR2 — Stable session identity declaration

The protocol must be able to declare a future stable session identity field so
host or runtime integrations can correlate multiple runs.

### FR3 — History-retention intent declaration

The protocol must be able to declare retained-history intent using the supported
history modes:

- `none`
- `last_turn`
- `full`
- `summary`

### FR4 — Fail-closed validation

The runtime validator must reject malformed async-session metadata, unsupported
enum values, and stray state-key fields whose matching policy is inactive.

### FR5 — No runner-owned storage behavior in the implemented baseline

The first OA8 implementation must not itself add:

- durable storage backends
- automatic transcript replay
- automatic history retrieval
- automatic summary generation
- semantic pruning execution

### FR6 — Future compatibility with summary and retention workflows

The protocol must remain broad enough that later implementations can add
summary-backed continuity or retention-aware continuity without redefining the
basic session identity and history-retention fields. Live prompt pruning and
compaction remain owned by `context-management-prepare-stage`.

## Validation Rules

The current implemented validator pass enforces these fail-closed rules.

### Required enum fields

- `mode` is required and must be one of:
  - `metadata_only`
  - `reuse_existing`
  - `create_or_resume`
- `persist` is required and must be one of:
  - `none`
  - `in_memory`
  - `external_checkpoint`
- `history` is required and must be one of:
  - `none`
  - `last_turn`
  - `full`
  - `summary`

### State-key field rules

When present, these fields must be non-empty strings:

- `session_id_state_key`
- `session_messages_state_key`

### Current implemented coupling rules

- if `persist != none`, `session_id_state_key` is required
- if `persist == none`, `session_id_state_key` must be omitted
- if `history == none`, `session_messages_state_key` must be omitted

### Future expansion note

If a later slice adds explicit summary-backed or split raw-history state keys,
that should be treated as a forward expansion from the current implemented
baseline rather than retroactively redefining the existing OA8 seam.

## Non-Goals

The first OA8 implementation must not introduce:

- vector-memory backends
- embedding configuration
- retrieval configuration
- semantic top-k parameters
- cross-run automatic replay
- summary-generation prompts
- multi-agent shared memory
- branching transcript DAG semantics
- approval pause/resume behavior

Those belong to later slices or adjacent workflow areas such as OA7.

## First-Customer Readiness Assessment for Power-Marimo

### Decision

The current API surface is sufficient for a first-customer `power-marimo`
workflow **if continuity is managed by the host/client across repeated calls**.

### Why

- reusable `WorkflowExecutionContext` already exists
- repeated async calls already exist
- caller-owned `run_id` already exists
- the fixture and package model already support bounded stateful workflows
- the likely first customer needs supervised bounded notebook/power-analysis
  orchestration more than runner-native durable multi-turn memory

### Constraint

The current API is **not** yet a native runner-owned multi-turn session
platform. Product and implementation language should stay honest about that.

See `specs/async-session-memory-pipeline/decision-memo.md` for the full memo.

## Acceptance Criteria

### AC1 — Protocol-only scope remains explicit

Given the OA8 feature spec,
when a future implementation uses it as guidance,
then it must preserve session-id and history-retention metadata without
claiming runner-owned durable memory or replay behavior in the first pass.

### AC2 — Validation expectations are concrete

Given a malformed `runtime.execution_policy.async_session` block,
when validation is implemented from this spec,
then unsupported enums, missing required state-key fields, and stray inactive
fields from the implemented baseline must be rejected.

### AC3 — Power-Marimo host-managed continuity remains a supported v1 story

Given the current public API surface,
when `power-marimo` manages continuity in the host across multiple calls,
then the runner can honestly be used for a first-customer bounded multi-turn
workflow without waiting for OA8 implementation.

### AC4 — Portable supporting references are repo-local

Given this feature spec,
when another machine or session reads it,
then the key external-document insights needed for understanding the feature are
available through repository-local supporting files rather than only external or
machine-specific paths.

## Risks and Tradeoffs

- If OA8 only models simplistic sliding-window continuity later, it may block
  richer retention-aware continuity.
- If OA8 tries to solve storage, replay, context preparation, and
  approval-resume in one step, it will likely exceed its intended narrow scope.
- If host-managed continuity is not documented for `power-marimo`, users may
  infer runner-native memory support that does not exist yet.

## Recommended Next Steps

1. Keep OA8 as an implemented metadata seam plus future feature-spec expansion
   package.
2. Do not block first-customer `power-marimo` delivery on OA8 implementation.
3. Document host-managed continuity as the v1 multi-turn pattern.
4. Prioritize safe tool adapters and, if needed, OA7 before treating OA8 as a
   customer-facing requirement.
5. Use `capability-status-report` so callers can distinguish host-managed
   continuity, metadata-only session declarations, live in-memory
   `AgentSession` support, and any future durable session store.
