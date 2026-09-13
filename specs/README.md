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
| Natural-language workflow authoring | [`spec.md`](natural-language-workflow-authoring/spec.md) | Ready for implementation | Agent Engineering asks only irreducible contract questions, creates guidance for missing capabilities, and may generate a sealed converter only after its isolated plugin contract is implemented |
| Local tool sandbox hardening | [`spec.md`](local-tool-sandbox-hardening/spec.md) | Future investigation | OS/runtime isolation and adversarial acceptance required before DAR admits untrusted executable workflow-local tools or converter assets |
| OpenAI-compatible provider wrapper | [`spec.md`](openai-compatible-provider-wrapper/spec.md) | Implemented through Slice 8 | Repository-owned facade, SDK-backed defaults, ChatGPT/Codex priority/visibility/default parity, account-header forwarding, tests, and docs complete; future provider changes require a new scoped slice |
| Default OpenAI/Codex auth discovery | [`spec.md`](default-openai-codex-auth/spec.md) | Implemented | Adapter-owned default OpenAI/Codex auth discovery, ordered Codex API-key/ChatGPT auth selection, caller precedence, unsupported-auth handling, opt-out behavior, tests, and docs complete |
| OpenAI Responses tool-loop compatibility | [`spec.md`](openai-responses-tool-loop-compat/spec.md) | Implemented Slice R1 | Upstream replacement for Power Marimo's private monkey patch: streamed Responses function-call preservation, structured tool-loop transcript rendering, ChatGPT/Codex `function_call_output` follow-ups, explicit `tool_choice_policy`, model-facing top-level `tool_results`, docs, and fake tests complete |
| LiteLLM provider adapter | [`spec.md`](litellm-provider-adapter/spec.md) | Slice L1 implemented and validated; upstream dependency adopted and shim retired | Upstream LiteLLM 1.97.0 is the default direct-SDK Chat Completions transport behind DAR's request/response boundary, with public factories, fake-test discipline, explicit official-SDK compatibility, and package-owned missing-transport errors; legacy OCI wheel cleanup and ChatGPT/Codex global migration remain deferred |
| LiteLLM-only Codex transport | [`spec.md`](litellm-only-codex-transport/spec.md) | Postponed pending LiteLLM upstream support | DAR retains direct SDK ChatGPT/Codex transport; upstream-compatibility analysis and re-entry feasibility gate are preserved for a future LiteLLM release/configuration |
| llama.cpp local-model adapter | [`spec.md`](llama-cpp-local-model/spec.md) | Implemented | Slices 1-3 and T5.0-T5.6 complete: direct in-process llama.cpp chat, endpoint helpers, local asset resolution, standalone embeddings, terminal embedding workflows, model-selectable embedding tools, tests, and docs complete |
| macOS MLX local-model adapter | [`spec.md`](mlx-local-model-adapter/spec.md) | Implemented | Public macOS-only in-process MLX adapter helpers, converted-directory/GGUF/Hub resolution, generation kwargs, capability metadata, identity validation, executor coverage, tests, and docs complete |
| macOS MLX local embedding adapter | [`spec.md`](mlx-local-embedding-adapter/spec.md) | Proposed | Optional macOS in-process backend for generalized embedding-model support: workflow packages lock model materials and descriptors, while DAR supplies only reviewed generic ABI/provider implementations |
| MLX local-model tool use | [`spec.md`](mlx-local-model-tool-use/spec.md) | M6.4 source helper delivered | Explicit sync/async Qwen3 MLX helpers own strict native-envelope parsing for the pinned artifact and complete the fake-only parity matrix; generic stock MLX remains text-only, and local-model competency remains a separate manual gate |
| Apple Foundation Models adapter | [`spec.md`](apple-foundation-model-adapter/spec.md) | A1–A4 implemented; A2 B5 bridge regression open | Async in-process Responses-compatible facade includes text/JSON Schema generation, coordinator-routed Apple tool callbacks, sealed-host profile selection, and schema-preserving gateway fallback. The eligible-Mac Fastmail read-only acceptance has redacted evidence; B5 tracks the real SDK bridged-wrapper `Annotated` resolution failure |
| Fastmail inbox triage | [`spec.md`](fastmail-inbox-triage/spec.md) | Implemented and v4 acceptance recorded | Task-specific direct-llama.cpp Qwen Fastmail triage package is limited to one current reviewed read-only `search_email` capability and a five-message result budget. The v4 package passed its redacted read-only acceptance with no mailbox mutation. |
| Model adapter coverage policy | [`spec.md`](model-adapter-coverage/spec.md) | Implemented | Public `model_adapter_coverage` policy, strict supplied-adapter failures, augmented default OpenAI coverage, local-only routing removal, tests, and docs complete |
| Model interface tool-parity tests | [`spec.md`](model-interface-parity/spec.md) | T1 deterministic matrix and wrapper-local T2 approval interaction delivered | Deterministic, offline controlled-tool matrix for adapter contract parity; manually gated runner is delivered and positive live acceptance is tracked separately |
| Live model-interface acceptance | [`spec.md`](live-model-interface-acceptance/spec.md) | Ready for implementation; initial observations recorded | Positive real-model S1/S2/S3/S4/S5 acceptance, classified run receipts, and compatibility diagnostics; malformed/adversarial rows remain deterministic injected-seam coverage |
| Workflow model support matrix | [`spec.md`](workflow-model-support-matrix/spec.md) | Draft; implementation not approved | Capability-gated, package/material-bound coverage for synthetic Fastmail and embedding workflows plus separately authorized redacted Fastmail live-probe receipts; unsupported and deferred combinations are classified rather than treated as failures |
| PyInstaller packaging support | [`spec.md`](pyinstaller-packaging-support/spec.md) | Implemented v1 baseline | Package-owned PyInstaller hook directory advertisement and `openai-model-registry` hook are complete, including data-file collection, metadata copying, and focused tests |
| Internal graph mutation | [`spec.md`](internal-graph-mutation/spec.md) | Implemented through pruning-context injection follow-up | Internal typed mutation, context-pruning attachment, validation, prepared-input integration, attachment diagnostics, and pruning-context graph injection for eligible `llm_step` interactions are complete; future structural node insertion, edge rewiring, richer link-level operations, and public schemas require a new approved slice |
| Hugging Face model search | [`spec.md`](hugging-face-model-search/spec.md) | Implemented | Public Hub discovery API, result contract, error translation, exports, tests, and docs complete |
| Hugging Face support layer | [`spec.md`](hugging-face-support-layer/spec.md) | Implemented | Internal shared Hub import/call/error mechanics, search routing, local download routing, tests, and validation complete |
| Local model availability API | [`spec.md`](local-model-availability-api/spec.md) | Implemented v1 baseline | Public read-only explicit-reference preflight covers local paths, Hugging Face file/snapshot refs, cache-root source reporting, backend-aware validation, injected no-download remote metadata checks, docs, and fake tests |
| Workflow model materials | [`spec.md`](workflow-model-materials/spec.md) | Reviewed; ready for implementation planning | Sealed portable workflow packages carry canonical immutable material locks; DAR verifies, downloads, prepares, and executes only those locked artifacts under host policy |
| Workflow capability requirements | [`spec.md`](workflow-capability-requirements/spec.md) | C1–C3 and C4.1 implemented; C4.2 test-ready | Sealed packages declare exact standard DAR capability contracts; DAR resolves an installed compatible provider or fails before materialization or input ingress |
| Workflow embedding and index artifacts | [`spec.md`](workflow-embedding-index-artifacts/spec.md) | Implemented through sealed portable runtime | Generic sealed document-snapshot to opaque vector-index-bundle contract; each workflow revision locks its own embedding model material closure while DAR supplies bounded ABI/provider admission and workflow-local chunk/index semantics |
| Workflow locked inference callback | [`spec.md`](workflow-locked-inference-callback/spec.md) | Proposed | Generic bounded sealed-asset callback to an exactly locked DAR generation model; package-local domain semantics remain outside DAR |
| Sealed artifact workflow runner | [`spec.md`](sealed-artifact-workflow-runner/spec.md) | Implemented through sealed portable runtime | Generic durable sealed-artifact input/output runtime used by embedding-index and locked-inference assets |
| Local model preparation | [`spec.md`](local-model-preparation/spec.md) | Implemented historical baseline; ownership superseded | DAR-owned cache, verification, and deterministic-preparation mechanics remain reusable; workflow-bound material declarations supersede the host recipe catalog as the portable contract |
| Local model runner interface | [`spec.md`](local-model-runner-interface/spec.md) | Implemented through T5; budget migration pending | DAR-owned generic `transformers-peft-v1` compatibility runner consumes verified base/adapter closures locked by the workflow; client runners are reserved for nonstandard model/runtime profiles |
| Model execution plugin interface | [`spec.md`](model-execution-plugin-interface/spec.md) | Future work | Host-registered, versioned model-execution plugins extend DAR only for nonstandard models while DAR retains verified artifacts, resource/lifecycle control, sealed ingress, and tracing |
| Model generation resource budgets | [`spec.md`](model-generation-resource-budgets/spec.md) | Ready for implementation | Canonical host-capped per-fragment, aggregate output, context, deadline, and enforceable memory budget contract for all model-generation runners; workflow page semantics remain workflow-local |
| Workflow input converter plugin | [`spec.md`](workflow-input-converter-plugin/spec.md) | Implemented through manual gate; release pending | Workflow-sealed, instance-durable Python converter packages pack opaque invocation bytes for a compatible standard runner without teaching DAR binary formats or tensor shapes; Docker and OS-level isolation are deferred to sandbox hardening |
| llmfit model-fit filter | [`spec.md`](llmfit-model-fit-filter/spec.md) | Future optional advisory feature | Proposed optional `llmfit`-on-`PATH` pre-download filter; keep recommended plus unknown models without bundling or installing llmfit |
| llama.cpp memory fit profile | [`spec.md`](llama-cpp-memory-fit-profile/spec.md) | Implemented v1 baseline | Optional post-resolution GGUF memory-fit profiler with injected evaluators, fail-open advisory results, strict-mode errors, deterministic fit math, suggested `n_ctx`, tests, and evidence complete |
| Capability status report | [`spec.md`](capability-status-report/spec.md) | Implemented | Public preflight report distinguishes live, metadata-only, missing-collaborator, disabled, and invalid runtime capabilities; CLI rendering and future collaborator types remain deferred |
| Host workflow integration | [`spec.md`](host-workflow-integration/spec.md) | Implemented through Slice H2 | Host tool binding registry helpers, canonical/model-facing id aliases, collision checks, bounded redacted trace/capability summaries, resolved model-selection handoff, inline/generated and loaded-workflow preflight, host id capability details, lifecycle docs, exports, and fake tests complete |
| Tool descriptor budgeting | [`spec.md`](tool-descriptor-budgeting/spec.md) | Implemented Slice T1 | Opt-in deterministic `ToolSelector` validates runtime/node policy, ranks only registry-exposed model tools, packs descriptors within token/count limits, enforces required tools before dispatch, and emits redacted diagnostics; NLTK remains deferred to benchmark-only future scope |
| Web tool pack | [`spec.md`](web-tool-pack/spec.md) | Implemented v1 baseline | Opt-in `web_search` and `web_fetch` registry helpers with required injected clients, bounded normalized results, URL scheme/domain policy, exports, and fake tests complete; richer network policy, redirects/timeouts, trace/capability status, and provider adapters remain deferred |
| Workspace data tool pack | [`spec.md`](workspace-data-tool-pack/spec.md) | Implemented v1 baseline | Opt-in JSON-compatible workspace data write/read/search/list/delete registry helpers with required injected store, metadata-first search/list, delete approval flag, exports, and fake tests complete; durable storage, indexing, trace/capability status, and host dirty-state remain caller-owned or deferred |
| Subagent tool pack | [`spec.md`](subagent-tool-pack/spec.md) | Implemented v1 baseline | Opt-in `run_subagent`/`run_subagents` registry helpers with required injected runner, presets, max-child policy, bounded normalized aggregate results, exports, and fake tests complete; the next specified slice is opt-in bounded `ask_llm` with an injected runner, while parallelism, timeout enforcement, trace/capability status, and durable child lifecycle remain deferred |
| Graphify semantic extractor tool | [`spec.md`](graphify-semantic-extractor-tool/spec.md) | First-release plus T7 opt-in implementation complete | Package-owned, registry-mediated extractor plus `graphify-extract`; emits validated staged artifacts through a bounded DAR worker workflow, while stock Graphify curation/promotion remains external; adaptive policy selection remains a deferred follow-on |
| Async session memory pipeline | [`spec.md`](async-session-memory-pipeline/spec.md) | Metadata baseline plus completed handoff | Metadata-only OA8 baseline implemented; live in-memory session behavior is owned by `persistent-agent-sessions`; pruning-context graph-injection work was completed through `context-management-prepare-stage` and `internal-graph-mutation` without expanding OA8 into durable memory |
| Persistent agent sessions | [`spec.md`](persistent-agent-sessions/spec.md) | Implemented v1 baseline | Public `AgentSession`, `AgentSessionState`, `AgentSessionResult`, and `InMemorySessionStore` provide bounded cross-prompt continuity, current-state retrieval, snapshot restart, history policies, same-session concurrency rejection, sync wrapper parity, and live capability/status reporting |
| Collaborative agent sessions | [`spec.md`](collaborative-agent-sessions/spec.md) | Implemented v1 baseline | In-memory `CollaborativeAgentSessionManager`, presets, child state snapshots, spawn/list/get/send/close/current-state APIs, snapshot restart, exports, and fake tests complete; wait/resume, streaming, capability/status, durable storage, and stronger compatibility checks remain deferred |
| Model event streaming | [`spec.md`](model-event-streaming/spec.md) | Implemented v1 session event stream | Public `AgentSession.accept_stream(...)` emits provider-neutral, redacted session events with session/run correlation, terminal final-result authority, terminal `AgentSessionResult`/`WorkflowResult` access, and caller-controlled stream filters; provider-native token deltas, model-tool-loop progress specialization, cancellation/backpressure expansion, and capability/status reporting remain future |
| Context management prepare stage | [`spec.md`](context-management-prepare-stage/spec.md) | Implemented through Slice 10 plus follow-ups | `prepare_model_input(...)` covers hierarchy injection, turn-aware session pruning, lane-budget assembly, selected older turns, file context, retrieved-context lane packing, deterministic basic compaction, rolling summaries, injected model-summary compaction, injected pre/mid-turn compaction seams, new-window reset metadata, overflow classification/retry diagnostics, trace/capability metadata, bounded pruning-context injection, exact/hybrid identifier preservation, and injected semantic older-turn selection; remote compaction and remaining richer profile behavior remain prepared follow-ups |
| Provider-backed context compaction | [`spec.md`](provider-backed-context-compaction/spec.md) | Implemented first slice | Caller-owned typed provider compaction for pre-turn and one-shot overflow retry, explicit capability/fallback policy, validated bounded replacement history, redacted window metadata, and fake-only tests; mid-turn/tool-loop compaction and transport binding remain deferred |
| Model-backed context summaries | [`spec.md`](model-backed-context-summaries/spec.md) | Implemented v1 baseline | Injected `context_summarizer` path for `model_summary` compaction, fail-closed missing summarizer behavior, bounded output, metadata, exports, and fake tests complete; richer prior-summary/provenance and capability/status reporting remain deferred |
| Semantic context profiles | [`spec.md`](semantic-context-profiles/spec.md) | Implemented through Slice S1 | Exact and `hybrid_exact_semantic` older-turn preservation plus injected fake-testable semantic older-turn selection are implemented with metadata and tests; memory-kind hints, stale/redundant omission, RAG lane borrowing, prompt-cache-aware ordering, and selector capability/status reporting remain deferred |
| LLM step interpreter middleware | [`spec.md`](llm-step-interpreter-middleware/spec.md) | Future investigation | Spec captured; backend selection, prototypes, and implementation not started |
| Tool invocation coordinator | [`spec.md`](tool-invocation-coordinator/spec.md) | Implemented | Internal async coordinator unifies direct-step and model-loop approval, lifecycle, tracing, and registry dispatch; the `live-guardrail-execution` tool-input V2 adopter is implemented, while provider, interpreter, and sandbox adopters remain deferred |
| Approval interruption and resume | [`spec.md`](approval-interruption-resume/spec.md) | Implemented v1 baseline | Direct and model-tool-loop approval-required interruption, public pause result, redacted approval traces, high-level API guardrails, capability status, tests, and evidence complete; durable resume remains deferred |
| Hash-chained governance audit | [`spec.md`](hash-chained-governance-audit/spec.md) | Future investigation | Optional caller-sink-backed, tamper-evident governance records with deterministic canonicalization, final-invocation fingerprint binding, compare-and-append semantics, verification, redaction, and required/best-effort failure policy; not implementation authorization |
| Sandbox and workspace runtime | [`spec.md`](sandbox-workspace-runtime/spec.md) | Partial approval-policy and ingress-primitive baseline | Approval-before-side-effect boundary and a host-only descriptor-relative no-follow file-copy primitive are implemented; model-facing write/shell runtime, workspace grants, sandbox adapters, staged commit/rollback, mutation audits, and authored-workflow-runtime-v1 input-artifact integration remain deferred |
| Authored workflow runtime v1 | [`spec.md`](authored-workflow-runtime-v1/spec.md) | Implemented historical capability record | DAR's implemented package-host, configured-MCP, ingress, approval, and execution contract; former `dar-authoring` plugin references are retained only as v1 evidence. |
| Agent-engineering plugin migration | [`spec.md`](agent-engineering-plugin-migration/spec.md) | Transfer complete; successor acceptance accepted | The successor plain-skills plugin owns the complete agent-engineering cohort and the DAR runtime profile. The complete clean-Codex author-then-run acceptance is accepted; this does not authorize publication or source cleanup. |
| MCP OAuth discovery and dynamic registration | [`spec.md`](mcp-oauth-discovery-registration/spec.md) | Implemented through O6; O7 human review pending | Human-only standards-based discovery, loopback-PKCE public-client registration, credential lifecycle, and drift invalidation for a configured HTTPS MCP endpoint; the opt-in Fastmail read-only run awaits human review, and no package/model provisioning, generic transport expansion, or Fastmail-specific behavior is added |
| MCP runtime integration | [`spec.md`](mcp-runtime-integration/spec.md) | Implemented v1 baseline | Explicit caller-supplied MCP registry injection, MCP provenance, conservative policy defaults, capability status, tests, and evidence complete; live transports, process lifecycle, and discovery remain deferred |
| Live guardrail execution | [`spec.md`](live-guardrail-execution/spec.md) | V1 and tool-input V2 implemented | Caller-registered input and validated tool-input pass/abort guardrails, fail-closed missing adapters, redacted traces, and fake-backed direct/model-loop tests are complete; output/tool-output, reject-content, retries, timeouts, and external adapters remain deferred |
| RAG orchestration contract | [`spec.md`](rag-orchestration-contract/spec.md) | Implemented v1 baseline | Expanded declarative `metadata.rag_pipeline` validation and capability/status reporting cover staged RAG metadata, retriever collaborators, provenance and context-management handoff declarations, source readiness, permissions, cache, and degraded states while keeping prompt packing, ingestion, embeddings, indexes, graph stores, rerankers, compressors, evaluators, and retrieval execution outside RAG ownership |
| Memory-aware context pipeline | [`spec.md`](memory-aware-context-pipeline/spec.md) | Proposed; roadmap refinement needed | Proposed passive caller-owned memory-context contract inspired by `memlayer`, with active retrieval kept outside the pipeline, a passive-context handoff first slice, fold-back gate to `rag_pipeline`, schema/enums, collaborator contracts, invocation points, evidence handoff, invariants, trace payloads, and capability/status states without adding runner-owned memory storage, embeddings, provider wrappers, background services, or `memlayer` as a dependency |
| SKILL.md source resolution | [`spec.md`](skill-source-resolution/spec.md) | Implemented v1 baseline | Opt-in package-local bundled `SKILL.md` loading under `skill-bundle/`, policy validation, bounded UTF-8 body loading, deterministic skill-ref injection, redacted provenance, capability/status reporting, and fake-adapter tests complete; external roots, `source_path` reads, support-file loading, network fetching, and caller-owned dynamic selection remain deferred |
| Iterative agent-loop runtime | [`spec.md`](iterative-agent-loop-runtime/spec.md) | Implemented v1 baseline | Bounded opt-in serial model-tool loops execute inside eligible `llm_step` nodes with registry dispatch, approval pauses, fail-closed safety checks, loop traces, tests, and evidence complete; state-field final selectors, durable resume, and multidimensional execution-budget accounting remain deferred |
| Power-Marimo dynamic workflow client | [`spec.md`](power-marimo-host-automation/spec.md) | Downstream boundary evaluated | DAR owns only generic dynamic workflow execution with host-provided tools; `../power-marimo` owns Marimo, Qt, hosted lifecycle, app safety policy, SDK/session behavior, and live validation |

## Completion Matrix

| Capability Area | Owning Spec Package | Implemented Baseline | Remaining / Deferred Work |
| --- | --- | --- | --- |
| Package-directory workflow loading and execution | `dynamic-agent-runner` | Complete through package alignment, async-first execution, tracing, hooks, prompt-cache metadata, portable `tool_type` preservation, and optional caller function-to-tool adaptation | Focused approval-parity evidence for function-adapted tools plus other future scoped expansions |
| OpenAI-compatible provider facade | `openai-compatible-provider-wrapper` | Sync/async provider facade, SDK-backed defaults, ChatGPT/Codex catalog parity, account-header forwarding, package exports, tests, and README example complete | Future provider-specific behavior requires a separate scoped spec or slice |
| Default OpenAI/Codex auth discovery | `default-openai-codex-auth` | Adapter default-provider resolver, `OPENAI_API_KEY` fallback, Codex user-level `config.toml` and ordered API-key/ChatGPT `auth.json` discovery, ChatGPT/Codex backend provider selection, opt-out behavior, redaction, tests, and docs complete | Future support for PAT or agent-identity auth requires a separate provider/base-url/signing spec |
| OpenAI Responses tool-loop compatibility | `openai-responses-tool-loop-compat` | Slice R1 implemented | Streamed Responses function-call preservation, structured tool-loop transcript rendering, ChatGPT/Codex `function_call_output` follow-ups, explicit `tool_choice_policy`, model-facing top-level `tool_results`, docs, and fake tests complete |
| LiteLLM provider adapter | `litellm-provider-adapter` | Upstream dependency adopted; Slice L1 complete | Default direct sync/async Chat Completions transport, request translation, response normalization, public factories, default-provider migration, fake tests, explicit official-SDK compatibility, and shim retirement complete; legacy OCI wheel cleanup and Codex global migration remain deferred |
| llama.cpp local-model adapters | `llama-cpp-local-model` | Local endpoint helpers, direct in-process llama.cpp chat adapters, provider-seam wiring, exports, model-resolution precedence, Hugging Face download wiring, local failure taxonomy, tests, and docs complete | Optional separate local embedding configuration remains later |
| macOS MLX local-model adapters | `mlx-local-model-adapter` | Public adapter helpers, converted-directory and GGUF preflight, injected Hub reference resolution, generation kwargs, conservative capability metadata, identity validation, executor coverage, tests, and docs complete | Embeddings, multimodal IO, streaming public APIs, structured output, model conversion, and MLX server helpers remain deferred; tool calling is owned by the separately planned `mlx-local-model-tool-use` feature |
| Apple Foundation Models adapter | `apple-foundation-model-adapter` | A1–A4 implemented; A2 B5 bridge regression open | Optional SDK metadata, strict-coverage integration, text/JSON Schema generation, Apple callback wrappers, sealed-host profile selection, and schema-preserving gateway fallback are complete. B5 tracks the real SDK bridged-wrapper `Annotated` resolution failure before model generation |
| Model adapter coverage policy | `model-adapter-coverage` | Public API/context argument, executor selection behavior, strict empty-list and nonmatching-adapter failures, augmented default OpenAI coverage, local-only routing removal, tests, and docs complete | Future coverage modes or arbitrary-provider discovery require a separate feature spec; ChatGPT/Codex catalog parity is owned by `openai-compatible-provider-wrapper` |
| Model interface tool-parity tests | `model-interface-parity` | T1.1–T1.6 deterministic matrix and wrapper-local T2 approval interaction delivered | Optional local-model competency remains separate from the no-network parity suite; live positive acceptance is owned by `live-model-interface-acceptance` |
| Live model-interface acceptance | `live-model-interface-acceptance` | Ready for implementation; initial observations recorded | A manually gated behavioral acceptance and receipt contract for real-model S1/S2/S3/S4/S5; malformed/adversarial provider data remains deterministic injected-seam coverage |
| PyInstaller packaging support | `pyinstaller-packaging-support` | Package advertises a PyInstaller hook directory through `pyinstaller40`; the package-owned `hook-openai_model_registry.py` collects `openai_model_registry` data files and copies `openai-model-registry` distribution metadata | Additional dependency hooks, downstream frozen-application builds, and CI PyInstaller packaging are deferred until a concrete caller requires them |
| Compile-time graph mutation | `internal-graph-mutation` | Internal typed mutation datamodel, context-pruning mutation, validation, prepared-input integration, attachment diagnostics, and pruning-context injection for eligible `llm_step` interactions complete | Future structural node insertion, edge rewiring, richer link-level context-management insertion, and public mutation schemas require new approval |
| Public Hugging Face model discovery | `hugging-face-model-search` | Repository-owned search API, normalized result types, error translation, exports, tests, and docs complete | Future richer Hub capabilities require a separate feature spec |
| Shared Hugging Face SDK support | `hugging-face-support-layer` | Internal helper for lazy Hub import, read-only Hub calls, and domain-specific error translation complete | Future Hub behavior beyond search and local-model downloads requires a separate feature spec |
| Local model availability preflight | `local-model-availability-api` | Public explicit-reference preflight API plus narrow cached inventory through Slice A4 complete | Inventory is limited to DAR-owned/default download cache locations and current caller-provided roots; native Hugging Face cache introspection, real metadata integration, and strict exception mode remain deferred |
| Optional local model fit filtering | `llmfit-model-fit-filter` | None | Future optional `llmfit` CLI JSON advisory layer to preserve recommended and unknown models before explicit Hub asset downloads |
| Optional llama.cpp memory fit profiling | `llama-cpp-memory-fit-profile` | Injected-evaluator, fail-open profiling for resolved local GGUF assets complete | Concrete llama.cpp command integration, metadata probing, automatic budget discovery, caching, GPU/offload recommendations, and execution gating remain deferred |
| Capability/status reporting | `capability-status-report` | Public report contract, package inspection, metadata-only declarations, model adapter coverage, tool registry coverage, built-in tool-pack status, invalid package reporting, tests, and completion evidence complete | Future CLI rendering and additional collaborator types remain deferred until there is a concrete caller |
| Host workflow integration | `host-workflow-integration` | Host-owned tool bindings, model-facing aliases, collision checks, bounded redacted diagnostics, resolved model selection helper, inline/generated and loaded-workflow preflight, host id capability-report details, lifecycle docs, exports, and tests complete | Future work only if another host integration gap appears |
| Tool descriptor budgeting | `tool-descriptor-budgeting` | Slice T1 implemented | Opt-in runtime/node policy validation, deterministic registry-exposed tool ranking, OpenAI-compatible descriptor token/count packing, required-tool enforcement, executor integration, redacted diagnostics, and fake tests complete; NLTK evaluation remains a benchmarked optional experiment |
| Web tool pack | `web-tool-pack` | Opt-in `web_search`/`web_fetch` registry pack with injected fake-testable clients, bounded normalized results, URL scheme/domain policy, exports, and tests complete | Redirect/timeouts/local-network policy, trace redaction, capability/status reporting, provider adapters, and extraction/readability remain deferred |
| Workspace data tool pack | `workspace-data-tool-pack` | Opt-in JSON-compatible write/read/search/list/delete registry pack with injected store, metadata-first search/list, delete approval flag, exports, and tests complete | Durable storage, indexing, trace/capability reporting, and host dirty-state remain caller-owned or deferred |
| Subagent tool pack | `subagent-tool-pack` | Opt-in `run_subagent`/`run_subagents` registry pack with injected runner, presets, max-child policy, normalized aggregate results, exports, and tests complete | Next: opt-in bounded `ask_llm` with an injected runner and caller-owned presets; parallel execution, timeout/iteration budgets, trace/capability reporting, recursive-spawn policy, and durable child lifecycle remain deferred |
| Graphify semantic extractor tool | `graphify-semantic-extractor-tool` | First-release plus T7 opt-in implementation complete | Follow-up work may add richer Graphify schema coverage, adaptive policy selection, or an explicit endpoint; the current package validates a curated corpus manifest, runs bounded parallel extraction through DAR, emits staged artifacts, and leaves Graphify build/curation/promotion in the stock workflow |
| Async session metadata | `async-session-memory-pipeline` | `runtime.execution_policy.async_session` metadata preservation and fail-closed validation complete | Durable external storage, broader memory replay, and summary generation are deferred; live in-memory sessions are owned by `persistent-agent-sessions`; pruning-context graph injection is complete through `context-management-prepare-stage` plus `internal-graph-mutation` |
| Persistent agent sessions | `persistent-agent-sessions` | Public `AgentSession` and `InMemorySessionStore` v1 complete with state snapshots, bounded `accept(...)`, history policies, session-id state injection, snapshot restart, same-session concurrency rejection, sync wrapper parity, and capability/status reporting | Optional structured snapshot summary metadata remains a future caller-owned schema extension; durable external stores, model-backed summaries, FTS/search archives, long-running graph executors, raw tool transcript replay, durable approval resume, and cross-process locking remain deferred |
| Collaborative agent sessions | `collaborative-agent-sessions` | In-memory parent/child session manager, presets, child state snapshots, spawn/list/get/send/close/current-state APIs, snapshot restart, exports, and tests complete | Wait/resume APIs, child event streaming, capability/status reporting, durable storage, compatibility validation, and explicit tool-policy enforcement remain deferred |
| Model event streaming | `model-event-streaming` | Session-level `AgentSession.accept_stream(...)` event stream complete with redacted execution events, session/run correlation, terminal final-result authority, terminal `AgentSessionResult`/`WorkflowResult` access, and caller-controlled stream filters | Provider-native token deltas, model-tool-loop progress specialization, cancellation/backpressure expansion, lower-level executor stream APIs, and streaming capability/status reporting remain deferred |
| Context-management prepare stage | `context-management-prepare-stage` | `prepare_model_input(...)` support exists for hierarchy injection, turn-aware current-run session pruning, lane-budget assembly, named compression profiles, deterministic and exact/hybrid older-turn selection, injected semantic older-turn selection, rolling summaries, injected model summaries, retrieved-context lane packing for RAG evidence, deterministic basic compaction, pre/mid-turn compaction seams, explicit reset metadata, overflow classification/retry diagnostics, capability status, trace metadata, and bounded pruning-context injection from supplied session messages | Derived `artifact_trail` diagnostics plus probe-based compression and degradation fixtures remain follow-up validation work; provider-backed remote compaction and remaining richer profile behavior remain prepared follow-ups; built-in embeddings/vector retrieval and runner-owned durable memory remain out of scope |
| Provider-backed context compaction | `provider-backed-context-compaction` | Implemented first slice | Caller-owned typed pre-turn/overflow-retry compaction with capability gating, replacement validation, redacted window metadata, fallback policy, and capability/status reporting; mid-turn/tool-loop behavior and transport binding remain deferred |
| Model-backed context summaries | `model-backed-context-summaries` | Injected summarizer collaborator path for `model_summary` compaction with fail-closed missing summarizer behavior, bounded output metadata, and fake tests complete | Richer prior-summary folding, source/file/tool provenance diagnostics, fallback ordering, and capability/status reporting remain deferred |
| Semantic context profiles | `semantic-context-profiles` | Exact and `hybrid_exact_semantic` older-turn selection preserve issue keys, filenames, and identifiers; Slice S1 adds caller-injected semantic scoring, missing-selector fallback diagnostics, direct/context collaborator threading, public selector contracts, and RAG lane separation with tests | Memory-kind hints, stale/redundant omission, RAG lane borrowing, prompt-cache-aware ordering, and selector capability/status reporting remain deferred |
| Interpreter middleware | `llm-step-interpreter-middleware` | Future feature spec and candidate interface expectations captured | Dependency checks, prototypes, benchmark evidence, backend selection, and implementation |
| Tool invocation coordinator | `tool-invocation-coordinator` | Shared direct/model coordinator complete | Approval-required input validation before approval, lifecycle, tracing, and registry dispatch now share one internal path; `live-guardrail-execution` tool-input V2 adoption is implemented, while provider, interpreter, and sandbox adoption remain deferred |
| Sandbox/workspace runtime | `sandbox-workspace-runtime` | Metadata-only `sandbox_runtime` preservation, approval-before-side-effect boundary, and host-only descriptor-relative no-follow file-copy primitive complete | Model-facing write tools, shell tools, workspace grants, sandbox adapters, staged commit/rollback, changed-path audits, and authored-workflow-runtime-v1 trusted input-artifact integration remain deferred |
| Authored workflow runtime v1 | `authored-workflow-runtime-v1` | Implemented historical capability record | Durable v1 DAR host/runtime contract and deterministic capability evidence; it does not revive the retired plugin. |
| Agent-engineering plugin migration | `agent-engineering-plugin-migration` | Transfer complete; successor acceptance accepted | Successor plain-skills plugin with complete moved guidance and a supplemental DAR runtime profile. The full clean-Codex author-then-run acceptance is accepted; publication and source cleanup remain separate decisions. |
| MCP OAuth discovery and dynamic registration | `mcp-oauth-discovery-registration` | Implemented through O6; O7 human review pending | Human-only protected-resource/authorization-server discovery, dynamic loopback-PKCE public-client registration, refresh/drift handling, and redacted evidence for configured HTTPS MCP endpoints; packages and skills retain no provisioning authority |
| Approval interruption/resume | `approval-interruption-resume` | Public interruption contract, direct and model-tool-loop approval-required pause, no-side-effect-before-approval behavior, redacted approval traces, high-level API guardrails, capability status, tests, and evidence complete | Durable resume, approval decisions, argument modification, parallel approvals, and serialized resume state remain deferred |
| Tamper-evident governance audit | `hash-chained-governance-audit` | None; future specification only | First release would define canonical governance records, caller-supplied append/verify collaborators, final-invocation fingerprints, mutation detection, redaction, and audit-failure policy; signatures, external anchors, remote stores, and compliance exports remain deferred |
| MCP runtime integration | `mcp-runtime-integration` | Metadata-only MCP registry-source and lifecycle diagnostics preservation plus explicit caller-supplied MCP registry injection complete | Live server discovery, process lifecycle, transports, reconnect, schema cache, and diagnostics beyond metadata remain deferred |
| Live guardrail execution | `live-guardrail-execution` | Caller-registered input and tool-input guardrail aborts complete | Validated direct and model-loop tool-input pass/abort checks run through the shared coordinator; output guardrails, tool-output, reject-content, retries, timeouts, and external adapters remain deferred |
| RAG orchestration contract | `rag-orchestration-contract` | Expanded `metadata.rag_pipeline` validation and capability/status reporting exist for staged retrievers, required collaborators, provenance and context-management handoff declarations, source readiness, permissions, cache, and degraded states | Retrieval infrastructure, prompt packing, ingestion, embeddings, indexes, graph stores, rerankers, compressors, evaluators, answer citation rendering, output guardrails, and live retrieval orchestration remain deferred |
| Memory-aware context pipeline | `memory-aware-context-pipeline` | None | Future declarative memory pipeline validation, capability/status reporting, fake-testable memory retrieval tiers, provenance, trace events, retrieved-context handoff, no-implicit-save enforcement, and a first-slice decision on whether distinct memory semantics justify remaining separate from RAG; salience and ingestion execution remain future/deferred |
| SKILL.md source resolution | `skill-source-resolution` | Opt-in package-local bundled `SKILL.md` loading, policy validation, bounded UTF-8 body loading, deterministic prompt injection, redacted provenance, and capability/status reporting complete | Token-aware skill-source budgets, `max_skills_per_turn`, and `overflow_behavior: error` diagnostics remain follow-up work; external roots, `source_path` reads, support-file prompt loading, network fetching, Markdown frontmatter parsing, raw-body debugging, and caller-owned dynamic selection remain deferred |
| Iterative agent-loop runtime | `iterative-agent-loop-runtime` | Bounded opt-in serial model-tool loop execution complete for eligible `llm_step` nodes | Loop `state_field`/`tool_result` final selectors, durable approval resume, output/tool guardrails, parallel tool calls, durable transcripts, and multidimensional estimated/reserved/actual budget accounting remain deferred |
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

The
[`AI-Agents-Projects-Tutorials`](https://github.com/MARKTECHPOST-AI-MEDIA-INC/AI-Agents-Projects-Tutorials)
repository, attributed by its README and canonical Git remote to MarkTechPost /
`MARKTECHPOST-AI-MEDIA-INC`, was evaluated as a broad educational corpus of
agent implementations and notebooks. It is design evidence, not a DAR runtime
dependency or implementation authority. The review used its OpenHarness,
governance, memory-engineering, cost-aware planning, agentic UI, MCP/OAuth,
A2A/ACP, guardrail, and tracing examples and produced these scoped updates:

- approval must bind the final normalized invocation after every
  policy-relevant transformation; post-approval mutation requires
  reauthorization
- tool guardrails remain separate from registry invocation and cannot dispatch
  handlers directly
- caller-supplied memory evidence may carry memory kind, salience, novelty,
  usage, and outcome signals without making DAR a memory store
- repair/self-check loops must share enclosing iteration, token, time, and cost
  limits
- replayable event contracts need stable ids and deduplication semantics, while
  UI transports remain downstream concerns
- live MCP authorization must validate resource/audience and scopes, and
  cancellation claims must reflect negotiated capabilities
- the tutorial governance record shape motivated the separate future
  [`hash-chained-governance-audit`](hash-chained-governance-audit/spec.md) spec

The corpus contains tutorial-oriented runtime installs, notebook magics,
dynamic execution, direct handler dispatch, incomplete protocol handling, and
stored notebook outputs. Those examples must not be copied as production safety
or reproducibility patterns.

The follow-up notebook review placed the remaining useful patterns under
existing owners instead of creating duplicate feature areas:

- contract-first decision invariants extend approval, guardrail, and governance
  record validation
- deterministic adversarial tool and leakage fixtures extend the owning safety
  specs' validation matrices; model judges remain optional annotations
- multidimensional estimated/reserved/actual accounting remains a future
  `iterative-agent-loop-runtime` slice, while planning optimization stays
  caller-owned
- staged validate/approve/commit/rollback semantics and canonical path
  containment extend `sandbox-workspace-runtime`
- procedural skill scores and outcomes remain caller-owned inputs to a future
  selector extension under `skill-source-resolution`; DAR does not learn or
  rewrite skills automatically

The
[`sickn33/antigravity-awesome-skills`](https://github.com/sickn33/antigravity-awesome-skills)
repository was evaluated as context-management and skill-loading design
evidence, with local Graphify review artifacts at
`/private/tmp/antigravity-awesome-skills-docs-graph/graphify-out/` and
`/private/tmp/antigravity-awesome-skills-focused-graph/graphify-out/`. Useful
ideas were folded into existing DAR spec owners rather than becoming a new
feature area:

- `skills/context-compression/SKILL.md` informs `context-management-prepare-stage`
  requirements for tokens-per-task thinking, probe-based compression tests, and
  first-class artifact-trail diagnostics.
- `skills/context-degradation/SKILL.md` informs context-management validation
  fixtures for lost-in-middle, poisoning, distraction, confusion, and clash.
- `docs/users/discovery-manifest.md`,
  `docs/integrations/jetski-cortex.md`, and
  `docs/users/agent-overload-recovery.md` inform `skill-source-resolution`
  requirements for manifest-based lazy loading, per-turn limits, token-aware
  budgets, and explicit overflow diagnostics.
- `skills/context-agent/SKILL.md` and
  `skills/context-agent/references/context-format.md` inform
  `persistent-agent-sessions` snapshot-summary shape for intent, decisions,
  pending tasks, modified files, blockers, next action, and metrics.

DAR does not adopt the Antigravity repository's activation scripts, global skill
directory management, full skill-library prompt injection, session archive,
SQLite FTS search, or durable memory implementation. Those remain caller-owned
or outside the runtime boundary.

Rodrigo Girao Serrao's
[`Write a coding agent from first principles`](https://mathspp.com/blog/write-a-coding-agent-from-first-principles)
was evaluated as a compact coding-agent substrate reference. Useful ideas were
folded into existing DAR spec owners instead of creating a new feature area:

- Source-file mutation and verification commands extend
  [`sandbox-workspace-runtime`](sandbox-workspace-runtime/spec.md): start with
  path-granted `write_file` plus `replace_text` or `insert_lines`, changed-path
  audits, and allowlisted `run_tests` or `run_linter`; keep arbitrary shell as a
  later high-risk capability.
- Provider-native tool-use blocks, immediate tool-result follow-ups, recoverable
  tool errors, and repair attempts extend
  [`iterative-agent-loop-runtime`](iterative-agent-loop-runtime/spec.md) without
  making loops unbounded.
- Large file, command, and structured tool outputs extend
  [`scratchpad-context-manager`](scratchpad-context-manager/spec.md) through the
  existing post-tool offload boundary.
- Visible tool progress extends
  [`model-event-streaming`](model-event-streaming/spec.md), while UI transports
  and terminal styling remain downstream concerns.
- Context clearing, trimming, import, and export extend
  [`persistent-agent-sessions`](persistent-agent-sessions/spec.md) and
  [`context-management-prepare-stage`](context-management-prepare-stage/spec.md)
  rather than creating a separate command layer in DAR.

DAR does not adopt the tutorial's text-parsed tool-call protocol, broad
`bash(command)` surface, full-file writes as the preferred edit primitive, or
interactive command prompt as a production approval boundary. A future
`coding-workspace-tool-pack` spec is only a possible split if the model-facing
tool-pack contract outgrows `sandbox-workspace-runtime`; it would depend on the
sandbox and approval specs and must not own grants, approval binding, backend
isolation, or resource enforcement.

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

Sana Hassan's ["Build a Nanobot-Style AI Agent in Google Colab with Tool
Calling, Session Memory, Skills, and MCP
Servers"](https://www.marktechpost.com/2026/06/26/build-a-nanobot-style-ai-agent-in-google-colab-with-tool-calling-session-memory-skills-and-mcp-servers/)
(MarkTechPost, June 26, 2026) and its linked tutorial notebook were evaluated as
a compact educational agent-loop reference. The reference is supporting design
evidence, not an implementation authority:

- Its normalized provider response and deterministic mock provider reinforce
  DAR's existing model-adapter boundary and fake-adapter unit-test strategy.
- Its callable-to-tool decorator motivates an optional
  `tool_from_function(...)` authoring convenience around the repository-owned
  tool registry. Inference must remain conservative, explicit metadata must win,
  and the resulting tool must traverse normal validation, approval, tracing,
  retry, and result-shaping behavior.
- Its compact skill descriptor reinforces separating descriptive capability
  metadata from runtime activation. DAR rejects the tutorial's process-global
  prompt and registry mutation as a workflow or session isolation model.
- Its lifecycle hook demonstrates useful observation points but not an approval
  boundary. Hooks must not silently authorize actions, and tool-call origin must
  not bypass DAR's approval stack.
- Its in-process `MCPServer` facade is an adapter example, not evidence of MCP
  transport, discovery, protocol, or lifecycle support.
- Its per-session history illustrates isolation by session key, but DAR does not
  adopt its lossy tool-transcript handling, process-local persistence
  assumptions, or unrestricted code-execution examples.

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
