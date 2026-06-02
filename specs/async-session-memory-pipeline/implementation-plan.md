# Async Session Memory Pipeline Implementation Plan

## Goal

Describe the smallest coherent implementation slice for OA8 so the runner can
preserve validated `runtime.execution_policy.async_session` metadata without
adding runner-owned session storage, automatic replay, or broader memory
behavior.

## Scope Boundary

This plan is for the **first implementation pass only**.

In scope:

- preserve the `async_session` mapping in loaded runtime metadata
- validate the mapping fail-closed
- surface the metadata through compiled/prepared workflow structures where other
  execution-policy seams are already preserved
- add tests for valid and malformed policy shapes

Out of scope:

- durable session storage
- transcript replay
- context pruning execution
- summary generation
- API changes that add first-class session objects
- host-managed continuity helpers for `power-marimo`

## Proposed Artifact Shape

Expected manifest block:

```yaml
runtime:
  execution_policy:
    async_session:
      mode: metadata_only | reuse_existing | create_or_resume
      persist: none | in_memory | external_checkpoint
      history: none | last_turn | full | summary
      session_id_state_key: session.id
      history_state_key: session.history
      summary_state_key: session.summary
```

## Implementation Files

### 1. `src/dynamic_agent_runner/models.py`

Add or extend typed model support so the runtime manifest preserves the raw
`runtime.execution_policy.async_session` metadata in the same style as the other
deferred execution-policy seams.

Expected work:

- add a typed model or dataclass for `AsyncSessionPolicy`, or preserve a raw
  validated mapping if that matches the existing deferred-policy pattern better
- wire the field into `RuntimeManifest`
- ensure compiled/prepared workflow structures keep the metadata accessible if
  other execution-policy seams are already copied forward there

### 2. `src/dynamic_agent_runner/validation.py`

Implement fail-closed validation for the new async-session policy.

Expected work:

- validate that `runtime.execution_policy.async_session` is a mapping
- validate required enum fields:
  - `mode`
  - `persist`
  - `history`
- validate non-empty string rules for:
  - `session_id_state_key`
  - `history_state_key`
  - `summary_state_key`
- enforce coupling rules:
  - `persist != none` requires `session_id_state_key`
  - `persist == none` forbids `session_id_state_key`
  - `history == none` forbids `history_state_key` and `summary_state_key`
  - `history == summary` requires `summary_state_key`
  - `history != summary` forbids `summary_state_key`
- fail closed for unsupported enum values and stray incompatible fields

### 3. `src/dynamic_agent_runner/executor.py`

No live behavior changes are expected in the first pass.

Possible minimal work only if needed for consistency:

- ensure prepared execution-plan metadata carries validated async-session policy
  forward in the same style as OA5/OA7/OA10 metadata-only seams

### 4. `tests/test_validation.py`

Add validation coverage for:

- valid metadata-only policy
- valid persisted summary policy
- invalid enum values
- missing required `session_id_state_key` when `persist != none`
- stray `session_id_state_key` when `persist == none`
- stray history-related keys when `history == none`
- missing `summary_state_key` when `history == summary`
- stray `summary_state_key` when `history != summary`

### 5. `tests/test_artifacts.py` and/or `tests/test_executor.py`

Add narrow preservation tests showing that:

- loaded workflow artifacts preserve validated async-session metadata
- compiled/prepared workflow structures keep the metadata available where
  expected
- current execution behavior remains unchanged

## Suggested Task Breakdown

1. Add or finalize the `async_session` policy shape in `RuntimeManifest` models.
2. Implement fail-closed validation rules in `validation.py`.
3. Preserve the metadata through compile/preparation surfaces as needed.
4. Add validation tests for valid and invalid policy shapes.
5. Add preservation tests proving there is no new runtime behavior.
6. Re-run targeted validation for models, validation, artifacts, and executor.

## Suggested Validation Commands

Primary targeted checks:

```bash
poetry run pytest \
  tests/test_validation.py \
  tests/test_artifacts.py \
  tests/test_executor.py -q
```

If model-specific fixtures are touched, optionally widen to:

```bash
poetry run pytest \
  tests/test_validation.py \
  tests/test_artifacts.py \
  tests/test_executor.py \
  tests/test_power_marimo_fixture.py -q
```

## Expected Deliverable

After the first implementation pass, the repository should support a validated,
portable, metadata-only `runtime.execution_policy.async_session` seam that is
usable by future host integrations and later runtime features, while leaving the
current execution model unchanged.
