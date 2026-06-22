# Tool Descriptor Budgeting Feature Specification

## Metadata

- Feature slug: `tool-descriptor-budgeting`
- Mode: `light`
- Artifact type: future feature specification / design evaluation
- Status: future prepared feature; NLTK parser work deferred as experiment
- Owner: tool registry plus context-management prepare stage
- Source context:
  - `src/dynamic_agent_runner/registry.py`
  - `src/dynamic_agent_runner/executor.py`
  - `src/dynamic_agent_runner/models.py`
  - `src/dynamic_agent_runner/token_budget.py`
  - `specs/context-management-prepare-stage/spec.md`
  - `specs/semantic-context-profiles/spec.md`
  - `README.md`
  - `pyproject.toml`

## Objective

Define an optional tool descriptor budgeting capability that keeps model tool
schema payloads concise by selecting and packing only the descriptors that are
eligible, relevant, and within a configured token budget.

This specification records the future feature idea only. It does not authorize
implementation yet and does not add an `nltk` dependency.

## Background Analysis

The motivating question was whether an NLTK prompt parser would be useful for
minimizing the tool descriptor load sent to the model so the context window
stays clean and concise.

The analysis found that the useful feature is not specifically an NLTK parser.
The useful feature is a tool descriptor selection and budgeting layer. NLTK
could be one lexical heuristic inside that layer, but it should not be the
primary design center.

Current repository evidence:

- `InMemoryToolRegistry.list_tools_for_node(...)` already filters tools through
  node-local `available_tools`, runtime overrides, disabled tools, and model
  exposure before model calls.
- `InMemoryToolRegistry.to_openai_tools(...)` converts selected registered tools
  into OpenAI function schemas.
- `openai_tool_schema(...)` currently emits the tool id, a
  `description_for_llm` fallback, and normalized `input_schema` parameters.
- `_execute_llm_step(...)` prepares messages first, then derives exposed tool
  schemas when `node.available_tools` is present.
- `prepare_model_input(...)` is the owning seam for prompt and context
  preparation, while tool schema generation remains registry-owned.
- Token estimation already uses `tiktoken`; `nltk` is not currently part of the
  package dependency set.

Implication: a future feature should preserve the existing registry and
prepare-stage boundaries, use deterministic metadata before natural-language
heuristics, and enforce budgets with the package's token-estimation machinery.

## Problem Statement

Workflows with many registered or node-available tools can spend unnecessary
prompt budget on tool descriptors that are irrelevant to the current prompt.
Large descriptor sets can also make the model's tool-choice surface noisy,
especially when several tools have similar names, descriptions, or schemas.

The runtime currently has explicit exposure controls, but once a node lists a
large `available_tools` set, all model-exposable selected tools are converted
into schemas. There is no package-owned selector that can rank tools, enforce a
descriptor budget, or record why descriptors were included or omitted.

## Scope

This feature covers:

1. deterministic tool descriptor budgeting before model request construction
2. optional prompt-aware tool preselection for `llm_step` nodes
3. token-aware packing of OpenAI-compatible tool schemas
4. structured diagnostics for included and omitted tool descriptors
5. conservative fallback behavior when selection confidence is low
6. policy validation under `runtime.execution_policy`
7. fake-testable scoring without live model, embedding, or external parser calls

## Non-Goals

This feature must not introduce:

- a required `nltk` dependency
- runner-owned embeddings, vector stores, or retrieval indexes
- model calls to decide which tool descriptors to include
- live OpenAI, Hugging Face, Marimo, or external tool calls in unit tests
- hidden removal of explicitly required tools
- mutation of the callable registry itself
- changes to direct `tool_use_step` execution semantics

## Proposed Policy Shape

Names are draft. The first implementation should stay smaller than this full
shape if tests prove that fewer controls are enough.

```yaml
runtime:
  execution_policy:
    tool_descriptor_budget:
      enabled: true
      model: gpt-4o-mini
      max_tokens: 1200
      strategy: deterministic_metadata
      low_confidence_behavior: include_all_within_budget
      required_tools:
        - read_file
      max_tools: 8
      diagnostics: redacted
```

Optional node-local override:

```yaml
nodes:
  - id: answer
    kind: llm_step
    available_tools:
      - search_repo
      - read_file
      - web_search
    tool_descriptor_budget:
      max_tokens: 800
      required_tools:
        - search_repo
```

Policy should be opt-in. Existing behavior remains unchanged when no descriptor
budget is configured.

## Proposed Runtime Shape

The likely implementation should introduce a small package-owned `ToolSelector`
near the registry boundary.

Expected flow:

1. `_execute_llm_step(...)` gets exposed tools from
   `registry.list_tools_for_node(node.source_node)` as it does today.
2. If descriptor budgeting is disabled, existing `registry.to_openai_tools(...)`
   behavior remains unchanged.
3. If descriptor budgeting is enabled, `ToolSelector` receives:
   - the prepared prompt messages or a bounded prompt text view
   - the exposed `RegisteredTool` values
   - execution policy and node-local overrides
   - model/token-budget settings
4. `ToolSelector` scores and orders tools using deterministic signals first:
   - exact tool id and label matches
   - `tool_type`
   - `description_for_llm`
   - schema property names and required fields
   - node-local `available_tools` order
   - required-tool policy
5. `ToolSelector` converts candidate tools through the existing
   `openai_tool_schema(...)` path and packs schemas until token or count limits
   are reached.
6. If confidence is low, the configured fallback must be explicit. The safe
   default should include all tools that fit within the budget and fail clearly
   if required tools cannot fit.
7. Prepared input metadata or trace payloads record redacted selection
   diagnostics.

## Functional Requirements

### FR1 - Preserve Existing Behavior by Default

Given a workflow has no tool descriptor budget policy, when an `llm_step`
exposes tools, then the runtime must pass the same model-exposable tool schemas
it passes today.

### FR2 - Respect Registry Exposure First

Given descriptor budgeting is enabled, when tools are selected, then
`ToolSelector` must operate only on tools already returned by
`list_tools_for_node(...)`. It must not expose hidden, disabled, missing, or
non-model-exposable tools.

### FR3 - Keep Required Tools

Given policy marks a tool as required, when descriptor budgeting runs, then that
tool must be included if it is exposed and can fit. If it cannot fit, execution
must fail clearly before making the model request.

### FR4 - Enforce Descriptor Budgets with Token Estimates

Given a descriptor token budget is configured, when schemas are packed, then
the runtime must estimate descriptor tokens with the package token-budget
machinery and omit optional descriptors that would exceed the budget.

### FR5 - Use Deterministic Scoring First

Given prompt-aware selection is enabled, when candidate tools are ranked, then
the first implementation must use deterministic metadata and lexical overlap.
It must not require NLTK, embeddings, or a model call.

### FR6 - Report Omission Reasons

Given optional tool descriptors are omitted, when traces or preparation
metadata are inspected, then diagnostics must report tool ids, inclusion state,
budget totals, and redacted omission reasons such as `over_budget`,
`low_score`, or `policy_removed`.

### FR7 - Fail Conservatively on Ambiguity

Given the selector cannot confidently distinguish tools, when fallback is
needed, then behavior must prefer including more eligible tools within budget or
failing clearly over silently hiding likely relevant tools.

## Acceptance Criteria

- Existing tool-exposure tests pass unchanged when policy is absent.
- New tests prove hidden, disabled, and non-model-exposable tools cannot be
  selected by `ToolSelector`.
- New tests prove required tools are included or fail clearly if they cannot
  fit.
- New tests prove optional tools are omitted when descriptor token limits are
  exceeded.
- New tests prove deterministic prompt/metadata scoring changes selected tools
  on a fixture with several candidate tools.
- Selection diagnostics are redacted and do not include raw prompt content or
  full schemas unless an explicit debug mode is later approved.
- Unit tests use fake tools and local token estimation only.

## NLTK Future Experiment

NLTK work is explicitly future experiment scope, not part of the first feature
slice.

Experiment question: does an NLTK-backed lexical parser materially improve tool
descriptor selection quality over a stdlib deterministic scorer on this
repository's expected workflow prompts?

Experiment constraints:

- run as an optional benchmark or prototype, not production code
- do not add `nltk` to runtime dependencies unless evidence justifies it
- compare against a no-dependency baseline using exact matching, normalization,
  token overlap, and schema-field overlap
- measure descriptor token reduction, selected-tool recall, false omissions,
  runtime overhead, package size, and setup friction
- use fixed local fixtures and no live model or external service calls

Promotion criteria:

- NLTK must improve relevant-tool recall or reduce false omissions enough to
  justify a new optional dependency surface.
- The implementation must be deterministic without downloading corpora at
  runtime.
- Failure modes must degrade to the no-dependency scorer.

## Validation Checklist

- Inspect existing registry and executor boundaries before implementation.
- Add RED tests for default no-op behavior, exposure preservation, required
  tool inclusion, over-budget omission, and diagnostics.
- Run focused registry/executor tests during iteration.
- Run `poetry run pytest tests/test_registry.py -q` and focused executor tests
  before claiming implementation complete.
- Run `graphify update .` after code changes, per repository graph guidance.
