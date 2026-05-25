# System Patterns

## Current Architecture

- The repository now has an initial `src/` package scaffold:
  - `src/dynamic_agent_runner/__init__.py` reserves public exports
  - `src/dynamic_agent_runner/api.py` exposes `load_agent_workflow` for artifact
    loading while reserving `run_agent_workflow` for later executor slices
  - `src/dynamic_agent_runner/artifacts.py` loads generated workflow artifacts
  - `src/dynamic_agent_runner/models.py` preserves internal artifact metadata
  - `src/dynamic_agent_runner/validation.py` validates loaded artifact
    relationships and supported `format_version: 1` enum values
  - `src/dynamic_agent_runner/openai_client.py` isolates the official OpenAI
    client behind a small fake-client-compatible adapter boundary
  - `src/dynamic_agent_runner/executor.py` composes loaded workflows, registry
    tools, and the OpenAI adapter into executable workflow runs
  - `src/dynamic_agent_runner/errors.py` defines project-specific exception
    types
- Tests currently contain an import smoke test at `tests/test_import.py`,
  artifact loader tests at `tests/test_artifacts.py`, validation tests at
  `tests/test_validation.py`, registry tests at `tests/test_registry.py`, and
  OpenAI adapter tests at `tests/test_openai_client.py`, and executor tests at
  `tests/test_executor.py`.
- Current repository structure has loader/model/validation/registry/adapter/
  executor behavior; CLI behavior remains a future slice.

## Observed Patterns

- Python package managed with Poetry.
- Source layout uses `src/dynamic_agent_runner/` as configured in
  `pyproject.toml`.
- Local development environment managed by mise.
- `env_setup` adds `lib`, `src`, and `bin` to `PYTHONPATH`/`PATH` when those
  directories exist.
- Ruff, flake8, isort, and pre-commit are configured.
- `load_agent_workflow(...)` loads generated workflow artifacts without
  executing them, then validates the loaded bundle before returning it.
- `run_agent_workflow(...)` now loads, validates, executes, and returns the final
  workflow result; `execute_workflow(...)` exposes detailed execution state.
- Error taxonomy starts with a base `DynamicAgentRunnerError` and specific
  loading, validation, registry, model, and workflow execution errors.
- Runtime artifact design preserves documented supported agent-pattern IDs as
  manifest metadata instead of expanding the primitive node taxonomy.
- Pattern-specific structures should be modeled through `patterns_present`,
  `participant_groups`, `roles`, `modes`, `phases`, declared tools, state,
  execution policy, and control-flow edges.
- Artifact inputs support path, raw-string, and already-parsed mapping forms for
  runtime manifests and tool indexes. Mermaid graphs and agent designs support
  path or raw-string inputs.
- Validation fails closed for missing required manifest fields, unsupported
  manifest/tool-index enum values, duplicate or missing node IDs, bad edge
  endpoints, unknown metadata tool references, and LLM nodes without prompt or
  prompt-source metadata. With an effective registry, tool-use dependencies can
  be validated against callable registry entries.
- `registry.py` defines runtime tool overrides as overlay inputs that can add,
  replace, disable, or restrict tools globally or per `llm_step` without mutating
  generated artifacts.
- Built-in default tools are explicit opt-in registry packs; the current
  `local_workspace` pack is read-only and not an ambient global capability.
- `openai_client.py` defines a protocol around `client.responses.create(...)`,
  so unit tests can inject fake clients without live OpenAI API calls.
- OpenAI request construction uses `input` messages plus optional `tools`,
  `tool_choice`, `response_format`, and extra model parameters.
- OpenAI response normalization extracts text and function calls into internal
  `ModelResponse` / `ModelToolCall` structures while preserving the raw response.
- `executor.py` maintains `WorkflowExecutionState` with prompt, node inputs,
  node outputs, tool results, execution records, errors, and final result.
- Executor control flow currently supports sequential edges and branch edges for
  `decision_step` nodes with `decision_subtype: llm_route`.
- Executor unit tests use fake OpenAI clients and fake registry tools only;
  no live OpenAI API calls are required.

## Boundaries and Unknowns

- Runtime manifest model: implemented for loader/model scope.
- Artifact loading behavior: implemented for Slice 2 scope.
- Supported pattern metadata preservation: implemented for loader/model scope.
- Validation engine: implemented for Slice 3 scope.
- Tool registry protocol and concrete registry: implemented for Slice 4 scope.
- OpenAI client adapter: implemented for Slice 5 scope.
- Workflow executor: implemented for Slice 6 scope.
- CLI: not implemented yet.

## Guidance for Future Work

- Continue from Slice 7 in `specs/dynamic-agent-runner/tasks.md`.
- Keep implementation aligned with the artifact-interpreter framing rather than
  expanding into a generic agent framework.
- Keep primitive runtime node kinds limited to `llm_step`, `tool_use_step`, and
  `decision_step` unless a later format version changes the contract.
- In Slice 7, add the CLI and documentation on top of the existing public API and
  executor without widening executor semantics beyond the committed task scope.
- Update this file as concrete modules, entry points, and architectural
  boundaries become real.
