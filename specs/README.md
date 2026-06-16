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

## Feature Specs

| Feature | Spec | Status | Completion |
| --- | --- | --- | --- |
| OpenAI-compatible provider wrapper | [`spec.md`](openai-compatible-provider-wrapper/spec.md) | Implemented | Slices 1-6 complete; optional compatibility polish only |
| Default OpenAI/Codex auth discovery | [`spec.md`](default-openai-codex-auth/spec.md) | Implemented | Adapter-owned default OpenAI/Codex auth discovery, ordered Codex API-key/ChatGPT auth selection, caller precedence, unsupported-auth handling, opt-out behavior, tests, and docs complete |
| llama.cpp local-model adapter | [`spec.md`](llama-cpp-local-model/spec.md) | Implemented | Slices 1-3 complete; direct in-process llama.cpp chat, endpoint helpers, local asset resolution, tests, and docs complete; optional embedding follow-up unscheduled |
| macOS MLX local-model adapter | [`spec.md`](mlx-local-model-adapter/spec.md) | Implemented | Public macOS-only in-process MLX adapter helpers, local path/Hub resolution, identity validation, executor coverage, tests, and docs complete |
| Model adapter coverage policy | [`spec.md`](model-adapter-coverage/spec.md) | Implemented | Public `model_adapter_coverage` policy, strict supplied-adapter failures, augmented default OpenAI coverage, local-only routing removal, tests, and docs complete |
| Internal graph mutation | [`spec.md`](internal-graph-mutation/spec.md) | Checkpoint complete | T3.2 complete for internal typed mutation, context-pruning attachment, validation, prepared-input integration, and diagnostics; future structural insertion, edge rewiring, link-level operations, and public schemas require a new approved slice |
| Hugging Face model search | [`spec.md`](hugging-face-model-search/spec.md) | Implemented | Public Hub discovery API, result contract, error translation, exports, tests, and docs complete |
| Hugging Face support layer | [`spec.md`](hugging-face-support-layer/spec.md) | Implemented | Internal shared Hub import/call/error mechanics, search routing, local download routing, tests, and validation complete |
| llmfit model-fit filter | [`spec.md`](llmfit-model-fit-filter/spec.md) | Future optional advisory feature | Proposed optional `llmfit`-on-`PATH` pre-download filter; keep recommended plus unknown models without bundling or installing llmfit |
| llama.cpp memory fit profile | [`spec.md`](llama-cpp-memory-fit-profile/spec.md) | Implemented v1 baseline | Optional post-resolution GGUF memory-fit profiler with injected evaluators, fail-open advisory results, strict-mode errors, deterministic fit math, suggested `n_ctx`, tests, and evidence complete |
| Capability status report | [`spec.md`](capability-status-report/spec.md) | Implemented | Public preflight report distinguishes live, metadata-only, missing-collaborator, disabled, and invalid runtime capabilities; CLI rendering and future collaborator types remain deferred |
| Async session memory pipeline | [`spec.md`](async-session-memory-pipeline/spec.md) | Metadata baseline plus future analysis | Metadata-only OA8 baseline implemented; no runner-owned session behavior |
| Context management prepare stage | [`spec.md`](context-management-prepare-stage/spec.md) | Implemented baseline plus future plan | Current `prepare_model_input(...)` baseline covers hierarchy injection, bounded session pruning, compact summaries, file context, and diagnostics; future work is specified for turn-aware lane assembly, named compression profiles, rolling summaries, deterministic and semantic selection, automatic compaction, and graph-mutation attachment/insertion boundaries |
| LLM step interpreter middleware | [`spec.md`](llm-step-interpreter-middleware/spec.md) | Future investigation | Spec captured; backend selection, prototypes, and implementation not started |
| Approval interruption and resume | [`spec.md`](approval-interruption-resume/spec.md) | Implemented v1 baseline | Direct approval-required `tool_use_step` interruption, public pause result, redacted approval traces, high-level API guardrails, capability status, tests, and evidence complete; durable resume remains deferred |
| Sandbox and workspace runtime | [`spec.md`](sandbox-workspace-runtime/spec.md) | Partial approval-policy baseline | Approval-before-side-effect boundary is implemented through approval interruption v1; write/shell runtime, workspace grants, sandbox adapters, and mutation audits remain deferred |
| MCP runtime integration | [`spec.md`](mcp-runtime-integration/spec.md) | Implemented v1 baseline | Explicit caller-supplied MCP registry injection, MCP provenance, conservative policy defaults, capability status, tests, and evidence complete; live transports, process lifecycle, and discovery remain deferred |
| Live guardrail execution | [`spec.md`](live-guardrail-execution/spec.md) | Implemented v1 baseline | Caller-registered input guardrail pass/abort, fail-closed missing adapters, redacted traces, capability status, tests, and evidence complete; output/tool phases remain deferred |
| RAG orchestration contract | [`spec.md`](rag-orchestration-contract/spec.md) | Future orchestration feature | Defines direct support for RAG metadata, orchestration modes, typed query/answer states, validation, capability/status, provenance, context assembly, guardrail/evaluation hooks, and primitive-node workflow patterns while keeping ingestion, embeddings, indexes, graph stores, rerankers, compressors, and evaluators caller-owned |
| SKILL.md source resolution | [`spec.md`](skill-source-resolution/spec.md) | Future source-loading feature | Skill metadata and refs exist; arbitrary source loading not implemented |
| Iterative agent-loop runtime | [`spec.md`](iterative-agent-loop-runtime/spec.md) | Implemented v1 baseline | Bounded opt-in serial model-tool loops execute inside eligible `llm_step` nodes with registry dispatch, approval pauses, fail-closed safety checks, loop traces, tests, and evidence complete; state-field final selectors and durable resume remain deferred |
| Power-Marimo host automation | [`spec.md`](power-marimo-host-automation/spec.md) | Future downstream integration | Placeholder-safe fixture exists; live Marimo/PyQt automation not implemented |

## Completion Matrix

| Capability Area | Owning Spec Package | Implemented Baseline | Remaining / Deferred Work |
| --- | --- | --- | --- |
| Package-directory workflow loading and execution | `dynamic-agent-runner` | Complete through package alignment, async-first execution, tracing, hooks, prompt-cache metadata, and portable `tool_type` preservation | Future scoped expansions only |
| OpenAI-compatible provider facade | `openai-compatible-provider-wrapper` | Sync/async provider facade, provider config, SDK-backed defaults, package exports, and README example complete | Optional compatibility polish for provider-specific behavior |
| Default OpenAI/Codex auth discovery | `default-openai-codex-auth` | Adapter default-provider resolver, `OPENAI_API_KEY` fallback, Codex user-level `config.toml` and ordered API-key/ChatGPT `auth.json` discovery, ChatGPT/Codex backend provider selection, opt-out behavior, redaction, tests, and docs complete | Future support for PAT or agent-identity auth requires a separate provider/base-url/signing spec |
| llama.cpp local-model adapters | `llama-cpp-local-model` | Local endpoint helpers, direct in-process llama.cpp chat adapters, provider-seam wiring, exports, model-resolution precedence, Hugging Face download wiring, local failure taxonomy, tests, and docs complete | Optional separate local embedding configuration remains later |
| macOS MLX local-model adapters | `mlx-local-model-adapter` | Public adapter helpers, converted-directory preflight, injected Hub reference resolution, identity validation, executor coverage, tests, and docs complete | GGUF, embeddings, multimodal, streaming, tool calling, structured output, model conversion, and MLX server helpers remain deferred |
| Model adapter coverage policy | `model-adapter-coverage` | Public API/context argument, executor selection behavior, strict empty-list and nonmatching-adapter failures, augmented default OpenAI coverage, local-only routing removal, tests, and docs complete | Future coverage modes or provider discovery require a separate feature spec |
| Compile-time graph mutation | `internal-graph-mutation` | Internal typed mutation datamodel, context-pruning mutation, validation, prepared-input integration, and diagnostics complete | Future structural node insertion, edge rewiring, link-level context-management insertion, and public mutation schemas require new approval |
| Public Hugging Face model discovery | `hugging-face-model-search` | Repository-owned search API, normalized result types, error translation, exports, tests, and docs complete | Future richer Hub capabilities require a separate feature spec |
| Shared Hugging Face SDK support | `hugging-face-support-layer` | Internal helper for lazy Hub import, read-only Hub calls, and domain-specific error translation complete | Future Hub behavior beyond search and local-model downloads requires a separate feature spec |
| Optional local model fit filtering | `llmfit-model-fit-filter` | None | Future optional `llmfit` CLI JSON advisory layer to preserve recommended and unknown models before explicit Hub asset downloads |
| Optional llama.cpp memory fit profiling | `llama-cpp-memory-fit-profile` | Injected-evaluator, fail-open profiling for resolved local GGUF assets complete | Concrete llama.cpp command integration, metadata probing, automatic budget discovery, caching, GPU/offload recommendations, and execution gating remain deferred |
| Capability/status reporting | `capability-status-report` | Public report contract, package inspection, metadata-only declarations, model adapter coverage, tool registry coverage, built-in tool-pack status, invalid package reporting, tests, and completion evidence complete | Future CLI rendering and additional collaborator types remain deferred until there is a concrete caller |
| Async session metadata | `async-session-memory-pipeline` | `runtime.execution_policy.async_session` metadata preservation and fail-closed validation complete | Runner-owned durable storage, replay, and summary generation are deferred; live prompt shaping is owned by `context-management-prepare-stage` |
| Context-management prepare stage | `context-management-prepare-stage` | Baseline `prepare_model_input(...)` support exists for hierarchy injection, bounded current-run session pruning, compact summary insertion, file-context injection, and trace metadata | Future implementation slices cover turn units, lane budgets, required/optional lanes, compression profiles (`balanced`, `fast`, `exact`, `semantic`, `recency_weighted`, `instruction_weighted`), deterministic older-turn selection, rolling summaries, provider compaction, pre/mid-turn triggers, overflow classification, and graph-mutation attachment/insertion |
| Interpreter middleware | `llm-step-interpreter-middleware` | Future feature spec and candidate interface expectations captured | Dependency checks, prototypes, benchmark evidence, backend selection, and implementation |
| Sandbox/workspace runtime | `sandbox-workspace-runtime` | Metadata-only `sandbox_runtime` preservation plus approval-before-side-effect boundary complete | Write tools, shell tools, workspace grants, sandbox adapters, and changed-path audits remain deferred |
| Approval interruption/resume | `approval-interruption-resume` | Public interruption contract, direct approval-required tool pause, no-side-effect-before-approval behavior, redacted approval traces, high-level API guardrails, capability status, tests, and evidence complete | Durable resume, approval decisions, model-emitted tool-call approval, argument modification, parallel approvals, and serialized resume state remain deferred |
| MCP runtime integration | `mcp-runtime-integration` | Metadata-only MCP registry-source and lifecycle diagnostics preservation plus explicit caller-supplied MCP registry injection complete | Live server discovery, process lifecycle, transports, reconnect, schema cache, and diagnostics beyond metadata remain deferred |
| Live guardrail execution | `live-guardrail-execution` | Metadata-only guardrail declaration preservation plus caller-registered input guardrail aborts before first runtime action complete | Output guardrails, tool guardrails, reject-content behavior, retries, timeouts, and external adapters remain deferred |
| RAG orchestration contract | `rag-orchestration-contract` | Limited `metadata.rag_pipeline` validation exists in the primary runtime | Future RAG contract slices should add stage-level RAG metadata, retrieval orchestration modes, typed query/answer contracts, capability/status reporting, provenance-aware retrieved-context contracts, context-management integration, guardrail/evaluation hooks, and examples without owning retrieval infrastructure |
| SKILL.md source resolution | `skill-source-resolution` | Package-local skill metadata and `skill_refs` preservation complete | Source loading, trust, precedence, and prompt injection are specified as future work |
| Iterative agent-loop runtime | `iterative-agent-loop-runtime` | Bounded opt-in serial model-tool loop execution complete for eligible `llm_step` nodes | Loop `state_field`/`tool_result` final selectors, durable approval resume, output/tool guardrails, parallel tool calls, and durable transcripts remain deferred |
| Power-Marimo host automation | `power-marimo-host-automation` | Placeholder-safe fixture and fake-tool execution coverage complete | Live Marimo-session tools, domain adapters, PyQt-widget automation, and host safety policy are specified as future work |

## Reading Order

1. Start with the primary [`dynamic-agent-runner/spec.md`](dynamic-agent-runner/spec.md).
2. Read [`dynamic-agent-runner/tasks.md`](dynamic-agent-runner/tasks.md) for the
   implementation history and feature roadmap index.
3. For OpenAI adapter default-auth discovery behavior, read
   [`default-openai-codex-auth/spec.md`](default-openai-codex-auth/spec.md),
   with completion evidence in
   [`default-openai-codex-auth/tasks.md`](default-openai-codex-auth/tasks.md).
4. Read a feature package when working in that specific area; each feature spec
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
  context-management policy inputs without creating runner-owned durable
  storage.
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

## High-ROI Remaining Work Order

The June 2026 council review plus the remaining-spec evaluation recommends this
dependency order. This is roadmap memory, not implementation authorization; each
item still needs a scoped plan and task slice before code changes begin.

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
8. Next: add opt-in package-local `skill-source-resolution`.
9. Implement additional local-model advisory features only when local-model
   ergonomics is the immediate driver: `llmfit-model-fit-filter` for
   pre-download filtering, plus any concrete llama.cpp command or metadata
   probing beyond the completed injected-evaluator
   `llama-cpp-memory-fit-profile` v1 baseline.
10. Add `power-marimo-host-automation` after approval/sandbox and host-managed
    continuity boundaries are clear.
11. Keep `async-session-memory-pipeline` host-managed in v1; add runner-owned
    durable session storage only after a concrete workflow proves the need.
12. Defer `llm-step-interpreter-middleware` until sandbox, approval, guardrails,
    tracing, redaction, and capability reporting are stable.

Clean dependency chain:

```text
status visibility
→ approval/sandbox mutation policy
→ MCP/guardrails
→ loops/skills
→ host integrations
→ durable memory
→ interpreter
```
