# Agent runtime package simplification analysis

<!-- markdownlint-disable MD013 -->

## Goal

Analyze where the current `agent-runtime-package.md` design concept could be
simplified to make the implemented and planned `dynamic-agent-runner` features
easier to build, validate, and evolve.

This is a design-analysis artifact only. It does not change runtime behavior,
the upstream agent-development skill reference, or the active SDD specification.

## Context reviewed

- Current external design reference:
  - `/Users/roschuma/Repos/roschuma/clinerules-roschuma/skills/agent-development-skill/references/agent-runtime-package.md`
- Current `dynamic-agent-runner` planning artifacts:
  - `specs/dynamic-agent-runner/spec.md`
  - `specs/dynamic-agent-runner/plan.md`
  - `specs/dynamic-agent-runner/tasks.md`
- Prior evaluation artifacts:
  - `cline-tasks/codex-cli-evaluation.md`
  - `cline-tasks/cline-evaluation.md`
  - `cline-tasks/codex-cline-combined-package-proposal.md`
  - `cline-tasks/openai-agents-python-evaluation.md`
  - `cline-tasks/evaluation-follow-up-implementation-plan.md`
- Current implementation modules:
  - `src/dynamic_agent_runner/models.py`
  - `src/dynamic_agent_runner/artifacts.py`
  - `src/dynamic_agent_runner/validation.py`
  - `src/dynamic_agent_runner/executor.py`
  - `src/dynamic_agent_runner/registry.py`
  - `src/dynamic_agent_runner/context.py`
  - `src/dynamic_agent_runner/api.py`
  - `src/dynamic_agent_runner/behavior.py`

## Executive summary

The current design has the right core insight: keep `agent-runtime.yaml` as the
portable source of truth, keep `agent-graph.mmd` derived, and preserve the small
primitive execution taxonomy of `llm_step`, `tool_use_step`, and `decision_step`.
That foundation has scaled well through the implemented features.

The main simplification opportunity is not to reduce the primitive executor. It
is to **separate the manifest into a small executable core plus explicit optional
extension profiles**. The current reference lists many optional top-level fields
and additional metadata fields in one namespace. That made sense while exploring
Codex, Cline, and OpenAI Agents SDK Python, but it now risks making every future
feature look like a new top-level manifest concern.

Recommended simplification:

1. Define a **core execution contract** for format version 1.
2. Move advanced optional surfaces into a namespaced `extensions:` map or a small
   set of named profiles.
3. Introduce a **derived execution plan** object inside the runner so runtime
   modules consume normalized views instead of raw manifest sections.
4. Treat context preparation, guardrails, MCP, sessions, interruption/resume,
   and sandbox/workspace behavior as independent capability modules with their
   own narrow metadata and validation.
5. Keep source design artifacts descriptive, and make the generated runtime
   package deliberately boring: graph, nodes, edges, tools, skills, policies,
   and extension declarations.

## What is already simple and should stay simple

### 1. Primitive node taxonomy

The design should keep the current primitive nodes:

- `llm_step`
- `tool_use_step`
- `decision_step`

This matches the implementation in `RuntimeNode`, `validate_runtime_manifest(...)`,
and `execute_workflow_async(...)`. It also remains consistent with the Codex,
Cline, and OpenAI Agents SDK Python evaluations: multi-agent collaboration,
handoffs, memory, MCP, computer-use, speech, and sandbox workflows can be
represented through metadata, tools, policies, phases, and edges until a future
format version truly needs more primitives.

Do **not** simplify by adding broad node kinds such as `agent_step`,
`memory_step`, `mcp_step`, or `multi_agent_step`. That would make the executor
larger, not simpler.

### 2. Generated artifacts as immutable baseline

The current behavior is good:

- generated artifacts are loaded and preserved
- runtime tool overrides are overlays
- runtime behavior overrides are overlays
- effective behavior is derived at execution time

This enables experimentation without regenerating the package and keeps tests
focused. The `behavior.py` model is a useful pattern for future derived views.

### 3. Registry-authoritative callable tools

The runner already keeps metadata separate from executable capability:

- manifest and tool-index entries describe tools
- `ToolRegistry` supplies callable tools
- tool exposure controls model visibility and direct-call validity
- `ToolPolicy` preserves side-effect/approval/sandbox hints without pretending
  to enforce a sandbox

This is one of the strongest simplifications compared with importing a full SDK
or plugin architecture.

## Current complexity pressure points

### 1. Too many optional top-level manifest fields

The current design reference lists required fields, recommended fields, and many
additional optional metadata fields:

- `runtime_surface`
- `workspace_boundary`
- `completion_contract`
- `result_surfaces`
- `permission_profile`
- `approval_channels`
- `action_policy`
- `sandbox_enforcement`
- `network_policy`
- `mutation_safety`
- `tool_exposure`
- `context_pipeline`
- `instruction_authority`
- `trace_bundle`
- `evidence_model`
- `event_contracts`
- `goals`
- `experimental_capabilities`

These fields are individually reasonable, but as peers of `nodes`, `edges`,
`tools`, and `skills`, they make the manifest look like one flat schema that must
eventually understand every runtime concern.

**Simplification:** keep the root small and move non-core concerns under a
namespaced extension surface.

Candidate shape:

```yaml
format_version: 1
package_type: dynamic_agent_design
package_id: example
entrypoint: analyze_request
packaging: ...
nodes: ...
edges: ...
tools: ...
skills: ...

runtime:
  model: gpt-4.1-mini
  max_steps: 20
  prompt_cache: ...
  token_budget: ...

extensions:
  context_management: ...
  guardrails: ...
  mcp: ...
  approvals: ...
  sessions: ...
  sandbox: ...
```

This keeps the root contract stable and makes future optional surfaces easier to
validate independently.

### 2. Design metadata and executable policy are mixed

Fields such as `patterns_present`, `participant_groups`, `modes`, `phases`, and
`roles` are mostly descriptive or structural metadata. Fields such as
`execution_policy.prompt_cache`, token budgets, retry policies, and `max_steps`
affect execution. Fields such as `sandbox_enforcement`, `network_policy`, and
`approval_channels` may look executable but are currently advisory unless scoped
by a feature.

**Simplification:** classify manifest fields by runtime force:

| Class | Meaning | Examples | Runtime behavior |
| --- | --- | --- | --- |
| Core executable | Required to traverse and execute | `nodes`, `edges`, `entrypoint` | validate and enforce |
| Runtime policy | Supported policy knobs | `max_steps`, `retry_policy`, `token_budget`, `prompt_cache` | validate and enforce where implemented |
| Capability declaration | Opt-in future/optional modules | `mcp`, `sessions`, `sandbox`, `guardrails` | validate if module enabled; otherwise preserve/warn |
| Design metadata | Reader/planner metadata | `patterns_present`, `phases`, `roles` | preserve, expose, do not enforce by default |

This classification should be explicit in `agent-runtime-package.md` and mirrored
in the runner's models.

### 3. The runner consumes raw manifest sections in many places

The implementation is intentionally lightweight, but execution now reads raw
node and manifest metadata directly in several places:

- `_model_name(...)`
- `_model_parameters(...)`
- `_model_retry_policy(...)`
- `_token_budget_policy(...)`
- `_tool_retry_policy(...)`
- `_failure_behavior(...)`
- `_output_schema_ref(...)`
- `_allowed_routes(...)`
- `_tool_arguments(...)`

This is still manageable, but each new planned feature could add more raw-shape
knowledge to the executor.

**Simplification:** add a normalization layer that derives an `ExecutionPlan` or
per-node `PreparedNode` before traversal.

Candidate internal shape:

```python
@dataclass(frozen=True)
class ExecutionPlan:
    workflow: LoadedAgentWorkflow
    nodes: Mapping[str, PreparedNode]
    edges_by_source: Mapping[str, tuple[RuntimeEdge, ...]]
    entrypoint: str
    max_steps: int

@dataclass(frozen=True)
class PreparedNode:
    id: str
    kind: str
    prompt: Mapping[str, object] | None
    model: str | None
    model_parameters: Mapping[str, object]
    available_tool_ids: tuple[str, ...]
    tool_id: str | None
    retry_policy: RetryPolicy
    token_budget: TokenBudgetPolicy
    output_contract_ref: str | None
    failure_behavior: str
    raw: Mapping[str, object]
```

Benefits:

- executor traversal becomes smaller
- validation and execution share one normalized view
- future prepare-model-input and guardrail stages have a stable insertion point
- raw manifest compatibility stays in one preparation module

### 4. Context preparation is split across prompt rendering, token budgeting, and prompt cache checks

Current execution renders messages, checks prompt-cache intent, enforces token
budgets, then builds an OpenAI request. Future OA3/E10/E11 work would add
session pruning, compaction, hierarchical prompt injection, and possibly
source-tracked context.

If added directly to `_execute_llm_step_async(...)`, this will grow quickly.

**Simplification:** make `prepare_model_input(...)` the one seam between
effective node behavior and model adapter calls.

Candidate pipeline:

```text
effective node behavior
  -> render base messages
  -> add inline skill instructions
  -> apply session/history policy
  -> inject source-tracked context
  -> run budget/compaction policy
  -> observe prompt-cache eligibility
  -> produce PreparedModelInput
```

The OpenAI adapter should only receive already-prepared messages/tools/options.

### 5. Tool metadata lacks one canonical provenance object

Current tool modeling has useful pieces:

- `ToolDefinition`
- `ToolPolicy`
- `ToolExposure`
- `RegisteredTool`
- `ToolRegistryOverrides`
- built-in pack construction

OA2 adds provenance needs: registered, built-in, override, MCP, and agent-as-tool.
This should not become five separate booleans or special-case code paths.

**Simplification:** add one `ToolOrigin` / `ToolSource` object and let registry
preparation assign it.

Candidate shape:

```python
@dataclass(frozen=True)
class ToolOrigin:
    source_type: Literal[
        "registered",
        "builtin_pack",
        "manifest",
        "tool_index",
        "override",
        "mcp",
        "agent_tool",
    ]
    source_id: str | None = None
    original_name: str | None = None
```

This simplifies MCP and agent-as-tool integration because both become registry
sources that emit normalized registered tools with provenance.

### 6. Approval, sandbox, and mutation policy should not be flattened into tool fields

The current `ToolPolicy` intentionally stores strings. That is fine for the
implemented scope. OA7/OA10 and the Codex/Cline evaluations show that approval,
sandbox, network, and mutation safety are separate dimensions.

**Simplification:** keep `ToolPolicy` lightweight for now, but when write/command
tools are scoped, create separate nested policies instead of expanding one flat
dataclass indefinitely.

Candidate future split:

```yaml
tools:
  - id: run_tests
    side_effect: mutate
    approval:
      mode: on_request
      channel: host
    sandbox:
      filesystem: workspace_write
      network: forbidden
    mutation:
      provenance: vcs_diff
```

This is simpler than trying to make `approval_required`, `sandbox`, `timeout`,
and `failure_behavior` carry all policy meaning.

## Recommended simplified package model

### Root manifest contract

Keep the root fields small:

```yaml
format_version: 1
package_type: dynamic_agent_design
package_id: <id>
name: <optional>
description: <optional>
entrypoint: <node id>
packaging: <package packaging>
nodes: []
edges: []
tools: []
skills: []
output_contracts: {}
runtime: {}
metadata: {}
extensions: {}
```

Suggested meanings:

- `runtime` — executable policies the current runner can interpret.
- `metadata` — design-only metadata such as patterns, phases, modes, roles, and
  participant groups.
- `extensions` — optional capability-specific declarations.

This does not require an immediate breaking change. The runner can support the
existing field locations while the design reference recommends the grouped shape
for newly generated packages.

### Extension modules

Use explicit extension keys rather than many root fields:

```yaml
extensions:
  context_management:
    prepare_stage: basic
  guardrails:
    declarations: []
  mcp:
    registry_sources: []
  approvals:
    interruption_state: disabled
  sessions:
    mode: none
  sandbox:
    workspace_manifest: null
```

Each extension should have its own validation strategy:

- unsupported extension with `required: true` -> fail closed
- unsupported extension with `required: false` -> preserve and warn/report
- supported extension with invalid shape -> fail closed

### Derived runtime views

Add internal derived views before implementing more features:

- `ExecutionPlan` for graph traversal and per-node normalized configuration
- `PreparedModelInput` for pre-model context and prompt construction
- `EffectiveToolCatalog` or `PreparedToolRegistry` for tool provenance, exposure,
  policy, and callable availability
- `RunOutcome` / `StepOutcome` only when iterative loop semantics are selected

These should be internal implementation simplifications first. They do not need
to become public API immediately.

## Suggested implementation-order simplification

The current backlog includes E9–E12 and OA1–OA10. A simpler order would be:

1. **Normalization layer first**
   - Add internal `ExecutionPlan` / `PreparedNode` without changing public
     manifest semantics.
   - Move raw-field interpretation out of `executor.py`.

2. **Prepare-model-input seam second**
   - Implement OA3/E10 as a no-op or pass-through stage initially.
   - Move prompt rendering, token-budget checks, and prompt-cache observation into
     that stage.
   - This creates the future home for E11 and session pruning.

3. **Tool provenance third**
   - Implement OA2 as metadata-only `ToolOrigin` on registered/effective tools.
   - This makes E9 MCP and OA6 agent-as-tool simpler.

4. **MCP registry-source design fourth**
   - Design E9/OA4 around `ToolOrigin` and registry-source diagnostics, not a
     special executor branch.

5. **Guardrail metadata fifth**
   - Add OA1 declarations only after the prepare/tool provenance surfaces exist,
     because input/output/tool-input/tool-output guardrails need those boundaries.

6. **Approval interruption and sandbox later**
   - OA7 and OA10 should wait until write/command tools are explicitly scoped.
   - Do not implement durable run-state until there is a real approval pause or
     long-running resume requirement.

7. **Agent-loop semantics last**
   - OA5 and `StepOutcome`/`NextStep` style loops should wait until a future spec
     selects iterative agent execution. The finite graph executor should not be
     bent into a partial agent-loop framework prematurely.

## Recommended changes to the design reference

If updating `agent-runtime-package.md`, focus on these changes:

1. Add a section named **Core vs extension manifest contract**.
2. Replace the flat “Additional optional metadata fields” list with grouped
   extension categories.
3. Add a field-classification table: core executable, runtime policy, capability
   declaration, design metadata.
4. Add a recommended grouped manifest shape using `runtime`, `metadata`, and
   `extensions`.
5. State that older flat fields remain accepted for `format_version: 1` but new
   generated packages should prefer grouped fields.
6. Add a runner-facing recommendation to build a derived `ExecutionPlan` before
   adding more optional features.
7. Add a warning that optional metadata is not enforcement unless a runner module
   explicitly supports it.

## Recommended changes to `dynamic-agent-runner` planning artifacts

If updating this repository's specs/tasks, the most useful backlog addition is a
small simplification-focused slice before E9/OA feature work:

```markdown
## Proposed simplification prerequisite

- [ ] S1. Add an internal `ExecutionPlan` / `PreparedNode` normalization layer so
      the executor consumes normalized per-node configuration rather than raw
      manifest dictionaries.
- [ ] S2. Add a pass-through `prepare_model_input(...)` stage and move prompt
      rendering, token-budget checks, and prompt-cache observation behind it.
- [ ] S3. Add metadata-only `ToolOrigin` / `ToolSource` provenance to prepared
      registry tools before MCP or agent-as-tool support.
- [ ] S4. Update manifest guidance to classify fields as core executable,
      runtime policy, capability declaration, or design metadata.
```

This prerequisite would simplify E9, E10, E11, E12, OA1, OA2, OA3, OA4, and OA6
without committing to durable sessions, approvals, sandboxing, or iterative loops.

## What not to simplify

- Do not remove the artifact package boundary; it is the product's core value.
- Do not collapse tool metadata and callable registry entries.
- Do not make `agent-design.md` the executable source of truth.
- Do not make Mermaid authoritative over YAML.
- Do not add a broad provider abstraction to simplify OpenAI-specific code.
- Do not collapse finite graph execution and iterative agent-loop execution into
  one ambiguous executor loop.
- Do not make optional metadata enforceable until the runner explicitly supports
  that capability.

## Risks and tradeoffs

- **Backward compatibility:** moving toward grouped `runtime`, `metadata`, and
  `extensions` fields should be additive for `format_version: 1`. Existing flat
  fields can remain supported while new generators prefer grouped output.
- **Schema drift:** adding extension namespaces reduces root-field sprawl but
  requires each extension to define its own validation expectations.
- **Over-normalization:** `ExecutionPlan` should simplify executor code, not
  become a second schema that duplicates every manifest field. Keep it focused on
  executable views.
- **Premature capability modules:** pass-through seams are useful; full sessions,
  guardrails, approvals, MCP, or sandbox runtimes should still wait for scoped
  requirements.

## Bottom line

The current concept should be simplified by **organizing complexity**, not by
weakening the runtime package model. Keep the small graph executor. Keep explicit
artifacts. Keep registry-owned tools. The next simplification should introduce a
normalization layer and extension namespace so each planned capability can be
added as a narrow module instead of another raw manifest branch inside the
executor.

## Validation

- Read current external `agent-runtime-package.md` reference — pass.
- Read current `dynamic-agent-runner` spec, plan, and tasks — pass.
- Read prior Codex, Cline, combined, and OpenAI Agents SDK Python evaluations —
  pass.
- Read current implementation modules for artifact loading, models, validation,
  registry, context, behavior, API, and executor — pass.
- Runtime tests/builds — not run; this analysis changes only a markdown design
  artifact.
- Existing unrelated local changes observed before writing: modified
  `memory-bank/notes/historical-user-prompts.txt` and untracked `docs/`.
