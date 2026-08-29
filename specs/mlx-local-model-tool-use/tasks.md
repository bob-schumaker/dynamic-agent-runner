# MLX Local-Model Tool-Use Tasks

Status: M6.1 and T6.2.1 delivered; injected-codec M6.2 is implementation-ready

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

- [x] T6.2.1 [discovery] Inspect the installed/pinned `mlx-lm` tokenizer and
  chat-template API before making a default-codec claim.
  - Spec: Codec and backend boundary; FR-1, FR-2
  - Evidence: `mlx-lm` is not installed in the Poetry environment and no pinned
    source exists in this repository. Existing unsupported-capability tests pass.
  - Validation: `poetry run pytest`
    `tests/test_mlx_models.py::test_mlx_adapter_rejects_tool_calls`
    `tests/test_mlx_models.py::test_mlx_adapter_reports_conservative_capabilities`
    passed (2 tests); targeted Markdown pre-commit passed.
  - Council/Ponytail disposition: do not add an unapproved upstream subproject
    or leave a permanently RED test in the repository; keep the default path
    unsupported and move the generic codec TDD work into one GREEN slice.
  - Gate: default codec remains blocked pending explicit upstream provenance,
    revision, license, and retention/update approval. No source pin was added.

- [x] T6.2.2 [tests/implementation] Add the injected versioned codec/candidate
  seam and make its focused RED tests GREEN in the same slice. Cover initial
  schema rendering, text response, one call, and canonical response-scoped IDs.
  - Spec: Codec and backend boundary; FR-1, FR-2
  - Files: `src/dynamic_agent_runner/mlx_models.py`, `tests/test_mlx_models.py`
  - Gate: it must not claim default `mlx-lm` compatibility or change the stock
    backend's unsupported state.
  - Implementation: `MLXToolCodec` renders one complete request and decodes text
    or one `MLXToolCallCandidate`; `MLXToolCapableBackend` admits only declared
    codec versions. Sync and async factories inject the codec. The stock
    `_MLXLMBackend` does not implement this protocol and remains tool-disabled.
  - Validation: focused RED failed at collection because the codec/candidate
    contract was absent; after implementation, MLX and executor tests passed
    (206), and the regression set passed (255). Ruff and
    diff-whitespace checks passed.
  - Council/Ponytail disposition: delivery review required a compatible backend
    before model resolution and strict normalization before activation; rejected
    registry, auto-detection, endpoint, and executor additions.

- [x] T6.2.3 [tests/implementation] Add RED then GREEN parser-boundary tests
  and bounded normalization for malformed JSON,
  duplicate keys, non-finite values, invalid root, unknown name, duplicate ID,
  multiple calls, trailing prose, and all documented size/depth/member limits.
  - Spec: Parse and normalization boundary; FR-2, FR-4
  - Files: `tests/test_mlx_models.py`, `src/dynamic_agent_runner/mlx_models.py`
  - Depends on: T6.2.2
  - Implementation: arguments are duplicate-safe, finite JSON objects with
    fixed 128 KiB response, 66 KiB candidate, 64 KiB arguments, depth-32, and
    256-member limits, canonical serialization, and exposed-name validation.
    The typed codec response permits one candidate;
    text plus a candidate is rejected, so multiple calls and trailing prose have
    no admissible normalized representation.
  - Validation: RED tests for malformed, non-finite, duplicate-key, non-object,
    unknown-name, and bounded candidates failed before normalization; all passed
    after implementation in the T6.2.2 delivery slice.

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

- [ ] T6.2.7 [decision/discovery] Before adding a default `mlx-lm` codec,
  obtain explicit approval for the authoritative upstream source, immutable
  revision, license/provenance record, retention/update policy, and inspection
  scope. Characterize that pinned API without importing it in pytest.
  - Depends on: T6.2.6
