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
- Artifact loading now works for runtime YAML, optional Mermaid graph, optional
  `agent-design.md`, and optional `tool-index.yaml` inputs.
- `load_agent_workflow(...)` now loads generated artifacts without executing
  workflows, validates loaded artifacts, and returns the validated bundle.
- Validation now covers required manifest fields, supported enum values, node ID
  uniqueness, edge references, tool-use references, LLM prompt presence, and
  external tool-index structure. Slice 4 planning now clarifies that execution
  requires callable registry entries, with `tool-index.yaml` acting as optional
  metadata.

## In Flight

- No source implementation work is currently in flight.
- Slice 4 — repository-owned tool registry — is the next active implementation
  slice, with expanded registry-authoritative scope recorded in `07edab0`.

## Remaining

- Implement Slice 4 — repository-owned tool registry:
  - define `ToolDefinition`, `RegisteredTool`, `ToolResult`, and a
    `ToolRegistry` protocol
  - implement `InMemoryToolRegistry` for tests and simple callers
  - implement conversion from registry tool definitions to OpenAI tool schema
  - implement tool invocation dispatch by manifest `tool_id`
  - preserve side-effect metadata, approval metadata, timeout/retry policy, and
    failure behavior
  - add runtime tool overrides for adding, replacing, disabling, and per-node
    tool exposure changes
  - reconcile validation so `tool_use_step` dependencies resolve to callable
    registry entries rather than manifest/tool-index metadata alone
  - add opt-in built-in default tool-pack support, starting with a read-only
    `local_workspace` pack for `read_file`, `list_files`, `search_files`, and
    `inspect_path`
  - keep write and command tools out of the default enabled set unless modeled as
    separate opt-in approval-aware packs
  - add tests for lookup, schema conversion, successful invocation, missing
    tools, bad inputs, tool failures, override layering, built-in pack enablement,
    workspace path restrictions, and node-reference requirements
- Define the concrete public Python API beyond reserved placeholders.
- Implement workflow execution through the official `openai` Python package.
- Design and implement the repository-owned tool registry pattern, including
  registry-authoritative tool lookup, optional manifest/tool-index metadata
  enrichment, conversion to OpenAI tool schema, invocation dispatch, side-effect
  metadata, approval metadata, timeout/retry policy, override layering, built-in
  pack enablement, and structured result or failure reporting.
- Add tests and validation commands once code exists.
- Expose a CLI in addition to the library API, per the current spec.
- Update the memory bank after the first meaningful implementation milestone.

## Risks or Follow-ups

- Loader and validation source now exist, but architecture sections should remain
  conservative until registry and runtime execution behavior exist.
- Slice 3 is complete, but unrestricted runtime implementation should still
  proceed slice-by-slice from the committed task list.
- Future sessions should verify artifact schemas before implementing parser or
  execution behavior.
- Supported agent-pattern IDs are preserved by loader/model work; full executor
  support still depends on later primitive node, edge, tool, policy, and adapter
  implementation.
- Future implementation should start with the official `openai` package and a
  repository-owned tool registry pattern; `ocihelper`, `ai-tools-core`, and
  `openai-tools-core` are intentionally not required by the latest spec.
- Slice 4 must preserve the distinction between optional tool-index metadata and
  executable registry tools; metadata-only tools cannot satisfy runtime tool
  dependencies.
- Memory-bank pre-commit validation for this refresh should be recorded in the
  commit result.
