# MLX Local-Model Tool-Use Tasks

Status: M6.1–M6.3 delivered; M6.4 owned-codec source delivery in progress

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

- [x] T6.2.6 [validation/docs] Run focused fake-only regression, document the
  opt-in capability and default unsupported state, and record the optional
  manual Qwen competency evidence separately from CI.
  - Spec: Acceptance and Validation
  - Files: `README.md`, `docs/files/python-api.rst`, `tasks.md`
  - Depends on: T6.2.5
  - Implementation route: update only the existing public MLX sections. State
    that the stock lazy `_MLXLMBackend` is text-only, reports
    `tool_calling=False`, and rejects tool-bearing requests before generation.
    State separately that an explicitly caller-injected `MLXToolCodec` and
    version-compatible `MLXToolCapableBackend` can opt into tool calling; DAR
    retains exposure, validation, approval, coordinator, tracing, and
    continuation ownership. Do not add a default-codec or Qwen tool-use recipe.
  - Acceptance: README and Python API documentation distinguish the default
    unsupported backend from the opt-in injected pair, preserve unsupported
    structured output/embeddings/multimodal/streaming claims, and make no claim
    that arbitrary MLX, a tokenizer, or stock `mlx-lm` is tool-capable. The
    focused CI record names fake-only tests and no optional MLX import, model
    load, Metal, network, credential, or live generation. The manual Qwen
    competency result is `not run` and remains outside pytest, CI, and release
    gates. A future dated record must name the DAR revision; eligible macOS host
    class; pinned model revision and local digest; `mlx-lm` distribution/lock
    and codec version; nonsecret template/parser and generation settings;
    bounded local recording-tool outcome; and redacted evidence digest. It can
    establish only that exact environment and cannot enable the stock backend.
  - Validation: `poetry run pytest tests/test_import.py
    tests/test_local_models.py tests/test_mlx_models.py tests/test_executor.py
    -q`; `poetry run ruff check src tests`; `ruff format --check`; targeted
    pre-commit; and `make -C docs html` without editing generated output.
  - Readiness: implementation-ready. This plan is ready to execute under its
    stated gates.
  - Review disposition: Council required an explicit default-versus-injected
    distinction and a non-synthetic manual-evidence boundary; accepted. Ponytail
    rejected a new documentation page, default codec recipe, and empty evidence
    receipt; the existing sections and task record are sufficient.
  - Implementation: the existing README and Python API MLX sections now state
    that the default backend is text-only and document the advanced compatible
    injected-pair option without a Qwen or default-codec recipe. They retain
    DAR's ownership of the execution controls and the other unsupported
    surfaces.
  - Manual Qwen competency: not run. There is no verified built-in Qwen codec
    and compatible stock backend; no local model was loaded and no live
    generation, external tool, network, credential, pytest, CI, or release
    claim was made. Any future dated evidence must satisfy the stated
    environment-and-outcome record requirements.
  - Validation: `poetry run pytest tests/test_import.py
    tests/test_local_models.py tests/test_mlx_models.py tests/test_executor.py
    -q` passed (262); `poetry run ruff check src tests` and `ruff format --check
    src tests` passed; targeted Markdown pre-commit passed; and
    `poetry run make -C docs html` passed. The generated Python API source and
    rendered HTML were reviewed without hand-editing generated output.
  - Delivery review: Council approved the documentation content 2–1; the sole
    validation-evidence concern was resolved by the passing focused regression
    and Poetry-scoped documentation build. Ponytail confirmed that the existing
    two documentation sections plus this record are the smallest complete
    delivery.

- [x] T6.2.7 [decision/discovery] Record the approved `mlx-lm` upstream source,
  immutable revision, license/provenance record, retention/update policy,
  selected smaller Qwen3 parity artifact, and tokenizer inspection scope.
  - Evidence: `implementation-decision.md` pins `mlx-lm` v0.31.3 source commit
    `ed1fca4`, the Poetry lock hash, and
    `mlx-community/Qwen3-4B-Instruct-2507-nvfp4` revision
    `111ab717db337468c86004a79bd9df19c6e3986d`.
  - Gate: characterize the selected tokenizer API without importing `mlx_lm` in
    pytest; live competency remains an eligible-Mac manual step.

## M6.3 — Native MLX Safetensors Asset Recognition

- [x] T6.3.1 [tests/implementation] Extend DAR's MLX local-asset validation and
      scoped inventory contract to recognize native MLX safetensors snapshots
      while preserving the existing converted-NPZ layout.
  - Trigger: the locally cached `Qwen/Qwen3-4B-MLX-4bit` snapshot uses
    `model.safetensors`, `config.json`, `tokenizer.json`, tokenizer metadata,
    and vocabulary files; it is not a converted `tokenizer.model` plus
    `weights.npz` layout.
  - Scope: add one non-public validator in `local_models.py`, reused by MLX
    path resolution, availability, and caller/default-Hub inventory. The native
    layout requires contained regular `config.json`, `tokenizer.json`, and
    direct `model.safetensors` or the bounded, duplicate-safe index contract in
    `spec.md`. A recognized Hub snapshot permits only repository-contained blob
    symlinks; an ordinary directory permits only directory-contained files.
    Preserve the converted-NPZ branch's current behavior as the alternative
    layout. Do not load a model, import `mlx_lm` in pytest, infer a tool codec,
    add a model server, or relax containment.
  - RED: temporary direct-native, indexed-native, converted-NPZ, and valid
    contained-Hub-symlink fixtures must prove sync/async injected-adapter
    resolution, availability taxonomy, and one-item inventory classification.
    Cover missing config/tokenizer/weights; malformed, duplicate-key,
    non-string, traversing, missing, and unreferenced index entries; a direct
    native layout with an extra shard; and
    escaping config/tokenizer/shard symlinks. Assert zero loader, optional
    import, download, endpoint, or process calls.
  - GREEN: both layouts pass the shared structural boundary; invalid resolution
    raises `LocalModelResolutionError`, availability is `INVALID`, and inventory
    skips the candidate. The native Qwen snapshot may become eligible for a
    separate manual `mlx_lm` load check, but that check is not a pytest, CI, or
    release requirement.
  - Validation: `poetry run pytest tests/test_mlx_models.py
    tests/test_local_models.py -q`; focused import regression; Ruff, formatter,
    and targeted pre-commit. A real model load or generation requires a separate
    human-authorized manual acceptance step.
  - Readiness: implementation-ready. Council required exact native-layout,
    index, containment, and error-taxonomy contracts; accepted above. Ponytail
    accepted one internal validator and existing fixtures: no dependency,
    public API, registry, or loader abstraction is warranted.
  - Implementation: `_validate_mlx_model_directory` in `local_models.py` now
    centralizes converted-NPZ and native-safetensors admission. MLX adapter
    resolution, availability, and inventory reuse it. Native direct weights and
    bounded duplicate-safe indexes are accepted only under the specified
    containment root; invalid candidates fail closed through their existing
    result/error taxonomy.
  - Validation: focused import/local-model/MLX tests passed (197); full pytest
    passed (`1501 passed, 1 skipped, 6 deselected`); Ruff lint/format and
    targeted pre-commit passed. Tests use temporary fixtures and injected fake
    backends only; no `mlx_lm` import, model load, generation, network,
    endpoint, or external tool call occurred.
  - Delivery review: Council approved after adding default-Hub cached
    resolution, oversized-index pre-read bounds, adapter fail-closed, and
    invalid-inventory-omission evidence. Ponytail confirmed the shared private
    validator is the smallest complete delivery.

## M6.4 — Built-in Qwen3 MLX Tool Codec

- [x] T6.4.1 [discovery/compatibility] Characterize the pinned Qwen3 Instruct
      artifact against `mlx-lm` v0.31.3's public tokenizer, template,
      generation, and tool-parser interfaces on an eligible Apple Silicon host.
  - Spec: Built-in codec-profile activation; M6.4 built-in Qwen3 acceptance.
  - Files: `specs/mlx-local-model-tool-use/m6.4-compatibility-profile.md`
    (create), `implementation-decision.md`, `tasks.md`.
  - Record: the canonical Hub-relative locator
    `models--mlx-community--Qwen3-4B-Instruct-2507-nvfp4/snapshots/<revision>`
    for the selected repository and revision, an ordered SHA-256 manifest for
    config/tokenizer/weight files, installed `mlx-lm` version, public
    tokenizer/template/generation/parser symbols and signatures, initial and
    continuation render/result shapes, and each faithfully supported
    `tool_choice` mapping. Use fixed synthetic fixtures and record only
    structural shapes plus hashes or redacted excerpts: never host prompts,
    credentials, handler payloads, or an unredacted rendered transcript. The
    profile must not contain an author-machine absolute cache path. Use a local
    cached artifact only; do not download, invoke a tool, or contact an
    endpoint.
  - Exit: record exactly one of `qualified`, `ineligible_provenance`,
    `incompatible_runtime`, `incompatible_template`,
    `incompatible_tool_choice`, or `incompatible_parser`.
    `incompatible_runtime` covers an unavailable or wrong `mlx-lm`
    distribution or public generation API. Only `qualified` unlocks
    T6.4.2–T6.4.6. Every other outcome requires an explicit implementation
    decision before DAR owns a parser or accepts another Qwen artifact.
  - Readiness: implementation authorized by the owned-codec decision.
  - Delivery: `incompatible_parser` in
    `m6.4-compatibility-profile.md`. Native synthetic initial/continuation
    rendering and `json_tools.parse_tool_call` were characterized without model
    inference or tool dispatch. The parser accepts extracted JSON but rejects
    the template's delimiter-wrapped native response; DAR explicitly owns the
    narrow parser required for that envelope.
  - Delivery review: Council found and resolved cache-root portability, total
    runtime-exit, and de-secreted-evidence gaps. Ponytail confirmed the profile,
    Hub-relative locator, and a strict owned envelope parser are the smallest
    complete delivery; no generic runtime mechanism was added.

The package-owned implementation is in
`src/dynamic_agent_runner/qwen3_mlx_tools.py`. It is explicit opt-in, binds only
the pinned configured model ID, and leaves generic MLX factories text-only.

- [x] T6.4.2 [tests] Add fake-only tests for the owned Qwen3 template and
      envelope-parser contract.
  - Files: `tests/test_mlx_models.py`.
  - RED: the public helper and pinned identity export were absent.
  - GREEN: a fake tokenizer and fake `mlx_lm` generation module prove one
    wrapped call is normalized; malformed/mixed/duplicate-key envelopes and a
    mismatched configured model identity fail before tool dispatch.

- [x] T6.4.3 [implementation] Add a separate public Qwen3 source module and
      explicit helper.
  - Files: `src/dynamic_agent_runner/qwen3_mlx_tools.py`,
    `src/dynamic_agent_runner/__init__.py`.
  - Delivery: sync and async Qwen3 helpers accept a caller-loaded model and
    tokenizer, pair an owned strict codec with a compatible backend, and require
    the pinned configured model identity. They do not change generic MLX
    factories, add model-family detection, or add an executor/approval path.

- [x] T6.4.4 [tests/integration] Prove the built-in Qwen3 pair uses DAR's
      ordinary sync and async tool/continuation flow.
  - Spec: FR-2, FR-3; M6.4 built-in Qwen3 acceptance.
  - Files: `tests/test_mlx_models.py`, `tests/test_executor.py`.
  - Depends on: T6.4.3.
  - Acceptance: after one normalized `create_record` candidate, the executor
    validates and invokes the controlled handler once, appends the canonical
    assistant call and matching result, and receives a text completion on the
    second request. Invalid capability gates and malformed output dispatch zero
    handlers. Test every profile-supported `tool_choice`, rejection of every
    other choice, and concurrent sync/async calls serialize generation. This
    remains fake-only and does not make the live model a pytest dependency.
  - Validation: `poetry run pytest -q tests/test_mlx_models.py
    tests/test_executor.py`.
  - Delivery: fake-only sync and async executor coverage proves the pinned
    helper normalizes one `search_repo` candidate, invokes the controlled
    handler once, and renders the canonical assistant-call/tool-result
    continuation before receiving text. The Qwen3 codec rejects `auto`,
    `required`, and `none` before generation, and a per-adapter lock serializes
    concurrent sync and async generation through the shared sync adapter.

- [ ] T6.4.5 [manual acceptance] Run and record the pinned local Qwen3 MLX
      competency protocol after deterministic tests pass.
  - Spec: M6.4 built-in Qwen3 acceptance.
  - Files: `specs/mlx-local-model-tool-use/validation.md` (create only for the
    dated evidence), `specs/mlx-local-model-tool-use/tasks.md`.
  - Depends on: T6.4.4.
  - Procedure: on an eligible Apple Silicon host, run at least three bounded
    recording-tool initial-selection/continuation pairs using one
    profile-supported `tool_choice`, fixed prompt fixture, seed, temperature,
    max tokens, and timeout from T6.4.1. A successful pair has exactly one
    allowed schema-valid `create_record` call followed by the recorded text
    completion; record all outcome categories, failures, host/DAR/artifact/
    `mlx-lm`/codec provenance, and redacted raw-output digests.
  - Boundary: manual local evidence only; no external tool, account, endpoint,
    download, pytest, CI, or release claim. Model variation is reported as a
    rate/outcome, not a deterministic contract failure.

- [ ] T6.4.6 [docs/validation] Document the exact built-in capability boundary
      and run the final regression suite.
  - Spec: Capability truthfulness; M6.4 built-in Qwen3 acceptance.
  - Depends on: T6.4.5.
  - Files: `README.md`, `docs/files/python-api.rst`,
    `specs/mlx-local-model-tool-use/{spec,plan,tasks,validation}.md`.
  - Acceptance: documentation names only the pinned Qwen3 pair as built-in;
    arbitrary MLX artifacts, unsupported parser/template states, streaming,
    structured output, embeddings, multimodal, and parallel calls remain
    unsupported. The manual receipt is separate from CI claims.
  - Validation: `poetry run pytest -q`; `poetry run ruff check src tests`;
    `poetry run ruff format --check src tests`; `pre-commit run --files
    <changed files>`; regenerate and review documentation without editing
    `docs/source/*.rst` directly.
