# Agent Development Workflow Mechanics

This reference contains operational mechanics used by the governing
`agent-development` workflow. That workflow remains authoritative for
activation, policy, safety, authority boundaries, and completion requirements.
Load this reference only after the workflow is in use and execution details are
needed.

## Moved sections

## References

- `agent-runtime-package.md` — authoritative for local agent-design
  vocabulary, framework-neutral pattern selection, autonomy levels, contracts,
  memory boundaries, evaluation, and runtime-package conventions
- bundled SDD runtime contract — authoritative for agent SDD artifacts,
  approvals, artifact authority, consistency analysis, and drift control
- the paired `agent-development` execution skill — use for discovery, pattern
  selection, design artifacts, and implementation handoff
- bundled source-system MCP runtime policy — authoritative for live MCP-backed
  source-system reads or mutations
- bundled Obsidian memory runtime contract — authoritative for Obsidian-backed
  durable AI memory
- `skill-authoring` — supporting when an agent-design change requires
  substantial skill authoring or revision

## Evaluation and Observability Expectations

Before claiming an agent design or implementation is ready, identify supporting
evidence. Useful evidence includes:

- design review against required dimensions
- evaluator or judge calibration checks when sufficiency scoring or stop/continue
  gates are part of the design
- golden and edge-case tasks
- tool-contract tests and structured-output validation
- safety and prompt-injection checks
- timeout, retry, and failure-mode checks
- trace payload capture, retention, and redaction review
- layered observability checks covering workflow-level traces, orchestrator
  decisions, delegated specialists, and external tool spans when applicable
- event-layer contract review when events cross runtime, UI, transport, or
  telemetry boundaries
- changed-state provenance review for code-writing or mutation-capable agents
- exact validation commands for implemented code

If validation is skipped, partial, unavailable, or only proposed, say so plainly.

## Structured Shape and Behavioral Guidance

For structured output, let schemas and output contracts define field names,
types, cardinality, and structural meaning. Let prompts and instructions define
interpretation, evidence thresholds, quality criteria, exceptions, and common
mistakes. Remove repeated schema definitions from prompts unless the repetition
expresses a behavioral constraint that the schema cannot encode. Existing
runtime-package schema and validator guidance remains authoritative for contract
validation.

## Additional moved sections from workflow evaluation pass (agent-development.md)

## Framework-Neutral Runtime Policy

Record runtime choices explicitly. Valid targets include `local`, `in-process`,
`cloud API`, `embedded`, `offline`, `hybrid`, and `undecided`.

When runtime is undecided, keep the design portable and isolate any
framework-specific interface behind contracts.

Framework or provider selection should consider model capabilities,
tool-calling, structured-output, or embedding support, deployment environment,
data residency and privacy, latency and cost, offline needs, testability,
observability, team familiarity, and maintenance risk.

When a design includes LLM-backed steps, derive provider-neutral model
requirements from the source task before choosing or recommending concrete
models. Use the source task's acceptance criteria, risk, inputs, expected output,
tool use, embedding or semantic-similarity needs, context size, latency, cost,
privacy, and uncertainty tolerance to classify the needed capabilities and
reasoning level. If those facts are missing or materially ambiguous, ask for
clarification or record `unknown`; do not fill the gap with provider
assumptions.

When a design uses retrieval-augmented generation (RAG), record whether retrieval
is keyword, structured lookup, embedding-backed semantic retrieval,
GraphRAG/knowledge-graph retrieval, hybrid, or undecided. For embedding-backed RAG,
define the embedding model requirements, corpus and chunking boundaries,
vector-store or index ownership, metadata filters, reranking or deduplication
behavior, freshness and rebuild policy, citation or provenance requirements, and
fallback behavior when retrieval is weak or unavailable. For GraphRAG, also
define graph construction inputs, entity and relationship extraction policy,
schema or ontology ownership, graph store ownership, traversal and subgraph
selection rules, graph/vector hybrid behavior, conflict resolution, and
provenance for graph-derived claims.

For research or evidence-gathering agents, consider a short named pattern such as
`evidence loop`: start with the least expensive adequate evidence path, evaluate
sufficiency explicitly, deepen retrieval only when needed, and stop when the
evidence clears a defined gate or the retrieval budget is exhausted.

## Runtime Projection and Conversion Hygiene

Use this guidance when one agent definition must be projected into another
runtime format, such as Markdown frontmatter to TOML, YAML, JSON, or a runtime
package manifest.

Treat the source definition as authoritative until the generated target is
reviewed. A converter or projection script should:

- declare the source format, target format, and output location
- expose a dry-run or preview mode before writing files
- use an explicit field mapping table for model, reasoning, tools,
  permissions, memory, turn limits, background behavior, and description text
- preserve unsupported source fields as warnings, comments, or review items
  rather than silently dropping them
- require manual review when a source capability cannot be represented in the
  target runtime, especially memory, background execution, tool restrictions,
  and approval behavior
- validate generated syntax with the target parser or schema
- keep install, registration, and README instructions in sync with generated
  artifacts
- avoid hardcoding a provider or model name unless the target runtime requires
  one and the tradeoff is documented

When generated instructions embed source body text, review the target prompt as
human-facing prose, not merely valid syntax. Remove stale source-runtime
instructions that would mislead the target runtime, and record any semantic loss
in the output summary.

## Required Design Dimensions

Every non-trivial agent design should record:

- purpose, users or callers, in-scope behavior, and out-of-scope behavior
- agent necessity decision and simpler alternatives considered
- autonomy level and approval gates
- runtime and model constraints
- provider-neutral model requirements for material LLM-backed steps, especially
  runtime-package `llm_step` nodes
- runtime surface, workspace boundary, and relevant ownership boundaries when
  runtime state, hosted execution, workspaces, or persistence matter
- selected agent pattern, LLM workflow, and coordination pattern when needed
- evaluator or sufficiency-gate design when the agent gathers evidence, including
  the stop/continue contract and how missing information drives follow-up work
- exit strategy for every generated workflow or runtime package, including
  terminal conditions, exhaustion behavior, ambiguous-completion behavior, and
  hard bounds for any loop
- completion contract and result surfaces for non-trivial loops
- tool exposure strategy, tool contracts, event contracts, and
  structured-output contracts
- model-facing normalization or truncation policy for noisy tool outputs when raw
  backend payloads are too large or cluttered for safe model consumption
- permission, approval, and enforcement model for side-effecting tools or
  external actions
- sandbox, network, mutation-safety, and changed-state-provenance model for
  code-writing, shell-capable, network-capable, or mutation-capable agents
- state, context sources, memory modes, and context pipeline
- RAG or retrieval pipeline details when retrieval augments model context,
  including embedding-backed semantic retrieval and GraphRAG/knowledge-graph
  retrieval when used
- retrieval-depth budgets, retry limits, and escalation criteria when evidence
  gathering can expand in cost or scope
- prompt and instruction architecture, including instruction authority and
  instruction-source precedence when multiple instruction sources exist
- safety, security, and privacy guardrails
- guardrail placement at input, tool, delegated-agent, output, event, or
  mutation boundaries where risk occurs
- diagnostic evidence model for complex agents, including model-visible versus
  runtime-only evidence and trace payload handling
- persistent goals, budgets, and terminal statuses for long-running agents
- configuration layering, compatibility behavior, and explicit opt-in for any
  experimental capabilities
- evaluation, observability, and operations plan
- implementation linkage, open questions, risks, and decisions

For small designs, a compressed version is acceptable if it still records agent
necessity, autonomy, runtime, tools, memory, safety, and evaluation.
