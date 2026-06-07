# Active Context

## Current Focus

- The latest completed work is adapter-coverage client documentation:
  - `2429727` (`docs(adapter-coverage): document coverage policy`) documented
    `model_adapter_coverage` in README, Python API docs, specs, and memory.
  - `cb52cd0` (`docs(skill): clarify adapter coverage modes`) refined
    `docs/skills/dynamic-agent-runner/SKILL.md` with default OpenAI behavior,
    strict vs augmented adapter coverage, and local llama.cpp adapter usage.
- Recent completed Hugging Face/spec milestones also include:
  - `2425a4e` (`docs(specs): add hugging face support layer spec`)
  - `191f722` (`docs(hugging-face): document model search api`)
  - `3f5b51f` (`docs(specs): align feature status matrix`)
- Model adapter coverage is implemented through Slices 1-4: public APIs and
  `WorkflowExecutionContext` accept `model_adapter_coverage`, strict mode keeps
  supplied adapters authoritative, augmented mode preserves default OpenAI
  coverage, `local_only` metadata no longer filters adapter selection, and the
  repository-local client skill now calls out default OpenAI and local
  llama.cpp adapter usage.
- The active authoritative change spec for the current session is
  `specs/mlx-local-model-adapter/spec.md`. It defines a macOS-only in-process
  MLX local-model adapter direction, local asset/reference boundaries, strict
  local-only coverage guidance, and the distinction from caller-provided
  OpenAI-compatible local endpoints. Implementation plan/tasks are prepared in
  `specs/mlx-local-model-adapter/plan.md` and
  `specs/mlx-local-model-adapter/tasks.md`.
- The repo has a top-level spec index at `specs/README.md` that identifies the
  primary runtime spec, all feature-spec packages, and the completion matrix.
- The primary runtime spec remains `specs/dynamic-agent-runner/spec.md`.

## Current Spec Authority Map

- Primary runtime contract:
  - `specs/dynamic-agent-runner/spec.md`
  - package-directory-first loading/execution, async-first runtime, tool
    registry, OpenAI-compatible adapter/provider boundary, validation, tracing,
    prompt preparation, runtime-policy metadata, and public API direction
- Implemented or checkpoint-complete feature specs:
  - `specs/openai-compatible-provider-wrapper/spec.md`
  - `specs/llama-cpp-local-model/spec.md`
  - `specs/internal-graph-mutation/spec.md`
  - `specs/hugging-face-model-search/spec.md`
  - `specs/async-session-memory-pipeline/spec.md`
  - `specs/model-adapter-coverage/spec.md`
- Active next-change spec:
  - `specs/mlx-local-model-adapter/spec.md`
- Future investigation or future-feature specs:
  - `specs/llm-step-interpreter-middleware/spec.md`
  - `specs/approval-interruption-resume/spec.md`
  - `specs/sandbox-workspace-runtime/spec.md`
  - `specs/mcp-runtime-integration/spec.md`
  - `specs/live-guardrail-execution/spec.md`
  - `specs/skill-source-resolution/spec.md`
  - `specs/iterative-agent-loop-runtime/spec.md`
  - `specs/power-marimo-host-automation/spec.md`
  - `specs/hugging-face-support-layer/spec.md`

## Current Status

- Core runtime implementation is complete through package-alignment P5, E14
  async-first execution, OA11 portable `tool_type` alignment, prompt-cache
  metadata, provider-wrapper Slices 1-6, llama.cpp local-model Slices 1-2, and
  the first internal graph-mutation checkpoint.
- Public Hugging Face model discovery is implemented with a repository-owned
  search API, normalized result type, package-owned error boundary, exports,
  deterministic tests, and Python API docs.
- Model adapter coverage policy is implemented with the public
  `model_adapter_coverage` argument on high-level and lower-level execution
  APIs, strict missing-coverage failures, augmented default OpenAI coverage, and
  no `local_only` adapter-routing semantics.
- User-facing docs now document the current mise/Poetry setup, package-owned
  local-model helper boundary, Hugging Face discovery test coverage, adapter
  coverage modes, default OpenAI fallback behavior, and dependency direction.
- The Hugging Face support-layer spec is future internal infrastructure only:
  it would centralize lazy Hub import, read-only SDK calls, and low-level error
  mechanics without merging search and local-model asset resolution.
- Metadata-only runtime surfaces are implemented for guardrails, MCP registry
  sources/lifecycle diagnostics, approval interruption, async session policy,
  sandbox runtime policy, and tool-use completion policy.
- Live runtime behavior is still deferred for approval pause/resume, writable
  sandbox/workspace execution, live MCP discovery/invocation, live guardrail
  enforcement, arbitrary `SKILL.md` source loading, iterative model/tool loops,
  and Power-Marimo host automation.
- The active llama.cpp gate remains optional Slice 3: separate local embedding
  configuration, only if explicitly scheduled.
- The active MLX gate is ready for implementation from
  `specs/mlx-local-model-adapter/tasks.md`; start with Slice 1 public contract
  and failure tests.

## Next Steps

- For implementation: continue from
  `specs/mlx-local-model-adapter/tasks.md` and commit after each selected
  implementation slice if the user asks to execute the plan.
- For documentation: keep `README.md`, `docs/files/`, `specs/README.md`,
  `specs/dynamic-agent-runner/tasks.md`, and feature spec statuses synchronized
  when new slices are selected or closed.
- For validation: continue using fake clients/tools for unit tests and avoid live
  OpenAI, MCP, Marimo, or local-model infrastructure in core unit validation.
