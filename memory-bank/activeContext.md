# Active Context

## Current Focus

- No implementation slice is currently active.
- A new draft spec package, `specs/litellm-provider-adapter/`, now proposes
  making LiteLLM the package's core OpenAI-compatible transport while
  preserving repository-owned OpenAI/Codex auth discovery and mapping default
  Codex behavior through a helper shaped like
  `create_litellm_codex_adapter_from_codex_auth(...)`.
- `docs/source/conf.py` was refreshed and committed separately to derive Sphinx
  project metadata from `pyproject.toml`/git config and to simplify the
  Confluence SSO session override path.
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
  develop/main branch synchronization, and post-hoc SDD representation in
  `specs/pyinstaller-packaging-support/` are done.
- The package-owned `openai_model_registry` PyInstaller hook now also collects
  `tiktoken_ext` hidden imports so frozen apps include tokenizer encoding
  namespace-package plugins.
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
- `rag-orchestration-contract` v1 is implemented. It provides expanded
  declarative `metadata.rag_pipeline` validation and capability/status
  reporting for retriever collaborators, provenance requirements, source
  readiness, permissions, cache, degraded states, and context-management
  handoff declarations while keeping retrieval infrastructure and prompt
  packing out of RAG ownership.
- RAG + context-management integration is split by ownership:
  `rag-orchestration-contract` declares and preflights retrieved evidence
  requirements; `context-management-prepare-stage` owns retrieved-context
  lanes, packing, trimming, compression, diagnostics, and final prompt
  injection.
- `skill-source-resolution` v1 is implemented. Source loading is opt-in and
  package-local only: referenced bundled `SKILL.md` bodies under
  `skill-bundle/` inject through `skill_instructions` after effective
  `skill_refs` are derived, with bounded UTF-8 loading, redacted provenance,
  fail-closed validation, and capability/status reporting for metadata-only,
  live, and rejected states.
- `persistent-agent-sessions` is now specified as a proposed v1 feature:
  public `AgentSession`-style API, `InMemorySessionStore`, current session-state
  retrieval, and restart from saved state while preserving bounded per-prompt
  workflow runs instead of a long-running graph executor.
- `model-event-streaming` is now specified as a proposed
  post-persistent-session feature: caller-facing `llm_step` and model-tool-loop
  event streaming, final-result authority, and `AgentSession.accept_stream(...)`
  as the intended primary surface after persistent sessions exist.
- The next ROI action is no longer skill-source, RAG orchestration v1, or
  context-management prepare-stage v1. LiteLLM provider implementation now has
  a draft spec, and persistent agent sessions plus post-session model event
  streaming now have proposed specs, but code work for any of these should wait
  for an approved implementation plan.
  Local-model advisory implementation should happen only when local-model
  ergonomics is the immediate driver.

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
- PyInstaller packaging support for `openai-model-registry` now includes
  registry data files, distribution metadata, and `tiktoken_ext` hidden imports
  for tokenizer encoding plugins.
- `pyinstaller-packaging-support` now has a dedicated post-hoc feature spec,
  implementation plan, task list, validation log, and spec-index coverage.
- Agent-architecture follow-ups from `AI Agents in Action, Second Edition` are
  tracked across the relevant spec packages without changing implementation
  scope.
- RAG orchestration follow-ups from Apple Books RAG references are tracked in
  `specs/rag-orchestration-contract/spec.md` with citations by title, author,
  publisher, and ISBN rather than local file paths.
- RAG orchestration v1 implementation is complete with validation and
  capability/status coverage, and the full spec surface now consistently
  records the RAG/context-management ownership split.
- Skill-source resolution v1 is implemented and documented; open decisions are
  deferred beyond v1.
- Core LiteLLM adapter planning is captured in
  `specs/litellm-provider-adapter/spec.md`; it is draft-only and not yet
  implementation authorization.
- Persistent agent session planning is captured in
  `specs/persistent-agent-sessions/spec.md`; it is proposed v1 only and not yet
  implementation authorization.
- Model event streaming planning is captured in
  `specs/model-event-streaming/spec.md`; it is proposed only after persistent
  sessions and is not yet implementation authorization.
- Sphinx configuration refresh is committed separately from the LiteLLM spec.

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
  - `specs/rag-orchestration-contract/spec.md`
  - `specs/context-management-prepare-stage/spec.md`
  - `specs/pyinstaller-packaging-support/spec.md`
- Draft feature packages:
  - `specs/litellm-provider-adapter/spec.md`
- Proposed feature packages:
  - `specs/persistent-agent-sessions/spec.md`
  - `specs/model-event-streaming/spec.md`
- Prepared feature packages:
  - `specs/llama-cpp-memory-fit-profile/spec.md`
- Later feature packages:
  - `specs/power-marimo-host-automation/spec.md`
  - `specs/async-session-memory-pipeline/spec.md`
  - `specs/llm-step-interpreter-middleware/spec.md`
  - optional local-model advisory specs:
    `specs/llmfit-model-fit-filter/spec.md`

## Next Steps

- If implementing LiteLLM support, first approve or refine
  `specs/litellm-provider-adapter/spec.md`, then create plan/tasks artifacts
  that decide request mapping, Codex auth adaptation, model-id aliasing,
  Responses API support, PyInstaller handling, and official OpenAI SDK
  compatibility/fallback behavior before editing runtime code.
- If implementing persistent agent sessions, first create an approved plan/tasks
  slice from `specs/persistent-agent-sessions/spec.md` that decides API return
  shape, sync-wrapper scope, workflow compatibility checks, `history: summary`
  behavior, and where `session_id_state_key` writes.
- If implementing model event streaming, do it only after persistent sessions
  have an approved plan and baseline. Create plan/tasks that decide event
  iterator vs sink shape, adapter streaming protocol, redaction/tool payload
  policy, cancellation/backpressure behavior, and terminal event/result shape.
- If continuing local-model advisory work, decide whether the pending
  `pyproject.toml` / `poetry.lock` optional llama.cpp metadata edits should be
  committed, revised, or discarded before executing another slice.
- If extending skill-source support, start a new beyond-v1 plan before adding
  external roots, `source_path` reads, support-file prompt loading, network
  fetching, Markdown frontmatter parsing, or raw-body debugging modes.
- If extending context growth management beyond the implemented prepare-stage
  slices, create a new approved plan before adding provider-backed remote
  compaction, semantic selectors, model-backed summaries, richer profile
  behavior, or prompt-cache-aware ordering.
- Preserve unit-test boundaries: fake clients, fake tools, fake MCP bindings,
  fake guardrails, and fake local-model profilers only; no live OpenAI, MCP,
  Hugging Face, Marimo, llama.cpp, or local model calls in core tests.
