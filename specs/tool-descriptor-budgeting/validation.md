# Tool Descriptor Budgeting Validation

## Metadata

- Feature slug: `tool-descriptor-budgeting`
- Status: candidate readiness validation; implementation not started
- Date: 2026-06-22

## Readiness Checks

- The spec has a narrow Slice T1 boundary.
- Slice T1 has no blocking `NEEDS CLARIFICATION` items.
- The feature is opt-in and preserves existing behavior by default.
- The selector starts only from registry-exposed `RegisteredTool` values.
- Required-tool failure behavior is explicit and happens before model dispatch.
- Unit-test strategy is fake-only and live-call-free.
- NLTK, embeddings, vector stores, retrieval indexes, and model-backed
  selection are explicitly deferred.
- Diagnostics are redacted by default and do not include raw prompt content or
  full descriptors.
- LiteLLM/provider work is not required for this slice.

## Validation To Run During Implementation

```bash
poetry run pytest tests/test_validation.py -q
poetry run pytest tests/test_registry.py -q
poetry run pytest tests/test_executor.py -q
poetry run pytest -q
poetry run ruff check src tests
```

Run targeted `pre-commit run --files ...` on the actual changed files before
committing implementation.

## Out-of-Scope Confirmation

The candidate preparation does not:

- change source behavior
- add runtime dependencies
- add NLTK or downloaded corpora
- change direct `tool_use_step` execution semantics
- add live model, provider, parser, retrieval, or external service calls
- make descriptor budgeting default-on
