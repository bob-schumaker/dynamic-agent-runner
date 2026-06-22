# Outstanding Spec Work ROI Evaluation

## Metadata

- Feature slug: `outstanding-spec-roi`
- Mode: `light`
- Artifact type: spec portfolio evaluation / roadmap note
- Status: advisory; not implementation authorization
- Date: 2026-06-22
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
| 1 | `litellm-provider-adapter` | Very high, paused | Slice L1 remains prepared, but implementation is paused until LiteLLM supports the package's Python 3.14 target. The prepared scope is default direct SDK Chat Completions transport, fake tests, request/response translation, and an explicit official-SDK compatibility path; ChatGPT/Codex-on-LiteLLM is deferred to a Responses-aware follow-up slice. |
| 2 | `semantic-context-profiles` deferred selector work | Medium-high | Builds on existing context-management behavior and improves prompt quality. Best next slice is a fake semantic selector protocol plus profile-specific diagnostics, with no embeddings or vector ownership. |
| 3 | `memory-aware-context-pipeline` first slice | Medium-high, gated | Useful if it proves memory-specific identity, ownership, provenance, and no-implicit-save policy beyond RAG. First slice should be validation, capability/status, fake retrieval output, retrieved-context handoff, and trace metadata only. |

## Conditional ROI

| Spec Work | ROI | Recommendation |
| --- | --- | --- |
| `provider-backed-context-compaction` | Medium | Valuable for long sessions, but depends on provider capability clarity and likely benefits from LiteLLM/provider work first. |
| `rag-orchestration-contract` future work | Medium | Declarative v1 is done. Next ROI is answer citation/provenance rendering or live retrieval orchestration only if a caller needs it. Do not build retrieval infrastructure. |
| `model-event-streaming` deferred work | Medium | Provider-native token deltas are useful UX, but the current terminal-result/filter surface solved the known downstream blocker. Wait for another concrete streaming need. |
| `workspace-data-tool-pack` deferred work | Medium | Capability/status and host dirty-state are useful. Durable storage and indexing should stay caller-owned unless a host proves the need. |
| `subagent-tool-pack` deferred work | Medium | Parallelism, timeouts, and capability status could pay off after sustained subagent usage. Keep durable child lifecycle deferred. |

## Low ROI Unless a Caller Is Blocked

| Spec Work | ROI | Recommendation |
| --- | --- | --- |
| `llmfit-model-fit-filter` | Low-medium | Useful local-model ergonomics, but narrow. Do only when local-model selection becomes active work. |
| `sandbox-workspace-runtime` write/shell slices | Low-medium now, high later | Important but risky. Approval-before-side-effect exists; write and shell tools need concrete path-grant requirements before implementation. |
| `approval-interruption-resume` durable resume | Low-medium | Useful for long-running or mutating workflows, but the current direct approval pause is enough until a real resume workflow appears. |
| `mcp-runtime-integration` live transports | Low-medium | Current explicit registry injection is the right baseline. Live discovery and process lifecycle add operational risk; defer until a host needs them. |
| `live-guardrail-execution` output/tool phases | Low-medium | Important eventually, but input guardrails cover the first safety boundary. Output/tool phases need clearer policy semantics. |
| `collaborative-agent-sessions` deferred work | Low-medium | Wait/resume and capability/status are reasonable, but durable and cross-process work should wait. |
| `skill-source-resolution` external roots | Low | Package-local loading is done. External roots, network loading, and support-file reads increase trust and path complexity; defer. |
| `web-tool-pack` deferred work | Low | V1 exists. Redirects, readability, provider adapters, and richer network policy are only worth it for a concrete caller. |
| `llm-step-interpreter-middleware` | Low for now | Potentially powerful but high-risk. Keep behind sandbox, approval, guardrail maturity, and benchmark evidence. |

## Recommended Order

1. Resume `litellm-provider-adapter` Slice L1 when LiteLLM supports the
   package's Python target.
2. Add the `semantic-context-profiles` fake-selector slice.
3. Run the `memory-aware-context-pipeline` first-slice validation to decide
   whether it remains separate from RAG.
4. Add `provider-backed-context-compaction` after provider capability boundaries
   are clearer.

## Recently Completed Since This Evaluation

| Spec Work | Completed Slice | Evidence |
| --- | --- | --- |
| `tool-descriptor-budgeting` | Slice T1 | `fd1b54c` implemented opt-in descriptor budgeting; `f7ab5d5` recorded completion evidence and runtime policy docs |
| `host-workflow-integration` | Slice H2 | Inline/generated and loaded-workflow capability preflight, host id capability details, lifecycle docs, and fake tests |

## Deferral Guidance

Do not start these next without a concrete blocking caller:

- interpreter middleware
- live MCP transports
- full sandbox write/shell runtime
- durable approval resume
- durable memory or storage work
- runner-owned retrieval infrastructure

These surfaces are high-complexity and should remain behind explicit caller
pressure, scoped plans, and fake-testable acceptance criteria.

## Validation Checklist

- The evaluation is linked from `specs/README.md`.
- The artifact does not mark any future work as implementation-approved.
- The highest-ROI items preserve existing ownership boundaries.
- The memory-aware recommendation preserves the RAG separation and
  no-implicit-save constraint.
