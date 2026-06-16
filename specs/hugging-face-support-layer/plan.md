# Hugging Face Support Layer Implementation Plan

Status: implemented; Slices 1-3 complete

## Goal

Implement the internal support layer described in
`specs/hugging-face-support-layer/spec.md` so Hugging Face model discovery and
local-model asset downloads share lazy SDK import and read-only call mechanics
while preserving their separate public error contracts.

## Spec Trace

- Spec: `specs/hugging-face-support-layer/spec.md`
- Related model-search spec: `specs/hugging-face-model-search/spec.md`
- Related local-model spec: `specs/llama-cpp-local-model/spec.md`
- Dependent MLX tasks: `specs/mlx-local-model-adapter/tasks.md` T3.5 and T3.6

## Existing Implementation Context

- `hugging_face_models.py` imports `HfApi` inside `_default_hub_search(...)` and
  translates failures to `HuggingFaceModelSearchError`.
- `local_models.py` imports `hf_hub_download` and `snapshot_download` inside
  `_load_huggingface_download_helpers(...)` and translates failures to
  `LocalModelResolutionError`.
- Local-model resolution already supports injected fake download callables, and
  tests must preserve that injection seam.
- The support layer must stay internal and must not be exported from
  `dynamic_agent_runner.__init__`.

## Planning Decisions

- Add `src/dynamic_agent_runner/hugging_face_support.py`.
- Add an internal `HuggingFaceSupportError` for support-layer import/call
  failures; domain modules translate that error to their existing public errors.
- Provide simple read-only helpers:
  - `load_hugging_face_hub()`
  - `list_hub_models(...)`
  - `download_hub_file(...)`
  - `download_hub_snapshot(...)`
- Keep cache, offline policy, search result normalization, and local-model
  resolution semantics in the existing domain modules.
- Keep all tests deterministic with fake Hub modules/callables.

## Implementation Shape

### Slice 1 — Internal Support Module and Search Routing

Create the support module and route `hugging_face_models._default_hub_search`
through `list_hub_models(...)`. Add tests for:

- import failure translated by the support layer
- SDK call failure translated by the support layer
- search domain still translating support errors to
  `HuggingFaceModelSearchError`
- package root not exporting support-layer internals

### Slice 2 — Local Download Routing

Route `local_models._load_huggingface_download_helpers()` through
`download_hub_file(...)` and `download_hub_snapshot(...)`. Add tests for:

- support-layer file download wrapper using injected fake Hub callables
- support-layer snapshot download wrapper using injected fake Hub callables
- local-model domain preserving `LocalModelResolutionError`
- existing injected local-model download callables still bypass default Hub
  helpers

### Slice 3 — Spec Maintenance and Regression

Update spec/tasks evidence and run focused regression:

```bash
poetry run pytest tests/test_hugging_face_support.py \
  tests/test_hugging_face_models.py tests/test_local_models.py -q
```

Then run targeted pre-commit for changed files.

## Non-Implementation Notes

- Do not change public model search return types.
- Do not make model search feed local-model downloads.
- Do not change local cache precedence or offline policy behavior.
- Do not add public package-root exports for the support layer.
- Do not add live network tests.
