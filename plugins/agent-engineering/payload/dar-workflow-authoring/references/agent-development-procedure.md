---
lifecycle: retained-disabled
---

# Agent Development Workflow

<task_objective>
Design, specify, evaluate, or prepare a framework-neutral AI agent or agentic
system while deciding honestly whether an agent is warranted at all.
</task_objective>

<when_to_use>
Invoke this workflow when the user asks to design, build, specify, evaluate,
review, or implement an AI agent, or when the task requires deciding whether a
problem should use an agent, workflow, RAG system, tool-calling loop,
multi-agent system, or other autonomous AI component.
</when_to_use>

## Activation Conditions

- **Activation:** contextual or explicit
- **Trigger when:**
  - the user asks to design, build, specify, evaluate, review, or implement an
    AI agent
  - the user asks whether a task should use an agent, workflow, RAG system,
    tool-calling loop, multi-agent system, or autonomous AI component
  - the task requires choosing autonomy, tools, memory, runtime, evaluation,
    observability, or safety controls
  - an SDD, plan, or implementation request makes agent architecture a material
    design decision
- **Requires:**
  - a target product, repository, feature, or system context
  - enough information to evaluate whether agentic behavior is needed, or a
    clear need to ask clarifying questions
- **Do not apply when:**
  - the task is an ordinary code edit, documentation edit, or bug fix where
    agent architecture is not in scope
  - the user only wants completion debate, Council advice, SDD artifacts
    without an agent design decision, or live source-system work without the
    applicable MCP workflow

## Core Expectations

- Decide whether an agent is warranted before designing one. Prefer
  deterministic code, fixed workflows, RAG, or simple LLM calls when they
  satisfy the need.
- Stay framework-neutral. Do not assume a provider, framework, SDK, hosting
  model, or runtime unless selected by the user, repository, or governing spec.
- Support local, in-process, cloud API, embedded, offline or air-gapped, and
  hybrid runtimes.
- Treat provider-specific examples as vocabulary, not required infrastructure.
- Use the three-layer model for non-trivial designs:
  - agent pattern — what kind of agent is being built
  - LLM workflow — how cognition, retrieval, or reasoning is structured
  - agentic workflow — how agents, tools, events, and systems coordinate
- For research, review, or evidence-heavy agents, prefer explicit sufficiency
  checks over vague “keep going until it looks done” behavior.
- Choose the lowest autonomy level that satisfies the task.
- Define tool, event, memory, structured-output, context, safety, evaluation,
  and observability contracts before implementation.
- Ask for or infer provider-neutral model requirements from the source task for
  each material `llm_step`, including required capabilities, reasoning depth,
  context needs, output requirements, operational tradeoffs, and fallback
  policy.
- For non-trivial designs, record the runtime surface and workspace boundary so
  callers can tell where orchestration runs and what live state may be
  affected.
- For side-effecting designs, distinguish enforceable permission profiles from
  approval prompts; asking permission is not the same as enforcing a boundary.
- For any generated agent workflow or runtime package, define an explicit exit
  strategy before implementation. For loops, include terminal conditions plus
  hard iteration or step bounds so the workflow cannot run forever.
- For non-trivial agent loops, define the completion contract and result
  surfaces before implementation.
- For complex observability, distinguish model-visible context from runtime-only
  evidence, traces, tool payloads, and raw diagnostics.

## Related Workflows and Skills

- Use `corpus/capabilities/agent-development/SKILL.md` for detailed execution
  mechanics, artifact generation, and implementation handoff.
- Use `corpus/policies/65-spec-driven-development.md` and
  `corpus/procedures/spec-driven-development.md` when durable feature-level
  specs,
  plans, tasks, approvals, or drift control are needed.
- Use `corpus/policies/68-source-mcp-selection.md` for live Confluence, Jira,
  or other
  source-system MCP access.
- Use `corpus/procedures/obsidian-memory-workflow.md` for Obsidian-backed
  durable AI
  memory.
- Use `corpus/procedures/council-deliberation.md` for multi-perspective advice
  about an agent decision, not as the agent-design workflow itself.
- Use `corpus/procedures/completion-debate.md` only when the user explicitly
  wants adversarial completion verification or a Judge gate.

## Orchestration Expectations

- Load `corpus/capabilities/agent-development/SKILL.md` for agent-vs-non-agent
  evaluation, architecture selection, contract definition, artifact generation,
  and implementation-handoff mechanics.
- Keep the current task context, desired deliverable shape, and any SDD,
  runtime, source-MCP, or Obsidian-memory boundaries explicit before the skill
  proceeds.
- Route follow-on implementation, live source access, durable memory work, or
  subagent execution to their stronger workflows instead of embedding those
  mechanics here.
- Report the agent decision, chosen architecture, artifacts, risks, and next
  workflow clearly.

## Agent-vs-Non-Agent Decision Policy

Prefer a non-agent solution when steps are known at design time, deterministic
code or a fixed workflow can produce the result, a single LLM/RAG flow is
enough, no dynamic tool selection or iteration is needed, or safety and
evaluation would be stronger with a simpler design.

An agent may be warranted when the system needs open-ended runtime decisions,
dynamic tool selection, multi-step planning, iterative refinement, bounded
external actions, memory across runs, or specialized roles that do not fit one
fixed workflow.

If evidence is insufficient, record the decision as uncertain and ask for
clarification instead of defaulting to agentic complexity.

## SDD Relationship

A top-level SDD may drive the agent design choice. When it exists, consume it
as governing context for scope, autonomy, runtime constraints, tool
permissions, privacy boundaries, acceptance criteria, and validation.

When the user asks to design or build the agent as a feature, or asks for SDD,
create or update feature-level SDD artifacts following
`corpus/policies/65-spec-driven-development.md` and
`corpus/procedures/spec-driven-development.md`, commonly:

```text
specs/<agent-feature-slug>/spec.md
specs/<agent-feature-slug>/agent-design.md
specs/<agent-feature-slug>/plan.md
specs/<agent-feature-slug>/tasks.md
specs/<agent-feature-slug>/validation.md
specs/<agent-feature-slug>/decision-log.md
```

This workflow may populate `agent-design.md`, but SDD remains authoritative for
spec gates, artifact authority, approvals, consistency analysis, and drift
control.

## Safety and Authority Boundaries

Agent design does not override stronger workflow authority:

- Rule 68 and `corpus/capabilities/mcp-server-wrapper/SKILL.md` govern live
  external source-system access through the repository-local wrapper.
- Obsidian memory workflow governs Obsidian-backed durable AI memory.
- `corpus/procedures/memory-bank-maintenance.md` governs repo-local durable
  project
  memory.
- `corpus/procedures/artifact-task-control.md` governs restart-authoritative
  task state.
- SDD governs feature intent, specs, plans, tasks, approvals, and drift when
  SDD artifacts are active.

High-risk agent behavior needs explicit boundaries:

- Side-effecting, destructive, costly, privacy-sensitive, or
  security-sensitive actions require approval unless a stronger active workflow
  or user-approved policy already permits them.
- For research, compliance, market, pricing, policy, or other fact-sensitive
  agents, define when grounded retrieval is mandatory and whether the agent may
  answer from model memory alone at all.
- Approval prompts do not replace enforceable sandbox, network, filesystem,
  external-system, or mutation boundaries.
- Experimental capabilities require explicit opt-in and compatibility caveats
  before they become design assumptions.
- Do not store secrets, credentials, or high-risk personal data in prompts,
  memories, traces, or generated artifacts.

<detailed_sequence_of_steps>

1. Load `corpus/capabilities/agent-development/SKILL.md`.
2. Confirm the governing context, desired agent-design deliverable, and any
   active SDD, source-MCP, memory, runtime, or approval constraints.
3. Tell the skill whether the request is evaluating whether an agent is needed,
   producing a design handoff, or preparing runtime-oriented agent artifacts.
4. Follow the skill for architecture evaluation, contract definition, artifact
   generation, and follow-on workflow selection.
5. Route implementation, MCP-backed source-system work, Obsidian-memory work,
   or rigorous subagent execution to the stronger downstream workflow as needed.
6. Report the agent decision, architecture, generated artifacts, open questions,
   risks, and next workflow honestly.
</detailed_sequence_of_steps>

<expected_output>
Return an honest agent-design result that states whether an agent is warranted,
what autonomy/runtime/pattern choices were made, what contracts and safety
boundaries apply, what artifacts were generated, and which workflow should be
used next.
</expected_output>

## Completion Standard

This workflow is being followed correctly when:

- detailed agent-design mechanics were handled through
  `corpus/capabilities/agent-development/SKILL.md`
- framework-neutral design boundaries and stronger workflow authorities remained
  explicit
- the agent decision, architecture result, risks, and next workflow were
  reported honestly
