# Async Session Memory Pipeline Implementation Plan

## Goal

Describe the next coherent expansion slice for OA8 now that the runner already
preserves validated `runtime.execution_policy.async_session` metadata without
adding runner-owned session storage, automatic replay, or broader memory
behavior.

## Scope Boundary

This plan is for the **next expansion pass after the implemented metadata-only
baseline**.

Already implemented baseline:

- preserve the `async_session` mapping in loaded runtime metadata
- validate the mapping fail-closed
- surface the metadata through compiled/prepared workflow structures

In scope for the next expansion pass:

- reconcile the spec package with the implemented field names
- decide whether to keep `session_messages_state_key` as the durable baseline or
  expand toward richer split fields such as summary-backed continuity metadata
- add any newly approved metadata fields without changing live runtime behavior
- extend tests only for the approved metadata expansion

Out of scope:

- durable session storage
- transcript replay
- context pruning execution
- summary generation
- API changes that add first-class session objects
- host-managed continuity helpers for `power-marimo`

## Proposed Artifact Shape

Current implemented manifest block:

```yaml
runtime:
  execution_policy:
    async_session:
      mode: metadata_only | reuse_existing | create_or_resume
      persist: none | in_memory | external_checkpoint
      history: none | last_turn | full | summary
      session_id_state_key: session.id
      session_messages_state_key: session.messages
```

Future expansion candidates should build from this exact baseline rather than
replacing it informally in the docs.

## Implementation Files

### 1. `src/dynamic_agent_runner/models.py`

The typed model support already exists. Future work here should extend it only if
new approved metadata fields are added.

Expected work:

- preserve compatibility for the existing `AsyncSessionPolicy`
- extend `AsyncSessionPolicy` only if new approved metadata fields are added
- keep `RuntimeManifest` / `ExecutionPlan` propagation aligned with the existing
  metadata-only seam

### 2. `src/dynamic_agent_runner/validation.py`

The fail-closed validation path already exists. Future work here should extend
it only for newly approved metadata fields.

Expected work:

- keep the current mapping/enum validation intact
- keep non-empty string validation for:
  - `session_id_state_key`
  - `session_messages_state_key`
- keep current coupling rules intact
- extend validation only after the docs approve any new metadata fields

### 3. `src/dynamic_agent_runner/executor.py`

No live behavior changes are expected in the first pass.

Possible minimal work only if needed for consistency:

- ensure prepared execution-plan metadata carries validated async-session policy
  forward in the same style as OA5/OA7/OA10 metadata-only seams

### 4. `tests/test_validation.py`

The existing validation coverage already includes:

- valid metadata-only policy
- invalid enum values
- missing required `session_id_state_key` when `persist != none`
- stray session state keys when `persist == none`
- stray `session_messages_state_key` when `history == none`

Future validation coverage may add:

- any newly approved summary-backed or richer retention metadata fields

### 5. `tests/test_artifacts.py` and/or `tests/test_executor.py`

The existing artifact/executor coverage already shows that:

- loaded workflow artifacts preserve validated async-session metadata
- compiled/prepared workflow structures keep the metadata available where
  expected
- current execution behavior remains unchanged

## Suggested Task Breakdown

1. Align the OA8 feature-spec package with the implemented metadata-only seam.
2. Decide whether any additional metadata fields are truly needed.
3. Extend `AsyncSessionPolicy` only for approved new fields.
4. Extend validation only for those approved fields.
5. Extend artifact/executor preservation tests only where the metadata grows.
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

After the next expansion pass, the repository should keep the existing
validated, portable, metadata-only `runtime.execution_policy.async_session`
seam and, if approved, extend it in a way that remains compatible with future
host integrations while leaving the current execution model unchanged.
