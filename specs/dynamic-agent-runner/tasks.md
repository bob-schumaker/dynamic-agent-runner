# dynamic-agent-runner Task List

## Status

- State: E14 Slices I.1 through I.7 are complete; the planned E14 async-first
  implementation and validation slice sequence is complete.
- Source spec: `specs/dynamic-agent-runner/spec.md`
- Technical plan: `specs/dynamic-agent-runner/plan.md`
- Downstream driver:
  `specs/dynamic-agent-runner/references/power-marimo-agent-support-analysis.md`
  identifies `../power-marimo` as the first-customer fit for the next runtime
  capabilities.
- Readiness verdict: ready for the runtime-package simplification follow-up; not
  ready for unrestricted MCP, durable session, approval-resume, or PyQt-widget
  automation work.
- Next active slice: S5 — Power-Marimo runtime-package fixture or example.

## Slice 0 — Planning and documentation readiness checkpoint

- [x] T0.1 Update `spec.md` so its consistency notes acknowledge the follow-on
      `plan.md` and `tasks.md` artifacts.
- [x] T0.2 Keep `plan.md` and `tasks.md` tracked together as the current
      implementation planning artifacts.
- [x] T0.3 Update `README.md` to remove stale `ai-tools-core` wording and align
      with the official `openai` package and repository-owned registry direction.
- [x] T0.4 Keep `pyproject.toml` and `poetry.lock` dependency changes separate
      from documentation/spec commits unless explicitly committing dependency
      state.

## Slice 0 Completion Evidence

- `spec.md` acknowledges `plan.md` and `tasks.md` as follow-on planning artifacts.
- `plan.md` and `tasks.md` are tracked in commit `2979342`.
- `README.md` is aligned with the official `openai` package and
  repository-owned registry direction.
- `pyproject.toml` and `poetry.lock` remain separate uncommitted dependency changes.

## Slice 1 — Package scaffold and dependency alignment

- [x] T1.1 Verify `pyproject.toml` and `poetry.lock` match the latest spec
      direction: official `openai`, no required `ocihelper`, no required
      `ai-tools-core` / `openai-tools-core`.
- [x] T1.2 Create `src/dynamic_agent_runner/__init__.py` with initial public
      exports reserved for the API surface.
- [x] T1.3 Add foundational modules: `errors.py`, `api.py`, and minimal package
      metadata/docstrings.
- [x] T1.4 Create `tests/` and a smoke test that imports `dynamic_agent_runner`.
- [x] T1.5 Confirm `README.md` remains aligned with the official `openai`
      package and repository-owned tool registry direction.
- [x] T1.6 Run `poetry check`, import smoke tests, and targeted pre-commit for
      changed files.

## Slice 1 Completion Evidence

- `pyproject.toml` and `poetry.lock` align with the official `openai`
  package direction and do not require `ocihelper`, `ai-tools-core`, or
  `openai-tools-core`.
- `src/dynamic_agent_runner/` exists with initial public API exports and
  project-specific exception classes.
- `tests/test_import.py` covers the package import smoke test.
- README remains aligned with the official `openai` package and
  repository-owned registry direction.

## Slice 2 — Artifact models and loaders

- [x] T2.1 Define internal models for runtime manifest metadata, documented
      supported pattern IDs, nodes, edges, tools, skills, participant groups,
      modes, phases, roles, output contracts, and validation sections.
- [x] T2.2 Implement runtime YAML loading from path, raw string, and
      already-parsed object inputs.
- [x] T2.3 Implement Mermaid graph loading and `mermaid_diagram` reference
      resolution relative to the runtime YAML path.
- [x] T2.4 Implement optional external `tool-index.yaml` loading from path, raw
      string, and already-parsed object inputs.
- [x] T2.5 Implement lightweight `agent-design.md` loading and reference checks
      for the runtime manifest and Mermaid graph.
- [x] T2.6 Preserve `patterns_present` metadata for the documented supported
      agent pattern IDs without treating patterns as primitive node kinds.
- [x] T2.7 Add fixture-based tests for valid and malformed artifact inputs,
      including at least one metadata-rich pattern shape such as
      `multi-agent-collaboration` or `memory-augmented-agent`.

## Slice 2 Completion Evidence

- `src/dynamic_agent_runner/models.py` defines internal artifact models for
  runtime manifests, nodes, edges, tools, tool indexes, agent designs, and loaded
  workflow bundles.
- `src/dynamic_agent_runner/artifacts.py` loads runtime YAML, Mermaid graph text,
  optional tool indexes, and optional agent design markdown from paths, raw
  strings, or already-parsed mapping inputs.
- `load_agent_workflow(...)` now loads artifacts without executing workflows;
  `run_agent_workflow(...)` remains reserved for later executor slices.
- `PyYAML >=6.0` is declared as a direct runtime dependency for YAML artifact
  loading.
- `tests/test_artifacts.py` covers valid raw-string, path-based, and parsed
  object loading; malformed YAML; missing referenced Mermaid graphs; and
  metadata-rich pattern preservation for `multi-agent-collaboration` and
  `memory-augmented-agent`.

## Slice 3 — Validation engine

- [x] T3.1 Validate required runtime manifest fields: `format_version`,
      `package_type`, `package_id`, `entrypoint`, `packaging`, `nodes`, and
      `edges`.
- [x] T3.2 Validate supported enums for initial scope: `format_version: 1`,
      `package_type: dynamic_agent_design`, observed node kinds, decision
      subtypes, and edge kinds.
- [x] T3.3 Validate node IDs are unique and every edge endpoint references an
      existing node.
- [x] T3.4 Validate every `tool_use_step` references an available manifest or
      external tool-index tool. Superseded for execution by Slice 4 registry
      semantics: callable registry entries are authoritative.
- [x] T3.5 Validate every `llm_step` has prompt data or a prompt source.
- [x] T3.6 Validate external `tool-index.yaml` structure: `format_version`,
      `index_type`, `tools`, and `skills`.
- [x] T3.7 Add tests for clear errors on missing artifacts, malformed schemas,
      unsupported versions, inconsistent nodes, and missing tools.

## Slice 3 Completion Evidence

- `src/dynamic_agent_runner/validation.py` validates required manifest fields,
  supported enum values, node identity, edge references, tool references, LLM
  prompt presence, and external tool-index structure. Slice 4 must reconcile
  this with the clarified registry-authoritative execution semantics.
- `load_agent_workflow(...)` now validates loaded artifacts before returning
  them for later execution slices.
- `tests/test_validation.py` covers passing validation, required-field failures,
  unsupported enum failures, duplicate node IDs, bad edge endpoints, missing
  entrypoints, unknown tool references, missing LLM prompts, and malformed tool
  indexes.

## Slice 4 — Repository-owned tool registry

- [x] T4.1 Define `ToolDefinition`, `RegisteredTool`, `ToolResult`, and a
      `ToolRegistry` protocol.
- [x] T4.2 Implement `InMemoryToolRegistry` for tests and simple callers.
- [x] T4.3 Implement conversion from registry tool definitions to OpenAI tool
      schema.
- [x] T4.4 Implement tool invocation dispatch by manifest `tool_id`.
- [x] T4.5 Preserve side-effect metadata, approval metadata, timeout/retry
      policy, and failure behavior in registry data structures.
- [x] T4.6 Add runtime tool overrides for adding, replacing, disabling, and
      restricting or extending tools globally or per `llm_step` without mutating
      generated agent-design artifacts.
- [x] T4.7 Validate override consistency, including unknown base tools,
      malformed added tools, disabled tools still required by `tool_use_step`
      nodes, and overrides targeting non-`llm_step` nodes.
- [x] T4.8 Reconcile validation so `tool_use_step` execution dependencies must
      resolve to the effective callable registry; manifest and `tool-index.yaml`
      entries are metadata and do not make a tool callable by themselves.
- [x] T4.9 Add opt-in built-in default tool-pack support, starting with a
      read-only `local_workspace` pack for `read_file`, `list_files`,
      `search_files`, and `inspect_path` constrained to approved workspace roots.
- [x] T4.10 Keep write and command tools out of the default enabled set; if
      introduced, model them as separate opt-in approval-aware packs.
- [x] T4.11 Add tests for lookup, schema conversion, successful invocation,
      missing tools, bad inputs, and tool failures.
- [x] T4.12 Add tests for override layering, effective registry additions,
      replacement definitions, disabled tools, and per-node tool exposure.
- [x] T4.13 Add tests for built-in pack enablement, disabled-by-default behavior,
      workspace path restrictions, and node-reference requirements.

## Slice 4 Completion Evidence

- `src/dynamic_agent_runner/registry.py` defines the repository-owned registry
  protocol, `RegisteredTool`, `ToolResult`, runtime override models,
  `InMemoryToolRegistry`, OpenAI tool schema conversion, registry invocation,
  registry-authoritative tool reference validation, and the opt-in read-only
  `local_workspace` built-in tool pack.
- `src/dynamic_agent_runner/validation.py` accepts an optional callable registry
  during workflow validation so `tool_use_step` dependencies can be checked
  against executable registry entries instead of metadata-only tool-index entries.
- `load_agent_workflow(...)` accepts an optional `tool_registry` for validation
  while still avoiding workflow execution.
- `tests/test_registry.py` covers lookup, OpenAI schema conversion, invocation,
  missing tools, bad inputs, tool failures, runtime override layering,
  disabled-tool validation, registry-authoritative tool references,
  built-in pack enablement, workspace path restrictions, and node-reference
  requirements.

## Slice 5 — OpenAI client adapter

- [x] T5.1 Define the runtime's minimal OpenAI client protocol for injected
      fake/stub clients.
- [x] T5.2 Implement the default adapter using the official `openai` Python
      package.
- [x] T5.3 Implement request construction for rendered messages and optional
      OpenAI tool schemas.
- [x] T5.4 Normalize model responses into internal result/event structures.
- [x] T5.5 Surface OpenAI/model failures as project-specific errors.
- [x] T5.6 Add tests using fake clients only; no live API calls in unit tests.

## Slice 5 Completion Evidence

- `src/dynamic_agent_runner/openai_client.py` defines the runtime's minimal
  OpenAI client protocol, request and response dataclasses, lazy default OpenAI
  client construction, and `OpenAIClientAdapter` for the official Responses API
  boundary.
- `build_openai_request(...)` constructs model requests from rendered messages,
  optional OpenAI tool schemas, tool choice, response format, and extra model
  parameters.
- `normalize_openai_response(...)` extracts model text and function-tool calls
  into internal `ModelResponse` and `ModelToolCall` structures.
- Adapter failures are wrapped in `ModelExecutionError` so callers see
  project-specific model errors.
- `tests/test_openai_client.py` uses fake clients only and covers request
  construction, injected-client execution, response normalization, error
  wrapping, and input validation.

## Slice 6 — Workflow executor

- [x] T6.1 Implement execution state for prompt, node inputs, node outputs,
      tool results, final result, and errors.
- [x] T6.2 Implement `llm_step` prompt rendering and model-call execution.
- [x] T6.3 Implement `tool_use_step` input resolution, registry dispatch, output
      recording, and configured failure behavior.
- [x] T6.4 Implement `decision_step` with `decision_subtype: llm_route`.
- [x] T6.5 Implement `sequential` and `branch` control-flow edges.
- [x] T6.6 Fail clearly for unsupported node kinds, decision subtypes, or edge
      semantics.
- [x] T6.7 Add fake-client/fake-tool end-to-end tests for successful workflow,
      partial failure, and final-result return behavior.

## Slice 6 Completion Evidence

- `src/dynamic_agent_runner/executor.py` defines workflow execution state,
  execution records, final result objects, and `execute_workflow(...)`.
- `llm_step` execution renders prompt templates, exposes node tools through the
  registry-to-OpenAI schema path, and calls the Slice 5 OpenAI adapter boundary.
- `tool_use_step` execution resolves inputs, dispatches through the Slice 4
  registry, records structured tool results, and honors error/fallback failure
  behavior.
- `decision_step` with `decision_subtype: llm_route` extracts a route from model
  or JSON-like output and follows matching branch edges.
- Sequential and branch control-flow edges are implemented; unsupported node,
  decision, and edge configurations fail with `WorkflowExecutionError`.
- `run_agent_workflow(...)` now loads, validates, executes, and returns the final
  workflow result while `execute_workflow(...)` remains available for detailed
  state inspection.
- `tests/test_executor.py` uses fake clients and fake tools only and covers
  successful workflow execution, tool failure behavior, branch routing, public
  API final-result behavior, and step-limit failures.

## Slice 7 — CLI and documentation

- [x] T7.1 Add a CLI entry point for loading artifacts and running a workflow
      from a prompt.
- [x] T7.2 Support CLI options for `agent-design.md`, runtime YAML, Mermaid
      graph, optional `tool-index.yaml` metadata, registry configuration, and
      prompt input.
- [x] T7.3 Return final output on success and clear non-zero errors on loading,
      validation, registry, model, or execution failure.
- [x] T7.4 Add CLI tests using local fixtures and fake clients/tools.
- [x] T7.5 Update README with concrete API and CLI usage.
- [x] T7.6 Run full available validation and update memory bank after the first
      meaningful implementation milestone.

## Slice 7 Completion Evidence

- `src/dynamic_agent_runner/cli.py` defines `main(...)`, `build_parser()`, and
  `console_main()` for running generated workflow artifacts from the command
  line.
- `pyproject.toml` exposes the `dynamic-agent-runner` console script.
- CLI options cover runtime manifest, agent design, Mermaid graph, optional tool
  index metadata, prompt text, prompt file, stdin prompt input, max steps, and
  the opt-in read-only local workspace registry pack via `--workspace-root`.
- The CLI prints the final workflow result to stdout and reports runtime-specific
  errors to stderr with exit code `1`.
- `tests/test_cli.py` uses local fixture artifacts and fake OpenAI clients only;
  it covers path-based execution, prompt-file input, stdin input, missing prompt
  errors, and execution error reporting.
- `README.md` now documents concrete Python API and CLI usage.

## Slice 8 — Retry and resilience policy

- [x] T8.1 Add a small package-owned retry policy model for model calls and tool
      calls, preserving fail-closed behavior when no retry policy is configured.
- [x] T8.2 Add Tenacity-backed bounded retry execution for retryable OpenAI/model
      failures behind the existing OpenAI adapter boundary.
- [x] T8.3 Add bounded retry execution for retryable tool invocation failures
      using registry/tool policy metadata.
- [x] T8.4 Record retry attempt count, final failure reason, and final outcome in
      execution state or trace data.
- [x] T8.5 Add tests for retryable failures, non-retryable failures, retry limit
      exhaustion, and default no-retry behavior using fake clients/tools only.
- [x] T8.6 Update README or usage notes only if a new public API or CLI option is
      introduced.

## Slice 8 Completion Evidence

- `src/dynamic_agent_runner/retry.py` defines package-owned `RetryPolicy` and
  `RetryRecord` models plus Tenacity-backed bounded retry execution helpers.
- `execute_workflow(...)` records retry outcomes in
  `WorkflowExecutionState.retry_records` for model and tool call sites.
- Model retry policy can come from node `retry_policy`, manifest
  `execution_policy.model_retry_policy`, or manifest
  `execution_policy.retry_policy`.
- Tool retry policy can come from node `retry_policy` or callable registry tool
  definition metadata.
- Default behavior remains one attempt with fail-closed error propagation when no
  retry policy is configured.
- `tests/test_executor.py` covers retryable model failures, non-retryable model
  failures, model retry exhaustion, retryable tool failures, non-retryable tool
  failures, tool retry exhaustion, and default no-retry behavior using fake
  clients and fake tools only.
- `README.md` documents retry metadata and retry outcome recording.

## Slice 9 — Output contracts and route validation

- [x] T9.1 Define how manifest `output_contracts` map to runtime validation for
      model outputs.
- [x] T9.2 Validate required output fields for `llm_step` results before storing
      them as trusted node state.
- [x] T9.3 Tighten `decision_step` / `llm_route` validation so malformed routes
      or routes outside declared branch conditions fail clearly.
- [x] T9.4 Keep model-assisted repair or Instructor-style retry behavior out of
      scope unless explicitly introduced by a later spec update.
- [x] T9.5 Add tests for valid output contracts, malformed model output,
      malformed route output, and unknown route values.

## Slice 9 Completion Evidence

- `execute_workflow(...)` validates `llm_step` `output_schema_ref` declarations
  against `runtime_manifest.output_contracts` before storing model output as
  trusted node state.
- Output contract required fields are validated against JSON object model output
  or adapter-provided structured output. Plain text remains accepted only for the
  fixture-compatible single-field `message` contract.
- `decision_step` nodes with `decision_subtype: llm_route` now validate extracted
  routes against `decision_contract.allowed_paths` when that contract is present.
- Malformed route output and routes outside declared allowed paths fail clearly
  before branch traversal.
- Model-assisted repair or Instructor-style retry behavior remains out of scope.
- `tests/test_executor.py` covers valid output contracts, missing fields,
  unstructured model output, unknown output contracts, malformed route output,
  and unknown route values.
- `tests/test_cli.py` fixture fake responses now satisfy the declared
  `hello_message` contract while still exercising route extraction.
- `README.md` documents current output-contract and route-validation behavior.

## Slice 10 — Token budgeting and context preflight

- [x] T10.1 Add optional token-estimation support for rendered OpenAI messages,
      using `tiktoken` as the preferred implementation dependency.
- [x] T10.2 Add a token-budget policy model that can be configured per workflow,
      model, or call site without changing generated artifacts.
- [x] T10.3 Fail clearly, or apply an explicitly configured truncation policy,
      when rendered messages exceed configured limits.
- [x] T10.4 Add CLI/debug reporting for estimated token counts only if it can be
      done without live model calls.
- [x] T10.5 Add tests for token estimation, over-budget failure, disabled-budget
      pass-through behavior, and unknown-model fallback behavior.

## Slice 10 Completion Evidence

- `src/dynamic_agent_runner/token_budget.py` defines package-owned
  `TokenBudgetPolicy`, `TokenUsageRecord`, and `TokenEstimate` models plus
  `tiktoken`-backed prompt-token estimation.
- `execute_workflow(...)` runs token preflight for `llm_step` nodes when
  node-level or manifest-level `token_budget` / `token_budget_policy` metadata is
  configured.
- Default behavior remains pass-through with no token estimation and no model
  request blocking when no token budget is configured.
- Over-budget prompts fail clearly before the OpenAI adapter is called.
- Token estimates are recorded in `WorkflowExecutionState.token_usage`, including
  model, estimated prompt tokens, configured budget, encoding name,
  fallback-encoding flag, and exceeded status.
- Unknown models fall back to `cl100k_base` and record the fallback flag.
- Automatic truncation remains unsupported; unsupported `on_exceed` policies fail
  clearly if the budget is exceeded.
- `tests/test_token_budget.py` covers token estimation, unknown-model fallback,
  policy parsing, disabled policy behavior, and invalid policy values.
- `tests/test_executor.py` covers budget-enabled execution, over-budget failure
  before model call, and disabled-budget pass-through behavior.
- `README.md` documents token-budget configuration and token-usage recording.

## Slice 11 — Execution tracing and observability hooks

- [x] T11.1 Define a package-owned trace event model for node start/completion,
      model request/response, tool invocation, retry, decision, error, and final
      result events.
- [x] T11.2 Add an optional trace sink interface that can receive events without
      requiring external observability dependencies.
- [x] T11.3 Ensure trace data can later support redaction of prompt, model, tool,
      and result fields before external emission.
- [x] T11.4 Add tests that trace events are emitted in expected order for
      successful workflows, tool failures, model failures, and retry attempts.
- [x] T11.5 Defer Logfire/OpenTelemetry integration until the package-owned trace
      interface is stable.

## Slice 11 Completion Evidence

- `src/dynamic_agent_runner/tracing.py` defines package-owned `TraceEvent`,
  `TraceSink`, `InMemoryTraceSink`, and `WorkflowTracer` primitives with no
  external observability dependency.
- `execute_workflow(...)` records ordered events in
  `WorkflowExecutionState.trace_events` and accepts an optional `trace_sink`
  for live event delivery.
- Trace events cover workflow start/completion, node start/completion, model
  request/response, token-budget checks, tool invocation/result, retry
  records, decisions, node errors, workflow errors, and final results.
- `TraceEvent.redacted_payload()` and `TraceEvent.redacted()` support shallow
  redaction of prompt, request, model content, tool arguments, tool outputs,
  node outputs, and final-result fields before external emission.
- `run_agent_workflow(...)` forwards an optional trace sink while continuing
  to return the final result.
- `tests/test_tracing.py` covers successful workflows, tool failures, model
  failures, and retry-attempt tracing with fake clients/tools only.
- Logfire/OpenTelemetry integration remains deferred until the package-owned
  trace interface is stable.

## Slice 12 — Runtime behavior overrides for prompts and skills

- [x] T12.1 Add runtime behavior override models for prompt patch operations,
      skill definition overlays, and per-node skill binding changes.
- [x] T12.2 Load optional behavior override artifacts from path, raw YAML, and
      already-parsed mapping inputs without mutating generated artifacts.
- [x] T12.3 Preserve optional `skill_refs` metadata on `llm_step` nodes and
      validate referenced skills against the effective skill catalog.
- [x] T12.4 Validate override targets, prompt operations, and skill binding
      operations so invalid overrides fail before execution.
- [x] T12.5 Compute effective `llm_step` prompt and skill behavior at execution
      time while leaving `RuntimeNode.raw` and loaded artifacts unchanged.
- [x] T12.6 Support inline skill instructions and prompt roles in initial scope;
      defer arbitrary `SKILL.md` source-path resolution.
- [x] T12.7 Add API and CLI inputs for runtime behavior overrides.
- [x] T12.8 Add tests for loading, validation, prompt replacement/prepend/append,
      skill binding add/remove/only, node isolation, artifact immutability, and
      invalid override failures.

## Slice 12 Completion Evidence

- `src/dynamic_agent_runner/models.py` defines runtime behavior override models
  for prompt `replace` / `prepend` / `append`, skill definition overlays, and
  per-node skill binding `add` / `remove` / `only` operations.
- `src/dynamic_agent_runner/artifacts.py` loads optional runtime behavior
  overrides from paths, raw YAML strings, and already-parsed mappings.
- `RuntimeNode` preserves optional `skill_refs` metadata while keeping raw
  manifest data unchanged.
- `src/dynamic_agent_runner/behavior.py` derives effective prompt and skill
  behavior without mutating loaded generated artifacts.
- `src/dynamic_agent_runner/validation.py` validates override versions, target
  node existence, `llm_step` scoping, prompt operations, skill references, and
  effective prompts before execution.
- `execute_workflow(...)` renders effective prompts and inline skill
  instructions, including prompt-role placement, during `llm_step` execution.
- `load_agent_workflow(...)`, `run_agent_workflow(...)`, and the CLI accept
  optional runtime behavior override inputs.
- `tests/test_artifacts.py`, `tests/test_validation.py`,
  `tests/test_executor.py`, and `tests/test_cli.py` cover loading, validation,
  prompt replacement/prepend/append, skill add/remove/only, node isolation,
  artifact immutability, CLI input wiring, and invalid override failures.
- Validation run: `ruff check src tests && ruff format --check src tests &&
  pytest -q` — pass; 93 tests passed.

## Slice 13 — Prompt-cache intent and trace observation

- [x] T13.1 Parse and preserve optional `execution_policy.prompt_cache` metadata
      as provider-neutral cache intent without requiring it for existing
      manifests.
- [x] T13.2 Validate prompt-cache metadata shape, including `enabled`,
      `strategy`, `min_prefix_tokens`, `prefix_parts`, `variable_parts`,
      `cache_key_hint`, and optional `provider_hints`.
- [x] T13.3 Preserve declared stable-prefix ordering during message rendering
      when doing so does not change prompt semantics.
- [x] T13.4 Reuse existing token-budget estimation to compute stable-prefix token
      estimates and clearly record when estimation is unavailable.
- [x] T13.5 Emit trace/debug evidence for cache eligibility, rendered
      stable-prefix part names, prefix token estimate, prefix hash, first
      variable part, caller override status, and adapter fallback status.
- [x] T13.6 Allow runtime callers to disable or override prompt-cache behavior
      per execution request before any provider-specific behavior is applied.
- [x] T13.7 Keep provider-specific cache pass-through adapter-gated and add it
      only after SDK/API support is verified.
- [x] T13.8 Record observed cached-token usage, cache-read status, or equivalent
      provider response metadata when the provider exposes it.
- [x] T13.9 Add tests for disabled, enabled-but-ineligible, eligible,
      override-disabled, invalid metadata, unsupported prompt part names,
      `x-` extension part names, provider-hint behavior, missing token-estimator
      behavior, and missing provider cache telemetry behavior.

## Slice 13 Completion Evidence

- `src/dynamic_agent_runner/prompt_cache.py` defines provider-neutral
  `PromptCachePolicy` parsing and prompt-cache eligibility observation helpers.
- `src/dynamic_agent_runner/validation.py` validates optional
  `execution_policy.prompt_cache` metadata and fails closed for malformed
  policy shape.
- `src/dynamic_agent_runner/executor.py` preserves rendered message part names,
  emits `prompt_cache_checked` trace events, supports per-execution
  `prompt_cache=False` overrides, and records provider cached-token telemetry
  when exposed by the model response.
- `src/dynamic_agent_runner/api.py` forwards the optional `prompt_cache` runtime
  execution override.
- `tests/test_prompt_cache.py` covers parsing, invalid metadata, eligible and
  ineligible prefixes, override-disabled behavior, `x-` extension part names,
  missing token-estimator behavior, and provider cached-token telemetry.
- Validation run: `ruff check src tests && ruff format --check src tests &&
  python -m pytest -q` — pass; 104 tests passed.

## Runtime-package simplification follow-up

Driver reference:
`specs/dynamic-agent-runner/references/power-marimo-agent-support-analysis.md`
shows that the first downstream candidate needs grouped manifest support,
preparation seams, and tool provenance before safe Marimo notebook automation.

- [x] S1. Update manifest models and validation to prefer grouped `runtime`,
      `metadata`, and `extensions` maps, parse `output_contracts` as an array of
      contract objects, and reject or clearly report legacy flat optional root
      fields.
      - Completed in commit `695c0cc`: `RuntimeManifest` now preserves grouped
        maps, derives convenience accessors from grouped sections, indexes
        array-shaped `output_contracts`, validates extension envelopes, and
        rejects legacy flat optional root fields.
      - Validation: `poetry run pytest -q` — pass; 164 tests passed.
      - Pre-commit: `pre-commit run --files <S1 changed files>` — pass.
- [x] S2. Add an internal `ExecutionPlan` / `PreparedNode` normalization layer so
      the executor consumes normalized per-node configuration instead of raw
      manifest dictionaries.
      - Completed in commit `b315c96`: added internal `ExecutionPlan` and
        `PreparedNode` models plus `prepare_execution_plan(...)`, resolved node
        lookup, outgoing-edge indexes, max-step defaults, per-node model/tool/
        decision fields, output-contract references, token/retry policy values,
        and optional unsupported extension visibility during preparation.
      - The executor now routes finite graph execution through prepared nodes
        while preserving public API behavior and existing workflow semantics.
      - RED: `poetry run pytest
        tests/test_executor.py::test_prepare_execution_plan_resolves_node_indexes_and_defaults
        -q` — failed because `prepare_execution_plan` did not exist yet.
      - GREEN: same targeted test — pass; 1 test passed.
      - Targeted validation: `poetry run pytest tests/test_executor.py
        tests/test_validation.py tests/test_registry.py -q` — pass; 78 tests
        passed.
      - Full validation: `poetry run pytest -q` — pass; 165 tests passed.
      - Pre-commit: `pre-commit run --files src/dynamic_agent_runner/models.py
        src/dynamic_agent_runner/executor.py tests/test_executor.py` — pass after
        Ruff Format rewrote `src/dynamic_agent_runner/executor.py` once.
      - Note: the planning note listed `tests/test_behavior.py`, but that file is
        not present; S2 validation used existing executor, validation, and registry
        tests instead.
- [x] S3. Add a pass-through `prepare_model_input(...)` / `PreparedModelInput`
      seam before expanding context-management, session pruning, hierarchical
      prompt injection, or Marimo notebook-state context injection.
      - Completed in commit `33096b5`: `PreparedModelInput` captures rendered
        messages and named prompt parts, and `prepare_model_input(...)`
        centralizes prompt rendering, prompt-cache observation, token-budget
        preflight, and behavior override integration for `llm_step` execution
        while preserving current prompt semantics.
      - RED: `poetry run pytest
        tests/test_executor.py::test_prepare_model_input_renders_messages_and_named_parts
        -q` — failed because `prepare_model_input` did not exist yet.
      - GREEN: same targeted test — pass; 1 test passed.
      - Focused validation: `poetry run pytest
        tests/test_executor.py::test_prepare_model_input_renders_messages_and_named_parts
        tests/test_executor.py::test_execute_workflow_records_token_usage_when_budget_enabled
        tests/test_prompt_cache.py::test_prompt_cache_trace_records_eligibility_and_prefix_evidence
        -q` — pass; 3 tests passed.
      - Targeted validation: `poetry run pytest tests/test_executor.py
        tests/test_prompt_cache.py tests/test_token_budget.py tests/test_tracing.py
        -q` — pass; 62 tests passed.
      - Full validation: `poetry run pytest -q` — pass; 166 tests passed.
      - Pre-commit: `pre-commit run --files
        src/dynamic_agent_runner/executor.py tests/test_executor.py` — pass after
        replacing an unnecessary dict comprehension flagged by Ruff.
- [x] S4. Add `ToolSource` provenance metadata before MCP, Marimo-session,
      domain-SDK, or agent-as-tool registry sources are implemented.
      - Completed in commit `a46bb5a` (`feat(registry): add tool source
        provenance`).
      - Added `ToolSource` / `ToolSourceKind` metadata for manifest declarations,
        external tool-index entries, built-in local workspace tools, runtime
        overrides, and caller-registered tools.
      - Model-request traces now include diagnostic `tool_sources` metadata for
        model-exposed tools without changing callable dispatch or exposure rules.
      - RED: `poetry run pytest
        tests/test_registry.py::test_tool_definition_records_manifest_and_index_source_metadata
        tests/test_registry.py::test_runtime_overrides_add_replace_disable_and_restrict_per_node
        tests/test_registry.py::test_local_workspace_tool_pack_is_opt_in_and_path_restricted
        -q` — failed because `ToolSource` did not exist yet.
      - RED: `poetry run pytest
        tests/test_tracing.py::test_model_request_trace_includes_model_exposed_tool_sources
        -q` — failed because model-request traces did not include
        `tool_sources`.
      - GREEN: `poetry run pytest
        tests/test_tracing.py::test_model_request_trace_includes_model_exposed_tool_sources
        tests/test_registry.py::test_tool_definition_records_manifest_and_index_source_metadata
        tests/test_registry.py::test_runtime_overrides_add_replace_disable_and_restrict_per_node
        tests/test_registry.py::test_local_workspace_tool_pack_is_opt_in_and_path_restricted
        -q` — pass; 4 tests passed.
      - Targeted validation: `poetry run pytest tests/test_registry.py
        tests/test_tracing.py tests/test_validation.py -q` — pass; 49 tests
        passed.
      - Full validation: `poetry run pytest -q` — pass; 168 tests passed.
      - Pre-commit: `pre-commit run --files src/dynamic_agent_runner/models.py
        src/dynamic_agent_runner/registry.py src/dynamic_agent_runner/executor.py
        tests/test_registry.py tests/test_tracing.py` — pass.
- [ ] S5. Draft a narrow `power-marimo` runtime-package fixture or example as a
      supervised, bounded workflow-orchestration agent using primitive nodes and
      placeholder Marimo/domain tool definitions.
      - Next active slice.

## Deferred library-evaluation follow-ups

- [ ] D1. Revisit Rich only when CLI UX/debug output needs structured tables,
      trees, or colorized output.
- [ ] D2. Revisit Diskcache only when a concrete model/tool/result caching policy
      is specified, including side-effect and staleness semantics.
- [ ] D3. Revisit LiteLLM only if the runtime direction changes from
      OpenAI-first to multi-provider model routing.
- [ ] D4. Keep Watchfiles out of core runtime scope; consider only as a local dev
      helper if prompt/artifact hot-reload workflows become valuable.

## Deferred Codex/Cline evaluation follow-ups

- [x] E1. Introduce a `WorkflowExecutionContext` / `RunContext` object separate
      from mutable `WorkflowExecutionState`.
      - Implemented in commit `38929f1`: added
        `src/dynamic_agent_runner/context.py`, exported `RunContext`, and allowed
        `execute_workflow(...)` / `run_agent_workflow(...)` to accept the context
        while rejecting ambiguous duplicate runtime arguments.
      - Validation: `ruff check src tests && ruff format --check src tests &&
        python -m pytest -q` — pass; 108 tests passed.
- [x] E2. Add a lightweight `ModelCapabilities` model for context window,
      structured-output support, reasoning support, modalities, and parallel
      tool-call support.
      - Implemented in commit `13c6dac`: added `ModelCapabilities`, parsed
        runtime `execution_policy.model_capabilities` into `RuntimeManifest`, and
        exported the metadata model publicly.
      - Capability metadata is preserved for inspection without being passed
        through as OpenAI request parameters.
      - Validation: `ruff check src tests && ruff format --check src tests &&
        python -m pytest -q` — pass; 132 tests passed.
- [x] E3. Strengthen tool input-schema validation for OpenAI-compatible
      object-shaped function schemas.
      - Implemented in commit `44b0847`: added a shared registry schema
        normalization path for OpenAI tool exposure and invocation validation.
      - The registry now rejects malformed `input_schema` values, non-object
        schemas, non-mapping `properties`, non-list or non-string `required`
        entries, and unsupported top-level `oneOf` / `anyOf` / `allOf`.
      - Model-facing OpenAI tool parameters now omit top-level `$schema` metadata.
      - Validation: `ruff check src tests && ruff format --check src tests &&
        python -m pytest -q` — pass; 116 tests passed.
- [x] E4. Add explicit tool exposure states: `direct`, `deferred`,
      `direct_model_only`, and `hidden`.
      - Implemented in commit `61f1548`: added `ToolExposure`, model-facing
        exposure filtering, direct-tool callable checks, and fail-closed unknown
        exposure validation.
      - Validation: `ruff check src tests && ruff format --check src tests &&
        python -m pytest -q` — pass; 121 tests passed.
- [x] E5. Clarify separation between tool catalog metadata, callable registry
      entries, node exposure, approval policy, and sandbox/side-effect policy.
      - Implemented in commit `61f1548`: added `ToolPolicy` to preserve
        side-effect, approval, sandbox, timeout, retry, and failure metadata
        separately from callable registry entries and node exposure decisions.
      - Validation: `python -m pytest tests/test_registry.py
        tests/test_validation.py tests/test_import.py -q` — pass; 34 tests
        passed.
- [x] E6. Refine `ToolResult` into model-facing output, raw output,
      trace/log preview, and hook/event payload facets.
      - Implemented in commit `815f55a`: extended `ToolResult` with
        `model_output`, `raw_output`, `log_preview`, `event_payload`, and
        `sensitive_fields` while preserving `output` fallback behavior.
      - The registry now preserves structured `ToolResult` objects returned by
        tool handlers, and the executor uses model-facing output for prompt/state
        references while emitting raw/log/event facets in tool-result traces.
      - Validation: `ruff check src tests && ruff format --check src tests &&
        python -m pytest -q` — pass; 123 tests passed.
- [x] E7. Define narrow in-process lifecycle hook protocols for model, tool,
      node, permission, and workflow boundaries.
      - Implemented in commit `bf18554`: added `WorkflowLifecycleHooks`, stable
        hook context objects, execution-context/API wiring, and executor calls for
        node, model, tool, and workflow lifecycle points.
      - `PermissionHookContext` is exported as the reserved permission-boundary
        context shape, while active controls remain limited to trusted Python
        hooks that may raise project errors to abort execution.
      - Validation: `ruff check src tests && ruff format --check src tests &&
        python -m pytest -q` — pass; 129 tests passed.
- [x] E8. Extend trace vocabulary for tool lifecycle, usage updates, status
      notices, and future permission/context-management events.
      - Implemented in commit `bcd76d4`: added `tool_started` and
        `tool_finished` events around direct tool invocation while preserving the
        existing `tool_invocation` and `tool_result` compatibility events.
      - The executor now emits warning `status_notice` events for fallback tool
        failures with stable code, message, tool id, and error detail.
      - Validation: `ruff check src tests && ruff format --check src tests &&
        python -m pytest -q` — pass; 125 tests passed.
- [ ] E9. Draft MCP registry-source support with server provenance, visibility,
      status, tool cache, disabled state, operation locking, and memory-pollution
      metadata.
- [ ] E10. Add a context-management prepare-stage design for future compaction
      policies while preserving current fail-closed token-budget behavior.
- [ ] E11. Consider hierarchical file-backed prompt context only with explicit
      roots, source tracking, scan limits, and token/byte budgets.
- [ ] E12. Keep multi-agent collaboration represented through primitive nodes and
      optional delegation tools; defer durable team runtime until requirements
      justify it.
- [x] E13. Define and validate the package's thread-safety and concurrent
      invocation contract for multiple client-created agents.
      - Implemented in commit `2e45888`: added per-run `run_id` generation and
        caller-provided `run_id` support through `execute_workflow(...)` and
        `run_agent_workflow(...)`.
      - `TraceEvent` and lifecycle hook context objects now carry run-correlation
        metadata so interleaved runs can be distinguished in shared observability
        surfaces.
      - `InMemoryTraceSink`, `WorkflowTracer`, `OpenAIClientAdapter` lazy default
        client initialization, and `InMemoryToolRegistry` read/mutation helpers
        now use synchronization for shared QThread-style callers. Tool handlers
        and lifecycle hook implementations remain responsible for synchronizing
        their own mutable internal state.
      - Validation: `poetry run pytest -q && poetry run python -m compileall -q
        src tests && pre-commit run --files src/dynamic_agent_runner/api.py
        src/dynamic_agent_runner/executor.py src/dynamic_agent_runner/hooks.py
        src/dynamic_agent_runner/openai_client.py
        src/dynamic_agent_runner/registry.py src/dynamic_agent_runner/tracing.py
        tests/test_concurrency.py tests/test_hooks.py` — pass; 136 tests
        passed.
- [x] E14. Implement async-first execution APIs and sync wrapper behavior without
      creating a separate runtime implementation.
      - Detailed implementation plan: `cline-tasks/evaluation-follow-up-implementation-plan.md`.
      - Slice I.1 async OpenAI client boundary completed in commit `acca9da`:
        added async OpenAI protocol types, `AsyncOpenAIClientAdapter`,
        `create_default_async_openai_client()`, package exports, and fake-client
        tests while keeping request construction and response normalization shared.
      - Slice I.2 async retry helper completed in commit `f2296e9`: added
        `run_with_retry_async(...)`, exported it publicly, preserved retry attempt
        counts, and ensured `asyncio.CancelledError` propagates without retry.
      - Slice I.3 callable-shape metadata for tools completed in commit
        `ff144f5`: added `RegisteredTool.handler_is_async`,
        `invoke_tool_async(...)`, awaited async handlers, and `asyncio.to_thread(...)`
        dispatch for sync handlers in the async registry path.
      - Slice I.4 callable-shape metadata for lifecycle hooks completed in commit
        `2b9271b`: added `RegisteredLifecycleHook`, recorded configured hook
        callable shape in `WorkflowLifecycleHooks`, added
        `invoke_lifecycle_hook_async(...)`, exported hook metadata/dispatch helpers,
        and awaited async hooks from the current synchronous executor
        compatibility path when no event loop is already running.
      - Slice I.5 async executor core completed in commit `72c28dd`: added
        `execute_workflow_async(...)`, async workflow/node helpers, awaited async
        model calls, awaited async direct tool dispatch, awaited lifecycle hook
        dispatch, and a sync-path guard for async model adapters.
      - Slice I.6 public async API and sync wrappers completed in commit
        `4f279ff`: added `run_agent_workflow_async(...)`, exported
        `execute_workflow_async(...)` and `run_agent_workflow_async(...)`,
        converted sync public entry points into wrappers over the async semantic
        path, and made sync wrappers reject already-running event loops with
        `WorkflowExecutionError`.
      - Slice I.7 cancellation and concurrent async validation completed in commit
        `7990503`: added cancellation, concurrent async run-correlation, and
        sync/async public entry-point parity tests in `tests/test_concurrency.py`.
      - Slice I.1 validation: `poetry run pytest tests/test_import.py
        tests/test_openai_client.py -q` — pass; 11 tests passed.
      - Slice I.1 pre-commit: `pre-commit run --files
        src/dynamic_agent_runner/openai_client.py src/dynamic_agent_runner/__init__.py
        tests/test_openai_client.py` — pass.
      - Slice I.2 validation: `poetry run pytest tests/test_retry.py
        tests/test_executor.py tests/test_import.py -q` — pass; 32 tests passed.
      - Slice I.2 pre-commit: `pre-commit run --files
        src/dynamic_agent_runner/retry.py src/dynamic_agent_runner/__init__.py
        tests/test_retry.py` — pass.
      - Slice I.3 validation: `poetry run pytest tests/test_registry.py
        tests/test_validation.py tests/test_import.py -q` — pass; 39 tests passed.
      - Slice I.3 pre-commit: `pre-commit run --files
        src/dynamic_agent_runner/registry.py tests/test_registry.py` — pass.
      - Slice I.4 validation: `poetry run pytest tests/test_hooks.py
        tests/test_executor.py tests/test_import.py -q` — pass; 39 tests passed.
      - Slice I.4 pre-commit: `pre-commit run --files
        src/dynamic_agent_runner/hooks.py src/dynamic_agent_runner/executor.py
        src/dynamic_agent_runner/__init__.py tests/test_hooks.py
        tests/test_import.py` — pass.
      - First-class async public APIs `execute_workflow_async(...)` and
        `run_agent_workflow_async(...)` are available for event-loop callers.
      - Synchronous APIs for CLI, scripts, tests, cron jobs, and simple automation
        now wrap the async semantic path.
      - Sync wrappers raise a clear project error when called from an
        already-running event loop, directing callers to the async APIs.
      - Use one async-canonical model-client protocol and verify native OpenAI
        async behavior from official SDK documentation/source before
        implementation; use
        the local Obsidian note titled
  `How make async calls to OpenAI’s API in Python  Medium.md`
        only as supporting guidance for the expected `openai.AsyncOpenAI` /
        awaited-call shape.
      - Adapt sync-only model clients behind the async protocol when needed rather
        than adding a separate sync executor protocol.
      - Inspect sync/async tool-handler callable shape at registration or setup
        time and dispatch each handler correctly during async execution.
      - Inspect sync/async lifecycle hook callable shape at setup time and invoke
        or await each hook correctly during async execution.
      - Implement best-effort cancellation propagation across workflow, node,
        model, tool, hook, registry, and child-task boundaries; document
        non-cancellable sync or external boundaries honestly.
      - Update the E13 concurrent invocation contract for async consistency:
        concurrent async runs must preserve per-run state isolation, `run_id`
        metadata, trace correlation, hook correlation, and synchronized
        package-owned shared helpers.
      - Acceptance evidence covers async model calls, async tools, async hooks,
        cancellation, sync wrapper compatibility, and concurrent async runs.
      - Slice I.7 validation: `poetry run pytest tests/test_concurrency.py
        tests/test_executor.py -q` — pass; 43 tests passed.
      - Slice I.7 broader validation: `poetry run pytest tests/test_executor.py
        tests/test_tracing.py tests/test_prompt_cache.py tests/test_token_budget.py
        tests/test_hooks.py tests/test_registry.py tests/test_openai_client.py
        tests/test_import.py tests/test_cli.py tests/test_concurrency.py -q` —
        pass; 129 tests passed.
      - Slice I.7 pre-commit: `poetry run pre-commit run --files
        tests/test_concurrency.py` — pass.

## Deferred OpenAI Agents SDK Python evaluation follow-ups

- [ ] OA1. Add guardrail metadata for input, output, tool-input, and
      tool-output phases, including abort and reject-content behavior.
- [ ] OA2. Extend tool provenance metadata to distinguish registered,
      built-in, override, MCP, and future agent-as-tool origins.
- [ ] OA3. Design a prepare-model-input stage for context compaction, session
      pruning, and hierarchical prompt injection before model adapter calls.
- [ ] OA4. Fold MCP lifecycle diagnostics into E9: active/failed server lists,
      error maps, strict/degraded startup, reconnect, and cleanup timeouts.
- [ ] OA5. Draft tool-use completion policy for future iterative agent-loop
      support, including run-again, stop-on-tool, and custom final-output
      decisions.
- [ ] OA6. Preserve handoff vs agent-as-tool as distinct manifest metadata
      patterns for multi-agent workflows.
- [ ] OA7. Design workflow interruption and resumable run state for
      approval-required tools before implementing live approval pauses.
- [ ] OA8. Consider a small async session protocol only after multi-turn memory
      requirements are explicit.
- [ ] OA9. Consider an optional `tool_from_function(...)` helper that generates
      explicit registry metadata while preserving side-effect and approval policy.
- [ ] OA10. Keep sandbox/workspace runtime support separate from default local
      tool packs and defer it until write/command tool requirements are approved.

## Cross-Cutting Validation Tasks

- [ ] V1. Keep unit tests free of live OpenAI API calls.
- [ ] V2. Run `poetry check` after package/dependency changes.
- [ ] V3. Run targeted `pytest` after each implemented slice once tests exist.
- [ ] V4. Run `pre-commit run --files <changed files>` before scoped commits.
- [ ] V5. Track drift: update `spec.md`, `plan.md`, or this task list when
      implementation reveals changed requirements, architecture, or task order.
- [x] V6. Add concurrency validation before claiming full thread safety: run
      concurrent fake-client/fake-tool executions and verify there is no
      library-owned run-state crosstalk and that shared-collaborator behavior
      matches the documented contract.
      - Completed in commit `2e45888` with `tests/test_concurrency.py` covering
        shared-context concurrent runs, run-correlated traces/hooks, synchronized
        in-memory registry registration/invocation, public API `run_id`
        propagation, and thread-safe lazy default-client initialization.
- [x] V7. Add async-interface validation before claiming async support: cover
      async model calls, async tool handlers, async lifecycle hooks, cancellation
      propagation, sync wrapper compatibility including already-running event-loop
      misuse, and concurrent async runs that preserve E13 run-correlation
      semantics.
      - Partially covered in commit `72c28dd`: async executor core validation now
        covers async model calls, async direct tool handlers, async lifecycle
        hooks, and sync-path rejection of async model adapters.
      - Partially covered in commit `4f279ff`: public async API exports, high-level
        async API final-result behavior, sync wrapper conversion, ordinary sync
        wrapper execution, and already-running event-loop misuse are validated.
      - Completed in commit `7990503`: cancellation-focused tests validate
        in-flight async workflow cancellation propagation plus trace/hook
        observations, concurrent async run validation preserves E13 run
        correlation, and sync/async public entry points preserve observable final
        result and trace event shapes.
