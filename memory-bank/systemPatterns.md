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
  - `src/dynamic_agent_runner/errors.py` defines project-specific exception
    types
- Tests currently contain an import smoke test at `tests/test_import.py` and
  artifact loader tests at `tests/test_artifacts.py`, plus validation tests at
  `tests/test_validation.py`.
- Current repository structure has loader/model/validation behavior only;
  registry, adapter, executor, and CLI behavior remain future slices.

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
- `run_agent_workflow(...)` still raises `NotImplementedError` until later
  validation, registry, adapter, and executor slices are implemented.
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
  endpoints, unknown tool references, and LLM nodes without prompt or
  prompt-source metadata. Slice 4 will update tool semantics so execution depends
  on callable registry entries, not metadata-only tool-index presence.
- Slice 4 planning now defines runtime tool overrides as overlay inputs that can
  add, replace, disable, or restrict tools globally or per `llm_step` without
  mutating generated artifacts.
- Built-in default tools, if provided, should be explicit opt-in registry packs;
  the initial pack should be read-only `local_workspace` tools and not ambient
  global capabilities.

## Boundaries and Unknowns

- Runtime manifest model: implemented for loader/model scope.
- Artifact loading behavior: implemented for Slice 2 scope.
- Supported pattern metadata preservation: implemented for loader/model scope.
- Validation engine: implemented for Slice 3 scope.
- Tool registry protocol and concrete registry: not implemented yet; Slice 4
  scope now includes registry-authoritative tool availability, runtime tool
  overrides, and opt-in built-in default tool packs.
- OpenAI client adapter: not implemented yet.
- Workflow executor and CLI: not implemented yet.

## Guidance for Future Work

- Continue from Slice 4 in `specs/dynamic-agent-runner/tasks.md`.
- Keep implementation aligned with the artifact-interpreter framing rather than
  expanding into a generic agent framework.
- Keep primitive runtime node kinds limited to `llm_step`, `tool_use_step`, and
  `decision_step` unless a later format version changes the contract.
- In Slice 4, implement the repository-owned tool registry without yet adding
  OpenAI adapter or workflow executor behavior. Include callable registry lookup,
  optional metadata enrichment from manifest/tool-index data, runtime overrides,
  and opt-in built-in `local_workspace` tools.
- Keep OpenAI API calls behind a small adapter boundary and keep unit tests free
  of live model calls.
- Update this file as concrete modules, entry points, and architectural
  boundaries become real.
