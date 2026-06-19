# Subagent Tool Pack Specification

## Metadata

- Feature slug: `subagent-tool-pack`
- Mode: `light`
- Artifact type: implemented feature specification
- Status: implemented v1 baseline
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Required predecessors:
  - `specs/persistent-agent-sessions/spec.md`
  - `specs/iterative-agent-loop-runtime/spec.md`
  - `specs/capability-status-report/spec.md`
- Related feature packages:
  - `specs/collaborative-agent-sessions/spec.md`
  - `specs/model-event-streaming/spec.md`
  - `specs/web-tool-pack/spec.md`
  - `specs/sandbox-workspace-runtime/spec.md`
  - `specs/approval-interruption-resume/spec.md`
  - `specs/live-guardrail-execution/spec.md`
  - `specs/context-management-prepare-stage/spec.md`
- Collateral:
  - `specs/subagent-tool-pack/analysis.md`

## Objective

Add an explicit, opt-in built-in subagent tool pack that lets a parent
`llm_step` delegate bounded work to one or more child model/workflow executions
through the existing `ToolRegistry` boundary.

The first implementation target is Cline-style callable specialist fanout:
short-lived child executions with constrained tools, budgets, and structured
aggregate results. Persistent spawned child sessions are intentionally deferred
to `collaborative-agent-sessions`.

## Implementation Status

The v1 baseline is implemented in `src/dynamic_agent_runner/subagents.py` with
exports from `dynamic_agent_runner`.

Completed:

- opt-in `run_subagent` and `run_subagents` registry pack
- required injected `SubagentRunner`
- explicit `SubagentPreset` and `SubagentToolPolicy`
- maximum child-count enforcement
- normalized `SubagentResult` and aggregate child result mapping
- fake-runner tests and import coverage

Deferred:

- parallel execution and `max_parallel` enforcement
- per-child timeout, iteration, token, or cost-budget enforcement
- parent/child trace correlation and capability/status reporting
- approval, sandbox, guardrail, and recursive-spawn policy enforcement beyond
  metadata defaults
- optional `ask_llm`
- durable child sessions, lifecycle APIs, and parent/child topology, which
  remain owned by `collaborative-agent-sessions`

## Problem Statement

DAR already has the right primitives for bounded delegation:

- `ToolRegistry` is the authority for model-visible tool exposure.
- `llm_step` model tool calls already dispatch through the registry.
- `execute_workflow_async(...)` can run a child workflow with ordinary runtime
  limits, traces, guardrails, approval policy, and tool registries.
- `AgentSession` can preserve state across prompts when persistence is needed.
- `accept_stream(...)` can expose redacted execution events for session-backed
  runs.

What is missing is a standard package-owned tool shape for "ask a specialist"
or "run these bounded child investigations" without every host inventing its
own delegation schemas, concurrency limits, result aggregation, trace posture,
and state boundary.

## Design Position

Subagents should enter the runtime as tools first.

The parent workflow remains an ordinary finite workflow. A parent `llm_step`
can call a registered subagent tool; the tool handler may execute a child
workflow, a one-shot LLM call, or a child `AgentSession`, but that execution is
behind the tool boundary and returns a normal `ToolResult`.

This avoids adding a new primitive workflow node kind. Multi-agent structure is
metadata and registry behavior, not a replacement for `llm_step`,
`tool_use_step`, and `decision_step`.

## LLM-as-Tool Fit

`llm as a tool` is the narrowest useful subagent form, not a competing
architecture.

The stack is:

1. plain tool: deterministic or external action behind `RegisteredTool`
2. LLM as tool: one bounded model interaction behind `RegisteredTool`
3. workflow as tool: child `execute_workflow_async(...)` behind `RegisteredTool`
4. session as tool: child `AgentSession.accept(...)` behind `RegisteredTool`

The first subagent pack should support workflow-as-tool and may include a
smaller LLM-as-tool adapter pattern for classification, summarization,
extraction, review, compaction, or "ask a specialist model once" use cases.
Session-as-tool behavior belongs to `collaborative-agent-sessions` unless the
child session is caller-owned and already registered as an ordinary tool.

## Scope

This feature covers:

1. an opt-in built-in `subagent` registry pack
2. model-visible tool schemas for bounded delegation
3. execution of one or more child prompts through injected child runners
4. child workflow/session configuration and tool allowlists
5. concurrency, iteration, timeout, and token-budget limits
6. result normalization and aggregate result shaping
7. trace events and redaction for parent/child correlation
8. approval, sandbox, guardrail, and capability/status integration
9. fake-client/fake-runner tests only

## Non-Goals

This feature must not introduce:

- ambient subagent availability for every workflow
- unbounded autonomous child loops
- recursive child spawning by default
- new primitive workflow node kinds
- durable child session management
- cross-process agent process management
- cloud or IDE-specific collaboration protocols
- live model, web, MCP, shell, or filesystem calls in unit tests
- automatic broad tool inheritance from the parent

Persistent spawned agents, resumable child sessions, child lifecycle APIs, and
parent/child thread topology are owned by `collaborative-agent-sessions`.

## Proposed Tool Pack Shape

The first built-in pack should be named `subagent` and remain disabled by
default.

Candidate v1 tool ids:

- `run_subagent` - run one bounded specialist prompt and return one result.
- `run_subagents` - run a bounded list of specialist prompts, optionally in
  parallel, and return an aggregate result.
- `ask_llm` - optional smaller adapter for a one-shot model interaction when a
  full workflow child is unnecessary.

The minimal useful slice may implement only `run_subagents` if that keeps the
parent-facing contract closer to the external evidence.

Conceptual API shape:

```python
registry = create_subagent_registry(
    runner=child_runner,
    presets={
        "research": SubagentPreset(
            workflow=research_workflow,
            tool_ids=("local_workspace_search", "web_search"),
            max_iterations=3,
            timeout_seconds=60,
        ),
        "reviewer": SubagentPreset(
            model_requirements={"reasoning_profile": {"level": "high"}},
            tool_ids=("local_workspace_read",),
            max_iterations=1,
        ),
    },
    policy=SubagentToolPolicy(
        max_children=5,
        max_parallel=3,
        require_approval=True,
        allow_recursive_spawn=False,
    ),
)
```

Names are draft. Implementation planning should keep concrete APIs small and
aligned with existing registry and capability-reporting conventions.

## Users and User Stories

- As a workflow author, I can expose a specialist delegation tool to selected
  `llm_step` nodes without changing the graph node taxonomy.
- As an application host, I can constrain child tools, budgets, model
  requirements, concurrency, and approval policy before exposing subagents.
- As a parent model, I can ask bounded specialists to inspect different aspects
  of a problem and receive structured results.
- As a safety reviewer, I can verify child executions inherit appropriate
  runtime limits and cannot silently broaden tool authority.
- As a UI caller, I can correlate parent tool calls with child run summaries
  without receiving raw child transcripts by default.

## Functional Requirements

### FR-1: Keep Subagents Explicitly Opt-In

Given no subagent pack is enabled and no caller registers equivalent tools, when
a workflow references subagent tool ids, then execution must fail through the
existing unavailable-tool path.

Given the caller enables the subagent pack, when registry preparation runs, then
subagent tools are registered only in the effective registry and are still
exposed only to nodes that reference them.

### FR-2: Run Child Work Through Injected Runners

Given a subagent tool is invoked, when child work is needed, then the runtime
must call an injected child runner rather than hard-coding a provider, global
model, external process, or IDE service.

The child runner may wrap `execute_workflow_async(...)`, an `AgentSession`, or a
one-shot model adapter, but the pack contract should depend on a small
package-owned interface that is fakeable in tests.

### FR-3: Preserve Registry Authority and Tool Isolation

Given a child execution starts, when it needs tools, then child tool exposure
must be derived from explicit preset/policy allowlists.

The child must not automatically inherit every parent tool. Recursive spawning
must be disabled by default and require explicit policy approval if ever
enabled.

### FR-4: Bound Delegation

Given a subagent tool invocation contains one or more child prompts, when the
tool runs, then policy must enforce maximum children, maximum parallel children,
per-child timeout, per-child step/iteration limits, token or cost budgets where
available, and aggregate output limits.

Limit exhaustion must return a structured partial/failed child result rather
than leaving the parent without correlation.

### FR-5: Normalize Child Results

Given child executions complete, when the parent receives the `ToolResult`, then
the model-facing output must use a bounded package-owned shape.

Each child result should include child id, preset/role, status, result summary,
error category when failed, elapsed time, budget/limit facts when available,
and optional citations or evidence handles. Raw child traces and transcripts
must not be model-visible by default.

### FR-6: Support Structured Aggregate Results

Given multiple child executions run, when aggregation completes, then the tool
must return both per-child results and an aggregate summary or status block that
lets the parent reason about successful, failed, timed-out, interrupted, and
cancelled children.

The aggregate result must preserve deterministic ordering, even when child work
is executed concurrently.

### FR-7: Preserve Approval, Guardrail, and Sandbox Boundaries

Given child work can amplify tool-use risk, when a subagent tool is exposed,
then policy must declare approval behavior, sandbox/network/workspace grants,
guardrail placement, and forbidden tool classes.

Approval-required child actions must pause or fail closed through existing
approval surfaces; v1 must not perform child side effects before required
approval.

### FR-8: Correlate Parent and Child Observability

Given a subagent tool invokes child work, when trace events are emitted, then
events must correlate parent run id, parent node id, parent tool call id, child
run/session id when available, child preset/role, status, duration, limits, and
redacted result preview.

Trace payloads must not dump full child transcripts, raw tool arguments, raw
tool outputs, secrets, or unbounded page/file contents.

### FR-9: Report Capability Status

Given a workflow references subagent tools, when capability status is generated,
then the report must distinguish disabled subagent pack, missing child runner,
missing child presets, live configured runner, policy-rejected configuration,
and metadata-only subagent declarations.

## Acceptance Criteria

- The `subagent` pack is disabled unless explicitly enabled.
- Subagent tools resolve only through `ToolRegistry`.
- A missing injected child runner fails clearly.
- Child tool authority is explicit and isolated from broad parent registry
  inheritance.
- Policy enforces max children, max parallelism, timeout, iteration, and output
  bounds.
- Multiple child results preserve deterministic aggregate ordering.
- Child failures, timeouts, and interruptions are represented per child.
- Parent-visible output is structured and bounded.
- Traces correlate parent and child activity while redacting raw transcripts.
- Capability/status reports disabled, missing-collaborator, live, and
  policy-rejected states.
- Unit tests use fake child runners, fake model adapters, and fake registries.

## Implementation Planning Notes

- Start test-first in registry/capability tests for disabled-by-default behavior,
  missing runner failures, and configured pack reporting.
- Add executor tests for a parent `llm_step` model tool call that invokes
  `run_subagents` and receives normalized child results.
- Add fake runner tests for success, child failure, timeout, partial aggregate,
  deterministic ordering, and max-child rejection.
- Keep child execution behind a package-owned protocol so direct workflow,
  one-shot LLM, and session-backed implementations can share the same pack
  contract.
- Treat `ask_llm` as optional. Do not add it unless the implementation can keep
  model requirements, prompt schema, output contract, and trace redaction small.
- Do not expose recursive subagent spawning in v1.
- Route durable child state and lifecycle APIs to
  `collaborative-agent-sessions`.

## TDD Implementation Tasks

Completed v1 slices:

1. RED: pack disabled/unavailable tests; GREEN: opt-in registry registration and
   missing-runner failure.
2. RED: child runner protocol tests; GREEN: fake runner invocation and
   normalized single-child result.
3. RED: fanout tests; GREEN: bounded serial child execution with deterministic
   aggregate ordering.
4. RED: policy-limit tests; GREEN: max children enforcement.
5. RED: executor integration test; GREEN: parent `llm_step` model tool call uses
   the subagent tool through ordinary registry dispatch.

Deferred slices:

1. RED: policy-limit tests; GREEN: max parallel, timeout, iteration, output
   limit, and recursion-disabled enforcement.
2. RED: trace/capability tests; GREEN: parent/child correlation, redaction, and
   capability/status states.

## Validation Checklist

Relevant commands:

```bash
poetry run pytest tests/test_subagents.py tests/test_import.py -q
poetry run pytest tests/test_executor.py -q
```

Deferred validation must confirm no live model, web, MCP, shell, or filesystem
dependency appears in unit tests unless explicitly faked.
