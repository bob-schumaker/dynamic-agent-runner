# Local Model Availability API Slice A1 Plan

Status: prepared for implementation

## Goal

Implement the first slice of `local-model-availability-api`: a public,
read-only availability check for one explicit local model reference. The slice
must report local source, cache root, resolved path, backend validation status,
and optional fakeable remote metadata without downloading, constructing
adapters, loading models, or scanning broad provider caches.

## Spec Trace

- Spec: `specs/local-model-availability-api/spec.md`
- Downstream request:
  `cline-tasks/local-model-availability-api-feature-request.md`
- Related local-model spec: `specs/llama-cpp-local-model/spec.md`
- Related MLX spec: `specs/mlx-local-model-adapter/spec.md`
- Related Hugging Face support spec: `specs/hugging-face-support-layer/spec.md`
- Related post-resolution advisory spec:
  `specs/llama-cpp-memory-fit-profile/spec.md`

## Slice Boundary

Slice A1 includes:

- package-owned value objects for explicit availability references and results
- a public `check_local_model_availability(...)` entry point
- no-download local precedence checks for explicit path, explicit cache root,
  and the default cache root
- backend-aware validation for llama.cpp GGUF, MLX GGUF, and converted MLX
  directories
- optional injected remote metadata lookup for known Hugging Face file or
  snapshot references
- package-root exports and Python API documentation
- deterministic fake tests

Slice A1 defers:

- `list_local_model_assets(...)`
- broad Hugging Face cache enumeration
- Ollama cache inventory beyond exact filename checks in the approved cache root
- real Hugging Face metadata integration beyond an injectable seam
- memory-fit profiling, model loading, adapter construction, and execution
- strict exception mode for ordinary missing or invalid user-selected assets

## Existing Implementation Context

- `src/dynamic_agent_runner/local_models.py` already owns
  `LocalModelPathConfig`, `HuggingFaceModelFileReference`,
  `HuggingFaceSnapshotReference`, `resolve_local_model_path(...)`, local cache
  precedence, default cache root, and llama.cpp local adapter configuration.
- `src/dynamic_agent_runner/mlx_models.py` already owns converted MLX and MLX
  GGUF path validation, but those helpers are private to the adapter module.
- `src/dynamic_agent_runner/hugging_face_support.py` owns lazy SDK import and
  shared Hub error translation for search and downloads. A1 should not add live
  metadata calls to unit tests.
- `tests/test_local_models.py` already has precedence tests and fake download
  callables.
- `tests/test_mlx_models.py` already has temporary converted MLX directory and
  GGUF fixtures.
- `tests/test_import.py` is the current package-root export smoke test.

## Public Contract Decisions

Add a small public contract in `local_models.py` unless implementation size
clearly justifies a new module.

Preferred value objects:

- `LocalModelAssetReference`
- `LocalModelAvailability`
- `LocalModelAvailabilityStatus`
- `LocalModelAvailabilitySource`
- optional internal/public metadata object only if the fake metadata seam needs
  more than primitive values

Use string enums where this repository already uses enum-backed public status
vocabularies. Values should include:

- `available`
- `missing`
- `would_download`
- `invalid`
- `unknown`

The reference should support:

- `provider`: `local_path` or `hugging_face`
- `repo_id`
- `filename`
- `revision`
- `explicit_path`
- `model_filename`
- `model_cache_root`
- `model_format`: `gguf`, `mlx`, or `auto`
- `backend`: `llama_cpp`, `mlx`, or `auto`

If both `filename` and `model_filename` are present, implementation should use
the concrete asset name that matches the existing runtime model-resolution
contract. If neither is available for a Hugging Face snapshot, return a
structured `unknown` or `invalid` result instead of scanning the repository.

## Availability Flow

`check_local_model_availability(reference, *, allow_network_metadata=False,
metadata_lookup=None)` should follow this order:

1. Normalize the reference into a local filename, optional explicit path,
   optional explicit cache root, and optional Hugging Face identity.
2. If an explicit path is present:
   - return `available` with source `explicit_path` when it exists and validates
   - return `missing` or `invalid` without fallback unless the reference also
     explicitly identifies cache lookup behavior
3. Check explicit cache root plus model filename.
4. Check the default local-model cache root plus model filename.
5. If local checks found a candidate, validate it for the requested backend and
   format before reporting `available`.
6. If local checks miss and no remote reference exists, return `missing`.
7. If local checks miss and a remote reference exists:
   - with `allow_network_metadata=False`, return `missing` or `unknown` without
     invoking metadata lookup
   - with `allow_network_metadata=True`, call the injected metadata lookup and
     return `would_download`, `invalid`, or `unknown` according to its result

The implementation must never call the existing Hub download helpers from this
availability path.

## Backend Validation Approach

Keep validation small and shared:

- Move or duplicate only the minimum MLX path validation logic needed by A1.
- Prefer a local helper in `local_models.py` only if it can serve both A1 and
  MLX without creating a circular dependency.
- Do not import MLX or llama.cpp.
- For GGUF, validate by file existence, file-ness, and `.gguf` suffix only.
- For converted MLX, validate the same structural files currently expected by
  `mlx_models.py`: `config.json`, `tokenizer.model`, and `weights.npz` or
  `weights.*.npz`.
- Return structured invalid results for ordinary user-selected invalid assets.

If sharing validation from `mlx_models.py` would require an awkward dependency
direction, leave the adapter helpers private and add package-owned validation
helpers in `local_models.py`; a later cleanup can route MLX through them.

## Remote Metadata Seam

Keep remote metadata injectable in A1. A callable can accept the normalized
reference and return a small package-owned metadata result or primitive mapping
with:

- `exists`
- `size_bytes`
- `message`
- `warnings`

Do not add real `huggingface_hub` metadata integration until a later slice unless
the implementation can do so without live tests, broad API growth, or cache
layout assumptions.

## Compatibility

- Existing `resolve_local_model_path(...)` behavior remains unchanged.
- Existing llama.cpp and MLX adapter construction remains unchanged.
- Existing automatic download behavior during model execution remains unchanged.
- Public search through `search_hugging_face_models(...)` remains the remote
  catalog discovery path.
- Availability results are advisory preflight metadata; callers still control
  execution policy and download confirmation.

## Validation Strategy

Use test-first implementation.

Focused RED/GREEN commands:

```bash
poetry run pytest tests/test_local_models.py tests/test_mlx_models.py \
  tests/test_hugging_face_support.py tests/test_import.py -q
```

Focused docs/API command:

```bash
poetry run ruff check src tests
```

Targeted pre-commit before completing A1:

```bash
pre-commit run --files \
  src/dynamic_agent_runner/local_models.py \
  src/dynamic_agent_runner/mlx_models.py \
  src/dynamic_agent_runner/__init__.py \
  tests/test_local_models.py \
  tests/test_mlx_models.py \
  tests/test_import.py \
  docs/files/python-api.rst \
  docs/skills/dynamic-agent-runner/SKILL.md \
  specs/local-model-availability-api/spec.md \
  specs/local-model-availability-api/plan.md \
  specs/local-model-availability-api/tasks.md \
  specs/local-model-availability-api/validation.md \
  specs/README.md
```

## Risks and Tradeoffs

- Sharing MLX validation can create dependency-direction risk. Prefer a small
  shared helper over importing `mlx_models.py` from `local_models.py`.
- Remote metadata can easily grow into a Hub SDK wrapper. Keep A1 injected and
  fake-testable.
- `unknown` versus `missing` semantics are subtle when metadata lookup is
  disabled. Tests should lock the exact A1 behavior.
- Broad inventory is tempting but not needed for the downstream blocker; keep it
  deferred.
