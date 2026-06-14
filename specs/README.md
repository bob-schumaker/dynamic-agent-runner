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
| Internal graph mutation | [`spec.md`](internal-graph-mutation/spec.md) | Checkpoint complete | T3.2 complete; no additional tasks scheduled |
| Hugging Face model search | [`spec.md`](hugging-face-model-search/spec.md) | Implemented | Public Hub discovery API, result contract, error translation, exports, tests, and docs complete |
| Hugging Face support layer | [`spec.md`](hugging-face-support-layer/spec.md) | Implemented | Internal shared Hub import/call/error mechanics, search routing, local download routing, tests, and validation complete |
| llmfit model-fit filter | [`spec.md`](llmfit-model-fit-filter/spec.md) | Future optional advisory feature | Proposed optional `llmfit`-on-`PATH` pre-download filter; keep recommended plus unknown models without bundling or installing llmfit |
| llama.cpp memory fit profile | [`spec.md`](llama-cpp-memory-fit-profile/spec.md) | Future optional advisory feature | Proposed optional post-resolution memory-fit profiler for concrete local GGUF assets; estimate safe context without changing adapter execution |
| Capability status report | [`spec.md`](capability-status-report/spec.md) | Implemented | Public preflight report distinguishes live, metadata-only, missing-collaborator, disabled, and invalid runtime capabilities; CLI rendering and future collaborator types remain deferred |
| Async session memory pipeline | [`spec.md`](async-session-memory-pipeline/spec.md) | Metadata baseline plus future analysis | Metadata-only OA8 baseline implemented; no runner-owned session behavior |
| LLM step interpreter middleware | [`spec.md`](llm-step-interpreter-middleware/spec.md) | Future investigation | Spec captured; backend selection, prototypes, and implementation not started |
| Approval interruption and resume | [`spec.md`](approval-interruption-resume/spec.md) | Implemented v1 baseline | Direct approval-required `tool_use_step` interruption, public pause result, redacted approval traces, high-level API guardrails, capability status, tests, and evidence complete; durable resume remains deferred |
| Sandbox and workspace runtime | [`spec.md`](sandbox-workspace-runtime/spec.md) | Partial approval-policy baseline | Approval-before-side-effect boundary is implemented through approval interruption v1; write/shell runtime, workspace grants, sandbox adapters, and mutation audits remain deferred |
| MCP runtime integration | [`spec.md`](mcp-runtime-integration/spec.md) | Implemented v1 baseline | Explicit caller-supplied MCP registry injection, MCP provenance, conservative policy defaults, capability status, tests, and evidence complete; live transports, process lifecycle, and discovery remain deferred |
| Live guardrail execution | [`spec.md`](live-guardrail-execution/spec.md) | Future live-runtime feature | Guardrail metadata baseline exists; live enforcement not implemented |
| SKILL.md source resolution | [`spec.md`](skill-source-resolution/spec.md) | Future source-loading feature | Skill metadata and refs exist; arbitrary source loading not implemented |
| Iterative agent-loop runtime | [`spec.md`](iterative-agent-loop-runtime/spec.md) | Future live-runtime feature | Tool-use completion metadata exists; live iterative loop not implemented |
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
| Compile-time graph mutation | `internal-graph-mutation` | Internal typed mutation datamodel, context-pruning mutation, validation, prepared-input integration, and diagnostics complete | Future structural graph surgery or public mutation schema require new approval |
| Public Hugging Face model discovery | `hugging-face-model-search` | Repository-owned search API, normalized result types, error translation, exports, tests, and docs complete | Future richer Hub capabilities require a separate feature spec |
| Shared Hugging Face SDK support | `hugging-face-support-layer` | Internal helper for lazy Hub import, read-only Hub calls, and domain-specific error translation complete | Future Hub behavior beyond search and local-model downloads requires a separate feature spec |
| Optional local model fit filtering | `llmfit-model-fit-filter` | None | Future optional `llmfit` CLI JSON advisory layer to preserve recommended and unknown models before explicit Hub asset downloads |
| Optional llama.cpp memory fit profiling | `llama-cpp-memory-fit-profile` | None | Future optional profiler for resolved local GGUF assets to estimate resident memory, context growth, supported context tiers, and suggested effective context |
| Capability/status reporting | `capability-status-report` | Public report contract, package inspection, metadata-only declarations, model adapter coverage, tool registry coverage, built-in tool-pack status, invalid package reporting, tests, and completion evidence complete | Future CLI rendering and additional collaborator types remain deferred until there is a concrete caller |
| Async session metadata | `async-session-memory-pipeline` | `runtime.execution_policy.async_session` metadata preservation and fail-closed validation complete | Runner-owned durable storage, replay, summary generation, and pruning are deferred |
| Interpreter middleware | `llm-step-interpreter-middleware` | Future feature spec and candidate interface expectations captured | Dependency checks, prototypes, benchmark evidence, backend selection, and implementation |
| Sandbox/workspace runtime | `sandbox-workspace-runtime` | Metadata-only `sandbox_runtime` preservation plus approval-before-side-effect boundary complete | Write tools, shell tools, workspace grants, sandbox adapters, and changed-path audits remain deferred |
| Approval interruption/resume | `approval-interruption-resume` | Public interruption contract, direct approval-required tool pause, no-side-effect-before-approval behavior, redacted approval traces, high-level API guardrails, capability status, tests, and evidence complete | Durable resume, approval decisions, model-emitted tool-call approval, argument modification, parallel approvals, and serialized resume state remain deferred |
| MCP runtime integration | `mcp-runtime-integration` | Metadata-only MCP registry-source and lifecycle diagnostics preservation plus explicit caller-supplied MCP registry injection complete | Live server discovery, process lifecycle, transports, reconnect, schema cache, and diagnostics beyond metadata remain deferred |
| Live guardrail execution | `live-guardrail-execution` | Metadata-only guardrail declaration preservation complete | Guardrail adapters, phase execution, abort/reject behavior, and redaction are specified as future work |
| SKILL.md source resolution | `skill-source-resolution` | Package-local skill metadata and `skill_refs` preservation complete | Source loading, trust, precedence, and prompt injection are specified as future work |
| Iterative agent-loop runtime | `iterative-agent-loop-runtime` | Metadata-only tool-use completion policy preservation complete | ReAct-style loop execution, stop policy, and loop trace behavior are specified as future work |
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
6. Next: add `live-guardrail-execution`.
7. Add bounded `iterative-agent-loop-runtime`.
8. Add opt-in package-local `skill-source-resolution`.
9. Implement local-model advisory features only when local-model ergonomics is
   the immediate driver: `llmfit-model-fit-filter` for pre-download filtering and
   `llama-cpp-memory-fit-profile` for post-resolution GGUF profiling.
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
