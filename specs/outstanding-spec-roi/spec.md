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
| 1 | `memory-aware-context-pipeline` exit gate | First passive-context slice implemented; reassessment pending | Decide whether memory semantics remain distinct from RAG using the existing metadata, capability, provenance, and no-implicit-save evidence before authorizing any richer slice. |
| 2 | `sandbox-workspace-runtime` first write/edit slice | Metadata and host-only ingress primitive exist; model-facing write/shell runtime is deferred | If a coding-agent caller is blocked, add the smallest path-granted write/edit and allowlisted verification slice. Keep arbitrary shell, workspace grants, commit/rollback, and mutation audits behind separate gates. |
| 3 | `live-guardrail-execution` output/tool-output phases | Input and tool-input V2 are implemented; later phases remain deferred | Add only when a concrete caller defines output and tool-output policy semantics; reuse the existing coordinator and keep handler dispatch out of guardrails. |

The first item is the next implementation-ready scope decision. These items
should not be silently converted into general adapter changes.

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
- Apple Foundation Models A2 B5.2 native required-first tool-choice binding:
  bounded investigation is complete, but the native API is unavailable on the
  current macOS 26 host and absent from the installed Python bridge. Revisit
  only on macOS 27+ with a bridge exposing
  `GenerationOptions.ToolCallingMode`; then repeat the controlled selection and
  post-callback completion evidence. Do not add a fallback or production
  binding while this gate is blocked.
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

1. Reassess the first-slice boundary of `memory-aware-context-pipeline` before
   authorizing richer memory behavior.
2. If a caller supplies concrete pressure, evaluate the first slice of
   `sandbox-workspace-runtime` or `live-guardrail-execution` as separate scoped
   work.
3. Reopen Apple A2 B5.2 only after the macOS 27+/bridge prerequisite is met.

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
- Completed Apple A1--A4 work is not ranked as outstanding; B5.2 is recorded as
  bounded and blocked pending macOS 27+/bridge support rather than actionable
  work on the current host.
- The implemented external adapter is excluded from outstanding work.
- Live acceptance T5.2 is recorded complete and excluded from outstanding work.
- Apple B5 remains a bounded evidence gate rather than implicit authorization
  for source changes; its native required-first sub-gate is blocked until the
  recorded platform and bridge prerequisites are met.
- Deferred work preserves DAR's generic runtime boundary and caller ownership.
- The document remains advisory and does not replace a feature's
  `plan.md`, `tasks.md`, or `validation.md`.
