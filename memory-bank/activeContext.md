# Active Context

## Current Focus

- No implementation slice is currently active.
- The high-ROI queue has advanced through four major runtime foundations:
  capability/status visibility, approval/sandbox approval-before-side-effect
  policy, explicit MCP registry injection, and caller-registered input
  guardrails.
- Bounded `iterative-agent-loop-runtime` v1 is now implemented and documented.
- `llama-cpp-memory-fit-profile` is prepared for v1 implementation as an
  optional, read-only, injected-evaluator advisory feature.
- Recent local-model maintenance tightened optional-runtime behavior:
  direct llama.cpp docs now point callers to the `llamacpp` extra, missing
  default `llama_cpp` imports are covered by regression tests, and MLX adapter
  tests verify non-macOS use fails before model resolution or `mlx_lm` loading.
- PyInstaller packaging support for `openai-model-registry` is complete:
  package-owned hook files, metadata advertisement, build-gated DevOps SCM PR,
  and develop/main branch synchronization are done.
- Context growth management has a dedicated spec package:
  `specs/context-management-prepare-stage/` now owns session pruning, context
  compaction, hierarchical prompt-context injection, and provider-neutral
  hierarchical compression planning.
- The current preferred compression scheme is turn-aware lane assembly:
  pinned hierarchy, current turn, recent turns, rolling structured summary,
  deterministic older-turn selection with chronological reassembly, and
  deterministic fallback trimming before optional provider compaction.
- The context-management spec now adopts LCWMS-derived lifecycle, segment
  metadata, and quality/efficiency metric vocabulary while keeping
  runner-owned durable memory and built-in vector/embedding retrieval out of
  scope.
- Survey-note analysis added required-vs-optional lane semantics,
  reserve-token output headroom, lost-in-the-middle-aware ordering, model
  routing boundaries, exact retrieval boundaries, and overflowing-history
  evaluation guidance to the context-management spec.
- The spec inventory and completion matrix now include
  `context-management-prepare-stage`; graph mutation is recorded as the
  standalone derived workflow-operation layer, with context management as one
  usage that may be attached to nodes or inserted on links such as ReAct
  loopbacks.
- Context compression profiles are specified as policy presets:
  `balanced`, `fast`, `exact`, `semantic`, `recency_weighted`, and
  `instruction_weighted`.
- Cross-cutting follow-up ideas from Micheal Lanham's `AI Agents in Action,
  Second Edition: Intelligent Workflows With LLMs, MCP, A2A, and More`
  (Manning, ISBN `9781633434530`) are recorded as future-work notes in the
  owning specs: MCP resources/prompts, evaluation guardrails, loop controls,
  memory-selection hints, capability/deployment reporting, and sandbox safety.
- `rag-orchestration-contract` is now a proposed future-feature spec for
  RAG as an orchestration contract rather than runner-owned retrieval
  infrastructure. It includes production-oriented metadata for index lifecycle,
  permission-aware retrieval, retrieval routers/profiles, cache contracts,
  GraphRAG construction vs query-time retrieval, degraded execution, and
  evaluation lifecycle hooks.
- `skill-source-resolution` v1 is implemented. Source loading is opt-in and
  package-local only: referenced bundled `SKILL.md` bodies under
  `skill-bundle/` inject through `skill_instructions` after effective
  `skill_refs` are derived, with bounded UTF-8 loading, redacted provenance,
  fail-closed validation, and capability/status reporting for metadata-only,
  live, and rejected states.
- The next ROI action is no longer skill-source v1. Local-model advisory
  implementation should happen only when local-model ergonomics is the
  immediate driver; context-management implementation remains available from
  `specs/context-management-prepare-stage/tasks.md` when prompt growth becomes
  the immediate driver.

## Recent Completed Work

- Capability status reporting is implemented:
  - public report contract and package inspection
  - metadata-only declarations
  - model adapter, tool registry, built-in tool-pack, approval, MCP, and
    guardrail collaborator/status reporting
  - invalid package reporting
- Approval/sandbox v1 baseline is implemented:
  - `ApprovalInterruptionState`, `ApprovalInterruption`, and
    `WorkflowInterruptedResult`
  - direct approval-required `tool_use_step` pause before handler invocation
  - no side effect before approval
  - redacted approval trace events
  - high-level `run_agent_workflow*` APIs fail clearly on interrupted workflows
  - sandbox work remains partial: approval-before-side-effect exists, but write,
    shell, workspace grants, sandbox adapters, and mutation audits remain
    deferred
- MCP v1 baseline is implemented:
  - `MCPToolBinding`
  - `registered_tool_from_mcp_binding(...)`
  - `create_mcp_registry(...)`
  - MCP-origin tool provenance
  - conservative hidden and approval-required defaults
  - live MCP registry-entry capability status
  - live MCP transports, process lifecycle, discovery, reconnect, cache, and
    diagnostics beyond metadata remain deferred
- Live guardrail v1 baseline is implemented:
  - `GuardrailDecision`, `GuardrailResult`, and `InMemoryGuardrailRegistry`
  - input guardrails run before first model/tool action
  - missing input adapters fail closed
  - abort decisions raise `GuardrailExecutionError`
  - redacted guardrail traces
  - capability status for missing/live input guardrail adapter coverage
  - output/tool phases, reject-content, warning-only behavior, retries,
    timeouts, and external adapters remain deferred
- Iterative agent-loop runtime v1 is implemented:
  - opt-in activation through
    `runtime.execution_policy.tool_use_completion.run_again: required`
  - serial model-emitted tool dispatch through `ToolRegistry`
  - model-facing tool-result transcript feedback into the next model turn
  - fail-closed handling for unavailable/hidden tools, malformed arguments,
    failed tools, and max loop exhaustion
  - approval-required model tool calls pause before invocation
  - loop lifecycle and final-output trace events
  - loop `state_field`/`tool_result` final selectors, durable approval resume,
    output/tool guardrails, parallel tool calls, and durable transcripts remain
    deferred
- llama.cpp memory-fit profile is prepared for v1 implementation:
  - planned as a post-resolution GGUF advisory API
  - v1 uses only caller-injected evaluators/profilers
  - fail-open is the default, strict mode is scoped to the profiling call, no
    cache or automatic memory-budget discovery is planned for v1
  - suggested kwargs are limited to `n_ctx`
- Local-model optional-runtime hardening is in place at the test/docs layer:
  - direct llama.cpp helpers remain lazy and report a package-owned
    `ModelExecutionError` when the default `llama_cpp` dependency is absent
  - MLX helpers remain constructible on non-macOS, advertise their model aliases,
    and fail with the macOS-only `ModelExecutionError` before resolving model
    paths or loading dependencies when generation is attempted off macOS
- PyInstaller packaging support for `openai-model-registry` is complete.
- Agent-architecture follow-ups from `AI Agents in Action, Second Edition` are
  tracked across the relevant spec packages without changing implementation
  scope.
- RAG orchestration follow-ups from Apple Books RAG references are tracked in
  `specs/rag-orchestration-contract/spec.md` with citations by title, author,
  publisher, and ISBN rather than local file paths.
- Skill-source resolution v1 is implemented and documented; open decisions are
  deferred beyond v1.

## Current Spec Authority Map

- Primary runtime contract:
  - `specs/dynamic-agent-runner/spec.md`
- Recently completed feature packages:
  - `specs/capability-status-report/spec.md`
  - `specs/approval-interruption-resume/spec.md`
  - `specs/sandbox-workspace-runtime/spec.md`
  - `specs/mcp-runtime-integration/spec.md`
  - `specs/live-guardrail-execution/spec.md`
  - `specs/iterative-agent-loop-runtime/spec.md`
  - `specs/skill-source-resolution/spec.md`
- Prepared feature packages:
  - `specs/llama-cpp-memory-fit-profile/spec.md`
  - `specs/context-management-prepare-stage/spec.md`
  - `specs/rag-orchestration-contract/spec.md`
- Later feature packages:
  - `specs/power-marimo-host-automation/spec.md`
  - `specs/async-session-memory-pipeline/spec.md`
  - `specs/llm-step-interpreter-middleware/spec.md`
  - optional local-model advisory specs:
    `specs/llmfit-model-fit-filter/spec.md`

## Next Steps

- If continuing local-model advisory work, decide whether the pending
  `pyproject.toml` / `poetry.lock` optional llama.cpp metadata edits should be
  committed, revised, or discarded before executing another slice.
- If extending skill-source support, start a new beyond-v1 plan before adding
  external roots, `source_path` reads, support-file prompt loading, network
  fetching, Markdown frontmatter parsing, or raw-body debugging modes.
- If implementing context growth management, use
  `specs/context-management-prepare-stage/plan.md` and `tasks.md`; start with
  policy/turn-unit metadata, lifecycle diagnostics, scoring/metric fields, and
  lane-based prompt assembly. Preserve required lanes, reserve output headroom,
  compression profiles, and add overflowing-history checks before provider or
  mid-turn compaction.
- Preserve unit-test boundaries: fake clients, fake tools, fake MCP bindings,
  fake guardrails, and fake local-model profilers only; no live OpenAI, MCP,
  Hugging Face, Marimo, llama.cpp, or local model calls in core tests.
