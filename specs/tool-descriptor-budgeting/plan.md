# Tool Descriptor Budgeting Implementation Plan

## Metadata

- Feature slug: `tool-descriptor-budgeting`
- Status: implementation candidate plan for Slice T1
- Date: 2026-06-22
- Owning spec: `specs/tool-descriptor-budgeting/spec.md`

## Scope

Slice T1 adds an opt-in tool descriptor budgeting policy for `llm_step` model
requests. It ranks and packs only registry-exposed, model-exposable tool
descriptors before `build_openai_request(...)`.

Slice T1 does not add NLTK, embeddings, model-backed selection, descriptor
compression, persistent learned state, live-service calls, or any change to
direct `tool_use_step` execution.

## Current Architecture Fit

The implementation should stay close to existing seams:

- `RuntimeNode.raw` already preserves node-local metadata, so node-local
  `tool_descriptor_budget` can be read without changing manifest loading shape.
- `RuntimeManifest.execution_policy` already preserves runtime policy mappings.
- `InMemoryToolRegistry.list_tools_for_node(...)` is the authority for exposed
  model tools.
- `openai_tool_schema(...)` is the authority for OpenAI-compatible descriptor
  shape.
- `_execute_llm_step_async(...)` already calls `prepare_model_input(...)` before
  collecting exposed tools and building the model request.
- `token_budget.py` already owns model-aware token estimation and fallback
  encoding behavior.

The narrow integration point is the block in `_execute_llm_step_async(...)`
that currently turns `exposed_tools` into `tools`.

## Technical Approach

1. Add validation for `runtime.execution_policy.tool_descriptor_budget` and
   node-local `tool_descriptor_budget` on `llm_step` nodes.
2. Add small package-owned policy/result structures for descriptor budgeting.
   Keep them internal unless a public use case appears during implementation.
3. Add a `ToolSelector` near the registry boundary. It should accept prepared
   messages, exposed `RegisteredTool` values, policy, node-local override,
   effective model, and descriptor limits.
4. Convert candidate tools through `openai_tool_schema(...)` before estimating
   descriptor token cost. Do not duplicate schema normalization logic.
5. Rank using deterministic metadata:
   - required-tool policy
   - exact tool id and label matches in prepared prompt text
   - normalized token overlap from `description_for_llm`
   - schema property and required-field name matches
   - original `available_tools` exposure order as a stable tie-breaker
6. Pack required descriptors first, then optional descriptors until `max_tokens`
   or `max_tools` would be exceeded.
7. Fail with `WorkflowExecutionError` before model dispatch when a required tool
   is not exposed or cannot fit.
8. Emit redacted diagnostics through the existing trace/preparation metadata
   path used for model-request diagnostics.
9. Preserve the current `registry.to_openai_tools(...)` path when the policy is
   absent or disabled.

## Policy Shape

Slice T1 supports this runtime policy shape:

```yaml
runtime:
  execution_policy:
    tool_descriptor_budget:
      enabled: true
      model: gpt-4o-mini
      max_tokens: 1200
      max_tools: 8
      strategy: deterministic_metadata
      low_confidence_behavior: include_all_within_budget
      required_tools:
        - read_file
      diagnostics: redacted
```

Node-local override:

```yaml
nodes:
  - id: answer
    kind: llm_step
    available_tools:
      - search_repo
      - read_file
    tool_descriptor_budget:
      max_tokens: 800
      required_tools:
        - search_repo
```

Runtime and node-local `required_tools` are unioned. Node-local scalar controls
override runtime scalar controls.

## Key Decisions

- Policy is opt-in and disabled by default.
- Hidden, disabled, missing, deferred-only, or non-model-exposable tools remain
  invisible to the selector because selection starts from
  `list_tools_for_node(...)`.
- The selector should not mutate the registry or registered tool definitions.
- Diagnostics must be redacted by default and should not include raw prompts or
  full schemas.
- Unknown strategies and malformed policy values fail during validation.
- NLTK is benchmark-only future scope.

## Risks

- Token estimates over serialized descriptors may not match provider-side tool
  accounting exactly. Slice T1 should treat this as an estimate and report the
  estimator metadata.
- Required-tool handling can surprise users if a too-small budget makes a node
  fail. The error message must name the required tool and budget reason.
- Prompt-aware lexical scoring can overfit tests. Keep fixtures small and
  deterministic, and prefer conservative fallback over aggressive omission.
- Adding diagnostics to traces can expose sensitive content if done carelessly.
  Diagnostics must be id/reason/count oriented.

## Validation Strategy

Primary commands after implementation:

```bash
poetry run pytest tests/test_validation.py -q
poetry run pytest tests/test_registry.py -q
poetry run pytest tests/test_executor.py -q
poetry run pytest -q
poetry run ruff check src tests
pre-commit run --files \
  src/dynamic_agent_runner/registry.py \
  src/dynamic_agent_runner/executor.py \
  src/dynamic_agent_runner/validation.py \
  src/dynamic_agent_runner/token_budget.py \
  tests/test_registry.py tests/test_executor.py tests/test_validation.py \
  specs/tool-descriptor-budgeting/spec.md \
  specs/tool-descriptor-budgeting/plan.md \
  specs/tool-descriptor-budgeting/tasks.md \
  specs/tool-descriptor-budgeting/validation.md
```

Adjust the final file list to the actual changed files.
