# Collaborative Agent Sessions Specification

## Metadata

- Feature slug: `collaborative-agent-sessions`
- Mode: `light`
- Artifact type: implemented feature specification
- Status: implemented v1 baseline after `subagent-tool-pack`
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Required predecessors:
  - `specs/persistent-agent-sessions/spec.md`
  - `specs/subagent-tool-pack/spec.md`
  - `specs/model-event-streaming/spec.md`
  - `specs/capability-status-report/spec.md`
- Related feature packages:
  - `specs/iterative-agent-loop-runtime/spec.md`
  - `specs/context-management-prepare-stage/spec.md`
  - `specs/provider-backed-context-compaction/spec.md`
  - `specs/model-backed-context-summaries/spec.md`
  - `specs/sandbox-workspace-runtime/spec.md`
  - `specs/approval-interruption-resume/spec.md`
- Collateral:
  - `specs/collaborative-agent-sessions/analysis.md`

## Objective

Add a session-level collaboration layer that lets callers spawn, inspect,
message, wait for, resume, close, snapshot, and restart persistent child agent
sessions.

This feature is the stateful successor to `subagent-tool-pack`. Where the
subagent tool pack returns bounded child results to a parent tool call,
collaborative sessions keep named child agents alive across turns and expose
their current state to the caller.

## Implementation Status

The v1 baseline is implemented in `src/dynamic_agent_runner/collaboration.py`
with exports from `dynamic_agent_runner`.

Completed:

- `CollaborativeAgentSessionManager` for in-memory parent/child session
  coordination
- `CollaborativeAgentPreset`, `ChildAgentState`, and
  `CollaborativeAgentSessionState`
- child spawn, list, get-state, send-input, close, current-state, and
  from-snapshot APIs
- child session construction through an injected `session_factory`
- copy-safe serializable state mappings
- fake-session tests and import coverage

Deferred:

- wait/resume APIs and interruption-specific resume data
- child event streaming
- capability/status reporting
- durable external storage and cross-process locking
- stronger parent/child workflow compatibility validation
- explicit child tool-policy enforcement beyond preset metadata

## Problem Statement

`AgentSession` currently supports one reusable workflow session with in-memory
state retrieval and snapshot restart. That is enough for a single persistent
agent, but it does not model a parent session coordinating multiple child
sessions.

Some workflows need child agents that remain available after the first delegated
task:

- a research child that keeps accumulating source context
- a reviewer child that can be resumed after approval or new evidence
- a compaction/review child used by the parent across multiple prompts
- a long-running specialist that the caller wants to inspect independently

Those scenarios need lifecycle state, parent/child relationships, status,
message routing, event streaming, and restart semantics. They should not be
hidden inside one opaque `ToolResult`.

## Design Position

Collaborative agent sessions are a session-management feature, not a workflow
node feature.

The owning abstraction should be a parent session or session manager that
coordinates child `AgentSession` instances. Parent workflows may interact with
children through registered tools, but callers should also have direct APIs to
retrieve current child state and restart sessions from saved state.

This keeps persistent collaboration aligned with the existing
`AgentSession`/`InMemorySessionStore` model and avoids turning the executor into
an always-running graph process manager.

## Scope

This feature covers:

1. parent/child session topology
2. child agent lifecycle APIs
3. child status and state snapshots
4. restart from saved parent and child state
5. child message routing through bounded `AgentSession.accept(...)` runs
6. optional caller-facing event streaming from child runs
7. child registry/tool-policy isolation
8. lifecycle traces and capability/status reporting
9. `InMemorySessionStore`-backed v1 persistence

## Non-Goals

This feature must not introduce:

- durable external storage in v1
- cross-process locking or distributed schedulers
- IDE/cloud-specific thread protocols as public API
- unbounded always-running graph executors
- automatic background execution without caller-owned lifecycle calls
- broad inherited tool authority for child sessions
- recursive spawning by default
- live model, web, MCP, shell, or filesystem calls in unit tests

## Proposed Public Shape

Names are draft. The intended shape is a small manager layered on top of
`AgentSession` and `InMemorySessionStore`.

```python
manager = CollaborativeAgentSessionManager(
    parent_session=parent,
    session_store=store,
    presets={
        "research": CollaborativeAgentPreset(
            workflow=research_workflow,
            tool_ids=("web_search", "web_fetch", "local_workspace_read"),
            max_concurrent_runs=1,
        )
    },
)

child = manager.spawn_agent(
    preset_id="research",
    name="source-research",
    role="evidence collector",
    prompt="Find evidence about the failing behavior.",
)

await manager.wait_agent(child.agent_id)
state = manager.get_agent_state(child.agent_id)
snapshot = manager.current_state().to_mapping()

restored = CollaborativeAgentSessionManager.from_snapshot(
    snapshot,
    parent_session=parent,
    session_store=store,
    presets=presets,
)
```

Parent workflows may also expose manager operations as tools, but tool exposure
must remain explicit and policy-bound.

## Lifecycle Model

Candidate v1 operations:

- `spawn_agent`: create a child session and optionally start its first prompt
- `send_input`: send a prompt to an existing child session
- `wait_agent`: wait for a running child session to reach a terminal or
  interrupted state
- `resume_agent`: resume a child session after an interruption when resume data
  is available
- `close_agent`: mark a child session closed and reject future prompts
- `get_agent_state`: retrieve child state, status, last run, and metadata
- `list_agents`: list child sessions for a parent session
- `current_state`: retrieve parent collaboration state
- `from_snapshot`: restart the collaboration manager from saved state

Candidate child statuses:

- `pending_init`
- `idle`
- `running`
- `interrupted`
- `completed`
- `errored`
- `closed`
- `not_found`

Status names should be Python/YAML-safe but can map cleanly to external protocol
terms such as Codex's `pendingInit`, `running`, `interrupted`, `completed`,
`errored`, `shutdown`, and `notFound`.

## Users and User Stories

- As an application host, I can spawn a named child agent and continue using it
  across parent prompts.
- As a UI caller, I can list active child agents and show each child's current
  status, role, last result, and interruption state.
- As a workflow author, I can expose selected child-session operations to a
  parent `llm_step` through normal tools.
- As a safety reviewer, I can verify child sessions have isolated tool policy,
  bounded execution, approval handling, and clear shutdown behavior.
- As an application host, I can save a collaboration snapshot and restart the
  manager with parent and child state intact.

## Functional Requirements

### FR-1: Maintain Parent/Child Topology

Given a parent session spawns child agents, when state is retrieved, then each
child must record parent session id, child session id, agent id, name, role,
preset id, workflow identity, status, last run id, and metadata needed for
restart.

Child ids must be stable across state retrieval and snapshot restart.

### FR-2: Spawn Child Sessions Explicitly

Given the caller requests `spawn_agent`, when a child preset is valid, then the
manager must create a child `AgentSession` with explicit workflow context,
store, tool registry, and policy.

Given the preset is missing or policy-rejected, spawn must fail clearly before
creating partial live state.

### FR-3: Route Prompts Through Bounded Session Runs

Given a child receives `send_input`, when it accepts the prompt, then execution
must use the existing `AgentSession.accept(...)` or `accept_stream(...)`
bounded-run semantics.

The child must reject concurrent prompts unless future policy explicitly
serializes a queue.

### FR-4: Expose Current Collaboration State

Given a manager is active, when the caller asks for current state, then the API
must return copy-safe parent/child state including statuses, child snapshots,
turn counts, last results, interruptions, and closed/error metadata.

The state shape must be serializable with ordinary Python data structures.

### FR-5: Restart From Saved State

Given a saved collaboration snapshot, when the caller restarts with compatible
parent context, child presets, and session store, then the manager must restore
child topology and child `AgentSession` snapshots.

Given a snapshot references an incompatible parent workflow, missing child
preset, unknown schema version, or incompatible child workflow identity, restart
must fail clearly.

### FR-6: Close and Reuse Child Sessions Safely

Given a child is closed, when future prompts target that child, then the manager
must reject the operation clearly.

Given a child is idle or completed but not closed, when a new prompt is sent,
then the manager may reuse the same `AgentSession` and append a new bounded run
according to existing session behavior.

### FR-7: Preserve Tool and Workspace Isolation

Given a child session is created, when its workflow needs tools, then the
manager must use explicit preset/caller policy for child tools, workspace,
network, sandbox, approvals, and guardrails.

Children must not inherit all parent tools automatically. Recursive spawn tools
must be disabled by default.

### FR-8: Stream Child Events Optionally

Given the caller requests streaming, when a child run is active, then the manager
should expose redacted child events with parent session id, child agent id,
child session id, child run id, event sequence, event type, and payload.

Partial stream events remain observational. Child session state is committed
only after successful bounded-run completion.

### FR-9: Report Capability Status

Given a package or host declares collaborative-session use, when capability
status is generated, then the report must distinguish unsupported feature,
metadata-only declaration, missing manager/store/presets, live in-memory
manager, policy-rejected configuration, and durable-storage-not-supported.

## Acceptance Criteria

- Child sessions are created only through explicit spawn calls or explicit
  manager tools.
- Parent/child ids, roles, presets, workflow identities, statuses, and last-run
  metadata are retrievable.
- Child prompts execute through ordinary bounded `AgentSession` runs.
- Same-child concurrent prompts fail clearly in v1.
- Child state snapshots can be serialized and restored with
  `InMemorySessionStore`.
- Incompatible parent or child workflow identity fails restart.
- Closed children reject future prompts.
- Child tool registries are explicit and isolated.
- Recursive spawn is disabled by default.
- Optional streaming uses redacted session events and does not commit partial
  deltas as successful assistant turns.
- Capability/status reports missing, live, metadata-only, policy-rejected, and
  durable-storage-deferred states.

## Implementation Planning Notes

- Build on `AgentSessionState` rather than inventing a second transcript model.
- Add a collaboration state dataclass with schema version, parent session id,
  child records, and manager metadata.
- Keep v1 storage in `InMemorySessionStore` or a small in-memory collaboration
  store; durable external persistence is a later spec.
- Use explicit preset ids as the stable bridge between snapshots and runtime
  child construction.
- Keep manager operations callable directly by the host first; expose them as
  parent tools only after direct API behavior is tested.
- Align event names with existing `AgentSessionStreamEvent` where possible.
- Preserve final-result authority from `model-event-streaming`: partial events
  are not committed transcript state.

## TDD Implementation Tasks

Completed v1 slices:

1. RED: manager creation and empty state tests; GREEN: collaboration state
   dataclass, snapshot serialization, and parent id recording.
2. RED: spawn tests; GREEN: child `AgentSession` creation from explicit preset,
   stable agent ids, and missing-preset failures.
3. RED: send tests; GREEN: prompt routing through bounded child
   `AgentSession.accept(...)` and status transitions.
4. RED: close/list/get-state tests; GREEN: closed-state rejection and copy-safe
   child state retrieval.
5. RED: restart tests; GREEN: `from_snapshot(...)` restoration of child state
   with injected presets and session factory.

Deferred slices:

1. RED: wait/resume/concurrency tests; GREEN: wait APIs, interruption resume,
   and same-child concurrency rejection.
2. RED: compatibility tests; GREEN: parent workflow, child workflow, preset id,
   and schema-version checks.
3. RED: streaming tests; GREEN: optional redacted child event forwarding using
   `AgentSession.accept_stream(...)`.
4. RED: capability/status tests; GREEN: live in-memory, metadata-only,
   missing-collaborator, policy-rejected, and durable-storage-deferred states.

## Validation Checklist

Relevant commands:

```bash
poetry run pytest tests/test_collaborative_sessions.py tests/test_import.py -q
```

Deferred validation must confirm unit tests use fake model adapters and fake tool
registries only, with no live OpenAI, MCP, web, shell, filesystem mutation, or
local-model dependency.
