# Outstanding Spec Work ROI Evaluation

## Metadata

- Feature slug: `outstanding-spec-roi`
- Mode: `light`
- Artifact type: spec portfolio evaluation / roadmap note
- Status: advisory; not implementation authorization
- Date: 2026-09-24
- Source context:
  - `specs/README.md` status index, reconciled 2026-09-13
  - current feature `spec.md`, `plan.md`, and `tasks.md` artifacts
  - `memory-bank/activeContext.md`
  - `memory-bank/progress.md`

## Objective

Keep a current priority map of the repository's unimplemented, partially
implemented, and explicitly deferred spec surface. This note prevents
completed work from being ranked as outstanding and prevents deferred ideas
from being treated as implementation commitments.

Every candidate still requires its own scoped plan, task list, and validation
strategy before code changes begin. This artifact does not authorize source
edits, live-provider activity, model downloads, or external integrations.

## Current implementation-ready surface

These are the items with the clearest path to action today:

| Rank | Spec work | Current state | Why it is actionable |
| --- | --- | --- | --- |
| 1 | `live-model-interface-acceptance` T5.2 | T5.1 complete; one manual compatibility-resolution task remains | The remaining work is bounded to the tested Qwen3/vLLM 0.28.0 B0--B2 evidence. It should record a passing configuration, record the tested combination as unsupported, or open a separate adapter task if DAR diverges from a conforming endpoint. |
| 2 | Apple Foundation Models A2 B5 | A1--A4 implemented; bridged-wrapper `Annotated` regression remains open | This is a narrow SDK compatibility gate, not a reason to expand the adapter surface. Resolve it only with the pinned SDK/runtime evidence and preserve the existing fake-only unit-test boundary. |
| 3 | `memory-aware-context-pipeline` exit gate | First passive-context slice implemented; reassessment pending | Decide whether memory semantics remain distinct from RAG using the existing metadata, capability, provenance, and no-implicit-save evidence before authorizing any richer slice. |

The first item is the next implementation-ready acceptance task. B5 is a
compatibility gate, and the memory-aware item is a scope decision; neither
should be silently converted into general adapter changes.

## Highest-value future candidates

| Spec work | Current state | Recommendation |
| --- | --- | --- |
| `memory-aware-context-pipeline` | No implementation; future first slice | Start only when a caller needs memory semantics distinct from RAG. The first slice should validate memory identity, ownership, provenance, capability/status reporting, fake retrieval tiers, retrieved-context handoff, and no-implicit-save behavior. |
| `sandbox-workspace-runtime` | Metadata and host-only ingress primitive exist; model-facing write/shell runtime is deferred | If a coding-agent caller is blocked, add the smallest path-granted write/edit and allowlisted verification slice. Keep arbitrary shell, workspace grants, commit/rollback, and mutation audits behind separate gates. |
| `live-guardrail-execution` | Input and tool-input V2 are implemented; output/tool-output phases remain | Add output and tool-output enforcement only when policy semantics and a concrete caller are defined. Reuse the coordinator; do not dispatch handlers from guardrails. |
| `provider-backed-context-compaction` | Pre-turn and one-shot overflow retry are implemented; mid-turn/tool-loop and transport binding remain deferred | Extend only after a caller proves the current compaction seams are insufficient and the provider capability contract is explicit. |
| `rag-orchestration-contract` | Declarative validation and capability/status reporting exist; execution infrastructure is deferred | Consider answer citation/provenance rendering or live retrieval orchestration only for a concrete caller. DAR should not acquire ingestion, embedding, index, reranking, or graph-store ownership. |

## Deferred or caller-triggered work

These remain valid spec surfaces but have no current implementation priority:

- `model-execution-plugin-interface`: future host-registered plugins for
  nonstandard models; requires a concrete nonstandard runtime first.
- `llm-step-interpreter-middleware`: future investigation only; backend choice,
  prototypes, benchmarks, and safety boundaries are unresolved.
- `hash-chained-governance-audit`: future caller-sink-backed audit records;
  defer until a regulated or high-risk caller needs tamper evidence.
- `mcp-runtime-integration` live transports: explicit registry injection is the
  baseline; discovery, process lifecycle, reconnect, and schema caching remain
  operationally expensive.
- `litellm-only-codex-transport`: postponed pending conforming upstream
  LiteLLM support; do not begin source work while the re-entry gate is blocked.
- `llmfit-model-fit-filter`: optional advisory pre-download filtering only when
  local-model selection becomes an active bottleneck.
- `model-event-streaming` provider-native deltas and lower-level streaming,
  `subagent-tool-pack` bounded `ask_llm`, `workspace-data-tool-pack` durable
  storage/indexing, `web-tool-pack` richer network policy, and
  `skill-source-resolution` external roots: caller-triggered follow-ups only.
- `iterative-agent-loop-runtime` durable resume, parallel tool calls, and
  multidimensional budget accounting: defer until a caller requires them.

## Completed work excluded from this portfolio

The following are not outstanding feature work and should not be ranked as
next candidates: the OpenAI-compatible provider wrapper, default OpenAI/Codex
auth discovery, LiteLLM provider-adapter baseline, llama.cpp and MLX adapter
baselines, local-model availability, sealed-artifact runtime and output-handler
interfaces, workflow materials/capabilities/index artifacts, session/runtime
baselines, context preparation baseline, tool invocation coordination,
approval interruption v1, model-generation budgets, tool packs v1, and the
multimodal model-runner protocol.

Some of those specs retain explicitly deferred follow-ups. Those follow-ups
remain under their owning spec and are listed above only when they represent a
real unimplemented boundary.

## Recommended order

1. Complete `live-model-interface-acceptance` T5.2 using only the recorded
   B0--B2 compatibility evidence.
2. Resolve Apple A2 B5 as a pinned SDK compatibility gate; create a new task
   only if the evidence identifies a DAR-owned adapter defect.
3. Reassess the first-slice boundary of `memory-aware-context-pipeline` before
   authorizing richer memory behavior.
4. If a caller supplies concrete pressure, evaluate the first slice of
   `sandbox-workspace-runtime` or `live-guardrail-execution` as separate scoped
   work.

## Deferral guidance

Do not start future or deferred work without a concrete blocking caller and a
new approved task boundary. In particular, do not begin interpreter
middleware, live MCP transports, full sandbox write/shell runtime, durable
approval resume, governance-audit persistence, durable memory, runner-owned
retrieval infrastructure, or LiteLLM-only Codex migration merely because a
spec exists.

## Validation checklist

- The status and completion claims agree with `specs/README.md` and the owning
  task artifacts as of 2026-09-24.
- Completed Apple A1--A4 work is not ranked as outstanding; only B5 remains.
- The implemented external adapter is excluded from outstanding work.
- Live acceptance T5.2 is identified as the first implementation-ready
  acceptance task.
- Live acceptance T5.2 and Apple B5 remain bounded evidence gates rather than
  implicit authorization for source changes.
- Deferred work preserves DAR's generic runtime boundary and caller ownership.
- The document remains advisory and does not replace a feature's
  `plan.md`, `tasks.md`, or `validation.md`.
