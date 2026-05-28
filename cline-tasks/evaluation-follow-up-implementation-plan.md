# Evaluation Follow-Up Implementation Plan

## Goal

Prepare implementation work for the deferred Codex/Cline follow-ups that are most
relevant to `power-marimo` and near-term `dynamic-agent-runner` evolution:

- E1 — introduce `WorkflowExecutionContext` / `RunContext`
- E3 — strengthen tool input-schema validation
- E4 — add explicit tool exposure states
- E5 — clarify tool catalog / callable registry / exposure / approval / sandbox
  policy separation
- E6 — refine `ToolResult` into clearer output facets
- E7 — define narrow in-process lifecycle hook protocols
- E8 — extend trace vocabulary

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
- There are no lifecycle hooks yet.

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

## Slice E — E8: Extended Trace Vocabulary

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

## Slice F — E7: Narrow In-Process Lifecycle Hooks

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

## Recommended First Slice

Start with **E1 only** as the first implementation slice.

Reasons:

- It is mostly refactor/contract work.
- It creates the clean place to attach model capabilities, tool policy, trace
  sink, hooks, prompt-cache override, and future context-management settings.
- It minimizes behavioral risk before changing tool semantics.

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
- `tests/test_registry.py`
- `tests/test_executor.py`
- `tests/test_tracing.py`
- `tests/test_validation.py`

Repository state check:

- `git status --short && git branch --show-current` — pass; branch `develop`,
  no uncommitted changes were reported before saving this file.
