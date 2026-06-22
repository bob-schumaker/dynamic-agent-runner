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

Focused evidence:

- `poetry run pytest tests/test_executor.py -q -k "semantic or older_turn or retrieved_context"`
  passed with `7 passed, 113 deselected`.
- `poetry run pytest tests/test_import.py -q` passed with `1 passed`.
- Focused Ruff on touched source and tests passed.

## Final Checks

```bash
poetry run ruff check src tests
poetry run pytest -q
```

Final evidence:

- `poetry run ruff check src tests` passed.
- `poetry run pytest -q` passed with `558 passed`.

## Manual Review Checklist

- No embedding, vector-store, graph-store, retrieval, or network dependency is
  added.
- Selector inputs are structured and limited to older session turns.
- Selector outputs are bounded and referenced by `turn_id`.
- Missing selector fallback is visible in prepared-input metadata.
- Exact identifier protection survives injected selector scoring.
- Retrieved context remains in the retrieved-context lane.
- Existing deterministic overlap and exact/hybrid tests still pass.
