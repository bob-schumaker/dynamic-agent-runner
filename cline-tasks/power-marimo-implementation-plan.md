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
  S5.
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

**Status:** Complete in commit `695c0cc`.

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

- [x] Current grouped runtime manifests load and validate.
- [x] Legacy flat optional root fields fail or report clearly.
- [x] `output_contracts` array entries still support existing output validation.
- [x] All existing fixture packages are migrated and continue to load.

Completion evidence:

- Commit: `695c0cc` (`feat(models): support grouped runtime manifests`).
- `poetry run pytest -q` — pass; 164 tests passed.
- `pre-commit run --files <S1 changed files>` — pass.

### Slice S2 — ExecutionPlan and PreparedNode normalization

**Status:** Complete in commit `b315c96`.

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

- [x] Executor behavior remains unchanged for existing finite graph workflows.
- [x] Unsupported or ignored grouped manifest features are visible in preparation
  reports or traceable validation errors.
- [x] Future feature slices can attach behavior to `PreparedNode` without raw
  manifest surgery.

Completion evidence:

- Commit: `b315c96` (`feat(executor): add prepared execution plan`).
- RED: `poetry run pytest
  tests/test_executor.py::test_prepare_execution_plan_resolves_node_indexes_and_defaults
  -q` — failed because `prepare_execution_plan` did not exist yet.
- GREEN: same targeted test — pass; 1 test passed.
- Targeted validation: `poetry run pytest tests/test_executor.py
  tests/test_validation.py tests/test_registry.py -q` — pass; 78 tests passed.
- Full validation: `poetry run pytest -q` — pass; 165 tests passed.
- `pre-commit run --files src/dynamic_agent_runner/models.py
  src/dynamic_agent_runner/executor.py tests/test_executor.py` — pass after Ruff
  Format rewrote `src/dynamic_agent_runner/executor.py` once.
- Note: planned validation referenced `tests/test_behavior.py`, but that file does
  not exist in this repository; the S2 targeted suite used existing executor,
  validation, and registry tests instead.

### Slice S3 — PreparedModelInput and prepare_model_input seam

**Status:** Complete in commit `33096b5`.

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

- [x] Existing `llm_step` execution output remains stable.
- [x] Token-budget and prompt-cache trace evidence still appears as before.
- [x] Named prepared input parts can later include notebook state, SLD summaries,
  and domain tool results.

Completion evidence:

- Commit: `33096b5` (`feat(executor): add prepared model input seam`).
- RED: `poetry run pytest
  tests/test_executor.py::test_prepare_model_input_renders_messages_and_named_parts
  -q` — failed because `prepare_model_input` did not exist yet.
- GREEN: same targeted test — pass; 1 test passed.
- Focused seam checks: `poetry run pytest
  tests/test_executor.py::test_prepare_model_input_renders_messages_and_named_parts
  tests/test_executor.py::test_execute_workflow_records_token_usage_when_budget_enabled
  tests/test_prompt_cache.py::test_prompt_cache_trace_records_eligibility_and_prefix_evidence
  -q` — pass; 3 tests passed.
- Targeted validation: `poetry run pytest tests/test_executor.py
  tests/test_prompt_cache.py tests/test_token_budget.py tests/test_tracing.py
  -q` — pass; 62 tests passed.
- Full validation: `poetry run pytest -q` — pass; 166 tests passed.
- `pre-commit run --files src/dynamic_agent_runner/executor.py
  tests/test_executor.py` — pass after replacing an unnecessary dict
  comprehension flagged by Ruff.

### Slice S4 — ToolOrigin and ToolSource provenance

**Status:** Complete in commit `a46bb5a`.

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

- [x] Existing tool invocation behavior remains unchanged.
- [x] Tool provenance is available for diagnostics and future source-specific
  policy.
- [x] Runtime overrides preserve clear provenance when they add or replace tools.

Completion evidence:

- Commit: `a46bb5a` (`feat(registry): add tool source provenance`).
- RED: `poetry run pytest
  tests/test_registry.py::test_tool_definition_records_manifest_and_index_source_metadata
  tests/test_registry.py::test_runtime_overrides_add_replace_disable_and_restrict_per_node
  tests/test_registry.py::test_local_workspace_tool_pack_is_opt_in_and_path_restricted
  -q` — failed because `ToolSource` did not exist yet.
- RED: `poetry run pytest
  tests/test_tracing.py::test_model_request_trace_includes_model_exposed_tool_sources
  -q` — failed because model-request traces did not include `tool_sources`.
- GREEN: `poetry run pytest
  tests/test_tracing.py::test_model_request_trace_includes_model_exposed_tool_sources
  tests/test_registry.py::test_tool_definition_records_manifest_and_index_source_metadata
  tests/test_registry.py::test_runtime_overrides_add_replace_disable_and_restrict_per_node
  tests/test_registry.py::test_local_workspace_tool_pack_is_opt_in_and_path_restricted
  -q` — pass; 4 tests passed.
- Targeted validation: `poetry run pytest tests/test_registry.py
  tests/test_tracing.py tests/test_validation.py -q` — pass; 49 tests passed.
- Full validation: `poetry run pytest -q` — pass; 168 tests passed.
- `pre-commit run --files src/dynamic_agent_runner/models.py
  src/dynamic_agent_runner/registry.py src/dynamic_agent_runner/executor.py
  tests/test_registry.py tests/test_tracing.py` — pass.

### Slice S5 — Power-Marimo runtime-package fixture or example

**Goal:** Create a narrow first-customer fixture that proves the grouped manifest
and preparation seams can represent the intended `power-marimo` notebook agent.

Deliverables:

- Add a fixture or example runtime package for a supervised Marimo notebook power
  experiment agent.
- Keep it placeholder-safe: no live Marimo server, no real SLD data, no live
  `power-tetris-sdk` calls.
- Model the downstream `marimo-pair` capability as an agent-as-tool node: it is
  backed by `../power-marimo/skills/marimo-pair/SKILL.md` and invoked to perform
  a specific bounded Marimo task rather than treated as a primitive runtime node
  or durable handoff.
- Model the workflow with primitive nodes:
  - analyze user experiment request
  - invoke the `marimo-pair` agent-as-tool for the bounded notebook operation
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
- The fixture records `marimo-pair` as an agent-as-tool/SKILL-backed invocation,
  distinct from primitive node kinds and from handoff-style multi-agent metadata.
- Fake tools can exercise the bounded happy path, or the unsupported live path
  fails with a clear error.
- The fixture demonstrates a supervised, bounded agent rather than free-form
  autonomous notebook mutation.

Completion evidence:

- Commit: `84dfd31` (`test(power-marimo): add runtime package fixture`).
- RED: `poetry run pytest tests/test_power_marimo_fixture.py -q` — failed
  because `tests/fixtures/power-marimo/agent-runtime.yaml` did not exist yet.
- GREEN: `poetry run pytest tests/test_power_marimo_fixture.py -q` — pass; 2
  tests passed after adding the placeholder fixture and correcting the final
  prompt input to use the produced node output.
- Targeted validation: `poetry run pytest tests/test_power_marimo_fixture.py
  tests/test_agent_pattern_fixtures.py -q` — pass; 4 tests passed.
- Pre-commit: `pre-commit run --files tests/test_power_marimo_fixture.py
  tests/fixtures/power-marimo/agent-runtime.yaml
  tests/fixtures/power-marimo/agent-graph.mmd
  tests/fixtures/power-marimo/agent-design.md` — pass.

## Recommended Commit Boundaries

Use one commit per slice when the slice is implemented:

1. [x] `feat(models): support grouped runtime manifests` — `695c0cc`
2. [x] `feat(executor): add prepared execution plan` — `b315c96`
3. [x] `feat(executor): add prepared model input seam` — `33096b5`
4. [x] `feat(registry): add tool source provenance` — `a46bb5a`
5. [x] `test(power-marimo): add runtime package fixture` — `84dfd31`

For each slice, update `specs/dynamic-agent-runner/tasks.md` with completion
evidence and run targeted validation before committing.

## Risks and Open Questions

- Existing fixtures and tests assumed flat root metadata; S1 migrated them in
  commit `695c0cc`.
- `output_contracts` migration from mapping to array must preserve current
  output validation behavior; S1 and S2 validations preserved existing contract
  behavior.
- `ExecutionPlan` is now implemented as an internal normalized execution view in
  commit `b315c96`; it should not become a second public manifest format.
- `PreparedModelInput` now preserves current prompt semantics in commit
  `33096b5`; notebook-state and retrieval features remain future extension
  points.
- `ToolSource` now records diagnostic/provenance metadata in commit `a46bb5a`;
  it should remain non-enforcing until a later policy slice defines
  source-specific enforcement.
- The downstream `marimo-pair` capability should be represented in S5 as an
  agent-as-tool invocation backed by `SKILL.md`, not as a new primitive node kind
  or a durable handoff pattern; S5 implemented that as placeholder fixture
  metadata in commit `84dfd31`.
- `power-marimo` live notebook automation remains out of scope for this plan;
  S5 intentionally uses fake tools, synthetic domain output, and placeholder
  Marimo metadata only.

## Completion Standard

This implementation track is complete when:

- grouped manifests are the local runtime contract
- legacy flat optional root fields are rejected or clearly reported
- executor code consumes a prepared internal execution view
- model input preparation has a stable seam for future Marimo context
- tool provenance exists before new registry source types are added
- a bounded `power-marimo` fixture proves the first-customer shape without live
  external dependencies
- the `marimo-pair` fixture path is represented as an agent-as-tool/SKILL-backed
  operation rather than a new runtime primitive
