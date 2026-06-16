# Active Context

## Current Focus

- No implementation slice is currently active.
- The high-ROI queue has advanced through four major runtime foundations:
  capability/status visibility, approval/sandbox approval-before-side-effect
  policy, explicit MCP registry injection, and caller-registered input
  guardrails.
- Bounded `iterative-agent-loop-runtime` v1 is now implemented and documented.
- `llama-cpp-memory-fit-profile` is prepared for v1 implementation as an
  optional, read-only, injected-evaluator advisory feature.
- Recent local-model maintenance tightened optional-runtime behavior:
  direct llama.cpp docs now point callers to the `llamacpp` extra, missing
  default `llama_cpp` imports are covered by regression tests, and MLX adapter
  tests verify non-macOS use fails before model resolution or `mlx_lm` loading.
- PyInstaller packaging support for `openai-model-registry` is complete:
  package-owned hook files, metadata advertisement, build-gated DevOps SCM PR,
  and develop/main branch synchronization are done.
- Context growth management has a dedicated spec package:
  `specs/context-management-prepare-stage/` now owns session pruning, context
  compaction, hierarchical prompt-context injection, and provider-neutral
  hierarchical compression planning.
- The current preferred compression scheme is turn-aware lane assembly:
  pinned hierarchy, current turn, recent turns, rolling structured summary,
  deterministic older-turn selection with chronological reassembly, and
  deterministic fallback trimming before optional provider compaction.
- The next recorded ROI focus in `specs/README.md` is opt-in package-local
  `skill-source-resolution`; local-model advisory implementation should happen
  when local-model ergonomics is the immediate driver.

## Recent Completed Work

- Capability status reporting is implemented:
  - public report contract and package inspection
  - metadata-only declarations
  - model adapter, tool registry, built-in tool-pack, approval, MCP, and
    guardrail collaborator/status reporting
  - invalid package reporting
- Approval/sandbox v1 baseline is implemented:
  - `ApprovalInterruptionState`, `ApprovalInterruption`, and
    `WorkflowInterruptedResult`
  - direct approval-required `tool_use_step` pause before handler invocation
  - no side effect before approval
  - redacted approval trace events
  - high-level `run_agent_workflow*` APIs fail clearly on interrupted workflows
  - sandbox work remains partial: approval-before-side-effect exists, but write,
    shell, workspace grants, sandbox adapters, and mutation audits remain
    deferred
- MCP v1 baseline is implemented:
  - `MCPToolBinding`
  - `registered_tool_from_mcp_binding(...)`
  - `create_mcp_registry(...)`
  - MCP-origin tool provenance
  - conservative hidden and approval-required defaults
  - live MCP registry-entry capability status
  - live MCP transports, process lifecycle, discovery, reconnect, cache, and
    diagnostics beyond metadata remain deferred
- Live guardrail v1 baseline is implemented:
  - `GuardrailDecision`, `GuardrailResult`, and `InMemoryGuardrailRegistry`
  - input guardrails run before first model/tool action
  - missing input adapters fail closed
  - abort decisions raise `GuardrailExecutionError`
  - redacted guardrail traces
  - capability status for missing/live input guardrail adapter coverage
  - output/tool phases, reject-content, warning-only behavior, retries,
    timeouts, and external adapters remain deferred
- Iterative agent-loop runtime v1 is implemented:
  - opt-in activation through
    `runtime.execution_policy.tool_use_completion.run_again: required`
  - serial model-emitted tool dispatch through `ToolRegistry`
  - model-facing tool-result transcript feedback into the next model turn
  - fail-closed handling for unavailable/hidden tools, malformed arguments,
    failed tools, and max loop exhaustion
  - approval-required model tool calls pause before invocation
  - loop lifecycle and final-output trace events
  - loop `state_field`/`tool_result` final selectors, durable approval resume,
    output/tool guardrails, parallel tool calls, and durable transcripts remain
    deferred
- llama.cpp memory-fit profile is prepared for v1 implementation:
  - planned as a post-resolution GGUF advisory API
  - v1 uses only caller-injected evaluators/profilers
  - fail-open is the default, strict mode is scoped to the profiling call, no
    cache or automatic memory-budget discovery is planned for v1
  - suggested kwargs are limited to `n_ctx`
- Local-model optional-runtime hardening is in place at the test/docs layer:
  - direct llama.cpp helpers remain lazy and report a package-owned
    `ModelExecutionError` when the default `llama_cpp` dependency is absent
  - MLX helpers remain constructible on non-macOS, advertise their model aliases,
    and fail with the macOS-only `ModelExecutionError` before resolving model
    paths or loading dependencies when generation is attempted off macOS
- PyInstaller packaging support for `openai-model-registry` is complete.

## Current Spec Authority Map

- Primary runtime contract:
  - `specs/dynamic-agent-runner/spec.md`
- Recently completed feature packages:
  - `specs/capability-status-report/spec.md`
  - `specs/approval-interruption-resume/spec.md`
  - `specs/sandbox-workspace-runtime/spec.md`
  - `specs/mcp-runtime-integration/spec.md`
  - `specs/live-guardrail-execution/spec.md`
  - `specs/iterative-agent-loop-runtime/spec.md`
- Prepared feature packages:
  - `specs/llama-cpp-memory-fit-profile/spec.md`
  - `specs/context-management-prepare-stage/spec.md`
- Next ROI feature package:
  - `specs/skill-source-resolution/spec.md`
- Later feature packages:
  - `specs/power-marimo-host-automation/spec.md`
  - `specs/async-session-memory-pipeline/spec.md`
  - `specs/llm-step-interpreter-middleware/spec.md`
  - optional local-model advisory specs:
    `specs/llmfit-model-fit-filter/spec.md`

## Next Steps

- If continuing local-model advisory work, decide whether the pending
  `pyproject.toml` / `poetry.lock` optional llama.cpp metadata edits should be
  committed, revised, or discarded before executing another slice.
- If following the ROI queue instead, prepare `skill-source-resolution` before
  implementation.
- If implementing context growth management, use
  `specs/context-management-prepare-stage/plan.md` and `tasks.md`; start with
  policy/turn-unit metadata and lane-based prompt assembly before provider or
  mid-turn compaction.
- Preserve unit-test boundaries: fake clients, fake tools, fake MCP bindings,
  fake guardrails, and fake local-model profilers only; no live OpenAI, MCP,
  Hugging Face, Marimo, llama.cpp, or local model calls in core tests.
