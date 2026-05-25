# dynamic-agent-runner Task List

## Status

- State: Slice 7 complete; ready for post-CLI follow-on planning
- Source spec: `specs/dynamic-agent-runner/spec.md`
- Technical plan: `specs/dynamic-agent-runner/plan.md`
- Readiness verdict: ready for a narrow readiness/scaffold slice only; not ready
  for unrestricted runtime implementation
- Next active slice: post-Slice 7 follow-on planning

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

- [x] T3.1 Validate required runtime manifest fields: `format_version`,
      `package_type`, `package_id`, `entrypoint`, `packaging`, `nodes`, and
      `edges`.
- [x] T3.2 Validate supported enums for initial scope: `format_version: 1`,
      `package_type: dynamic_agent_design`, observed node kinds, decision
      subtypes, and edge kinds.
- [x] T3.3 Validate node IDs are unique and every edge endpoint references an
      existing node.
- [x] T3.4 Validate every `tool_use_step` references an available manifest or
      external tool-index tool. Superseded for execution by Slice 4 registry
      semantics: callable registry entries are authoritative.
- [x] T3.5 Validate every `llm_step` has prompt data or a prompt source.
- [x] T3.6 Validate external `tool-index.yaml` structure: `format_version`,
      `index_type`, `tools`, and `skills`.
- [x] T3.7 Add tests for clear errors on missing artifacts, malformed schemas,
      unsupported versions, inconsistent nodes, and missing tools.

## Slice 3 Completion Evidence

- `src/dynamic_agent_runner/validation.py` validates required manifest fields,
  supported enum values, node identity, edge references, tool references, LLM
  prompt presence, and external tool-index structure. Slice 4 must reconcile
  this with the clarified registry-authoritative execution semantics.
- `load_agent_workflow(...)` now validates loaded artifacts before returning
  them for later execution slices.
- `tests/test_validation.py` covers passing validation, required-field failures,
  unsupported enum failures, duplicate node IDs, bad edge endpoints, missing
  entrypoints, unknown tool references, missing LLM prompts, and malformed tool
  indexes.

## Slice 4 — Repository-owned tool registry

- [x] T4.1 Define `ToolDefinition`, `RegisteredTool`, `ToolResult`, and a
      `ToolRegistry` protocol.
- [x] T4.2 Implement `InMemoryToolRegistry` for tests and simple callers.
- [x] T4.3 Implement conversion from registry tool definitions to OpenAI tool
      schema.
- [x] T4.4 Implement tool invocation dispatch by manifest `tool_id`.
- [x] T4.5 Preserve side-effect metadata, approval metadata, timeout/retry
      policy, and failure behavior in registry data structures.
- [x] T4.6 Add runtime tool overrides for adding, replacing, disabling, and
      restricting or extending tools globally or per `llm_step` without mutating
      generated agent-design artifacts.
- [x] T4.7 Validate override consistency, including unknown base tools,
      malformed added tools, disabled tools still required by `tool_use_step`
      nodes, and overrides targeting non-`llm_step` nodes.
- [x] T4.8 Reconcile validation so `tool_use_step` execution dependencies must
      resolve to the effective callable registry; manifest and `tool-index.yaml`
      entries are metadata and do not make a tool callable by themselves.
- [x] T4.9 Add opt-in built-in default tool-pack support, starting with a
      read-only `local_workspace` pack for `read_file`, `list_files`,
      `search_files`, and `inspect_path` constrained to approved workspace roots.
- [x] T4.10 Keep write and command tools out of the default enabled set; if
      introduced, model them as separate opt-in approval-aware packs.
- [x] T4.11 Add tests for lookup, schema conversion, successful invocation,
      missing tools, bad inputs, and tool failures.
- [x] T4.12 Add tests for override layering, effective registry additions,
      replacement definitions, disabled tools, and per-node tool exposure.
- [x] T4.13 Add tests for built-in pack enablement, disabled-by-default behavior,
      workspace path restrictions, and node-reference requirements.

## Slice 4 Completion Evidence

- `src/dynamic_agent_runner/registry.py` defines the repository-owned registry
  protocol, `RegisteredTool`, `ToolResult`, runtime override models,
  `InMemoryToolRegistry`, OpenAI tool schema conversion, registry invocation,
  registry-authoritative tool reference validation, and the opt-in read-only
  `local_workspace` built-in tool pack.
- `src/dynamic_agent_runner/validation.py` accepts an optional callable registry
  during workflow validation so `tool_use_step` dependencies can be checked
  against executable registry entries instead of metadata-only tool-index entries.
- `load_agent_workflow(...)` accepts an optional `tool_registry` for validation
  while still avoiding workflow execution.
- `tests/test_registry.py` covers lookup, OpenAI schema conversion, invocation,
  missing tools, bad inputs, tool failures, runtime override layering,
  disabled-tool validation, registry-authoritative tool references,
  built-in pack enablement, workspace path restrictions, and node-reference
  requirements.

## Slice 5 — OpenAI client adapter

- [x] T5.1 Define the runtime's minimal OpenAI client protocol for injected
      fake/stub clients.
- [x] T5.2 Implement the default adapter using the official `openai` Python
      package.
- [x] T5.3 Implement request construction for rendered messages and optional
      OpenAI tool schemas.
- [x] T5.4 Normalize model responses into internal result/event structures.
- [x] T5.5 Surface OpenAI/model failures as project-specific errors.
- [x] T5.6 Add tests using fake clients only; no live API calls in unit tests.

## Slice 5 Completion Evidence

- `src/dynamic_agent_runner/openai_client.py` defines the runtime's minimal
  OpenAI client protocol, request and response dataclasses, lazy default OpenAI
  client construction, and `OpenAIClientAdapter` for the official Responses API
  boundary.
- `build_openai_request(...)` constructs model requests from rendered messages,
  optional OpenAI tool schemas, tool choice, response format, and extra model
  parameters.
- `normalize_openai_response(...)` extracts model text and function-tool calls
  into internal `ModelResponse` and `ModelToolCall` structures.
- Adapter failures are wrapped in `ModelExecutionError` so callers see
  project-specific model errors.
- `tests/test_openai_client.py` uses fake clients only and covers request
  construction, injected-client execution, response normalization, error
  wrapping, and input validation.

## Slice 6 — Workflow executor

- [x] T6.1 Implement execution state for prompt, node inputs, node outputs,
      tool results, final result, and errors.
- [x] T6.2 Implement `llm_step` prompt rendering and model-call execution.
- [x] T6.3 Implement `tool_use_step` input resolution, registry dispatch, output
      recording, and configured failure behavior.
- [x] T6.4 Implement `decision_step` with `decision_subtype: llm_route`.
- [x] T6.5 Implement `sequential` and `branch` control-flow edges.
- [x] T6.6 Fail clearly for unsupported node kinds, decision subtypes, or edge
      semantics.
- [x] T6.7 Add fake-client/fake-tool end-to-end tests for successful workflow,
      partial failure, and final-result return behavior.

## Slice 6 Completion Evidence

- `src/dynamic_agent_runner/executor.py` defines workflow execution state,
  execution records, final result objects, and `execute_workflow(...)`.
- `llm_step` execution renders prompt templates, exposes node tools through the
  registry-to-OpenAI schema path, and calls the Slice 5 OpenAI adapter boundary.
- `tool_use_step` execution resolves inputs, dispatches through the Slice 4
  registry, records structured tool results, and honors error/fallback failure
  behavior.
- `decision_step` with `decision_subtype: llm_route` extracts a route from model
  or JSON-like output and follows matching branch edges.
- Sequential and branch control-flow edges are implemented; unsupported node,
  decision, and edge configurations fail with `WorkflowExecutionError`.
- `run_agent_workflow(...)` now loads, validates, executes, and returns the final
  workflow result while `execute_workflow(...)` remains available for detailed
  state inspection.
- `tests/test_executor.py` uses fake clients and fake tools only and covers
  successful workflow execution, tool failure behavior, branch routing, public
  API final-result behavior, and step-limit failures.

## Slice 7 — CLI and documentation

- [x] T7.1 Add a CLI entry point for loading artifacts and running a workflow
      from a prompt.
- [x] T7.2 Support CLI options for `agent-design.md`, runtime YAML, Mermaid
      graph, optional `tool-index.yaml` metadata, registry configuration, and
      prompt input.
- [x] T7.3 Return final output on success and clear non-zero errors on loading,
      validation, registry, model, or execution failure.
- [x] T7.4 Add CLI tests using local fixtures and fake clients/tools.
- [x] T7.5 Update README with concrete API and CLI usage.
- [x] T7.6 Run full available validation and update memory bank after the first
      meaningful implementation milestone.

## Slice 7 Completion Evidence

- `src/dynamic_agent_runner/cli.py` defines `main(...)`, `build_parser()`, and
  `console_main()` for running generated workflow artifacts from the command
  line.
- `pyproject.toml` exposes the `dynamic-agent-runner` console script.
- CLI options cover runtime manifest, agent design, Mermaid graph, optional tool
  index metadata, prompt text, prompt file, stdin prompt input, max steps, and
  the opt-in read-only local workspace registry pack via `--workspace-root`.
- The CLI prints the final workflow result to stdout and reports runtime-specific
  errors to stderr with exit code `1`.
- `tests/test_cli.py` uses local fixture artifacts and fake OpenAI clients only;
  it covers path-based execution, prompt-file input, stdin input, missing prompt
  errors, and execution error reporting.
- `README.md` now documents concrete Python API and CLI usage.

## Cross-Cutting Validation Tasks

- [ ] V1. Keep unit tests free of live OpenAI API calls.
- [ ] V2. Run `poetry check` after package/dependency changes.
- [ ] V3. Run targeted `pytest` after each implemented slice once tests exist.
- [ ] V4. Run `pre-commit run --files <changed files>` before scoped commits.
- [ ] V5. Track drift: update `spec.md`, `plan.md`, or this task list when
      implementation reveals changed requirements, architecture, or task order.
