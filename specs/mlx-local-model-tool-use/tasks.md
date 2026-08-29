# MLX Local-Model Tool-Use Tasks

Status: M6.1 and T6.2.1–T6.2.5 delivered; T6.2.6 is next

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
  - Historical evidence: before source selection, existing
    unsupported-capability tests passed. The selected package, source, and
    Qwen3 target are now recorded in `implementation-decision.md`.
  - Validation: `poetry run pytest`
    `tests/test_mlx_models.py::test_mlx_adapter_rejects_tool_calls`
    `tests/test_mlx_models.py::test_mlx_adapter_reports_conservative_capabilities`
    passed (2 tests); targeted Markdown pre-commit passed.
  - Council/Ponytail disposition: do not add an unapproved upstream subproject
    or leave a permanently RED test in the repository; keep the default path
    unsupported and move the generic codec TDD work into one GREEN slice.
  - Gate: the stock backend remains unsupported until the selected Qwen3
    tokenizer/template and parser pass the runtime compatibility gate.

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

- [x] T6.2.4 [tests/implementation] Add RED then GREEN sync/async continuation
  tests, proving the second codec request renders DAR's existing assistant call
  and matching `model_tool_result` with canonical ID/name/arguments.
  - Spec: Rendered transcript; FR-3
  - Files: `tests/test_mlx_models.py`, `src/dynamic_agent_runner/mlx_models.py`
  - Depends on: T6.2.3
  - Implementation route: TDD, using the existing fake MLX codec/backend seam;
    do not add an MLX-specific executor loop.
  - Acceptance: build the continuation from the first normalized
    `ModelToolCall` and DAR's existing transcript shape. For both a
    codec-supplied ID and an adapter-generated ID, assert the second captured
    `OpenAIModelRequest` retains the exposed schemas, appends the assistant
    call before its matching `model_tool_result`, and preserves the canonical
    ID, name, and arguments in both records. The second decoded response is
    ordinary text with zero tool calls. Run the same assertions through the
    async factory and require two rendered requests in each path.
  - Validation: `poetry run pytest tests/test_mlx_models.py -q`; no optional
    MLX import, model load, Metal, network, or handler invocation.
  - Readiness: implementation-ready. This plan is ready to execute under its
    stated gates.
  - Review disposition: Council required exact ordered continuation-pair and
    ID assertions; accepted. Council found no production-code gap. Ponytail
    accepted the existing fake codec/backend seam as the smallest solution.
  - Implementation: a four-case fake-only matrix covers sync/async adapters
    with adapter-generated and codec-supplied IDs. It builds continuation maps
    using DAR's existing transcript helper, captures the second codec request,
    and asserts the canonical assistant/result pair, retained tools and choice,
    two renders, and ordinary text completion. No runtime source change was
    needed because the adapter already passes the complete request to its codec.
  - TDD disposition: characterization exception. The new contract coverage was
    GREEN on its first run because the existing complete-request pass-through
    already satisfied the specified behavior; no production GREEN change or
    refactor was warranted.
  - Validation: `poetry run pytest tests/test_mlx_models.py -q` passed (45);
    `poetry run pytest tests/test_import.py tests/test_local_models.py
    tests/test_mlx_models.py tests/test_executor.py -q` passed (259); Ruff,
    Markdown pre-commit, and whitespace checks passed.
  - Delivery review: Council approved 2–1. The dissenting malformed-second-turn
    case was rejected as duplicate parser coverage from T6.2.3; executor loop
    and zero-dispatch behavior remain exclusively owned by T6.2.5. Ponytail
    confirmed that the test-only existing fake seam is the smallest delivery.

- [x] T6.2.5 [tests/implementation] Add RED then GREEN executor integration
  proving one fake
  MLX tool call uses the normal coordinator and registry exactly once, resumes
  through the codec continuation, and rejects malformed output before dispatch.
  - Spec: FR-2, FR-3
  - Files: `src/dynamic_agent_runner/executor.py`,
    `src/dynamic_agent_runner/mlx_models.py`, `tests/test_executor.py`
  - Depends on: T6.2.4
  - Implementation route: TDD against the public synchronous executor using
    `loop_tool_workflow`, one real injected `MLXLocalModelAdapter`, a compatible
    fake codec/backend, and a recording `InMemoryToolRegistry` handler. Do not
    add an MLX executor path, a shared test abstraction, or an approval-policy
    bypass. If the RED test exposes generic executor admission or DAR's
    canonical flat function descriptor as the missing boundary, repair only
    that shared boundary and cover it with the integration test.
  - Acceptance: the valid two-turn fake codec response first emits the exposed
    `search_repo` call, then ordinary text. Assert exactly one normalized
    handler invocation and one tool-loop dispatch trace; exactly two codec and
    backend calls; and that the second codec request ends with DAR's ordered
    assistant call and matching `model_tool_result`, retaining the canonical
    call ID, name, arguments, and model-facing output. For a malformed first
    candidate using the same exposed tool, assert the package-owned execution
    failure, zero handler invocations, zero tool-loop dispatch traces, zero
    continuation request, and one initial codec/backend call. Both cases use
    fake temporary MLX assets only, with no optional MLX import, model load,
    Metal, network, or approval interaction.
  - Readiness: implementation-ready. This plan is ready to execute under its
    stated gates.
  - Review disposition: Council approved after requiring the real compatible
    adapter path and explicit malformed-output zero-dispatch evidence. The
    proposed sync/async duplicate was rejected as T6.2.4-owned adapter parity;
    this slice owns the public executor integration boundary. Ponytail accepted
    one local fake codec/backend and the existing executor fixture as the
    smallest solution; no runtime abstraction is justified.
  - Readiness amendment: delivery RED evidence showed that the executor admitted
    only OpenAI adapter classes and the MLX allowlist read only nested tool
    descriptors, although DAR sends a canonical flat `type: "function"` form.
    This authorizes exactly generic `create_response` admission/awaitable
    handling and flat-function-name allowlisting; it does not authorize a
    separate MLX loop or any policy change. The integration test is the
    flat-descriptor acceptance evidence.
  - Implementation: the executor now treats any object with callable
    `create_response` as one adapter, keeps synchronous calls off-loop, and
    awaits a returned awaitable when necessary. MLX allowlisting accepts DAR's
    flat `type: "function"` descriptor as well as nested `function.name`.
    The fake-only public-executor tests cover a valid MLX call and continuation,
    malformed duplicate-key rejection before dispatch, and the generic
    awaitable-returning adapter boundary.
  - TDD: RED first exposed non-OpenAI adapter iteration, then the flat-tool-name
    mismatch; the generic awaitable regression exposed the final protocol gap.
    Each focused test passed after the shared boundary repair.
  - Validation: `poetry run pytest tests/test_executor.py tests/test_mlx_models.py
    -q` passed (213); `poetry run pytest tests/test_import.py
    tests/test_local_models.py tests/test_mlx_models.py tests/test_executor.py
    -q` passed (262); `poetry run ruff check src tests`, `ruff format --check`,
    Markdown pre-commit, and whitespace checks passed.
  - Delivery review: Council approved 3–0 after the readiness amendment.
    Ponytail accepted the local fakes and necessary shared-boundary repair;
    rejected a new adapter hierarchy, MLX-specific executor loop, or shared
    test framework.

- [ ] T6.2.6 [validation/docs] Run focused fake-only regression, document the
  opt-in capability and default unsupported state, and record the optional
  manual Qwen competency evidence separately from CI.
  - Spec: Acceptance and Validation
  - Files: `README.md`, `docs/files/python-api.rst`, feature artifacts
  - Depends on: T6.2.5

- [x] T6.2.7 [decision/discovery] Record the approved `mlx-lm` upstream source,
  immutable revision, license/provenance record, retention/update policy,
  selected smaller Qwen3 parity artifact, and tokenizer inspection scope.
  - Evidence: `implementation-decision.md` pins `mlx-lm` v0.31.3 source commit
    `ed1fca4`, the Poetry lock hash, and
    `mlx-community/Qwen3-4B-Instruct-2507-nvfp4` revision
    `111ab717db337468c86004a79bd9df19c6e3986d`.
  - Gate: characterize the selected tokenizer API without importing `mlx_lm` in
    pytest; live competency remains an eligible-Mac manual step.
