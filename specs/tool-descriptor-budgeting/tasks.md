# Tool Descriptor Budgeting Tasks

## Metadata

- Feature slug: `tool-descriptor-budgeting`
- Status: Slice T1 implemented
- Date: 2026-06-22
- Owning spec: `specs/tool-descriptor-budgeting/spec.md`
- Plan: `specs/tool-descriptor-budgeting/plan.md`

## Slice T1: Opt-In Deterministic Descriptor Budgeting

- [x] T1.1 Add RED validation tests proving
      `runtime.execution_policy.tool_descriptor_budget` must be a mapping when
      present, validates positive integer `max_tokens` and `max_tools`, accepts
      `enabled: false`, and rejects unknown strategies.
- [x] T1.2 Add RED validation tests for node-local `tool_descriptor_budget` on
      `llm_step` nodes and rejection on non-`llm_step` nodes.
- [x] T1.3 Add RED registry/selector tests proving hidden, disabled, missing,
      deferred-only, and non-model-exposable tools cannot be selected.
- [x] T1.4 Add RED selector tests proving required tools are included before
      optional tools and fail clearly when not exposed or unable to fit.
- [x] T1.5 Add RED selector tests proving optional tools are omitted when
      descriptor token limits or `max_tools` limits are reached.
- [x] T1.6 Add RED selector tests proving deterministic prompt and metadata
      scoring prefers matching tool ids, descriptions, schema fields, and
      required-field names over unrelated candidates.
- [x] T1.7 Add RED executor tests proving no policy preserves the current
      `registry.to_openai_tools(...)` behavior and model request shape.
- [x] T1.8 Add RED executor tests proving enabled policy changes only the
      `tools` list passed into `build_openai_request(...)` and fails before
      dispatch for required-tool budget failures.
- [x] T1.9 Add RED tracing or prepared-input metadata tests proving diagnostics
      include selected ids, omitted ids, reasons, token totals, and counts while
      excluding raw prompt content and full descriptors.
- [x] T1.10 Implement policy parsing helpers and validation for runtime and
      node-local descriptor budget metadata.
- [x] T1.11 Implement selector policy/result/diagnostic structures using
      package-owned errors at public execution boundaries.
- [x] T1.12 Implement `ToolSelector` deterministic scoring, required-tool
      enforcement, descriptor conversion through `openai_tool_schema(...)`, and
      token-aware packing.
- [x] T1.13 Integrate `ToolSelector` into `_execute_llm_step_async(...)` after
      `prepare_model_input(...)` and after registry exposure filtering.
- [x] T1.14 Add redacted diagnostics to the existing model-request trace or
      prepared-input metadata path.
- [x] T1.15 Update README/API docs only if implementation exposes user-facing
      policy details beyond the spec.
- [x] T1.16 Run focused validation:
      `poetry run pytest tests/test_validation.py -q`,
      `poetry run pytest tests/test_registry.py -q`, and
      `poetry run pytest tests/test_executor.py -q`.
- [x] T1.17 Run final validation:
      `poetry run pytest -q` and `poetry run ruff check src tests`.
- [x] T1.18 Update this task list, `validation.md`, and the spec index with
      completion evidence after implementation.

## Deferred Follow-Up: Scoring Quality Experiments

- [x] T2.1 Build a local benchmark fixture set with prompts, eligible tools,
      expected required tools, acceptable optional tools, and false-omission
      checks. The evaluator-only contract is validated by
      `tests/test_tool_descriptor_benchmark_fixtures.py`.
- [ ] T2.2 Compare the no-dependency deterministic scorer against an optional
      NLTK-backed lexical scorer without adding NLTK to runtime dependencies.
- [ ] T2.3 Measure descriptor token reduction, selected-tool recall, false
      omissions, runtime overhead, dependency size, and setup friction.
- [ ] T2.4 Promote an optional parser strategy only if benchmark evidence beats
      the deterministic baseline enough to justify the dependency surface.

## Deferred Follow-Up: Policy Polish

- [ ] T3.1 Add additional fallback behaviors only after Slice T1 traces show a
      real need.
- [ ] T3.2 Add capability/status reporting for descriptor budgeting only if
      hosts need preflight visibility.
- [ ] T3.3 Add descriptor compression or summarization only as a separate spec
      after selection/packing behavior is stable.
