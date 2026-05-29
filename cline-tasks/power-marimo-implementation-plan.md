# Power-Marimo Support Implementation Plan

## Goal

Turn the `power-marimo` first-customer analysis into an ordered
`dynamic-agent-runner` implementation sequence. The target is a safe,
supervised, bounded workflow-orchestration runtime path for an AI-assisted
Marimo notebook proof of concept, without prematurely implementing free-form
notebook autonomy, durable approval pause/resume, MCP discovery, or PyQt widget
runtime support.

## Source References

- `cline-tasks/power-marimo-analysis.md` — working analysis note from the
  `../power-marimo` repository inspection.
- `specs/dynamic-agent-runner/references/power-marimo-agent-support-analysis.md`
  — spec-local supporting reference used by the current SDD artifacts.
- `specs/dynamic-agent-runner/spec.md` — governing runtime requirements.
- `specs/dynamic-agent-runner/tasks.md` — active task list; next active slice is
  S1.
- `../power-marimo/specs/project-roadmap/spec.md` — downstream roadmap context.
- `../power-marimo/skills/marimo-pair/SKILL.md` — downstream notebook-operation
  and safety contract.

## Current Baseline

`dynamic-agent-runner` currently supports a finite graph executor with primitive
node kinds:

- `llm_step`
- `tool_use_step`
- `decision_step`

It also supports:

- async-first execution and sync wrappers
- callable tool registry and opt-in read-only local workspace tools
- output contracts and route validation
- prompt and skill behavior overrides
- token budgeting, retries, tracing, hooks, and prompt-cache observation

However, the local runtime model still needs to catch up with the upstream
runtime-package schema that now uses grouped `runtime`, `metadata`, and
`extensions` maps and `output_contracts` as an array.

## Non-Goals

Do not include these in the first implementation sequence unless the user
explicitly re-scopes the work:

- live Marimo notebook automation in this repository
- `power-marimo` first-party source implementation
- durable approval pauses or resumable notebook mutation state
- MCP-style dynamic tool discovery
- broad ReAct notebook autonomy
- PyQt/PySide embedded Marimo widget support
- provider-specific prompt-cache request pass-through

## Implementation Sequence

### Slice S1 — Grouped runtime manifest model and validation

**Goal:** Make `dynamic-agent-runner` consume the current upstream
`format_version: 1` runtime-package schema.

Deliverables:

- Update `RuntimeManifest` to parse grouped maps:
  - `runtime`
  - `metadata`
  - `extensions`
- Preserve current convenience accessors where useful, but derive them from the
  grouped maps rather than old flat root fields.
- Parse `output_contracts` as an array of contract objects.
- Add validation for extension envelopes:
  - unsupported `required: true` extensions fail closed
  - unsupported `required: false` extensions are preserved and reported when a
    report channel exists
  - malformed extension envelopes fail validation
- Reject or clearly report legacy pre-customer flat optional root fields:
  - `execution_policy`
  - `state`
  - `patterns_present`
  - `participant_groups`
  - `modes`
  - `phases`
  - `roles`
  - `runtime_surface`
  - `workspace_boundary`
  - `completion_contract`
- Update all agent-pattern fixtures to the grouped manifest shape.
- Update tests that currently assume flat optional manifest fields.

Likely files:

- `src/dynamic_agent_runner/models.py`
- `src/dynamic_agent_runner/validation.py`
- `src/dynamic_agent_runner/executor.py`
- `src/dynamic_agent_runner/prompt_cache.py`
- `tests/test_artifacts.py`
- `tests/test_validation.py`
- `tests/test_executor.py`
- `tests/test_prompt_cache.py`
- `tests/fixtures/agent-patterns/**/agent-runtime.yaml`

Validation:

```bash
poetry run pytest tests/test_artifacts.py tests/test_validation.py \
  tests/test_executor.py tests/test_prompt_cache.py \
  tests/test_agent_pattern_fixtures.py -q
pre-commit run --files <changed files>
```

Acceptance criteria:

- Current grouped runtime manifests load and validate.
- Legacy flat optional root fields fail or report clearly.
- `output_contracts` array entries still support existing output validation.
- All existing fixture packages are migrated and continue to load.

### Slice S2 — ExecutionPlan and PreparedNode normalization

**Goal:** Stop spreading raw manifest dictionary interpretation across executor,
validation, prompt-cache, and registry preparation code.

Deliverables:

- Add internal immutable preparation models such as:
  - `ExecutionPlan`
  - `PreparedNode`
  - optional `PreparedToolBinding` if needed
- Resolve defaults and indexes once during preparation.
- Separate executable control flow from metadata overlays and unsupported
  extension reports.
- Keep public API compatibility where practical.
- Route executor code through prepared nodes rather than raw `RuntimeNode.raw`
  lookups.

Likely files:

- `src/dynamic_agent_runner/models.py`
- `src/dynamic_agent_runner/executor.py`
- `src/dynamic_agent_runner/validation.py`
- `src/dynamic_agent_runner/behavior.py`
- `src/dynamic_agent_runner/registry.py`
- `tests/test_executor.py`
- `tests/test_validation.py`

Validation:

```bash
poetry run pytest tests/test_executor.py tests/test_validation.py \
  tests/test_registry.py tests/test_behavior.py -q
pre-commit run --files <changed files>
```

Acceptance criteria:

- Executor behavior remains unchanged for existing finite graph workflows.
- Unsupported or ignored grouped manifest features are visible in preparation
  reports or traceable validation errors.
- Future feature slices can attach behavior to `PreparedNode` without raw
  manifest surgery.

### Slice S3 — PreparedModelInput and prepare_model_input seam

**Goal:** Add the seam needed for Marimo notebook-state context construction
without implementing full context-management automation yet.

Deliverables:

- Add `PreparedModelInput` to represent rendered model messages plus named input
  parts.
- Add `prepare_model_input(...)` as the model-input preparation boundary for
  `llm_step` nodes.
- Move prompt rendering, token-budget checks, prompt-cache observation, and
  behavior override integration behind this seam where practical.
- Preserve current prompt rendering semantics.
- Leave session pruning, compaction, retrieval, and notebook-state injection as
  future extension points.

Likely files:

- `src/dynamic_agent_runner/executor.py`
- `src/dynamic_agent_runner/behavior.py`
- `src/dynamic_agent_runner/prompt_cache.py`
- `src/dynamic_agent_runner/token_budget.py`
- `src/dynamic_agent_runner/models.py`
- `tests/test_executor.py`
- `tests/test_prompt_cache.py`
- `tests/test_token_budget.py`

Validation:

```bash
poetry run pytest tests/test_executor.py tests/test_prompt_cache.py \
  tests/test_token_budget.py tests/test_tracing.py -q
pre-commit run --files <changed files>
```

Acceptance criteria:

- Existing `llm_step` execution output remains stable.
- Token-budget and prompt-cache trace evidence still appears as before.
- Named prepared input parts can later include notebook state, SLD summaries, and
  domain tool results.

### Slice S4 — ToolOrigin and ToolSource provenance

**Goal:** Prepare the registry model for mixed tool origins before Marimo-session,
MCP, domain-SDK, or agent-as-tool sources are added.

Deliverables:

- Add a small provenance model such as `ToolOrigin` or `ToolSource`.
- Record origin information for:
  - manifest declarations
  - external tool index entries
  - built-in local workspace tools
  - runtime overrides
  - caller-registered tools
- Keep provenance metadata separate from callable dispatch and tool exposure.
- Include origin metadata in trace payloads or preparation reports where useful.

Likely files:

- `src/dynamic_agent_runner/models.py`
- `src/dynamic_agent_runner/registry.py`
- `src/dynamic_agent_runner/tracing.py`
- `tests/test_registry.py`
- `tests/test_tracing.py`

Validation:

```bash
poetry run pytest tests/test_registry.py tests/test_tracing.py \
  tests/test_validation.py -q
pre-commit run --files <changed files>
```

Acceptance criteria:

- Existing tool invocation behavior remains unchanged.
- Tool provenance is available for diagnostics and future source-specific policy.
- Runtime overrides preserve clear provenance when they add or replace tools.

### Slice S5 — Power-Marimo runtime-package fixture or example

**Goal:** Create a narrow first-customer fixture that proves the grouped manifest
and preparation seams can represent the intended `power-marimo` notebook agent.

Deliverables:

- Add a fixture or example runtime package for a supervised Marimo notebook power
  experiment agent.
- Keep it placeholder-safe: no live Marimo server, no real SLD data, no live
  `power-tetris-sdk` calls.
- Model the workflow with primitive nodes:
  - analyze user experiment request
  - inspect or validate notebook/session state
  - run placeholder domain experiment tool
  - prepare notebook cell plan
  - summarize result
- Include placeholder tool definitions for:
  - `discover_marimo_servers`
  - `execute_marimo_code`
  - `inspect_notebook_state`
  - `run_room_power_analysis`
- Encode Marimo guardrails in `runtime.execution_policy` and tool policy.
- Validate that the fixture loads and either executes with fake tools or fails
  clearly for intentionally unsupported live behavior.

Likely files:

- `tests/fixtures/power-marimo/agent-runtime.yaml`
- `tests/fixtures/power-marimo/agent-graph.mmd`
- `tests/fixtures/power-marimo/agent-design.md`
- `tests/test_power_marimo_fixture.py`
- optional README or fixture note under `tests/fixtures/power-marimo/`

Validation:

```bash
poetry run pytest tests/test_power_marimo_fixture.py \
  tests/test_agent_pattern_fixtures.py -q
pre-commit run --files <changed files>
```

Acceptance criteria:

- The fixture uses grouped `runtime`, `metadata`, and `extensions` maps.
- The fixture validates against current runtime semantics.
- Fake tools can exercise the bounded happy path, or the unsupported live path
  fails with a clear error.
- The fixture demonstrates a supervised, bounded agent rather than free-form
  autonomous notebook mutation.

## Recommended Commit Boundaries

Use one commit per slice when the slice is implemented:

1. `feat(models): support grouped runtime manifests`
2. `refactor(executor): add prepared execution plan`
3. `refactor(executor): add prepared model input seam`
4. `feat(registry): add tool provenance metadata`
5. `test(fixtures): add power-marimo runtime package`

For each slice, update `specs/dynamic-agent-runner/tasks.md` with completion
evidence and run targeted validation before committing.

## Risks and Open Questions

- Existing fixtures and tests may assume flat root metadata; migrating them is
  part of S1 and may touch many files.
- `output_contracts` migration from mapping to array must preserve current
  output validation behavior.
- `ExecutionPlan` should not become a second public manifest format; it is an
  internal normalized view.
- `PreparedModelInput` should preserve current prompt semantics before adding
  notebook-state or retrieval features.
- `ToolOrigin` should remain diagnostic/provenance metadata until a later policy
  slice defines source-specific enforcement.
- `power-marimo` still lacks first-party source, tests, and safe domain fixtures,
  so live notebook automation should stay out of scope for this plan.

## Completion Standard

This implementation track is complete when:

- grouped manifests are the local runtime contract
- legacy flat optional root fields are rejected or clearly reported
- executor code consumes a prepared internal execution view
- model input preparation has a stable seam for future Marimo context
- tool provenance exists before new registry source types are added
- a bounded `power-marimo` fixture proves the first-customer shape without live
  external dependencies
