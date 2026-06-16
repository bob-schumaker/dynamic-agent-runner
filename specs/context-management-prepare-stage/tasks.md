# Context Management Prepare Stage Task List

Status: future backlog; no tasks started

## Prerequisites

- Spec: `specs/context-management-prepare-stage/spec.md`
- Plan: `specs/context-management-prepare-stage/plan.md`
- Current implementation anchors:
  - `src/dynamic_agent_runner/executor.py`
  - `src/dynamic_agent_runner/openai_client.py`
  - `src/dynamic_agent_runner/capabilities.py`
  - `tests/test_executor.py`

## Slice 1 — Policy and metadata contract

- [ ] T1.1 [tests] Add RED validation coverage for
      `runtime.execution_policy.prepare_model_input.context_compaction.auto`.
  - Spec: FR7, FR10
  - Files/components: `tests/test_validation.py`,
    `src/dynamic_agent_runner/validation.py`
  - Cover invalid threshold types, negative thresholds, unknown scopes,
    unsupported implementation modes, and reset-vs-compaction ambiguity.
  - Validation: `poetry run pytest tests/test_validation.py -q`

- [ ] T1.2 [tests] Add RED executor coverage for threshold derivation and
      clamping from model context-window metadata.
  - Spec: FR7
  - Files/components: `tests/test_executor.py`,
    `src/dynamic_agent_runner/executor.py`
  - Cover default 90% threshold, configured threshold clamping, missing
    context-window metadata, and strict/unavailable behavior.
  - Validation: `poetry run pytest tests/test_executor.py -q -k auto_compact`

- [ ] T1.3 [implementation] Add normalized automatic compaction policy parsing
      and prepared-input metadata fields.
  - Spec: FR6, FR7, FR10
  - Files/components: `src/dynamic_agent_runner/executor.py`,
    `src/dynamic_agent_runner/models.py`
  - Include threshold, scope, phase, trigger, reason, implementation,
    window-id, token-baseline, and reset-vs-compaction diagnostics.
  - Validation:
    `poetry run pytest tests/test_executor.py tests/test_validation.py -q`

## Slice 2 — Pre-turn remote compaction seam

- [ ] T2.1 [tests] Add RED pre-turn remote compaction coverage using an injected
      fake compactor.
  - Spec: FR8, FR9, FR10
  - Files/components: `tests/test_executor.py`,
    `src/dynamic_agent_runner/executor.py`
  - Cover over-threshold pre-turn compaction before adapter invocation,
    replacement-history installation, token recounting, and trace metadata.
  - Validation:
    `poetry run pytest tests/test_executor.py -q -k pre_turn_compaction`

- [ ] T2.2 [implementation] Add a provider/injected remote compaction boundary.
  - Spec: FR9
  - Files/components: `src/dynamic_agent_runner/openai_client.py`,
    `src/dynamic_agent_runner/executor.py`
  - Keep `/responses/compact` as an optional provider capability; do not call it
    from unit tests.
  - Validation:
    `poetry run pytest tests/test_openai_client.py tests/test_executor.py -q`

- [ ] T2.3 [implementation] Emit pre-turn compaction traces and capability
      status.
  - Spec: FR6, FR9
  - Files/components: `src/dynamic_agent_runner/tracing.py`,
    `src/dynamic_agent_runner/capabilities.py`,
    `tests/test_tracing.py`
  - Include trigger, reason, phase, implementation, status, token counts, and
    provider capability status without sensitive transcript content.
  - Validation:
    `poetry run pytest tests/test_tracing.py tests/test_executor.py -q`

## Slice 3 — Local summarization fallback

- [ ] T3.1 [tests] Add RED local summarization fallback coverage with a fake
      model adapter.
  - Spec: FR3, FR9
  - Files/components: `tests/test_executor.py`
  - Cover deterministic summary prompt, retained-message limit, summary
    placement, no-summary when nothing was pruned, and failure taxonomy.
  - Validation: `poetry run pytest tests/test_executor.py -q -k local_compaction`

- [ ] T3.2 [implementation] Add explicit local summarization fallback.
  - Spec: FR3, FR9
  - Files/components: `src/dynamic_agent_runner/executor.py`
  - Require explicit policy opt-in; no hidden live model call.
  - Validation: `poetry run pytest tests/test_executor.py -q`

## Slice 4 — Mid-turn iterative-loop compaction

- [ ] T4.1 [tests] Add RED iterative-loop coverage for mid-turn compaction
      unavailability.
  - Spec: FR8
  - Files/components: `tests/test_executor.py`
  - Prove the runtime fails or stops explicitly when more model work is needed
    after threshold exhaustion and mid-turn compaction is not enabled.
  - Validation: `poetry run pytest tests/test_executor.py -q -k mid_turn_compaction`

- [ ] T4.2 [implementation] Add mid-turn compaction for eligible iterative
      loops.
  - Spec: FR8, FR10
  - Files/components: `src/dynamic_agent_runner/executor.py`
  - Preserve pending tool-call, approval, retry, and loop trace state.
  - Validation: `poetry run pytest tests/test_executor.py -q`

## Slice 5 — Explicit new-context-window reset

- [ ] T5.1 [tests] Add RED coverage for reset behavior distinct from
      summarizing compaction.
  - Spec: FR10
  - Files/components: `tests/test_executor.py`,
    `tests/test_capabilities.py`
  - Cover reset metadata, no summary generation, and reset not counted as
    compaction success.
  - Validation:
    `poetry run pytest tests/test_executor.py tests/test_capabilities.py -q`

- [ ] T5.2 [implementation] Add explicit reset/new-window policy or tool.
  - Spec: FR10
  - Files/components: `src/dynamic_agent_runner/executor.py`,
    `src/dynamic_agent_runner/registry.py`
  - Keep reset opt-in and separate from `context_compaction`.
  - Validation:
    `poetry run pytest tests/test_executor.py tests/test_registry.py -q`

## Final Validation

Before committing a future implementation slice:

- `poetry run pytest -q`
- `poetry check`
- `poetry run ruff check src tests`

Unit tests must not make live OpenAI, `/responses/compact`, Hugging Face,
Marimo, MCP, or local model calls.
