# Active Context

## Current Focus

- Repository bootstrap/specification work has been refreshed in the memory bank
  after committing the SDD spec and README runtime-direction update.

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
- In progress:
  - No source implementation work is currently in progress.
- Not started:
  - Source layout, implementation, and tests.

## Important Current Facts

- The working tree reported all top-level repository files as untracked at
  memory-bank creation time.
- No source code was present outside configuration and environment files.
- Product purpose is now confirmed by user instruction: read generated agent
  workflow artifacts, use OpenAI-compatible interfaces and `ai-tools-core`, run
  from a prompt, and return the final result.
- Concrete architecture and public API remain unimplemented.
- Latest observed branch history includes:
  - `c9cd13c docs(readme): document ai-tools runtime direction`
  - `b1182e9 docs(spec): add dynamic agent runner specification`
  - `c7f292b docs(memory-bank): add project memory baseline`
  - `ed7917f build: add OCI build configuration`
  - `ad3eb90 chore(config): add project configuration`
  - `0ffbb5e docs(readme): a description of the sweetmeat`
- Current uncommitted dependency direction changes remove `ocihelper` and keep
  `ai-tools-core` as the initial runtime/tooling dependency.

## Next Steps

- Commit the dependency/lock changes separately when ready.
- When implementation begins, update `systemPatterns.md` and `progress.md` with
  observed source layout and behavior.
