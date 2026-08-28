<!-- markdownlint-disable MD013 -->
# Apple Foundation Models Adapter Validation Log

Status: A1–A4 implementation, A3 C4 validation, and one human-authorized
Fastmail mutation acceptance complete; full test suite green

## Post-C4 Fastmail mutation acceptance — 2026-08-28

- A sealed Apple-backed workflow used the generic G5 authorized-binding path to
  create one Fastmail `create_note`. The human manually verified the result.
- The acceptance retained no mailbox content, OAuth material, raw tool result,
  or unredacted tool schema. A distinct live Fastmail/OAuth operation still
  requires its own current receipt and human dispatch authorization.

## A3 C4 Apple-backed Fastmail/O7 acceptance — 2026-08-27

- The eligible-Mac Apple-backed saved workflow completed the human-authorized
  Fastmail read-only invocation after a current-surface preflight. The retained
  evidence is limited to package/transcript digests, terminal status, dispatch
  count, and bounded diagnostic byte counts.
- Final verification: `poetry run pytest -q` — 1234 passed, 1 skipped, 6
  deselected; `poetry run ruff check src tests`, `pre-commit run --all-files`,
  and `git diff --check` passed.
- This completes C4.1–C4.5 and O7. The later single Fastmail mutation
  acceptance used the generic G5 workflow-policy path, not an Apple-specific
  permission model.

## A3 C4.3 Fastmail-schema preflight readiness — 2026-08-27

- RED: no host-owned operation could prove that the current reviewed MCP
  schema would translate into an Apple wrapper without creating a model session
  or dispatching the tool.
- GREEN: a reconnect-compatible reviewed-surface preflight performs one
  `tools/list` revalidation, requires the named tool to remain human-approved
  read-only, translates its schema only in memory through the same Apple
  wrapper translator, and returns only the full-surface digest and
  `admissible` or `blocked`. It retains no raw schema and creates neither
  an Apple model session nor a tool dispatch.
- Fake coverage proves admissible and blocked schemas, redacted receipt
  representations, one reconnected-surface lookup, and no Apple session. No
  OAuth, Fastmail, Apple live model, or mailbox call was made.
- Checkpoint validation: `poetry run pytest tests/test_apple_foundation_models.py
  tests/test_dar_authoring_mcp_surfaces.py -q` — 73 passed. The later C4
  completion evidence above records the full verification and human-authorized
  eligible-Mac run.

## A3 C3 Apple callbacks through host-owned MCP binding — 2026-08-27

- RED: a fake Apple sealed-host write callback reached the reviewed
  `send_email` MCP handler without an approval interruption. The original
  host-side `approval_required="no"` metadata correctly preserves the legacy
  host action flow, but did not give the Apple callback coordinator a pending
  approval boundary.
- GREEN: the Apple adapter now projects only active sealed-host
  `authorized-mcp:` side-effect bindings into a private callback registry with
  `approval_required="yes"`. That registry validates each operation against
  the original active registry object before allowing its projected entry, so
  the projection cannot hide a changed host surface. No generic provider
  registry, Apple-specific host decision collaborator, or second host run API
  was added.
- Fake Apple-host coverage proves the session receives only the currently bound
  read-only wrapper despite a broader discovered MCP surface; the reviewed
  callback dispatches once, has no exposed raw handler or registry, and returns
  a DAR-owned terminal result with a redacted host trace. The approval-required
  write callback reaches neither the host handler nor the MCP client, returns a
  typed provider interruption, and leaves a redacted failed trace. A direct
  regression rejects a source-registry replacement after callback projection.
- Validation: `poetry run pytest tests/test_apple_foundation_models.py
  tests/test_dar_authoring_host.py::test_apple_host_runs_only_the_bound_read_only_mcp_callback
  tests/test_dar_authoring_host.py::test_apple_host_does_not_dispatch_an_unapproved_write_callback
  tests/test_dar_authoring_runner.py tests/test_dar_authoring_authorized_tools.py
  tests/test_dar_authoring_mcp_tools.py -q` — 98 passed; `poetry run pytest -q`
  — 1210 passed, 1 skipped, 6 deselected; `poetry run ruff check src tests` and
  `git diff --check` passed.
- Council: the debugging triad's independent review found a source-currentness
  gap and a missing handler-entry assertion; both were added before its
  challenge round cleared C3. Ponytail: `Lean already. Ship.`

## A3 C2 sealed-runner adapter selection — 2026-08-27

- RED: the focused runner suite failed because `WorkflowRunner` did not accept
  an active configured profile ID.
- GREEN: HTTP profiles still construct `create_local_adapter`; Apple profiles
  construct `create_apple_foundation_model_async_adapter` from exactly one
  stored alias. The runner accepts both existing adapter types, rejects a
  same-alias HTTP-to-Apple profile mismatch before sealed input consumption,
  and passes strict adapter coverage to DAR.
- Fake Apple saved-workflow coverage proves sealed input consumption, terminal
  `{\"message\": ...}` shaping, async bridge execution, error/cancellation
  propagation, and redacted trace metadata. An unadvertised package model
  fails without invoking the model.
- Validation: `poetry run pytest tests/test_dar_authoring_runner.py
  tests/test_dar_authoring_host.py -q` — 29 passed; `poetry run pytest -q` —
  1207 passed, 1 skipped, 6 deselected; `poetry run ruff check src tests` and
  `git diff --check` passed.

## Scope

- Feature: `specs/apple-foundation-model-adapter/spec.md`
- Plan: `specs/apple-foundation-model-adapter/plan.md`
- A1 task record: `specs/apple-foundation-model-adapter/tasks.md`
- Canonical A2 task list: `specs/apple-foundation-model-adapter/a2-tasks.md`
- A1 only: local final text and explicit JSON Schema output.
- A2 Apple tool callbacks are governed by `a2-plan.md` and `a2-tasks.md`.
  B0 through B4.3 implementation, documentation, and validation evidence is
  recorded below.

## Preparation checks

- Spec, plan, tasks, and validation artifacts now exist and agree on A1/A2
  boundaries.
- The existing async OpenAI adapter and strict model-coverage path are the only
  approved executor seams.
- Unit/live test separation is explicit: fakes for deterministic tests, marked
  eligible-Mac tests for real Apple generation.
- The original preparation slice made no source or dependency changes; A1
  implementation now exists in commits `4af46fb`, `df88337`, `e773531`, and
  `01c1146`, while runtime defaults remain unchanged.

## Executed A1 evidence

- Slice 1: `4af46fb` — lazy contract, portability, and fail-closed tests.
- Slice 2: `df88337` — session translation, cancellation, and optional SDK
  dependency metadata.
- Slice 3: `e773531` — structured-output validation, capability metadata, and
  package-owned error causes.
- Slice 4: `01c1146` — strict executor selection coverage.
- Slice 5: live text/JSON/workflow tests and README documentation are prepared;
  default pytest excludes their `apple_live` marker, while selected tests skip
  unless macOS, `apple-fm-sdk`, and `SystemLanguageModel.is_available()` are
  present.
- Focused implementation suite: `149 passed, 2 skipped`.
- `poetry check`, Ruff, and focused pre-commit passed.

## Slice 6 completion-gate evidence

- Full suite: poetry run pytest -q — 677 passed, 4 skipped.
- SDK extra installation succeeded and apple-fm-sdk 0.2.1 imported successfully.
- Standalone live verification succeeded for text generation, structured JSON Schema generation, and a strict-coverage DAR workflow.
- Historical pytest-native live execution produced native GenerationError status
  255 despite availability reporting success; the current restored environment
  result is recorded in the A2 B0 diagnosis below.
- Ruff: `poetry run ruff check src tests` — passed.
- Metadata: `poetry check` — passed.
- Package build: `poetry build` — passed with network-enabled retry.
- Focused pre-commit and `git diff --check` pass for the final slice.

The implementation, deterministic validation, and standalone live runtime paths
are complete. The historical status-255 behavior remains tracked as T6.6 while
the restored-environment B0 result is investigated.

## A2 B0 native-harness diagnosis — 2026-08-26

- Installed the declared optional `apple-fm-sdk==0.2.1` extra into the project
  environment; before installation, all marked live tests skipped because the
  module was absent.
- The minimal standalone text-generation probe passed cleanly.
- The marked pytest file passed once, then passed in three consecutive repeat
  runs: 12 live test executions total, with no recurrence of status 255.
- Each pytest process emitted the same ignored `apple_fm_sdk` destructor error
  during interpreter teardown: `_ManagedObject.__del__` attempted to call a
  `None` release function. The standalone probe did not emit it.
- Current conclusion: status 255 is not reproducible in the restored declared
  environment. The teardown defect is SDK-native evidence, not a reason to add
  retries or pytest-specific production behavior. Keep standalone execution as
  the authoritative live gate while the harness is monitored.

## A2 B0.3 SDK construction spike — 2026-08-26

- Detected installed optional dependency: `apple-fm-sdk==0.2.1`.
- A local, non-generating construction probe created `@generable`
  `GenerationSchema` instances, a `Tool` subclass, and `GeneratedContent`; it
  awaited the tool callback directly without constructing a model session or
  invoking model generation.
- The probe demonstrated scalar, array, nested-object, string-enum, numeric,
  and array-cardinality schema paths plus JSON callback-argument extraction.
- `Optional[T]` serialized as a required field; `Literal[...]` and `dict[...]`
  schemas failed serialization. These are rejected A2 input forms.
- The version-pinned admitted/rejected matrix and generated wrapper-name policy
  are authoritative in `a2-plan.md`.
- The distribution metadata and lockfile report `apple-fm-sdk==0.2.1`; the
  installed module's `__version__` reports stale `0.1.0` metadata.
- Inside the Codex execution sandbox, both `SystemLanguageModel.token_count`
  and bare `LanguageModelSession.respond` returned native
  `GenerationError(status: 255)` despite `(True, None)` availability; this is
  not a context-window or tool-registration failure.
- Outside that sandbox, a bare response succeeded, then a no-side-effect
  `LanguageModelSession.respond` sentinel invoked `dar_tool_0` exactly once
  with parsed `{"token": "DAR_SENTINEL"}` arguments. The callback ran on a
  different thread and event loop from the caller. B0.3 is complete; B1 must
  marshal bridge work to the executor-owned loop.
- **Live-test environment requirement:** run Apple Foundation Models probes
  elevated outside the Codex sandbox in this environment. This requirement is
  proven only for the B0.3 native callback probe, not for all Apple hosts.
- Reproducible callback evidence (run this command from an elevated host
  terminal outside the Codex execution sandbox in this environment):

  ```bash
  poetry run pytest -m apple_live \
    tests/test_live_apple_foundation_models.py::test_live_apple_tool_callback_sentinel -q
  ```

  It passed on 2026-08-26. The SDK emitted its known deprecated
  `asyncio.iscoroutinefunction` warning and ignored teardown deallocator error;
  neither changed the successful callback assertions.

## A2 B1.1 coordinator characterization — 2026-08-26

- Added passing characterization coverage before B1.2 extraction. This is not a
  RED/GREEN implementation slice: the existing private coordinator already
  serves both executor paths, and the tests freeze its observable contract.
- Direct `tool_use_step` coverage proves normalized prepared arguments,
  `before_tool` → handler → `after_tool` order, direct result and node-output
  ownership, a fixed run id, and the absence of a provider call id.
- The model-loop coverage issues two distinct provider call ids and proves each
  remains bound to its own normalized arguments, lifecycle traces, result key,
  result output, and final model continuation.
- `poetry run pytest tests/test_executor.py -q` — `143 passed`.
- Ruff, pre-commit, and `git diff --check` passed for the B1.1 files.
- `poetry run pytest -q` produced `1125 passed, 1 skipped, 4 deselected`, plus
  the pre-existing unrelated MCP-server expectation failure in
  `tests/test_mcp_server.py::test_stdio_server_hides_execution_tools_without_a_configured_host`.
- Council, runtime, and ponytail review found no remaining P0/P1 issue. B1.2
  remains responsible for the dependency-light provider ingress request; B1.3
  owns wire-context exclusion tests.

## A2 B1.2 coordinator extraction — 2026-08-26

- Extracted the shared tool invocation boundary to
  `dynamic_agent_runner.tool_invocation`. The executor retains retries, node
  output recording, and workflow interruption/result control flow.
- `ActiveAdapterToolContext` is a non-wire `OpenAIModelRequest` field. It
  snapshots the exact model-facing selected `RegisteredTool` objects, the run
  state, plan/node, tracer/hooks, registry, and explicit retry policy; the
  coordinator accepts one request-bound invocation closure.
- Initial, overflow-retry, and iterative follow-up requests retain the same
  adapter context. Direct and model-loop callers both use the extracted
  coordinator.
- Descriptor-budget coverage captures the active adapter request and proves
  that its selected-tool snapshot contains `read_file` and excludes the
  node-exposed but omitted `search_repo` tool.
- RED: `poetry run pytest tests/test_openai_client.py::test_build_openai_request_keeps_adapter_context_out_of_extra -q`
  — expected `AttributeError` before the field was introduced.
- GREEN: `poetry run pytest tests/test_openai_client.py tests/test_executor.py -q`
  — `207 passed` after extraction and migration.
- Full validation: `poetry run pytest -q` — `1127 passed, 1 skipped, 4
  deselected`; `poetry run ruff check src tests`, `pre-commit run --files
  <B1.2 files>`, and `git diff --check` passed. B1.3 remains the owner of
  explicit wire-kwargs/trace exclusion and stale/raw-context tests.

## A2 B1.3 non-wire and stale-context contract — 2026-08-26

- `OpenAIModelRequest.to_kwargs()` excludes `adapter_context`; executor model
  request traces are asserted identical to the non-Apple provider kwargs for
  both the initial request and iterative tool-loop follow-up.
- Those wire/trace payloads contain neither the adapter context nor identities
  for the active registry or mutable execution state.
- `ActiveAdapterToolContext` validates its own snapshot, not only the helper:
  raw OpenAI descriptors are rejected at both construction paths. Replacing a
  registered tool after context creation fails before the invocation closure
  runs.
- RED: `poetry run pytest tests/test_tool_invocation.py -q` — raw descriptor
  acceptance failed the new factory test, then the direct-construction test.
- GREEN: `poetry run pytest tests/test_tool_invocation.py
  tests/test_openai_client.py tests/test_executor.py -q` — `210 passed`.
- Council and ponytail review found no remaining P0/P1 findings after the
  constructor-level invariant was added.
- Delivery validation: `poetry run pytest -q` — `1130 passed, 1 skipped, 4
  deselected`; `poetry run ruff check src tests`, `pre-commit run --files
  <B1.3 files>`, and `git diff --check` passed.

## A2 B1.4 provider interruption and decision primitives — 2026-08-26

- Added a typed provider interruption with fixed safe text and opaque metadata;
  the original DAR approval record is accessible only through the internal
  unwrap helper and never through a public `approval` field.
- Added canonical SHA-256 fingerprints bound to a runtime-checked
  `PreparedToolInvocation`, run/workflow/node/tool/action correlation, and
  normalized arguments. A synchronous collaborator receives the typed request;
  its returned invocation ID and fingerprint must exactly match or fail closed.
- Added an atomic, non-negative provider callback budget with boolean claims.
  B1.4 does not route decisions through coordinator dispatch or implement
  provider session behavior; B3.3 creates the budget per Apple session.
- RED: `poetry run pytest tests/test_tool_invocation.py -q` — missing B1.4
  types first caused collection failure; raw descriptor and direct context tests
  separately established the prior B1.3 RED cycles.
- GREEN: `poetry run pytest tests/test_tool_invocation.py
  tests/test_openai_client.py tests/test_executor.py -q` — `214 passed`.
- Council and ponytail review found no remaining P0/P1 findings.
- Delivery validation: `poetry run pytest -q` — `1134 passed, 1 skipped, 4
  deselected`; `poetry run ruff check src tests`, `poetry check`, elevated
  `poetry build`, `pre-commit run --files <B1.4 files>`, and `git diff --check`
  passed.

## A2 B1.5 provider decision dispatch — 2026-08-26

- Approval-required provider dispatch prepares and validates arguments, runs the
  input guardrail, then binds the synchronous decision request to the exact
  normalized invocation fingerprint before any lifecycle hook or handler.
- An approved decision invokes the prepared request exactly once. A per-context,
  lock-protected callback identity claim rejects replay before a collaborator or
  invocation runs. Mismatched and unknown collaborator responses fail closed.
- Denied, cancelled, and expired decisions return a typed terminal non-dispatch
  outcome: no tool handler, lifecycle hook, retry, registry dispatch, result
  write, or approval-pause trace occurs. The executor converts it to a
  non-retry `WorkflowExecutionError` before result/state handling.
- Only unresolved returns the existing DAR `ApprovalInterruption`; only that
  path emits approval pause trace records and becomes an executor-visible
  `WorkflowInterruptedResult`.
- RED: `poetry run pytest -q tests/test_tool_invocation.py` — 6 decision-outcome
  failures before coordinator wiring.
- GREEN: `poetry run pytest -q tests/test_tool_invocation.py tests/test_executor.py`
  — `162 passed`.
- Council initially found that terminal decisions were incorrectly represented
  as resumable pauses. The typed terminal outcome and executor handling resolved
  it; final council and ponytail reviews reported no P0/P1/P2 findings.
- Delivery validation: `poetry run pytest tests/test_tool_invocation.py
  tests/test_executor.py -q` — `162 passed`; `poetry run ruff check src tests`,
  `poetry check`, `poetry build`, focused pre-commit, and `git diff --check`
  passed. `poetry run pytest -q` reached `1145 passed, 1 skipped, 4 deselected`
  plus the pre-existing unrelated configured-host expectation failure in
  `tests/test_mcp_server.py::test_stdio_server_hides_execution_tools_without_a_configured_host`.

## A2 B2.1 schema-safe wrapper RED contract — 2026-08-26

- Added strict expected-failure tests for B2.2, with a fake SDK that enforces
  the observed `Tool` subclass, non-empty opaque name/description,
  `GenerationSchema`, and async `call(...)` construction contract without
  invoking callbacks.
- The admitted representative requires two ordered opaque wrappers
  (`dar_tool_0`, `dar_tool_1`) for only the trusted active context, including
  string enum, numeric bounds, array cardinality, nested object, and
  `list[Nested]` forms. Nested generated types must themselves provide a
  `GenerationSchema`.
- Rejection coverage requires a pre-session failure for caller `$ref`,
  composition, optional properties, null forms, non-string enums, `const`,
  `format`, `pattern`, string lengths, unknown keywords, and object-map forms.
  Stale/raw contexts and duplicate active identities also fail before session
  creation.
- RED evidence: `poetry run pytest -q --runxfail
  tests/test_apple_foundation_models.py::test_apple_tool_bridge_constructs_only_opaque_active_wrappers`
  fails because the current A1 adapter reports tool calling unsupported.
- Stored contract gate: `poetry run pytest -q -rxX
  tests/test_apple_foundation_models.py` — `20 passed, 19 xfailed`; all xfails
  are strict and must be removed by B2.2 when the implementation turns them
  green.
- Delivery validation: `poetry run ruff check src tests`, `poetry check`,
  `poetry build`, focused pre-commit, and `git diff --check` passed. `poetry run
  pytest -q` reached `1145 passed, 1 skipped, 4 deselected, 19 xfailed` plus
  the same pre-existing configured-host expectation failure in
  `tests/test_mcp_server.py::test_stdio_server_hides_execution_tools_without_a_configured_host`.

## A2 B2.2 schema-safe wrapper preparation — 2026-08-26

- Apple session construction receives one native `Tool` subclass per current
  tool in the typed `ActiveAdapterToolContext`; inactive and unexposed tools
  never reach the session. Opaque provider-facing names remain ordered
  `dar_tool_<index>` values, while the DAR tool id stays bridge-private.
- The active context, not wire descriptors, determines wrapper selection. A
  tool-bearing wire request without that typed context fails before session
  creation; an active typed context still produces wrappers when the wire
  descriptor list is empty.
- The strict translator admits the B0.3 scalar, array, nested-object, enum, and
  bound subset and rejects unsupported forms before session construction. It
  also rejects non-identifier and Python-keyword property names because the
  SDK spike did not prove an alias mechanism that preserves their model-visible
  names. Wrapper callbacks deliberately raise the B3 boundary error and never
  dispatch a DAR handler in this slice.
- RED/GREEN: B2.1's 19 strict expected-failure cases were removed after the
  implementation made them pass. `poetry run pytest -q
  tests/test_apple_foundation_models.py tests/test_openai_client.py
  tests/test_executor.py` — `251 passed`.
- Council and ponytail review found and resolved trusted-context activation,
  model-visible aliasing, and Python-keyword admission gaps. Final council and
  ponytail reviews reported no remaining P0/P1 findings.
- Delivery checks: `poetry run ruff check src tests`, `poetry check`,
  `poetry build`, `pre-commit run --files <B2.2 files>`, and `git diff --check`
  passed. Full `poetry run pytest -q` reached `1167 passed, 1 skipped, 4
  deselected` plus the known unrelated configured-host expectation failure in
  `tests/test_mcp_server.py::test_stdio_server_hides_execution_tools_without_a_configured_host`.

## A2 B3.1 callback RED contract — 2026-08-26

- Added a fake Apple callback session that invokes native wrapper instances with
  `GeneratedContent.to_json()`-style arguments. The approved contract exercises
  two active wrappers with distinct DAR tool ids and handlers, preventing a
  bridge from routing every wrapper to the first tool.
- The approved path spies on the exact coordinator ingress and requires two
  distinct nonempty action ids and result keys, one handler call per callback,
  decision binding, coordinator lifecycle traces (`tool_started`, `tool_result`,
  `tool_finished`), state results keyed by callback, and callback serialization
  of only `ToolResult.model_facing_output`.
- The invalid-arguments path requires coordinator entry and validation before an
  approval decision, handler, lifecycle hook, state result, or trace event. It
  retains the established Apple nested-error normalization by requiring a
  `ToolRegistryError` somewhere in the causal chain rather than as the outer
  error.
- Stored contract gate: `poetry run pytest -q -rxX
  tests/test_apple_foundation_models.py` — `42 passed, 2 xfailed`.
  Coupled coordinator gate: `poetry run pytest -q -rxX
  tests/test_apple_foundation_models.py tests/test_tool_invocation.py
  tests/test_executor.py` — `204 passed, 2 xfailed`. Both xfails are strict and
  are B3.2's implementation gate.
- Council and ponytail review found and resolved trace-origin, Apple error-chain,
  callback identity, and multi-wrapper routing gaps. Final reviews reported no
  remaining P0/P1 findings.
- Delivery checks: `poetry run ruff check src tests`, `poetry check`,
  `poetry build`, `pre-commit run --files <B3.1 files>`, and `git diff --check`
  passed. Full `poetry run pytest -q` reached `1167 passed, 1 skipped, 4
  deselected, 2 xfailed` plus the known unrelated configured-host expectation
  failure in
  `tests/test_mcp_server.py::test_stdio_server_hides_execution_tools_without_a_configured_host`.

## A2 B3.2 callback coordination — 2026-08-26

- Each Apple wrapper now constructs a request for the shared coordinator. The
  coordinator retains validation, active-tool exposure, executor-bound input
  guardrails, approval decisions, lifecycle hooks, trace/state updates, and
  model-facing result selection. The wrapper never dispatches a handler.
- Callback work runs inline only on the executor loop. A callback on a different
  Apple SDK loop is marshalled via `run_coroutine_threadsafe`; fake evidence
  proves coordinator execution occurs on the bound executor loop.
- Unresolved approval becomes `ProviderToolInterruption` and then a
  `WorkflowInterruptedResult`. Denied, cancelled, expired, validation/guardrail
  failures, failed results, and unserializable model-facing output use the typed
  terminal callback path, which the executor converts to a non-retry
  `WorkflowExecutionError`.
- RED: focused guardrail and failed-result tests initially failed because the
  active context did not carry a provider guardrail runner and the callback
  serialized failed results. The cross-loop and terminal-retry tests were added
  before their bridge behavior.
- GREEN: `poetry run pytest -q tests/test_apple_foundation_models.py
  tests/test_tool_invocation.py tests/test_executor.py` — `217 passed`.
  Council and ponytail re-review found no remaining P0/P1/P2 issues.
- Delivery checks: `poetry run ruff check src tests`, `poetry check`,
  `poetry build`, focused `pre-commit run --files`, and `git diff --check`
  passed. Full `poetry run pytest -q` reached `1180 passed, 1 skipped, 4
  deselected` plus the known unrelated configured-host expectation failure in
  `tests/test_mcp_server.py::test_stdio_server_hides_execution_tools_without_a_configured_host`.

## A2 B3.3 callback budget — 2026-08-26

- Apple wrapper creation now creates one atomic `ProviderCallbackBudget` for
  each native session and shares it among that session's wrappers. Its limit is
  the active plan `max_steps`, with the executor's existing `max_steps or 8`
  fallback; it does not reuse a context budget across sessions.
- Each callback claims a slot before argument parsing, approval, coordinator
  entry, handler dispatch, state mutation, or lifecycle hook. On exhaustion,
  DAR emits `provider_callback_budget_exhausted` on the executor loop with only
  the tool id, callback id, limit, and claimed count, then uses the existing
  non-retry provider-terminal path.
- RED: zero-, one-, and N+1-budget tests initially did not raise an exhaustion
  outcome because callbacks had no budget. Council then identified a mismatch
  where zero was interpreted as no calls rather than DAR's default eight;
  correction now matches the executor. The obsolete context-level budget field
  was removed so the per-session ownership is unambiguous.
- GREEN: `poetry run pytest -q tests/test_apple_foundation_models.py
  tests/test_tool_invocation.py tests/test_executor.py` — `220 passed`.
  Council and ponytail final reviews found no P0/P1/P2 issues.
- Delivery checks: `poetry run ruff check src tests`, `poetry check`,
  `poetry build`, focused `pre-commit run --files`, and `git diff --check`
  passed. Full `poetry run pytest -q` reached `1183 passed, 1 skipped, 4
  deselected` plus the known unrelated configured-host expectation failure in
  `tests/test_mcp_server.py::test_stdio_server_hides_execution_tools_without_a_configured_host`.

## A2 B3.4 callback cancellation and completion — 2026-08-26

- Each Apple response owns a thread-safe callback-session liveness guard. A
  callback checks it at entry, after the coordinator's pre-invocation lifecycle
  hook, and after its handler returns. The pre-dispatch check prevents a
  callback that was admitted before cancellation from reaching the handler.
- DAR's synchronous finalization of `tool_results`, `tool_result`, and
  `tool_finished` executes under a short session-backed commit guard, so a
  completed or cancelled response cannot race a later result or trace write.
  The guard deliberately does not own Apple-session abort/cleanup, which is
  B3.5 work.
- RED: `poetry run pytest -q tests/test_tool_invocation.py -k
  'continuation_guard_rejects_cancellation_before_handler_dispatch or
  result_commit_guard_rejects_closure_before_state_and_trace_writes'` — `2
  failed`: closure after `before_tool` still dispatched the handler and the
  coordinator had no result-commit guard.
- GREEN: the same command — `2 passed`; `poetry run pytest -q
  tests/test_apple_foundation_models.py tests/test_tool_invocation.py
  tests/test_executor.py` — `226 passed`.
- Existing Apple fake coverage proves callbacks after normal completion and
  cancellation fail closed. The new coordinator tests deterministically prove
  closure between coordinator entry and handler dispatch, and between handler
  return and result-state/trace finalization; neither path invokes an after hook
  or writes a result after closure.
- Council initially found a finalization TOCTOU; ponytail found an admission
  gap before handler dispatch. The pre-dispatch liveness recheck and lock-backed
  commit guard resolved both. Final council and ponytail reviews reported no
  P0/P1/P2 findings.

## A2 B3.5 terminal callback cleanup — 2026-08-26

- The installed `apple-fm-sdk` exposes no public session `abort`, `cancel`, or
  `close` method. Its `respond()` implementation cancels its native task and
  resets task state on coroutine cancellation or error. DAR therefore ends the
  current response by propagating its typed terminal callback outcome and closes
  its own callback capability once in the response `finally` path; it does not
  invent or call an unsupported SDK cleanup API.
- Deterministic fake session tests cover unresolved approval, callback-budget
  exhaustion, and cancellation. Each terminal path stops the scripted
  `respond()` callback sequence before its next callback, closes the DAR
  callback capability exactly once, and rejects an attempted later callback.
  The budget case retains only the permitted first handler call; the unresolved
  case has no handler call. Cancellation retains its already-started handler
  but has no result state and exactly one pre-cancellation `tool_started` trace,
  with no `tool_result` or `tool_finished` trace.
- Characterization/GREEN: `poetry run pytest -q
  tests/test_apple_foundation_models.py -k 'unresolved_approval_preserves_dar_interruption
  or budget_exhaustion_aborts_session_once or cancellation_aborts_session_once'`
  — `3 passed`; `poetry run pytest -q tests/test_apple_foundation_models.py
  tests/test_tool_invocation.py tests/test_executor.py` — `228 passed`.
  The existing response `finally` and terminal propagation satisfy the added
  B3.5 proof; no production cleanup behavior was added.
- Ponytail initially required explicit cancellation trace evidence. The test
  now requires exactly `tool_started`, excluding post-cancellation result and
  completion traces. Final council and ponytail reviews reported no P0/P1/P2
  findings.

## A2 B4.1 elevated live callback smoke — 2026-08-26

- Added two `apple_live` no-side-effect sentinels that use the real Apple SDK
  and DAR's Apple adapter, active tool context, coordinator, approval decision,
  hooks, tracing, and tool registry. They are selected explicitly and run
  elevated outside the Codex sandbox on this host.
- Approved sentinel: `before_tool` is observed before its local handler, then
  `after_tool`; it records one approved decision and DAR's
  `tool_started`/`tool_result`/`tool_finished` traces. The handler only returns
  a fixed local status object.
- Denied sentinel: the real callback reaches DAR's collaborator exactly once;
  it never reaches the handler or result state and emits no normal tool
  lifecycle trace. Apple may retry its failed native callback; the per-session
  one-call budget blocks that retry before another decision, optionally emitting
  only `provider_callback_budget_exhausted`.
- Elevated live evidence: `poetry run pytest -vv -m apple_live
  tests/test_live_apple_foundation_models.py::test_live_apple_dar_callback_sentinel`
  — `1 passed, 1 warning in 1.46s`; the denied test with its corresponding node
  — `1 passed, 1 warning in 1.63s`. Both emitted the known SDK deprecated
  `asyncio.iscoroutinefunction` warning and ignored `_ManagedObject.__del__`
  teardown `TypeError`; neither changed the test assertions.
- Council and ponytail reviews reported no P0/P1/P2 findings. Exactly-once and
  cross-loop behavior remain deterministic fake-backed proof, as specified by
  B0/B3 rather than this nondeterministic provider smoke.

## A2 B4.2 public documentation — 2026-08-26

- Updated the public README and authored Python API documentation to replace
  the former A1-only statement that Apple tools were unsupported.
- The published contract now documents active-node wrapper selection,
  coordinator-owned validation/guardrails/approval/hooks/traces/state, exact
  approved dispatch, terminal non-dispatch decisions, unresolved interruption,
  callback-session closure, callback budget, and the admitted tool-schema
  subset.
- The same documentation records the historical sandbox-only status-255 result,
  its non-reproduction in the restored environment, the elevated local harness
  command boundary, and the current SDK deprecation warning plus ignored
  teardown ``TypeError``. It explicitly states that the harness condition is
  not a universal Apple-host requirement.

## A2 B4.3 consolidated validation — 2026-08-27

- RED/GREEN provenance: the focused RED/GREEN transitions for B1 through B3
  remain recorded in their individual entries above. The consolidated current
  GREEN command, `poetry run pytest -q tests/test_apple_foundation_models.py
  tests/test_tool_invocation.py tests/test_executor.py`, completed with `228
  passed in 2.05s`.
- Full test command, `poetry run pytest -q`, completed with `1191 passed, 1
  skipped, 6 deselected, 1 failed in 9.47s`. The sole failure remains
  `tests/test_mcp_server.py::test_stdio_server_hides_execution_tools_without_a_configured_host`:
  it expects an empty stdio tool list, while the configured runtime exposes
  `run_dar_workflow`. This is an existing non-A2 MCP expectation conflict, not
  an Apple callback failure.
- `poetry run ruff check src tests` reported `All checks passed!`; `poetry
  check` reported `All set!`; and `poetry build` produced the 0.2.1 sdist and
  wheel.
- Elevated eligible-Mac gate, run outside the Codex execution sandbox:
  `poetry run pytest -vv -m apple_live
  tests/test_live_apple_foundation_models.py::test_live_apple_dar_callback_sentinel
  tests/test_live_apple_foundation_models.py::test_live_apple_dar_callback_denied_approval_skips_handler`
  completed with `2 passed, 2 warnings in 3.28s`. The warnings were the known
  SDK deprecation of `asyncio.iscoroutinefunction`; interpreter teardown also
  emitted the known ignored `_ManagedObject.__del__` ``TypeError``. Neither
  changed the approved or denied callback assertions.

## T6.7 MCP ``tools/list`` contract — 2026-08-27

- Decision: the generic DAR MCP server exposes ``run_dar_workflow`` only when
  its local host opens successfully. An unavailable or unconfigured host
  returns an empty tool list; a configured host exposes the one sealed-workflow
  execution surface.
- Replaced the environment-dependent no-host test, which had accidentally
  opened the developer's configured default host, with an explicit opener that
  raises ``OSError``. The configured-host test remains the positive contract
  coverage.
- `poetry run pytest -q tests/test_mcp_server.py` — `14 passed in 0.96s`.
  `poetry run pytest -q` — `1195 passed, 1 skipped, 6 deselected in 10.88s`.

## Required evidence by slice

### Slice 1

Record RED failures for missing public contract, lazy import portability, and
unsupported request/platform behavior, then GREEN results from
`poetry run pytest tests/test_apple_foundation_models.py tests/test_import.py -q`.

### Slice 2

Record fake-backed translation, fresh-session, cancellation, and generation
option tests. Prove no SDK import or session creation occurs for rejected
requests.

### Slice 3

Record normalized text/structured responses, capability metadata, package-owned
errors with preserved causes, and opaque-error classification behavior.

### Slice 4

Record strict Apple alias selection, strict missing-coverage failure, augmented
fallback preservation, and unchanged executor adapter boundaries.

### Slice 5

Record eligible-Mac live text, JSON Schema, and strict workflow results or the
precise prerequisite-based skip reason. Record documentation and import checks.

### Slice 6

Run and record:

```bash
poetry run pytest tests/test_apple_foundation_models.py \
  tests/test_executor.py tests/test_import.py -q
poetry run pytest -q
poetry run ruff check src tests
poetry check
poetry build
pre-commit run --files <changed files>
```

No live Apple test is part of the unit-test command. A1 completion requires either standalone eligible-Mac live evidence or a precise prerequisite or runtime limitation record;
the absence of an eligible Mac does not weaken deterministic unit coverage.

## Post-implementation live verification findings

- Optional SDK installation and import succeeded on macOS arm64.
- Clean standalone Python processes successfully exercised DAR text, structured JSON Schema, and strict-coverage workflow paths.
- Historical pytest-native execution failed inside Apple native generation with
  `GenerationError` status 255 despite successful availability. In the restored
  declared environment, the marked pytest suite passed 12 live executions with
  no status-255 recurrence, but emitted an SDK-native destructor error at
  process teardown. Standalone execution remains the authoritative live gate
  while that teardown defect is monitored.

## T6.6 standalone direct release gate — 2026-08-27

- Replaced pytest-native model generation as the A1 release gate with
  `scripts/run_apple_live_release_gate.py`. The script directly exercises DAR's
  Apple adapter for text, explicit JSON Schema output, and strict workflow
  execution; it emits only a format-versioned status/check receipt.
- Elevated eligible-Mac evidence: `poetry run python
  scripts/run_apple_live_release_gate.py` —
  `{"checks":["text","structured_output","strict_workflow"],"format_version":1,"status":"passed"}`.
- The script is the A1 release gate and must run outside the Codex execution
  sandbox on this host. Marked pytest-native Apple tests remain diagnostic
  evidence and A2 callback smoke coverage; no runtime retry or pytest-specific
  workaround was added.
