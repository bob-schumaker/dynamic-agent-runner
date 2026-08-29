# MLX Local-Model Tool-Use Implementation Plan

Status: M6.1 and M6.2 delivered; M6.3 native-safetensors recognition is next

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
manifest schema, or endpoint helpers. The selected optional `mlx-lm`
dependency, Qwen3 Instruct target, and pinned parity artifact are recorded in
[`implementation-decision.md`](implementation-decision.md).

## M6.3 Approach

1. Move MLX directory structural admission behind one non-public helper in
   `local_models.py`. It distinguishes the unchanged converted-NPZ branch from
   the exact native safetensors contract in `spec.md`; `mlx_models.py` consumes
   the helper and translates an invalid result through its existing
   `LocalModelResolutionError` boundary.
2. For native files, determine the containment root as the enclosing Hub
   repository for a recognized `models--*/snapshots/<revision>` path and as the
   model directory otherwise. Permit a symlink only when its resolved regular
   file remains inside that root.
3. Use the same helper for availability and both caller-root/default-Hub
   inventory. Keep inventory output at one MLX directory/snapshot item, while
   invalid native candidates are skipped. Do not scan additional roots or add
   model management.
4. Start with focused RED fixtures in `tests/test_mlx_models.py` and
   `tests/test_local_models.py`: direct native, indexed native, unchanged NPZ,
   valid contained Hub blob links, each invalid native category, and the
   resolution/availability/inventory taxonomy. Make the tests GREEN with the
   shared helper, then run the existing focused regression set.

## M6.3 Affected Surfaces

- `src/dynamic_agent_runner/local_models.py`
- `src/dynamic_agent_runner/mlx_models.py`
- `tests/test_local_models.py`
- `tests/test_mlx_models.py`
- `specs/mlx-local-model-tool-use/{spec,plan,tasks}.md`

The slice does not change loader selection, `_MLXLMBackend`, codec parsing,
executor dispatch, policy/approval, or documentation outside its task evidence.

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

M6.3 uses the same RED/GREEN discipline and runs:

```bash
poetry run pytest tests/test_mlx_models.py tests/test_local_models.py -q
poetry run pytest tests/test_import.py tests/test_local_models.py \
  tests/test_mlx_models.py -q
poetry run ruff check src tests
pre-commit run --files <changed files>
```

## Risks and Gates

- A tokenizer's native chat template may not support the selected codec. Inspect
  it before implementation; do not invent compatibility.
- The accepted source and artifact decision is recorded in
  [`implementation-decision.md`](implementation-decision.md). Inspect the
  selected Qwen3 tokenizer/template and parser interfaces before activating the
  built-in codec; preserve a text-only capability state if they do not meet the
  contract.
- Model output is untrusted. Bounds and duplicate-safe parsing happen before
  `ModelToolCall` emission.
- This slice is serial and one-call-only. Parallel tool calls are a separate
  future decision.
- Native structural admission must never be represented as `mlx_lm` runtime
  compatibility. A real load/generation remains separately human-authorized.
- Capability metadata changes only when the concrete configured pair passes the
  fake contract tests; the default backend remains false.
