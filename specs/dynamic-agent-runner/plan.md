# dynamic-agent-runner Implementation Plan

## Goal

Implement the `dynamic-agent-runner` Python package described by
`specs/dynamic-agent-runner/spec.md`: load generated agent workflow artifacts,
validate their relationships, execute supported workflow nodes through the
official `openai` Python package, dispatch tools through a repository-owned tool
registry pattern, expose a public API and CLI, and return either a final result
or a clear error.

## Source Artifacts

- `specs/dynamic-agent-runner/spec.md` — feature source of truth.
- `README.md` — repository overview; aligned with the official `openai`
  package and repository-owned tool registry direction.
- `pyproject.toml` — package/dependency configuration; currently includes the
  official `openai` dependency and package include for `src/dynamic_agent_runner`.
- `memory-bank/` — durable project context; not authoritative over the spec.

## Current Repository State

- No source package exists yet.
- `pyproject.toml` and `poetry.lock` have uncommitted dependency/package metadata
  changes.
- `poetry check` passed after metadata cleanup.
- The package include points to `src/dynamic_agent_runner`, so the first
  implementation slice should scaffold that package before build validation.
- README has been refreshed to align with the official `openai` package and
  repository-owned registry direction before deeper runtime implementation.
- A 3-round implementation-readiness debate concluded this plan is ready only
  for a narrow readiness/scaffold slice, not unrestricted runtime coding.

## Technical Approach

### Package layout

Create a conventional `src/` package layout:

```text
src/dynamic_agent_runner/
  __init__.py
  api.py
  artifacts.py
  errors.py
  models.py
  validation.py
  registry.py
  openai_client.py
  executor.py
  cli.py

tests/
  fixtures/
  test_artifacts.py
  test_validation.py
  test_registry.py
  test_openai_client.py
  test_executor.py
  test_cli.py
```

Initial implementation may merge modules if simpler, but should preserve these
boundaries conceptually.

### Public API

Expose a small public API from `dynamic_agent_runner`:

- `load_agent_workflow(...)` — parse and validate artifacts without executing.
- `run_agent_workflow(...)` — load, validate, execute, and return a final result.
- `ToolRegistry` / registry protocol types for caller-provided tools.
- clear exception types for loading, validation, registry, model, and execution
  failures.

Keep API names aligned with `README.md` and update README when the API is
implemented or renamed.

### Artifact loading

Support input forms from the spec:

- filesystem paths
- raw strings
- already-parsed objects

Initial parser responsibilities:

- runtime YAML for `format_version: 1`
- Mermaid graph text loading and reference resolution
- optional `tool-index.yaml`
- lightweight `agent-design.md` reference checks for runtime manifest and Mermaid
  graph mentions

Use strongly typed internal dataclasses or Pydantic models only if they reduce
complexity. Prefer standard-library dataclasses for the first slice unless schema
validation becomes too large.

### Validation

Validation should happen before execution and fail closed for unsupported or
inconsistent artifacts.

Initial checks:

- required runtime manifest fields are present
- `format_version == 1`
- `package_type == dynamic_agent_design`
- node IDs are unique
- edge endpoints reference existing nodes
- `tool_use_step` tool IDs resolve to manifest or external tool-index entries
- `llm_step` has prompt data or a resolvable prompt source
- Mermaid graph references the same node IDs where practical
- external `tool-index.yaml` has supported `format_version`, `index_type`,
  `tools`, and `skills` sections

### Tool registry pattern

Implement a repository-owned registry instead of depending on `ai-tools-core`.

Core concepts:

- `ToolDefinition` — manifest/tool-index metadata, JSON schema, side-effect and
  policy fields.
- `RegisteredTool` — callable adapter plus definition.
- `ToolRegistry` protocol — lookup by `tool_id`, list tools for an LLM step,
  convert registered tools to OpenAI tool schema, and invoke tools by ID.
- `InMemoryToolRegistry` — first concrete implementation for tests and simple
  callers.

Registry responsibilities:

- translate manifest/tool-index definitions into runtime-callable entries
- convert tool definitions to OpenAI tool schema
- validate required tool inputs using the declared input schema where practical
- record side-effect metadata, approval metadata, timeout/retry policy, and
  structured success/failure results
- fail clearly for missing tools, malformed tool inputs, and unapproved
  side-effecting tools

### OpenAI client adapter

Use the official `openai` Python package through a small adapter boundary.

Responsibilities:

- construct the default OpenAI client lazily from caller configuration or
  environment-supported defaults
- accept a protocol-compatible injected client for tests
- send rendered messages and optional tool schemas
- normalize model responses into internal execution events/results
- surface API/model failures as project-specific errors

The first implementation should use fake/stub clients in tests and avoid live
model calls in unit tests.

### Executor

Implement the minimum node execution needed for the observed example:

- `llm_step`
- `tool_use_step`
- `decision_step` with `decision_subtype: llm_route`
- `sequential` and `branch` edges

Keep unsupported node kinds, decision subtypes, and edge kinds explicit errors
until implemented.

Execution state should track:

- original user prompt
- rendered node inputs
- node outputs
- tool results
- final result
- errors and failure behavior

### CLI

Expose a CLI that can load artifacts and run the workflow:

```bash
dynamic-agent-runner run \
  --agent-design path/to/agent-design.md \
  --runtime path/to/agent-runtime.yaml \
  --graph path/to/agent-graph.mmd \
  --tool-index path/to/tool-index.yaml \
  --prompt "..."
```

Exact command shape may use `docopt-ng` or another existing dependency pattern,
but must support clear non-zero exits for loading, validation, model, registry,
and execution failures.

## Implementation Slices

0. **Planning and documentation readiness checkpoint**
   - keep `spec.md`, `plan.md`, and `tasks.md` consistent and tracked
   - align README with the official `openai` package and repository-owned tool
     registry direction
   - preserve the distinction between readiness/scaffold work and deeper runtime
     implementation

1. **Package scaffold and dependency alignment**
   - create `src/dynamic_agent_runner/`
   - add initial public exports and error types
   - ensure `pyproject.toml`, `poetry.lock`, and package layout agree
   - verify dependency/lockfile churn before committing it
   - confirm README remains aligned with the official `openai` package and
    repository-owned registry direction

2. **Artifact models and loaders**
   - parse runtime YAML, Mermaid text, optional tool index, and design document
   - support path, raw-string, and already-parsed-object inputs
   - add fixture-based tests

3. **Validation engine**
   - implement manifest, graph, tool-index, and relationship checks
   - add clear error objects/messages

4. **Repository-owned tool registry**
   - implement registry protocols, in-memory registry, schema conversion, and
     invocation dispatch
   - add tests for lookup, OpenAI schema conversion, tool invocation, and failure
     cases

5. **OpenAI adapter**
   - implement client protocol and default official `openai` adapter
   - add fake-client tests for request/response normalization and model failures

6. **Workflow executor**
   - implement `llm_step`, `tool_use_step`, `decision_step`, sequential flow,
     branch flow, state updates, and final-result return behavior
   - add end-to-end fake-client/fake-tool tests

7. **CLI and documentation**
   - add CLI entry point
   - update README usage examples
   - add CLI tests and validation notes

## Validation Strategy

Use staged validation as implementation grows:

- `poetry check`
- `python -m pytest` once tests exist
- targeted tests for each implementation slice
- `pre-commit run --files <changed files>` before scoped commits
- full `pre-commit run` before larger integration checkpoints

Unit tests must not require live OpenAI API calls. Use fake or stub clients for
model behavior and fake registries for tool behavior.

## Risks and Decisions

- README must remain aligned with the spec's official `openai` package and
  repository-owned registry direction; stale `ai-tools-core` language should not
  survive into implementation commits.
- `pyproject.toml` points to `src/dynamic_agent_runner`; builds may fail until
  the source package exists.
- Exact OpenAI SDK call shape should be isolated behind the adapter because SDK
  APIs may evolve.
- Tool schema validation depth should start pragmatic and become stricter as
  real generated manifests stabilize.
- Safety, authentication, logging, and redaction requirements remain expected
  drift points from the spec and should be promoted into artifacts when clarified.

## Implementation-Readiness Debate Result

A 3-round document-analysis debate reviewed `spec.md`, this plan, and
`tasks.md` for implementation readiness. The Judge passed the debate result with
a qualified verdict:

- The artifact set is not ready for unrestricted runtime implementation.
- The artifact set is ready for a narrow readiness/scaffold slice.
- Before parser, registry, OpenAI adapter, executor, or CLI runtime behavior, the
  repository should align stale docs, track planning artifacts, validate and
  commit dependency state, create the initial source package scaffold, add an
  import smoke test, and run targeted validation.

## Plan Gate

This plan is accepted as the current technical planning artifact for a narrow
readiness/scaffold slice. Deeper runtime implementation should wait until that
slice is complete and validated.
