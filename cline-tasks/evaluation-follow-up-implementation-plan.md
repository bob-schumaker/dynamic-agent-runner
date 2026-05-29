# Evaluation Follow-Up Implementation Plan

## Goal

Prepare implementation work for the deferred Codex/Cline follow-ups that are most
relevant to `power-marimo` and near-term `dynamic-agent-runner` evolution:

- E1 — introduce `WorkflowExecutionContext` / `RunContext`
- E2 — add lightweight model capability metadata
- E3 — strengthen tool input-schema validation
- E4 — add explicit tool exposure states
- E5 — clarify tool catalog / callable registry / exposure / approval / sandbox
  policy separation
- E6 — refine `ToolResult` into clearer output facets
- E7 — define narrow in-process lifecycle hook protocols
- E8 — extend trace vocabulary
- E14 — implement async-first execution APIs and sync wrappers (Slices I.1
  and I.2 complete)

## Current Implementation Shape

The current implementation has these relevant characteristics:

- `WorkflowExecutionState` mixes mutable runtime outputs with execution-envelope
  concerns that are passed separately to `execute_workflow(...)`.
- `ToolResult` is simple: `tool_id`, `success`, `output`, and `error`.
- Tool schema conversion validates only that `input_schema` is a mapping before
  passing it through to OpenAI.
- Tool exposure is currently per-node `available_tools` plus
  `ToolExposureOverride(add/remove/only)`; no explicit `direct`, `deferred`,
  `direct_model_only`, or `hidden` state exists.
- Tool policy is present as raw metadata fields, but catalog, callable,
  exposure, approval, and sandbox boundaries are not yet first-class.
- Tracing has a generic event model and current event types, but no dedicated
  tool lifecycle or status vocabulary.
- Lifecycle hooks are now implemented through trusted in-process
  `WorkflowLifecycleHooks` callbacks.
- Model capability metadata for context window, structured-output support,
  reasoning support, modalities, and parallel tool-call support is now preserved
  through `ModelCapabilities`.

## Slice A — E1: `WorkflowExecutionContext` / `RunContext` — Complete

**Goal:** Refactor execution parameters into a stable context object without
changing behavior.

Likely files:

- `src/dynamic_agent_runner/context.py`
- `src/dynamic_agent_runner/executor.py`
- `src/dynamic_agent_runner/api.py`
- `src/dynamic_agent_runner/__init__.py`
- `tests/test_executor.py` or new `tests/test_context.py`

Suggested model:

```python
@dataclass(frozen=True)
class WorkflowExecutionContext:
    workflow: LoadedAgentWorkflow
    model_adapter: OpenAIClientAdapter
    tool_registry: ToolRegistry | None = None
    max_steps: int | None = None
    trace_sink: TraceSink | None = None
    prompt_cache: bool | None = None
```

Keep the public `execute_workflow(...)` signature compatible, but internally
normalize to the context object.

**Why first:** This reduces parameter sprawl before hooks and richer policy
fields are introduced.

Completion evidence:

- Implemented in commit `38929f1`.
- Added `src/dynamic_agent_runner/context.py` with
  `WorkflowExecutionContext` and `RunContext`.
- Preserved `execute_workflow(workflow, ...)` compatibility while allowing
  `execute_workflow(context, ...)` and `run_agent_workflow(...,
  execution_context=context)`.
- Rejected ambiguous invocations that combine a context with duplicate runtime
  or artifact keyword arguments.
- Validation: `ruff check src tests && ruff format --check src tests &&
  python -m pytest -q` — pass; 108 tests passed.

## Slice B — E3: Stronger Tool Schema Validation — Complete

**Goal:** Fail early on malformed OpenAI-compatible function schemas.

Likely files:

- `src/dynamic_agent_runner/registry.py`
- `tests/test_registry.py`

Checks to add:

- `input_schema` must be a mapping when present.
- Top-level schema must be object-shaped or inferable as object-shaped.
- `properties` must be a mapping when present.
- `required` must be a sequence of strings when present.
- Reject ambiguous top-level `oneOf`, `anyOf`, or `allOf` unless explicitly
  supported later.
- Remove or ignore `$schema` in model-facing OpenAI tool schema output.

**Why second:** This is low-risk and supports all later tool exposure and policy
work.

Completion evidence:

- Implemented in commit `44b0847`.
- Added shared registry-side schema normalization for OpenAI tool schema exposure
  and invocation input validation.
- Rejected malformed `input_schema` values, non-object schemas, non-mapping
  `properties`, invalid `required` entries, and top-level `oneOf` / `anyOf` /
  `allOf` combinators.
- Removed top-level `$schema` metadata from model-facing OpenAI tool parameters.
- Validation: `ruff check src tests && ruff format --check src tests &&
  python -m pytest -q` — pass; 116 tests passed.

## Slice C — E4 + E5: Tool Exposure States and Policy Separation — Complete

**Goal:** Make tool availability dimensions explicit while preserving current
behavior.

Likely files:

- `src/dynamic_agent_runner/models.py`
- `src/dynamic_agent_runner/registry.py`
- `src/dynamic_agent_runner/validation.py`
- `tests/test_registry.py`
- `tests/test_validation.py`

Candidate addition:

```python
class ToolExposure(str, Enum):
    DIRECT = "direct"
    DEFERRED = "deferred"
    DIRECT_MODEL_ONLY = "direct_model_only"
    HIDDEN = "hidden"
```

Initial semantics:

- `direct`: default current behavior; exposed to model and callable when
  registered.
- `deferred`: metadata only for now; not model-exposed unless future lazy-loading
  behavior is defined.
- `direct_model_only`: model-exposed but not valid for direct `tool_use_step`
  execution unless explicitly allowed later.
- `hidden`: callable/internal metadata may exist, but not exposed to model.

Policy separation should be introduced with lightweight dataclasses/properties
rather than a full sandbox engine.

**Why third:** This changes how tools are selected and validated; it should
happen after context and schema hardening.

Completion evidence:

- Implemented in commit `61f1548`.
- Added `ToolExposure` with `direct`, `deferred`, `direct_model_only`, and
  `hidden` states.
- Added `ToolPolicy` for side-effect, approval, sandbox, timeout, retry, and
  failure-behavior metadata without implementing a sandbox engine.
- Filtered model-facing tools so only `direct` and `direct_model_only` are
  model-exposable; `hidden` remains direct-callable but not model-exposed.
- Rejected `direct_model_only` and `deferred` tools for direct `tool_use_step`
  invocation/validation.
- Validation: `ruff check src tests && ruff format --check src tests &&
  python -m pytest -q` — pass; 121 tests passed.

## Slice D — E6: Richer `ToolResult` Facets — Complete

**Goal:** Preserve backward compatibility while adding model-facing, raw, log,
and event facets.

Likely files:

- `src/dynamic_agent_runner/registry.py`
- `src/dynamic_agent_runner/executor.py`
- `tests/test_registry.py`
- `tests/test_executor.py`
- `tests/test_tracing.py`

Candidate compatible shape:

```python
@dataclass(frozen=True)
class ToolResult:
    tool_id: str
    success: bool
    output: Any = None
    error: str | None = None
    model_output: Any | None = None
    raw_output: Any | None = None
    log_preview: str | None = None
    event_payload: Mapping[str, Any] | None = None
    sensitive_fields: tuple[str, ...] = ()
```

Implementation rule: if `model_output` is absent, continue using `output` so
existing tests and callers do not break.

**Why fourth:** This builds on clearer tool policy/exposure and prepares tracing
and hooks.

Completion evidence:

- Implemented in commit `815f55a`.
- Extended `ToolResult` with `model_output`, `raw_output`, `log_preview`,
  `event_payload`, and `sensitive_fields`.
- Preserved structured `ToolResult` objects returned by registered handlers.
- Used `model_output` as the downstream prompt/state output when present while
  retaining `output` as the backward-compatible fallback.
- Included raw/log/event facets and sensitive-field metadata in tool-result trace
  payloads.
- Validation: `ruff check src tests && ruff format --check src tests &&
  python -m pytest -q` — pass; 123 tests passed.

## Slice E — E8: Extended Trace Vocabulary — Complete

**Goal:** Add richer event types around existing operations without requiring
external observability.

Likely files:

- `src/dynamic_agent_runner/executor.py`
- `src/dynamic_agent_runner/tracing.py` if event constants are introduced
- `tests/test_tracing.py`

Initial additions:

- `tool_started`
- `tool_finished`
- `status_notice` where useful

Keep old `tool_invocation` and `tool_result` initially, or transition tests
carefully.

**Why before hooks:** Hooks should be able to rely on the new event vocabulary
once introduced.

Completion evidence:

- Implemented in commit `bcd76d4`.
- Added `tool_started` and `tool_finished` events around direct tool invocation
  while preserving existing `tool_invocation` and `tool_result` compatibility
  events.
- Added warning `status_notice` events for fallback tool failures, including a
  stable code, message, tool id, and error detail.
- Validation: `ruff check src tests && ruff format --check src tests &&
  python -m pytest -q` — pass; 125 tests passed.

## Slice F — E7: Narrow In-Process Lifecycle Hooks — Complete

**Goal:** Add safe Python protocol hooks around stable lifecycle points.

Likely files:

- `src/dynamic_agent_runner/hooks.py`
- `src/dynamic_agent_runner/context.py`
- `src/dynamic_agent_runner/executor.py`
- `src/dynamic_agent_runner/api.py`
- `src/dynamic_agent_runner/__init__.py`
- `tests/test_hooks.py` or updates to `tests/test_executor.py`

Start with observational hooks and limited controls:

- `before_node`
- `after_node`
- `before_model`
- `after_model`
- `before_tool`
- `after_tool`
- `after_workflow`

Initial control can be minimal: allow hooks to raise project errors or return a
structured stop reason later. Avoid arbitrary shell hooks, plugin loading, or
untrusted hook sources.

**Why last:** Hooks touch the most lifecycle boundaries and are safer after
context, result facets, and trace vocabulary are stable.

Completion evidence:

- Implemented in commit `bf18554`.
- Added `src/dynamic_agent_runner/hooks.py` with `WorkflowLifecycleHooks` and
  stable hook context objects for node, model, tool, permission-boundary, and
  workflow observations.
- Passed lifecycle hooks through `WorkflowExecutionContext`,
  `execute_workflow(...)`, and `run_agent_workflow(...)`.
- Invoked `before_node`, `after_node`, `before_model`, `after_model`,
  `before_tool`, `after_tool`, and `after_workflow` at stable executor lifecycle
  points.
- Kept controls minimal: trusted Python hooks may raise project errors to
  abort execution; shell hooks, plugin loading, and untrusted hook sources remain
  out of scope.
- Validation: `ruff check src tests && ruff format --check src tests &&
  python -m pytest -q` — pass; 129 tests passed.

## Slice G — E2: Lightweight Model Capabilities — Complete

**Goal:** Preserve model capability metadata without making it ambient provider
configuration.

Likely files:

- `src/dynamic_agent_runner/models.py`
- `src/dynamic_agent_runner/__init__.py`
- `tests/test_model_capabilities.py`
- `tests/test_import.py`

Initial semantics:

- Parse `execution_policy.model_capabilities` into a lightweight
  `ModelCapabilities` model.
- Preserve context-window, structured-output, reasoning, modality, and
  parallel-tool-call support metadata.
- Keep capability metadata observational for now: it must not leak into OpenAI
  request parameters unless a later scoped slice maps capabilities to provider
  behavior.

Completion evidence:

- Implemented in commit `13c6dac`.
- Added `ModelCapabilities` and `RuntimeManifest.model_capabilities`.
- Exported `ModelCapabilities` from the package root.
- Added tests for field normalization, manifest preservation, public export, and
  separation from OpenAI request kwargs.
- Validation: `ruff check src tests && ruff format --check src tests &&
  python -m pytest -q` — pass; 132 tests passed.

## Slice I — E14: Async-First Execution APIs and Wrappers — In Progress

**Goal:** Convert workflow execution to a true async-first runtime while keeping
existing synchronous public APIs as compatibility wrappers.

E14 should deliver these public behavior changes:

- `execute_workflow_async(...)` returns `WorkflowResult` and becomes the
  canonical executor entry point.
- `run_agent_workflow_async(...)` returns the final workflow result and becomes
  the canonical high-level API entry point.
- `execute_workflow(...)` and `run_agent_workflow(...)` remain available, but
  delegate to the async APIs through a safe sync wrapper.
- Sync wrappers raise a project error when called from an already-running event
  loop in the same thread.
- OpenAI model execution uses one async-canonical model-client protocol.
- Tool handlers and lifecycle hooks can be sync or async, with callable shape
  inspected at registration or setup time.
- Cancellation is best-effort and propagates through async model calls, tool
  calls, hook calls, and child tasks where the underlying boundary supports it.
- E13 run-correlation semantics remain valid for concurrent async runs.

### E14 source facts observed during planning

- Current executor is fully synchronous in `src/dynamic_agent_runner/executor.py`:
  `execute_workflow(...)` drives the loop, calls synchronous helper functions,
  uses `_call_hook(...)`, invokes `adapter.create_response(...)`, and calls
  `registry.invoke_tool(...)`.
- Current public API in `src/dynamic_agent_runner/api.py` exposes only
  `run_agent_workflow(...)`, which loads artifacts and calls
  `execute_workflow(...)`.
- Current OpenAI adapter in `src/dynamic_agent_runner/openai_client.py` defines
  a synchronous `OpenAIClientProtocol`, synchronous `OpenAIClientAdapter`, and
  `create_default_openai_client()` using `openai.OpenAI`.
- Current registry in `src/dynamic_agent_runner/registry.py` stores bare tool
  handlers and invokes them synchronously.
- Current hooks in `src/dynamic_agent_runner/hooks.py` are typed as synchronous
  callbacks.
- Local OpenAI SDK source confirms async support exists:
  - `/Users/roschuma/Repos/github/openai-python/src/openai/_client.py` defines
    `AsyncOpenAI`.
  - `/Users/roschuma/Repos/github/openai-python/src/openai/resources/responses/`
  `responses.py`
    defines `AsyncResponses.create(...)` as `async def create(...)`.
  - `/Users/roschuma/Repos/github/openai-python/src/openai/_base_client.py`
    defines `AsyncAPIClient` around `httpx.AsyncClient` and exposes
    `async close()`, `async __aenter__`, and `async __aexit__`.

### Slice I.1 — async OpenAI client boundary

Status: complete in commit `acca9da`.

Likely files:

- `src/dynamic_agent_runner/openai_client.py`
- `src/dynamic_agent_runner/__init__.py`
- `tests/test_openai_client.py`

Implementation steps:

1. Introduce async-canonical protocol types:
   - `AsyncOpenAIResponsesResource` with `async create(...)`.
   - `AsyncOpenAIClientProtocol` with `.responses`.
2. Add `AsyncOpenAIClientAdapter` or convert `OpenAIClientAdapter` into an
   async-canonical adapter with `async create_response(...)`.
3. Add `create_default_async_openai_client()` using `openai.AsyncOpenAI`.
4. Keep response normalization and request construction shared.
5. Provide a compatibility adapter for sync-only clients only if needed for
   existing fake/client tests; do not make a parallel sync executor protocol the
   runtime contract.

Validation:

```bash
poetry run pytest tests/test_openai_client.py -q
```

Acceptance evidence:

- Fake async client is awaited by `AsyncOpenAIClientAdapter`.
- Native async default-client factory uses `openai.AsyncOpenAI`.
- Request construction and response normalization remain shared with the existing
  synchronous adapter boundary.
- Model failures still become `ModelExecutionError`.
- Validation: `poetry run pytest tests/test_import.py tests/test_openai_client.py
  -q` — pass; 11 tests passed.
- Pre-commit: `pre-commit run --files src/dynamic_agent_runner/openai_client.py
  src/dynamic_agent_runner/__init__.py tests/test_openai_client.py` — pass.

### Slice I.2 — async retry helper

Status: complete in commit `f2296e9`.

Likely files:

- `src/dynamic_agent_runner/retry.py`
- `tests/test_executor.py` or `tests/test_retry.py`

Implementation steps:

1. Add `run_with_retry_async(...)` using Tenacity's async retry support or a
   minimal explicit async retry loop.
2. Preserve `RetryPolicy` and `RetryRecord` shape.
3. Ensure `asyncio.CancelledError` is not swallowed or retried as an ordinary
   model/tool error.
4. Keep synchronous `run_with_retry(...)` only for compatibility helpers if still
   needed by sync adapters.

Validation:

```bash
poetry run pytest tests/test_executor.py -q
```

Acceptance evidence:

- `run_with_retry_async(...)` uses Tenacity async retry support while preserving
  `RetryPolicy` and attempt-count return behavior.
- Async retryable failures preserve attempt counts.
- `asyncio.CancelledError` propagates without retry, even when `BaseException` is
  supplied as retryable input.
- Validation: `poetry run pytest tests/test_retry.py tests/test_executor.py
  tests/test_import.py -q` — pass; 32 tests passed.
- Pre-commit: `pre-commit run --files src/dynamic_agent_runner/retry.py
  src/dynamic_agent_runner/__init__.py tests/test_retry.py` — pass.

### Slice I.3 — callable-shape metadata for tools

Likely files:

- `src/dynamic_agent_runner/registry.py`
- `tests/test_registry.py`

Implementation steps:

1. Add sync/async callable-shape metadata to `RegisteredTool`, detected when the
   tool is registered or constructed.
2. Extend `ToolRegistry` with an async invocation path such as
   `invoke_tool_async(...)`.
3. For async handlers, await the handler directly.
4. For sync handlers, run them through the documented sync-handler policy. Prefer
   a small helper boundary such as `asyncio.to_thread(...)` if blocking work must
   not block the event loop, and document that cancellation cannot safely kill an
   already-running sync handler thread.
5. Keep existing `invoke_tool(...)` as sync wrapper compatibility if needed by
   callers or tests.

Validation:

```bash
poetry run pytest tests/test_registry.py -q
```

Acceptance evidence:

- Registration/setup records whether each handler is sync or async.
- Async handlers are awaited and can return `ToolResult`.
- Sync handlers still work through the async executor path.
- Handler exceptions still become failed `ToolResult` values.

### Slice I.4 — callable-shape metadata for lifecycle hooks

Likely files:

- `src/dynamic_agent_runner/hooks.py`
- `src/dynamic_agent_runner/context.py`
- `tests/test_hooks.py`

Implementation steps:

1. Add hook wrapper or hook metadata structures that record whether each callback
   is sync or async during hook setup.
2. Add an async hook invocation helper that awaits async hooks and invokes sync
   hooks according to the chosen policy.
3. Preserve existing hook context dataclasses and run IDs.
4. Preserve trusted-hook abort behavior: raised project errors still abort
   execution; cancellation should propagate.

Validation:

```bash
poetry run pytest tests/test_hooks.py -q
```

Acceptance evidence:

- Async before/after node hooks are awaited.
- Async before/after model hooks are awaited.
- Async before/after tool hooks are awaited.
- Existing sync hooks still work.
- Hook context run IDs remain correct.

### Slice I.5 — async executor core

Likely files:

- `src/dynamic_agent_runner/executor.py`
- `tests/test_executor.py`
- `tests/test_tracing.py`
- `tests/test_prompt_cache.py`
- `tests/test_token_budget.py`

Implementation steps:

1. Add `execute_workflow_async(...)` as the canonical executor.
2. Convert the execution loop and node helpers to async equivalents.
3. Await model calls, tool invocations, and hook dispatch.
4. Preserve synchronous helper behavior for prompt rendering, token-budget checks,
   prompt-cache observation, output-contract validation, decision routing, trace
   emission, and state recording.
5. Preserve E13 `run_id` behavior and trace/hook correlation.
6. Add cancellation handling around the workflow loop:
   - emit a workflow cancellation/error trace when possible,
   - call `after_workflow` with an error/cancellation context when safe,
   - re-raise cancellation rather than converting it to a success result.

Validation:

```bash
poetry run pytest \
  tests/test_executor.py \
  tests/test_tracing.py \
  tests/test_prompt_cache.py \
  tests/test_token_budget.py \
  -q
```

Acceptance evidence:

- Async model call path works.
- Async direct tool path works.
- Async hooks work at executor lifecycle points.
- Existing retry, token-budget, prompt-cache, output-contract, tracing, and route
  behavior still passes.

### Slice I.6 — public async API and sync wrappers

Likely files:

- `src/dynamic_agent_runner/api.py`
- `src/dynamic_agent_runner/executor.py`
- `src/dynamic_agent_runner/__init__.py`
- `src/dynamic_agent_runner/cli.py`
- `tests/test_executor.py`
- `tests/test_cli.py`
- `tests/test_import.py`

Implementation steps:

1. Add `run_agent_workflow_async(...)` to load, validate, execute, and return the
   final result through `execute_workflow_async(...)`.
2. Export `execute_workflow_async(...)` and `run_agent_workflow_async(...)` from
   the package root.
3. Convert sync `execute_workflow(...)` and `run_agent_workflow(...)` into wrappers
   over their async counterparts.
4. Add a helper such as `_run_async_from_sync(...)` that:
   - calls `asyncio.run(...)` when no loop is running in the current thread,
   - raises `WorkflowExecutionError` with guidance when a loop is already running.
5. Keep CLI behavior synchronous by calling the sync wrapper from non-event-loop
   CLI execution.

Validation:

```bash
poetry run pytest \
  tests/test_executor.py \
  tests/test_cli.py \
  tests/test_import.py \
  -q
```

Acceptance evidence:

- Async public API returns the same final result shape as sync API.
- Sync wrappers work from ordinary synchronous callers.
- Sync wrappers raise a clear project error from an already-running event loop.
- CLI tests continue to pass.
- Public exports include the new async APIs.

### Slice I.7 — cancellation and concurrent async validation

Likely files:

- `tests/test_concurrency.py`
- `tests/test_executor.py`
- `tests/test_hooks.py`
- `tests/test_registry.py`
- possibly `src/dynamic_agent_runner/executor.py`

Implementation steps:

1. Add cancellation-focused tests using async fake model/tool/hook collaborators
   that block on `asyncio.Event`.
2. Cancel an in-flight workflow task and assert cancellation propagates.
3. Verify trace/hook cancellation observations that are feasible without
   swallowing cancellation.
4. Add concurrent async run tests using shared workflow/context objects.
5. Assert E13 invariants under async concurrency:
   - per-run state isolation,
   - run IDs remain distinct,
   - shared trace sink events are distinguishable by `run_id`,
   - hook observations are run-correlated,
   - package-owned shared helpers remain safe.

Validation:

```bash
poetry run pytest tests/test_concurrency.py tests/test_executor.py -q
```

Acceptance evidence:

- Cancellation test passes and does not produce a success result.
- Concurrent async runs preserve E13 run correlation.
- Sync and async entry points do not drift in observable final result, trace, hook,
  or error behavior.

### Recommended E14 implementation order

1. Slice I.1 — async OpenAI client boundary — complete in commit `acca9da`.
2. Slice I.2 — async retry helper — complete in commit `f2296e9`.
3. Slice I.3 — async-capable tool registry dispatch — next.
4. Slice I.4 — async-capable lifecycle hook dispatch.
5. Slice I.5 — async executor core.
6. Slice I.6 — public async API and sync wrappers.
7. Slice I.7 — cancellation and concurrent async validation.
8. Documentation/memory-bank checkpoint after implementation validation.

This order keeps the lowest-level awaitable boundaries stable before rewriting
executor control flow and public API behavior.

## Recommended Next Slice

Continue E14 with **Slice I.3 — callable-shape metadata for tools**.

Reasons:

- Slice I.1 has verified the local OpenAI SDK async surface and established the
  async model-client boundary.
- Slice I.2 has introduced the awaitable retry helper and cancellation-safe retry
  boundary.
- Slice I.3 should introduce async-capable tool-handler metadata and dispatch
  before hook and executor conversion work.

## Validation Plan

For each slice:

```bash
ruff check src tests
ruff format --check src tests
python -m pytest -q
```

For narrower early checks during development:

```bash
python -m pytest \
  tests/test_executor.py \
  tests/test_registry.py \
  tests/test_tracing.py \
  tests/test_validation.py \
  -q
```

## Preparation Evidence

Files inspected before this plan was saved:

- `src/dynamic_agent_runner/models.py`
- `src/dynamic_agent_runner/registry.py`
- `src/dynamic_agent_runner/executor.py`
- `src/dynamic_agent_runner/tracing.py`
- `src/dynamic_agent_runner/validation.py`
- `src/dynamic_agent_runner/__init__.py`
- `src/dynamic_agent_runner/api.py`
- `src/dynamic_agent_runner/context.py`
- `src/dynamic_agent_runner/hooks.py`
- `src/dynamic_agent_runner/openai_client.py`
- `src/dynamic_agent_runner/retry.py`
- `tests/test_registry.py`
- `tests/test_executor.py`
- `tests/test_tracing.py`
- `tests/test_validation.py`
- `/Users/roschuma/Repos/github/openai-python/src/openai/_client.py`
- `/Users/roschuma/Repos/github/openai-python/src/openai/_base_client.py`
- `/Users/roschuma/Repos/github/openai-python/src/openai/resources/responses/`
  `responses.py`

Repository state check:

- `git status --short && git branch --show-current` — pass; branch `develop`;
  only unrelated untracked `docs/` was reported before saving the E14 plan.
