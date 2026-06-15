# Hugging Face Model Search Implementation Plan

Status: implementation plan complete through Slice 3

## Goal

Plan the first public Hugging Face model-discovery surface for
`dynamic-agent-runner`, derived from the authoritative feature spec at
`specs/hugging-face-model-search/spec.md`.

The implementation must let callers search Hugging Face models through a
repository-owned API without exposing raw `huggingface_hub` objects as the
package contract, and without broadening into download, execution, or write-side
Hub management.

## Spec Trace

- Spec: `specs/hugging-face-model-search/spec.md`
- Related repo guardrails:
  - `specs/dynamic-agent-runner/spec.md`
  - `specs/llama-cpp-local-model/spec.md`
- Existing implementation context:
  - `src/dynamic_agent_runner/local_models.py`
  - `src/dynamic_agent_runner/errors.py`
  - `src/dynamic_agent_runner/__init__.py`
  - `docs/files/python-api.rst`

## Planning Decisions

- Public entry point: add a function-first API named
  `search_hugging_face_models(...)`.
- Module ownership: put discovery behavior in a new public helper module,
  `src/dynamic_agent_runner/hugging_face_models.py`, instead of extending
  `local_models.py`. `local_models.py` remains focused on local endpoint and
  asset-resolution helpers.
- Result contract: add a frozen repository-owned value object named
  `HuggingFaceModelSearchResult`.
- Filter contract: support an intentionally small first-slice filter set:
  `query`, `limit`, `task`, `tags`, `sort`, and `direction`.
- Error boundary: add `HuggingFaceModelSearchError` as a package-owned error
  type rooted in `DynamicAgentRunnerError`.
- SDK boundary: lazily import `huggingface_hub` inside the default search
  adapter so package import does not fail only because optional runtime context
  lacks a usable Hub SDK.
- Test strategy: use dependency injection or monkeypatching for the Hub search
  callable so tests never require live Hugging Face network access.

## Public Contract

The first public function should have this practical shape:

```python
def search_hugging_face_models(
    query: str | None = None,
    *,
    limit: int = 10,
    task: str | None = None,
    tags: Sequence[str] = (),
    sort: str | None = None,
    direction: str | None = None,
) -> tuple[HuggingFaceModelSearchResult, ...]:
    ...
```

The implementation may accept a private keyword-only adapter parameter for
tests, but that parameter must not be documented as public API.

`HuggingFaceModelSearchResult` should include only stable, useful fields:

- `repo_id: str`
- `display_name: str | None`
- `task: str | None`
- `tags: tuple[str, ...]`
- `likes: int | None`
- `downloads: int | None`
- `last_modified: str | None`

Field normalization should be tolerant of upstream SDK shape differences. A
missing upstream field should become `None` or an empty tuple, not a raw
attribute error.

## Delivery Strategy

### Slice 1 — Public contract and deterministic tests

Create RED tests that define the caller-visible behavior before implementation:

- package-root import for `search_hugging_face_models`
- repository-owned result objects
- minimal filter shaping
- deterministic fake search adapter
- package-owned error translation

This slice proves the feature boundary and avoids live network dependence.

### Slice 2 — Implementation and exports

Add the new module, value object, public function, error type, and package-root
exports.

The default adapter should translate the first-slice filters to
`huggingface_hub` model search using the installed SDK's public API, but callers
should receive only repository-owned result objects and errors.

### Slice 3 — Documentation and validation

Document the public API in the Python API docs and add validation evidence.

Documentation must make clear that discovery does not imply runtime
compatibility, download support, or local endpoint configuration.

## Validation Plan

- `poetry run pytest tests/test_hugging_face_models.py -q`
- `poetry run pytest tests/test_import.py tests/test_hugging_face_models.py -q`
- `poetry run pytest tests/test_local_models.py`
  `tests/test_hugging_face_models.py -q`
- `poetry run pytest tests/test_openai_client.py`
  `tests/test_hugging_face_models.py -q`

Live Hugging Face calls are intentionally excluded from the required validation
plan. Any optional live smoke test must be manual, documented separately, and
must not gate CI.

## Non-Implementation Notes

- Do not add workflow-manifest fields for model search in this feature.
- Do not use search results to automatically download or launch models.
- Do not expose `huggingface_hub` result objects as the stable package contract.
- Do not add authenticated Hub mutation operations.
