# Active Context

## Current Focus

- The latest completed work is the Hugging Face model-search feature and a spec
  consistency refresh:
  - `191f722` (`docs(hugging-face): document model search api`)
  - `3f5b51f` (`docs(specs): align feature status matrix`)
- The repo has a top-level spec index at `specs/README.md` that identifies the
  primary runtime spec, all feature-spec packages, and the completion matrix.
- The primary runtime spec remains `specs/dynamic-agent-runner/spec.md`.
- There is no active implementation slice currently scheduled. Future code work
  should start from an explicit feature spec, plan, or task update.

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
- Future investigation or future-feature specs:
  - `specs/llm-step-interpreter-middleware/spec.md`
  - `specs/approval-interruption-resume/spec.md`
  - `specs/sandbox-workspace-runtime/spec.md`
  - `specs/mcp-runtime-integration/spec.md`
  - `specs/live-guardrail-execution/spec.md`
  - `specs/skill-source-resolution/spec.md`
  - `specs/iterative-agent-loop-runtime/spec.md`
  - `specs/power-marimo-host-automation/spec.md`

## Current Status

- Core runtime implementation is complete through package-alignment P5, E14
  async-first execution, OA11 portable `tool_type` alignment, prompt-cache
  metadata, provider-wrapper Slices 1-6, llama.cpp local-model Slices 1-2, and
  the first internal graph-mutation checkpoint.
- Public Hugging Face model discovery is implemented with a repository-owned
  search API, normalized result type, package-owned error boundary, exports,
  deterministic tests, and Python API docs.
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

- For implementation: select one future-feature spec or optional follow-up and
  create or approve a concrete plan/task slice before editing code.
- For documentation: keep `specs/README.md`, `specs/dynamic-agent-runner/tasks.md`,
  and feature spec statuses synchronized when new slices are selected or closed.
- For validation: continue using fake clients/tools for unit tests and avoid live
  OpenAI, MCP, Marimo, or local-model infrastructure in core unit validation.
