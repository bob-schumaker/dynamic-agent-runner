# internal graph mutation specification

## Metadata

- Feature slug: `internal-graph-mutation`
- Mode: `guided`
- Artifact type: authoritative SDD feature specification
- Status: authoritative current follow-up feature spec
  - initial internal graph-mutation datamodel implementation now exists in
    `src/dynamic_agent_runner/graph_mutation.py`
  - T1.3 focused GREEN datamodel evidence now exists in
    `tests/test_graph_mutation.py`
  - T2.4 focused GREEN mutation-diagnostics evidence now exists in
    `tests/test_executor.py` and `src/dynamic_agent_runner/executor.py`
  - T2.3 focused GREEN mutation-runtime evidence now exists in
    `tests/test_graph_mutation.py` and `src/dynamic_agent_runner/executor.py`
  - T1.4 focused GREEN execution-plan seam evidence now exists in
    `tests/test_executor.py`
  - T1.5 focused GREEN validation evidence now exists in
    `tests/test_validation.py`
  - any earlier prototype work is non-authoritative historical context only
- Related artifacts:
  - `specs/dynamic-agent-runner/spec.md`
  - `specs/dynamic-agent-runner/references/graph-mutation-interface-design.md`
  - `specs/llama-cpp-local-model/spec.md`
  - `src/dynamic_agent_runner/behavior.py`
  - `src/dynamic_agent_runner/executor.py`
  - `src/dynamic_agent_runner/graph_mutation.py`

## Objective

Define the authoritative repository direction for an internal compile-time
graph-mutation layer that derives execution-ready workflows from immutable base
runtime packages, beginning with context-pruning attachment for selected
`llm_step` nodes.

## Problem Statement

`dynamic-agent-runner` already distinguishes:

- immutable package-directory-based workflow artifacts
- caller-owned override compilation into derived runtime state
- a compile and preparation phase centered on `prepare_execution_plan(...)`
- derived prompt and skill overlays in `behavior.py`

The repository does not yet have an authoritative feature-level source of truth
for how graph mutation should fit those seams. Earlier prototype work was
reverted, so future work must not improvise mutation semantics or treat
mutation as in-place editing of portable workflow artifacts.

## Users

- Runtime maintainers defining future workflow-derivation seams.
- Future implementers of context-pruning or related prepare-stage transforms.
- Downstream hosts that need derived workflow behavior without mutating base
  package artifacts.

## Existing Runtime Context

- The canonical executable input remains the immutable runtime package directory
  defined in `specs/dynamic-agent-runner/spec.md`.
- The runtime already has a derived overlay model for prompts and skills, which
  strongly suggests graph mutation should also be modeled as derivation rather
  than in-place mutation.
- The detailed design note in
  `specs/dynamic-agent-runner/references/graph-mutation-interface-design.md`
  already recommends internal typed mutation specs applied during preparation.
- A separate future spec at `specs/llama-cpp-local-model/spec.md` owns local
  llama.cpp support. Local embeddings may enable the first pruning use case,
  but graph mutation must remain architecturally independent from any one local
  model transport.

## Scope

This feature specification covers:

1. an internal graph-mutation seam applied during workflow preparation
2. typed internal mutation definitions rather than YAML-first public artifacts
3. context-pruning attachment as the first mutation target
4. required manifest metadata for safe mutation attachment
5. fail-closed validation rules for derived workflow mutation

## Current Status and Boundary

- The repository now contains an initial internal graph-mutation datamodel and
  protocol module at `src/dynamic_agent_runner/graph_mutation.py`.
- Any earlier prototype code or prior test results are historical context only
  and do not count as current implementation or validation evidence.
- This artifact is now the repository's current authoritative next-feature spec
  for context-pruning-oriented runtime expansion.
- Companion planning artifacts now live at:
  - `specs/internal-graph-mutation/plan.md`
  - `specs/internal-graph-mutation/tasks.md`
- This artifact remains authoritative for feature intent, scope, and design
  boundaries, while the companion plan and task list own the first
  implementation path and execution sequencing.
- The repository now has committed prepared-input executor integration that
  populates the mutation-owned output slot before prompt rendering for eligible
  `llm_step` nodes.
- The repository now also has a committed first live `ContextPruningMutation`
  implementation that owns prepared-context rendering from declared metadata and
  is invoked by the executor rather than duplicated there.
- The repository now also records mutation-application diagnostics in
  `PreparedInputMetadata` and `model_input_prepared` trace payloads so prepared
  inputs can distinguish unchanged vs transformed `llm_step` rendering.

## Functional Requirements

### FR-1: Treat graph mutation as compile-time derivation

The runtime must support graph mutation as a compile-time derivation layer over
an immutable base workflow package.

Acceptance criteria:

- Given a base runtime package has been loaded, when derived runtime preparation
  runs, then graph mutation is applied during compile and preparation rather
  than as in-place mutation of package artifacts.
- Given graph mutation is applied, when callers inspect the originally loaded
  package, then the base workflow definition remains unchanged.
- Given no mutations are configured, when the workflow is prepared, then
  execution continues with the unmodified derived workflow.

### FR-2: Keep mutation definitions internal and typed first

The initial graph-mutation contract must be internal to the runtime and modeled
through typed internal protocols or datamodels.

Acceptance criteria:

- Given the first mutation slice is implemented, when mutation specifications
  are represented internally, then the runtime uses an internal typed protocol
  or datamodel rather than a second full workflow-definition schema.
- Given multiple mutation types may exist later, when the initial seam is
  chosen, then it leaves room for mutation identifiers, validation notices,
  diagnostics, and bundle-style orchestration.
- Given portable workflow packages remain the canonical cross-repository
  artifact boundary, when mutation support is introduced, then mutation
  internals do not become required top-level package artifacts in the first
  slice.

### FR-3: Use context pruning as the first mutation target

The first graph-mutation target must be internal context-pruning attachment for
selected `llm_step` nodes.

Acceptance criteria:

- Given a target `llm_step` is marked as eligible for context-pipeline
  preparation, when the first mutation is applied, then prompt or context input
  can be routed through internal pruning logic before the target model call.
- Given the first mutation slice is intentionally narrow, when implementation is
  chosen, then an input-transform-style mutation is acceptable even if no new
  visible graph node is inserted yet.
- Given future mutation needs may become more structural, when the first slice
  is designed, then the conceptual mutation seam still allows later evolution
  to true derived node and edge rewiring.

### FR-4: Require explicit workflow metadata for safe attachment

Portable workflow definitions must provide small, explicit metadata seams for
safe context-pipeline attachment.

Acceptance criteria:

- Given a workflow node is eligible for context mutation, when the portable
  manifest expresses that eligibility, then the manifest uses explicit metadata
  such as `context_pipeline` or `input_preparation` rather than implicit
  runtime guessing.
- Given pruning depends on declared input sources, when the workflow is
  prepared, then structured context-source metadata is available for the target
  node.
- Given pruning emits prepared context for the target node, when mutation is
  validated, then the input and output contract is explicit enough to avoid
  hidden coupling to prompt-template internals.
- Given higher-level strategy selection is useful, when the workflow opts into a
  pruning pipeline, then optional strategy or profile identifiers may be
  declared without forcing low-level implementation details into the portable
  manifest.

### FR-5: Validate graph mutation conservatively

The first graph-mutation slice must fail closed when required attachment or
workflow invariants are missing.

Acceptance criteria:

- Given a mutation targets a node that does not exist, when validation runs,
  then the runtime fails clearly before execution.
- Given a mutation targets a node that is not an eligible `llm_step`, when
  validation runs, then the runtime fails clearly before execution.
- Given required context-source or context-contract metadata is missing, when
  the mutation is prepared, then the runtime fails clearly rather than
  inferring hidden behavior.
- Given a mutation would orphan edges, remove the entrypoint, or otherwise make
  the derived workflow invalid, when validation runs, then the runtime rejects
  the derived workflow before execution.

## Non-Goals

- No local-model transport design in this feature.
- No requirement to model mutations as peer executable workflow packages.
- No requirement that the first slice perform full visible graph surgery or
  Mermaid rewriting.
- No requirement to expose a stable public YAML mutation schema in the first
  implementation slice.

## Design Constraints

- Preserve immutable base workflow artifacts and derived runtime layering.
- Keep mutation semantics internal until the repository has enough experience to
  justify a stable public artifact contract.
- Keep manifest additions small, explicit, and portable.
- Prefer the narrowest initial implementation that honestly supports the first
  context-pruning use case while preserving a path to richer structural
  mutation later.

## Validation Status

- This spec is authoritative for intended future behavior and boundaries.
- Fresh focused GREEN evidence now exists from:
  - `poetry run pytest tests/test_graph_mutation.py -q`
    - `test_workflow_mutation_bundle_can_describe_context_pruning_target`
    - `test_mutation_result_preserves_workflow_and_notices`
    - `test_workflow_graph_mutation_protocol_supports_apply_contract`
    - `test_context_pruning_mutation_renders_prepared_context_from_declared_sources`
    - `test_apply_workflow_mutations_aggregates_context_pruning_mutation_results`
    - observed result: `5 passed`
  - earlier `poetry run pytest tests/test_executor.py -q`
    - `test_prepare_execution_plan_keeps_base_workflow_unchanged_for_context_pipeline_nodes`
    - `test_prepare_execution_plan_derives_mutation_preparation_for_eligible_llm_step`
  - `poetry run pytest tests/test_validation.py -q`
    - `test_context_pipeline_attachment_requires_explicit_sources_and_contract`
    - `test_context_pipeline_attachment_rejects_non_llm_step_nodes`
    - observed result: `55 passed`
  - `poetry run pytest tests/test_executor.py -q -k`
    `"mutation_preparation_diagnostics or`
    `context_pipeline_prepared_context_before_render or`
    `context_contract_output_slot_name"`
    - `test_prepare_model_input_records_mutation_preparation_diagnostics`
    - `test_prepare_model_input_applies_context_pipeline_prepared_context_before_render`
    - `test_prepare_model_input_respects_context_contract_output_slot_name`
    - observed result: `3 passed, 52 deselected`
  - `poetry run pytest tests/test_executor.py -q`
    - observed result: `55 passed`
- The passing graph-mutation checkpoint proves the repository now has internal
  typed mutation datamodels, mutation orchestration, and a first live
  `ContextPruningMutation` runtime that can render the first context-pruning
  target from declared metadata.
- The passing executor checkpoint proves the repository now derives a
  workflow-level mutation bundle and per-node mutation-preparation seam during
  `prepare_execution_plan(...)` without mutating the base loaded workflow.
- The passing validation checkpoint proves the repository now enforces a
  fail-closed attachment contract for explicit `context_pipeline`,
  `context_sources`, and `context_contract` metadata on eligible `llm_step`
  nodes and rejects ineligible attachment targets before execution.
- The passing prepared-input checkpoint proves `prepare_model_input(...)` now
  assembles a mutation-aware render context before prompt formatting, including
  declared output slots such as `prepared_context` and `context_window`, while
  delegating the context-pruning transform itself to the runtime-owned mutation
  implementation.
- The passing diagnostics checkpoint proves prepared-input metadata and
  `model_input_prepared` trace payloads now expose runtime-owned mutation
  diagnostics, including whether mutation was applied, which mutation id ran,
  and which prepared output slots were populated.
- A fresh focused combined validation checkpoint now exists from
  `poetry run pytest tests/test_graph_mutation.py tests/test_validation.py`
  `tests/test_executor.py -q` with observed result `115 passed`, proving the
  internal mutation contract, fail-closed validation, prepared-input behavior,
  and mutation diagnostics remain green together across the first-slice test
  surfaces.
- Future implementation work must create fresh validation evidence rather than
  relying on any reverted prototype results.
