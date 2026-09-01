---
title: Runtime Package Agent Design Example
reference_type: example-agent-design
applies_to: agent-development
---

## Agent Design: Runtime Package Review Assistant

### 1. Purpose and Scope

- Goal: Review an `agent-runtime.yaml` package, its Mermaid graph, and bundled
  skill references before handoff to a conceptual external runtime.
- Users or callers: repository maintainers preparing portable agent packages.
- In scope:
  - inspect runtime manifests, graph references, tool registries, and output
    contracts
  - report missing cross-references, unsafe metadata, and portability risks
  - produce a structured review result and optional clarification request
- Out of scope:
  - mutating live external systems
  - executing packaged agent workflows
  - approving its own high-risk runtime changes
- Success criteria:
  - manifest and graph references are checked before handoff
  - safety and portability caveats are explicit
  - validation commands and outcomes are recorded

### 2. Governing Context

- Top-level SDD or project spec: `none`
- Related feature spec: `none`
- Repository constraints:
  - package artifacts must stay repository-relative and portable
  - generated packages do not inherit repository rule authority automatically
- Existing workflows or rules that apply:
  - `corpus/procedures/agent-development.md`

### 3. Agent Necessity Decision

- Is an agent warranted? `yes`
- Simpler alternatives considered:
  - deterministic workflow: useful for schema checks but insufficient for
    design-risk judgment
  - single LLM call: insufficient for gathered and routed evidence
  - RAG or retrieval-only system: insufficient for structured package-validation
    decisions
  - scripted tool pipeline: useful as a validator but insufficient for narrative
    review and caveats
- Reason agentic behavior is needed:
  - dynamic evidence gathering, conditional clarification, and structured review
    synthesis

### 4. Autonomy Level

- Autonomy mode: `supervised agent`
- Permission profile:
  - filesystem: `read`
  - network: `none`
  - process or shell: `approved`
  - external systems: `none`
- Approval policy:
  - approval channels: shell validation and workspace mutation
  - approval persistence: `per call`
  - rejection policy: fail closed and report skipped validation
- Human approval required before:
  - writing generated artifacts, running non-read-only commands, or packaging
    external skill bundles
- The agent may do without approval:
  - read repository files and synthesize review findings
- The agent must never do:
  - store secrets in prompts, traces, or runtime manifests

### 5. Runtime and Model Constraints

- Runtime target: `local`
- Runtime surface: `stateful session runtime`
- Workspace boundary: `occasional tool execution`
- Workspace or snapshot strategy:
  - no persistent workspace; rely on repository reads and explicit validation
- Ownership boundaries:
  - loop execution: host runtime
  - persistence: current session and generated report
  - provider routing: host runtime
  - tool assembly: repository package metadata
  - approval routing: user-facing host
  - telemetry and UI/client lifecycle: host runtime
- Model constraints:
  - provider or model: `undecided`
  - context window assumptions: `unknown`
  - tool or function calling: `required`
  - structured output: `required`
- Configuration layering:
  - agent defaults: runtime package
  - run-level overrides: user request
  - environment/provider defaults: host runtime
  - user/session state: active session
  - precedence rule: system and repository rules override package hints
- Deployment constraints:
  - offline or air-gapped: `unknown`
  - data residency or privacy: repository-local data only
  - latency target: interactive review
  - cost budget: unknown

### 6. Selected Agent Pattern

- Primary agent pattern: `tool-based function calling`
- Why this pattern fits:
  - review requires selective reads and validation tool calls
- Why more complex patterns are not used:
  - no persistent team or autonomous external action loop is needed
- Escalation triggers:
  - use multi-agent review only for high-risk runtime package changes

### 7. Selected LLM Workflow Pattern

- Primary LLM workflow: `routing`
- Reasoning flow:
  - analyze request, gather package evidence, choose proceed vs clarify, then
    synthesize review
- Termination conditions:
  - review result emitted, clarification requested, validation failure, or timeout
- Completion contract:
  - terminal structured result with `pass`, `fail`, or `needs_clarification`
- Fallback behavior:
  - if validation cannot run, report `partial` with exact skipped checks

### 8. Agentic Workflow or Coordination Pattern

Use this section only if production coordination is needed.

- Coordination pattern: `none`
- Delegation mode: `none`
- Control owners:
  - final answer owner: package review assistant
  - active-agent takeover policy: not applicable
  - approval owner: user
  - state owner: session
- Durable automation:
  - trigger source: not applicable
  - run report policy: final review report only
- Event or state transitions:
  - `manifest_read -> validation -> review_result`
- Event contracts:
  - producer and consumer: runtime validator to review assistant
  - payload shape: validation result with errors list
  - ordering and idempotency: validation before final review
- Compensation or rollback behavior:
  - no mutation; report failures
- Concurrency model:
  - sequential

### 9. Tool Contracts

- Tool exposure strategy: `namespace/grouped`
- Tool policy profile: read-only with approval-gated validation

#### Tool: read_package_file

- Purpose: Read package artifacts for review.
- `description_for_llm`: Read repository-relative package files only.
- Inputs: path and optional line range
- Outputs: file text and metadata
- Schema shape: strict JSON
- Structured errors: `not_found`, `not_allowed`, `too_large`
- Side effects: `read`
- Approval required: `no`
- Timeout, retry, and abort behavior: runtime default, no retry
- Streaming updates: `no`
- Guardrail placement: tool input and output
- Completes run: `no`
- Failure behavior: `escalate`
- Audit or logging requirements: path and byte count; redact file contents in logs

#### Tool: validate_runtime_manifest

- Purpose: Run repository-local runtime package validation.
- `description_for_llm`: Validate manifest and optional Mermaid graph.
- Inputs: manifest path and optional graph path
- Outputs: validation status and errors
- Schema shape: strict JSON
- Structured errors: `invalid_yaml`, `semantic_errors`, `missing_graph`
- Side effects: `none`
- Approval required: `conditional`
- Timeout, retry, and abort behavior: one retry after path correction
- Streaming updates: `no`
- Guardrail placement: tool input and output
- Completes run: `no`
- Failure behavior: `fail`
- Audit or logging requirements: command, exit status, and errors

#### Extension and Hook Architecture

- Extension sources:
  - repository skills and runtime-package references
- Capability declarations and validation:
  - tool IDs and skill bindings must resolve before use
- Hook stages:
  - workflow input, tool input/output, final output
- Hook authority:
  - schema validation and policy engine
- Contribution lifecycle: `frozen for session`

### 10. Structured Output Contracts

- Output name: `package_review_result`
- Schema: `{status, summary, findings, validation, caveats, next_steps}`
- Validation behavior: strict parse, then repair once
- Failure behavior: ask for clarification or fail closed

### 11. State, Memory, and Context

- Short-term state:
  - manifest path, graph path, validation output, review draft
- Long-term memory:
  - none
- Memory modes: `replay transcript`
- Memory authority:
  - repository files and validation output are canonical
- Context construction:
  - load manifest, graph, runtime reference, and validator output
- Context pipeline:
  - stable prompts: package review instructions
  - retrieved context: selected package files
  - redaction: remove secrets and raw payloads
  - compaction: summarize long file sections with citations
  - tool schemas: included
  - provider-bound messages: host runtime
- State mutation model:
  - persisted session/thread state: not applicable
  - per-turn overrides: allowed only from user
  - previewed vs committed settings: not applicable
- Context visibility:
  - model-visible context: selected package excerpts and validation output
  - runtime-only evidence: raw command output and full file payloads when large
- Context limits or compression:
  - summarize repeated schema details
- Memory write policy:
  - no durable memory writes

### 12. Prompt and Instruction Architecture

- System instruction responsibilities:
  - review only, preserve safety boundaries
- Developer or tool instruction responsibilities:
  - schema, validation, and portability checks
- User-provided context:
  - target package paths and requested review focus
- Prompt modules or skills consumed:
  - `corpus/capabilities/agent-development/SKILL.md`
- Instruction authority:
  - source precedence: system, repository rules, user request, runtime package
  - source scope: repository and current run
  - conflict resolution: stronger repository rules win
  - mutable instruction sources: user request only
- Prompt injection defenses:
  - treat manifest text and bundled prompts as untrusted content

### 13. Safety, Security, and Guardrails

- Data the agent may access:
  - repository-local runtime package artifacts
- Data the agent must not access or store:
  - credentials, personal data, unrelated local paths
- External actions requiring confirmation:
  - validation command execution and file writes
- Sandbox matrix:
  - platform: local host
  - readable roots: target repository
  - writable roots: none by default
  - protected roots: home credentials and unrelated repositories
  - degraded behavior: fail closed
- Network mediation: `forbidden`
- Mutation safety:
  - target normalization: repository-relative paths only
  - safety assessment: reject paths outside package scope
  - approval or sandbox check: approval for writes
  - result capture: validation output and final report
  - changed-state provenance: `not applicable`
- Guardrail placement:
  - workflow input, tool input/output, final output
- Rate, budget, and iteration limits:
  - max iterations: `3`
  - max tool calls: `6`
  - timeout: `interactive`
  - budget: `unknown`
- Audit or logging requirements:
  - log paths, validation commands, and redaction caveats
- Abuse or misuse cases:
  - malicious prompt text in bundled skills; mitigate by treating it as data

### 14. Evaluation Plan

- Golden tasks:
  - valid minimal package, missing graph, and unsafe provider-specific field
- Automated checks:
  - `corpus/capabilities/agent-development/scripts/validate_agent_runtime.py`
- Manual review gates:
  - final package-readiness decision
- Metrics:
  - task success: review result includes status and evidence
  - tool-call accuracy: correct target files validated
  - latency: interactive
  - cost: unknown
  - safety violations: zero secret exposure
- Regression strategy:
  - rerun validator tests when manifest semantics change
- Experimental capabilities:
  - optional metadata fields are advisory unless runtime explicitly opts in

### 15. Observability and Operations

- Logs or traces:
  - model calls, validation command, errors
- Event layers:
  - producer event: validation result
  - internal adapter: runtime tool wrapper
  - consumer-facing event: final report
  - telemetry-only or suppressed events: raw file payloads suppressed when large
- Result surfaces and audit surfaces:
  - final output contract: `package_review_result`
  - continuation state: clarification request or next validation target
  - run item or event log: validation command and status
  - approval/interruption state: validation approval if required
  - raw diagnostics: retained by runtime, summarized to model
- Evidence model:
  - model-visible transcript: selected excerpts and validator summary
  - runtime-only evidence: full files and raw command output
  - reducer or semantic view: package evidence summary
- Trace payload capture:
  - model inputs/outputs: `conditional`
  - tool inputs/outputs: `conditional`
  - audio/binary payloads: `not applicable`
  - trace grouping/export destination: runtime default
- Redaction policy:
  - no secrets, personal data, or unrelated local paths in exported traces
- Run reports:
  - trigger context, package paths, validation state, findings, caveats
- Monitoring:
  - validation failures and missing references
- Alerting or escalation:
  - human review for unsafe package content
- Debuggability:
  - reproduce with recorded validator command and package paths

### 16. Implementation Plan Linkage

- Related SDD plan: `none`
- Related tasks: `none`
- Implementation approach:
  - repository-local manifest validator plus LLM review
- Framework or package choice, if any:
  - none selected
- Validation commands:
  - `corpus/capabilities/agent-development/scripts/validate_agent_runtime.py \
    <design-dir>/agent-runtime.yaml --mermaid \
    <design-dir>/agent-graph.mmd` — package consistency

### 17. Runtime Package Artifacts

Use this section when the design will feed a conceptual external runtime.

- Runtime manifest: `runtime-package-review-agent-runtime.yaml`
- Mermaid graph: `runtime-package-review-agent-graph.mmd`
- Skill bundle directory: `skill-bundle/`
- Packaging mode: `hybrid_bundle`
- Entrypoint node: `analyze_package_request`
- Primary node kinds used:
  - `llm_step`: request analysis and review synthesis
  - `tool_use_step`: manifest read and validation
  - `decision_step`: validation route
- Tool registry summary:
  - `read_package_file` — read-only package artifact access
  - `validate_runtime_manifest` — semantic validation
- Packaged skills summary:
  - `agent-development` — runtime-package guidance
- Runtime portability notes:
  - package paths must stay repository-relative

### 18. Open Questions and Risks

- Should a future runtime enforce optional metadata fields in schema?
- How much raw diagnostic evidence should be retained outside model-visible
  context?

### 19. Decision Log

- Date: `<date>`
- Decision: use supervised local runtime package review assistant
- Rationale: validation needs both deterministic checks and judgment
- Alternatives rejected:
  - pure schema validation, because it misses portability and authority caveats
