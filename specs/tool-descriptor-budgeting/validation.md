# Tool Descriptor Budgeting Validation

## Metadata

- Feature slug: `tool-descriptor-budgeting`
- Status: Slice T1 implementation validation complete; T2.1 fixture corpus complete
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

## Completed Validation

Focused RED/GREEN node-id checks passed, 15 tests across:

- `tests/test_validation.py`
- `tests/test_registry.py`
- `tests/test_executor.py`

Affected test files passed, 228 tests:

```bash
poetry run pytest tests/test_validation.py tests/test_registry.py \
  tests/test_executor.py -q
```

Source/test pre-commit passed:

```bash
pre-commit run --files \
  src/dynamic_agent_runner/registry.py \
  src/dynamic_agent_runner/executor.py \
  src/dynamic_agent_runner/token_budget.py \
  src/dynamic_agent_runner/validation.py \
  tests/test_registry.py tests/test_validation.py tests/test_executor.py
```

- `graphify update .` — completed after source changes.
- `make -C docs source/runtime-policies.rst` — regenerated the authored runtime
  policy page.
- `poetry run pytest -q` — passed, 547 tests.
- `poetry run ruff check src tests` — passed.

Implementation commit:

- `fd1b54c feat(registry): add tool descriptor budgeting`

## T2.1 Fixture-Corpus Validation

- `tests/fixtures/tool-descriptor-budgeting/benchmark-v1.json` contains five
  fixed, local, self-contained evaluator cases.
- `tests/test_tool_descriptor_benchmark_fixtures.py` validates the versioned
  fixture shape, eligible-tool descriptors, required/optional membership,
  false-omission checks, distractors, and the planned case identities.
- The fixture test does not invoke `ToolSelector`, so it remains a scorer-neutral
  oracle for T2.2 and T2.3.

Focused RED/GREEN validation:

```bash
poetry run pytest tests/test_tool_descriptor_benchmark_fixtures.py -q
# RED: FileNotFoundError for the intentionally absent fixture
# GREEN: 1 passed

poetry run ruff check tests/test_tool_descriptor_benchmark_fixtures.py
# All checks passed
```

## Out-of-Scope Confirmation

Slice T1 does not:

- change source behavior
- add runtime dependencies
- add NLTK or downloaded corpora
- change direct `tool_use_step` execution semantics
- add live model, provider, parser, retrieval, or external service calls
- make descriptor budgeting default-on
