# Hugging Face Model Search Task List

Status: actionable task list; implementation not started

## Prerequisites

- Spec: `specs/hugging-face-model-search/spec.md`
- Plan: `specs/hugging-face-model-search/plan.md`
- Data model: `HuggingFaceModelSearchResult`
- Public entry point: `search_hugging_face_models(...)`

## Status

- State: Slice 1 RED contract tests are complete.
- Current execution gate: T2.1 is the next pending step.
- Scope rule: keep this feature limited to read-only public model discovery.
  Do not merge model download, endpoint startup, workflow schema, or write-side
  Hugging Face operations into these tasks.

## Slice 1 — Public Contract and Deterministic Tests

- [x] T1.1 [tests] Add RED tests for the public search entry point and result
      contract in `tests/test_hugging_face_models.py`.
  - Spec: FR-1, FR-2, FR-6
  - Plan: Public Contract; Slice 1
  - Files/components: `tests/test_hugging_face_models.py`,
    `src/dynamic_agent_runner/hugging_face_models.py`
  - Domain context: callers should import a repository-owned discovery API
    without touching `huggingface_hub` or private local-model helpers.
  - Depends on: none
  - Validation: `poetry run pytest tests/test_hugging_face_models.py -q`
  - Evidence: tests fail before `search_hugging_face_models(...)` and
    `HuggingFaceModelSearchResult` exist.
  - RED: `poetry run pytest tests/test_hugging_face_models.py -q` failed with
    `ModuleNotFoundError: No module named
    'dynamic_agent_runner.hugging_face_models'`.

- [x] T1.2 [tests] Add RED tests for limited filter shaping with a fake Hub
      search adapter.
  - Spec: FR-3, FR-6
  - Plan: Planning Decisions; Public Contract
  - Files/components: `tests/test_hugging_face_models.py`
  - Domain context: supported filters are `query`, `limit`, `task`, `tags`,
    `sort`, and `direction`; this API is not an arbitrary SDK passthrough.
  - Depends on: T1.1
  - Validation: `poetry run pytest tests/test_hugging_face_models.py -q`
  - Evidence: tests assert the exact repository-approved filter set sent to the
    fake adapter.
  - RED: covered by `test_search_hugging_face_models_shapes_limited_filter_set`;
    it fails before the public discovery module exists.

- [x] T1.3 [tests] Add RED tests for package-owned discovery error translation.
  - Spec: FR-4, FR-6
  - Plan: Planning Decisions; Validation Plan
  - Files/components: `tests/test_hugging_face_models.py`,
    `src/dynamic_agent_runner/errors.py`
  - Domain context: missing SDKs and upstream failures must surface as
    `HuggingFaceModelSearchError` with model-discovery context.
  - Depends on: T1.1
  - Validation: `poetry run pytest tests/test_hugging_face_models.py -q`
  - Evidence: tests fail before repository-owned error translation exists.
  - RED: covered by
    `test_search_hugging_face_models_translates_discovery_failures`; it fails
    before `HuggingFaceModelSearchError` is exported.

## Slice 2 — Implementation and Exports

- [ ] T2.1 [implementation] Add
      `src/dynamic_agent_runner/hugging_face_models.py` with the result value
      object, public search function, normalization helpers, and default Hub
      adapter.
  - Spec: FR-1, FR-2, FR-3, FR-6
  - Plan: Public Contract; Slice 2
  - Files/components: `src/dynamic_agent_runner/hugging_face_models.py`
  - Depends on: T1.1, T1.2
  - Validation: `poetry run pytest tests/test_hugging_face_models.py -q`
  - Evidence: contract and filter tests pass without live network calls.

- [ ] T2.2 [implementation] Add `HuggingFaceModelSearchError` to
      `src/dynamic_agent_runner/errors.py` and wire search failure translation.
  - Spec: FR-4
  - Plan: Planning Decisions; Slice 2
  - Files/components: `src/dynamic_agent_runner/errors.py`,
    `src/dynamic_agent_runner/hugging_face_models.py`
  - Depends on: T1.3, T2.1
  - Validation: `poetry run pytest tests/test_hugging_face_models.py -q`
  - Evidence: missing SDK and fake upstream failures surface as the package-owned
    search error.

- [ ] T2.3 [implementation] Export the public discovery surface from
      `src/dynamic_agent_runner/__init__.py`.
  - Spec: FR-1
  - Plan: Public Contract; Slice 2
  - Files/components: `src/dynamic_agent_runner/__init__.py`,
    `tests/test_import.py`, `tests/test_hugging_face_models.py`
  - Depends on: T2.1, T2.2
  - Validation: `poetry run pytest tests/test_import.py
    tests/test_hugging_face_models.py -q`
  - Evidence: callers can import `search_hugging_face_models`,
    `HuggingFaceModelSearchResult`, and `HuggingFaceModelSearchError` from the
    package root.

## Slice 3 — Documentation and Final Validation

- [ ] T3.1 [docs] Document the public discovery API and read-only boundary in
      the Python API docs.
  - Spec: FR-1, FR-5
  - Plan: Slice 3; Non-Implementation Notes
  - Files/components: `docs/files/python-api.rst`
  - Depends on: T2.3
  - Validation: `rg -n
    "search_hugging_face_models|HuggingFaceModelSearchResult|read-only"
    docs/files/python-api.rst`
  - Evidence: docs identify the canonical entry point and warn that discovery
    does not imply runtime compatibility or download support.

- [ ] T3.2 [validation] Run focused regression tests for discovery, imports,
      local-model helpers, and OpenAI provider seams.
  - Spec: FR-6
  - Plan: Validation Plan
  - Files/components: `tests/test_hugging_face_models.py`,
    `tests/test_import.py`, `tests/test_local_models.py`,
    `tests/test_openai_client.py`
  - Depends on: T3.1
  - Validation:
    `poetry run pytest tests/test_import.py tests/test_local_models.py
    tests/test_openai_client.py tests/test_hugging_face_models.py -q`
  - Evidence: focused regression suite passes without live Hugging Face network
    access.

- [ ] T3.3 [spec-maintenance] Record implementation evidence in this task list
      and update the specs index if the feature status changes.
  - Spec: Authoritative Boundary
  - Plan: Delivery Strategy
  - Files/components: `specs/hugging-face-model-search/tasks.md`,
    `specs/README.md`
  - Depends on: T3.2
  - Validation: `rg -n
    "Hugging Face model search|Public Hugging Face model discovery"
    specs/README.md specs/hugging-face-model-search/tasks.md`
  - Evidence: status and completion wording match the implemented state.
