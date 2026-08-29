# MLX Local-Model Tool-Use Tasks

Status: M6.1 delivered and validated; M6.2 is implementation-ready

## M6.1 — Contract and Delivery Readiness

- [x] Define the codec/backend boundary, strict normalized emission, bounds,
  continuation semantics, capability truthfulness, and non-goals in `spec.md`.
- [x] Record an implementation plan that keeps executor dispatch, approval, and
  lifecycle ownership unchanged.
- [x] Review the contract with Council and Ponytail; require a versioned codec,
  an explicitly compatible backend, duplicate-safe bounded parsing, one-call
  scope, and fake-only validation.
  - Council finding disposition: accepted; the codec is the one necessary
    model-family translation seam, while DAR retains every tool-execution
    concern.
  - Ponytail finding disposition: none. The scoped codec replaces neither an
    endpoint nor an executor path; no additional abstraction is warranted.
- [x] Validate the downstream M6.2 handoff: concrete target, implementation
  procedure, tests-first validation, and acceptance criteria are present.
- [x] Deliver the planning artifacts, re-read the governing links, and run
  `pre-commit run --files` on the changed Markdown artifacts.
  - Validation: passed (rumdl check and format); no runtime code changed.

## M6.2 — Tool-Capable MLX Adapter

- [ ] T6.2.1 [discovery/tests] Inspect the installed/pinned `mlx-lm` tokenizer
  and chat-template API. Add RED fake codec tests for initial schema rendering,
  text response, one call, and canonical response-scoped IDs.
  - Spec: Codec and backend boundary; FR-1, FR-2
  - Files: `src/dynamic_agent_runner/mlx_models.py`, `tests/test_mlx_models.py`
  - Gate: no default codec claim without observed compatible upstream API.

- [ ] T6.2.2 [tests] Add RED parser-boundary tests for malformed JSON,
  duplicate keys, non-finite values, invalid root, unknown name, duplicate ID,
  multiple calls, trailing prose, and all documented size/depth/member limits.
  - Spec: Parse and normalization boundary; FR-2, FR-4
  - Files: `tests/test_mlx_models.py`

- [ ] T6.2.3 [implementation] Add the typed versioned codec/candidate protocol,
  compatible-backend gate, renderer, bounded parser normalization, and
  capability-aware request rejection. Keep the stock backend text-only.
  - Spec: FR-1, FR-2, FR-4
  - Files: `src/dynamic_agent_runner/mlx_models.py`
  - Depends on: T6.2.1, T6.2.2

- [ ] T6.2.4 [tests/implementation] Add RED then GREEN sync/async continuation
  tests, proving the second codec request renders DAR's existing assistant call
  and matching `model_tool_result` with canonical ID/name/arguments.
  - Spec: Rendered transcript; FR-3
  - Files: `tests/test_mlx_models.py`, `src/dynamic_agent_runner/mlx_models.py`
  - Depends on: T6.2.3

- [ ] T6.2.5 [tests] Add RED then GREEN executor integration proving one fake
  MLX tool call uses the normal coordinator and registry exactly once, resumes
  through the codec continuation, and rejects malformed output before dispatch.
  - Spec: FR-2, FR-3
  - Files: `tests/test_executor.py`, `tests/test_mlx_models.py`
  - Depends on: T6.2.4

- [ ] T6.2.6 [validation/docs] Run focused fake-only regression, document the
  opt-in capability and default unsupported state, and record the optional
  manual Qwen competency evidence separately from CI.
  - Spec: Acceptance and Validation
  - Files: `README.md`, `docs/files/python-api.rst`, feature artifacts
  - Depends on: T6.2.5
