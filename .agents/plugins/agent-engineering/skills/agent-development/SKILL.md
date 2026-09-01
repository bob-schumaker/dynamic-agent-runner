---
name: agent-development
description: Use to design framework-neutral agents with SDD, safety, memory, implementation, and eval boundaries.
related_workflows:
  - ../../references/agent-development-procedure.md
related_rules:
  - preserve host SDD and source-system authorization boundaries
---

# agent development skill

Use this skill when the user wants to design, specify, or prepare an AI agent or
agentic system for implementation. Include baseline evaluation considerations as
one design dimension, but use `agent-evaluation` when evaluation plans,
rubrics, judge workflows, or regression gates are the main task.

This is paired with `../../references/agent-development-procedure.md`. It does
not replace host workflow activation boundaries, framework-neutral policy, SDD
authority, safety requirements, or completion standard.

## Purpose

Turn an agent idea into a reviewable design and implementation handoff:

1. read governing context
2. decide whether an agent is warranted
3. choose runtime, autonomy, agent, LLM-workflow, and coordination patterns
4. define workspace, tool, event, memory, structured-output, safety, evaluation,
   and observability contracts
5. produce an agent spec, SDD artifact, or conceptual external runtime package
6. generate Mermaid/YAML artifacts when a graph-backed manifest is needed
7. route implementation to the correct follow-on workflow

## References

- the governing `agent-development` workflow — authoritative for activation,
  policy, framework neutrality, safety, SDD relationship, and completion
- `agent-tool-contract-design` — supporting; use when agent tool, MCP tool, or
  CLI contract design needs deeper treatment than the main agent-design
  workflow
- `agent-evaluation` — supporting; use when agent evaluation plans, rubrics,
  judge workflows, regression gates, or human-review sampling need deeper
  treatment than the main agent-design workflow
- `references/agent-runtime-package.md` — authoritative for pattern
  vocabulary, runtime manifest, graph, prompt, tool, skill-bundle conventions,
  and runtime-package design details
- `references/agent-development-mechanics.md` — supporting; use for
  framework-neutral runtime policy, runtime projection and conversion hygiene,
  required design dimensions, and validation guidance
- `references/loop-engineering.md` — supporting; use for iterative or
  evidence-gathering loop contracts, verifier-first exits, no-progress guards,
  and in-loop context management
- `references/workflow-efficiency-review.md` — supporting; use for an explicit
  token, latency, cost-risk, or avoidable-model-work review of an agent
  workflow, including a redacted run-evidence report when available
- `references/examples/agent-pattern-examples.md` — supporting; use for
  concise examples when selecting a primary agent pattern
- `references/examples/simple-tool-agent-runtime.yaml` — supporting; use as a
  minimal smoke-test runtime package example
- `references/examples/react-tool-agent-runtime.yaml` — supporting; use as a
  route-gated ReAct/tool-loop runtime package example
- `templates/agent-design.md.template` — supporting; use when generating
  `agent-design.md`
- `templates/agent-runtime.yaml.template` — supporting; use when generating an
  external-runtime manifest
- `templates/agent-graph.mmd.template` — supporting; use when generating a
  Mermaid graph view
- `schemas/agent-runtime.schema.json` — supporting; use as a starter schema
  for `format_version: 1` manifests
- `scripts/validate_agent_runtime.py` — supporting; use for repository-local
  manifest and Mermaid consistency checks
- bundled SDD runtime contract — authoritative when the agent is designed or
  built through SDD artifacts
- `spec-driven-development` — supporting execution procedure for SDD artifact
  creation and maintenance
- bundled source-system MCP runtime policy — authoritative for live
  source-system MCP work that an agent may use or affect
- bundled Obsidian memory runtime contract — authoritative for Obsidian-backed
  durable AI memory

## Moved companion modules and DAR profile

Use the moved private module guidance when its concern is primary:

- `references/modules/agent-action-review/instructions.md`
- `references/modules/agent-environment-health/instructions.md`
- `references/modules/agent-evaluation/instructions.md`
- `references/modules/agent-tool-contract-design/instructions.md`

For an explicitly DAR-targeted workflow, load the supplemental
`../../references/dar-runtime-profile.md`. It preserves DAR package authoring,
host-owned material selection, and invocation/refusal constraints without
replacing this complete general design skill. Do not load it for a bare DAR
mention, a recommendation question, untrusted context, or a local path/ZIP.

## When to use this skill

Use this skill for requests such as:

- design an AI agent for this feature
- decide whether this should be an agent or a workflow
- create an agent design spec
- choose an agent pattern, LLM workflow, or multi-agent architecture
- define tools, memory, guardrails, and evaluation for an agent
- prepare implementation tasks for a tool-calling or memory-augmented agent
- add an `agent-design.md` artifact to an SDD feature
- generate an `agent-runtime.yaml` manifest and `agent-graph.mmd` diagram for a
  conceptual external runtime package
- package node-level prompts, tool descriptions, and required skills for a
  runtime-oriented agent design

Do not use it for ordinary implementation with no agent-design decision, final
completion debate, Council deliberation unless explicitly requested, live
external mutations without rule 68 authorization, or ordinary Obsidian vault
memory maintenance.

## Early Exit for Router Sequencing

If this module was opened only to satisfy router sequencing and the user has
not yet supplied a concrete agent goal, target system or workflow, governing
artifact, or design outcome, stop after this section.

In that case:

- confirm that the first request is classified as `agent-development`
- ask only for the agent goal, target system or workflow, and desired design
  artifact or outcome
- do not load, classify, summarize, or compare a later same-turn module such as
  `agent-evaluation`

## Core execution workflow

### 1. Read governing context

Start with read-only discovery. Inspect only the context needed for the decision:

- user request and success criteria
- active SDD artifacts such as `spec.md`, `plan.md`, or `tasks.md`
- `work-items/` plans or handoffs that govern the work
- `memory-bank/` files when durable repository context matters
- architecture docs, README files, tests, or code that constrain the agent
- source-system or memory-workflow rules when external tools are in scope

If a top-level SDD exists, treat it as governing context. Do not create a
competing planning authority.

### 2. Decide whether an agent is warranted

Compare the requested outcome with simpler alternatives: deterministic code,
ordinary automation, fixed workflow, single LLM call, RAG or retrieval-only
system, and scripted tool sequence with no runtime planning.

Record one decision:

- `agent warranted`
- `agent not warranted`
- `uncertain; clarification needed`

Prefer the simplest honest design. If an agent is not warranted, recommend the
simpler workflow and stop unless the user explicitly wants an agent anyway.

### 3. Establish runtime and model constraints

Ask or infer only from evidence:

- runtime target: local, in-process, cloud API, embedded, offline, hybrid, or
  undecided
- runtime surface and workspace boundary: stateless/stateful, local/shared/remote
  host, sandbox, no workspace, occasional tools, isolated workspace, resumable
  workspace, or per-agent workspace
- ownership boundaries: loop execution, persistence, provider routing, tool
  assembly, approvals, telemetry, UI/client lifecycle
- model capabilities and constraints: tool/function calling, structured output,
  embeddings, vision/input modalities, context, latency, cost, privacy
- source-task evidence for model requirements: task type, reasoning depth,
  capabilities, input size, output contract, citation/evidence needs,
  latency/cost, data boundary, uncertainty tolerance, fallback behavior
- deployment constraints: air-gapped, local-only, data residency, or hosted
  service
- framework or package preferences, if any
- configuration layering: agent defaults, run overrides, environment/provider
  defaults, user/session state, model-input filters, and precedence

If runtime is unknown, record `undecided` instead of assuming a provider. If a
model requirement cannot be inferred from the source task, record `unknown` or
ask a targeted clarification question rather than choosing a provider-specific
default.

### 4. Select the agent pattern

Choose the smallest fitting pattern:

- basic reasoning agent
- tool-based function-calling agent
- tool-server or MCP-style agent
- computer-use agent
- coding agent
- speech or voice agent
- workflow orchestration agent
- memory-augmented agent
- simulation or test-bed agent
- observer or monitoring agent
- multi-agent collaboration

Record why it fits and why more complex patterns are not used.

For delegated or multi-role designs, record the delegation mode: callable
specialist, specialist takeover, one-off sub-agent, persistent team, or peer
coordination. Identify who owns final answers, approval, state, and escalation.

### 5. Select the LLM workflow

Choose the reasoning and context-construction structure: prompt chaining,
routing, parallelization, retrieval-augmented generation (RAG), orchestration,
evaluator/reflection/refine loop, `evidence loop`, ReAct-style observe-think-act
loop, or custom deterministic-plus-model logic.

When selecting a ReAct-style loop for a runtime package, use
`references/agent-runtime-package.md` and the
packaged `react-tool-agent` example for the bounded loop shape, model-safe
observation state, and validator-backed `react_loop` contract. For executable
tool-loop packages, route through an explicit `reason -> route -> tool/final`
gate before any tool-use node so a final route can skip another tool call. Do
not emit an unconditional `llm_step -> tool_use_step` edge for ReAct. When the
user asks for a working package rather than a manifest-only design, include a
small host runner or test harness that registers the manifest tools with the
consumer runtime.

For evidence-gathering or research agents, use progressive depth: start with the
least expensive adequate evidence path, evaluate sufficiency, then retrieve
deeper or more targeted evidence only when the first pass is weak. For research,
review, or evidence-heavy work, `evidence loop` is often the shortest name for
an evaluator-gated workflow:

1. gather the cheapest adequate evidence first
2. run an evaluator or judge with an explicit stop/continue contract
3. if evidence is weak, use the evaluator's missing-information output to drive
   the next retrieval queries
4. stop when the evidence clears the gate or a defined retrieval budget is spent

When using an evaluator or judge, prefer structured outputs that can drive action
instead of vague prose, such as `is_good_enough`, `score`, `reason`, and
`missing_information`. Treat `missing_information` as first-class operational
output because it tells the orchestrator what to retrieve next.

For RAG workflows, decide whether retrieval is keyword, structured lookup,
embedding-backed semantic retrieval, GraphRAG/knowledge-graph retrieval, hybrid,
or undecided. For embedding-backed RAG, record embedding requirements, corpus and
chunking boundaries, index ownership, metadata filters, reranking/deduplication,
freshness/rebuild policy, provenance, and weak/stale/unavailable fallback. For
GraphRAG, record graph inputs, entity/relationship extraction, schema/ontology
and graph-store ownership, traversal/subgraph rules, graph/vector hybrid
behavior, conflict resolution, and graph-claim provenance.

Define an explicit exit strategy before implementation. Every generated agent
workflow or runtime package needs terminal conditions, exhaustion behavior, and
ambiguous-completion handling. Any graph with a loopback or repeatable
tool/model cycle must also include hard iteration or step bounds so it cannot
loop forever. For evidence-heavy agents, record retrieval budgets explicitly,
such as max turns, retry limits, maximum source expansion, and escalation
conditions when evidence stays weak.

For each material LLM-backed step, derive provider-neutral model requirements
from the source task before implementation. In runtime packages, express them as
`llm_step.model_requirements` when useful. Derivation cues:

- task type: classification, extraction, generation, planning, synthesis,
  critique, tool/route selection, code reasoning, math reasoning
- capabilities: structured output, functions/tool calling, embeddings, JSON
  mode, vision/input modalities, code/math reasoning when truly required
- reasoning level: `minimal`, `low`, `medium`, `high`, or `extended`, based on
  ambiguity, planning depth, constraints, risk, and evidence reconciliation
- context, output, and operational needs: input size, retrieved context, minimum
  context window, free text/JSON/schema/tool-call/citations/caveats, latency,
  cost, determinism, privacy/data boundary, fallback behavior

Do not treat reasoning level as permission to expose hidden chain of thought.
Require model-safe summaries or structured decisions when reasoning state must be
carried between steps.

### 6. Select production coordination when needed

Use this step only when the agent interacts with multiple services, agents,
events, queues, or long-running state.

Choose a coordination pattern: none, saga/choreography, dynamic dispatch,
scatter-gather, orchestration/supervisor, or feedback control. Record state
transitions, concurrency limits, compensation, and operator escalation. When
multiple specialists are involved, record whether they are peers, delegated
agents, or callable specialists. Narrow synchronous responsibilities are usually
clearest as callable specialists with strict input/output contracts.

For event-driven, scheduled, or durable automation, also record trigger sources,
goal lifecycle, run-report expectations, and where long-running state is stored.

### 7. Define tool, event, and structured-output contracts

Before enumerating individual tools, select a tool exposure strategy such as
direct exposure, deferred/search-mediated exposure, namespace grouping,
connector filtering, hidden runtime-only tools, or threshold-switched exposure.

For each tool, record:

- name, purpose, and model-facing description
- input and output schema
- model-visible raw or normalized output
- side effects, approvals, evidence depth, cost/latency, escalation criteria
- timeout, retry, failure, streaming, abort, structured-error, logging, audit
- guardrail placement and whether the tool can terminate or complete the run

When a tool contract needs focused design or review, use
`references/modules/agent-tool-contract-design/instructions.md` for naming, trigger
boundaries, schema, output, error, recovery, and safety mechanics.

When tools are contributed by skills, plugins, connectors, MCP servers, or other
extensions, record capability declarations, setup or validation steps, hook
stages, hook authority, and whether contributions are frozen for the session.

For each event or state transition, record name, producer/consumer, payload
shape, ordering, retry, idempotency, and compensation behavior.

For each model-to-code boundary, record the structured-output contract and
validation behavior. Prefer structured outputs and schema validation where
practical.

When backend payloads are large, noisy, or cluttered, define a normalization or
truncation policy before exposing them to the model. Prefer compact,
task-relevant fields, bounded previews, explicit truncation markers, and
preserved provenance over dumping raw payloads into context.

Place guardrails at the boundary where risk occurs: workflow input, model input,
tool input, tool output, delegated-agent boundary, final output, event ingress,
or mutation boundary.

For evaluator or judge roles, ensure output can drive follow-up action:
sufficiency, confidence/score, reason, missing information, recommended next
action.

### 8. Define memory and context policy

Record short-term state, retrieved context sources, durable memory sources,
canonical source of truth, context construction rules, pruning/compression or
retrieval policy, RAG index policy when applicable, and write-back policy.

Record memory mode: replay transcript, session store, server-managed
continuation, durable semantic memory, workspace memory, or compaction layer.
Describe the context pipeline from stable prompts through retrieved context,
redaction, compaction, tool schemas, and provider-bound messages.

When grounded evidence is required, state when the agent must not answer from
model memory alone and which source types it must retrieve or cite.

For research, compliance, policy, pricing, market, or other fact-sensitive
agents, decide explicitly whether model-memory-only answers are forbidden,
discouraged, or allowed only for low-risk scaffolding before grounded retrieval.

If Obsidian memory, memory-bank files, SDD artifacts, handoffs, generated
indexes, or caches overlap, identify which source is authoritative for the
current workflow.

For instruction authority, when multiple instruction sources exist, record
source list, scope, precedence, conflict handling, runtime mutability, and
stronger workflow boundaries. For stateful runtimes, distinguish persisted
session state, per-turn overrides, previewed/committed settings, model-visible
runtime injection, and history injection that does not create a new turn.

### 9. Define autonomy and safety envelope

Record the autonomy level: `assistive`, `supervised agent`, `bounded autonomous`,
or `high-autonomy`.

For that level, define:

- actions allowed without approval
- actions requiring approval
- forbidden actions
- enforceable permission profile for filesystem, network, process, external
  systems, data sources, and mutation authority
- approval policy, channels, pending state, resume owner, sticky/per-call
  decisions, rejection handling
- secrets or data the agent must not access or store
- prompt-injection defenses
- sandbox, network mediation, mutation-safety, and changed-state provenance
- rate, cost, iteration, and timeout limits
- escalation triggers

### 10. Define evaluation and observability

For an explicit workflow-efficiency review, use
`references/workflow-efficiency-review.md`. It owns static versus run-evidence
claim labels and the minimum redacted-report acceptance gate; it does not select
models, dispatch work, execute a runtime, or replace `agent-evaluation`.

Define the completion contract before finalizing evaluation: completion
mechanism, ambiguous-completion behavior, result surfaces, audit surfaces,
continuation state, and durable goals or budgets for long-running agents.

Create an evaluation plan before implementation. Include:

- golden tasks
- edge and failure cases
- evaluator or judge calibration checks when sufficiency scores or stop/continue
  gates are part of the design
- tool-contract tests and structured-output checks
- safety and prompt-injection checks
- regression strategy for prompt, model, memory, and tool changes
- manual review gates for high-risk behavior
- changed-state provenance checks for code-writing or mutation-capable agents

When evaluation design is the main problem, use
`references/modules/agent-evaluation/instructions.md` for evaluation-set
construction, rubrics, judge calibration, human-review sampling, state checks,
and regression gates.

Create an observability plan for event layers, logs, traces, metrics, redaction,
trace payload capture, run reports, model-visible versus runtime-only evidence,
and run reproduction.

For multi-agent or evidence-loop systems, prefer layered observability: a
workflow-level trace, orchestrator decision checkpoints, delegated-specialist or
callable-specialist spans, and external-tool spans when they materially affect
cost, evidence quality, or stopping decisions.

### 11. Generate or update design artifacts

If the user asks for an agent design spec, create or update `agent-design.md`
using:

```text
templates/agent-design.md.template
```

When SDD is active or requested, prefer:

```text
specs/<agent-feature-slug>/agent-design.md
```

For small features, embed the same content into `plan.md` as an `Agent Design`
section when a standalone file would be unnecessary.

When the design will feed a conceptual external runtime package, also
generate a runtime package using:

```text
templates/agent-runtime.yaml.template
templates/agent-graph.mmd.template
references/agent-runtime-package.md
```

Prefer the standard sibling layout unless the user requests another layout:

```text
<design-dir>/agent-design.md
<design-dir>/agent-runtime.yaml
<design-dir>/agent-graph.mmd
<design-dir>/skill-bundle/
```

Follow `references/agent-runtime-package.md` for
runtime-package details: `agent-runtime.yaml` as source of truth,
`agent-graph.mmd` as derived Mermaid view, default `hybrid_bundle`,
`format_version: 1`, node kinds, decision subtypes, tool/skill registries,
pattern metadata, examples, validator, schema, and portability rules. Preserve
the primitive node taxonomy (`llm_step`, `tool_use_step`, `decision_step`) and
use metadata for multi-agent, Council-like, or debate-like structure rather than
inventing new primitive node kinds.

When emitting `llm_step` nodes, ask for or infer `model_requirements` from the
source task when model needs are not obvious. Keep fields provider-neutral and
describe capability/reasoning requirements, not concrete model names. Use
`unknown` for unresolved context windows, cost, latency, data boundaries, or
fallback policy.

When emitting `agent-runtime.yaml`, use the grouped `runtime`, `metadata`, and
`extensions` maps from the runtime-package reference instead of older flat
optional root fields. Treat broad design vocabulary as human-facing until it is
placed in the correct grouped manifest location.

Normalize human-facing autonomy labels to YAML-safe manifest values when needed:
`supervised agent` -> `supervised_agent`, `bounded autonomous` ->
`bounded_autonomous`, and `high-autonomy` -> `high_autonomy`.

Respect SDD gates. Do not approve your own spec, plan, task list, or validation
claim when the SDD runtime contract requires human approval.

### 12. Route implementation work

After design is stable, route the next work explicitly:

- SDD for feature specs, plans, tasks, approvals, and drift control
- native Codex delegation for explicitly requested independent implementation
  streams; use `parallel-plan` only when its independent-stream and
  shared-worktree conditions apply
- rule 68 and the MCP wrapper for live external source-system operations
- ordinary implementation for small local changes that do not need stronger
  workflow control

Do not silently turn design into implementation unless the user requested
implementation and the relevant gates are satisfied.

## Output expectations

When reporting an agent design result, include:

- whether an agent is warranted
- autonomy, runtime/workspace/ownership boundaries, and model assumptions
- source-task evidence used for provider-neutral model requirements
- selected agent pattern, LLM workflow, coordination, delegation/control owner
- tool exposure, event, memory, structured-output, safety, evaluation, and
  observability highlights
- completion contract, result surfaces, permission/approval/enforcement model,
  evidence model, trace privacy caveats when applicable
- generated or updated artifact paths for runtime outputs
- open questions, risks, validation state, and next recommended workflow
