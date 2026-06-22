# Semantic Context Profiles Slice S1 Validation

## Validation Goals

S1 is complete when semantic older-turn selection can be driven by an injected
fake selector, missing-selector behavior is explicit in metadata, exact
identifier protection still works, and retrieved RAG evidence remains separated
from selector candidates.

## Focused Checks

```bash
poetry run pytest tests/test_executor.py -q -k "semantic or older_turn or retrieved_context"
poetry run pytest tests/test_import.py -q
```

## Final Checks

```bash
poetry run ruff check src tests
poetry run pytest -q
```

## Manual Review Checklist

- No embedding, vector-store, graph-store, retrieval, or network dependency is
  added.
- Selector inputs are structured and limited to older session turns.
- Selector outputs are bounded and referenced by `turn_id`.
- Missing selector fallback is visible in prepared-input metadata.
- Exact identifier protection survives injected selector scoring.
- Retrieved context remains in the retrieved-context lane.
- Existing deterministic overlap and exact/hybrid tests still pass.
