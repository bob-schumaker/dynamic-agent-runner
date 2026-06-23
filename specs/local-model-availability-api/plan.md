# Local Model Availability API Implementation Plan

Status: implemented through Slice A4

## Goal

Implement `local-model-availability-api` through small read-only slices. Slices
A1-A3 delivered explicit-reference availability preflight. Slice A4 added narrow
cached inventory for package-used roots only: the DAR default local-model cache
root and current caller-provided roots passed to the inventory call.

## Spec Trace

- Spec: `specs/local-model-availability-api/spec.md`
- Downstream request:
  `cline-tasks/local-model-availability-api-feature-request.md`
- Related local-model spec: `specs/llama-cpp-local-model/spec.md`
- Related MLX spec: `specs/mlx-local-model-adapter/spec.md`
- Related Hugging Face support spec: `specs/hugging-face-support-layer/spec.md`
- Related post-resolution advisory spec:
  `specs/llama-cpp-memory-fit-profile/spec.md`

## Completed Slice Boundary

Slices A1-A4 include:

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
- package-owned cached inventory value objects
- a public `list_local_model_assets(...)` entry point
- scanning the default local-model cache root
- scanning current caller-provided roots passed to that inventory call
- deterministic de-duplication by resolved path
- filesystem-only classification of direct GGUF files and converted MLX
  directories
- bounded warnings for missing, non-directory, unreadable, unsupported, or
  invalid local cache entries

Slices A1-A4 defer:

- broad Hugging Face cache enumeration and snapshot cache introspection
- recursive provider-cache discovery outside the approved root boundary
- real Hugging Face metadata integration beyond an injectable seam
- persistent root registration, root cleanup, migration, deletion, or ownership
  tracking
- remote metadata lookup, model search, and download-aware enrichment during
  inventory
- memory-fit profiling, model loading, adapter construction, and execution
- downstream UI policy and project option storage

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
- `LocalModelInventoryItem`
- `LocalModelInventory`
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

Slice A4 uses a narrow API shape:

```python
inventory = list_local_model_assets(
    model_cache_roots=(project_cache_root,),
    include_default_cache_root=True,
)
```

The inventory result should expose:

- `assets`: ordered tuple of package-owned item objects
- `warnings`: bounded root-level or scan-level diagnostics

Each item should expose at least:

- `path`
- `cache_root`
- `source`: default cache root or current caller-provided root
- `model_format`: `gguf`, `mlx`, or `unknown`
- `backend`: `llama_cpp`, `mlx`, or `auto`
- `status`: available or invalid if invalid entries are retained
- `message`
- `warnings`

Slice A4 skips unsupported or invalid direct children rather than returning
invalid inventory entries. It must not silently present invalid files as
available.

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

## Inventory Flow

`list_local_model_assets(*, model_cache_roots=(),
include_default_cache_root=True)` should follow this order:

1. Build the scan-root list from the default cache root, when enabled, followed
   by current caller-provided roots.
2. Normalize and de-duplicate roots by resolved path without requiring missing
   roots to exist.
3. For each existing directory root, inspect direct children only, except for
   the minimum directory check needed to recognize converted MLX model
   directories.
4. Classify supported direct `.gguf` files as GGUF assets.
5. Classify directories that match converted MLX structure as MLX assets.
6. For unsupported or invalid direct children, either skip with bounded warnings
   or return invalid inventory items according to the selected public contract.
7. De-duplicate discovered assets by resolved path, keeping the earlier root's
   source.
8. Return a structured inventory object even when no roots exist or no assets
   are found.

The inventory implementation must never call Hub metadata, Hub downloads,
adapter factories, model loading, generation, conversion, deletion, or
memory-fit profiling.

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

## Inventory Classification Approach

Keep inventory classification intentionally shallower than runtime resolution:

- direct `.gguf` files are candidate GGUF assets
- directories with converted MLX structure are candidate MLX assets
- hidden files and directories are skipped
- unsupported direct files are skipped with bounded warnings only if needed
- nested Hugging Face or Ollama provider internals are not recursively scanned
- caller-provided roots are used for the current call only and are not stored

## Compatibility

- Existing `resolve_local_model_path(...)` behavior remains unchanged.
- Existing llama.cpp and MLX adapter construction remains unchanged.
- Existing automatic download behavior during model execution remains unchanged.
- Public search through `search_hugging_face_models(...)` remains the remote
  catalog discovery path.
- Availability results are advisory preflight metadata; callers still control
  execution policy and download confirmation.
- Inventory results are local cache snapshots for current roots only; callers
  own any UI refresh cadence or project storage.

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

Targeted pre-commit used for A1:

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

Focused Slice A4 RED/GREEN commands:

```bash
poetry run pytest tests/test_local_models.py tests/test_import.py -q
poetry run ruff check src tests
```

Targeted pre-commit used for A4:

```bash
pre-commit run --files \
  src/dynamic_agent_runner/local_models.py \
  src/dynamic_agent_runner/__init__.py \
  tests/test_local_models.py \
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
- Broad inventory remains deferred and must stay restricted to
  DAR-owned/default download cache locations and current caller-provided roots
  unless a future spec revision changes that boundary.
- Current caller-provided roots can sound like ownership. The implementation
  must treat them as one-call scan inputs only.
- Recursive scanning can accidentally turn inventory into provider cache
  introspection. Slice A4 is direct-child only unless a supported converted MLX
  directory is being classified.
