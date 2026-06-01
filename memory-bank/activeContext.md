# Active Context

## Current Focus

- The runtime is implemented through package-alignment Slice P5, E14 async-first
  execution, and OA6 deferred multi-agent metadata preservation.
- The current next active slice is `OA7`: workflow interruption and resumable
  run state for approval-required tools.
- The active follow-up order is: `OA7`, `OA10`, `OA9`, `OA8`, then `OA11`.

## Current State Snapshot

- Public runtime surface is package-directory-first:
  `load_agent_workflow(...)`, `run_agent_workflow(...)`, and
  `run_agent_workflow_async(...)` accept package-based workflow inputs, while
  lower-level artifact seams remain available.
- The executor is async-first. Sync entry points are compatibility wrappers over
  the async semantic path and reject already-running event loops.
- Core implemented seams now include:
  - grouped manifest loading (`runtime`, `metadata`, `extensions`)
  - prepared execution planning and prepared model-input staging
  - repository-owned tool registry and override handling
  - OpenAI adapter boundary with fake-client-compatible tests
  - retry, output-contract validation, token-budget preflight, tracing, and
    runtime behavior overrides
  - run-correlation support for concurrent execution
- Supported future runtime-package metadata now includes:
  - provider-neutral `model_requirements`
  - `react_loop` validation
  - `metadata.rag_pipeline`
  - `evidence_loop`
  - deferred guardrails, MCP registry/lifecycle metadata,
    tool-use-completion metadata, and handoff vs agent-as-tool metadata

## Latest Completed Follow-up Slices

- `OA5` completed in `3d33bbb`: deferred
  `runtime.execution_policy.tool_use_completion` metadata is preserved without
  changing executor behavior.
- `OA6` completed in `d5f4114`: grouped `metadata.handoffs`, typed node-local
  `agent_as_tool` / `agent_tool` metadata, and corresponding `ExecutionPlan` /
  `PreparedNode` preservation are in place without adding a new primitive node
  kind or changing current executor behavior.
- OA6 validation passed with:
  `poetry run pytest`
  `tests/test_artifacts.py tests/test_validation.py`
  `tests/test_executor.py tests/test_power_marimo_fixture.py -q 2>&1`
  (`106 passed`) plus scoped `pre-commit` on the changed code/spec files.

## Important Current Facts

- The source of truth for current task sequencing is:
  - `specs/dynamic-agent-runner/spec.md`
  - `specs/dynamic-agent-runner/plan.md`
  - `specs/dynamic-agent-runner/tasks.md`
- The runtime intentionally remains OpenAI-first through a small adapter
  boundary; `ocihelper`, `ai-tools-core`, and `openai-tools-core` are not part
  of the intended initial runtime direction.
- Agent patterns, RAG/GraphRAG shapes, portable tool taxonomy, handoffs, and
  agent-as-tool semantics are represented as metadata layered onto the existing
  primitive runtime graph rather than as new primitive node kinds.
- `../power-marimo` remains the first downstream fit. Its `marimo-pair`
  capability is modeled as a bounded agent-as-tool/SKILL-backed operation, not a
  durable handoff or a new runtime primitive.
- Local llama.cpp and graph-mutation work exists only as preserved feature-spec
  material; the runtime codebase remains in its prior OpenAI-first state.

## Next Steps

- If implementation resumes, start from `OA7` in the governing SDD artifacts.
- Keep new behavior behind package-owned interfaces and fail-closed validation.
- Preserve fake-client/fake-tool tests and avoid live OpenAI API calls in unit
  coverage.
- Continue treating `parallel_join`, `parallel_fanout`, live MCP execution,
  approval/resume engines, and broader multi-agent runtime behavior as deferred
  until a scoped slice explicitly selects them.
