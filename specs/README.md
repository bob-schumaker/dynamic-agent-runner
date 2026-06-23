# dynamic-agent-runner Specs

This directory contains the repository's product/runtime specification and the
feature-spec packages that extend or analyze that primary direction.

## Primary Spec

The primary spec is
[`specs/dynamic-agent-runner/spec.md`](dynamic-agent-runner/spec.md). It owns the
package-directory-first runtime contract, executable workflow model, validation
rules, public API direction, and baseline runtime boundaries.

Companion planning artifacts:

- [`specs/dynamic-agent-runner/plan.md`](dynamic-agent-runner/plan.md)
- [`specs/dynamic-agent-runner/tasks.md`](dynamic-agent-runner/tasks.md)

Portfolio evaluation artifacts:

- [`specs/outstanding-spec-roi/spec.md`](outstanding-spec-roi/spec.md) records
  the current advisory ROI ranking for outstanding and deferred spec work. It is
  roadmap memory only, not implementation authorization.

## Feature Specs

| Feature | Spec | Status | Completion |
| --- | --- | --- | --- |
| OpenAI-compatible provider wrapper | [`spec.md`](openai-compatible-provider-wrapper/spec.md) | Implemented | Slices 1-6 complete; optional compatibility polish only |
| Default OpenAI/Codex auth discovery | [`spec.md`](default-openai-codex-auth/spec.md) | Implemented | Adapter-owned default OpenAI/Codex auth discovery, ordered Codex API-key/ChatGPT auth selection, caller precedence, unsupported-auth handling, opt-out behavior, tests, and docs complete |
| OpenAI Responses tool-loop compatibility | [`spec.md`](openai-responses-tool-loop-compat/spec.md) | Implemented Slice R1 | Upstream replacement for Power Marimo's private monkey patch: streamed Responses function-call preservation, structured tool-loop transcript rendering, ChatGPT/Codex `function_call_output` follow-ups, explicit `tool_choice_policy`, model-facing top-level `tool_results`, docs, and fake tests complete |
| LiteLLM provider adapter | [`spec.md`](litellm-provider-adapter/spec.md) | Implementation candidate; Slice L1 prepared but paused | Slice L1 remains prepared but is paused until LiteLLM supports the package's Python 3.14 target; prepared work covers default direct SDK chat-completions transport, plan/tasks/validation artifacts, fake-test discipline, explicit official-SDK compatibility path, and ChatGPT/Codex-on-LiteLLM deferred to a follow-up Responses-aware slice |
| llama.cpp local-model adapter | [`spec.md`](llama-cpp-local-model/spec.md) | Implemented | Slices 1-3 complete; direct in-process llama.cpp chat, endpoint helpers, local asset resolution, tests, and docs complete; optional embedding follow-up unscheduled |
| macOS MLX local-model adapter | [`spec.md`](mlx-local-model-adapter/spec.md) | Implemented | Public macOS-only in-process MLX adapter helpers, converted-directory/GGUF/Hub resolution, generation kwargs, capability metadata, identity validation, executor coverage, tests, and docs complete |
| Model adapter coverage policy | [`spec.md`](model-adapter-coverage/spec.md) | Implemented | Public `model_adapter_coverage` policy, strict supplied-adapter failures, augmented default OpenAI coverage, local-only routing removal, tests, and docs complete |
| PyInstaller packaging support | [`spec.md`](pyinstaller-packaging-support/spec.md) | Implemented v1 baseline | Package-owned PyInstaller hook directory advertisement and `openai-model-registry` hook are complete, including data-file collection, metadata copying, and focused tests |
| Internal graph mutation | [`spec.md`](internal-graph-mutation/spec.md) | Implemented through pruning-context injection follow-up | Internal typed mutation, context-pruning attachment, validation, prepared-input integration, attachment diagnostics, and pruning-context graph injection for eligible `llm_step` interactions are complete; future structural node insertion, edge rewiring, richer link-level operations, and public schemas require a new approved slice |
| Hugging Face model search | [`spec.md`](hugging-face-model-search/spec.md) | Implemented | Public Hub discovery API, result contract, error translation, exports, tests, and docs complete |
| Hugging Face support layer | [`spec.md`](hugging-face-support-layer/spec.md) | Implemented | Internal shared Hub import/call/error mechanics, search routing, local download routing, tests, and validation complete |
| Local model availability API | [`spec.md`](local-model-availability-api/spec.md) | Implemented v1 baseline | Public read-only explicit-reference preflight covers local paths, Hugging Face file/snapshot refs, cache-root source reporting, backend-aware validation, injected no-download remote metadata checks, docs, and fake tests |
| llmfit model-fit filter | [`spec.md`](llmfit-model-fit-filter/spec.md) | Future optional advisory feature | Proposed optional `llmfit`-on-`PATH` pre-download filter; keep recommended plus unknown models without bundling or installing llmfit |
| llama.cpp memory fit profile | [`spec.md`](llama-cpp-memory-fit-profile/spec.md) | Implemented v1 baseline | Optional post-resolution GGUF memory-fit profiler with injected evaluators, fail-open advisory results, strict-mode errors, deterministic fit math, suggested `n_ctx`, tests, and evidence complete |
| Capability status report | [`spec.md`](capability-status-report/spec.md) | Implemented | Public preflight report distinguishes live, metadata-only, missing-collaborator, disabled, and invalid runtime capabilities; CLI rendering and future collaborator types remain deferred |
| Host workflow integration | [`spec.md`](host-workflow-integration/spec.md) | Implemented through Slice H2 | Host tool binding registry helpers, canonical/model-facing id aliases, collision checks, bounded redacted trace/capability summaries, resolved model-selection handoff, inline/generated and loaded-workflow preflight, host id capability details, lifecycle docs, exports, and fake tests complete |
| Tool descriptor budgeting | [`spec.md`](tool-descriptor-budgeting/spec.md) | Implemented Slice T1 | Opt-in deterministic `ToolSelector` validates runtime/node policy, ranks only registry-exposed model tools, packs descriptors within token/count limits, enforces required tools before dispatch, and emits redacted diagnostics; NLTK remains deferred to benchmark-only future scope |
| Web tool pack | [`spec.md`](web-tool-pack/spec.md) | Implemented v1 baseline | Opt-in `web_search` and `web_fetch` registry helpers with required injected clients, bounded normalized results, URL scheme/domain policy, exports, and fake tests complete; richer network policy, redirects/timeouts, trace/capability status, and provider adapters remain deferred |
| Workspace data tool pack | [`spec.md`](workspace-data-tool-pack/spec.md) | Implemented v1 baseline | Opt-in JSON-compatible workspace data write/read/search/list/delete registry helpers with required injected store, metadata-first search/list, delete approval flag, exports, and fake tests complete; durable storage, indexing, trace/capability status, and host dirty-state remain caller-owned or deferred |
| Subagent tool pack | [`spec.md`](subagent-tool-pack/spec.md) | Implemented v1 baseline | Opt-in `run_subagent`/`run_subagents` registry helpers with required injected runner, presets, max-child policy, bounded normalized aggregate results, exports, and fake tests complete; parallelism, timeout enforcement, trace/capability status, and durable child lifecycle remain deferred |
| Async session memory pipeline | [`spec.md`](async-session-memory-pipeline/spec.md) | Metadata baseline plus completed handoff | Metadata-only OA8 baseline implemented; live in-memory session behavior is owned by `persistent-agent-sessions`; pruning-context graph-injection work was completed through `context-management-prepare-stage` and `internal-graph-mutation` without expanding OA8 into durable memory |
| Persistent agent sessions | [`spec.md`](persistent-agent-sessions/spec.md) | Implemented v1 baseline | Public `AgentSession`, `AgentSessionState`, `AgentSessionResult`, and `InMemorySessionStore` provide bounded cross-prompt continuity, current-state retrieval, snapshot restart, history policies, same-session concurrency rejection, sync wrapper parity, and live capability/status reporting |
| Collaborative agent sessions | [`spec.md`](collaborative-agent-sessions/spec.md) | Implemented v1 baseline | In-memory `CollaborativeAgentSessionManager`, presets, child state snapshots, spawn/list/get/send/close/current-state APIs, snapshot restart, exports, and fake tests complete; wait/resume, streaming, capability/status, durable storage, and stronger compatibility checks remain deferred |
| Model event streaming | [`spec.md`](model-event-streaming/spec.md) | Implemented v1 session event stream | Public `AgentSession.accept_stream(...)` emits provider-neutral, redacted session events with session/run correlation, terminal final-result authority, terminal `AgentSessionResult`/`WorkflowResult` access, and caller-controlled stream filters; provider-native token deltas, model-tool-loop progress specialization, cancellation/backpressure expansion, and capability/status reporting remain future |
| Context management prepare stage | [`spec.md`](context-management-prepare-stage/spec.md) | Implemented through Slice 10 plus follow-ups | `prepare_model_input(...)` covers hierarchy injection, turn-aware session pruning, lane-budget assembly, selected older turns, file context, retrieved-context lane packing, deterministic basic compaction, rolling summaries, injected model-summary compaction, injected pre/mid-turn compaction seams, new-window reset metadata, overflow classification/retry diagnostics, trace/capability metadata, bounded pruning-context injection, exact/hybrid identifier preservation, and injected semantic older-turn selection; remote compaction and remaining richer profile behavior remain prepared follow-ups |
| Provider-backed context compaction | [`spec.md`](provider-backed-context-compaction/spec.md) | Future prepared feature | Prepared optional provider-backed remote compaction follow-up, including `/responses/compact`-style capability gating, replacement-history validation, compaction window ids, token baselines, fallback behavior, and redacted diagnostics |
| Model-backed context summaries | [`spec.md`](model-backed-context-summaries/spec.md) | Implemented v1 baseline | Injected `context_summarizer` path for `model_summary` compaction, fail-closed missing summarizer behavior, bounded output, metadata, exports, and fake tests complete; richer prior-summary/provenance and capability/status reporting remain deferred |
| Semantic context profiles | [`spec.md`](semantic-context-profiles/spec.md) | Implemented through Slice S1 | Exact and `hybrid_exact_semantic` older-turn preservation plus injected fake-testable semantic older-turn selection are implemented with metadata and tests; memory-kind hints, stale/redundant omission, RAG lane borrowing, prompt-cache-aware ordering, and selector capability/status reporting remain deferred |
| LLM step interpreter middleware | [`spec.md`](llm-step-interpreter-middleware/spec.md) | Future investigation | Spec captured; backend selection, prototypes, and implementation not started |
| Approval interruption and resume | [`spec.md`](approval-interruption-resume/spec.md) | Implemented v1 baseline | Direct approval-required `tool_use_step` interruption, public pause result, redacted approval traces, high-level API guardrails, capability status, tests, and evidence complete; durable resume remains deferred |
| Sandbox and workspace runtime | [`spec.md`](sandbox-workspace-runtime/spec.md) | Partial approval-policy baseline | Approval-before-side-effect boundary is implemented through approval interruption v1; write/shell runtime, workspace grants, sandbox adapters, and mutation audits remain deferred |
| MCP runtime integration | [`spec.md`](mcp-runtime-integration/spec.md) | Implemented v1 baseline | Explicit caller-supplied MCP registry injection, MCP provenance, conservative policy defaults, capability status, tests, and evidence complete; live transports, process lifecycle, and discovery remain deferred |
| Live guardrail execution | [`spec.md`](live-guardrail-execution/spec.md) | Implemented v1 baseline | Caller-registered input guardrail pass/abort, fail-closed missing adapters, redacted traces, capability status, tests, and evidence complete; output/tool phases remain deferred |
| RAG orchestration contract | [`spec.md`](rag-orchestration-contract/spec.md) | Implemented v1 baseline | Expanded declarative `metadata.rag_pipeline` validation and capability/status reporting cover staged RAG metadata, retriever collaborators, provenance and context-management handoff declarations, source readiness, permissions, cache, and degraded states while keeping prompt packing, ingestion, embeddings, indexes, graph stores, rerankers, compressors, evaluators, and retrieval execution outside RAG ownership |
| Memory-aware context pipeline | [`spec.md`](memory-aware-context-pipeline/spec.md) | Proposed; roadmap refinement needed | Proposed caller-owned long-term memory orchestration contract inspired by `memlayer`, now refined with a retrieval-only first slice, fold-back gate to `rag_pipeline`, schema/enums, collaborator contracts, invocation points, evidence handoff, invariants, trace payloads, and capability/status states without adding runner-owned memory storage, embeddings, provider wrappers, background services, or `memlayer` as a dependency |
| SKILL.md source resolution | [`spec.md`](skill-source-resolution/spec.md) | Implemented v1 baseline | Opt-in package-local bundled `SKILL.md` loading under `skill-bundle/`, policy validation, bounded UTF-8 body loading, deterministic skill-ref injection, redacted provenance, capability/status reporting, and fake-adapter tests complete; external roots, `source_path` reads, support-file prompt loading, and network fetching remain deferred |
| Iterative agent-loop runtime | [`spec.md`](iterative-agent-loop-runtime/spec.md) | Implemented v1 baseline | Bounded opt-in serial model-tool loops execute inside eligible `llm_step` nodes with registry dispatch, approval pauses, fail-closed safety checks, loop traces, tests, and evidence complete; state-field final selectors and durable resume remain deferred |
| Power-Marimo dynamic workflow client | [`spec.md`](power-marimo-host-automation/spec.md) | Downstream boundary evaluated | DAR owns only generic dynamic workflow execution with host-provided tools; `../power-marimo` owns Marimo, Qt, hosted lifecycle, app safety policy, SDK/session behavior, and live validation |

## Completion Matrix

| Capability Area | Owning Spec Package | Implemented Baseline | Remaining / Deferred Work |
| --- | --- | --- | --- |
| Package-directory workflow loading and execution | `dynamic-agent-runner` | Complete through package alignment, async-first execution, tracing, hooks, prompt-cache metadata, and portable `tool_type` preservation | Future scoped expansions only |
| OpenAI-compatible provider facade | `openai-compatible-provider-wrapper` | Sync/async provider facade, provider config, SDK-backed defaults, package exports, and README example complete | Optional compatibility polish for provider-specific behavior |
| Default OpenAI/Codex auth discovery | `default-openai-codex-auth` | Adapter default-provider resolver, `OPENAI_API_KEY` fallback, Codex user-level `config.toml` and ordered API-key/ChatGPT `auth.json` discovery, ChatGPT/Codex backend provider selection, opt-out behavior, redaction, tests, and docs complete | Future support for PAT or agent-identity auth requires a separate provider/base-url/signing spec |
| OpenAI Responses tool-loop compatibility | `openai-responses-tool-loop-compat` | Slice R1 implemented | Streamed Responses function-call preservation, structured tool-loop transcript rendering, ChatGPT/Codex `function_call_output` follow-ups, explicit `tool_choice_policy`, model-facing top-level `tool_results`, docs, and fake tests complete |
| LiteLLM provider adapter | `litellm-provider-adapter` | None | Slice L1 is prepared but paused until LiteLLM supports the package's Python 3.14 target; the prepared slice remains direct sync/async completion transport, request translation, response normalization, public factories, default-provider migration, fake tests, and explicit official-SDK compatibility path |
| llama.cpp local-model adapters | `llama-cpp-local-model` | Local endpoint helpers, direct in-process llama.cpp chat adapters, provider-seam wiring, exports, model-resolution precedence, Hugging Face download wiring, local failure taxonomy, tests, and docs complete | Optional separate local embedding configuration remains later |
| macOS MLX local-model adapters | `mlx-local-model-adapter` | Public adapter helpers, converted-directory and GGUF preflight, injected Hub reference resolution, generation kwargs, conservative capability metadata, identity validation, executor coverage, tests, and docs complete | Embeddings, multimodal IO, streaming public APIs, tool calling, structured output, model conversion, and MLX server helpers remain deferred |
| Model adapter coverage policy | `model-adapter-coverage` | Public API/context argument, executor selection behavior, strict empty-list and nonmatching-adapter failures, augmented default OpenAI coverage, local-only routing removal, tests, and docs complete | Future coverage modes or provider discovery require a separate feature spec |
| PyInstaller packaging support | `pyinstaller-packaging-support` | Package advertises a PyInstaller hook directory through `pyinstaller40`; the package-owned `hook-openai_model_registry.py` collects `openai_model_registry` data files and copies `openai-model-registry` distribution metadata | Additional dependency hooks, downstream frozen-application builds, and CI PyInstaller packaging are deferred until a concrete caller requires them |
| Compile-time graph mutation | `internal-graph-mutation` | Internal typed mutation datamodel, context-pruning mutation, validation, prepared-input integration, attachment diagnostics, and pruning-context injection for eligible `llm_step` interactions complete | Future structural node insertion, edge rewiring, richer link-level context-management insertion, and public mutation schemas require new approval |
| Public Hugging Face model discovery | `hugging-face-model-search` | Repository-owned search API, normalized result types, error translation, exports, tests, and docs complete | Future richer Hub capabilities require a separate feature spec |
| Shared Hugging Face SDK support | `hugging-face-support-layer` | Internal helper for lazy Hub import, read-only Hub calls, and domain-specific error translation complete | Future Hub behavior beyond search and local-model downloads requires a separate feature spec |
| Local model availability preflight | `local-model-availability-api` | Public explicit-reference preflight API complete | Broad inventory, native Hugging Face cache introspection, real metadata integration, and strict exception mode remain deferred |
| Optional local model fit filtering | `llmfit-model-fit-filter` | None | Future optional `llmfit` CLI JSON advisory layer to preserve recommended and unknown models before explicit Hub asset downloads |
| Optional llama.cpp memory fit profiling | `llama-cpp-memory-fit-profile` | Injected-evaluator, fail-open profiling for resolved local GGUF assets complete | Concrete llama.cpp command integration, metadata probing, automatic budget discovery, caching, GPU/offload recommendations, and execution gating remain deferred |
| Capability/status reporting | `capability-status-report` | Public report contract, package inspection, metadata-only declarations, model adapter coverage, tool registry coverage, built-in tool-pack status, invalid package reporting, tests, and completion evidence complete | Future CLI rendering and additional collaborator types remain deferred until there is a concrete caller |
| Host workflow integration | `host-workflow-integration` | Host-owned tool bindings, model-facing aliases, collision checks, bounded redacted diagnostics, resolved model selection helper, inline/generated and loaded-workflow preflight, host id capability-report details, lifecycle docs, exports, and tests complete | Future work only if another host integration gap appears |
| Tool descriptor budgeting | `tool-descriptor-budgeting` | Slice T1 implemented | Opt-in runtime/node policy validation, deterministic registry-exposed tool ranking, OpenAI-compatible descriptor token/count packing, required-tool enforcement, executor integration, redacted diagnostics, and fake tests complete; NLTK evaluation remains a benchmarked optional experiment |
| Web tool pack | `web-tool-pack` | Opt-in `web_search`/`web_fetch` registry pack with injected fake-testable clients, bounded normalized results, URL scheme/domain policy, exports, and tests complete | Redirect/timeouts/local-network policy, trace redaction, capability/status reporting, provider adapters, and extraction/readability remain deferred |
| Workspace data tool pack | `workspace-data-tool-pack` | Opt-in JSON-compatible write/read/search/list/delete registry pack with injected store, metadata-first search/list, delete approval flag, exports, and tests complete | Durable storage, indexing, trace/capability reporting, and host dirty-state remain caller-owned or deferred |
| Subagent tool pack | `subagent-tool-pack` | Opt-in `run_subagent`/`run_subagents` registry pack with injected runner, presets, max-child policy, normalized aggregate results, exports, and tests complete | Parallel execution, timeout/iteration budgets, trace/capability reporting, recursive-spawn policy, and durable child lifecycle remain deferred |
| Async session metadata | `async-session-memory-pipeline` | `runtime.execution_policy.async_session` metadata preservation and fail-closed validation complete | Durable external storage, broader memory replay, and summary generation are deferred; live in-memory sessions are owned by `persistent-agent-sessions`; pruning-context graph injection is complete through `context-management-prepare-stage` plus `internal-graph-mutation` |
| Persistent agent sessions | `persistent-agent-sessions` | Public `AgentSession` and `InMemorySessionStore` v1 complete with state snapshots, bounded `accept(...)`, history policies, session-id state injection, snapshot restart, same-session concurrency rejection, sync wrapper parity, and capability/status reporting | Durable external stores, model-backed summaries, long-running graph executors, raw tool transcript replay, durable approval resume, and cross-process locking remain deferred |
| Collaborative agent sessions | `collaborative-agent-sessions` | In-memory parent/child session manager, presets, child state snapshots, spawn/list/get/send/close/current-state APIs, snapshot restart, exports, and tests complete | Wait/resume APIs, child event streaming, capability/status reporting, durable storage, compatibility validation, and explicit tool-policy enforcement remain deferred |
| Model event streaming | `model-event-streaming` | Session-level `AgentSession.accept_stream(...)` event stream complete with redacted execution events, session/run correlation, terminal final-result authority, terminal `AgentSessionResult`/`WorkflowResult` access, and caller-controlled stream filters | Provider-native token deltas, model-tool-loop progress specialization, cancellation/backpressure expansion, lower-level executor stream APIs, and streaming capability/status reporting remain deferred |
| Context-management prepare stage | `context-management-prepare-stage` | `prepare_model_input(...)` support exists for hierarchy injection, turn-aware current-run session pruning, lane-budget assembly, named compression profiles, deterministic and exact/hybrid older-turn selection, injected semantic older-turn selection, rolling summaries, injected model summaries, retrieved-context lane packing for RAG evidence, deterministic basic compaction, pre/mid-turn compaction seams, explicit reset metadata, overflow classification/retry diagnostics, capability status, trace metadata, and bounded pruning-context injection from supplied session messages | Provider-backed remote compaction and remaining richer profile behavior remain prepared follow-ups; built-in embeddings/vector retrieval and runner-owned durable memory remain out of scope |
| Provider-backed context compaction | `provider-backed-context-compaction` | None | Future provider-backed remote compaction path with capability gating, replacement-history validation, compaction window ids, token baselines, fallback policy, and capability/status reporting |
| Model-backed context summaries | `model-backed-context-summaries` | Injected summarizer collaborator path for `model_summary` compaction with fail-closed missing summarizer behavior, bounded output metadata, and fake tests complete | Richer prior-summary folding, source/file/tool provenance diagnostics, fallback ordering, and capability/status reporting remain deferred |
| Semantic context profiles | `semantic-context-profiles` | Exact and `hybrid_exact_semantic` older-turn selection preserve issue keys, filenames, and identifiers; Slice S1 adds caller-injected semantic scoring, missing-selector fallback diagnostics, direct/context collaborator threading, public selector contracts, and RAG lane separation with tests | Memory-kind hints, stale/redundant omission, RAG lane borrowing, prompt-cache-aware ordering, and selector capability/status reporting remain deferred |
| Interpreter middleware | `llm-step-interpreter-middleware` | Future feature spec and candidate interface expectations captured | Dependency checks, prototypes, benchmark evidence, backend selection, and implementation |
| Sandbox/workspace runtime | `sandbox-workspace-runtime` | Metadata-only `sandbox_runtime` preservation plus approval-before-side-effect boundary complete | Write tools, shell tools, workspace grants, sandbox adapters, and changed-path audits remain deferred |
| Approval interruption/resume | `approval-interruption-resume` | Public interruption contract, direct approval-required tool pause, no-side-effect-before-approval behavior, redacted approval traces, high-level API guardrails, capability status, tests, and evidence complete | Durable resume, approval decisions, model-emitted tool-call approval, argument modification, parallel approvals, and serialized resume state remain deferred |
| MCP runtime integration | `mcp-runtime-integration` | Metadata-only MCP registry-source and lifecycle diagnostics preservation plus explicit caller-supplied MCP registry injection complete | Live server discovery, process lifecycle, transports, reconnect, schema cache, and diagnostics beyond metadata remain deferred |
| Live guardrail execution | `live-guardrail-execution` | Metadata-only guardrail declaration preservation plus caller-registered input guardrail aborts before first runtime action complete | Output guardrails, tool guardrails, reject-content behavior, retries, timeouts, and external adapters remain deferred |
| RAG orchestration contract | `rag-orchestration-contract` | Expanded `metadata.rag_pipeline` validation and capability/status reporting exist for staged retrievers, required collaborators, provenance and context-management handoff declarations, source readiness, permissions, cache, and degraded states | Retrieval infrastructure, prompt packing, ingestion, embeddings, indexes, graph stores, rerankers, compressors, evaluators, answer citation rendering, output guardrails, and live retrieval orchestration remain deferred |
| Memory-aware context pipeline | `memory-aware-context-pipeline` | None | Future declarative memory pipeline validation, capability/status reporting, fake-testable memory retrieval tiers, provenance, trace events, retrieved-context handoff, no-implicit-save enforcement, and a first-slice decision on whether distinct memory semantics justify remaining separate from RAG; salience and ingestion execution remain future/deferred |
| SKILL.md source resolution | `skill-source-resolution` | Opt-in package-local bundled `SKILL.md` loading, policy validation, bounded UTF-8 body loading, deterministic prompt injection, redacted provenance, and capability/status reporting complete | External roots, `source_path` reads, support-file prompt loading, network fetching, Markdown frontmatter parsing, and raw-body debugging modes remain deferred |
| Iterative agent-loop runtime | `iterative-agent-loop-runtime` | Bounded opt-in serial model-tool loop execution complete for eligible `llm_step` nodes | Loop `state_field`/`tool_result` final selectors, durable approval resume, output/tool guardrails, parallel tool calls, and durable transcripts remain deferred |
| Power-Marimo dynamic workflow client | `power-marimo-host-automation` | Placeholder-safe fixture and fake-tool execution coverage complete; current `../power-marimo` evidence shows the host-owned tool-service and dynamic-agent-runner bridge pattern | No DAR implementation remains unless a generic runner contract is missing; Marimo, Qt, hosted lifecycle, domain adapters, app safety policy, and live validation remain downstream client concerns |

## Reading Order

1. Start with the primary [`dynamic-agent-runner/spec.md`](dynamic-agent-runner/spec.md).
2. Read [`dynamic-agent-runner/tasks.md`](dynamic-agent-runner/tasks.md) for the
   implementation history and feature roadmap index.
3. Read [`outstanding-spec-roi/spec.md`](outstanding-spec-roi/spec.md) for the
   current advisory ROI ranking of outstanding and deferred spec work.
4. For OpenAI adapter default-auth discovery behavior, read
   [`default-openai-codex-auth/spec.md`](default-openai-codex-auth/spec.md),
   with completion evidence in
   [`default-openai-codex-auth/tasks.md`](default-openai-codex-auth/tasks.md).
5. Read a feature package when working in that specific area; each feature spec
   owns its own scope boundary and completion evidence.

Do not treat future-analysis specs as implementation authorization. Feature
packages marked future investigation or optional follow-up require an explicit
scheduled task before code changes begin.

## Evaluated Cross-Cutting References

Micheal Lanham's `AI Agents in Action, Second Edition: Intelligent Workflows
With LLMs, MCP, A2A, and More` (Manning, ISBN `9781633434530`) was evaluated as
a cross-cutting agent architecture reference. Useful ideas were tracked as
future-work notes in the owning specs rather than as immediate implementation
scope:

- MCP `resources` and `prompts` belong to future MCP capability expansion, not
  the current explicit tool-binding baseline.
- Evaluation ideas such as rubrics, grounding checks, critic/evaluator agents,
  and trace-linked annotations belong near guardrails and future evaluation
  specs.
- Loop ideas such as layered termination gates, stagnation detection, strategy
  pivots, confidence gates, and knowledge-boundary awareness belong to future
  iterative-loop slices.
- Memory ideas such as semantic/episodic/procedural memory labels,
  access-frequency scoring, compression, and forgetting inform
  `memory-aware-context-pipeline` and context-management policy inputs without
  creating runner-owned durable storage.
- Production ideas such as prompt/tool/model versioning, idempotency,
  timeouts, fallback budgets, observability, and model routing inform
  capability/status, sandbox, and future deployment-oriented specs.

Jia Huang's `RAG from First Principles` (Packt Publishing, ISBN
`9781835888667`, 2026 metadata date) was evaluated as a RAG engineering
reference. Useful ideas were tracked in
[`rag-orchestration-contract/spec.md`](rag-orchestration-contract/spec.md):

- RAG should be first-class as orchestration metadata and workflow contract, not
  as runner-owned retrieval infrastructure.
- Ingestion, chunking, embeddings, vector storage, graph storage, reranking,
  compression, correction, and evaluation remain caller-owned.
- Retrieval mode, fusion, reranking, compression, correction, provenance,
  freshness, and evaluation should be modeled as distinct contract surfaces.
- Retrieval evaluation and response evaluation should remain separable so
  callers can inspect retrieval quality, faithfulness, groundedness, answer
  relevance, and context relevance independently.

Additional RAG and agent-data references were evaluated for production
orchestration details: Ranajoy Bose's `Mastering Retrieval-Augmented
Generation` (Apress, ISBN `9798868818080`), Tomaz Bratanic and Oskar Hane's
`Essential GraphRAG` (Manning, ISBN `9781633436268`), Andrei Gheorghiu's
`Building Data-Driven Applications with LlamaIndex - Second Edition` (Packt
Publishing, ISBN `9781806021857`), Mayo Oshin and Nuno Campos's `Learning
LangChain` (O'Reilly Media, ISBN `9781098167288`), Alireza Pareh and Alireza
Parandeh's `Building Generative AI Services with FastAPI` (O'Reilly Media, ISBN
`9781098160296`), Blaize Stewart and Ed Huang's `Agentic AI Data Architectures`
(O'Reilly Media, ISBN `0642572250140`), Benjamin Labaschin, Jim Allen Wallace,
Andrew Brookins, and Manvinder Singh's `Managing Memory for AI Agents`
(O'Reilly Media, ISBN `9798341661257`), Navnit Shukla, Kien Pham, Srikanth
Sopirala, and Harsha Tadiparthi's `AI-Ready Data Blueprints` (O'Reilly Media,
ISBN `9798341631786`), and Erik Benner, Hicham Assoudi, and Tural
Gulmammadov's `A Practical Guide to Oracle AI Engineering` (Packt Publishing,
ISBN `9781806110797`). They added these future contract concerns:

- Index lifecycle and source readiness should include source registries, source
  and index versions, refresh modes, tombstones, stale-source diagnostics, and
  source classes.
- Permission-aware retrieval should be declarable with permission scope, ACL
  authority, audit requirements, and fail-closed behavior when filtering cannot
  be confirmed.
- Retrieval routers and profiles should make query routing visible for
  capability/status reporting without adding a new primitive node kind.
- GraphRAG metadata should separate index-time graph construction from
  query-time graph retrieval strategies such as local search, global search,
  Cypher generation, and vector-plus-graph hybrid retrieval.
- Cache and degraded-execution metadata should distinguish response, semantic
  query, retrieval-result, and context-assembly caches, plus cache hit/miss,
  timeout, cancellation, stale-but-allowed, and partial-result states.

The repository-local RAG research notes under the Personal vault were also
evaluated as supporting material for the same spec. They reinforced additional
contract details:

- Retrieval orchestration should distinguish preindexed, just-in-time, hybrid,
  structural, and agentic retrieval modes instead of defaulting to vector
  search.
- Typed question parsing, typed answer states, reference-resolution loops, and
  absence-proof states should be explicit future contract surfaces.
- Retrieved evidence should preserve document structure, citation handles,
  parent/child links, adjacent ids, source coordinates, freshness, score, and
  context-management metadata when caller-owned retrievers provide them.
- Multi-stage retrieval funnels should expose candidate counts, cost/latency
  budgets, cache policy, thresholds, and fallback behavior without making the
  runner own retrieval infrastructure.

## Historical High-ROI Work Order

The June 2026 council review originally recommended this dependency order. Many
items are now complete. For the current advisory ROI ranking of still-outstanding
spec work, read [`outstanding-spec-roi/spec.md`](outstanding-spec-roi/spec.md).
Neither list is implementation authorization; each item still needs a scoped
plan and task slice before code changes begin.

1. Keep the spec portfolio status text consistent before new work.
2. Complete: implement `capability-status-report` so callers can distinguish
   live, metadata-only, missing-collaborator, disabled, unsupported, and invalid
   capabilities.
3. Complete: ship a narrow live-action vertical slice pairing
   `approval-interruption-resume` with `sandbox-workspace-runtime`.
4. Complete for the v1 boundary: expand capability/status reporting for the new
   approval/sandbox capabilities.
5. Complete: add policy-bound `mcp-runtime-integration`.
6. Complete: add `live-guardrail-execution`.
7. Complete: implement the prepared bounded `iterative-agent-loop-runtime` v1
   slice.
8. Complete: add opt-in package-local `skill-source-resolution`.
9. Complete: implement the `rag-orchestration-contract` v1 declarative
   validation and capability/status slice.
10. Implement additional local-model advisory features only when local-model
    ergonomics is the immediate driver: `llmfit-model-fit-filter` for
    pre-download filtering, plus any concrete llama.cpp command or metadata
    probing beyond the completed injected-evaluator
    `llama-cpp-memory-fit-profile` v1 baseline.
11. Complete: `host-workflow-integration` Slice H2 prevents downstream clients
    from duplicating inline preflight, host id report details, or
    context/session lifecycle glue. Keep
    `power-marimo-host-automation` as a downstream-boundary record, not an
    implementation target.
12. Keep `async-session-memory-pipeline` host-managed in v1. Pruning-context
    graph injection and the v1 session event stream are complete through their
    owning specs; add runner-owned durable session storage only after a concrete
    workflow proves the need.
13. Defer `llm-step-interpreter-middleware` until sandbox, approval, guardrails,
    tracing, redaction, and capability reporting are stable.

Clean dependency chain:

```text
status visibility
→ approval/sandbox mutation policy
→ MCP/guardrails
→ loops/skills
→ host workflow integration and standard tool packs
→ caller-owned memory orchestration
→ interpreter
```
