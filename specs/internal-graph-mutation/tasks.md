# Internal Graph Mutation Task List

Status: complete through Slice 4 pruning-context graph injection follow-up

## Prerequisites

- Spec: `specs/internal-graph-mutation/spec.md`
- Plan: `specs/internal-graph-mutation/plan.md`
- Data model: `src/dynamic_agent_runner/graph_mutation.py`
- Contracts: internal mutation protocol and datamodels in
  `src/dynamic_agent_runner/graph_mutation.py`

## Status

- State: authoritative spec and implementation plan exist; T1.1, T1.2, and T2.1
  RED coverage plus the T1.3, T1.4, T1.5, T2.2, T2.3, and T2.4 implementation
  slices are now committed
- Current execution gate: Slice 4 is complete; no additional graph-mutation
  pruning-context tasks are open
- Current GREEN evidence:
  - `poetry run pytest tests/test_graph_mutation.py -q` -> `5 passed`
  - `poetry run pytest tests/test_validation.py -q` -> `55 passed`
  - `poetry run pytest tests/test_executor.py -q -k`
    `"mutation_preparation_diagnostics or`
    `context_pipeline_prepared_context_before_render or`
    `context_contract_output_slot_name"` -> `3 passed, 52 deselected`
  - `poetry run pytest tests/test_executor.py -q` -> `55 passed`
  - `poetry run pytest tests/test_graph_mutation.py tests/test_validation.py`
    `tests/test_executor.py -q` -> `115 passed`
- Next implementation steps:
  - No additional tasks are currently scheduled in this artifact set
- Scope rule: keep the first completed checkpoint input-transform-only; do not
  introduce public mutation-package artifacts, true graph surgery, or
  llama.cpp/local-embedding transport ownership into these tasks. Future
  graph-mutation work may add structural insertion, edge rewiring, or
  link-level operations through a new approved task slice.

## Slice 1 — Mutation metadata contract and internal seam

- [x] T1.1 [tests] Add failing validation coverage in `tests/test_validation.py`
      for explicit context-pipeline attachment metadata on eligible `llm_step`
      nodes.
  - Spec: FR-3, FR-4, FR-5
  - Plan: Technical Summary; Proposed portable attachment metadata
  - Files/components: `tests/test_validation.py`,
    `src/dynamic_agent_runner/validation.py`
  - Domain context: the first slice must fail closed when mutation attachment is
    implicit, incomplete, or attached to an ineligible node
  - Depends on: none
  - Validation: `poetry run pytest tests/test_validation.py -q`
  - Evidence: `poetry run pytest tests/test_validation.py -q` currently fails on
    `test_context_pipeline_attachment_requires_explicit_sources_and_contract`
    and `test_context_pipeline_attachment_rejects_non_llm_step_nodes`, proving
    the context-pipeline metadata contract and corresponding validation do not
    yet exist

- [x] T1.2 [tests] Add failing mutation-seam coverage in `tests/test_executor.py`
      and/or `tests/test_graph_mutation.py` proving the base workflow remains
      unchanged while eligible `llm_step` nodes can receive derived mutation
      preparation.
  - Spec: FR-1, FR-2, FR-3
  - Plan: First-slice compile-time mutation flow; Internal mutation contract
  - Files/components: `tests/test_executor.py`,
    `tests/test_graph_mutation.py`, `src/dynamic_agent_runner/graph_mutation.py`
  - Domain context: graph mutation is a compile-time derivation layer, not an
    in-place edit of portable artifacts
  - Depends on: none
  - Validation: `poetry run pytest tests/test_executor.py -q`
  - Evidence: `poetry run pytest tests/test_executor.py -q` currently fails on
    `test_prepare_execution_plan_keeps_base_workflow_unchanged_for_context_pipeline_nodes`
    and `test_prepare_execution_plan_derives_mutation_preparation_for_eligible_llm_step`,
    proving no internal mutation bundle or per-node mutation-preparation seam
    exists yet

- [x] T1.3 [implementation] Add `src/dynamic_agent_runner/graph_mutation.py`
      with the first internal mutation protocol and datamodels.
  - Spec: FR-1, FR-2
  - Plan: Chosen approach; Internal mutation contract
  - Files/components: `src/dynamic_agent_runner/graph_mutation.py`
  - Depends on: T1.2
  - Validation: `poetry run pytest tests/test_graph_mutation.py -q`
  - Evidence: `poetry run pytest tests/test_graph_mutation.py -q` now passes with
    `3 passed`, proving repository-owned types such as
    `WorkflowGraphMutation`, `GraphMutationSpec`, `WorkflowMutationBundle`, and
    `MutationResult` exist and can represent the first context-pruning target

- [x] T1.4 [implementation] Integrate the mutation seam with
      `prepare_execution_plan(...)` so eligible nodes receive derived mutation
      preparation without mutating the base workflow.
  - Spec: FR-1, FR-2, FR-3
  - Plan: First-slice compile-time mutation flow
  - Files/components: `src/dynamic_agent_runner/models.py`,
    `src/dynamic_agent_runner/graph_mutation.py`
  - Depends on: T1.2, T1.3
  - Validation: `poetry run pytest tests/test_executor.py -q`
  - Evidence: `poetry run pytest tests/test_executor.py -q` now passes with
    `52 passed`, proving execution-plan preparation carries a mutation-owned
    workflow bundle and per-node derived mutation behavior while
    `LoadedAgentWorkflow` / `RuntimeManifest` stay unchanged

- [x] T1.5 [implementation] Extend `src/dynamic_agent_runner/validation.py` to
      reject missing or ambiguous mutation attachment metadata.
  - Spec: FR-4, FR-5
  - Plan: Affected Areas; Proposed portable attachment metadata
  - Files/components: `src/dynamic_agent_runner/validation.py`,
    `tests/test_validation.py`
  - Depends on: T1.1
  - Validation: `poetry run pytest tests/test_validation.py -q`
  - Evidence: `poetry run pytest tests/test_validation.py -q` now passes with
    `55 passed`, proving the repository enforces fail-closed attachment
    metadata for eligible `llm_step` nodes and rejects ineligible attachment
    targets before execution

## Slice 2 — Prepared-input integration for context-pruning attachment

- [x] T2.1 [tests] Add failing prepared-input coverage in `tests/test_executor.py`
      for routing declared context inputs through an internal mutation-owned
      transform before `llm_step` model execution.
  - Spec: FR-3, FR-4
  - Plan: Prepared-input mutation integration
  - Files/components: `tests/test_executor.py`,
    `src/dynamic_agent_runner/executor.py`
  - Domain context: the first live behavior should be a narrow input transform,
    not visible graph surgery
  - Depends on: T1.4, T1.5
  - Validation: `poetry run pytest tests/test_executor.py -q`
  - Evidence: `poetry run pytest tests/test_executor.py -q -k`
    `"context_pipeline_prepared_context_before_render or`
    `context_contract_output_slot_name"`
    now fails on
    `test_prepare_model_input_applies_context_pipeline_prepared_context_before_render`
    and `test_prepare_model_input_respects_context_contract_output_slot_name`
    with `missing prompt input 'prepared_context'` and `missing prompt input
    'context_window'`, proving prepared-input assembly still renders the prompt
    before mutation-owned output-slot population

- [x] T2.2 [implementation] Extend `prepare_model_input(...)` and adjacent
      executor helpers so mutation-derived prepared context is applied before
      request construction.
  - Spec: FR-1, FR-3
  - Plan: First-slice compile-time mutation flow; Executor integration contract
  - Files/components: `src/dynamic_agent_runner/executor.py`,
    `src/dynamic_agent_runner/models.py`
  - Depends on: T2.1
  - Validation: `poetry run pytest tests/test_executor.py -q`
  - Evidence: `poetry run pytest tests/test_executor.py -q -k`
    `"context_pipeline_prepared_context_before_render or`
    `context_contract_output_slot_name"` now passes with `2 passed, 52
    deselected`, and `poetry run pytest tests/test_executor.py -q` passes with
    `54 passed`, proving prepared model input includes the mutation-owned context
    output in a deterministic pre-model stage before prompt rendering

- [x] T2.3 [implementation] Add the first `ContextPruningMutation`
      implementation that consumes declared context metadata and produces a narrow
      repository-owned prepared-context transform.
  - Spec: FR-3, FR-4
  - Plan: Delivery Strategy Slice 2; Internal mutation contract
  - Files/components: `src/dynamic_agent_runner/graph_mutation.py`,
    `src/dynamic_agent_runner/executor.py`
  - Depends on: T1.3, T1.4, T2.2
  - Validation: `poetry run pytest tests/test_graph_mutation.py -q`
  - Evidence: `poetry run pytest tests/test_graph_mutation.py -q` now passes with
    `5 passed`, and `poetry run pytest tests/test_executor.py -q -k`
    `"context_pipeline_prepared_context_before_render or`
    `context_contract_output_slot_name or`
    `prepare_execution_plan_derives_mutation_preparation_for_eligible_llm_step"`
    passes with `3 passed, 51 deselected`, proving the first mutation target now
    exists as an internal context-pruning runtime and the executor delegates the
    prepared-context transform to it without regressing earlier seams

- [x] T2.4 [implementation] Record clear preparation diagnostics for mutation
      application so tests and traces can distinguish unchanged vs transformed
      `llm_step` inputs.
  - Spec: FR-1, FR-3, FR-5
  - Plan: Prepared-input mutation integration
  - Files/components: `src/dynamic_agent_runner/executor.py`,
    `tests/test_executor.py`
  - Depends on: T2.2, T2.3
  - Validation: `poetry run pytest tests/test_executor.py -q`
  - Evidence: `poetry run pytest tests/test_executor.py -q -k`
    `"mutation_preparation_diagnostics or`
    `context_pipeline_prepared_context_before_render or`
    `context_contract_output_slot_name"` now passes with `3 passed, 52
    deselected`, and `poetry run pytest tests/test_executor.py -q` passes with
    `55 passed`, proving mutation application status is now visible through
    prepared-input metadata and `model_input_prepared` trace diagnostics for
    transformed vs unchanged `llm_step` inputs

## Slice 3 — Validation evidence and artifact follow-up

- [x] T3.1 [tests] Run the focused mutation validation suite and record the
      outcome.
  - Spec: FR-1 through FR-5
  - Plan: Validation Strategy
  - Files/components: `tests/test_graph_mutation.py`, `tests/test_validation.py`,
    `tests/test_executor.py`
  - Depends on: T1.5, T2.4
  - Validation:
    `poetry run pytest tests/test_graph_mutation.py`
    `tests/test_validation.py tests/test_executor.py -q`
  - Evidence: `poetry run pytest tests/test_graph_mutation.py`
    `tests/test_validation.py tests/test_executor.py -q` now passes with
    `115 passed`, proving the first-slice mutation datamodel, fail-closed
    validation, prepared-input integration, and mutation diagnostics remain
    green together as one focused checkpoint

- [x] T3.2 [docs] Update the graph-mutation spec artifacts to record the first
      implementation checkpoint and validation evidence.
  - Spec: FR-1 through FR-5
  - Plan: Delivered Result
  - Files/components: `specs/internal-graph-mutation/spec.md`,
    `specs/internal-graph-mutation/plan.md`,
    `specs/internal-graph-mutation/tasks.md`
  - Depends on: T3.1
  - Validation:
    `poetry run pre-commit run --files`
    `specs/internal-graph-mutation/spec.md`
    `specs/internal-graph-mutation/plan.md`
    `specs/internal-graph-mutation/tasks.md`
  - Evidence: the artifact set now records the implemented slice honestly and
    stays aligned with repository reality, including the T3.1 focused mutation
    validation checkpoint and the resulting next-gate closure for this first
    implementation pass

## Ordering Notes

- Slice 1 must land before Slice 2 because the first live behavior depends on a
  validated internal mutation seam.
- Validation should fail closed before executor integration so mutation behavior
  cannot attach implicitly.
- The first implementation should remain input-transform-only until the
  repository proves that true node insertion, edge rewiring, or link-level
  operation insertion is needed.
- Context-management insertion on links between LLM steps, including ReAct
  loopbacks, is future graph-mutation work and should not be smuggled into the
  closed context-pruning checkpoint.
- Semantic ranking, embedding selection, and local-model transport follow-up
  should remain separate from this first mutation slice.

## Slice 4 — Pruning-context graph injection follow-up

- [x] T4.1 [tests] Add RED graph-mutation coverage for pruning-context
      injection around eligible `llm_step` interactions.
  - Spec: Completed Follow-up: Pruning-Context Injection; FR-1, FR-3, FR-4,
    FR-5, FR-6
  - Plan: Slice 4 — Pruning-context graph injection follow-up
  - Files/components: `tests/test_graph_mutation.py`,
    `src/dynamic_agent_runner/graph_mutation.py`
  - Cover immutable base workflow artifacts, eligible `llm_step` attachment,
    no-op behavior when no attachment policy exists, and mutation diagnostics
    naming the attachment point.
  - Depends on: T3.2
  - Validation:
    `poetry run pytest tests/test_graph_mutation.py -q -k pruning_context_injection`
  - Evidence: RED failed as expected before implementation because mutation
    notices did not name the `llm_step_interaction` attachment point.

- [x] T4.2 [tests] Add RED executor coverage proving injected
      pruning-context behavior is applied before the target `llm_step` model
      call.
  - Spec: Completed Follow-up: Pruning-Context Injection; FR-3, FR-4
  - Plan: Slice 4 — Pruning-context graph injection follow-up
  - Files/components: `tests/test_executor.py`,
    `src/dynamic_agent_runner/executor.py`
  - Cover supplied `WorkflowExecutionState.session_messages`, prepared input
    receiving pruned or compacted context, unchanged behavior with no
    graph-mutation policy, and redacted diagnostics.
  - Depends on: T4.1
  - Validation:
    `poetry run pytest tests/test_executor.py -q -k pruning_context_injection`
  - Evidence: RED failed as expected before implementation because
    `model_input_prepared` traces did not include redacted mutation attachment
    diagnostics.

- [x] T4.3 [tests] Add RED validation coverage for any new narrow attachment or
      link-level metadata needed by the follow-up.
  - Spec: FR-4, FR-5
  - Plan: Slice 4 — Pruning-context graph injection follow-up
  - Files/components: `tests/test_validation.py`,
    `src/dynamic_agent_runner/validation.py`
  - Cover only metadata proven necessary by T4.1/T4.2. If the existing
    `context_pipeline`, `context_sources`, and `context_contract` contract is
    sufficient, record this task as not needed rather than adding metadata.
  - Depends on: T4.1, T4.2
  - Validation:
    `poetry run pytest tests/test_validation.py -q -k context_pipeline`
  - Evidence: not needed for this slice. The existing `context_pipeline`,
    `context_sources`, and `context_contract` validation contract was sufficient;
    no new validation metadata was added.

- [x] T4.4 [implementation] Implement the smallest graph-mutation change that
      satisfies the RED pruning-context injection tests.
  - Spec: Completed Follow-up: Pruning-Context Injection
  - Plan: Slice 4 — Pruning-context graph injection follow-up
  - Files/components: `src/dynamic_agent_runner/graph_mutation.py`,
    `src/dynamic_agent_runner/executor.py`
  - Keep graph mutation responsible for deriving attachment/injection behavior
    only; delegate pruning, compaction, and prompt assembly to
    `context-management-prepare-stage`.
  - Depends on: T4.1, T4.2, T4.3 if needed
  - Validation:

    ```bash
    poetry run pytest tests/test_graph_mutation.py tests/test_executor.py \
      -q -k pruning_context_injection
    ```

  - Evidence: GREEN passed with `4 passed, 110 deselected` for
    `poetry run pytest tests/test_graph_mutation.py tests/test_executor.py -q`
    `-k pruning_context_injection`, and `114 passed` for
    `poetry run pytest tests/test_graph_mutation.py tests/test_executor.py -q`.

- [x] T4.5 [tests] Run the combined follow-up validation checkpoint and record
      evidence.
  - Spec: Completed Follow-up: Pruning-Context Injection
  - Plan: Validation Strategy
  - Files/components: `tests/test_graph_mutation.py`, `tests/test_executor.py`,
    `tests/test_validation.py`, `tests/test_agent_sessions.py`
  - Depends on: T4.4
  - Validation:

    ```bash
    poetry run pytest tests/test_graph_mutation.py tests/test_executor.py \
      tests/test_validation.py tests/test_agent_sessions.py -q
    ```

  - Completion evidence: `poetry run pytest tests/test_graph_mutation.py`
    `tests/test_executor.py tests/test_validation.py tests/test_agent_sessions.py`
    `-q` passed with `200 passed`.
