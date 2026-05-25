# Progress

## Working

- Baseline project configuration exists:
  - Python/Poetry package metadata in `pyproject.toml`
  - dependency lock file in `poetry.lock`
  - mise local environment configuration in `.mise.toml`
  - shell environment helper in `env_setup`
  - lint and pre-commit configuration files
- Product intent and current implementation-readiness state are documented in
  `README.md`.
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
- Memory-bank runtime-direction refresh commit exists:
  `4e69ea9 docs(memory-bank): refresh runtime direction context`.
- Spec update commit exists:
  `b247e11 docs(spec): use openai package runtime direction`.
- Memory-bank OpenAI runtime direction refresh commit exists:
  `bef8817 docs(memory-bank): record openai runtime direction`.
- Implementation-readiness gate commit exists:
  `2979342 docs(spec): record implementation readiness gate`.
- Slice 0 completion commit exists:
  `ea5a88a docs(spec): mark readiness checkpoint complete`.
- Slice 1 package scaffold commit exists:
  `d2766c0 feat(package): add initial runner scaffold`.
- Supported pattern metadata planning update commit exists:
  `db13d29 docs(spec): record supported agent patterns`.
- Slice 2 artifact loader commit exists:
  `64ad379 feat(artifacts): add workflow artifact loaders`.
- Slice 3 validation engine commit exists:
  `3469d49 feat(validation): add artifact validation engine`.
- Slice 4 registry scope update commit exists:
  `07edab0 docs(spec): expand slice 4 registry scope`.
- Slice 4 registry foundation commit exists:
  `cba3f43 feat(registry): add tool registry foundation`.
- Slice 5 OpenAI client adapter commit exists:
  `42f8d15 feat(openai): add client adapter boundary`.
- Slice 6 workflow executor commit exists:
  `4ce8c67 feat(executor): add workflow execution engine`.
- Agent-pattern fixture commit exists:
  `ef1fd38 test(fixtures): add agent pattern runtime packages`.
- Artifact loading now works for runtime YAML, optional Mermaid graph, optional
  `agent-design.md`, and optional `tool-index.yaml` inputs.
- `load_agent_workflow(...)` now loads generated artifacts without executing
  workflows, validates loaded artifacts, and returns the validated bundle.
- Validation now covers required manifest fields, supported enum values, node ID
  uniqueness, edge references, tool-use references, LLM prompt presence, and
  external tool-index structure. Slice 4 planning now clarifies that execution
  requires callable registry entries, with `tool-index.yaml` acting as optional
  metadata.
- The OpenAI adapter boundary now supports fake-client-compatible Responses API
  calls, request construction from rendered messages and optional tool schemas,
  response normalization, and `ModelExecutionError` wrapping.
- The workflow executor now supports execution state, LLM steps, tool-use steps,
  `llm_route` decisions, sequential and branch control flow, public
  `run_agent_workflow(...)` final-result execution, and fake-client/fake-tool
  executor tests.
- The repository now has hello-world runtime package fixtures for all 11
  documented supported agent patterns under `tests/fixtures/agent-patterns/`,
  with load/validation coverage in `tests/test_agent_pattern_fixtures.py`.

## In Flight

- No source implementation work is currently in flight.
- Slice 7 — CLI and documentation — is the next active implementation slice.

## Remaining

- Implement Slice 7 — CLI and documentation:
  - add a CLI entry point for loading artifacts and running a workflow from a
    prompt
  - support CLI options for `agent-design.md`, runtime YAML, Mermaid graph,
    optional `tool-index.yaml` metadata, registry configuration, and prompt input
  - return final output on success and clear non-zero errors on loading,
    validation, registry, model, or execution failure
  - add CLI tests using local fixtures and fake clients/tools
  - update README with concrete API and CLI usage
- Extend from the completed loader, validation, registry, OpenAI adapter, and
  executor foundation into the CLI slice.
- Use the all-pattern hello-world fixtures as the broad pattern test surface for
  future CLI and compatibility coverage.
- Update the memory bank after the first meaningful implementation milestone.

## Risks or Follow-ups

- Loader, validation, registry, OpenAI adapter, and executor source now exist,
  but architecture sections should remain conservative until CLI behavior exists.
- Slice 6 is complete, but unrestricted runtime implementation should still
  proceed slice-by-slice from the committed task list.
- Future sessions should verify artifact schemas before implementing parser or
  execution behavior.
- Supported agent-pattern IDs are preserved by loader/model work; full executor
  support still depends on later primitive node, edge, tool, policy, and adapter
  implementation.
- Future implementation should start with the official `openai` package and a
  repository-owned tool registry pattern; `ocihelper`, `ai-tools-core`, and
  `openai-tools-core` are intentionally not required by the latest spec.
- Slice 4 preserves the distinction between optional tool-index metadata and
  executable registry tools; metadata-only tools cannot satisfy runtime tool
  dependencies.
- Slice 5 preserves the OpenAI SDK behind a small adapter boundary and keeps unit
  tests free of live model calls.
- Slice 6 implements minimal executor semantics only; more advanced edge kinds,
  policies, approvals, and tool-call loops remain future extension areas.
- The all-pattern fixtures validate package shape and pattern metadata coverage;
  they do not prove full runtime execution support for every pattern-specific
  behavior.
- Memory-bank pre-commit validation for this refresh should be recorded in the
  commit result.
