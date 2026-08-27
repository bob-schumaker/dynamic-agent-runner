<!-- markdownlint-disable MD013 -->
# Apple Foundation Models Adapter Validation Log

Status: A1 implementation complete; standalone eligible-Mac live paths verified; pytest-native SDK verification under investigation; A2 plan approved

## Scope

- Feature: `specs/apple-foundation-model-adapter/spec.md`
- Plan: `specs/apple-foundation-model-adapter/plan.md`
- A1 task record: `specs/apple-foundation-model-adapter/tasks.md`
- Canonical A2 task list: `specs/apple-foundation-model-adapter/a2-tasks.md`
- A1 only: local final text and explicit JSON Schema output.
- A2 Apple tool callbacks are governed by `a2-plan.md` and `a2-tasks.md`; no
  A2 implementation evidence exists yet.

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
