# Progress

## Working

- Baseline project configuration exists:
  - Python/Poetry package metadata in `pyproject.toml`
  - dependency lock file in `poetry.lock`
  - mise local environment configuration in `.mise.toml`
  - shell environment helper in `env_setup`
  - lint and pre-commit configuration files
- Product intent is documented in `README.md`.
- Project configuration commit exists:
  `ad3eb90 chore(config): add project configuration`.
- Build configuration commit exists:
  `ed7917f build: add OCI build configuration`.
- Memory-bank baseline commit exists:
  `c7f292b docs(memory-bank): add project memory baseline`.
- SDD spec commit exists:
  `b1182e9 docs(spec): add dynamic agent runner specification`.
- README runtime-direction commit exists:
  `c9cd13c docs(readme): document ai-tools runtime direction`.

## In Flight

- No source implementation work is currently in flight.
- Dependency changes are currently uncommitted: `pyproject.toml` and
  `poetry.lock` remove `ocihelper` and keep `ai-tools-core`.

## Remaining

- Add or identify the actual source layout.
- Define the concrete public Python API.
- Implement reading of definition YAML, Mermaid diagram, and tool index.
- Implement workflow execution through OpenAI-compatible interfaces and
  `ai-tools-core` tool handling.
- Add tests and validation commands once code exists.
- Expose a CLI in addition to the library API, per the current spec.
- Update the memory bank after the first meaningful implementation milestone.

## Risks or Follow-ups

- The repository currently lacks source code, so architecture sections
  intentionally avoid detailed implementation claims.
- Pre-commit passed for the project-configuration commit and build-configuration
  commit, the spec commit, and the README runtime-direction commit. Memory-bank
  pre-commit validation should be recorded in the memory-bank refresh commit
  result.
- Future sessions should verify artifact schemas before implementing parser or
  execution behavior.
- Future implementation should start with OpenAI-compatible interfaces and
  `ai-tools-core`; `ocihelper` is intentionally being removed.
