# Model Adapter Coverage Implementation Plan

Status: implemented; Slices 1-4 complete

## Goal

Implement the authoritative behavior in
`specs/model-adapter-coverage/spec.md`: add a public
`model_adapter_coverage` policy with default `"augmented"` and strict
caller-supplied adapter coverage, while removing `local_only` adapter-routing
semantics.

## Spec Trace

- Spec: `specs/model-adapter-coverage/spec.md`
- Primary runtime spec: `specs/dynamic-agent-runner/spec.md`
- Related provider spec: `specs/openai-compatible-provider-wrapper/spec.md`
- Related local-model spec: `specs/llama-cpp-local-model/spec.md`

## Existing Implementation Context

- `api.py` accepts `model_adapter` on high-level sync and async APIs.
- `context.py` stores reusable runtime collaborators in
  `WorkflowExecutionContext`.
- `executor.py` normalizes model adapters, selects a model/adapter in
  `_select_model_and_adapter(...)`, and currently creates a default async OpenAI
  adapter when no adapters are supplied in simple cases.
- `executor.py` currently has `_requires_local_only(...)` and filters adapters
  by `is_local` for `local_only` node metadata.
- Tests in `tests/test_executor.py` already cover capability routing, missing
  adapter failures, default OpenAI adapter creation, native model-registry
  capability lookup, and local-only routing.

## Planning Decisions

- Public policy values are strings: `"augmented"` and `"strict"`.
- Default policy is `"augmented"` across public execution APIs and
  `WorkflowExecutionContext`.
- Invalid policy values fail before model selection with a package-owned
  execution-boundary error.
- Strict policy means "use only adapters supplied by the caller." It does not
  imply local preference.
- Augmented policy should consider supplied adapters first, then create a
  default `AsyncOpenAIClientAdapter` only when eligible OpenAI-default coverage
  is missing.
- Remove `local_only` routing behavior. Preserve `is_local` metadata on adapters
  for diagnostics or future features, but do not use it for this selection path.
- Keep the existing public `model_adapter` parameter name.

## Implementation Shape

Add `model_adapter_coverage` to:

- `WorkflowExecutionContext`
- `execute_workflow(...)`
- `execute_workflow_async(...)`
- `run_agent_workflow(...)`
- `run_agent_workflow_async(...)`

Executor-side helpers should normalize the policy once near execution-context
normalization, then pass the policy into model-input preparation and adapter
selection.

The selection flow should be easy to reason about:

1. normalize supplied adapters
2. validate policy
3. match supplied adapters against requested model and required capabilities
4. in strict mode, fail if supplied adapters do not match
5. in augmented mode, create a default OpenAI adapter for the selected model when
   supplied adapters do not match and the default OpenAI path is eligible

Implementation may choose whether augmented mode appends a synthetic default
adapter before matching or creates it after supplied-adapter matching fails.
Tests should lock the observable behavior, not private helper names.

## Error Contract

Use `WorkflowExecutionError` for execution-time coverage-policy failures.

Error messages should name:

- `model_adapter_coverage`
- the policy value when invalid or strict
- the requested or fallback model
- required capabilities when relevant

## Validation Plan

Focused validation:

```bash
poetry run pytest tests/test_executor.py tests/test_model_capabilities.py -q
```

Broader public API validation:

```bash
poetry run pytest tests/test_cli.py tests/test_executor.py \
  tests/test_model_capabilities.py tests/test_import.py -q
```

Final repository validation, if time permits:

```bash
poetry run pytest -q
pre-commit run --files <changed files>
```

## Non-Implementation Notes

- Do not add arbitrary-provider discovery from `/v1/models`; provider-specific
  ChatGPT/Codex catalog discovery belongs to the OpenAI-compatible provider
  wrapper spec.
- Do not start local model servers.
- Do not use Hugging Face search or download for adapter coverage.
- Do not add a workflow-manifest field for adapter coverage.
- Do not preserve `local_only` adapter-routing semantics.
