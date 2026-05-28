# dynamic-agent-runner Implementation Plan

## Goal

Implement the `dynamic-agent-runner` Python package described by
`specs/dynamic-agent-runner/spec.md`: load generated agent workflow artifacts,
validate their relationships, execute supported workflow nodes through the
official `openai` Python package, dispatch tools through a repository-owned tool
registry pattern, expose a public API and CLI, and return either a final result
or a clear error.

## Source Artifacts

- `specs/dynamic-agent-runner/spec.md` — feature source of truth, now including
  runtime behavior overrides for per-node prompts and skill bindings.
- `README.md` — repository overview; aligned with the official `openai`
  package and repository-owned tool registry direction.
- `pyproject.toml` — package/dependency configuration; currently includes the
  official `openai` dependency and package include for `src/dynamic_agent_runner`.
- `memory-bank/` — durable project context; not authoritative over the spec.

## Current Repository State

- Slice 1 is complete and committed: the initial source package scaffold exists
  under `src/dynamic_agent_runner/` with public API placeholders, project error
  types, and an import smoke test.
- `pyproject.toml` and `poetry.lock` include the official `openai` dependency
  and package include for `src/dynamic_agent_runner`.
- `poetry check`, the import smoke test, targeted pytest, and targeted
  pre-commit passed for the package scaffold slice.
- README has been refreshed to align with the official `openai` package and
  repository-owned registry direction before deeper runtime implementation.
- A 3-round implementation-readiness debate concluded this plan is ready only
  for slice-by-slice implementation, not unrestricted runtime coding.
- The next active implementation slice is Slice 2: artifact models and loaders.
- Evaluation follow-up Slice A is complete and committed: the runtime now exposes
  `WorkflowExecutionContext` / `RunContext` as a stable execution envelope that
  groups a loaded workflow with runtime collaborators while preserving the
  existing `execute_workflow(workflow, ...)` call shape.

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
- optional `tool-index.yaml` metadata
- lightweight `agent-design.md` reference checks for runtime manifest and Mermaid
  graph mentions
- preservation of documented supported agent-pattern metadata from
  `patterns_present`
- preservation of structural metadata used by broader pattern shapes, including
  `participant_groups`, `modes`, `phases`, and `roles`

Use strongly typed internal dataclasses or Pydantic models only if they reduce
complexity. Prefer standard-library dataclasses for the first slice unless schema
validation becomes too large.

Supported agent patterns from the agent-development skill's
`references/examples/agent-pattern-examples.md` should be treated as manifest
classification metadata during loading, not as new primitive node kinds. Loader
models should preserve these pattern IDs without requiring executor support for
every pattern in the first implementation:

- `basic-reasoning-agent`
- `tool-based-function-calling-agent`
- `tool-server-or-mcp-style-agent`
- `computer-use-agent`
- `coding-agent`
- `speech-or-voice-agent`
- `workflow-orchestration-agent`
- `memory-augmented-agent`
- `simulation-or-test-bed-agent`
- `observer-or-monitoring-agent`
- `multi-agent-collaboration`

### Validation

Validation should happen before execution and fail closed for unsupported or
inconsistent artifacts.

Initial checks:

- required runtime manifest fields are present
- `format_version == 1`
- `package_type == dynamic_agent_design`
- node IDs are unique
- edge endpoints reference existing nodes
- `tool_use_step` tool IDs resolve to callable entries in the effective registry
- `llm_step` has prompt data or a resolvable prompt source
- Mermaid graph references the same node IDs where practical
- external `tool-index.yaml` metadata, when supplied, has supported
  `format_version`, `index_type`, `tools`, and `skills` sections

### Tool registry pattern

Implement a repository-owned registry instead of depending on `ai-tools-core`.

### Runtime behavior override pattern

Implement runtime behavior overrides as a sibling overlay to runtime tool
overrides. The generated runtime manifest remains the baseline source of truth,
while caller-provided override artifacts compute effective node behavior at
preparation or execution time.

Core concepts:

- `RuntimeBehaviorOverrides` — caller-provided override bundle loaded from path,
  raw YAML, or parsed mapping input.
- `PromptOverride` — explicit `replace`, `prepend`, and `append` operations for
  prompt fields such as `system`, `developer`, `user_template`, and
  `output_schema_ref`.
- `SkillReferenceOverride` — per-node `only`, `add`, and `remove` semantics for
  skill references.
- `SkillDefinition` or equivalent structured model — skill metadata with
  optional inline runtime `instructions` and `prompt_role` for initial execution
  support.
- Effective node behavior — a derived runtime view that combines the base node
  prompt, base node `skill_refs`, override skill references, inline skill
  instructions, and prompt patch operations without mutating `RuntimeNode.raw`.

Initial scope should support inline skill instructions only. Arbitrary
`SKILL.md` source-path resolution should remain deferred until a later scoped
slice defines trust, packaging, precedence, and file-loading rules.

Core concepts:

- `ToolDefinition` — manifest/tool-index metadata, JSON schema, side-effect and
  policy fields.
- `RegisteredTool` — callable adapter plus definition.
- `ToolRegistry` protocol — lookup by `tool_id`, list tools for an LLM step,
  convert registered tools to OpenAI tool schema, and invoke tools by ID.
- `InMemoryToolRegistry` — first concrete implementation for tests and simple
  callers.
- Runtime tool overrides — caller-provided additions, replacements, disabled
  tool ids, and per-`llm_step` exposure changes layered over the generated
  manifest/tool-index baseline without mutating generated artifacts.
- Runtime behavior overrides — caller-provided prompt patches and skill binding
  changes for individual `llm_step` nodes, layered over generated artifacts
  without mutating the manifest, graph, tool index, or design document.
- Built-in tool packs — optional pre-registered registry sources that callers
  explicitly enable, starting with a conservative read-only `local_workspace`
  pack.

Registry responsibilities:

- combine callable registry adapters with manifest/tool-index metadata when
  useful, while treating the effective registry as authoritative for executable
  tool availability
- convert tool definitions to OpenAI tool schema
- validate required tool inputs using the declared input schema where practical
- record side-effect metadata, approval metadata, timeout/retry policy, and
  structured success/failure results
- fail clearly for missing tools, malformed tool inputs, and unapproved
  side-effecting tools
- apply runtime tool overrides so callers can add new tools, replace existing
  tool definitions, disable tools, or restrict/extend tool exposure for a single
  `llm_step`
- fail closed when overrides remove tools that `tool_use_step` nodes still
  require or target nodes that are not existing `llm_step` nodes
- fail closed when a `tool_use_step` references a tool id that appears only in
  manifest/tool-index metadata and has no callable registry entry
- provide opt-in built-in tool packs without making their tools ambient; nodes
  must still reference built-in tool ids before the tools are exposed or invoked
- constrain the initial `local_workspace` pack to read-only, workspace-rooted
  tools such as `read_file`, `list_files`, `search_files`, and `inspect_path`
- keep write and command-execution tools in separate, explicitly enabled,
  approval-aware packs if they are introduced

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

Do not expand the primitive node-kind taxonomy to represent agent patterns.
Pattern-specific structures such as multi-agent collaboration, memory-augmented
agents, observer workflows, computer-use loops, or speech workflows should be
modeled with `patterns_present`, `participant_groups`, `roles`, `phases`,
ordinary primitive nodes, declared tools, and control-flow edges. Executor
support can then be added incrementally for the relevant primitive nodes, edge
semantics, tools, and policies.

Execution state should track:

- original user prompt
- rendered node inputs
- node outputs
- tool results
- final result
- errors and failure behavior

Execution-envelope inputs should be grouped in `WorkflowExecutionContext` /
`RunContext` so future tool policy, tracing, hook, model-capability, and context
management settings can attach to one stable object instead of expanding
`execute_workflow(...)` keyword arguments indefinitely. The user prompt remains
a per-run input and is not stored in the reusable context object.

### CLI

Expose a CLI that can load artifacts and run the workflow:

```bash
dynamic-agent-runner run \
  --agent-design path/to/agent-design.md \
  --runtime path/to/agent-runtime.yaml \
  --graph path/to/agent-graph.mmd \
  --tool-index path/to/tool-index.yaml \
  --registry path/to/registry-config.yaml \
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
   - parse runtime YAML, Mermaid text, optional tool-index metadata, and design
     document
   - support path, raw-string, and already-parsed-object inputs
   - preserve supported pattern metadata, participant groups, modes, phases, and
     roles for later validation and execution slices
   - add fixture-based tests

3. **Validation engine**
   - implement manifest, graph, optional tool-index metadata, and relationship checks
   - add clear error objects/messages

4. **Repository-owned tool registry**
   - implement registry protocols, in-memory registry, schema conversion,
     invocation dispatch, runtime tool overrides, and opt-in built-in tool packs
   - add tests for lookup, OpenAI schema conversion, tool invocation, override
     layering, built-in pack enablement, per-node tool exposure, and failure
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

8. **Runtime behavior overrides (Slice 12 follow-up)**
   - add override artifact models and loaders
   - preserve optional node `skill_refs` metadata
   - validate per-node prompt patches and skill binding overrides
   - compute effective prompt/skill behavior without mutating generated artifacts
   - add API/CLI override inputs and fake-client tests

9. **Evaluation follow-up Slice A: workflow execution context**
   - add `src/dynamic_agent_runner/context.py` with
     `WorkflowExecutionContext` and `RunContext`
   - allow `execute_workflow(...)` and `run_agent_workflow(...)` to accept an
     execution context while preserving existing keyword-based compatibility
   - reject ambiguous calls that combine a context with duplicate runtime or
     artifact keyword arguments
   - validate with focused executor/API/import tests and the full test suite

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
- The source package now exists; future slices should keep the package layout,
  `pyproject.toml`, and tests aligned as modules are added.
- Exact OpenAI SDK call shape should be isolated behind the adapter because SDK
  APIs may evolve.
- Tool schema validation depth should start pragmatic and become stricter as
  real generated manifests stabilize.
- Runtime tool overrides are part of the Slice 4 registry contract because they
  affect effective tool availability, but they should remain overlay inputs that
  preserve generated artifacts as the baseline source of truth.
- Runtime behavior overrides are the prompt/skill counterpart to tool overrides:
  they should compute effective `llm_step` behavior from overlay inputs while
  preserving generated artifacts as immutable baselines.
- Runtime execution-context settings are now represented by
  `WorkflowExecutionContext` / `RunContext`; future runtime envelope additions
  should attach there when they are caller-provided execution collaborators or
  per-run policy controls rather than mutable workflow state.
- Tool-index files are optional metadata catalogs, not execution prerequisites;
  a tool can function only when the effective registry provides a callable entry.
- Built-in default tools should be opt-in registry packs, not implicit ambient
  capabilities. Start with read-only local workspace tools and keep write or
  command tools in stricter packs.
- Supported agent patterns are currently metadata-level compatibility targets;
  full executor support depends on later primitive node, edge, tool, policy, and
  adapter implementation.
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

This plan is accepted as the current technical planning artifact. The
readiness/scaffold slice is complete and validated. Continue with Slice 2 before
deeper validation, registry, OpenAI adapter, executor, or CLI runtime work.
