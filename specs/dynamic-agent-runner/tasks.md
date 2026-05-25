# dynamic-agent-runner Task List

## Status

- State: Slice 2 complete; ready for Slice 3
- Source spec: `specs/dynamic-agent-runner/spec.md`
- Technical plan: `specs/dynamic-agent-runner/plan.md`
- Readiness verdict: ready for a narrow readiness/scaffold slice only; not ready
  for unrestricted runtime implementation
- Next active slice: Slice 3 — validation engine

## Slice 0 — Planning and documentation readiness checkpoint

- [x] T0.1 Update `spec.md` so its consistency notes acknowledge the follow-on
      `plan.md` and `tasks.md` artifacts.
- [x] T0.2 Keep `plan.md` and `tasks.md` tracked together as the current
      implementation planning artifacts.
- [x] T0.3 Update `README.md` to remove stale `ai-tools-core` wording and align
      with the official `openai` package and repository-owned registry direction.
- [x] T0.4 Keep `pyproject.toml` and `poetry.lock` dependency changes separate
      from documentation/spec commits unless explicitly committing dependency
      state.

## Slice 0 Completion Evidence

- `spec.md` acknowledges `plan.md` and `tasks.md` as follow-on planning artifacts.
- `plan.md` and `tasks.md` are tracked in commit `2979342`.
- `README.md` is aligned with the official `openai` package and
  repository-owned registry direction.
- `pyproject.toml` and `poetry.lock` remain separate uncommitted dependency changes.

## Slice 1 — Package scaffold and dependency alignment

- [x] T1.1 Verify `pyproject.toml` and `poetry.lock` match the latest spec
      direction: official `openai`, no required `ocihelper`, no required
      `ai-tools-core` / `openai-tools-core`.
- [x] T1.2 Create `src/dynamic_agent_runner/__init__.py` with initial public
      exports reserved for the API surface.
- [x] T1.3 Add foundational modules: `errors.py`, `api.py`, and minimal package
      metadata/docstrings.
- [x] T1.4 Create `tests/` and a smoke test that imports `dynamic_agent_runner`.
- [x] T1.5 Confirm `README.md` remains aligned with the official `openai`
      package and repository-owned tool registry direction.
- [x] T1.6 Run `poetry check`, import smoke tests, and targeted pre-commit for
      changed files.

## Slice 1 Completion Evidence

- `pyproject.toml` and `poetry.lock` align with the official `openai`
  package direction and do not require `ocihelper`, `ai-tools-core`, or
  `openai-tools-core`.
- `src/dynamic_agent_runner/` exists with initial public API exports and
  project-specific exception classes.
- `tests/test_import.py` covers the package import smoke test.
- README remains aligned with the official `openai` package and
  repository-owned registry direction.

## Slice 2 — Artifact models and loaders

- [x] T2.1 Define internal models for runtime manifest metadata, documented
      supported pattern IDs, nodes, edges, tools, skills, participant groups,
      modes, phases, roles, output contracts, and validation sections.
- [x] T2.2 Implement runtime YAML loading from path, raw string, and
      already-parsed object inputs.
- [x] T2.3 Implement Mermaid graph loading and `mermaid_diagram` reference
      resolution relative to the runtime YAML path.
- [x] T2.4 Implement optional external `tool-index.yaml` loading from path, raw
      string, and already-parsed object inputs.
- [x] T2.5 Implement lightweight `agent-design.md` loading and reference checks
      for the runtime manifest and Mermaid graph.
- [x] T2.6 Preserve `patterns_present` metadata for the documented supported
      agent pattern IDs without treating patterns as primitive node kinds.
- [x] T2.7 Add fixture-based tests for valid and malformed artifact inputs,
      including at least one metadata-rich pattern shape such as
      `multi-agent-collaboration` or `memory-augmented-agent`.

## Slice 2 Completion Evidence

- `src/dynamic_agent_runner/models.py` defines internal artifact models for
  runtime manifests, nodes, edges, tools, tool indexes, agent designs, and loaded
  workflow bundles.
- `src/dynamic_agent_runner/artifacts.py` loads runtime YAML, Mermaid graph text,
  optional tool indexes, and optional agent design markdown from paths, raw
  strings, or already-parsed mapping inputs.
- `load_agent_workflow(...)` now loads artifacts without executing workflows;
  `run_agent_workflow(...)` remains reserved for later executor slices.
- `PyYAML >=6.0` is declared as a direct runtime dependency for YAML artifact
  loading.
- `tests/test_artifacts.py` covers valid raw-string, path-based, and parsed
  object loading; malformed YAML; missing referenced Mermaid graphs; and
  metadata-rich pattern preservation for `multi-agent-collaboration` and
  `memory-augmented-agent`.

## Slice 3 — Validation engine

- [ ] T3.1 Validate required runtime manifest fields: `format_version`,
      `package_type`, `package_id`, `entrypoint`, `packaging`, `nodes`, and
      `edges`.
- [ ] T3.2 Validate supported enums for initial scope: `format_version: 1`,
      `package_type: dynamic_agent_design`, observed node kinds, decision
      subtypes, and edge kinds.
- [ ] T3.3 Validate node IDs are unique and every edge endpoint references an
      existing node.
- [ ] T3.4 Validate every `tool_use_step` references an available manifest or
      external tool-index tool.
- [ ] T3.5 Validate every `llm_step` has prompt data or a prompt source.
- [ ] T3.6 Validate external `tool-index.yaml` structure: `format_version`,
      `index_type`, `tools`, and `skills`.
- [ ] T3.7 Add tests for clear errors on missing artifacts, malformed schemas,
      unsupported versions, inconsistent nodes, and missing tools.

## Slice 4 — Repository-owned tool registry

- [ ] T4.1 Define `ToolDefinition`, `RegisteredTool`, `ToolResult`, and a
      `ToolRegistry` protocol.
- [ ] T4.2 Implement `InMemoryToolRegistry` for tests and simple callers.
- [ ] T4.3 Implement conversion from registry tool definitions to OpenAI tool
      schema.
- [ ] T4.4 Implement tool invocation dispatch by manifest `tool_id`.
- [ ] T4.5 Preserve side-effect metadata, approval metadata, timeout/retry
      policy, and failure behavior in registry data structures.
- [ ] T4.6 Add tests for lookup, schema conversion, successful invocation,
      missing tools, bad inputs, and tool failures.

## Slice 5 — OpenAI client adapter

- [ ] T5.1 Define the runtime's minimal OpenAI client protocol for injected
      fake/stub clients.
- [ ] T5.2 Implement the default adapter using the official `openai` Python
      package.
- [ ] T5.3 Implement request construction for rendered messages and optional
      OpenAI tool schemas.
- [ ] T5.4 Normalize model responses into internal result/event structures.
- [ ] T5.5 Surface OpenAI/model failures as project-specific errors.
- [ ] T5.6 Add tests using fake clients only; no live API calls in unit tests.

## Slice 6 — Workflow executor

- [ ] T6.1 Implement execution state for prompt, node inputs, node outputs,
      tool results, final result, and errors.
- [ ] T6.2 Implement `llm_step` prompt rendering and model-call execution.
- [ ] T6.3 Implement `tool_use_step` input resolution, registry dispatch, output
      recording, and configured failure behavior.
- [ ] T6.4 Implement `decision_step` with `decision_subtype: llm_route`.
- [ ] T6.5 Implement `sequential` and `branch` control-flow edges.
- [ ] T6.6 Fail clearly for unsupported node kinds, decision subtypes, or edge
      semantics.
- [ ] T6.7 Add fake-client/fake-tool end-to-end tests for successful workflow,
      partial failure, and final-result return behavior.

## Slice 7 — CLI and documentation

- [ ] T7.1 Add a CLI entry point for loading artifacts and running a workflow
      from a prompt.
- [ ] T7.2 Support CLI options for `agent-design.md`, runtime YAML, Mermaid
      graph, optional `tool-index.yaml`, and prompt input.
- [ ] T7.3 Return final output on success and clear non-zero errors on loading,
      validation, registry, model, or execution failure.
- [ ] T7.4 Add CLI tests using local fixtures and fake clients/tools.
- [ ] T7.5 Update README with concrete API and CLI usage.
- [ ] T7.6 Run full available validation and update memory bank after the first
      meaningful implementation milestone.

## Cross-Cutting Validation Tasks

- [ ] V1. Keep unit tests free of live OpenAI API calls.
- [ ] V2. Run `poetry check` after package/dependency changes.
- [ ] V3. Run targeted `pytest` after each implemented slice once tests exist.
- [ ] V4. Run `pre-commit run --files <changed files>` before scoped commits.
- [ ] V5. Track drift: update `spec.md`, `plan.md`, or this task list when
      implementation reveals changed requirements, architecture, or task order.
