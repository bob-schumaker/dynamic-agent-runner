# Outstanding Spec Work ROI Evaluation

## Metadata

- Feature slug: `outstanding-spec-roi`
- Mode: `light`
- Artifact type: spec portfolio evaluation / roadmap note
- Status: advisory; not implementation authorization
- Date: 2026-08-22
- Source context:
  - `specs/README.md`
  - outstanding and partially implemented feature specs under `specs/`
  - `memory-bank/activeContext.md`
  - `memory-bank/progress.md`

## Objective

Evaluate the likely return on investment of outstanding spec work in the
`dynamic-agent-runner` spec corpus so future implementation choices can start
from a current priority map instead of treating all deferred work as equal.

This artifact is roadmap memory only. Each item still requires a scoped plan,
task list, and validation strategy before code changes begin.

## Evaluation Criteria

ROI is judged by:

- user or downstream-client value
- leverage across multiple workflows or host applications
- fit with existing package boundaries
- implementation risk and dependency surface
- whether the work is already fake-testable
- whether a concrete caller pressure exists in the current corpus

## Highest ROI

| Rank | Spec Work | ROI | Rationale |
| --- | --- | --- | --- |
| 1 | `apple-foundation-model-adapter` A1 | Very high, implementation complete with validation follow-up | Concrete on-machine caller need, successful local SDK and model probes, strong fit with the existing async provider facade and strict coverage, and a bounded first release for text plus explicit JSON Schema output. Slices 1-6 are implemented; standalone live text, structured, and strict-workflow paths succeeded; pytest-native Apple SDK verification remains a follow-up, and A2 tool callbacks remain separately gated. |
| 2 | `memory-aware-context-pipeline` first slice | Medium-high, gated | Useful if it proves memory-specific identity, ownership, provenance, and no-implicit-save policy beyond RAG. First slice should be validation, capability/status, fake retrieval output, retrieved-context handoff, and trace metadata only. |
| 3 | `provider-backed-context-compaction` | Medium | Valuable for long sessions, but depends on provider capability clarity and likely benefits from the completed LiteLLM provider work first. |

## Conditional ROI

| Spec Work | ROI | Recommendation |
| --- | --- | --- |
| `rag-orchestration-contract` future work | Medium | Declarative v1 is done. Next ROI is answer citation/provenance rendering or live retrieval orchestration only if a caller needs it. Do not build retrieval infrastructure. |
| `model-event-streaming` deferred work | Medium | Provider-native token deltas are useful UX, but the current terminal-result/filter surface solved the known downstream blocker. Wait for another concrete streaming need. |
| `workspace-data-tool-pack` deferred work | Medium | Capability/status and host dirty-state are useful. Durable storage and indexing should stay caller-owned unless a host proves the need. |
| `subagent-tool-pack` deferred work | Medium | First consider the specified bounded `ask_llm` slice when a caller needs one-shot specialist-model work; otherwise parallelism, timeouts, and capability status could pay off after sustained subagent usage. Keep durable child lifecycle deferred. |

## Low ROI Unless a Caller Is Blocked

| Spec Work | ROI | Recommendation |
| --- | --- | --- |
| `llmfit-model-fit-filter` | Low-medium | Useful local-model ergonomics, but narrow. Do only when local-model selection becomes active work. |
| `sandbox-workspace-runtime` write/shell slices | Low-medium now, high if a coding-agent caller is blocked | Important but risky. Approval-before-side-effect exists; the next useful slice should be minimal path-granted write/edit tools and allowlisted verification commands, not arbitrary shell. |
| `approval-interruption-resume` durable resume | Low-medium | Useful for long-running or mutating workflows, but the current direct approval pause is enough until a real resume workflow appears. |
| `hash-chained-governance-audit` | Low-medium | Tamper-evident decision history is valuable for regulated or high-risk tool workflows, but no current caller requires a governance ledger. Keep the caller-supplied sink and first-release boundary prepared until that need exists. |
| `mcp-runtime-integration` live transports | Low-medium | Current explicit registry injection is the right baseline. Live discovery and process lifecycle add operational risk; defer until a host needs them. |
| `live-guardrail-execution` output/tool phases | Low-medium | Important eventually, but input guardrails cover the first safety boundary. Output/tool phases need clearer policy semantics. |
| `collaborative-agent-sessions` deferred work | Low-medium | Wait/resume and capability/status are reasonable, but durable and cross-process work should wait. |
| `skill-source-resolution` external roots | Low | Package-local loading is done. External roots, network loading, and support-file reads increase trust and path complexity; defer. |
| `web-tool-pack` deferred work | Low | V1 exists. Redirects, readability, provider adapters, and richer network policy are only worth it for a concrete caller. |
| `llm-step-interpreter-middleware` | Low for now | Potentially powerful but high-risk. Keep behind sandbox, approval, guardrail maturity, and benchmark evidence. |

## Recommended Order

1. Approve and implement the prepared `apple-foundation-model-adapter` A1
   slices without pulling A2 tool callbacks into the initial release.
2. Run the `memory-aware-context-pipeline` first-slice validation to decide
   whether it remains separate from RAG.
3. Add `provider-backed-context-compaction` after provider capability boundaries
   are clearer.

## Recently Completed Since This Evaluation

| Spec Work | Completed Slice | Evidence |
| --- | --- | --- |
| `local-model-availability-api` | Slices A1-A4 | Explicit-reference preflight, backend-aware validation, injected no-download metadata checks, narrow DAR/default-cache inventory, caller-root inventory, docs, and fake tests |
| `openai-responses-tool-loop-compat` | Slice R1 | Streamed Responses function-call preservation, structured transcript rendering, ChatGPT/Codex `function_call_output` follow-ups, `tool_choice_policy`, model-facing `tool_results`, docs, and fake tests |
| `tool-descriptor-budgeting` | Slice T1 | `fd1b54c` implemented opt-in descriptor budgeting; `f7ab5d5` recorded completion evidence and runtime policy docs |
| `host-workflow-integration` | Slice H2 | Inline/generated and loaded-workflow capability preflight, host id capability details, lifecycle docs, and fake tests |
| `semantic-context-profiles` | Slice S1 | Caller-injected semantic older-turn selector, missing-selector fallback diagnostics, exact identifier protection, RAG lane separation, public selector contracts, docs, and fake tests |
| `litellm-provider-adapter` | Slice L1 and shim retirement | Upstream LiteLLM 1.97.0 runtime dependency, direct sync/async Chat Completions transport, public factories, package-owned missing-transport errors, fake tests, documentation, and removal of `dynamic_agent_runner.litellm`; OCI wheel cleanup and Codex global migration remain deferred |

## Deferral Guidance

Do not start these next without a concrete blocking caller:

- interpreter middleware
- live MCP transports
- full sandbox write/shell runtime
- a separate `coding-workspace-tool-pack` spec, unless the first sandbox-owned
  write/edit slice proves the standard tool-pack API needs its own owner
- durable approval resume
- hash-chained governance audit implementation
- durable memory or storage work
- runner-owned retrieval infrastructure

These surfaces are high-complexity and should remain behind explicit caller
pressure, scoped plans, and fake-testable acceptance criteria.

## Validation Checklist

- The evaluation is linked from `specs/README.md`.
- The artifact does not mark any future work as implementation-approved.
- The highest-ROI items preserve existing ownership boundaries.
- The Apple A1 ranking remains advisory, and A2 tool callbacks stay behind a
  separate approval and planning gate.
- The memory-aware recommendation preserves the RAG separation and
  no-implicit-save constraint.
