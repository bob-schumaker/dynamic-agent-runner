# Model Adapter Coverage Policy Specification

## Metadata

- Feature slug: `model-adapter-coverage`
- Mode: `light`
- Artifact type: public API behavior change specification
- Status: ready for implementation; plan and task list prepared; not implemented
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Related feature specs:
  - `specs/openai-compatible-provider-wrapper/spec.md`
  - `specs/llama-cpp-local-model/spec.md`
- Related implementation surfaces:
  - `src/dynamic_agent_runner/api.py`
  - `src/dynamic_agent_runner/context.py`
  - `src/dynamic_agent_runner/executor.py`
  - `src/dynamic_agent_runner/openai_client.py`
  - `tests/test_executor.py`
  - `tests/test_model_capabilities.py`

## Objective

Add an explicit client-facing model-adapter coverage policy that distinguishes
between strict caller-supplied adapter coverage and augmented coverage where the
runtime may create a default OpenAI adapter to fill missing model support. This
change also removes the separate `local_only` adapter-selection path because
strict coverage expresses the same caller intent more directly.

## Problem Statement

The current public API accepts `model_adapter` as one adapter or a sequence of
adapters. Executor selection already routes by adapter-advertised `models`,
`is_local`, `runtime.execution_policy.model_map`, and
`llm_step.model_requirements`, but the coverage policy is implicit:

- no provided adapters can cause a default OpenAI adapter to be created in simple
  cases
- provided adapters are effectively authoritative when capability routing
  matters
- there is no public option that says whether missing coverage should fail or be
  filled by a default OpenAI adapter
- `llm_step.model_requirements.operational_preferences.data_boundary:
  local_only` currently adds another adapter-selection mode that overlaps with
  the proposed strict coverage policy

Clients need to express two different intents clearly:

1. "Use exactly this adapter list and fail if it cannot cover the workflow."
2. "Use this adapter list, but add a default OpenAI adapter when coverage is
   missing."

## Proposed Public API

Add a `model_adapter_coverage` keyword argument to public execution entry points
and reusable execution context:

```python
run_agent_workflow(
    prompt="Run this workflow.",
    package_directory="path/to/agent-package",
    model_adapter=[local_adapter],
    model_adapter_coverage="augmented",
)
```

Allowed values:

- `"augmented"` — default; the runtime may create a default OpenAI adapter to
  fill missing coverage
- `"strict"` — the supplied adapter list is authoritative; missing coverage
  fails before any model request

The same keyword should be accepted by:

- `run_agent_workflow(...)`
- `run_agent_workflow_async(...)`
- `execute_workflow(...)`
- `execute_workflow_async(...)`
- `WorkflowExecutionContext`

## Functional Requirements

### FR-1: Default to augmented coverage

The public execution APIs must default `model_adapter_coverage` to
`"augmented"` for the normal default OpenAI behavior.

Acceptance criteria:

- Given a caller omits `model_adapter` and `model_adapter_coverage`, when a
  workflow can use the requested/default OpenAI model, then the runtime creates
  the default OpenAI adapter as it does today.
- Given a caller provides an adapter list that does not cover the selected model,
  when `model_adapter_coverage` is omitted, then the runtime may append or
  otherwise consider a default OpenAI adapter for non-local missing coverage.
- Given a caller provides `model_adapter_coverage="augmented"`, when model
  coverage is missing and the missing model is eligible for the default OpenAI
  path, then the runtime uses a default OpenAI adapter rather than failing only
  because the caller supplied some adapters.

### FR-2: Strict coverage fails when the provided list is empty

Strict mode must make caller-supplied adapter coverage authoritative, including
the empty-list case.

Acceptance criteria:

- Given `model_adapter=[]` and `model_adapter_coverage="strict"`, when execution
  reaches an `llm_step`, then execution fails before constructing or using a
  default OpenAI adapter.
- Given `model_adapter=None` and `model_adapter_coverage="strict"`, when
  execution reaches an `llm_step`, then execution fails before constructing or
  using a default OpenAI adapter.
- Given strict mode fails for missing coverage, then the error is a
  package-owned `WorkflowExecutionError` with a message that names strict
  adapter coverage and the affected model or capability requirements.

### FR-3: Strict coverage fails when provided adapters lack required support

Strict mode must preserve the caller's adapter boundary.

Acceptance criteria:

- Given strict mode and adapters that do not advertise the requested model, when
  the node has no special capability requirements, then execution fails instead
  of falling back to the first adapter or default OpenAI.
- Given strict mode and a node with required capabilities, when no provided
  adapter advertises a model satisfying those capabilities, then execution fails
  before any model request.

### FR-4: Remove local-only adapter-selection semantics

The runtime must remove the separate `local_only` adapter-selection behavior.
Clients that need local-only execution should pass only local adapters and set
`model_adapter_coverage="strict"`.

Acceptance criteria:

- Given a node declares `model_requirements.operational_preferences.data_boundary:
  local_only`, when model selection runs, then that metadata no longer changes
  adapter selection.
- Given a client needs local-only execution, when it supplies only local adapters
  with `model_adapter_coverage="strict"`, then missing coverage fails before any
  default OpenAI adapter can be created.
- Given a client supplies both remote and local adapters with strict coverage,
  when a remote adapter satisfies the requested model/capabilities first, then
  the runtime may select it; strict mode means "use only supplied adapters," not
  "prefer local adapters."
- Given code currently checks adapter `is_local` only for `local_only` routing,
  when this change is implemented, then that selection branch and its tests are
  removed or rewritten around strict coverage.

### FR-5: Augmented coverage fills eligible OpenAI-default gaps

Augmented mode may add the default OpenAI adapter, but it must not pretend to
satisfy non-OpenAI coverage.

Acceptance criteria:

- Given augmented mode and missing non-local coverage for an OpenAI model, when
  no provided adapter matches, then the runtime may create a default OpenAI
  adapter for the requested model or selected fallback model.
- Given augmented mode and model requirements choose a fallback model from
  `runtime.execution_policy.model_map`, when no provided adapter advertises that
  fallback model, then the runtime may create a default OpenAI adapter only if
  that fallback model is eligible for the hosted/default OpenAI path.

### FR-6: Validate coverage-policy values fail closed

The API must reject unknown coverage-policy values clearly.

Acceptance criteria:

- Given `model_adapter_coverage="best_effort"`, when execution starts, then the
  runtime raises a package-owned error or `ValueError` before model selection.
- Given `WorkflowExecutionContext` carries an invalid coverage policy, when it is
  used for execution, then execution fails before model selection.

## Design Notes

- Prefer a small typed/string-literal policy over overloading `model_adapter`
  shape. The difference between `None`, `[]`, and `[adapter]` should not be the
  only way to express client intent.
- Preserve the current `model_adapter` name for public API continuity. No
  backward compatibility is required for removing `local_only` selection
  semantics.
- Remove or ignore `_requires_local_only(...)` and any executor path that filters
  adapters by `is_local` solely because of node metadata. `is_local` may remain
  useful adapter metadata for diagnostics or future behavior, but it should not
  drive this coverage-policy change.
- The executor can normalize the effective adapter sequence after applying the
  coverage policy. The exact helper names are not authoritative.
- Public errors should use existing package-owned error types. The user request
  named `RuntimeError`, but this repository's execution-boundary error is
  `WorkflowExecutionError`; use that unless a later decision explicitly changes
  public exception policy.

## Non-Goals

- No live provider discovery from `/v1/models`.
- No automatic construction of local model servers.
- No automatic Hugging Face download as part of adapter coverage.
- No new manifest schema field for coverage policy in this change.
- No changes to tool registry selection.
- No backward-compatible preservation of `local_only` adapter-routing semantics.

## Validation Checklist

- [ ] `model_adapter_coverage` is accepted by sync and async high-level APIs.
- [ ] `model_adapter_coverage` is accepted by sync and async lower-level
      executor APIs.
- [ ] `WorkflowExecutionContext` stores and applies the coverage policy.
- [ ] Omitting the policy preserves augmented/default OpenAI behavior.
- [ ] Strict mode with `model_adapter=None` fails before default adapter
      construction.
- [ ] Strict mode with `model_adapter=[]` fails before default adapter
      construction.
- [ ] Strict mode with a nonmatching adapter fails before model request.
- [ ] Augmented mode with a nonmatching adapter can use the default OpenAI
      adapter for eligible non-local OpenAI coverage.
- [ ] `local_only` metadata no longer filters adapter selection.
- [ ] Tests that previously asserted `local_only` routing are removed or
      rewritten to assert strict coverage behavior.
- [ ] Unknown coverage-policy values fail clearly.
- [ ] Existing model capability routing tests continue to pass.

## Open Questions

- Should augmented mode append a default adapter to the candidate list, or should
  selection create a default adapter only after provided adapters fail to match?
- Should the coverage policy be represented internally as a string literal,
  enum, or small dataclass?
- Which hosted/default OpenAI eligibility check should be used for fallback
  models from `model_map` that are not recognized by `openai-model-registry`?
