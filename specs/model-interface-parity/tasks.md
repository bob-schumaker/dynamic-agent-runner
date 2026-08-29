# Model Interface Tool-Parity Tasks

Status: T1.1–T1.2 delivered; T1.3 is next

## Scope Rule

This task delivers only the deterministic, offline controlled-tool contract
matrix defined in `spec.md`. It does not run Fastmail, MCP, OAuth, a model
server, a downloaded model, Metal, or an approval interaction. The approval
gate and optional local-model competency measurements remain separate work.

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

- [ ] T1.3 [tests] Add recording-transport and injected-backend coverage for
      the OpenAI-compatible local endpoint and direct llama.cpp adapters,
      sync and async.
  - Spec: Interface Matrix; S1-S6; deterministic contract gate
  - Files/components: `tests/test_local_models.py` and T1.1 fixture helpers.
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

- [ ] T1.4 [tests] Add injected-pair MLX contract coverage and an explicit
      stock-backend unsupported regression.
  - Spec: Interface Matrix; FR-3; Validation Checklist
  - Files/components: `tests/test_mlx_models.py`, `tests/test_executor.py`, and
    the T1.1 fixture helpers.
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

- [ ] T1.5 [tests] Add Apple Foundation Models injected SDK/bridge contract
      coverage for its asynchronous callback path.
  - Spec: Interface Matrix; S1-S6; FR-1 and FR-3
  - Files/components: `tests/test_apple_foundation_models.py` and T1.1 fixture
    helpers.
  - Acceptance: the Apple async cell executes S1-S6 with the shared record and
    T1.1 blocker. Callbacks enter DAR's normal validation, coordinator,
    lifecycle, tracing, and result shaping before every valid controlled handler
    run; S2-invalid reaches validation but has zero handler dispatches, while
    S6 has zero coordinator and handler dispatches.
  - Expected RED: the injected bridge cannot yet satisfy each named scenario
    record.
  - Gate: fake SDK/bridge only; no eligible Mac, Apple Foundation runtime, or
    Fastmail invocation.
  - Validation: `poetry run pytest tests/test_apple_foundation_models.py -q`.

- [ ] T1.6 [validation] Run the complete deterministic matrix and record the
      exact covered interface/scenario cells and remaining separate gates.
  - Spec: Test Levels and Gates; Validation Checklist
  - Depends on: T1.1 through T1.5
  - Acceptance: every positive interface/mode/scenario cell in the
    Authoritative Contract Cells table has a passing deterministic record; the
    two stock-MLX negative cells are separately asserted; no unaccounted cell
    remains. The I/O blocker passes for the scoped matrix before broad
    regression begins. Approval and local-competency evidence are explicitly
    recorded as separate, not-run gates.
  - Validation: run the exact scoped parity test-node list under the T1.1
    blocker, then focused parity modules, `poetry run pytest -q`,
    `poetry run ruff check src tests`, `ruff format --check src tests`, and
    `pre-commit run --files <changed files>`.

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
