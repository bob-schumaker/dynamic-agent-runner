# MLX Local-Model Tool-Use Implementation Plan

Status: M6.1–M6.3 delivered; M6.4 owned-codec source delivery in progress

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

## M6.4 Owned Codec

T6.4.1 found that the selected `mlx_lm` parser accepts extracted JSON but not
the pinned Qwen3 template's delimiter-wrapped native response. DAR now owns one
strict parser and `create_qwen3_mlx_local_adapter()` in a separate source
module. The helper requires a caller-loaded model/tokenizer pair and the pinned
configured model identity; it supports only omitted `tool_choice` and leaves
generic MLX factories text-only. Manual model competency remains separate from
the fake-only source contract tests.

## Superseded M6.4 Approach — Built-in Qwen3 MLX Codec

1. Characterize the pinned Qwen3 artifact against the installed `mlx-lm`
   public APIs on an eligible Apple Silicon host. Record the tokenizer template
   call shape, tool-call result/parser shape, continuation representation, and
   exact generation controls before committing to a production parser. Do not
   infer syntax from a model card, raw completion text, or a different Qwen
   release.
   This is a binary compatibility spike: it creates a dated checked-in profile
   with a canonical Hub-relative snapshot locator, an ordered SHA-256 manifest,
   public symbols/signatures, parser input/result mapping, and supported
   `tool_choice` values. It captures only synthetic structural evidence and
   redacted digests, never host transcript or handler data. An unqualified
   result closes M6.4 text-only; it does not authorize an invented parser or
   subsequent implementation work.
2. Add test-local tokenizer/parser/backend doubles that express the discovered
   public API contract. Start with RED cases for initial rendering, assistant
   call plus tool-result continuation, valid one-call decoding, text decoding,
   and every incompatibility gate. These tests must not import `mlx_lm`, load a
   model, use Metal, or access the network.
3. Implement one private built-in Qwen3 codec and one private package-owned
   profile selector in `mlx_models.py`. Add `enable_builtin_codecs=False` to
   the existing sync and async generic factories. With opt-in enabled, select a
   codec only when the resolved artifact matches a qualified profile's exact
   default-Hub locator, manifest, template, parser, and supported `tool_choice`
   mapping; otherwise return the ordinary text-only adapter. Reuse
   `MLXToolCodec`, `_MLXLMBackend`, and existing bounded normalization. A
   caller-supplied codec or backend bypasses built-in selection; tool capability
   still requires the existing explicit compatible pair. Do not add public
   profile registration, broad Qwen-name matching,
   or a second registry. Serialize generation with one per-adapter lock.
4. Add adapter/executor integration tests proving the real built-in selection
   path enters the ordinary DAR tool validation and continuation flow; retain
   the injected-pair tests as the generic extension contract. Do not add a
   second loop, endpoint, registry branch, or approval behavior.
5. Run a separately initiated live local competency pass after deterministic
   tests are green. Use only bounded recording tools, fixed generation
   settings, and the exact selected artifact. Record attempts and outcomes;
   never make it a pytest, CI, release, or arbitrary-model guarantee.
6. Update the existing README/Python API wording: default MLX remains text-only;
   `enable_builtin_codecs=True` selects only qualified built-in profiles, with
   the pinned Qwen3 profile initially the sole candidate; caller codecs remain
   the path for every other MLX model.

## Superseded M6.4 Affected Surfaces

- `src/dynamic_agent_runner/mlx_models.py`
- `src/dynamic_agent_runner/__init__.py`
- `tests/test_mlx_models.py`
- `tests/test_executor.py`
- `README.md`
- `docs/files/python-api.rst`
- `specs/mlx-local-model-tool-use/{spec,plan,tasks}.md`
- `specs/mlx-local-model-tool-use/m6.4-compatibility-profile.md`
- `specs/mlx-local-model-tool-use/validation.md`

## Superseded M6.4 Validation

```bash
poetry run pytest -q tests/test_mlx_models.py tests/test_executor.py
poetry run pytest -q tests/test_import.py tests/test_local_models.py \
  tests/test_mlx_models.py tests/test_executor.py
poetry run pytest -q
poetry run ruff check src tests
poetry run ruff format --check src tests
pre-commit run --files <changed files>
poetry run make -C docs html
```

The live competency command is deliberately discovered and recorded in M6.4.1;
it may use a local cached artifact but must not download, contact an endpoint,
or invoke an external tool.
