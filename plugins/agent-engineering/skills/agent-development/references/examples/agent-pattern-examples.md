---
title: Agent Pattern Examples
reference_type: examples
applies_to: agent-development
patterns:
  - id: basic-reasoning-agent
    heading: "1. Basic reasoning agent"
  - id: tool-based-function-calling-agent
    heading: "2. Tool-based function-calling agent"
  - id: tool-server-or-mcp-style-agent
    heading: "3. Tool-server or MCP-style agent"
  - id: computer-use-agent
    heading: "4. Computer-use agent"
  - id: coding-agent
    heading: "5. Coding agent"
  - id: speech-or-voice-agent
    heading: "6. Speech or voice agent"
  - id: workflow-orchestration-agent
    heading: "7. Workflow orchestration agent"
  - id: evidence-loop-agent
    heading: "8. Evidence-loop agent"
  - id: knowledge-grounded-rag-agent
    heading: "9. Knowledge-grounded RAG agent"
  - id: memory-augmented-agent
    heading: "10. Memory-augmented agent"
  - id: simulation-or-test-bed-agent
    heading: "11. Simulation or test-bed agent"
  - id: observer-or-monitoring-agent
    heading: "12. Observer or monitoring agent"
  - id: multi-agent-collaboration
    heading: "13. Multi-agent collaboration"
---

## Agent Pattern Examples

Use these concise examples when choosing the `Primary agent pattern`; they are
starting points, not complete specifications. Some entries also name common
workflow overlays, such as RAG variants or evaluator-gated evidence gathering,
because those often change the safest design even when the base agent pattern is
the same. Each real design should still record agent necessity, autonomy,
runtime, tools, memory, safety, evaluation, and observability.

For implementation-ready designs, also record newer paired guidance that affects
the selected pattern: runtime surface, workspace boundary, completion contract,
result surfaces, permission profile, approval policy, tool exposure, context
pipeline, instruction authority, guardrail placement, changed-state provenance,
trace payload handling, and experimental capability opt-ins.

Companion examples show fuller output shapes:

- `runtime-package-agent-design.md` — example `agent-design.md` content using the
  expanded template fields
- `runtime-package-review-agent-runtime.yaml` — richer `agent-runtime.yaml`
  example with optional metadata fields and prompt-cache intent
- `runtime-package-review-agent-graph.mmd` — Mermaid graph paired with that
  richer runtime manifest
- `react-tool-agent-design.md` — route-gated ReAct/tool loop design example
- `react-tool-agent-runtime.yaml` — executable ReAct/tool manifest with
  `llm_route` branching before tool use
- `react-tool-agent-graph.mmd` — Mermaid graph paired with the ReAct/tool
  runtime manifest
- `react-tool-agent-host-pseudocode.md` — host-side pseudocode for registering
  the ReAct example's tool and invoking a consumer runtime
- `evidence-loop-research-agent-runtime.yaml` — evidence-heavy research example
  with evaluator gating, retrieval budgets, and callable specialists
- `evidence-loop-research-agent-graph.mmd` — Mermaid graph paired with that
  evidence-loop runtime manifest
- `multi-agent-coordination-agent-runtime.yaml` — coordinator-owned specialist
  delegation example with bounded `agent_tool` specialists
- `multi-agent-coordination-agent-graph.mmd` — Mermaid graph paired with that
  multi-agent coordination runtime manifest
- `persistent-goal-workflow-runtime.yaml` — long-running durable-goal example
  with checkpoint state and bounded loopback
- `persistent-goal-workflow-graph.mmd` — Mermaid graph paired with that
  persistent-goal runtime manifest
- `event-driven-triage-agent-runtime.yaml` — event-ingress triage example with
  owner notification approval and audit output
- `event-driven-triage-agent-graph.mmd` — Mermaid graph paired with that
  event-driven runtime manifest

### 1. Basic reasoning agent

- Scenario: A support assistant explains whether a proposed configuration is
  valid based on provided policy text.
- Why this pattern fits: The agent reasons over supplied context and produces a
  judgment, but does not need tools or long-running state.
- Simpler alternative: A fixed rules engine may be better if all checks are
  deterministic and policy is machine-readable.
- Typical tools or memory: None beyond prompt context; optional retrieval if
  policy text is too large.
- Autonomy level: `assistive`.
- Safety/auth/logging/redaction: Log decisions and cited policy sections; redact
  customer identifiers from prompts and traces.
- Runtime-package shape: Mostly `llm_step` nodes, with optional `decision_step`
  for pass/fail routing.

### 2. Tool-based function-calling agent

- Scenario: A release assistant checks build status, pulls changelog entries, and
  drafts a release note.
- Why this pattern fits: The agent chooses and calls bounded functions based on
  the user's request.
- Simpler alternative: A scripted pipeline may be better when every step is known
  and always runs in the same order.
- Typical tools or memory: Build-status lookup, changelog query, artifact list,
  and short-term run state.
- Autonomy level: `supervised agent` for read actions; approval before writes.
- Safety/auth/logging/redaction: Scope tool credentials, log tool calls and
  inputs, redact tokens and private artifact URLs.
- Runtime-package shape: `llm_step` for planning, `tool_use_step` for each
  function call, and `decision_step` for missing or failed data.

### 3. Tool-server or MCP-style agent

- Scenario: A workspace assistant reads Jira and Confluence through an internal
  MCP wrapper and drafts a synchronized project summary.
- Why this pattern fits: The agent interacts with external source systems through
  declared tool-server capabilities.
- Simpler alternative: Direct API scripts may be better for one fixed report.
- Typical tools or memory: MCP discovery, page/issue reads, optional comment or
  update tools gated by approval.
- Autonomy level: `assistive` or `supervised agent`.
- Safety/auth/logging/redaction: Use read-before-write, verify target identity,
  log source IDs and mutation status, never log credentials.
- Runtime-package shape: Tool registry entries for MCP commands, `tool_use_step`
  nodes for reads/mutations, and branch decisions for capability availability.

### 4. Computer-use agent

- Scenario: A desktop automation assistant operates a legacy GUI to export a
  report that has no API.
- Why this pattern fits: The task requires interacting with visual UI state and
  performing multi-step actions.
- Simpler alternative: Prefer API, CLI, or file-level automation whenever
  available.
- Typical tools or memory: Screenshot, click/type actions, UI-state memory, and
  checkpoints after each screen.
- Autonomy level: `supervised agent`; approval before destructive or submitting
  actions.
- Safety/auth/logging/redaction: Mask screenshots containing secrets, log high
  level actions instead of raw sensitive UI content, require confirmation before
  submit/delete.
- Runtime-package shape: Repeated observe-plan-act loops using `tool_use_step`
  for UI actions and `decision_step` for screen-state checks.

### 5. Coding agent

- Scenario: A repository assistant implements a small feature, updates tests, and
  reports validation evidence.
- Why this pattern fits: The agent must inspect code, plan edits, modify files,
  run tests, and iterate on failures.
- Simpler alternative: A human-authored patch or fixed codemod may be better for
  simple mechanical edits.
- Typical tools or memory: File read/search/edit, test runner, lint, git diff,
  and task progress state.
- Autonomy level: `supervised agent`; commits or broad rewrites require explicit
  user direction.
- Safety/auth/logging/redaction: Keep unrelated changes out of scope, record
  exact validation commands, avoid secrets in generated tests or logs.
- Runtime-package shape: `llm_step` planning and review nodes, `tool_use_step`
  file/test nodes, `decision_step` for validation failure routing.

### 6. Speech or voice agent

- Scenario: A meeting assistant listens to spoken status updates and creates a
  structured action-item summary.
- Why this pattern fits: The agent handles voice input/output and must account
  for transcription uncertainty.
- Simpler alternative: Batch transcription plus summarization may be enough when
  no interactive voice loop is needed.
- Typical tools or memory: Speech-to-text, text-to-speech, speaker labels,
  transcript chunks, and summary state.
- Autonomy level: `assistive`.
- Safety/auth/logging/redaction: Obtain recording consent, redact personal or
  confidential statements, mark uncertain transcripts.
- Runtime-package shape: `tool_use_step` for transcription, `llm_step` for
  summarization, `decision_step` for confidence or consent checks.

### 7. Workflow orchestration agent

- Scenario: An incident assistant coordinates diagnostic checks, owner routing,
  and status updates during a service degradation.
- Why this pattern fits: The agent coordinates multiple bounded steps and systems
  while adapting order based on findings.
- Simpler alternative: A static runbook or workflow engine is better when the
  branch logic is stable and deterministic.
- Typical tools or memory: Monitoring queries, ticket/status tools, owner map,
  run state, and escalation policy.
- Autonomy level: `bounded autonomous` for read-only diagnosis; approval before
  customer-visible updates or remediation.
- Safety/auth/logging/redaction: Log decisions, tool outputs, and escalation
  triggers; redact customer data and sensitive infrastructure details.
- Runtime-package shape: Phased graph with `tool_use_step` diagnostics,
  `decision_step` routing, and event/state transitions.

### 8. Evidence-loop agent

This is best treated as a workflow overlay for an evidence-heavy agent, often on
top of a tool-based, workflow-orchestration, or research-oriented base pattern.

- Scenario: A research assistant starts with a cheap answer, asks an evaluator if
  the evidence is sufficient, then performs deeper targeted retrieval only when
  gaps remain.
- Why this pattern fits: The task is evidence-heavy, cost-sensitive, and benefits
  from an explicit stop/continue gate instead of a vague iterative loop.
- Simpler alternative: A single RAG pass or fixed search pipeline may be enough
  when the question is narrow and the retrieval path is already known.
- Typical tools or memory: Fast answer tool, search, scrape or source-reader
  tools, short-term evidence bundle, evaluator output, and final report state.
- Distinguishing contract: The evaluator should return structured fields such as
  `is_good_enough`, `score`, `reason`, and `missing_information`, with
  `missing_information` driving the next retrieval queries.
- Delegation shape: Often uses callable specialists, such as a judge/evaluator
  specialist and a final synthesis or report-writing specialist.
- Autonomy level: `supervised agent` or `bounded autonomous`, depending on
  whether the agent is allowed to expand retrieval automatically within a defined
  budget.
- Safety/auth/logging/redaction: Define when grounded retrieval is mandatory,
  cap source expansion and retries, preserve provenance, and log evaluator
  decisions plus retrieval-depth spending.
- Observability: Prefer layered traces covering workflow state, evaluator gates,
  specialist calls, and external evidence tools.
- Runtime-package shape: `tool_use_step` evidence collection, `decision_step`
  sufficiency gates, optional callable-specialist `llm_step` nodes, and one final
  synthesis result.

### 9. Knowledge-grounded RAG agent

This is also often a workflow overlay rather than a distinct base agent pattern:
the base pattern may still be basic reasoning, tool-based function calling, or
workflow orchestration, with grounded retrieval added as the dominant context
construction rule.

- Scenario: A technical support assistant answers product questions using a
  versioned documentation corpus, support knowledge base, and known-issue index.
- Why this pattern fits: The agent's value depends on grounding responses in
  retrieved evidence and citing authoritative sources instead of answering from
  model memory alone.
- Simpler alternative: A search page, static FAQ, or single prompt with supplied
  context may be better when the corpus is small or the user can inspect sources
  directly.
- Typical tools or memory: Keyword search, embedding-backed vector retrieval,
  structured metadata filters, reranker, source reader, citation formatter, and
  retrieval-quality state.
- RAG variants: Keyword or structured lookup for exact policy and identifier
  queries; embedding-backed semantic RAG for concept and troubleshooting queries;
  GraphRAG or knowledge-graph retrieval for relationship-heavy questions; hybrid
  retrieval when exact matches and semantic context both matter.
- Autonomy level: `assistive`; escalate or ask for clarification when retrieval
  is weak, stale, contradictory, or uncited.
- Safety/auth/logging/redaction: Preserve corpus provenance, record index
  freshness, redact private documents from traces, and disclose when retrieval
  evidence is incomplete or conflicting.
- Runtime-package shape: Retrieval `tool_use_step` nodes, retrieval-sufficiency
  and source-authority `decision_step` nodes, and grounded `llm_step` synthesis
  that requires citations and caveats.

### 10. Memory-augmented agent

- Scenario: A project assistant remembers recurring architecture decisions and
  uses them to advise future implementation plans.
- Why this pattern fits: Durable memory materially improves future task quality
  and must be reconciled with current source truth.
- Simpler alternative: A local README or memory-bank may be enough if no dynamic
  retrieval or write-back is needed.
- Typical tools or memory: Repo memory bank, Obsidian notes, decision logs,
  retrieval indexes, and provenance metadata.
- Autonomy level: `assistive`; memory writes should be proposed or confirmed.
- Safety/auth/logging/redaction: Preserve provenance, avoid secrets or high-risk
  personal data, disclose stale or conflicting memory.
- Runtime-package shape: Retrieval `tool_use_step`, memory-confidence
  `decision_step`, and `llm_step` synthesis with cited memory sources.

### 11. Simulation or test-bed agent

- Scenario: A safety evaluator simulates adversarial users against a planned
  tool-calling agent before implementation.
- Why this pattern fits: The agent generates scenarios, runs controlled trials,
  and evaluates behavior under edge cases.
- Simpler alternative: Fixed unit tests are better for known deterministic
  contracts.
- Typical tools or memory: Scenario generator, test harness, scoring rubric,
  result store, and regression snapshots.
- Autonomy level: `assistive` or `bounded autonomous` inside a sandbox.
- Safety/auth/logging/redaction: Use synthetic data, isolate tools, log prompts
  and outputs for review, prevent live external mutations.
- Runtime-package shape: `llm_step` scenario generation, `tool_use_step` harness
  execution, `decision_step` pass/fail scoring and retry limits.

### 12. Observer or monitoring agent

- Scenario: A quality monitor watches pipeline results and flags anomalous test
  failures for human triage.
- Why this pattern fits: The agent observes events continuously or periodically
  and decides whether to alert.
- Simpler alternative: Threshold alerts are better when simple metrics capture
  the risk.
- Typical tools or memory: Event stream, metrics, log summaries, baseline state,
  and alert history.
- Autonomy level: `assistive`; alerting may be automatic, remediation requires
  approval.
- Safety/auth/logging/redaction: Redact logs, avoid leaking incident details,
  log alert rationale and suppress duplicate alerts.
- Runtime-package shape: Event `tool_use_step`, anomaly `decision_step`, and
  `llm_step` explanation or triage recommendation.

### 13. Multi-agent collaboration

- Scenario: A design review panel has separate architect, security, and
  operations roles critique a proposed agent runtime package.
- Why this pattern fits: Independent roles expose tradeoffs and dissent that a
  single prompt may miss.
- Simpler alternative: One reviewer prompt may be enough for low-risk decisions.
- Typical tools or memory: Persona instructions, shared evidence bundle,
  per-role outputs, synthesis state, and optional Judge or approval gate.
- Autonomy level: `assistive`.
- Safety/auth/logging/redaction: Keep evidence bundles minimal, disclose
  independence limits, log dissent and unresolved questions, redact sensitive
  source context before sharing across roles or backends.
- Runtime-package shape: Participant groups, parallel or batched `llm_step`
  role nodes, `parallel_join` or synthesis node, and `decision_step` for final
  recommendation or gate.
