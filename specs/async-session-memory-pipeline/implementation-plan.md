# Async Session Memory Pipeline Implementation Plan

## Goal

Record the completed adjacent work target that depended on OA8 session metadata:
pruning-context graph injection for `llm_step` interactions. The runtime
continues to preserve validated `runtime.execution_policy.async_session`
metadata without adding durable runner-owned session storage or broader memory
behavior, and live in-memory session continuity is implemented separately by
`specs/persistent-agent-sessions/spec.md`.

## Scope Boundary

This plan is a **completed handoff record**, not an authorization to expand OA8
into live memory execution. It does not replace the implemented `AgentSession`
v1 surface and does not move context-management or graph-mutation ownership into
the async-session feature package.

Already implemented baseline:

- preserve the `async_session` mapping in loaded runtime metadata
- validate the mapping fail-closed
- surface the metadata through compiled/prepared workflow structures

Completed handoff scope:

- confirmed the async-session metadata consumed by pruning-context injection
- routed implementation ownership to `context-management-prepare-stage` and
  `internal-graph-mutation`
- defined the TDD entry point for injecting pruning-context behavior around
  eligible `llm_step` interactions
- verified that existing `AgentSession` session messages can flow into the
  prepare-stage path without adding a durable memory backend

Out of scope:

- durable session storage
- transcript replay
- runner-owned context pruning execution inside OA8
- runner-owned summary generation inside OA8
- API changes that add first-class session objects
- host-managed continuity helpers for `power-marimo`
- public graph-mutation package schemas
- structural graph insertion beyond the approved graph-mutation slice

## Proposed Artifact Shape

Current implemented manifest block:

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

Future expansion candidates should build from this exact baseline rather than
replacing it informally in the docs.

## Owning Feature Boundaries

- `async-session-memory-pipeline` supplies the metadata seam for session
  identity and retained-history intent.
- `persistent-agent-sessions` supplies live in-memory session state and restart
  snapshots through `AgentSession` and `InMemorySessionStore`.
- `context-management-prepare-stage` supplies pruning, compaction, lane assembly,
  prompt-context injection, and preparation diagnostics.
- `internal-graph-mutation` supplies graph-level attachment or insertion around
  eligible `llm_step` nodes and edges.

Future work streams should start from the context-management or graph-mutation
artifacts while keeping this package as a boundary reference.

## Implementation Files

### 1. `src/dynamic_agent_runner/executor.py`

This is the integration point where session messages, prepared input, and
mutation-derived context currently meet.

Completed work:

- add RED coverage first for an eligible `llm_step` interaction receiving pruned
  session context from existing session messages
- keep `WorkflowExecutionState.session_messages` as the input source for this
  pass
- preserve current behavior when no context-management or graph-mutation policy
  is enabled
- emit preparation diagnostics through the existing prepared-input metadata path

### 2. `src/dynamic_agent_runner/graph_mutation.py`

This owns the graph-injection seam for eligible `llm_step` interactions.

Completed work:

- start with the existing input-transform mutation checkpoint
- add only the narrow metadata or runtime shape needed to select pruning-context
  behavior for an `llm_step` interaction
- leave true edge rewiring or inserted nodes for a later approved structural
  graph-mutation slice unless the new tests prove the existing attachment seam is
  insufficient

### 3. `src/dynamic_agent_runner/models.py`

The async-session typed model support already exists. Future work here should
extend it only if a later work stream proves the current metadata shape cannot
identify the relevant session input.

Retained boundary:

- preserve compatibility for the existing `AsyncSessionPolicy`
- avoid new durable-memory fields unless a separate OA8 expansion is approved
- keep `RuntimeManifest` / `ExecutionPlan` propagation aligned with the existing
  metadata-only seam

### 4. `tests/test_executor.py`

This was the primary TDD surface for proving model-input behavior.

Executed RED tests:

- an eligible `llm_step` interaction receives pruned context from supplied
  session messages before the model call
- a workflow with no pruning-context policy remains unchanged
- diagnostics identify included, pruned, compacted, or omitted session context
  without leaking full transcript content

### 5. `tests/test_graph_mutation.py`

This proved graph-level injection shape remains a derived runtime
operation rather than an in-place package edit.

Executed RED tests:

- the base workflow artifact remains unchanged after pruning-context attachment
- eligible `llm_step` interactions receive the derived mutation behavior
- ineligible nodes fail closed through existing validation or mutation checks

## Executed Task Breakdown

1. Added RED executor coverage for pruning-context behavior fed by existing
   `session_messages`.
2. Added RED graph-mutation coverage for the attachment diagnostics needed by
   the target `llm_step` interaction.
3. Implemented the narrowest prepare-stage integration that prunes or compacts
   supplied session messages before the model call.
4. Kept async-session metadata unchanged because tests did not prove a missing
   declaration is required.
5. Recorded diagnostics through existing prepared-input and mutation metadata.
6. Re-ran targeted validation for executor, graph mutation, session, and
   validation surfaces.

## Suggested Validation Commands

Primary targeted checks:

```bash
poetry run pytest \
  tests/test_executor.py \
  tests/test_graph_mutation.py \
  tests/test_agent_sessions.py \
  tests/test_validation.py -q
```

If only documentation changes are made while preparing the stream, run:

```bash
pre-commit run --files \
  specs/async-session-memory-pipeline/spec.md \
  specs/async-session-memory-pipeline/implementation-plan.md \
  specs/README.md
```

If model metadata changes are later approved, widen to:

```bash
poetry run pytest \
  tests/test_validation.py \
  tests/test_artifacts.py \
  tests/test_executor.py -q
```

If model-specific fixtures are touched, also include:

```bash
poetry run pytest \
  tests/test_validation.py \
  tests/test_artifacts.py \
  tests/test_executor.py \
  tests/test_power_marimo_fixture.py -q
```

## Delivered Result

Eligible `llm_step` interactions can now receive pruning-context preparation
from supplied session messages through the existing context-management and
graph-mutation seams. The repository should keep the validated, portable,
metadata-only
`runtime.execution_policy.async_session` seam unchanged unless a concrete test
proves an additional declaration is required, and durable memory behavior should
remain out of OA8 until a separate slice is approved.
