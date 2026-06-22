# Progress

## Working

- Core runtime supports package-directory workflow loading and execution,
  async-first APIs, sync wrappers, tool registry/overrides, OpenAI-compatible
  adapters/providers, retry, output contracts, token budgeting, tracing, hooks,
  prompt preparation, validation, runtime behavior overrides, model adapter
  coverage, local model helpers, in-memory persistent sessions, session event
  streaming, bounded pruning-context graph injection, and
  metadata-only future surfaces.
- Default OpenAI/Codex auth discovery and ChatGPT/Codex backend compatibility
  are implemented.
- llama.cpp and MLX local-model adapters are implemented through their current
  scoped baselines. The MLX adapter now supports converted-MLX and GGUF model
  formats, resolved-path loading, filtered generation kwargs with request-level
  overrides, conservative capability metadata, and focused regression coverage
  for those behaviors plus unsupported-platform short-circuit behavior.
- Capability status reporting is implemented for:
  - finite execution
  - metadata-only declarations
  - model adapter coverage
  - tool registry coverage
  - built-in tool-pack status
  - approval interruption coverage
  - MCP-origin registry entries
  - input guardrail adapter coverage
  - RAG metadata, retriever collaborator, provenance, and context-handoff
    readiness
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
  distribution metadata for frozen downstream clients. The hook also collects
  `tiktoken_ext` hidden imports so tokenizer encoding plugins are preserved in
  frozen apps.
- Sphinx configuration now derives project metadata from `pyproject.toml` and
  git config, and its Confluence mode uses a session override for Selenium SSO.
- The package advertises its PyInstaller hook directory through the
  `pyinstaller40` entry point, and the hook support was merged through the
  build-gated DevOps SCM PR flow.
- PyInstaller packaging support is now represented by
  `specs/pyinstaller-packaging-support/`, with `spec.md`, `plan.md`,
  `tasks.md`, `validation.md`, `specs/README.md` coverage, and primary roadmap
  coverage in `specs/dynamic-agent-runner/tasks.md`.
- Skill-source resolution v1 is implemented:
  - `runtime.execution_policy.skill_source_resolution` policy parsing and
    validation
  - package-local bundled `SKILL.md` resolution under `skill-bundle/`
  - fail-closed path, symlink, encoding, binary-content, and byte-budget checks
  - deterministic injection through `skill_instructions` after runtime
    `skill_refs` overrides
  - redacted prepared-input and trace provenance metadata
  - capability/status reporting for metadata-only, live, and rejected states
- `context-management-prepare-stage` now owns the prompt-preparation feature
  spec for session pruning, context compaction, hierarchical prompt-context
  injection, and provider-neutral hierarchical context compression.
- `context-management-prepare-stage` is implemented through Slice 10, including
  bounded pruning-context preparation from supplied session messages before
  eligible `llm_step` prompt rendering.
- Future context-window handling has three prepared feature specs:
  `provider-backed-context-compaction` for `/responses/compact`-style provider
  compaction plus window ids/baselines, `model-backed-context-summaries` for
  explicit summarizer collaborators, and `semantic-context-profiles` for richer
  profile/selector behavior.
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
- `internal-graph-mutation` is complete through Slice 4, with attachment
  diagnostics for pruning-context behavior around eligible `llm_step`
  interactions while keeping base workflow artifacts immutable.
- Cross-cutting future-work ideas from Micheal Lanham's `AI Agents in Action,
  Second Edition: Intelligent Workflows With LLMs, MCP, A2A, and More`
  (Manning, ISBN `9781633434530`) are tracked in the owning specs without
  expanding immediate implementation scope.
- `rag-orchestration-contract` v1 is implemented as a declarative RAG
  orchestration contract, not a retrieval infrastructure framework. V1 provides
  expanded `metadata.rag_pipeline` validation and capability/status reporting
  for caller-owned retriever collaborators, provenance requirements, source
  readiness, permissions, cache, degraded states, and
  context-management handoff declarations.
- Retrieved-context prompt assembly is owned by
  `context-management-prepare-stage`: RAG metadata can declare context assembly
  needs, but retrieved-context lanes, packing, trimming, compression,
  diagnostics, and final prompt injection belong to context management.
- `skill-source-resolution` is complete for the v1 boundary. It remains
  opt-in, package-local, and fake-test covered; external roots, `source_path`
  reads, support-file prompt loading, and network fetching remain deferred.
- ReAct/tool workflow guidance exists in authored docs and documents
  route-gated tool execution.
- `llama-cpp-memory-fit-profile` is prepared for v1 implementation as an
  optional injected-evaluator advisory profile for resolved GGUF assets.
- `litellm-provider-adapter` is drafted as a future core provider-transport
  spec. It proposes making LiteLLM the core OpenAI-compatible transport,
  preserving repository-owned OpenAI/Codex auth discovery, and mapping default
  Codex behavior through `create_litellm_codex_adapter_from_codex_auth(...)`.
- `persistent-agent-sessions` is implemented as a v1 feature for
  cross-prompt continuity through public `AgentSession`,
  `AgentSessionState`, `AgentSessionResult`, and `InMemorySessionStore`, with
  state retrieval, copy-safe snapshots, snapshot restart, history policies,
  session-id state injection, same-session concurrency rejection, sync wrapper
  parity, docs, and live capability/status reporting while keeping each prompt
  as a bounded executor run.
- `model-event-streaming` v1 is implemented through
  `AgentSession.accept_stream(...)`, with redacted session/run lifecycle events,
  prepared-input diagnostics, session/run correlation, terminal final-result
  authority, terminal `AgentSessionResult`/`WorkflowResult` access for trusted
  in-process consumers, and caller-controlled stream filters for progress
  events, terminal events, terminal session-result attachment, and progress
  event types.
- `tool-descriptor-budgeting` is captured as a future prepared feature spec.
  It proposes an optional `ToolSelector` policy that ranks eligible tools,
  packs OpenAI-compatible descriptors within a token budget, records redacted
  omission diagnostics, and leaves NLTK parser work as a benchmarked future
  experiment.
- `memory-aware-context-pipeline` is captured as a proposed future feature spec.
  It adapts useful `memlayer` ideas into a DAR-native, caller-owned contract
  for durable agent/user memory retrieval, provenance, traceability, and
  no-implicit-save behavior. Its first slice is intentionally retrieval-only
  and fake-testable; salience execution, ingestion execution, background work,
  embeddings, durable stores, provider wrappers, and `memlayer` itself remain
  out of scope.
- `async-session-memory-pipeline` remains a metadata/session-boundary reference.
  Pruning-context graph injection was completed through
  `internal-graph-mutation` and `context-management-prepare-stage` without
  adding durable runner-owned memory to OA8.
- Graphify is initialized for the repo with ignored generated output in
  `graphify-out/`. The current graph is AST/code-only and queryable through
  `graphify query`, `graphify path`, and `graphify explain`; semantic
  docs/spec extraction requires an LLM API key.
- Power-Marimo is now documented as a downstream DAR client boundary, not a
  DAR-owned automation feature. DAR owns generic dynamic-agent workflow
  execution with host-provided registries/adapters/context; `../power-marimo`
  owns Marimo, Qt/QExt, hosted lifecycle, app safety policy, SDK/session
  behavior, and live validation.
- Downstream Power-Marimo implementation handoff notes now exist under
  `../power-marimo/cline-tasks/` for the expanded MLX API surface and for
  host-automation migration toward the implemented DAR host-integration APIs.
- The Python 3.14.6 `.mise.toml`/`poetry.lock` refresh was committed and then
  reverted. A fresh redo commit is intentionally pending after the memory-bank
  refresh so downstream build automation sees a new triggering commit.

## Latest Milestones

- `16a0a19` added the memory-aware context pipeline spec and spec-index
  coverage, including the explicit rule that RAG-retrieved content is not
  persisted to context memory just because both `metadata.rag_pipeline` and
  `metadata.memory_pipeline` are present.
- `a5d3209` added the tool descriptor budgeting spec and spec-index coverage,
  naming `ToolSelector` as the future package-owned interface and keeping NLTK
  parser work experimental.
- `7d991cf` refreshed `poetry.lock`.
- `ae80bfd` refreshed memory-bank stream-session state.
- `9b45bf5` added regression tests for terminal stream
  `AgentSessionResult`/`WorkflowResult` access, terminal-only streaming,
  terminal-result omission, and progress event-type filtering.
- `0237b42` expanded `AgentSession.accept_stream(...)` with terminal
  `session_result`/`workflow_result` access and stream-consumption flags.
- `bdf29ef` aligned README, Sphinx API/observability docs, and the
  repo-local client skill with the stream-result/filter contract.
- `e1676c5` aligned the model-event-streaming specs and spec index with the
  Power-Marimo client-requested terminal-result/filter follow-up.
- `29d528d` aligned docs with the current repository status, including Python
  3.14.6 setup wording and implemented host/tool-pack surfaces.
- `6361e05` added tests for the expanded MLX adapter surface, including GGUF,
  generation kwargs, request overrides, and capabilities.
- `3fbfd63` expanded the MLX local adapter surface in source.
- `682b14f` documented the expanded MLX adapter API surface.
- `cda44d1` updated the MLX adapter completion spec surface.
- `9b17bc1` aligned the Power-Marimo spec with the downstream dynamic-workflow
  client boundary.
- `b296dd8` recorded the AGENTS.md project learning that Marimo, Qt, hosted UI,
  and app-specific automation remain downstream concerns.
- `fc7ad78` added graphify guidance to `AGENTS.md` and the repo-local
  `.agents/skills/graphify-noise-reduction/SKILL.md` addon.
- `bc7dff7` ignored generated `graphify-out/` artifacts.
- `957f673` prepared context-window follow-up specs for provider-backed
  compaction, model-backed summaries, and semantic context profiles.
- `9ccfc3c` aligned the completed async-session, graph-mutation,
  context-management, model-event-streaming, and persistent-session spec
  surfaces.
- `77dee3c` implemented v1 session event streaming through
  `AgentSession.accept_stream(...)`.
- `db2df00` captured the session event stream contract with RED tests.
- `a71d8e6` verified that `AgentSession` history can feed bounded pruning
  context without changing session persistence semantics.
- `7d00fe2` reported pruning-context attachment points through graph-mutation
  diagnostics.
- `e4e94d5` bounded injected pruning context before eligible `llm_step` prompt
  rendering.
- `184e6eb` captured RED context-management coverage for bounded
  pruning-context injection.
- `4a67119` captured RED graph-mutation coverage for pruning-context attachment
  diagnostics.
- `4620e52` refreshed memory-bank state after preparing pruning-context
  follow-up work.
- `386daa3` prepared pruning-context graph injection as follow-up Slice 4 in
  `internal-graph-mutation` and Slice 10 in
  `context-management-prepare-stage`, with async-session recorded as a boundary
  handoff rather than the implementation owner.
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
- `c54164e` added the post-hoc PyInstaller packaging support spec package and
  reconciled the spec inventory/roadmap so the hook work is represented.
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
- `b76d581` prepared the RAG orchestration contract for v1 implementation,
  added plan/tasks/validation artifacts, aligned the RAG/context-management
  ownership split, and refreshed the spec inventory/high-ROI order.
- `215e659`, `dd88fff`, and `5ba47a1` implemented RAG v1 validation,
  retriever capability/status reporting, and provenance/context-management
  handoff enforcement.
- `e67e68c` recorded RAG orchestration v1 completion evidence and refreshed
  spec/memory status.
- `78d080c` prepared `skill-source-resolution` for implementation by resolving
  v1 decisions, adding `plan.md` and `tasks.md`, and updating the spec index.
- `5f7d1fd`, `79cce93`, `99ed79d`, `ac8028b`, `9b5f6a8`, and `9f0557b`
  implemented and documented skill-source resolution v1 across policy models,
  package-local resolver validation, prompt injection, override coverage,
  capability/status reporting, and spec completion evidence.
- `3c5e672` added the core LiteLLM OpenAI-compatible adapter spec and spec
  index coverage.
- `eca1436` updated Sphinx configuration metadata loading and Confluence SSO
  session setup.
- `4782099` added the persistent agent sessions feature spec and spec index
  coverage.
- `c52b4cc` added the model event streaming feature spec and spec index
  coverage.
- `ecada0d` prepared the persistent-session TDD work stream.
- `53cad69`, `68f0d0b`, `08c9b76`, and `8c02300` implemented persistent
  sessions across state/store, bounded `accept(...)`, history/snapshot restart,
  concurrency guard, sync wrapper parity, and capability/status reporting.
- `cf8050e`, `10c71fc`, and `918c601` documented the persistent-session API,
  marked the spec implemented, and reconciled async-session versus
  persistent-session ownership across the spec surface.
- The commits between those checkpoints implemented:
  - capability-status report contract, metadata-only reporting, collaborator
    coverage, approval/MCP/guardrail status
  - approval interruption result contract and direct tool pause enforcement
  - explicit MCP tool binding and registry construction helpers
  - input guardrail contract and executor enforcement
  - opt-in iterative model-tool loops, safety hardening, and loop trace events

## Remaining

- LiteLLM provider work remains spec-only. Before implementation, create
  plan/tasks artifacts for the core dependency change, default provider
  selection, Codex auth adaptation, request/response mapping, fake-test
  strategy, and packaging implications.
- Model event streaming v1 is complete, but provider-native token deltas,
  model-tool-loop progress events, cancellation/backpressure expansion,
  lower-level executor event APIs, and streaming capability/status reporting
  remain deferred.
- Tool descriptor budgeting remains spec-only. Before implementation, create
  plan/tasks artifacts for `ToolSelector` policy validation, deterministic
  scoring, token-aware descriptor packing, diagnostics, and fake-test coverage.
- Memory-aware context pipeline remains spec-only. Before implementation,
  create plan/tasks artifacts for `metadata.memory_pipeline` validation,
  capability/status reporting, fake memory retrieval output, retrieved-context
  handoff, trace payloads, and the first-slice decision about whether the
  memory-specific surface should remain separate from `metadata.rag_pipeline`.
  Do not implement salience execution, ingestion execution, background jobs,
  runner-owned stores, embeddings, or `memlayer` dependencies in the first
  slice.
- Context-window follow-up implementation remains future. Start from the
  prepared specs for provider-backed context compaction, model-backed context
  summaries, or semantic context profiles before editing runtime code.
- Optional local-model advisory work remains deferred until local-model
  ergonomics is the immediate driver:
  - `llmfit-model-fit-filter` for pre-download filtering
  - prepared `llama-cpp-memory-fit-profile` v1 for post-resolution GGUF
    profiling
- No larger PyInstaller packaging work is currently pending after the hook
  support PR, branch synchronization, and `tiktoken_ext` hidden-import update.
- Power-Marimo-specific automation remains outside DAR. If `../power-marimo`
  exposes new needs, route them through generic runner contracts rather than
  DAR-owned Marimo, Qt, SDK, or app-lifecycle code.
- Runner-owned durable session storage remains deferred until a concrete
  workflow proves the need.
- Runner-owned RAG infrastructure remains out of scope. Future RAG work should
  stay focused on live retrieval orchestration only through caller-owned tools,
  richer routing metadata, answer citation rendering, evaluator/output-guardrail
  hooks, and context-management handoff boundaries.
- Skill-source resolution beyond v1 needs a new plan before adding external
  roots, `source_path` reads, support-file prompt loading, network fetching,
  executable skill files, Markdown frontmatter parsing, or raw skill-body trace
  payloads.
- Context-management prepare-stage v1 is implemented through Slice 10. The
  richer remote-compaction, model-summary, and semantic/profile tracks are now
  prepared as separate future specs.
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
