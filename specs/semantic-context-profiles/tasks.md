# Semantic Context Profiles Slice S1 Tasks

## Status

Prepared for implementation.

## Tasks

1. RED: Add tests for injected semantic selection.
   - Verification: a fake selector can select an older turn with low lexical
     overlap when `strategy: injected_semantic` and `profile: semantic` are
     configured.

2. RED: Add tests for missing-selector fallback diagnostics.
   - Verification: `semantic`/`injected_semantic` without a selector records
     missing-selector status and deterministic fallback metadata without making
     live embedding or model calls.

3. RED: Add tests that exact identifier protection survives semantic ranking.
   - Verification: exact issue keys, filenames, and quoted identifiers remain
     selectable even if the fake selector ranks another candidate higher.

4. RED: Add tests that retrieved RAG evidence is not passed to the selector.
   - Verification: fake selector candidates include older session turns only,
     and retrieved context stays in the retrieved-context lane.

5. GREEN: Add a small context selector contract.
   - Verification: package exports expose stable candidate/selection structures
     or type aliases, and `tests/test_import.py` passes.

6. GREEN: Thread the selector through execution collaborators.
   - Verification: direct `execute_workflow_async(...)` kwargs and
     `WorkflowExecutionContext` can carry the selector without conflicting with
     existing runtime kwargs.

7. GREEN: Implement injected semantic older-turn selection.
   - Verification: selected, omitted, and rejected metadata remain bounded and
     trace-safe; chronological reassembly remains the default.

8. GREEN: Preserve existing deterministic and exact behavior.
   - Verification: existing `tests/test_executor.py` prepare-model-input tests
     pass unchanged except for explicit metadata additions covered by S1 tests.

9. Optional docs update.
   - Verification: if public kwargs or exports are added, README and
     `docs/files/python-api.rst` document that selectors are caller-injected and
     fake-testable, with no built-in embeddings or vector stores.

10. Final validation.
    - Verification: run the focused and final commands in
      [`validation.md`](validation.md).

## Stop Conditions

- Stop and rescope if implementation requires embedding/vector dependencies.
- Stop and rescope if selector state needs durable memory ownership.
- Stop and rescope if RAG evidence must be mixed into session-turn candidates;
  that belongs to a separate RAG/context lane-borrowing slice.
