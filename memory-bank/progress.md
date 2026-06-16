# Progress

## Working

- Core runtime supports package-directory workflow loading and execution,
  async-first APIs, sync wrappers, tool registry/overrides, OpenAI-compatible
  adapters/providers, retry, output contracts, token budgeting, tracing, hooks,
  prompt preparation, validation, runtime behavior overrides, model adapter
  coverage, local model helpers, and metadata-only future surfaces.
- Default OpenAI/Codex auth discovery and ChatGPT/Codex backend compatibility
  are implemented.
- llama.cpp and MLX local-model adapters are implemented through their current
  scoped baselines, with regression coverage for optional direct llama.cpp
  dependency absence and MLX unsupported-platform short-circuit behavior.
- Capability status reporting is implemented for:
  - finite execution
  - metadata-only declarations
  - model adapter coverage
  - tool registry coverage
  - built-in tool-pack status
  - approval interruption coverage
  - MCP-origin registry entries
  - input guardrail adapter coverage
  - invalid packages
- Approval/sandbox v1 baseline is implemented:
  - direct approval-required `tool_use_step` interruption
  - public interruption result contract
  - no side effect before approval
  - redacted approval traces
  - high-level API guardrails for interrupted workflows
  - capability status for the live approval boundary
- MCP v1 baseline is implemented:
  - explicit caller-supplied MCP registry injection
  - MCP-origin provenance
  - hidden and approval-required conservative defaults
  - trusted metadata overrides
  - capability status for live MCP-origin registry entries
- Live guardrail v1 baseline is implemented:
  - caller-registered input guardrails
  - pass/abort decisions
  - fail-closed missing adapter behavior
  - abort before first model/tool action
  - redacted guardrail traces
  - capability status for input guardrail coverage
- Iterative agent-loop runtime v1 is implemented:
  - opt-in bounded loops for eligible `llm_step` nodes
  - serial model-emitted tool calls dispatched through `ToolRegistry`
  - model-facing tool output fed into follow-up model turns
  - approval pause before approval-required model tool invocation
  - fail-closed behavior for unavailable/hidden tools, malformed arguments,
    tool failures, and loop exhaustion
  - loop lifecycle/final-output trace events
- Registry-provided model tools use OpenAI Responses API function-tool shape
  with top-level `name`.
- Package-owned PyInstaller support now includes a hook provider and bundled
  `openai_model_registry` hook that collects registry data files and
  distribution metadata for frozen downstream clients.
- The package advertises its PyInstaller hook directory through the
  `pyinstaller40` entry point, and the hook support was merged through the
  build-gated DevOps SCM PR flow.
- `context-management-prepare-stage` now owns the prompt-preparation feature
  spec for session pruning, context compaction, hierarchical prompt-context
  injection, and provider-neutral hierarchical context compression.
- The preferred future compression architecture is turn-aware lane assembly:
  pinned hierarchy, current turn, recent turns, rolling structured summary,
  selected older turns, bounded file/tool context, chronological reassembly,
  and deterministic fallback trimming.
- The context-management spec now includes lifecycle-stage diagnostics,
  segment/turn scoring metadata, quality/efficiency metrics, and an explicit
  injected-selector-only boundary for future semantic retrieval.
- Context-window survey analysis is captured in the spec as required vs
  optional lanes, output/continuation headroom, lost-in-the-middle-aware
  ordering, model-routing boundaries, exact-retrieval boundaries, and
  overflowing-history evaluation fixtures.
- Context-management compression profiles are now specified as policy presets:
  `balanced`, `fast`, `exact`, `semantic`, `recency_weighted`, and
  `instruction_weighted`.
- The spec inventory and completion matrix now include
  `context-management-prepare-stage`, and graph mutation is documented as the
  derived workflow-operation layer rather than a context-management helper.
- Cross-cutting future-work ideas from Micheal Lanham's `AI Agents in Action,
  Second Edition: Intelligent Workflows With LLMs, MCP, A2A, and More`
  (Manning, ISBN `9781633434530`) are tracked in the owning specs without
  expanding immediate implementation scope.
- `rag-orchestration-contract` now records RAG as a future orchestration
  contract, not a retrieval infrastructure framework. It covers caller-owned
  retrievers/adapters, provenance, context injection, index lifecycle,
  permission-aware retrieval, routing profiles, GraphRAG layers, cache state,
  degraded execution traces, and evaluation hooks.
- `skill-source-resolution` is prepared for v1 implementation with a spec, plan,
  and task list. The v1 boundary is opt-in package-local bundled `SKILL.md`
  loading only, with deterministic skill-ref injection, bounded UTF-8 bodies,
  redacted provenance, and capability/status reporting.
- ReAct/tool workflow guidance exists in authored docs and documents
  route-gated tool execution.
- `llama-cpp-memory-fit-profile` is prepared for v1 implementation as an
  optional injected-evaluator advisory profile for resolved GGUF assets.

## Latest Milestones

- `128acc2` recorded capability-status v1 completion.
- `6ee9d43` recorded approval/sandbox v1 completion.
- `2786e52` recorded MCP explicit registry-injection v1 completion.
- `633cbe3` recorded live input-guardrail v1 completion.
- `4d60fb1` recorded iterative agent-loop runtime v1 completion.
- `987915a` prepared the llama.cpp memory-fit profile v1 implementation plan.
- `c8a8770` added missing default `llama_cpp` dependency handling coverage.
- `89ace5e` documented the optional direct llama.cpp extra in README/API docs.
- `8c83492` added MLX unsupported-platform coverage proving non-macOS execution
  fails before model resolution or dependency loading.
- `8f63fb9`, `55a6fba`, and `7b7cf6d` completed package-owned PyInstaller
  hook support for `openai-model-registry`, hook advertisement, and packaging
  cleanup after build validation.
- `743b38c` added the context-management prepare-stage spec, plan, task list,
  and context-pruning reference relocation out of async-session memory.
- `5dd0e5a` recast context-management planning around provider-neutral
  hierarchical compression, including turn units, budget lanes, rolling
  summaries, deterministic older-turn selection, chronological reassembly, and
  fallback trimming.
- `ed22596` added LCWMS-derived lifecycle, metadata, and metric taxonomy to
  the context-management spec while preserving the no durable runner memory and
  no built-in vector retrieval boundaries.
- `bc65162` tracked context-window survey findings in the spec, including
  required/optional context, reserve-token headroom, lost-in-the-middle
  ordering, model routing, exact retrieval, and overflow fixture guidance.
- `b7bb17e` refined context-compression boundaries, added named compression
  profiles, and clarified graph mutation as the workflow-derivation mechanism
  for future context-management attachment or insertion.
- `89488e4` aligned the top-level README, spec inventory, completion matrix,
  and graph-mutation planning artifacts with those boundaries.
- `fcde8bf` tracked evaluated agent-architecture follow-ups across the spec
  index, MCP runtime, guardrails, iterative loops, context management,
  capability reporting, and sandbox/workspace specs.
- `f59e7dd` expanded the RAG orchestration spec with production RAG ideas from
  evaluated RAG books, including index lifecycle, permission-aware retrieval,
  retrieval routers/profiles, cache contracts, GraphRAG construction vs
  query-time retrieval, degraded execution, and evaluation lifecycle metadata.
- `78d080c` prepared `skill-source-resolution` for implementation by resolving
  v1 decisions, adding `plan.md` and `tasks.md`, and updating the spec index.
- The commits between those checkpoints implemented:
  - capability-status report contract, metadata-only reporting, collaborator
    coverage, approval/MCP/guardrail status
  - approval interruption result contract and direct tool pause enforcement
  - explicit MCP tool binding and registry construction helpers
  - input guardrail contract and executor enforcement
  - opt-in iterative model-tool loops, safety hardening, and loop trace events

## Remaining

- Next highest-ROI slice in the roadmap: implement `skill-source-resolution`
  Slice 1, covering policy/data model, resolver provenance dataclasses, policy
  shape validation, and targeted validation tests.
- Optional local-model advisory work remains deferred until local-model
  ergonomics is the immediate driver:
  - `llmfit-model-fit-filter` for pre-download filtering
  - prepared `llama-cpp-memory-fit-profile` v1 for post-resolution GGUF
    profiling
- No PyInstaller packaging work is currently pending after the hook support PR
  and branch synchronization.
- Pending package metadata from earlier local-model work may still need review
  if local-model dependency packaging resumes.
- Power-Marimo host automation remains deferred until approval/sandbox and
  host-managed continuity boundaries are clear.
- Runner-owned durable session storage remains deferred until a concrete
  workflow proves the need.
- Runner-owned RAG infrastructure remains out of scope. RAG future work should
  stay focused on metadata validation, capability/status diagnostics, trace
  contracts, provenance, context-management integration, and fake-adapter
  evaluation hooks.
- Skill-source resolution v1 must stay package-local and opt-in. Do not add
  external roots, `source_path` reads, support-file prompt loading, network
  fetching, executable skill files, or raw skill-body trace payloads in v1.
- Live prompt pruning, compaction, and hierarchical prompt-context injection are
  owned by `context-management-prepare-stage`, not the async-session memory
  pipeline.
- Context compression implementation should begin with turn grouping and lane
  assembly, including lifecycle diagnostics and metric metadata, then
  compression-profile normalization and deterministic older-turn selection.
  Required lanes, output headroom, and overflowing-history checks should be
  addressed before summary generation or provider-owned compaction.
- LLM step interpreter middleware remains deferred until sandbox, approval,
  guardrails, tracing, redaction, and capability reporting are stable.

## Risks or Follow-ups

- Do not treat future-feature specs as implementation approval; create scoped
  plan/task/validation checkpoints before code changes.
- Approval interruption is v1 only: durable resume, approval decisions,
  model-emitted tool-call approval, argument modification, parallel approvals,
  and serialized resume state remain deferred.
- Sandbox runtime is partial: approval-before-side-effect exists, but write
  tools, shell tools, workspace grants, sandbox adapters, and changed-path audits
  remain deferred.
- MCP runtime is v1 only: live transports, process lifecycle, discovery,
  reconnect, schema cache, and diagnostics beyond metadata remain deferred.
- Guardrails are v1 only: output phases, tool phases, reject-content behavior,
  warning-only behavior, retries, timeouts, and external adapters remain
  deferred.
- Iterative loops are v1 only: loop `state_field`/`tool_result` final selectors,
  durable approval resume, output/tool guardrails, parallel tool calls, and
  durable transcripts remain deferred.
- llama.cpp memory-fit profiling is only prepared, not implemented. V1 should
  use fake evaluators in tests and must not run live llama.cpp binaries or load
  real GGUF models.
- Keep high-risk execution surfaces behind registry, approval, sandbox,
  capability-status, and guardrail boundaries.
- Keep core tests fake-only; do not add live OpenAI, MCP, Hugging Face, Marimo,
  llama.cpp, or local-model calls to unit tests.
- Keep MLX local execution macOS-only and lazy on other platforms: adapter
  construction and model alias inspection should not import `mlx_lm`, resolve
  local model assets, or fail until generation is attempted.
