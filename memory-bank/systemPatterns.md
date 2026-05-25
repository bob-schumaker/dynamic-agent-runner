# System Patterns

## Current Architecture

- No application architecture is visible yet because no source tree is present.
- Current repository structure is configuration-first:
  - `pyproject.toml` for package metadata, dependencies, and Ruff settings
  - `poetry.lock` for locked dependencies
  - `ocibuild*.conf` for OCI build, repository, team, and notification metadata
  - `python-build-system.py` for Poetry/PDM-oriented OCI build execution
  - `.mise.toml` for local Python, Poetry, virtualenv, and shell hooks
  - `env_setup` for sourced shell environment setup
  - `.pre-commit-config.yaml`, `.flake8`, and `.isort.cfg` for lint/check
    tooling

## Observed Patterns

- Python package managed with Poetry.
- Local development environment managed by mise.
- `env_setup` adds `lib`, `src`, and `bin` to `PYTHONPATH`/`PATH` when those
  directories exist, suggesting future code may use one or more of those
  directories.
- Ruff, flake8, isort, and pre-commit are configured, though no Python files
  were present at initial memory-bank creation.
- OCI build configuration packages wheels/source distributions and publishes to
  configured release/development repositories.

## Boundaries and Unknowns

- Domain model: unknown.
- Runtime entry point: unknown.
- Testing layout: unknown.
- Packaging layout: Poetry package metadata and lock file exist; source package
  layout is still unknown.
- Agent framework or provider assumptions: unknown.

## Guidance for Future Work

- Inspect or create source layout deliberately before adding implementation.
- Keep framework and provider assumptions explicit if this becomes an agent
  runner implementation.
- Update this file once concrete modules, entry points, or architectural
  boundaries exist.
