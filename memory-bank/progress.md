# Progress

## Working

- Core runtime supports package-directory workflow loading and execution,
  async-first APIs, sync wrappers, tool registry/overrides, OpenAI-compatible
  adapters/providers, retry, output contracts, token budgeting, tracing, hooks,
  prompt preparation, validation, runtime behavior overrides, model adapter
  coverage, local model helpers, and metadata-only future surfaces.
- Default OpenAI/Codex auth discovery and ChatGPT/Codex backend compatibility
  are implemented.
- llama.cpp and MLX local-model adapters are implemented through their current
  scoped baselines.
- Capability status reporting is implemented for:
  - finite execution
  - metadata-only declarations
  - model adapter coverage
  - tool registry coverage
  - built-in tool-pack status
  - approval interruption coverage
  - MCP-origin registry entries
  - input guardrail adapter coverage
  - invalid packages
- Approval/sandbox v1 baseline is implemented:
  - direct approval-required `tool_use_step` interruption
  - public interruption result contract
  - no side effect before approval
  - redacted approval traces
  - high-level API guardrails for interrupted workflows
  - capability status for the live approval boundary
- MCP v1 baseline is implemented:
  - explicit caller-supplied MCP registry injection
  - MCP-origin provenance
  - hidden and approval-required conservative defaults
  - trusted metadata overrides
  - capability status for live MCP-origin registry entries
- Live guardrail v1 baseline is implemented:
  - caller-registered input guardrails
  - pass/abort decisions
  - fail-closed missing adapter behavior
  - abort before first model/tool action
  - redacted guardrail traces
  - capability status for input guardrail coverage
- Iterative agent-loop runtime v1 is implemented:
  - opt-in bounded loops for eligible `llm_step` nodes
  - serial model-emitted tool calls dispatched through `ToolRegistry`
  - model-facing tool output fed into follow-up model turns
  - approval pause before approval-required model tool invocation
  - fail-closed behavior for unavailable/hidden tools, malformed arguments,
    tool failures, and loop exhaustion
  - loop lifecycle/final-output trace events
- Registry-provided model tools use OpenAI Responses API function-tool shape
  with top-level `name`.
- ReAct/tool workflow guidance exists in authored docs and documents
  route-gated tool execution.
- `llama-cpp-memory-fit-profile` is prepared for v1 implementation as an
  optional injected-evaluator advisory profile for resolved GGUF assets.

## Latest Milestones

- `128acc2` recorded capability-status v1 completion.
- `6ee9d43` recorded approval/sandbox v1 completion.
- `2786e52` recorded MCP explicit registry-injection v1 completion.
- `633cbe3` recorded live input-guardrail v1 completion.
- `4d60fb1` recorded iterative agent-loop runtime v1 completion.
- `987915a` prepared the llama.cpp memory-fit profile v1 implementation plan.
- The commits between those checkpoints implemented:
  - capability-status report contract, metadata-only reporting, collaborator
    coverage, approval/MCP/guardrail status
  - approval interruption result contract and direct tool pause enforcement
  - explicit MCP tool binding and registry construction helpers
  - input guardrail contract and executor enforcement
  - opt-in iterative model-tool loops, safety hardening, and loop trace events

## Remaining

- Next highest-ROI slice in the roadmap: opt-in package-local
  `skill-source-resolution`.
- Optional local-model advisory work remains deferred until local-model
  ergonomics is the immediate driver:
  - `llmfit-model-fit-filter` for pre-download filtering
  - prepared `llama-cpp-memory-fit-profile` v1 for post-resolution GGUF
    profiling
- Power-Marimo host automation remains deferred until approval/sandbox and
  host-managed continuity boundaries are clear.
- Runner-owned durable session storage remains deferred until a concrete
  workflow proves the need.
- LLM step interpreter middleware remains deferred until sandbox, approval,
  guardrails, tracing, redaction, and capability reporting are stable.

## Risks or Follow-ups

- Do not treat future-feature specs as implementation approval; create scoped
  plan/task/validation checkpoints before code changes.
- Approval interruption is v1 only: durable resume, approval decisions,
  model-emitted tool-call approval, argument modification, parallel approvals,
  and serialized resume state remain deferred.
- Sandbox runtime is partial: approval-before-side-effect exists, but write
  tools, shell tools, workspace grants, sandbox adapters, and changed-path audits
  remain deferred.
- MCP runtime is v1 only: live transports, process lifecycle, discovery,
  reconnect, schema cache, and diagnostics beyond metadata remain deferred.
- Guardrails are v1 only: output phases, tool phases, reject-content behavior,
  warning-only behavior, retries, timeouts, and external adapters remain
  deferred.
- Iterative loops are v1 only: loop `state_field`/`tool_result` final selectors,
  durable approval resume, output/tool guardrails, parallel tool calls, and
  durable transcripts remain deferred.
- llama.cpp memory-fit profiling is only prepared, not implemented. V1 should
  use fake evaluators in tests and must not run live llama.cpp binaries or load
  real GGUF models.
- Keep high-risk execution surfaces behind registry, approval, sandbox,
  capability-status, and guardrail boundaries.
- Keep core tests fake-only; do not add live OpenAI, MCP, Hugging Face, Marimo,
  llama.cpp, or local-model calls to unit tests.
