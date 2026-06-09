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
| Async session memory pipeline | [`spec.md`](async-session-memory-pipeline/spec.md) | Metadata baseline plus future analysis | Metadata-only OA8 baseline implemented; no runner-owned session behavior |
| LLM step interpreter middleware | [`spec.md`](llm-step-interpreter-middleware/spec.md) | Future investigation | Spec captured; backend selection, prototypes, and implementation not started |
| Approval interruption and resume | [`spec.md`](approval-interruption-resume/spec.md) | Future live-runtime feature | Metadata baseline exists; live pause/resume not implemented |
| Sandbox and workspace runtime | [`spec.md`](sandbox-workspace-runtime/spec.md) | Future live-runtime feature | Metadata baseline exists; write/shell runtime not implemented |
| MCP runtime integration | [`spec.md`](mcp-runtime-integration/spec.md) | Future live-runtime feature | Metadata diagnostics baseline exists; live MCP discovery/invocation not implemented |
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
| Async session metadata | `async-session-memory-pipeline` | `runtime.execution_policy.async_session` metadata preservation and fail-closed validation complete | Runner-owned durable storage, replay, summary generation, and pruning are deferred |
| Interpreter middleware | `llm-step-interpreter-middleware` | Future feature spec and candidate interface expectations captured | Dependency checks, prototypes, benchmark evidence, backend selection, and implementation |
| Sandbox/workspace runtime | `sandbox-workspace-runtime` | Metadata-only `sandbox_runtime` preservation complete | Write tools, shell tools, workspace grants, and approval policy are specified as future work |
| Approval interruption/resume | `approval-interruption-resume` | Metadata-only `approval_interruption` preservation complete | Live pause/resume engine and serialized resume state are specified as future work |
| MCP runtime integration | `mcp-runtime-integration` | Metadata-only MCP registry-source and lifecycle diagnostics preservation complete | Live server discovery, lifecycle, registry injection, and invocation are specified as future work |
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
