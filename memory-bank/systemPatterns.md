# System Patterns

## Current Architecture

- The repository now has an initial `src/` package scaffold:
  - `src/dynamic_agent_runner/__init__.py` reserves public exports
  - `src/dynamic_agent_runner/api.py` reserves `load_agent_workflow` and
    `run_agent_workflow` placeholders
  - `src/dynamic_agent_runner/errors.py` defines project-specific exception
    types
- Tests currently contain an import smoke test at `tests/test_import.py`.
- Current repository structure remains intentionally minimal while artifact
  loader/runtime behavior is implemented slice-by-slice.

## Observed Patterns

- Python package managed with Poetry.
- Source layout uses `src/dynamic_agent_runner/` as configured in
  `pyproject.toml`.
- Local development environment managed by mise.
- `env_setup` adds `lib`, `src`, and `bin` to `PYTHONPATH`/`PATH` when those
  directories exist.
- Ruff, flake8, isort, and pre-commit are configured.
- Initial public API uses placeholders that raise `NotImplementedError` until
  later implementation slices add loaders, validation, registry, adapter, and
  executor behavior.
- Error taxonomy starts with a base `DynamicAgentRunnerError` and specific
  loading, validation, registry, model, and workflow execution errors.

## Boundaries and Unknowns

- Runtime manifest model: not implemented yet.
- Artifact loading behavior: not implemented yet.
- Validation engine: not implemented yet.
- Tool registry protocol and concrete registry: not implemented yet.
- OpenAI client adapter: not implemented yet.
- Workflow executor and CLI: not implemented yet.

## Guidance for Future Work

- Continue from Slice 2 in `specs/dynamic-agent-runner/tasks.md`.
- Keep implementation aligned with the artifact-interpreter framing rather than
  expanding into a generic agent framework.
- Keep OpenAI API calls behind a small adapter boundary and keep unit tests free
  of live model calls.
- Update this file as concrete modules, entry points, and architectural
  boundaries become real.
