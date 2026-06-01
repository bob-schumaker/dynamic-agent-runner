# Active Context

## Current Focus

- The runtime is implemented through package-alignment Slice P5, E14 async-first
  execution, OA7 deferred approval interruption metadata preservation, OA10
  deferred sandbox/workspace runtime metadata preservation, and OA9
  `tool_from_function(...)` helper support.
- The current next active slice is `OA8`: consider a small async session
  protocol only after multi-turn memory requirements are explicit.
- The active follow-up order is: `OA8`, then `OA11`.

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
    tool-use-completion metadata, handoff vs agent-as-tool metadata,
    approval interruption/resumable-run metadata, and sandbox/workspace runtime
    metadata

## Latest Completed Follow-up Slices

- `OA9` completed in `c181328`: the registry now exposes an optional
  `tool_from_function(...)` helper that builds `RegisteredTool` instances from
  Python callables, accepts explicit metadata when provided, and falls back to
  conservative inference for missing label, description, and input-schema
  fields using the callable name, docstring, and supported signature/type-hint
  shapes.
- OA9 validation passed with:
  `poetry run pytest tests/test_registry.py tests/test_import.py -q 2>&1`
  (`32 passed`) and scoped `poetry run pre-commit run --files ...` on the OA9
  code/spec/doc files.
- `OA10` completed in `540f56a`: deferred
  `runtime.execution_policy.sandbox_runtime` metadata is preserved on
  `RuntimeManifest` and `ExecutionPlan` without changing the current read-only
  `local_workspace` built-in tool pack or enabling a writable workspace runtime.
- OA10 validation passed with:
  `poetry run pytest tests/test_artifacts.py tests/test_validation.py -q 2>&1`
  (`66 passed`) and scoped `poetry run pre-commit run --files ...` on the OA10
  code/spec/doc files.
- `OA7` completed in `ce85a55`: deferred
  `runtime.execution_policy.approval_interruption` metadata is preserved on
  `RuntimeManifest` and `ExecutionPlan` without adding a live approval engine or
  pause/resume execution behavior.
- OA7 validation passed with:
  `poetry run pytest tests/test_artifacts.py tests/test_validation.py -q 2>&1`
  (`60 passed`) and scoped `poetry run pre-commit run --files ...` on the OA7
  code/spec/doc files.
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

- If implementation resumes, start from `OA8` in the governing SDD artifacts.
- Keep new behavior behind package-owned interfaces and fail-closed validation.
- Preserve fake-client/fake-tool tests and avoid live OpenAI API calls in unit
  coverage.
- Continue treating `parallel_join`, `parallel_fanout`, live MCP execution,
  approval/resume engines, and broader multi-agent runtime behavior as deferred
  until a scoped slice explicitly selects them.
