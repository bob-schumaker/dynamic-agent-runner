# Active Context

## Current Focus

- The latest completed work is docs alignment in `9354d24`
  (`docs: align docs with current repo state`).
- That docs refresh updated `README.md` and authored Sphinx files under
  `docs/files/` to match current setup, public API, local-model, and Hugging
  Face discovery state.
- Recent completed Hugging Face/spec milestones also include:
  - `2425a4e` (`docs(specs): add hugging face support layer spec`)
  - `191f722` (`docs(hugging-face): document model search api`)
  - `3f5b51f` (`docs(specs): align feature status matrix`)
- Model adapter coverage is implemented through Slices 1-4: public APIs and
  `WorkflowExecutionContext` accept `model_adapter_coverage`, strict mode keeps
  supplied adapters authoritative, augmented mode preserves default OpenAI
  coverage, and `local_only` metadata no longer filters adapter selection.
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
  local-model helper boundary, Hugging Face discovery test coverage, and
  dependency direction.
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

## Next Steps

- For implementation: select a scoped feature spec or create/update a task
  breakdown before editing code.
- For documentation: keep `README.md`, `docs/files/`, `specs/README.md`,
  `specs/dynamic-agent-runner/tasks.md`, and feature spec statuses synchronized
  when new slices are selected or closed.
- For validation: continue using fake clients/tools for unit tests and avoid live
  OpenAI, MCP, Marimo, or local-model infrastructure in core unit validation.
