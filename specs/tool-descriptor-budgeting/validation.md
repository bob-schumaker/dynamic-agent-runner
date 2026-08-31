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

## T2.2 Scorer-Comparison Validation

- `nltk` is declared only in the Poetry `test` group; production dependencies
  and `src/dynamic_agent_runner/` remain NLTK-free.
- `tests/tool_descriptor_benchmark.py` compares stable, fixture-local rankings
  from the stdlib deterministic scorer and an NLTK Porter-stemming scorer.
- The NLTK scorer uses `wordpunct_tokenize` and `PorterStemmer`, with no corpus
  download or network path.

```bash
poetry run pytest tests/test_tool_descriptor_benchmark_comparison.py -q
# 4 passed

poetry run ruff check tests/tool_descriptor_benchmark.py \
  tests/test_tool_descriptor_benchmark_comparison.py
# All checks passed
```

## T2.3 Measurement Evidence

The fixed-corpus measurement uses canonical OpenAI function descriptors with
`estimate_text_tokens(..., model="gpt-4o-mini")`, NLTK 3.10.3, and no tokenizer
fallback (`o200k_base`). Timings are one local observation over 20 warmed
full-corpus iterations, not a performance gate.

| Metric | Deterministic | NLTK lexical |
| --- | ---: | ---: |
| Required-tool recall | 4 / 6 | 4 / 6 |
| False omissions | 2 | 2 |
| Descriptor-token reduction | 45.90% | 45.90% |
| Median full-corpus scorer time | 171,854 ns | 2,017,395 ns |

Both scorers miss `read_file` and `write_file` for
`inspect_then_modify_config`; this is reported evidence, not a corpus or scorer
tuning target. NLTK direct installed bytes were 6,529,742. Its resolved core
closure was `click`, `defusedxml`, `joblib`, `nltk`, `regex`, and `tqdm`
(9,464,109 installed bytes). Its incremental test-only surface was
`defusedxml`, `joblib`, and `nltk` (7,531,654 installed bytes). Setup requires
only `poetry install --with test`; there are no runtime NLTK imports and no
corpus downloads.

```bash
poetry run pytest tests/test_tool_descriptor_benchmark_measurements.py \
  tests/test_tool_descriptor_benchmark_comparison.py \
  tests/test_tool_descriptor_benchmark_fixtures.py -q
# 11 passed
```

## T2.4 Promotion Gate

No optional parser strategy was promoted. T2.3 found equal recall, false
omissions, and descriptor-token reduction for both scorers, while the NLTK path
was slower and added a measured test-only dependency surface. The runtime stays
with `deterministic_metadata`; no parser implementation, runtime import,
dependency, policy value, or fallback path was added. A future candidate must
define its expected quality improvement and acceptable cost before re-opening
this gate.

## Out-of-Scope Confirmation

Slice T1 does not:

- change source behavior
- add runtime dependencies
- add NLTK or downloaded corpora
- change direct `tool_use_step` execution semantics
- add live model, provider, parser, retrieval, or external service calls
- make descriptor budgeting default-on
