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
| OpenAI-compatible provider wrapper | [`spec.md`](openai-compatible-provider-wrapper/spec.md) | Implemented follow-up | Slices 1-6 complete; optional compatibility polish only |
| llama.cpp local-model adapter | [`spec.md`](llama-cpp-local-model/spec.md) | Active feature record | Slices 1-2 complete; optional Slice 3 embedding follow-up unscheduled |
| Internal graph mutation | [`spec.md`](internal-graph-mutation/spec.md) | First checkpoint complete | T3.2 complete; no additional tasks scheduled |
| Async session memory pipeline | [`spec.md`](async-session-memory-pipeline/spec.md) | Metadata baseline plus future expansion analysis | Metadata-only OA8 baseline implemented; no runner-owned session behavior |
| LLM step interpreter middleware | [`spec.md`](llm-step-interpreter-middleware/spec.md) | Future investigation | Spec captured; backend selection, prototypes, and implementation not started |
| Approval interruption and resume | [`spec.md`](approval-interruption-resume/spec.md) | Future feature spec | Metadata baseline exists; live pause/resume not implemented |
| Sandbox and workspace runtime | [`spec.md`](sandbox-workspace-runtime/spec.md) | Future feature spec | Metadata baseline exists; write/shell runtime not implemented |
| MCP runtime integration | [`spec.md`](mcp-runtime-integration/spec.md) | Future feature spec | Metadata diagnostics baseline exists; live MCP discovery/invocation not implemented |
| Live guardrail execution | [`spec.md`](live-guardrail-execution/spec.md) | Future feature spec | Guardrail metadata baseline exists; live enforcement not implemented |
| SKILL.md source resolution | [`spec.md`](skill-source-resolution/spec.md) | Future feature spec | Skill metadata and refs exist; arbitrary source loading not implemented |
| Iterative agent-loop runtime | [`spec.md`](iterative-agent-loop-runtime/spec.md) | Future feature spec | Tool-use completion metadata exists; live iterative loop not implemented |
| Power-Marimo host automation | [`spec.md`](power-marimo-host-automation/spec.md) | Future downstream integration spec | Placeholder-safe fixture exists; live Marimo/PyQt automation not implemented |

## Completion Matrix

| Capability Area | Owning Spec Package | Implemented Baseline | Remaining / Deferred Work |
| --- | --- | --- | --- |
| Package-directory workflow loading and execution | `dynamic-agent-runner` | Complete through package alignment, async-first execution, tracing, hooks, prompt-cache metadata, and portable `tool_type` preservation | Future scoped expansions only |
| OpenAI-compatible provider facade | `openai-compatible-provider-wrapper` | Sync/async provider facade, provider config, SDK-backed defaults, package exports, and README example complete | Optional compatibility polish for provider-specific behavior |
| Local endpoint-backed model adapters | `llama-cpp-local-model` | Local endpoint helpers, provider-seam wiring, exports, model-resolution precedence, Hugging Face download wiring, and local failure taxonomy complete | Optional separate local embedding configuration and in-process llama.cpp evaluation |
| Compile-time graph mutation | `internal-graph-mutation` | Internal typed mutation datamodel, context-pruning mutation, validation, prepared-input integration, and diagnostics complete | Future structural graph surgery or public mutation schema require new approval |
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
3. Read a feature package when working in that specific area; each feature spec
   owns its own scope boundary and completion evidence.

Do not treat future-analysis specs as implementation authorization. Feature
packages marked future investigation or optional follow-up require an explicit
scheduled task before code changes begin.
