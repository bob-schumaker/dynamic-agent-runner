# MLX Local-Model Tool-Use Implementation Plan

Status: M6.1 delivered; M6.2 is implementation-ready and next

## Goal

Extend only the in-process MLX adapter with an opt-in codec/backend seam that
renders a model-specific tool template and emits strict DAR `ModelToolCall`
values. Reuse the executor's existing tool loop; do not create another one.

## Approach

1. Add a small typed codec/candidate contract in `mlx_models.py` and a
   factory-injected `tool_codec` path. The backend and codec explicitly advertise
   compatibility; the stock `_MLXLMBackend` remains unsupported.
2. Replace the unconditional tool rejection with capability-aware rejection.
   Text-only and structured-output behavior otherwise remains unchanged.
3. Route tool-aware generation through the codec renderer and normalize only its
   typed candidate into `ModelResponse`/`ModelToolCall` under fixed bounds.
4. Preserve the current async wrapper over the sync implementation.
5. Prove the existing executor appends the ordinary transcript and routes one
   normalized MLX tool call through its existing coordinator.

## Affected Surfaces

- `src/dynamic_agent_runner/mlx_models.py`
- `tests/test_mlx_models.py`
- `tests/test_executor.py`
- `README.md` and `docs/files/python-api.rst` only after implementation is green

No change is planned for `executor.py`, tool registries, approval code, model
manifest schema, endpoint helpers, or package dependencies unless the M6.2
upstream API inspection proves an optional dependency declaration is necessary.

## TDD and Validation

M6.2 begins with focused RED tests, then makes them GREEN before any broader
regression run. It must run:

```bash
poetry run pytest tests/test_mlx_models.py tests/test_executor.py -q
poetry run pytest tests/test_import.py tests/test_local_models.py \
  tests/test_mlx_models.py tests/test_executor.py -q
poetry run ruff check src tests
pre-commit run --files <changed files>
```

The optional pinned-Qwen manual competency run is outside pytest and happens
only after deterministic tests pass. It records artifact revision, `mlx-lm`
version, codec version, generation settings, and outcome without becoming a
claim of CI parity.

## Risks and Gates

- A tokenizer's native chat template may not support the selected codec. Inspect
  it before implementation; do not invent compatibility.
- T6.2.1 found no installed or pinned `mlx-lm` source. Do not add a source pin
  without explicit provenance approval; a future default-codec task is gated on
  that decision, while the injected-codec seam remains independently executable.
- Model output is untrusted. Bounds and duplicate-safe parsing happen before
  `ModelToolCall` emission.
- This slice is serial and one-call-only. Parallel tool calls are a separate
  future decision.
- Capability metadata changes only when the concrete configured pair passes the
  fake contract tests; the default backend remains false.
