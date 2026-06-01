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
  caller-owned runtime behavior overrides for per-node prompts and skill
  bindings over an immutable base package.
- `README.md` — repository overview; aligned with the official `openai`
  package and repository-owned tool registry direction.
- `pyproject.toml` — package/dependency configuration; currently includes the
  official `openai` dependency and package include for `src/dynamic_agent_runner`.
- `memory-bank/` — durable project context; not authoritative over the spec.

## Current Repository State

- Core planned implementation slices are complete through package-alignment P5:
  the source package scaffold, artifact loading, validation, registry, model
  adapter, executor, CLI, async execution, runtime-package simplification, and
  package-directory-first alignment work are all implemented and committed.
- `pyproject.toml` and `poetry.lock` include the official `openai` dependency
  and package include for `src/dynamic_agent_runner`.
- `poetry check`, the import smoke test, targeted pytest, and targeted
  pre-commit passed for the package scaffold slice.
- README has been refreshed to align with the official `openai` package and
  repository-owned registry direction before deeper runtime implementation.
- A 3-round implementation-readiness debate concluded this plan is ready only
  for slice-by-slice implementation, not unrestricted runtime coding.
- E14 Slice I.7 is complete and committed: cancellation and concurrent async
  validation now covers in-flight async workflow cancellation, workflow-level
  cancellation observations, concurrent async shared-context run correlation, and
  sync/async public entry-point parity.
- Evaluation follow-up Slice A is complete and committed: the runtime now exposes
  `WorkflowExecutionContext` / `RunContext` as a stable execution envelope that
  groups a loaded workflow with runtime collaborators while preserving the
  existing `execute_workflow(workflow, ...)` call shape.
- Evaluation follow-up Slice B is complete and committed: the registry now
  validates OpenAI-compatible tool input schemas before model exposure or
  invocation input validation.
- Evaluation follow-up Slice C is complete and committed: the registry and
  metadata models now expose explicit tool exposure states and preserve
  lightweight tool policy metadata separately from callable registration and
  per-node exposure decisions.
- Evaluation follow-up Slice D is complete and committed: `ToolResult` now
  preserves separate model-facing, raw, log-preview, event-payload, and sensitive
  trace facets while retaining backward-compatible `output` fallback behavior.
- Evaluation follow-up Slice E is complete and committed: tool execution tracing
  now emits `tool_started`, `tool_finished`, and fallback `status_notice` events
  while preserving the older `tool_invocation` and `tool_result` events.
- Evaluation follow-up Slice F is complete and committed: the runtime now exposes
  trusted in-process lifecycle hooks for node, model, tool, permission-boundary,
  and workflow observations through the execution context and public API.
- Evaluation follow-up Slice G is complete and committed: the runtime now preserves
  lightweight `ModelCapabilities` metadata from runtime execution policy without
  treating capability declarations as provider request parameters.
- Evaluation follow-up Slice H is complete and committed: the runtime now
  assigns each execution a `run_id`, propagates that run correlation through
  traces and lifecycle hooks, and synchronizes package-owned in-memory/shared
  helper surfaces used by QThread-style callers.
- E14 decisions and implementation sequencing are recorded for future work:
  async execution should become the first-class runtime implementation, with
  `execute_workflow_async(...)` and `run_agent_workflow_async(...)` as public
  APIs and the existing sync APIs as wrappers that reject calls from an
  already-running event loop. The detailed slice plan lives in
  `cline-tasks/evaluation-follow-up-implementation-plan.md`.
- E14 Slice I.1 is complete and committed: the OpenAI client boundary now has
  async protocol types, `AsyncOpenAIClientAdapter`, a default `openai.AsyncOpenAI`
  factory, public exports, and fake-client tests.
- E14 Slice I.2 is complete and committed: `run_with_retry_async(...)` now
  preserves async retry attempt counts and propagates `asyncio.CancelledError`
  without retry.
- E14 Slice I.3 is complete and committed: registered tools now record handler
  callable shape and the registry exposes async invocation with awaited async
  handlers and thread-dispatched sync handlers.
- E14 Slice I.4 is complete and committed: lifecycle hooks now record callback
  callable shape, expose async hook dispatch helpers, and await async hooks from
  the current sync executor compatibility path when no event loop is already
  running.
- E14 Slice I.5 is complete and committed: `execute_workflow_async(...)` now
  drives an async workflow loop, awaits model calls through the async OpenAI
  adapter boundary, awaits direct tool dispatch through `invoke_tool_async(...)`,
  awaits lifecycle hooks, preserves existing helper semantics for rendering,
  token budgets, prompt-cache observations, output contracts, route handling,
  tracing, and state recording. The sync executor originally rejected async
  model adapters until Slice I.6 converted sync public entry points.
- Runtime-package simplification S1-S5 is complete and committed: grouped
  manifests, prepared execution planning, prepared model input, tool provenance,
  and a placeholder-safe Power-Marimo fixture now cover the first downstream
  package shape without live Marimo, SLD, or `power-tetris-sdk` access.
- A package-alignment review against the agent-development skill's current
  `references/agent-runtime-package.md` concluded that this repository should
  treat agent skill output as an immutable base package directory with fixed
  sibling artifacts (`agent-design.md`, `agent-runtime.yaml`,
  `agent-graph.mmd`, and `skill-bundle/`). Caller-initiated overrides remain a
  separate runtime input layered over that immutable base and compiled into a
  final workflow before execution.
- That same alignment review also means future shared manifest additions should
  be phrased in the upstream grouped-contract vocabulary: portable tool taxonomy,
  handoff vs agent-as-tool metadata, and approval/interruption metadata should
  extend `runtime`, `metadata`, and `extensions` rather than reintroducing flat
  root fields or runtime-specific MCP injection contracts.
- The S5 Power-Marimo fixture records `marimo-pair` as a SKILL-backed
  agent-as-tool `tool_use_step` using
  `../power-marimo/skills/marimo-pair/SKILL.md`; it does not introduce a new
  primitive runtime node kind or durable handoff-style multi-agent metadata.
- The next active planning surface is no longer a new implementation slice under
  the original P-series sequence. Active remaining work is the promoted
  Codex/Cline evaluation follow-ups and OpenAI Agents SDK Python evaluation
  follow-ups captured in `tasks.md`.
- The recommended implementation order for that active follow-up backlog is:
  OA7, OA10, OA9, OA8, then OA11 as the final upstream-conditional item.
- OA2 is now implemented in the working tree: tool provenance preserves the
  existing low-level source kind while adding a higher-level origin bucket that
  distinguishes registered, built-in, override, and future MCP or
  agent-as-tool origins without collapsing that metadata into a portable
  tool-type taxonomy.
- OA2 validation evidence: `poetry run pytest tests/test_registry.py
  tests/test_artifacts.py tests/test_validation.py 2>&1` — pass; 68 tests
  passed.
- OA3 is now implemented in the working tree: `prepare_model_input(...)` is the
  dedicated pre-adapter preparation seam for hierarchical prompt injection,
  session-message pruning, and summary-style context compaction, and
  `PreparedModelInput` now preserves preparation metadata describing those
  transformations.
- OA3 validation evidence: `poetry run pytest tests/test_executor.py -q 2>&1`
  — pass; 47 tests passed.
- OA1 is now implemented in the working tree: `RuntimeManifest` preserves
  deferred guardrail declarations from `extensions.guardrails.declarations`,
  including supported `input`, `output`, `tool_input`, and `tool_output`
  phases plus `abort` and `reject_content` tripwire behavior metadata.
- OA1 validation evidence: `poetry run pytest tests/test_validation.py
  tests/test_executor.py -q 2>&1` — pass; 74 tests passed.
- OA4+E9 is now implemented in the working tree: `RuntimeManifest` preserves
  deferred MCP registry-source metadata from
  `extensions.mcp_registry_sources.sources` and deferred MCP lifecycle
  diagnostics metadata from `extensions.mcp_lifecycle_diagnostics`, including
  source visibility/status, tool-cache policy, disabled state,
  operation-locking, memory-pollution fields, strict/degraded startup,
  reconnect policy, cleanup timeout, and state keys for active/failed servers
  plus error maps.
- OA4+E9 validation evidence: `validate_runtime_manifest(...)` now treats
  `mcp_registry_sources` and `mcp_lifecycle_diagnostics` as supported extension
  ids, fails closed for malformed payloads and unsupported enum-like values,
  and `prepare_execution_plan(...)` keeps those supported MCP extensions out of
  generic unsupported-extension reporting.
- OA4+E9 validation evidence: `poetry run pytest tests/test_validation.py
  tests/test_executor.py -q 2>&1` — pass; 76 tests passed.
- E11 is now implemented in the working tree: `prepare_model_input(...)` now
  supports a narrower opt-in file-backed prompt-context policy for
  package-root-backed workflows, adding deterministic file-context prompt parts
  with source provenance plus byte/token accounting in `PreparedInputMetadata`.
- E11 validation evidence: `validate_runtime_manifest(...)` now fails closed for
  malformed `runtime.execution_policy.prepare_model_input.file_context`
  mappings, non-relative or escaping roots, unsupported prompt roles, and
  invalid scan-depth, file-count, byte-budget, or token-budget values.
- E11 validation evidence: `poetry run pytest tests/test_validation.py
  tests/test_executor.py -q 2>&1` — pass; 80 tests passed.
- OA5 is now implemented in the working tree: `RuntimeManifest` and
  `ExecutionPlan` preserve deferred
  `runtime.execution_policy.tool_use_completion` metadata for future iterative
  agent-loop runtimes, covering `run_again`, `stop_on_tool`, `final_output`,
  and `final_output_state_key` without changing current executor loop behavior.
- OA5 validation evidence: `validate_runtime_manifest(...)` now fails closed for
  malformed `tool_use_completion` policy shapes, unsupported enum-like values,
  missing `final_output_state_key` when `final_output` is `state_field`, and
  stray state-key metadata when `final_output` is not `state_field`.
- OA5 validation evidence: `poetry run pytest tests/test_validation.py
  tests/test_executor.py -q 2>&1` — pass; 83 tests passed.
- OA6 is now implemented in the working tree: `RuntimeManifest` preserves
  grouped `metadata.handoffs` for future active-agent transfer workflows, while
  `RuntimeNode` and `PreparedNode` preserve typed node-local `agent_as_tool` /
  `agent_tool` metadata for bounded delegation without introducing a new
  primitive node kind or changing current executor semantics.
- OA6 validation evidence: `validate_runtime_manifest(...)` now fails closed for
  malformed `metadata.handoffs`, unsupported `on_handoff` or `nested_history`
  values, blank grouped handoff fields, non-mapping node-level agent metadata,
  agent-as-tool metadata on non-`tool_use_step` nodes, missing `skill_id` /
  `task_boundary`, and unsupported `output_mode` values.
- OA6 validation evidence: `poetry run pytest tests/test_artifacts.py
  tests/test_validation.py tests/test_executor.py tests/test_power_marimo_fixture.py
  -q 2>&1` — pass; 106 tests passed.
- OA7 is implemented in the working tree: `RuntimeManifest` and `ExecutionPlan`
  now preserve deferred `runtime.execution_policy.approval_interruption`
  metadata for future approval-required tool pauses, interruption checkpoints,
  and resumable run state without adding a live approval engine or pause/resume
  execution behavior in the current runtime.
- OA7 validation evidence: `validate_runtime_manifest(...)` now fails closed for
  malformed `approval_interruption` policy shapes, unsupported `mode`,
  `persist`, or `resume_from` values, non-string or blank state-key fields,
  persisted interruption policies that omit required resumable state keys, and
  `persist: none` policies that incorrectly declare persisted state-key fields.
- OA10 is implemented in the working tree: `RuntimeManifest` and `ExecutionPlan`
  now preserve deferred `runtime.execution_policy.sandbox_runtime` metadata for
  future writable-workspace and command-execution runtimes without changing the
  current read-only `local_workspace` built-in pack or enabling a live sandbox.
- OA10 validation evidence: `validate_runtime_manifest(...)` now fails closed for
  malformed `sandbox_runtime` policy shapes, unsupported `mode`, `filesystem`,
  `persist_workspace`, or `command_policy` values, non-string or blank workspace
  state-key fields, persisted workspace policies that omit required state keys,
  `persist_workspace: none` policies that still declare state keys, and
  command-execution policies that incorrectly pair with `filesystem: read_only`.
- OA9 is planned as a caller ergonomics slice after the provenance and policy
  metadata work: the registry should expose an optional `tool_from_function(...)`
  helper that can build `RegisteredTool` instances from Python callables while
  letting explicit metadata override inferred defaults. Missing or incomplete
  metadata should fall back conservatively to callable-name, docstring, and
  supported-signature inference rather than introducing a broader agent SDK
  compatibility layer.
- OA8 is planned as a protocol-design slice after the earlier metadata seams: the
  runtime should preserve deferred `runtime.execution_policy.async_session`
  metadata for future multi-turn or resumable async workflows, including compact
  session-id and history-retention protocol fields, without enabling live session
  persistence, conversation replay, or automatic cross-run message reuse in the
  current runtime.

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

The package-alignment work has replaced the earlier loose artifact utility
contract with a package-directory-first contract while preserving lower-level
compatibility seams for tests and controlled callers.

Initial parser responsibilities:

- package-directory loading rooted at one design bundle path
- `agent-runtime.yaml` loading as the sole authoritative executable artifact
- sibling `agent-design.md` and `agent-graph.mmd` loading relative to the package
  root
- `skill-bundle/` reference resolution and existence checks for top-level skill
  bundle paths and support files
- lightweight `agent-design.md` reference checks for runtime manifest and Mermaid
  graph mentions within the package boundary
- preservation of documented supported agent-pattern metadata from
  `patterns_present`
- preservation of structural metadata used by broader pattern shapes, including
  `participant_groups`, `modes`, `phases`, and `roles`
- preservation of grouped-surface boundaries so future portable tool taxonomy,
  approval/interruption metadata, and handoff vs agent-as-tool metadata can be
  consumed without confusing them with runtime-specific MCP/source wiring

Use strongly typed internal dataclasses or Pydantic models only if they reduce
complexity. Prefer standard-library dataclasses for the first slice unless schema
validation becomes too large.

Package-alignment review decisions:

- Drop backward-compatible public reliance on separate `runtime_manifest`,
  `mermaid_graph`, `agent_design`, `tool_index`, and `runtime_overrides`
  arguments as the main skill-output contract.
- Keep runtime/workflow overrides as a caller-owned runtime layer, but not as
  part of the canonical agent-development-skill output package.
- Add first-class `skill-bundle/` handling and validate bundled skill/support
  references explicitly.
- Add an explicit compile/preparation phase that combines the immutable base
  package plus caller overrides into the final execution-ready workflow.
- Preserve lower-level helper seams only when useful for tests or internal
  implementation, not as the primary public API contract.

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

Implement runtime behavior overrides as a caller-owned overlay parallel to
runtime tool overrides. The generated package remains the immutable base
definition, while caller-provided override artifacts are validated during
compilation/preparation and produce effective node behavior for the derived
final workflow.

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

- `ToolDefinition` — manifest/tool-index metadata, JSON schema, exposure state,
  side-effect metadata, and lightweight policy fields.
- `ToolResult` — structured invocation result with backward-compatible `output`
  plus optional `model_output`, `raw_output`, `log_preview`, `event_payload`, and
  `sensitive_fields` facets.
- `ToolExposure` — explicit model/direct-call visibility state with `direct`,
  `deferred`, `direct_model_only`, and `hidden` values.
- `ToolPolicy` — side-effect, approval, sandbox, timeout, retry, and failure
  behavior metadata preserved separately from callable registration.
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
- convert model-exposable tool definitions to OpenAI tool schema
- validate explicit tool exposure states and fail closed for unknown exposure
  values
- preserve tool policy metadata separately from callable registration and
  per-node model exposure decisions
- validate tool input schemas before model exposure or invocation validation,
  including object-shaped schemas, mapping-shaped `properties`, string-only
  `required` entries, no top-level `oneOf` / `anyOf` / `allOf`, and no `$schema`
  metadata in model-facing parameters
- validate required tool inputs using the declared input schema where practical
- record side-effect metadata, approval metadata, timeout/retry policy, and
  structured success/failure results with separate model-facing, raw, log-preview,
  event-payload, and sensitive-field facets
- fail clearly for missing tools, malformed tool inputs, and unapproved
  side-effecting tools
- apply runtime tool overrides so callers can add new tools, replace existing
  tool definitions, disable tools, or restrict/extend tool exposure for a single
  `llm_step`
- fail closed when overrides remove tools that `tool_use_step` nodes still
  require or target nodes that are not existing `llm_step` nodes
- fail closed when a `tool_use_step` references a tool id that appears only in
  manifest/tool-index metadata and has no callable registry entry
- fail closed when a direct `tool_use_step` references a registered tool whose
  exposure is model-only or deferred rather than directly callable
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

Concurrent invocation support preserves this boundary: `WorkflowExecutionState`
and prompt-specific data remain per invocation, while package-owned shared
helpers provide explicit synchronization for current in-memory trace sink, tracer,
lazy OpenAI adapter initialization, and in-memory registry read/mutation paths.
Caller-provided tool handlers and lifecycle hook implementations remain
responsible for synchronizing their own mutable internal state.

E14 async work should implement a true async-first internal executor. The public
async APIs, `execute_workflow_async(...)` and `run_agent_workflow_async(...)`, are
the primary runtime entry points. Existing synchronous public APIs remain for
scripts, tests, cron jobs, the CLI, and simple automation as wrappers over that
async path, but they must raise a clear project error if called from an
already-running event loop.

Model execution should use one async-canonical model-client protocol. Native
OpenAI async support must be verified against official SDK behavior or source
code before implementation; the local note
the local Obsidian note titled
  `How make async calls to OpenAI’s API in Python  Medium.md`
is supporting guidance for the expected `openai.AsyncOpenAI` / awaited-call shape,
not an authoritative API contract. Sync-only model clients may be adapted behind
the async protocol, but a separate sync runtime protocol should not become the
executor contract.

Tool handlers and lifecycle hooks may be synchronous or asynchronous. Their
callable shape should be inspected and recorded during registration or setup so
async execution can invoke or await them correctly without guessing at first
use. Cancellation should use best-effort propagation to active model calls, tool
calls, hook calls, and child tasks where supported, while documenting non-
cancellable sync or external boundaries honestly.

E13 remains part of the E14 contract: concurrent async runs must preserve
per-run state isolation, run IDs, trace correlation, hook-context correlation,
and synchronization for package-owned shared helpers that remain shared across
threads or async tasks.

### CLI

Expose a CLI that can load artifacts and run the workflow:

```bash
dynamic-agent-runner run \
  --package path/to/design-dir \
  --registry path/to/registry-config.yaml \
  --prompt "..."
```

Exact command shape may use `docopt-ng` or another existing dependency pattern,
but must support clear non-zero exits for loading, validation, model, registry,
and execution failures.

## New package-alignment slices

18. **Package-alignment Slice P1: canonical package-directory loader**
    - add a package-directory-first loading path rooted at one design bundle
    - require `agent-runtime.yaml` and fixed sibling artifact discovery
    - preserve lower-level helpers only as internal seams where still useful

19. **Package-alignment Slice P2: strict sibling artifact and bundle validation**
    - validate `agent-design.md`, `agent-graph.mmd`, and `skill-bundle/`
      references as one package boundary
    - fail clearly for missing bundle files or broken manifest bundle references

20. **Package-alignment Slice P3: explicit compile/final-workflow phase**
    - validate caller-owned overrides against the immutable base package
    - compile base package plus overrides into a final execution-ready workflow

21. **Package-alignment Slice P4: package-directory-first public API and CLI**
    - simplify public API to accept a package directory as the primary contract
    - keep caller-owned override input as a separate runtime argument over the
      immutable base package
    - simplify CLI to a `--package` style contract and keep override inputs
      clearly separate from the canonical base package

22. **Package-alignment Slice P5: manifest/runtime alignment cleanup for
    upstream taxonomy**
    - align manifest capability vocabulary with the current upstream runtime-
      package guidance
    - preserve and validate provider-neutral `model_requirements`, ReAct-style
      loop metadata, and `rag` / `embedding_retrieval` / `graph_retrieval` /
      `graphrag` classifications
    - document `evidence_loop` metadata and capability-routing expectations

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

10. **Evaluation follow-up Slice B: stronger tool schema validation**
    - normalize registry tool input schemas through one validation path before
      OpenAI schema exposure and invocation required-field checks
    - reject malformed object schemas, malformed `properties` or `required`, and
      unsupported top-level schema combinators
    - strip `$schema` metadata from model-facing OpenAI tool parameters
    - validate with focused registry tests and the full test suite

11. **Evaluation follow-up Slice C: tool exposure states and policy separation**
    - add `ToolExposure` states for `direct`, `deferred`,
      `direct_model_only`, and `hidden` tools
    - add `ToolPolicy` metadata for side effects, approval, sandbox, timeout,
      retry, and failure behavior
    - filter model-facing tools by exposure and reject non-callable exposures for
      direct `tool_use_step` validation/invocation
    - validate with focused registry/validation/import tests and the full test
      suite

12. **Evaluation follow-up Slice D: richer tool result facets**
    - extend `ToolResult` with `model_output`, `raw_output`, `log_preview`,
      `event_payload`, and `sensitive_fields` while preserving `output` fallback
    - preserve structured `ToolResult` objects returned by handlers instead of
      wrapping them as ordinary output
    - use model-facing output for downstream prompt rendering, state-key outputs,
      and node-output unwrapping
    - include raw/log/event facets and sensitive fields in tool-result trace
      payloads
    - validate with focused registry/executor/tracing/import tests and the full
      test suite

13. **Evaluation follow-up Slice E: extended trace vocabulary**
    - emit `tool_started` before direct tool invocation with tool id and redacted
      arguments
    - preserve existing `tool_invocation` and `tool_result` events for
      compatibility
    - emit `tool_finished` after tool results are recorded for both success and
      fail-closed error paths
    - emit `status_notice` warnings for non-fatal fallback tool failures
    - validate with focused tracing/executor tests and the full test suite

14. **Evaluation follow-up Slice F: narrow in-process lifecycle hooks**
    - add `WorkflowLifecycleHooks` and stable context objects for node, model,
      tool, permission-boundary, and workflow observations
    - pass hooks through `WorkflowExecutionContext`,
      `execute_workflow(...)`, and `run_agent_workflow(...)`
    - invoke observational `before_node`, `after_node`, `before_model`,
      `after_model`, `before_tool`, `after_tool`, and `after_workflow` callbacks
      at stable lifecycle points
    - keep hook controls minimal: trusted Python hooks may raise project
      errors to
      abort execution, while shell hooks, plugin loading, and untrusted hook
      sources remain out of scope
    - validate with focused hook/executor/tracing tests and the full test suite

15. **Evaluation follow-up Slice G: lightweight model capabilities metadata**
    - add `ModelCapabilities` metadata for context window, structured-output
      support, reasoning support, modalities, and parallel tool-call support
    - preserve capability metadata from runtime `execution_policy` without making
      it ambient provider request configuration
    - export `ModelCapabilities` for callers that need to inspect loaded workflow
      metadata
    - validate with focused model-capability/artifact/import/executor tests and
      the full test suite

16. **Evaluation follow-up Slice H: thread-safety and concurrent invocation contract**
    - completed in commit `2e45888`
    - added per-run `run_id` generation and optional caller-provided run IDs to
      `execute_workflow(...)` and `run_agent_workflow(...)`
    - added run-correlation metadata to trace events and lifecycle hook contexts
      so interleaved executions remain distinguishable
    - synchronized `InMemoryTraceSink`, `WorkflowTracer`, lazy default-client
      initialization in `OpenAIClientAdapter`, and `InMemoryToolRegistry`
      read/mutation paths
    - documented the remaining boundary: caller-provided mutable tool handlers
      and lifecycle hook implementations must synchronize their own shared state
    - validated with concurrent fake-client/fake-tool execution tests, the full
      test suite, compile checks, and targeted pre-commit

17. **Evaluation follow-up Slice I / E14: async-first execution APIs and wrappers**
    - detailed implementation sequencing is recorded in
      `cline-tasks/evaluation-follow-up-implementation-plan.md`
    - Slice I.1 async OpenAI client boundary is complete in commit `acca9da`
    - Slice I.2 async retry helper is complete in commit `f2296e9`
    - Slice I.3 callable-shape metadata for tools is complete in commit `ff144f5`
    - Slice I.4 callable-shape metadata for lifecycle hooks is complete in
      commit `2b9271b`
    - Slice I.5 async executor core is complete in commit `72c28dd`
    - Slice I.6 public async API and sync wrappers is complete in commit
      `4f279ff`
    - Slice I.7 cancellation and concurrent async validation is complete in commit
      `7990503`
    - true async public APIs `execute_workflow_async(...)` and
      `run_agent_workflow_async(...)` are now the first-class runtime path
    - existing sync public APIs for CLI, scripts, tests, cron jobs, and simple
      automation now wrap the async semantic path
    - sync wrappers raise a clear project error when called from an
      already-running event loop, directing callers to the async APIs
    - use one async-canonical model-client protocol, with native async OpenAI
      adapter support now established by Slice I.1 after inspecting the local
      OpenAI Python SDK checkout and verifying official SDK behavior/source-code
      details
    - adapt sync-only model clients behind the async protocol when needed without
      making a separate sync executor contract
    - inspect and record sync/async tool-handler callable shape at
      registration or setup time and dispatch each handler correctly during async
      execution
    - inspect and record sync/async lifecycle hook callable shape at setup time
      and invoke or await each hook correctly during async execution
    - implement best-effort cancellation propagation across workflow, node, model,
      tool, hook, and child-task boundaries; document non-cancellable sync or
      external boundaries honestly
    - keep E13 run-correlation guarantees consistent for concurrent async runs:
      per-run state isolation, run IDs, trace correlation, hook-context
      correlation, and synchronized package-owned shared helpers
    - validate async model calls, async tool handlers, async lifecycle hooks,
      cancellation, sync wrapper compatibility, and concurrent async runs

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
- Core execution state remains per run, and E13 now adds run-correlation
  metadata plus synchronization for package-owned shared helper surfaces.
  `InMemoryTraceSink`, `WorkflowTracer`, `OpenAIClientAdapter` lazy default-client
  initialization, and `InMemoryToolRegistry` read/mutation helpers are covered by
  tests for concurrent use. Caller-provided mutable tool handlers and lifecycle
  hooks remain caller-managed for synchronization.
- E14 is now defined as a true async-first implementation direction, not only a
  design spike: async public APIs become first-class, while sync APIs become
  wrappers over the async path for simple callers and the CLI. The detailed E14
  implementation plan is in `cline-tasks/evaluation-follow-up-implementation-plan.md`.
- E14 Slice I.1 completed the async OpenAI client boundary in commit `acca9da`:
  `AsyncOpenAIClientAdapter` awaits injected async clients, the default async
  factory uses `openai.AsyncOpenAI`, and request construction/response
  normalization remain shared with the existing sync adapter.
- E14 Slice I.2 completed the async retry helper in commit `f2296e9`:
  `run_with_retry_async(...)` uses Tenacity's async retry support, preserves
  attempt-count return behavior, and propagates `asyncio.CancelledError` without
  retry.
- E14 Slice I.3 completed callable-shape metadata for tools in commit `ff144f5`:
  `RegisteredTool` records sync/async handler shape, `ToolRegistry` exposes
  `invoke_tool_async(...)`, async handlers are awaited directly, and sync handlers
  use `asyncio.to_thread(...)` on the async registry path.
- E14 Slice I.4 completed callable-shape metadata for lifecycle hooks in commit
  `2b9271b`: `WorkflowLifecycleHooks` records configured callback shape in
  `RegisteredLifecycleHook` metadata, `invoke_lifecycle_hook_async(...)` invokes
  sync hooks or awaits async hooks, and the current sync executor compatibility
  path awaits async hooks when no event loop is already running.
- E14 Slice I.5 completed the async executor core in commit `72c28dd`:
  `execute_workflow_async(...)` now drives an async workflow loop and async node
  helpers, awaits async model calls through `AsyncOpenAIClientAdapter`, awaits
  direct tool dispatch through `ToolRegistry.invoke_tool_async(...)`, awaits
  lifecycle hooks through `invoke_lifecycle_hook_async(...)`, preserves existing
  retry, token-budget, prompt-cache, output-contract, tracing, and route behavior,
  and originally rejected async model adapters from the synchronous executor path
  until public wrappers were converted.
- E14 Slice I.6 completed public async API and sync wrappers in commit
  `4f279ff`: `run_agent_workflow_async(...)` now loads, validates, executes
  through `execute_workflow_async(...)`, and returns the final result;
  `execute_workflow_async(...)` and `run_agent_workflow_async(...)` are exported
  from the package root; `execute_workflow(...)` and `run_agent_workflow(...)`
  now wrap their async counterparts through `_run_async_from_sync(...)`; sync
  wrappers call `asyncio.run(...)` only when no event loop is active and raise
  `WorkflowExecutionError` from an already-running event loop.
- E14 Slice I.7 completed cancellation and concurrent async validation in commit
  `7990503`: `tests/test_concurrency.py` now covers in-flight async workflow
  cancellation propagation, workflow cancellation trace and `after_workflow` hook
  observations, concurrent async runs reusing one execution context with distinct
  run IDs, shared trace-sink and hook run correlation, and sync/async public API
  parity for final results and trace event shapes.
- Sync wrappers must reject already-running event loops with a clear project
  error rather than attempting nested event-loop execution.
- The model-client contract should be async-canonical. OpenAI async support must
  be verified against official SDK behavior or source before implementation; use
  `/Users/roschuma/Repos/github/openai-python/` as the local source checkout for
  that inspection. The local Medium note is only supporting guidance.
- Supporting both sync and async collaborator styles increases API and test-matrix
  complexity, so tool-handler and lifecycle-hook callable shape must be inspected
  at registration/setup time and stored for deterministic dispatch.
- Async cancellation guarantees are best-effort and must be scoped to what model,
  tool, hook, and external boundaries actually support.
- Tool input schemas now fail closed for malformed OpenAI-compatible function
  parameter shapes; future support for top-level schema combinators should be an
  explicit compatibility expansion rather than pass-through behavior.
- Tool exposure is now explicit: only `direct` and `direct_model_only` tools are
  model-exposable, only `direct` and `hidden` tools are direct-callable,
  `deferred` remains metadata-only for future lazy-loading behavior, and unknown
  exposure values fail validation.
- Tool policy metadata is now preserved in `ToolPolicy`, separate from callable
  registry entries and node exposure decisions; this is not yet a sandbox or
  approval engine.
- Tool results now preserve richer facets: `model_output` drives downstream
  prompt/state references when present, `output` remains the fallback for existing
  callers, and raw/log/event facets are available for trace payloads and future
  hooks.
- Tool trace vocabulary now includes explicit `tool_started` and `tool_finished`
  lifecycle events around the existing compatibility events, plus warning
  `status_notice` events for fallback tool failures; hooks can rely on this
  vocabulary as the starting tool lifecycle surface.
- Lifecycle hooks are now trusted in-process Python callbacks attached through
  `WorkflowLifecycleHooks` and `WorkflowExecutionContext`; they are observational
  except that raising a project error aborts execution. Shell hooks, plugin
  loading, and untrusted hook sources remain out of scope.
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

This plan is accepted as the current technical planning artifact. The currently
planned implementation sequence is complete through package-alignment P5 and the
tracked async-first follow-up slices. Future work should start from the active
Codex/Cline and OpenAI Agents SDK Python follow-up tasks in this order: OA7,
OA10, OA9, OA8, then OA11 unless a new scoped spec/plan update supersedes that
sequence.
