# Model Interface Tool-Parity Tasks

Status: T1.1–T1.6 deterministic matrix and T2 approval-interaction gate
delivered; local-model competency and live/external acceptance remain separate

## Scope Rule

T1 delivers only the deterministic, offline controlled-tool contract matrix
defined in `spec.md`. T1 does not run Fastmail, a live MCP connection, OAuth, a
model server, a downloaded model, Metal, or an approval interaction. T2 is the
sole separate, wrapper-local approval exception; optional local-model competency
remains separate work.

## Authoritative Contract Cells

T1.1 defines one test-only `ParityRecord` projection and scripted scenario
inputs in its selected existing test area. Every positive interface/mode cell
below must run S1 through S6 and compare that same projection. No provider row
may substitute an adapter-only assertion for coordinator dispatch.

| Interface seam | Required positive modes | Required scenarios |
| --- | --- | --- |
| executor fake adapter | sync, async | S1-S5; S6 normalized malformed-call variant |
| OpenAI scripted client | sync, async | S1-S6 |
| LiteLLM scripted completion | sync, async | S1-S6 |
| recording local endpoint transport | sync, async | S1-S6 |
| injected llama.cpp backend | sync, async | S1-S6 |
| compatible injected MLX pair | sync, async | S1-S6 |
| Apple injected SDK/bridge | async | S1-S6 |

The stock MLX sync and async factories are separate expected-negative cells:
each rejects a tool-bearing request before generation or dispatch. There are no
other N/A cells. Every test installs the T1.1 test-local external-I/O blocker,
which fails attempted network, process-start, or model-download behavior.

## Scripted Scenario Contract

| Scenario | Scripted normalized call sequence | Required record outcome |
| --- | --- | --- |
| S1 | `create_record({"title": "DAR", "body": "controlled"})`, then text completion | one `create_record` invocation with those normalized arguments; no decoy call |
| S2 | valid `transform_record({"record_id": "record-seed", "operation": "uppercase"})`; invalid unknown, missing, wrong-type, and malformed variants | valid variant dispatches once; every invalid variant reports a package-owned error and dispatches zero handlers |
| S3 | `lookup_record({"key": "seed"})`, result `{"record_id": "record-seed", "body": "seed"}`, then `transform_record({"record_id": "record-seed", "operation": "uppercase"})`, then text completion | exactly the ordered two invocations and deterministic transformed result |
| S4 | `fail_controlled({"code": "planned"})`, whose handler returns `ToolResult(success=False, error="planned controlled failure")` | one failed invocation, `WorkflowExecutionError` completion with the fixed error, one model-tool-loop call trace, `tool_failure` stop trace, no continuation request, and no provider exception leakage |
| S5 | text completion with no call | zero invocations and no synthetic tool result |
| S6 | provider seams: malformed or incomplete native tool-call payload; executor fake: malformed normalized tool-call variant | package-owned model/tool error, zero handler and coordinator dispatches |

`ParityRecord` equality covers only the spec's deterministic fields: interface,
mode, scenario, exposed schemas, normalized calls, invocation sequence/results,
completion class, and package-owned error or trace type. Provider IDs, prose,
timestamps, and token usage remain diagnostic only.

## T1 — Deterministic Controlled-Tool Contract Matrix

- [x] T1.1 [discovery/tests] Choose the smallest existing test location for the
      controlled registry and comparison record, then add RED executor-level
      sync and async fixture tests for S1-S6.
  - Spec: Controlled Tool Contract; Required Scenarios; Parity Observables;
    FR-1 and FR-2
  - Inspect first: `tests/test_executor.py` and the nearest adapter test files;
    do not introduce a production test framework or a shared runtime registry.
  - Fixture: a test-only `ParityRecord` and process-local `lookup_record`,
    `create_record`, `transform_record`, and `fail_controlled` handlers with
    fresh state, invocation recording, and explicit `approval_required: "no"`
    definitions. S1-S4 and S6 use `loop_tool_workflow` with all four tools
    exposed, `tool_choice_policy.initial: "required"`, and
    `after_tool_result: "auto"`; its existing `run_again: "required"` policy
    drives S3's two turns. S5 uses a test-local no-loop `workflow_from` fixture
    with the same exposed tools and `tool_choice_policy.initial: "auto"`, so a
    text completion is admissible. The direct sync and async fake adapters
    return scripted `ModelResponse`/`ModelToolCall` values only, and run
    through public workflow execution.
  - I/O gate: a test-local fixture must intercept `socket.create_connection`,
    `socket.socket.connect`, `subprocess.Popen`,
    `asyncio.create_subprocess_exec`, `asyncio.create_subprocess_shell`, and
    `local_models.download_hub_file`/`download_hub_snapshot` (and their
    `hugging_face_support` origins). One focused test proves every interception
    fails; all parity cases use it.
  - Acceptance: implement the Scripted Scenario Contract exactly for both fake
    modes, including S2's four invalid variants, S3's returned `record-seed`
    continuation, and S6's normalized malformed-call variant. S4's handler
    returns the stated failed `ToolResult`; assert its `WorkflowExecutionError`,
    one loop-call trace, `tool_failure` stop, and no continuation. Assert no
    `WorkflowInterruptedResult` or approval trace in every scenario. The record
    has the stated equality projection.
  - Expected RED: at least one assertion for each S1-S6 observable fails before
    the scenario fixture and comparison projection exist; a helper-only RED is
    insufficient.
  - Validation: `poetry run pytest tests/test_executor.py -q`.
  - Delivered: `tests/test_executor.py` holds the test-local controlled registry,
    shared projection, scripted sync/async fake adapters, and I/O gate. The
    S2 wrong-type and unknown-field cases exposed a narrow registry defect, so
    `registry.py` now enforces declared string types, enum values, and unknown
    field rejection for strict (`additionalProperties: false`) input schemas
    before handlers run. This production repair is limited to the fixture's
    existing strict schemas and is covered by the focused executor/registry run.

- [x] T1.2 [tests] Add provider-seam contract fixtures for OpenAI and LiteLLM,
      sync and async, using only their existing scripted clients.
  - Spec: Interface Matrix; S1-S6; FR-1 and FR-3
  - Files/components: `tests/test_openai_client.py`,
    `tests/test_litellm_provider_adapter.py`; extract T1.1's immutable record,
    controlled registry/workflow builders, projection, and explicit I/O blocker
    into one importable test-only support module, then update T1.1 to use it.
    Keep scenario-specific assertions in their named test modules. This does
    not authorize runtime code, a global `conftest.py` hook, or a test framework.
    Make the existing scripted OpenAI fake sequence-capable for S3 continuation;
    script LiteLLM through its injected sync/async completion callables.
    Each provider cell must capture its adapter's returned normalized
    `ModelResponse` values at the existing `response_validator` boundary (or a
    test-local equivalent delegating recorder) and derive `ParityRecord`
    normalized calls from that capture. Do not populate a record from an
    expected `ModelToolCall` sequence or substitute direct `ModelResponse`
    values for a provider-native response.
  - Acceptance: every OpenAI and LiteLLM sync/async cell executes S1-S6 from
    the Authoritative Contract Cells table, installs the T1.1 blocker, and
    emits the shared `ParityRecord`. Valid calls use the public executor and
    ordinary coordinator; S2-invalid reaches normal validation but dispatches
    zero handlers, while S6 dispatches neither coordinator nor handler.
  - Expected RED: each scripted native response cannot yet satisfy the named
    cell's common-record equality assertion.
  - Validation: focused OpenAI and LiteLLM adapter tests, then the T1.1 test.
  - Delivered: `tests/parity_support.py` is the single test-only reusable seam;
    native scripted Responses and Chat Completions payloads enter their actual
    adapter normalizers, are captured by `response_validator`, and run through
    the public executor. OpenAI and LiteLLM cover S1–S6 in sync and async,
    including the complete invalid S2 matrix, continuation, failure, and
    no-coordinator boundaries.

- [x] T1.3 [tests] Add recording-transport and injected-backend coverage for
      the OpenAI-compatible local endpoint and direct llama.cpp adapters,
      sync and async.
  - Spec: Interface Matrix; S1-S6; deterministic contract gate
  - Files/components: `tests/test_local_models.py` and T1.1 fixture helpers.
    The endpoint factory has no transport argument: install a sequence-capable
    recording client on the constructed sync/async adapter's existing private
    client seam only in the test. Assert the default-provider path is untouched
    and retain the factory's normal local identity validator. Wrap each real
    endpoint and llama adapter in a test-local delegating response recorder so
    records derive normalized calls from actual adapter output, never expected
    scripts. Direct llama may receive an inert `tmp_path` sentinel solely to
    satisfy its local path locator; it is not a model artifact. Its injected
    backend must supply every response, and tests must prove no dependency
    loader, download callable, or model load touches the sentinel. For both
    seams, include the complete S2 invalid matrix, S3 continuation request,
    S4 one-call/no-continuation, S6 zero coordinator/handler, I/O blocker, and
    sync/async projection equality.
  - Gate: transports and backends are injected fakes; no endpoint process,
    llama model load, Hugging Face download, or local artifact is permitted.
  - Acceptance: every local-endpoint and direct-llama sync/async cell executes
    S1-S6 with the shared record and T1.1 blocker. The public executor/coordinator
    records exact handler order for valid calls; S2-invalid reaches validation
    but records zero handlers, while S6 records zero coordinator and handler
    dispatches.
  - Expected RED: the recording transport/injected backend cannot yet satisfy
    its named scenario record.
  - Validation: focused local-model adapter tests, then the T1.1 test.
  - Delivered: `tests/test_local_models.py` drives the factory-created local
    endpoint adapters through injected sequence-capable clients and a
    test-local delegating response recorder. Its fail-on-call provider guard
    proves no default client path is used, while the factory's identity
    validator remains active. The direct llama adapters use injected sequence
    backends and an inert existing path sentinel; their dependency loader,
    download callables, and default loader are fail-on-call. Both seams cover
    S1–S6 in sync and async modes, including the complete invalid S2 matrix,
    S3 continuation, S4 stop/no-continuation, S6 pre-dispatch rejection, and
    equal normalized projections.

- [x] T1.4 [tests] Add injected-pair MLX contract coverage and an explicit
      stock-backend unsupported regression.
  - Spec: Interface Matrix; FR-3; Validation Checklist
  - Files/components: `tests/test_mlx_models.py`, `tests/test_executor.py`, and
    the T1.1 fixture helpers.
    Reuse only the existing compatible fake codec/backend seam with a
    test-local sequence backend and a small sync/async delegating response
    recorder; derive `ParityRecord.normalized_calls` from returned adapter
    responses, never expected codec candidates. A minimal converted-layout
    `tmp_path` directory may satisfy the adapter's local-path validation, but
    is inert metadata, not an MLX artifact. Inject fail-on-call dependency,
    download, default-loader, and `mlx_lm` import guards and prove the backend
    is the sole generation route. Execute full S1–S6 in sync and async,
    including every S2-invalid variant: missing, wrong-type, enum, and unknown
    arguments must reach normal loop validation, while malformed JSON is
    rejected by the MLX codec-normalization boundary before a normalized call.
    Assert S3's three renders with `record-seed` in the continuation, S4's one
    render/`tool_failure`/no continuation, S6's malformed codec candidate
    before coordinator or handler dispatch, and equal sync/async record
    projections. For each public stock factory,
    inject `_MLXLMBackend` with opaque model/tokenizer spies and an otherwise
    compatible codec, then run a tool-bearing request through the public
    executor/registry. Assert `tool_calling=False`, package-owned rejection
    before resolution, codec render/decode or backend generation, loader or
    download, and coordinator or handler dispatch.
  - Acceptance: the compatible injected pair executes S1-S6 in sync and async
    form with the shared record and T1.1 blocker, through the public
    executor/coordinator. S2-invalid reaches validation but has zero handler
    dispatches, while S6 has zero coordinator and handler dispatches. The stock
    `_MLXLMBackend` sync and async factories reject a
    tool-bearing request before generation and cannot be counted as
    parity-capable.
  - Expected RED: the compatible pair does not yet satisfy each named record;
    the stock-negative test is GREEN only on rejection before dispatch.
  - Gate: no default codec claim, `mlx_lm` import, model load, or live Qwen run.
  - Validation: `poetry run pytest tests/test_mlx_models.py
    tests/test_executor.py -q`.
  - Delivered: `tests/test_mlx_models.py` drives the existing compatible fake
    codec/backend pair through S1–S6 using real injected adapter responses and
    a test-local recorder, for both public factories. The inert converted
    layout is only adapter metadata; import, default-loader, dependency, and
    download guards remain untouched. Missing, wrong-type, enum, and unknown
    S2 arguments reach normal loop validation, while malformed JSON is
    correctly rejected by the codec-normalization boundary before a normalized
    call. Each public stock factory is exercised through the executor with an
    injected `_MLXLMBackend` and compatible codec; it reports no tool capability
    and rejects before path resolution, codec activity, generation, or dispatch.

- [x] T1.5 [tests] Add Apple Foundation Models injected SDK/bridge contract
      coverage for its asynchronous callback path.
  - Spec: Interface Matrix; S1-S6; FR-1 and FR-3
  - Files/components: `tests/test_apple_foundation_models.py` and T1.1 fixture
    helpers.
  - Acceptance: each cell runs through public `execute_workflow_async` with the
    existing test-local no-loop workflow, so DAR—not a hand-built active
    context—installs the trusted callback context. The Apple final response is
    text-only and must not synthesize `ModelToolCall` values; derive the shared
    record's normalized calls from an observed wrapper/coordinator callback
    receipt, never the expected script or response text. The Apple async cell
    executes S1-S6 with the T1.1 blocker and no approval trace. Callbacks enter
    DAR's normal validation, coordinator, lifecycle, tracing, and result
    shaping before every valid controlled handler run. Structured S2-invalid
    variants reach the real coordinator once and have zero handler dispatches;
    malformed native payloads (the S2 malformed variant and S6) enter the
    provider-terminal path before coordinator or handler dispatch. S3
    executes two ordered callbacks in one fake `session.respond`, including the
    `record-seed` continuation. Within the fake callback S4 is a
    `ProviderToolTerminalError`; through the executor it is the required
    `WorkflowExecutionError` with no second model response, fixed failure/trace
    evidence, and no provider exception leakage.
  - Expected RED: the injected bridge cannot yet satisfy each named scenario
    record.
  - Gate: fake SDK/bridge only; no eligible Mac, Apple Foundation runtime, or
    Fastmail invocation.
  - Validation: `poetry run pytest tests/test_apple_foundation_models.py -q`.
  - Delivered: the public async executor installs the Apple callback context for
    every controlled scenario through the existing no-loop workflow. The fake
    SDK records callback attempts while a real coordinator spy supplies the
    shared record's observed normalized calls; the adapter recorder proves the
    text response contains no synthetic tool calls. S1–S6 include all
    structured S2 failures, malformed native S2/S6 failures, S3's two ordered
    callback results, and S4's terminal `tool_finished` evidence. The initial
    RED found the fixture enum lacked its explicit JSON-Schema string type;
    adding it preserves existing semantics and admits the exact controlled
    schema to Apple's direct wrapper. No production code changed.

- [x] T1.6 [validation] Run the complete deterministic matrix and record the
      exact covered interface/scenario cells and remaining separate gates.
  - Spec: Test Levels and Gates; Validation Checklist
  - Depends on: T1.1 through T1.5
  - Acceptance: every positive interface/mode/scenario cell in the
    Authoritative Contract Cells table has a passing deterministic record; the
    two stock-MLX negative cells are separately asserted; no unaccounted cell
    remains. The I/O blocker passes for the scoped matrix before broad
    regression begins. Approval and local-competency evidence are explicitly
    recorded as separate, not-run gates. Add
    `parity_semantic_projection` and per-scenario baselines in
    `tests/parity_support.py`, then assert them from its existing record maker
    and `test_executor.py`'s local record maker; do not add an aggregate runner
    that imports or private-calls other test modules. The projection must cover
    scenario/variant identity, exposed schemas, JSON-canonical normalized
    calls, invocation/results, completion outcome, and an approved package
    error category. It excludes interface/mode and provider trace mechanics.
    Structured S2 invalids are `validation_error`; malformed S2/S6 are
    `normalization_error` and may be `ModelExecutionError` for the MLX codec or
    `WorkflowExecutionError` elsewhere; S4 is `tool_failure`. Native tests
    retain exact error assertions. Apple S4 is the explicit callback-native
    exception: it proves one model request, a failed `tool_finished` event,
    executor `WorkflowExecutionError`, and no response continuation rather
    than a model-loop `tool_failure` stop trace. Record the closure in new
    `specs/model-interface-parity/validation.md`: a machine-readable
    13-positive-row (sync/async where applicable) by S1-S6 ledger including
    S2 variants, plus two stock-MLX negative rows, each linked to exact pytest
    nodes/results and separate-not-run approval, competency, and live gates.
  - Validation: run this exact scoped parity command before broad checks:

    <!-- rumdl-disable MD013 -->

    ```sh
    poetry run pytest -q \
      tests/test_executor.py::test_model_interface_parity_s1_selects_only_create_record \
      tests/test_executor.py::test_model_interface_parity_io_blocker_rejects_every_external_seam \
      tests/test_executor.py::test_model_interface_parity_sync_and_async_records_match \
      tests/test_executor.py::test_model_interface_parity_s5_sync_and_async_records_match \
      tests/test_executor.py::test_model_interface_parity_s2_valid_and_invalid_arguments \
      tests/test_executor.py::test_model_interface_parity_s3_continues_with_lookup_identifier \
      tests/test_executor.py::test_model_interface_parity_s4_reports_controlled_failure \
      tests/test_executor.py::test_model_interface_parity_s5_completes_without_a_tool \
      tests/test_executor.py::test_model_interface_parity_s6_rejects_malformed_normalized_call_before_dispatch \
      tests/test_openai_client.py::test_model_interface_parity_openai_s1_uses_normalized_native_call \
      tests/test_openai_client.py::test_model_interface_parity_openai_native_scenarios \
      tests/test_litellm_provider_adapter.py::test_model_interface_parity_litellm_native_scenarios \
      tests/test_local_models.py::test_model_interface_parity_local_endpoint_native_scenarios \
      tests/test_local_models.py::test_model_interface_parity_llama_cpp_native_scenarios \
      tests/test_mlx_models.py::test_model_interface_parity_mlx_injected_pair_native_scenarios \
      tests/test_mlx_models.py::test_model_interface_parity_stock_mlx_rejects_tools_before_dispatch \
      tests/test_apple_foundation_models.py::test_model_interface_parity_apple_callback_native_scenarios
    ```

    <!-- rumdl-enable MD013 -->

    Then run focused parity modules, `poetry run pytest -q`,
    `poetry run ruff check src tests`, `ruff format --check src tests`, and
    `pre-commit run --files <changed files>`.
  - Delivered: `tests/parity_support.py` now supplies a scenario-level semantic
    projection and canonical baselines, asserted from both existing record
    makers. Each record captures schemas from its actual adapter-facing request
    (or provider-bound equivalent), rather than reconstructing them from the
    fixture. The Apple fixture uses the same wrong-type and unknown-field inputs
    as every other seam. `validation.md` records the 13 positive rows, two stock
    MLX negative rows, exact scoped nodes, and the separate gates.
  - Validation: the exact scoped node command passed (143); focused parity
    modules passed (578); full pytest passed (`1451 passed, 1 skipped, 6
    deselected`); Ruff check and format check passed.

## T2 — Generated-Workflow Approval Interaction Gate

T2 verifies approval as a generated-workflow execution attribute. It does not
add a core DAR restriction, native DAR resume API, live model, live MCP
connection, or external mutation. It uses the public `WorkflowRunner` with a
scripted model, test-local binding/surface controls, and a fake authorized MCP
client whose `call_tool` recorder is the counted dispatch surrogate.

- [x] T2.1 [discovery/tests] Add one dedicated, test-local `_approval_runner`
      setup in `tests/test_dar_authoring_runner.py` for a controlled
      `create_record` and one declared side-effect decoy. It builds their
      discovered schemas, approved surface entries, per-tool provenance rules,
      explicit total budget, ledger/store, and scripted `QueuedClient`
      responses. Reuse the existing `FakeMCPClient` and `FakeApprovalBroker`;
      do not evolve runtime code, a general fixture framework, a local handler,
      or direct registry invocation.
  - The compiled workflow policy declares `create_record` as
    `approval_required: true`. Spy test-locally on
    `workflow_host.runner.create_host_tool_registry`, delegating to the real
    factory after recording its supplied bindings, and assert the materialized
    `authorized-mcp:` binding is `approval_required: "no"`. Public runner
    outcomes, broker decisions, and fake-client dispatch counts—not unexposed
    DAR approval traces—prove the wrapper alone receives the action and approval.
  - Call `parity_support.install_parity_io_blocker(monkeypatch)` and add a
    small blocked-socket probe to prove it is active. Use a scripted fake model
    and fake binding/surface controls; the fake client's recorded `call_tool` is
    the allowed in-process dispatch surrogate. No credential, Fastmail, live
    MCP, or external call is allowed.
  - The fixture's `max_total_tool_calls` is explicit. One public runner run
    preflights immutable registration/policy identity; each binding invocation
    re-loads its current binding, verifies the current surface, and claims the
    shared total-call counter before dispatch.
  - RED observed: the test initially failed because `_approval_runner` did not
    exist; GREEN adds only the named test-local setup and delegating spy.
  - Validation: `poetry run pytest tests/test_dar_authoring_runner.py -q`.
  - Delivered: the text-only scripted public run captures both real authorized
    bindings through the delegated factory, proves the compiled declared tools
    are approval-required while `authorized-mcp:create_record` is unapproved,
    keeps the decoy exposed, and proves the shared I/O blocker is active. It
    makes zero broker decisions and fake-client dispatches, leaving T2.2's
    approval/dispatch outcomes unimplemented.

### T2.1 Readiness Review

- Council triad: approved one dedicated, test-local `_approval_runner` because
  the existing runner helper hard-codes the mail tools, schemas, provenance, and
  scripted responses. The setup reuses its existing fake MCP client, broker,
  and queued client rather than changing runtime code or creating a general
  fixture framework.

- Council triad: requires a delegating `create_host_tool_registry` spy because
  public `WorkflowRunner` results do not expose materialized host bindings or
  DAR approval traces. The spy proves wrapper-owned `approval_required: "no"`;
  public result, broker, and fake-client counts prove the observable boundary.

- Ponytail: approved the dedicated local helper as the smallest viable shape.
  Reusing the existing `parity_support` blocker with a blocked-socket probe
  avoids a second I/O fixture; no provider transport, core resume API, or
  generic test abstraction is authorized.

### T2.1 Delivery Review

- Council triad: approved the delivered setup, binding observation, and I/O
  proof in the named runner test. It preserves public `WorkflowRunner`
  execution and the wrapper-only approval boundary without entering T2.2.

- Ponytail: approved the local setup, delegating spy, and reused blocker as the
  smallest complete test shape. No runtime policy/enforcement change, provider
  transport, dependency, or generic fixture is included. Focused runner tests
  passed (26); full pytest passed (`1452 passed, 1 skipped, 6 deselected`).

- [x] T2.2 [tests/implementation] Add RED then GREEN deny and `approve_once`
      cases for one schema-valid `create_record` invocation.
  - Acceptance: an absent broker fails at public runner preflight with
    `RunDarWorkflowError`, zero broker/fake-client calls, and no ledger action.
    Deny or cancel after a schema-valid handler entry writes intent plus the
    matching terminal ledger receipt and makes zero fake-client `call_tool`
    calls. An invalid decision or broker exception after handler entry writes
    intent plus a failed terminal receipt with zero fake-client calls. Invalid
    schema, provenance, binding, current surface, or total-budget input reaches
    neither broker nor fake client and does not spend budget.
  - `approve_once` yields one broker decision and one fake-client dispatch only
    after schema, provenance, binding, surface, ledger-claim, and budget checks.
    Direct `WorkflowApprovalStore` coverage proves a granted receipt cannot be
    replayed or used with a different action digest; a new generated invocation
    receives a fresh action and may prompt again. Do not claim that changed valid
    arguments automatically fail when the broker independently approves them.
  - Boundary: this is generated-workflow policy. The wrapper cannot broaden its
    exposed surface or bypass validation, provenance, current-surface, ledger,
    or budget checks.
  - Validation: `poetry run pytest tests/test_dar_authoring_runner.py`
    `tests/test_dar_authoring_authorized_tools.py`
    `tests/test_dar_authoring_approvals.py -q`.
  - Delivered: public runner coverage proves reusable absent-broker preflight,
    one approved `create_record` dispatch, and deny/cancel/invalid/broken
    intent-plus-terminal zero-dispatch outcomes. Existing approval-store tests
    remain the direct replay and changed-digest proof. Authorized-binding tests
    prove malformed/provenance input, binding failure, surface drift, and budget
    exhaustion stop before an added broker or fake-client call.

### T2.2 Delivery Review

- Council triad and Ponytail: approved the test-only slice. It reuses the
  T2.1 harness, fake client, approval broker, ledger/store, and I/O blocker;
  it adds no runtime policy, transport, resume, or generic test abstraction.

- Validation: focused approval modules passed (54); full pytest passed (`1462
  passed, 1 skipped, 6 deselected`); Ruff passed.

- [x] T2.3 [tests/implementation] Add RED then GREEN
      `approve_rest_of_run` coverage using two valid `create_record` calls in
      one bounded run.
  - Acceptance: an initial `approved_for_rest_of_run` decision allows a second
    valid `create_record` call with different schema-valid,
    provenance-valid arguments only after normal schema, provenance, binding,
    surface, ledger, and total-budget checks, with no second broker decision
    and exactly one second fake-client dispatch. A third scripted decoy call
    must prompt independently, then deny, with zero decoy fake-client dispatch.
    Prove grant scope behaviorally; the existing wrapper stores an opaque
    in-memory key rather than exposing a new grant-scope receipt or presenter
    API.
  - The grant deliberately does not bind later valid arguments for the same
    declared tool. Binding or current-surface drift blocks a later same-run
    call, as does total-budget exhaustion. A fresh `WorkflowRunner.run()`
    re-preflights current registration/profile and must prompt again, including
    after a denied or failed prior run; there is no persistence or recovery reuse
    claim.
  - Non-goal: do not implement approval for all future workflow runs.
  - Validation: focused wrapper approval test module.

  - Delivered: the public wrapper sequence grants `create_record` once for its
    active run, dispatches a second valid call with different arguments without
    a second broker decision, then independently prompts and denies the
    `delete_record` decoy. A fresh run prompts again for `create_record`.
    Focused direct checks prove run grants cannot bypass total-budget, current
    surface, or binding revalidation.

### T2.3 Delivery Review

- Council triad: approved after the public test identified the approval
  sequence as `create_record`, `delete_record`, then fresh-run `create_record`,
  and direct tests covered post-grant binding, surface, and budget failures.

- Ponytail: approved the smallest change: existing wrapper harness, fake
  client, broker, and in-memory grant store cover the behavior without runtime
  code, dependencies, or a new test abstraction.

- Validation: focused wrapper approval modules passed (54); full pytest passed
  (`1466 passed, 1 skipped, 6 deselected`); Ruff passed.

- [x] T2.4 [validation/docs] Record the deterministic approval receipt and
      update the parity spec status without changing T1's closed result.
  - Acceptance: record exact test nodes/results, the injected no-I/O proof,
    approval outcome evidence, and the continuing separation from local-model
    competency and live/external acceptance. Run focused approval tests, full
    pytest, Ruff, formatter, and pre-commit on changed files.
  - Delivered receipt:
    - `poetry run pytest -q tests/test_dar_authoring_runner.py`
      `tests/test_dar_authoring_authorized_tools.py`
      `tests/test_dar_authoring_approvals.py` passed all 58 collected nodes.
      The T2 nodes were:
      `test_runner_materializes_wrapper_approval_binding_without_external_io`,
      `test_runner_requires_an_approval_broker_before_consuming_input`,
      `test_runner_dispatches_create_record_once_after_approval`,
      `test_runner_grants_rest_of_run_only_to_the_same_declared_tool`, and
      `test_runner_records_terminal_receipt_without_dispatch_when_approval_fails`
      for `broker0-denied`, `broker1-cancelled`, `broker2-failed`, and
      `broker3-failed`.
    - The authorized-binding T2 nodes passed:
      `test_authorized_binding_rejects_invalid_inputs_before_approval_or_budget`,
      `test_authorized_binding_rejects_exhausted_budget_before_second_approval`,
      `test_authorized_binding_rejects_binding_failure_before_approval`,
      `test_authorized_binding_rejects_surface_drift_before_approval`,
      `test_authorized_binding_dispatches_only_after_local_approval`,
      `test_authorized_binding_does_not_dispatch_a_rejected_local_approval`
      for `denied-denied` and `cancelled-cancelled`,
      `test_authorized_binding_fails_closed_when_local_approval_fails`,
      `test_authorized_binding_fails_closed_without_broker_when_policy_requires_approval`,
      `test_authorized_binding_reuses_only_one_tool_run_grant`,
      `test_run_grant_does_not_bypass_an_exhausted_budget`,
      `test_run_grant_does_not_bypass_surface_revalidation`, and
      `test_run_grant_does_not_bypass_binding_revalidation`.
    - The approval-store T2 nodes passed:
      `test_approval_is_granted_and_consumed_once_for_the_exact_action`,
      `test_approval_rejects_a_changed_action_without_spending_the_request`,
      `test_approval_expires_without_creating_a_grant`, and
      `test_denied_approval_cannot_later_be_granted`.
    - `test_runner_materializes_wrapper_approval_binding_without_external_io`
      installs the executable blocked-socket/process/download probe; the T2.3
      run-grant node uses the same probe. `FakeMCPClient.call_tool` is the
      allowed in-process dispatch surrogate, not a live MCP invocation.
    - `poetry run pytest -q` passed (`1466 passed, 1 skipped, 6 deselected`).
      `poetry run ruff check src tests` passed. `poetry run ruff format --check
      src tests` passed (173 files already formatted). `pre-commit run --files
      specs/README.md specs/model-interface-parity/spec.md
      specs/model-interface-parity/tasks.md` passed.
  - Boundary: this closes only deterministic T1 parity and wrapper-local T2
    approval interaction. Local-model competency measurements and live/external
    acceptance remain manual, separate gates.

### T2.4 Delivery Review

- Council triad required the exact focused node/result list, executable no-I/O
  proof, in-process dispatch distinction, and changed-file pre-commit receipt;
  all are recorded above.

- Ponytail approved the three-document receipt/status update: it reuses the
  existing test evidence and adds no test, runtime code, dependency, or
  abstraction.

## T2 Readiness Review

- Council triad: approved after binding T2 to the public `WorkflowRunner` and
  its existing wrapper-local broker/authorized-MCP fake seam. The tasks assert
  generated-policy approval while keeping DAR's host binding unapproved, so no
  core interruption, live connection, or external dispatch is introduced.
- Council required fail-closed ordering: absent broker fails at runner preflight;
  invalid inputs fail before broker or fake-client dispatch; post-entry deny,
  cancel, invalid decision, and broker failure have their distinct ledger
  outcomes. The run grant is proven only behaviorally, is isolated from a decoy,
  and has no persistence claim across a fresh runner run.
- Ponytail: approved reuse of the existing runner, fake authorized-MCP client,
  approval broker, total-call counter, and opaque in-memory grant key. No new
  parity framework, core resume API, grant-scope receipt, or provider transport
  is authorized.

## Readiness Review

- Council triad: approved after requiring the shared `ParityRecord`, exhaustive
  interface/mode/scenario cells, concrete scripted observables, coordinator
  dispatch assertions, and a test-local external-I/O blocker. The final review
  also distinguishes the executor's normalized malformed-call S6 variant from
  provider-native malformed payloads.
- Ponytail: approved the smallest shape—one test-only projection and local I/O
  blocker in an existing test area. No production registry, adapter framework,
  dependency, endpoint, or test process is authorized.

## Delivery Review

- Council triad: approved after confirming every S1-S6 path produces the
  common record; S3 asserts the returned `record-seed` continuation; the I/O
  interceptor proof reaches every listed seam; S4 records `tool_failure` with
  no continuation; and S6 rejects malformed normalized arguments before
  coordinator dispatch.
- Ponytail: accepted the strict-schema repair and the test-only helper as the
  smallest delivery shape. No generic JSON-Schema engine, runtime parity
  framework, provider process, or new dependency was added.

## T1.6 Delivery Review

- Council triad: approved after requiring records to capture exposed schemas
  from each actual adapter-facing request or provider-bound tool envelope, and
  requiring the closure ledger to name every supporting node for each positive
  interface/mode row. The scoped command passed (143), focused parity modules
  passed (578), and the full suite passed (`1451 passed, 1 skipped, 6
  deselected`).
- Ponytail: accepted the smallest correction: one test-only envelope normalizer
  and request capture at existing recorders. No runtime change, aggregate test
  runner, generic test framework, provider process, or dependency was added.

## T1.2 Readiness Review

- Council triad: required a minimal, test-only support extraction because
  pytest fixtures and helpers private to `test_executor.py` cannot safely serve
  the named OpenAI and LiteLLM modules. The extraction is limited to the shared
  controlled-tool fixtures, record projection, and I/O blocker; provider-native
  scripts and assertions remain local to their adapter tests.
- Ponytail: accepts the support module as the smallest reusable seam. It must
  not become runtime code, a generic parity framework, or a global test hook.
- Council parsing gate: require a test-local adapter-response recorder so each
  provider record proves native scripted payloads became the observed normalized
  calls before executor/coordinator entry.

## T1.2 Delivery Review

- Council triad: approved the bounded support extraction and native-provider
  matrix after requiring full S2 invalid coverage, sync/async record equality,
  S3 continuation evidence, strict S4/S6 failure boundaries, and package-owned
  error assertions. No runtime code, provider process, approval interaction, or
  external I/O was introduced.
- Ponytail: accepted the one test-only support module and local scenario
  assertions; no generic parity framework or production abstraction was added.

## T1.3 Delivery Review

- Council triad: approved after requiring and verifying a fail-on-call default
  provider guard for the endpoint seam, real-adapter normalized-response
  recording, full S1–S6 sync/async coverage, and projection equality. The
  injected llama backend and inert path sentinel prove the tests neither load
  nor download a model.
- Ponytail: approved the test-only fakes, recorders, scenario table, and shared
  assertions as the smallest shape that covers both required native formats;
  no runtime code, dependency, or generic framework was added.

## T1.4 Delivery Review

- Council triad: approved the real injected-adapter record provenance, full
  sync/async S1–S6 matrix, structured-versus-malformed S2 boundary, and the
  codec-present stock `_MLXLMBackend` negatives through the public executor.
  Fail-on-call guards prove no MLX import, loader, download, generation, or
  dispatch occurs outside the compatible injected path.
- Ponytail: approved the existing fake codec/backend plus small local sequence
  and recorder helpers as the smallest complete shape. No runtime change,
  default codec, model artifact, or generalized test framework was added.

## T1.5 Delivery Review

- Council triad: approved public-executor/no-loop coverage after independent
  focused runs. It records actual coordinator receipts, covers every S2 invalid
  variant, proves the first S3 callback returns `record-seed`, verifies S4's
  failed `tool_finished` payload and no continuation, and rejects malformed
  S2/S6 before coordinator, handler, or model response.
- Ponytail: approved one adapter recorder because it is necessary to prove the
  Apple text response contains no synthetic calls; all other coverage reuses
  existing fake SDK/session, shared registry, record, and I/O blocker helpers.
