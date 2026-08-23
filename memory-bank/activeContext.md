<!-- markdownlint-disable MD013 -->
# Active Context

## Current Focus

- `live-guardrail-execution` V2 is implemented in `78f9d9c`: caller-registered
  pass-or-abort `tool_input` guardrails run after validated preparation and
  before approval, hooks, retry, or dispatch for direct `tool_use_step` and
  model-tool-loop origins. Declarations run in manifest order, subjects are
  recursively copied, and missing, malformed, or mismatched outcomes fail
  closed with redacted trace events. Focused validation passed with 251 tests;
  the full suite passed with 694 tests and 4 skips, alongside Ruff, pre-commit,
  package, and docs builds.
- V2 adopts the internal coordinator from `bda6333` through a private
  executor-supplied guardrail runner; it adds no public coordinator API. Output
  and tool-output guardrails, reject-content, retries, timeouts, and external
  adapters remain deferred. The next highest-ROI preparation target is
  `provider-backed-context-compaction`; memory-aware context has already
  completed its passive first slice and needs only its exit-gate reassessment.
- The shared DAR tool-invocation coordinator is implemented in `bda6333`.
  Direct `tool_use_step` and model-tool-loop calls now share approval,
  lifecycle, tracing, and registry-dispatch behavior. Approval-required input
  validation happens before an interruption; registry preparation binds the
  validated arguments to a resolved tool. Provider, interpreter, and sandbox
  ingress remain separately scoped follow-up adopters; tool-input guardrails
  are now the implementation-ready V2 adopter described above.
- LiteLLM is now an upstream `^1.97.0` runtime dependency. The temporary
  `dynamic_agent_runner.litellm` shim and vendored-wheel packaging flow are
  retired; direct sync/async Chat Completions transport remains the implemented
  L1 boundary, while broader Codex migration is deferred.
- Latest committed spec-context slice: `a1f3011` added
  `specs/scratchpad-context-manager/spec.md` and recorded
  `sickn33/antigravity-awesome-skills` provenance across `specs/README.md`,
  `context-management-prepare-stage`, `skill-source-resolution`, and
  `persistent-agent-sessions`. Scratchpad remains spec-only: v1 is a
  caller-owned `ScratchpadStore` protocol plus automatic large tool-result
  offload to compact artifact refs, with read/list/search/delete tools and
  durable storage deferred.
- Antigravity-derived context follow-ups are now assigned to existing spec
  owners rather than a new feature area: `artifact_trail`, probe-based
  compression tests, and degradation fixtures belong to
  `context-management-prepare-stage`; lazy skill loading/token budgets and
  `overflow_behavior: error` belong to `skill-source-resolution`; structured
  session snapshot summary metadata belongs to `persistent-agent-sessions`.
- The latest committed Graphify spec alignment is `54ac838`. T7 is implemented
  as opt-in token/file chunking with adaptive splitting, summary-only
  reconciliation, and safety-constrained partial merge/duplicate repair. T8 is implemented as a pure advisory policy selector. The T8.7 benchmark
  (13 sibling repositories, 472 admitted documents) retained fixed8 as the
  runtime default; token-aware remains opt-in and advisory after gpt-5.4-mini
  and gpt-5.4 live probes mostly timed out.
- The current branch includes the Graphify semantic-output contract fix in
  `ab0c40e`: worker prompts require a top-level `nodes`/`edges`/`hyperedges`
  object, exact `source_file` provenance, node ids, edge endpoints, and
  hyperedge endpoint arrays. Focused Graphify tests pass.
- Live interoperability coverage is intentionally separate from the Graphify
  implementation. Commits `588610e` and `9c34e91` provide an opt-in,
  structured-output test that sends the same model/prompt through the installed
  Codex CLI and DAR adapter, validates both through an injected contract, and
  keeps the normal unit suite offline. It requires
  `DAR_RUN_LIVE_CODEX_PARITY=1`.
- Documentation now records the current Graphify CLI model-selection behavior
  and live-test boundary in `b5af3a3`; authored Sphinx files remain under
  `docs/files/`.
- The Graphify semantic extractor is implemented through commits `4214d7f`,
  `9236cd6`, `b0d1e0d`, `7a08576`, `4eab435`, and `b48f419`. The package-owned,
  registry-mediated `graphify-extract` console workflow
  validates manifests and semantic output, runs bounded parallel workers,
  emits staged artifacts outside accepted `graphify-out/`, and leaves stock
  Graphify curation/promotion external. Commit `c0de3b8` also caches the
  provider-aware default model once per extraction run.
- The OpenAI-compatible provider spec now has a committed ChatGPT/Codex model
  catalog parity bug-fix slice (`6d5d7a1`). TDD work remains: preserve catalog
  priority and visibility, choose the first visible model as default, forward
  `ChatGPT-Account-ID`, and retain generic-provider fallback behavior.
- `specs/apple-foundation-model-adapter/` records A1 as implemented for local text and explicit JSON Schema output through the existing async facade. Standalone live text, structured, and strict-workflow paths succeeded; pytest-native Apple SDK generation remains blocked by opaque status 255 despite availability preflight. A2 remains a separately gated Apple tool-callback bridge through DAR approval and tool-runtime behavior.
- `specs/llm-step-interpreter-middleware/spec.md` now records the recommended
  multi-interpreter contract in commit `c9f505f`: one DAR-owned
  `run_interpreter` model gateway, bounded package-local or caller-supplied
  usage descriptors, multiple node-allowed interpreter ids, async-first
  caller-provided adapters, and node-scoped first-release state. Interpreter
  tool requests must enter a DAR-owned invocation coordinator before registry
  execution so exposure, validation, approval, hooks, tracing, state,
  redaction, and model-facing result shaping remain authoritative.
- Interpreter middleware remains future work. The amended spec still needs
  approval, backend prototypes and benchmarks, general-purpose runtime safety
  and redaction decisions, a descriptor budget, and an approval/resume decision
  for nested tools before implementation planning.
- The repository knowledge-graph toolchain is installed and initialized through
  commit `a74bf68`. CodeGraph owns indexed source navigation, GitNexus owns
  execution-flow and change-impact analysis, and Graphify owns the allowlisted
  knowledge corpus. Guidance and maintenance scripts now come from installed
  skills under `/Users/roschuma/.agents/skills/`; the deleted repo-local copies
  are not authoritative.
- Commit `e59005e` updated AGENTS guidance to use installed graph skills, live
  Osaurus model discovery, staged Graphify refresh gates, and the skill-local
  knowledge-graph maintenance entrypoint.
- Graphify is now restricted to the knowledge-only allowlist, including
  `specs/`, and semantic extraction routes through Osaurus with approved OpenAI
  models. Generated `graphify-out/`, `.codegraph/`, and local
  `.graphifyignore` state stay uncommitted. The current Graphify data is useful
  for corpus topology and consistency triage, not as a substitute for
  deterministic traceability checks or CodeGraph/source verification.
- Documentation has been refreshed to match the current runtime surface around
  bounded subagent helpers and collaborative session coordination. Commit
  `1f76a9a` updated `README.md` and authored Sphinx docs under `docs/files/` to
  document `CollaborativeAgentSessionManager`, clarify that autonomous
  multi-agent orchestration remains out of scope, and record validation coverage
  for subagent packs and collaborative parent/child sessions.
- Docs validation for that refresh passed with `make -C docs html`. Generated
  `docs/source/*.rst` output was unchanged after the build; authored docs remain
  the source of truth.
- `specs/local-model-availability-api/` is implemented through the v1 baseline.
  The feature started from a downstream Power Marimo request captured in
  `cline-tasks/local-model-availability-api-feature-request.md`, then gained
  spec/plan/tasks/validation artifacts and was executed in three committed
  slices:
  - `43ec3c3` added the public availability contract and no-download explicit
    path/cache-root checks.
  - `6cddf46` added MLX GGUF/converted-directory validation plus an injected
    remote metadata seam for `would_download`, invalid, and unknown states.
  - `49291f3` documented the API and marked the spec/corpus as implemented.
- The public local-model availability API now exposes
  `LocalModelAssetReference`, `LocalModelAvailability`,
  `LocalModelAvailabilityStatus`, `LocalModelAvailabilitySource`,
  `LocalModelRemoteMetadata`, and `check_local_model_availability(...)` from
  the package root. It is read-only: no downloads, adapter construction, model
  loading, generation, memory profiling, broad inventory, or native Hugging Face
  cache introspection.
- Final local-model availability validation passed:
  `poetry run pytest tests/test_local_models.py tests/test_mlx_models.py`
  `tests/test_hugging_face_support.py tests/test_import.py -q` with
  `71 passed`; `poetry run ruff check src tests`; and targeted pre-commit.
- `local-model-availability-api` Slice A4 is now implemented as narrow cached
  inventory. The public surface is a read-only
  `list_local_model_assets(...)` helper with package-owned inventory value
  objects, default-cache and current-call root scanning, deterministic
  de-duplication, direct GGUF and converted MLX classification, bounded
  warnings, package-root exports, docs, and fake filesystem tests.
- The A4 inventory boundary is strict: scan only DAR-owned/default download
  cache locations plus current caller-provided roots for that call. Do not scan
  arbitrary sibling/parent directories, recurse through provider cache
  internals, persist caller-provided roots, manage/delete/migrate local model
  directories, perform Hub metadata/search/downloads, construct adapters, load
  models, run generation, or memory-profile assets.
- Recent local-model commits:
  - `0f0b671` completed cached inventory Slice A4 evidence and corpus status.
  - `2efa99a` documented the cached inventory API.
  - `24f7f79` added cached inventory safety-bound tests.
  - `c88c9e9` added current caller-provided root scanning.
  - `71ef5b6` added default cache inventory over direct GGUF and converted MLX.
  - `63c115b` added the public cached inventory contract.
  - `5addae5` prepared the cached inventory Slice A4 spec, plan, tasks,
    validation log, corpus index, and AGENTS learning.
  - `fbed269` refreshed memory-bank state after local-model availability v1.
  - `49291f3` documented the local-model availability API and marked the
    baseline complete.
  - `6cddf46` added MLX validation and injected no-download remote metadata.
  - `43ec3c3` added the public availability contract and no-download local
    checks.
- Current implementation horizon after local-model availability A4: native
  Hugging Face cache introspection, real metadata integration, strict exception
  mode, broad inventory, persistent root management, model loading, downloads,
  and execution remain deferred. The ROI queue now treats Apple A1 and
  memory-aware context validation as the next implementation candidates;
  LiteLLM Slice L1 is complete.
- `specs/openai-responses-tool-loop-compat/` Slice R1 is implemented and
  complete. DAR now upstreams the behavior Power Marimo had been patching
  locally: streamed Responses function-call preservation, internal structured
  tool-loop transcript data, ChatGPT/Codex `function_call_output` follow-ups,
  phase-aware `tool_choice_policy.initial` /
  `tool_choice_policy.after_tool_result`, and top-level `{{tool_results}}`
  rendering through `ToolResult.model_facing_output` while preserving raw
  `WorkflowExecutionState.tool_results`.
- A downstream Power Marimo adoption handoff note now exists at
  `../power-marimo/nonspec-tasks/power-marimo-openai-responses-tool-loop-dar-handoff.md`.
  It recommends upgrading to a DAR build with Responses R1, deleting
  Power Marimo's `openai_responses_compat` monkey patch, migrating notebook chat
  manifests from `tool_choice: required` to `tool_choice_policy`, and keeping
  Power Marimo domain compaction downstream through `ToolResult.model_output`.
- `specs/host-workflow-integration/` Slice H2 is complete. DAR now exposes
  `inspect_agent_workflow_capabilities(...)` for inline runtime manifests and
  already loaded workflows, reuses the existing `CapabilityStatusReport`
  contract, and reports host canonical/model-facing ids for tools registered
  through `HostToolBinding`.
- `specs/tool-descriptor-budgeting/` Slice T1 is complete. The feature is
  opt-in and deterministic: it validates runtime/node policy, ranks only
  registry-exposed model tools, packs descriptors within token/count limits,
  enforces required tools before dispatch, and emits redacted diagnostics.
- `specs/litellm-provider-adapter/` Slice L1 is implemented and validated:
  DAR includes a minimal `dynamic_agent_runner.litellm` sync/async
  OpenAI-compatible transport, direct Chat Completions translation, public
  factories, fake tests, and an explicit official-SDK compatibility path.
  ChatGPT/Codex now has an opt-in Responses-native wrapper; global default
  replacement remains intentionally deferred.
- The latest manual OCI package run under Python 3.13 completed successfully.
  Its DAR wheel contains the bundled transport and its artifact also contains
  `litellm-1.92.0-py3-none-any.whl`, whose SHA-256 matches the checked-in
  wheel. Upstream LiteLLM publication remains deferred.
- L2.1 Codex compatibility audit is complete in
  `specs/litellm-provider-adapter/l2-codex-compatibility.md` (commit
  `85a4b37`). It establishes Responses as the Codex transport boundary,
  `aresponses(...)` async-first with `responses(...)` sync parity, DAR-owned
  auth/model-listing policy, and capability-gated Chat Completions fallback.
- L2.2-L2.6 are implemented in separate slices: `46a7b5f` adds the native
  Responses seam, `25ee3e6` adds model aliases, `7ac62ef` adds DAR auth/config
  handoff, `e244284` preserves instruction/tool transcript semantics, and
  `55f4aa2` adds the opt-in auth-resolving wrapper with SDK rollback.
- `specs/memory-aware-context-pipeline/spec.md` remains a proposed caller-owned
  long-term memory orchestration contract inspired by `memlayer`. Its first
  passive-context slice is implemented and fake-testable: manifest validation,
  capability reporting, and metadata preservation are live, while retrieval,
  salience, ingestion, persistence, and background execution remain deferred.
  The explicit fold-back gate to `metadata.rag_pipeline` remains pending exit-gate
  reassessment.
- NLTK parser work for tool descriptor selection is explicitly deferred as a
  future benchmarked experiment, not Slice T1 scope.
- The previous completed stream resolved a downstream Power-Marimo blocker in
  `AgentSession.accept_stream(...)`: terminal stream events can now expose the
  same `AgentSessionResult`/`WorkflowResult` shape as `accept(...)`, and callers
  can choose progress events, terminal events, terminal session-result
  attachment, and progress event-type filters.
- Recent commits:
  - `c263146` completed OpenAI Responses tool-loop Slice R1 across the feature
    spec, spec index, ROI notes, and dynamic-agent-runner roadmap.
  - `a1e7a20` rendered top-level `{{tool_results}}` using
    `ToolResult.model_facing_output` while preserving raw state.
  - `0aae18f` added phase-aware runtime/node-local `tool_choice_policy`.
  - `2686de1` rendered structured tool-loop transcripts as Responses
    `function_call`/`function_call_output` follow-ups for ChatGPT/Codex.
  - `50463ee` preserved streamed Responses function-call output items.
  - `4572d29` refreshed memory-bank state during Responses R1 execution.
  - `8395c58` prepared OpenAI Responses tool-loop compatibility Slice R1 with
    plan/tasks/validation artifacts and aligned the ROI/spec corpus around it as
    the then-current highest-value non-paused candidate.
  - `17834d1` added the OpenAI Responses tool-loop compatibility feature spec
    and the downstream Power Marimo feature-request note.
  - `0fa4d47` aligned the spec corpus after host-workflow H2 completion so the
    plan, index, and dynamic-agent-runner roadmap no longer describe inline
    preflight as pending work.
  - `278c933` implemented host-workflow H2: inline/generated and loaded-workflow
    capability preflight, host id capability details, API exports, docs, specs,
    and fake tests.
  - `a29ad7b` prepared host-workflow integration H2 with plan/tasks/validation
    artifacts.
  - `3c5ee5b` aligned descriptor-budgeting status after implementation and
    removed it from the outstanding ROI queue.
  - `5b95125` refreshed memory-bank state after descriptor budgeting.
  - `f7ab5d5` recorded descriptor-budgeting completion in README, runtime
    policy docs, spec index, and validation artifacts.
  - `fd1b54c` implemented opt-in tool descriptor budgeting in registry,
    validation, token estimation, executor integration, and tests.
  - `c001c3f` prepared tool descriptor budgeting for implementation and aligned
    the spec corpus around the LiteLLM Python 3.14 pause.
  - `cb88c53` prepared the LiteLLM provider adapter as the then-current
    implementation candidate with plan/tasks/validation artifacts and a
    narrowed Slice L1.
  - `2183e74` recorded the outstanding-spec ROI ranking and marked the older
    roadmap order historical.
  - `234c4b0` refreshed the memory bank after memory-aware context work.
  - `16a0a19` added the memory-aware context pipeline spec and spec-index
    coverage, including the RAG separation/no-implicit-save constraint.
  - `a5d3209` added the tool descriptor budgeting spec and spec-index coverage.
- The stream-result work is committed in separate slices:
  - `0237b42` added the source API behavior in `sessions.py`
  - `9b45bf5` added focused session-stream regression tests
  - `e1676c5` aligned the model-event-streaming spec surface
  - `bdf29ef` aligned README/Sphinx/skill docs with the new client contract
- The expanded MLX surface is implemented and committed in source/test slices:
  explicit converted-MLX vs GGUF model formats, GGUF path validation, resolved
  path loading for the default `mlx_lm` backend, filtered generation kwargs
  with request-level overrides, and conservative adapter capabilities.
- Downstream handoff notes were created under `../power-marimo/cline-tasks/`
  for:
  - migrating Power Marimo to the expanded MLX API surface
  - moving Power Marimo host automation toward implemented DAR host surfaces
    such as `HostToolBinding`, `create_host_tool_registry`,
    `ResolvedModelSelection`, `summarize_trace_events`, and
    `summarize_capability_report`
- `specs/async-session-memory-pipeline/` is now a completed boundary handoff:
  async-session owns session identity/history metadata only; live sessions are
  owned by `persistent-agent-sessions`; pruning behavior is owned by
  `context-management-prepare-stage`; graph attachment/injection is owned by
  `internal-graph-mutation`.
- `specs/internal-graph-mutation/` is complete through Slice 4 for
  pruning-context attachment diagnostics around eligible `llm_step`
  interactions.
- `specs/context-management-prepare-stage/` is complete through Slice 10 for
  bounded pruning-context preparation from supplied
  `WorkflowExecutionState.session_messages` and `AgentSession` history.
- `specs/model-event-streaming/` is implemented for the v1
  `AgentSession.accept_stream(...)` surface. It streams redacted session/run
  lifecycle and prepared-input diagnostics, preserves terminal final-result
  authority, exposes terminal `session_result`/`workflow_result` for trusted
  in-process consumers by default, and supports caller-controlled stream
  filters. Provider-native token deltas and richer loop-progress streaming
  remain future work.
- Context-window follow-up work now has three prepared future feature specs:
  `provider-backed-context-compaction`, `model-backed-context-summaries`, and
  `semantic-context-profiles`. They split remote `/responses/compact`-style
  provider compaction/window baselines, explicit model-backed summarizer
  adapters, and richer semantic/profile selection behavior.
- Power-Marimo has been reclassified as a downstream dynamic-workflow client,
  not a DAR-owned automation feature. DAR must stay a generic workflow runner
  with host-provided tools, model adapters, execution context collaborators,
  traces, and runtime policy; Marimo, Qt/QExt, hosted UI lifecycle,
  Power-Marimo safety policy, SDK/session behavior, and live validation belong
  in `../power-marimo`.
- `specs/tool-descriptor-budgeting/` is implemented through Slice T1. NLTK,
  embeddings, vector stores, descriptor compression, model-backed selection,
  capability/status reporting, and richer fallback behavior remain deferred.
- `specs/host-workflow-integration/` is implemented through Slice H2. The v1
  helper surface now includes host tool binding, model-facing aliases, resolved
  model-selection handoff, bounded diagnostics, inline/generated and
  loaded-workflow capability preflight, and host id capability details.
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
- `memory-aware-context-pipeline` is proposed, not implementation-authorized.
  It deliberately differs from RAG by modeling caller-owned durable agent/user
  memory with memory identity, temporal provenance, persistence eligibility, and
  explicit ingestion. If a workflow declares both RAG and memory pipelines, DAR
  must not persist RAG-retrieved content to context memory unless the workflow
  explicitly invokes a caller-owned memory ingestion tool with deliberate input.
- `skill-source-resolution` v1 is implemented. Source loading is opt-in and
  package-local only: referenced bundled `SKILL.md` bodies under
  `skill-bundle/` inject through `skill_instructions` after effective
  `skill_refs` are derived, with bounded UTF-8 loading, redacted provenance,
  fail-closed validation, and capability/status reporting for metadata-only,
  live, and rejected states.
- `persistent-agent-sessions` v1 is implemented:
  public `AgentSession`, `AgentSessionState`, `AgentSessionResult`, and
  `InMemorySessionStore` provide bounded cross-prompt continuity, current-state
  retrieval, copy-safe snapshots, snapshot restart, history policies,
  session-id state injection, same-session concurrency rejection, sync wrapper
  parity, docs, and live capability/status reporting.
- `model-event-streaming` v1 is implemented on top of persistent sessions.
- The next ROI actions are Apple Foundation Models A1 and
  `memory-aware-context-pipeline` first-slice validation. LiteLLM Slice L1 is
  complete with a bundled fallback and temporary OCI wheelhouse artifact;
  OpenAI Responses R1 and semantic context selector Slice S1 are already
  implemented.

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
- Core LiteLLM adapter implementation and its packaging boundary are captured
  in `specs/litellm-provider-adapter/spec.md`; upstream package publication
  and global default Codex-provider replacement remain open.
- Persistent agent sessions v1 is implemented and documented; completion
  evidence is captured in `specs/persistent-agent-sessions/validation.md`, and
  cross-spec ownership wording was reconciled across the spec surface.
- Pruning-context graph injection is implemented:
  - `4a67119` captured RED graph-mutation diagnostics coverage.
  - `184e6eb` captured RED context-management injection coverage.
  - `e4e94d5` bounded injected pruning context before prompt rendering.
  - `7d00fe2` reported pruning-context attachment points.
  - `a71d8e6` verified `AgentSession` history can feed bounded pruning context.
- Model event streaming v1 is implemented:
  - `db2df00` captured the session stream contract with tests.
  - `77dee3c` added `AgentSession.accept_stream(...)` and exported
    `AgentSessionStreamEvent`.
- `9ccfc3c` reconciled the completed async-session, graph-mutation,
  context-management, model-event-streaming, and persistent-session spec
  surfaces.
- `957f673` prepared three context-window follow-up specs for provider-backed
  compaction, model-backed summaries, and semantic context profiles.
- `3fbfd63` implemented the expanded MLX local adapter surface.
- `6361e05` added focused tests for the expanded MLX surface.
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
  - `specs/persistent-agent-sessions/spec.md`
  - `specs/model-event-streaming/spec.md`
- Implementation-ready feature packages:
  - `specs/apple-foundation-model-adapter/`
- Deferred implementation follow-ups:
  - upstream LiteLLM publication and global default Codex-provider replacement
    in `specs/litellm-provider-adapter/spec.md`
- Prepared feature packages:
  - `specs/llama-cpp-memory-fit-profile/spec.md`
  - `specs/provider-backed-context-compaction/spec.md`
  - `specs/model-backed-context-summaries/spec.md`
  - `specs/semantic-context-profiles/spec.md`
- Downstream boundary/reference packages:
  - `specs/power-marimo-host-automation/spec.md`
- Later feature packages:
  - `specs/async-session-memory-pipeline/spec.md`
  - `specs/llm-step-interpreter-middleware/spec.md`
  - optional local-model advisory specs:
    `specs/llmfit-model-fit-filter/spec.md`

## Next Steps

- Approve Apple Foundation Models A1 and execute its bounded `plan.md`,
  `tasks.md`, and `validation.md` without pulling A2 tool callbacks into the
  first release.
- Keep Apple A2 and interpreter middleware aligned on one future DAR-owned tool
  invocation coordinator. Do not let provider callbacks or interpreter bridges
  call handlers or `ToolRegistry.invoke_tool_async(...)` directly.
- Before planning interpreter implementation, resolve the five remaining
  clarification items and run backend prototypes/benchmarks. Keep executable
  adapters caller-provided and descriptor frontmatter non-executable.
- Run the `memory-aware-context-pipeline` declarative first-slice validation when
  it is scheduled, including the explicit decision to retain a distinct memory
  contract or fold it back into RAG.
- Resume LiteLLM work only for upstream package publication, live Codex parity,
  or an approved global-default migration; L2.2-L2.6 are complete as an
  opt-in wrapper.
- If extending model event streaming beyond v1, create plan/tasks for
  provider-native token deltas, adapter streaming protocol, model-tool-loop
  progress events, cancellation/backpressure behavior, redaction/tool payload
  policy, and capability/status reporting.
- If continuing local-model advisory work, decide whether the pending
  `pyproject.toml` / `poetry.lock` optional llama.cpp metadata edits should be
  committed, revised, or discarded before executing another slice.
- If extending skill-source support, start a new beyond-v1 plan before adding
  external roots, `source_path` reads, support-file prompt loading, network
  fetching, Markdown frontmatter parsing, or raw-body debugging modes.
- If extending context growth management beyond the implemented prepare-stage
  slices, start from one of the prepared follow-up specs:
  `provider-backed-context-compaction`, `model-backed-context-summaries`, or
  `semantic-context-profiles`.
- Use CodeGraph for current source and call paths, GitNexus for execution-flow
  and change-impact questions, and Graphify for specifications, rationale, and
  cross-document relationships. Do not use Graphify's knowledge graph as proof
  of implementation conformance.
- Preserve unit-test boundaries: fake clients, fake tools, fake MCP bindings,
  fake guardrails, and fake local-model profilers only; no live OpenAI, MCP,
  Hugging Face, Marimo, llama.cpp, or local model calls in core tests.
