# Active Context

## Current Focus

- Repository bootstrap/specification work has been refreshed after committing the
  SDD spec update that selects the official `openai` Python package and a
  repository-owned tool registry pattern.

## Current Status

- Done:
  - Inspected repository top-level files.
  - Reviewed `pyproject.toml`, `.pre-commit-config.yaml`, `.mise.toml`,
    `.flake8`, `.isort.cfg`, `.gitignore`, and `env_setup`.
  - Confirmed no Python, Markdown, or RST source/docs files were present before
    creating the memory bank.
  - Captured user-confirmed product intent for the library.
  - Committed project configuration in `ad3eb90`.
  - Committed build and package configuration in `ed7917f`.
  - Committed memory-bank baseline in `c7f292b`.
  - Committed dynamic agent runner specification in `b1182e9`.
  - Committed README runtime-direction update in `c9cd13c`.
  - Committed memory-bank runtime-direction refresh in `4e69ea9`.
  - Committed spec update selecting the official `openai` package and custom
    registry direction in `b247e11`.
- In progress:
  - No source implementation work is currently in progress.
- Not started:
  - Source layout, implementation, tests, and concrete tool registry design.

## Important Current Facts

- No source code is present outside configuration and environment files.
- Product purpose is confirmed by user instruction: read generated agent workflow
  artifacts, use the official `openai` Python package for default model
  execution, use a repository-owned tool registry pattern for tool calls, run
  from a prompt, and return the final result.
- `ai-tools-core` / `openai-tools-core` and `ocihelper` are not part of the
  intended initial runtime implementation direction.
- Concrete architecture and public API remain unimplemented.
- Latest observed branch history includes:
  - `b247e11 docs(spec): use openai package runtime direction`
  - `4e69ea9 docs(memory-bank): refresh runtime direction context`
  - `c9cd13c docs(readme): document ai-tools runtime direction`
  - `b1182e9 docs(spec): add dynamic agent runner specification`
  - `c7f292b docs(memory-bank): add project memory baseline`
- Current uncommitted dependency files are `pyproject.toml` and `poetry.lock`.
  Earlier dependency changes removed `ocihelper` and retained `ai-tools-core`,
  but the latest spec direction now expects the official `openai` package and no
  required `ai-tools-core` dependency.

## Next Steps

- Reconcile dependency/lock changes with the latest spec direction when ready:
  add the official `openai` package and remove required `ai-tools-core` if that
  matches the next implementation slice.
- When implementation begins, update `systemPatterns.md` and `progress.md` with
  observed source layout and behavior.
