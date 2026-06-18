# Context Management Prepare Stage Task List

Status: implemented through Slice 10 pruning-context injection behavior

## Prerequisites

- Spec: `specs/context-management-prepare-stage/spec.md`
- Plan: `specs/context-management-prepare-stage/plan.md`
- Current implementation anchors:
  - `src/dynamic_agent_runner/executor.py`
  - `src/dynamic_agent_runner/openai_client.py`
  - `src/dynamic_agent_runner/capabilities.py`
  - `tests/test_executor.py`

## Slice 1 — Policy, turn model, and metadata contract

- [x] T1.1 [tests] Add RED validation coverage for
      `runtime.execution_policy.prepare_model_input.context_compaction.auto`.
  - Spec: FR7, FR10, FR12, FR14, FR16, FR17
  - Files/components: `tests/test_validation.py`,
    `src/dynamic_agent_runner/validation.py`
  - Cover invalid threshold types, negative thresholds, unknown scopes,
    unsupported implementation modes, invalid strategies, invalid manual/auto
    modes, invalid lane budgets, invalid selection modes, and
    reset-vs-compaction ambiguity. Cover invalid metric and lifecycle-stage
    declarations if policy exposes them. Cover supported and unsupported
    compression profiles.
  - Validation: `poetry run pytest tests/test_validation.py -q`

- [x] T1.2 [tests] Add RED executor coverage for turn-unit grouping.
  - Spec: FR2, FR11, FR16
  - Files/components: `tests/test_executor.py`,
    `src/dynamic_agent_runner/executor.py`
  - Cover user/assistant turns, tool-call/result pairs, multi-tool turns,
    retry/error records where represented, stable turn/segment ids, lane
    assignment, and fail-closed invalid structures.
  - Validation: `poetry run pytest tests/test_executor.py -q -k turn_grouping`

- [x] T1.3 [tests] Add RED executor coverage for threshold derivation and
      reserve-token trigger precedence.
  - Spec: FR7, FR12
  - Files/components: `tests/test_executor.py`,
    `src/dynamic_agent_runner/executor.py`
  - Cover default 90% threshold, configured threshold clamping, missing
    context-window metadata, reserve-token trigger precedence, and
    strict/unavailable behavior.
  - Validation: `poetry run pytest tests/test_executor.py -q -k auto_compact`

- [x] T1.4 [implementation] Add normalized compression policy parsing, turn
      grouping, and prepared-input metadata fields.
  - Spec: FR2, FR6, FR7, FR10, FR12, FR14, FR16, FR17
  - Files/components: `src/dynamic_agent_runner/executor.py`,
    `src/dynamic_agent_runner/models.py`
  - Include turn ids, lane ids, threshold, scope, phase, trigger, reason,
    implementation, strategy, mode, window-id, token-baseline, reserve-token,
    lifecycle-stage status, importance/relevance scores, caller-provided
    access history, metric names, effective compression profile, and
    reset-vs-compaction diagnostics.
  - Validation:
    `poetry run pytest tests/test_executor.py tests/test_validation.py -q`

## Slice 2 — Lane-based prompt assembly

- [x] T2.1 [tests] Add RED coverage for lane budget assembly.
  - Spec: FR4, FR5, FR14, FR16, FR17
  - Files/components: `tests/test_executor.py`,
    `src/dynamic_agent_runner/executor.py`
  - Cover pinned hierarchy, current turn, recent turns, rolling-summary slot,
    selected older-turn slot, file/tool lane, lane ordering, lane utilization,
    lane metadata, and profile-specific lane priority for `balanced`, `fast`,
    `exact`, `recency_weighted`, and `instruction_weighted`.
  - Validation:
    `poetry run pytest tests/test_executor.py -q -k context_lanes`

- [x] T2.2 [tests] Add RED coverage for lane budget enforcement.
  - Spec: FR6, FR14, FR16
  - Files/components: `tests/test_executor.py`
  - Cover per-lane token limits, no implicit cross-lane borrowing, trimmed and
    omitted counts, information density or redundancy metrics where
    implemented, and protected current-turn behavior.
  - Validation:
    `poetry run pytest tests/test_executor.py -q -k lane_budget`

- [x] T2.3 [implementation] Add lane-based prompt assembly.
  - Spec: FR4, FR5, FR6, FR14, FR16
  - Files/components: `src/dynamic_agent_runner/executor.py`
  - Assemble prepared input from explicit lanes with stable ordering and
    metadata, including lane utilization, before any summarization or provider
    compaction.
  - Validation: `poetry run pytest tests/test_executor.py -q`

## Slice 3 — Deterministic older-turn selection

- [x] T3.1 [tests] Add RED coverage for deterministic older-turn selection.
  - Spec: FR15, FR16
  - Files/components: `tests/test_executor.py`,
    `src/dynamic_agent_runner/executor.py`
  - Cover path overlap, symbol/name overlap, state-key overlap, tool-name
    overlap, error/decision markers, max selected turns, empty selection,
    selected/omitted reasons, and relevance scores.
  - Validation:
    `poetry run pytest tests/test_executor.py -q -k older_turn_selection`

- [x] T3.2 [tests] Add RED coverage for chronological reassembly.
  - Spec: FR15
  - Files/components: `tests/test_executor.py`
  - Cover ranked selections returned out of order and final selected-turn
    rendering in original chronological order.
  - Validation:
    `poetry run pytest tests/test_executor.py -q -k chronological_reassembly`

- [x] T3.3 [implementation] Add deterministic older-turn selector.
  - Spec: FR6, FR15, FR16, FR17
  - Files/components: `src/dynamic_agent_runner/executor.py`
  - Use deterministic overlap only, add an injected selector seam for future
    semantic selectors, make no built-in embedding/vector calls, and report
    selected/rejected/omitted metadata. Route `semantic` profile behavior
    through the injected selector seam only.
  - Validation: `poetry run pytest tests/test_executor.py -q`

## Slice 3A — RAG Retrieved-Context Lane

- [x] T3A.1 [tests] Add RED coverage for caller-provided retrieved evidence as
      a bounded context lane.
  - Spec: RAG/context-management integration boundary
  - Files/components: `tests/test_executor.py`,
    `src/dynamic_agent_runner/executor.py`
  - Cover evidence mappings with source id, chunk id, citation handle,
    required/optional lane hints, token estimates, scores, freshness metadata,
    and packing hints. Prove raw retrieved content is not emitted in trace
    metadata.
  - Validation:
    `poetry run pytest tests/test_executor.py -q -k retrieved_context_lane`

- [x] T3A.2 [implementation] Add retrieved-context lane packing and diagnostics.
  - Spec: RAG/context-management integration boundary
  - Files/components: `src/dynamic_agent_runner/executor.py`
  - Consume caller-provided evidence already placed in runtime state or prepared
    context by RAG/tool orchestration. Apply context-management lane budgets,
    required-vs-optional handling, ordering, trimming, compression hooks, and
    omission diagnostics. Do not run retrieval, embeddings, rerankers, or
    evaluators.
  - Validation:
    `poetry run pytest tests/test_executor.py -q -k retrieved_context_lane`

## Slice 4 — Deterministic fallback compaction

- [x] T4.1 [tests] Add RED executor coverage for deterministic fallback
      compaction.
  - Spec: FR11, FR12, FR14, FR16
  - Files/components: `tests/test_executor.py`,
    `src/dynamic_agent_runner/executor.py`
  - Cover no live model call, latest-turn protection, older-history reduction,
    token-count metadata, compression ratio metadata, and no-op behavior when
    already under target.
  - Validation:
    `poetry run pytest tests/test_executor.py -q -k basic_compaction`

- [x] T4.2 [tests] Add RED coverage for tool-call/result pair safety.
  - Spec: FR11
  - Files/components: `tests/test_executor.py`
  - Cover old pair removal, latest pair preservation, multi-tool turns, and
    fail-closed behavior when a valid pair cannot be preserved.
  - Validation:
    `poetry run pytest tests/test_executor.py -q -k compaction_tool_pairs`

- [x] T4.3 [implementation] Add deterministic fallback compaction.
  - Spec: FR11, FR12, FR14, FR16
  - Files/components: `src/dynamic_agent_runner/executor.py`
  - Trim oversized retained tool results/file blocks first, then selected older
    turns, then oldest recent turns beyond the protected suffix, and finally
    summary detail below required headings. Emit compression-ratio and
    coverage-completeness metadata where practical.
  - Validation: `poetry run pytest tests/test_executor.py -q`

## Slice 5 — Rolling summary compaction

- [x] T5.1 [tests] Add RED rolling summary coverage with a fake
      model adapter.
  - Spec: FR3, FR14, FR16
  - Files/components: `tests/test_executor.py`
  - Cover required structured headings, retained-turn limits, prior-summary
    folding, file/source provenance carry-forward, summary placement,
    no-summary when nothing was evicted, summary fidelity or
    information-retention proxy metadata, and failure taxonomy.
  - Validation: `poetry run pytest tests/test_executor.py -q -k local_compaction`

- [x] T5.2 [implementation] Add explicit rolling summary compaction.
  - Spec: FR3, FR9, FR14, FR16
  - Files/components: `src/dynamic_agent_runner/executor.py`
  - Require explicit policy opt-in; no hidden live model call. Emit summary
    fidelity or information-retention proxy metadata where practical.
  - Validation: `poetry run pytest tests/test_executor.py -q`

## Slice 6 — Pre-turn compaction seam

- [x] T6.1 [tests] Add RED pre-turn compaction coverage using an injected fake
      compactor.
  - Spec: FR8, FR9, FR10
  - Files/components: `tests/test_executor.py`,
    `src/dynamic_agent_runner/executor.py`
  - Cover over-threshold pre-turn compaction before adapter invocation,
    replacement-history installation, token recounting, and trace metadata.
  - Validation:
    `poetry run pytest tests/test_executor.py -q -k pre_turn_compaction`

- [x] T6.2 [implementation] Add a provider/injected compaction boundary.
  - Spec: FR9
  - Files/components: `src/dynamic_agent_runner/openai_client.py`,
    `src/dynamic_agent_runner/executor.py`
  - Keep provider compaction optional; do not call any live provider from unit
    tests.
  - Validation:
    `poetry run pytest tests/test_openai_client.py tests/test_executor.py -q`

- [x] T6.3 [implementation] Emit pre-turn compaction traces and capability
      status.
  - Spec: FR6, FR9, FR16
  - Files/components: `src/dynamic_agent_runner/tracing.py`,
    `src/dynamic_agent_runner/capabilities.py`,
    `tests/test_tracing.py`
  - Include trigger, reason, phase, implementation, status, token counts, and
    provider capability status without sensitive transcript content. Use stable
    lifecycle-stage names.
  - Validation:
    `poetry run pytest tests/test_tracing.py tests/test_executor.py -q`

## Slice 7 — Mid-turn iterative-loop compaction

- [x] T7.1 [tests] Add RED iterative-loop coverage for mid-turn compaction
      unavailability.
  - Spec: FR8
  - Files/components: `tests/test_executor.py`
  - Prove the runtime fails or stops explicitly when more model work is needed
    after threshold exhaustion and mid-turn compaction is not enabled.
  - Validation: `poetry run pytest tests/test_executor.py -q -k mid_turn_compaction`

- [x] T7.2 [implementation] Add mid-turn compaction for eligible iterative
      loops.
  - Spec: FR8, FR10
  - Files/components: `src/dynamic_agent_runner/executor.py`
  - Preserve pending tool-call, approval, retry, and loop trace state.
  - Validation: `poetry run pytest tests/test_executor.py -q`

## Slice 8 — Explicit new-context-window reset

- [x] T8.1 [tests] Add RED coverage for reset behavior distinct from
      summarizing compaction.
  - Spec: FR10
  - Files/components: `tests/test_executor.py`,
    `tests/test_capabilities.py`
  - Cover reset metadata, no summary generation, and reset not counted as
    compaction success.
  - Validation:
    `poetry run pytest tests/test_executor.py tests/test_capabilities.py -q`

- [x] T8.2 [implementation] Add explicit reset/new-window policy or tool.
  - Spec: FR10
  - Files/components: `src/dynamic_agent_runner/executor.py`,
    `src/dynamic_agent_runner/registry.py`
  - Keep reset opt-in and separate from `context_compaction`.
  - Validation:
    `poetry run pytest tests/test_executor.py tests/test_registry.py -q`

## Slice 9 — Context-overflow error classification

- [x] T9.1 [tests] Add RED provider-overflow classification coverage.
  - Spec: FR13
  - Files/components: `tests/test_openai_client.py`,
    `tests/test_executor.py`
  - Cover OpenAI/OpenRouter-style `context_length_exceeded`, Anthropic-style
    invalid request, and generic 400 token/context/window message patterns.
  - Validation:
    `poetry run pytest tests/test_openai_client.py tests/test_executor.py -q`

- [x] T9.2 [implementation] Add defensive overflow classification and optional
      one-retry compaction path.
  - Spec: FR13
  - Files/components: `src/dynamic_agent_runner/openai_client.py`,
    `src/dynamic_agent_runner/executor.py`
  - Keep retry opt-in, emit explicit diagnostics, and never retry after
    compaction if the second provider call fails.
  - Validation:
    `poetry run pytest tests/test_openai_client.py tests/test_executor.py -q`

## Final Validation

Completed implementation slices were validated with:

- `poetry run pytest -q`
- `poetry check`
- `poetry run ruff check src tests`

Unit tests must not make live OpenAI, `/responses/compact`, Hugging Face,
Marimo, MCP, embedding/vector retrieval, local summarizer, or local model
calls.

## Slice 10 — Pruning-context injection behavior

- [x] T10.1 [tests] Add RED executor coverage for pruning supplied session
      messages before an eligible `llm_step` model call.
  - Spec: Completed Follow-up: Pruning-Context Injection
  - Plan: Slice 10 — Pruning-context injection behavior
  - Files/components: `tests/test_executor.py`,
    `src/dynamic_agent_runner/executor.py`
  - Cover supplied `WorkflowExecutionState.session_messages`, turn-aware
    pruning, context budget enforcement, and prepared input visible to the
    target prompt before adapter invocation.
  - Depends on: internal graph mutation T4.1/T4.2, or an existing attachment
    fixture that can drive the prepare-stage behavior directly
  - Validation:
    `poetry run pytest tests/test_executor.py -q -k pruning_context_injection`
  - Evidence: RED failed as expected because `{prepared_context}` received raw
    session history before prepare-stage pruning.

- [x] T10.2 [tests] Add RED executor coverage for no-policy preservation and
      redacted diagnostics.
  - Spec: Completed Follow-up: Pruning-Context Injection
  - Plan: Slice 10 — Pruning-context injection behavior
  - Files/components: `tests/test_executor.py`
  - Cover unchanged prompt rendering when no pruning-context policy is enabled,
    included/pruned/compacted/omitted counts, stable ids where available, and no
    full transcript text in trace metadata.
  - Depends on: T10.1
  - Validation:
    `poetry run pytest tests/test_executor.py -q -k pruning_context_injection`
  - Evidence: RED failed as expected because mutation context diagnostics were
    missing from `model_input_prepared` trace payloads.

- [x] T10.3 [implementation] Implement the smallest prepare-stage behavior that
      satisfies the RED pruning-context injection tests.
  - Spec: Completed Follow-up: Pruning-Context Injection
  - Plan: Slice 10 — Pruning-context injection behavior
  - Files/components: `src/dynamic_agent_runner/executor.py`
  - Reuse existing turn grouping, lane budgets, deterministic older-turn
    selection, rolling summary, and injected compactor seams. Do not introduce a
    durable store, embedding selector, live model summarizer, or graph-mutation
    attachment mechanism here.
  - Depends on: T10.1, T10.2
  - Validation:
    `poetry run pytest tests/test_executor.py -q -k pruning_context_injection`
  - Evidence: GREEN passed with `3 passed, 105 deselected`; full executor
    validation passed with `108 passed`.

- [x] T10.4 [tests] Verify `AgentSession`-supplied messages can feed the
      prepare-stage behavior without changing session persistence semantics.
  - Spec: Completed Follow-up: Pruning-Context Injection
  - Plan: Slice 10 — Pruning-context injection behavior
  - Files/components: `tests/test_agent_sessions.py`,
    `tests/test_executor.py`, `src/dynamic_agent_runner/sessions.py`
  - Cover the existing `AgentSession` message flow into
    `WorkflowExecutionState.session_messages`; do not add durable store behavior
    or transcript replay.
  - Depends on: T10.3
  - Validation:

    ```bash
    poetry run pytest tests/test_agent_sessions.py tests/test_executor.py \
      -q -k pruning_context_injection
    ```

  - Evidence: focused session validation passed with `1 passed, 21 deselected`,
    proving `AgentSession` history can feed bounded pruning context while the
    store still retains the full in-memory session state.

- [x] T10.5 [tests] Run the combined context-management follow-up checkpoint and
      record evidence.
  - Spec: Completed Follow-up: Pruning-Context Injection
  - Plan: Validation Strategy
  - Files/components: `tests/test_executor.py`, `tests/test_agent_sessions.py`,
    `tests/test_graph_mutation.py`, `tests/test_validation.py`
  - Depends on: T10.4 and graph-mutation T4.5
  - Validation:

    ```bash
    poetry run pytest tests/test_executor.py tests/test_agent_sessions.py \
      tests/test_graph_mutation.py tests/test_validation.py -q
    ```

  - Completion evidence: `poetry run pytest tests/test_executor.py`
    `tests/test_agent_sessions.py tests/test_graph_mutation.py`
    `tests/test_validation.py -q` passed with `200 passed`.
