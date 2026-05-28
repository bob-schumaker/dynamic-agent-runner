# Active Context

## Current Focus

- Follow-up design documentation for concurrent invocation and async/sync
  interface support is recorded. Governing docs commit `d9fa4ad` adds future
  thread-safety work for shared collaborators and future async execution APIs
  while preserving synchronous APIs as wrappers over the same runtime semantics.

## Current Status

- Done:
  - Inspected repository top-level files.
  - Reviewed `pyproject.toml`, `.pre-commit-config.yaml`, `.mise.toml`,
    `.flake8`, `.isort.cfg`, `.gitignore`, and `env_setup`.
  - Confirmed no Python, Markdown, or RST source/docs files were present before
    creating the memory bank.
  - Captured user-confirmed product intent for the library.
  - Committed project configuration in `ad3eb90`.
  - Committed build and package configuration in `ed7917f`.
  - Committed memory-bank baseline in `c7f292b`.
  - Committed dynamic agent runner specification in `b1182e9`.
  - Committed README runtime-direction update in `c9cd13c`.
  - Committed memory-bank runtime-direction refresh in `4e69ea9`.
  - Committed spec update selecting the official `openai` package and custom
    registry direction in `b247e11`.
  - Committed memory-bank OpenAI runtime direction refresh in `bef8817`.
  - Created and committed implementation-readiness planning artifacts and README
    alignment in `2979342`.
  - Marked Slice 0 complete and advanced the task list to Slice 1 in `ea5a88a`.
  - Completed Slice 1 package scaffold, dependency alignment, and import smoke
    test in `d2766c0`.
  - Updated `spec.md`, `plan.md`, and `tasks.md` for the 11 documented supported
    agent-pattern IDs and committed that planning drift update in `db13d29`.
  - Completed Slice 2 artifact models/loaders in `64ad379`.
  - Completed Slice 3 validation engine in `3469d49`.
  - Expanded Slice 4 planning scope in `07edab0` to make the callable registry
    authoritative, treat `tool-index.yaml` as optional metadata, add runtime
    tool overrides, and include opt-in built-in default tool packs.
  - Completed Slice 4 repository-owned tool registry foundation in `cba3f43`.
  - Completed Slice 5 OpenAI client adapter boundary in `42f8d15`.
  - Completed Slice 6 workflow executor in `4ce8c67`.
  - Added hello-world test-resource runtime packages for all 11 supported
    agent-pattern IDs and updated the spec to record that test surface in
    `ef1fd38`.
  - Completed Slice 7 CLI and documentation in `30a6b0a`.
  - Added all-fixture CLI coverage and explicit unsupported-edge failure behavior
    in `da1848d`.
  - Added `cline-tasks/libraries-that-made-my-ai-agents-work.md` in `33632d4` as
    a source artifact for package-addition evaluation.
  - Updated `spec.md` and `tasks.md` with runtime hardening requirements and
    follow-on slices in `a0b1490`.
  - Completed Slice 8 retry and resilience policy in `a274b8b`.
  - Completed Slice 9 output contracts and route validation in `69b68ef`.
  - Completed Slice 10 token budgeting and context preflight in `d3a5c51`.
  - Completed Slice 11 execution tracing and observability hooks in `ecb8115`.
  - Updated the SDD artifacts to define runtime behavior override requirements,
    then completed Slice 12 prompt/skill behavior overrides in `7d950b7`.
  - Added future feature spec `specs/llm-step-interpreter-middleware/spec.md`
    in `e305b55`, with packaged source reference
    `specs/llm-step-interpreter-middleware/references/give-your-agents-an-interpreter.md`.
  - Completed Slice 13 prompt-cache intent and trace observation in `aed3b13`.
  - Added Codex and Cline evaluation artifacts plus a combined package proposal
    and deferred task-list follow-ups in `88dad33`.
  - Added the evaluation follow-up implementation plan in `8013dc1`.
  - Completed evaluation follow-up Slice A in `38929f1`, adding
    `WorkflowExecutionContext` / `RunContext` and compatible context-aware
    executor/API entry points.
  - Updated governing spec/plan/task documents and the implementation plan for
    Slice A completion evidence in `ae9fc73`.
  - Completed evaluation follow-up Slice B in `44b0847`, strengthening registry
    validation for OpenAI-compatible tool input schemas.
  - Updated governing spec/plan/task documents and the implementation plan for
    Slice B completion evidence in `b73553f`.
  - Completed evaluation follow-up Slice C in `61f1548`, adding explicit
    `ToolExposure` states and lightweight `ToolPolicy` metadata.
  - Updated governing spec/plan/task documents and the implementation plan for
    Slice C completion evidence in `4996aaa`.
  - Completed evaluation follow-up Slice D in `815f55a`, adding richer
    `ToolResult` facets for model-facing, raw, log-preview, event-payload, and
    sensitive-field output handling.
  - Updated governing spec/plan/task documents and the implementation plan for
    Slice D completion evidence in `521c288`.
  - Completed evaluation follow-up Slice E in `bcd76d4`, adding `tool_started`,
    `tool_finished`, and fallback `status_notice` trace events while preserving
    existing tool trace compatibility events.
  - Updated governing spec/plan/task documents and the implementation plan for
    Slice E completion evidence in `93ddb91`.
  - Completed evaluation follow-up Slice F in `bf18554`, adding trusted
    in-process lifecycle hooks and stable hook context objects for node, model,
    tool, permission-boundary, and workflow observations.
  - Updated governing spec/plan/task documents and the implementation plan for
    Slice F completion evidence in `a82d10f`.
  - Completed evaluation follow-up Slice G / E2 in `13c6dac`, adding
    lightweight `ModelCapabilities` metadata parsed from runtime execution policy.
  - Updated governing spec/plan/task documents and the implementation plan for
    Slice G / E2 completion evidence in `97fe320`.
  - Updated governing spec/plan/task documents for future concurrent invocation
    and async/sync interface work in `d9fa4ad`.
- In progress:
  - None currently; awaiting the next scoped follow-up direction after this
    memory-bank checkpoint.
- Not started:
  - Provider-specific prompt-cache request pass-through is deferred until exact
    SDK/API support is verified; Slice 13 records metadata and telemetry only.
  - Interpreter middleware implementation is not started; the future spec
    explicitly defers backend selection until prototypes and benchmarks exist.
  - Remaining deferred Codex/Cline follow-ups include E9 through E14; no next
    candidate slice has been selected after recording concurrency and async
    interface follow-ups.

## Important Current Facts

- Initial source package scaffold now exists under `src/dynamic_agent_runner/`,
  and Slice 2 added artifact loading modules and tests.
- Product purpose is confirmed by user instruction: read generated agent workflow
  artifacts, use the official `openai` Python package for default model
  execution, use a repository-owned tool registry pattern for tool calls, run
  from a prompt, and return the final result.
- `ai-tools-core` / `openai-tools-core` and `ocihelper` are not part of the
  intended initial runtime implementation direction.
- Current planning artifacts are:
  - `specs/dynamic-agent-runner/spec.md`
  - `specs/dynamic-agent-runner/plan.md`
  - `specs/dynamic-agent-runner/tasks.md`
  - `specs/llm-step-interpreter-middleware/spec.md` — future feature spec for
    optional interpreter middleware and custom interpreter registration
- A Council review and a 3-round debate both concluded the artifact set was
  ready only for slice-by-slice implementation, not unrestricted runtime
  implementation. Slices 0 through 13 plus evaluation follow-up Slices A, B,
  C, D, E, F, and G are complete; E9 through E14 remain deferred follow-up
  candidates.
- `cline-tasks/codex-cli-evaluation.md` and `cline-tasks/cline-evaluation.md`
  capture read-only external runtime-pattern evaluations. The synthesized
  proposal lives at `cline-tasks/codex-cline-combined-package-proposal.md`.
- `specs/dynamic-agent-runner/tasks.md` now contains `Deferred Codex/Cline
  evaluation follow-ups` E1 through E14. E1 is complete and checked off with
  implementation commit `38929f1`, E3 is complete and checked off with
  implementation commit `44b0847`, E4/E5 are complete and checked off with
  implementation commit `61f1548`, E6 is complete and checked off with
  implementation commit `815f55a`, E7 is complete and checked off with
  implementation commit `bf18554`, E8 is complete and checked off with
  implementation commit `bcd76d4`, and E2 is complete and checked off with
  implementation commit `13c6dac`. `spec.md`, `plan.md`, `tasks.md`, and
  `cline-tasks/evaluation-follow-up-implementation-plan.md` were refreshed for
  Slice G / E2 in `97fe320`.
  Future E13 and E14 are recorded for thread-safety / concurrent invocation and
  async/sync interface design, respectively, in `d9fa4ad`.
- Supported agent patterns from the upstream agent-development skill are now
  treated as manifest metadata, not as new primitive runtime node kinds. Slice 2
  now preserves `patterns_present`, `participant_groups`, `modes`, `phases`, and
  `roles` metadata during loading.
- `tests/fixtures/agent-patterns/` now contains a hello-world runtime package for
  every `SUPPORTED_AGENT_PATTERNS` entry. Each package contains
  `agent-design.md`, `agent-runtime.yaml`, and `agent-graph.mmd`.
- `tests/test_agent_pattern_fixtures.py` verifies that the fixture directory
  covers all 11 supported pattern IDs and that each package loads and validates
  through `load_agent_workflow(...)`.
- `load_agent_workflow(...)` loads artifacts without execution and validates
  loaded artifacts before returning them. `run_agent_workflow(...)` now loads,
  validates, executes, and returns the final workflow result.
- Validation checks required manifest fields, supported enum values, node ID
  uniqueness, edge endpoint references, tool-use references, LLM prompt presence,
  and external tool-index structure. Slice 4 reconciled execution semantics so
  callable registry entries, not manifest/tool-index metadata alone, determine
  tool availability.
- `PyYAML >=6.0` is now a direct runtime dependency for YAML artifact loading.
- Slice 4 implementation from `cba3f43`:
  - `src/dynamic_agent_runner/registry.py` now defines `ToolRegistry`,
    `RegisteredTool`, `ToolResult`, runtime override models,
    `InMemoryToolRegistry`, OpenAI schema conversion, invocation dispatch,
    registry-authoritative tool reference validation, and an opt-in read-only
    `local_workspace` built-in tool pack.
  - `load_agent_workflow(...)` accepts an optional `tool_registry` for validation
    while still avoiding execution.
  - `tests/test_registry.py` covers registry lookup, schema conversion,
    invocation, missing tools, bad inputs, tool failures, override layering,
    built-in pack enablement, path restrictions, and node-reference requirements.
- Slice 5 implementation from `42f8d15`:
  - `src/dynamic_agent_runner/openai_client.py` now defines the minimal OpenAI
    client protocol, request/response dataclasses, lazy default official OpenAI
    client construction, and `OpenAIClientAdapter`.
  - `build_openai_request(...)` constructs Responses API requests from rendered
    messages, optional tool schemas, tool choice, response format, and extra
    model parameters.
  - `normalize_openai_response(...)` extracts response text and function calls
    into `ModelResponse` and `ModelToolCall` structures.
  - Adapter and request-construction failures surface as `ModelExecutionError`.
  - `tests/test_openai_client.py` uses fake clients only and covers request
    construction, injected-client execution, response normalization, error
    wrapping, and input validation.
- Slice 6 implementation from `4ce8c67`:
  - `src/dynamic_agent_runner/executor.py` now defines `WorkflowExecutionState`,
    `NodeExecution`, `WorkflowResult`, and `execute_workflow(...)`.
  - `llm_step` execution renders prompt templates, exposes node tools through the
    registry-to-OpenAI schema path, and calls the Slice 5 OpenAI adapter.
  - `tool_use_step` execution resolves inputs, dispatches through the Slice 4
    registry, records structured tool results, and honors configured failure
    behavior.
  - `decision_step` with `decision_subtype: llm_route` extracts JSON-like or text
    routes and follows matching branch edges.
  - `tests/test_executor.py` uses fake clients and fake tools only and covers
    successful execution, tool failure behavior, branch routing, public API final
    result behavior, and step-limit failures.
- Slice 7 implementation from `30a6b0a`:
  - `src/dynamic_agent_runner/cli.py` now defines the CLI parser, injectable
    `main(...)`, and `console_main()` entry point.
  - `pyproject.toml` exposes the `dynamic-agent-runner` console script through
    `[project.scripts]`.
  - CLI options support runtime manifest, optional design/graph/tool-index paths,
    prompt text, prompt-file input, stdin prompt input, max steps, and opt-in
    read-only local workspace registry roots.
  - `tests/test_cli.py` uses fixture artifacts and fake OpenAI clients only and
    covers successful path execution, prompt input modes, missing prompt errors,
    and model/execution error reporting.
  - `README.md` now documents concrete Python API and CLI usage.
- Follow-on CLI/executor test hardening from `da1848d`:
  - `tests/test_cli.py` now runs the CLI across all currently executable
    hello-world pattern fixtures with fake registry tools and fake OpenAI
    clients.
  - `multi-agent-collaboration` is covered as an expected unsupported fixture
    because it uses `parallel_join`, which is not implemented by the current
    executor.
  - `src/dynamic_agent_runner/executor.py` now fails clearly when a node has only
    unsupported outgoing edge kinds instead of silently ending the workflow.
  - Tool-using CLI fixtures without a callable registry now assert the expected
    missing-registry failure path.
- Library-evaluation roadmap update from `a0b1490`:
  - `spec.md` now includes requirements for bounded retry/resilience policy,
    output-contract enforcement, token budgeting/context preflight, and
    execution tracing hooks.
  - `tasks.md` now defines Slice 8 retry/resilience, Slice 9 output contracts,
    Slice 10 token budgeting, and Slice 11 tracing/observability.
  - LiteLLM, Watchfiles, Rich, and Diskcache are deferred unless later scoped
    requirements justify them.
- Slice 8 implementation from `a274b8b`:
  - `src/dynamic_agent_runner/retry.py` defines package-owned `RetryPolicy`
    and `RetryRecord` models plus Tenacity-backed retry helpers.
  - `src/dynamic_agent_runner/executor.py` applies bounded retry policy to
    model calls and tool calls while preserving default one-attempt fail-closed
    behavior.
  - `WorkflowExecutionState.retry_records` records operation, attempts,
    outcome, and final error for model and tool call sites.
  - Retry policy can come from node metadata, manifest execution policy, or
    callable registry tool metadata, depending on call site.
  - `tests/test_executor.py` covers retryable, non-retryable, exhaustion, and
    default no-retry behavior using fake clients and fake tools.
- Slice 9 implementation from `69b68ef`:
  - `src/dynamic_agent_runner/executor.py` validates `llm_step`
    `output_schema_ref` declarations against `runtime_manifest.output_contracts`
    before model output is stored as trusted node state.
  - Required output fields are validated against JSON object model output or
    adapter-provided structured output; plain text remains accepted only for
    the fixture-compatible single-field `message` contract.
  - `decision_step` nodes with `decision_subtype: llm_route` validate extracted
    routes against `decision_contract.allowed_paths` when present.
  - Malformed route output and routes outside allowed paths fail clearly before
    branch traversal.
  - Model-assisted repair or Instructor-style retry behavior remains out of
    scope.
  - `tests/test_executor.py` and `tests/test_cli.py` cover output contracts,
    route validation, and fixture responses that satisfy `hello_message`.
- Slice 10 implementation from `d3a5c51`:
  - `src/dynamic_agent_runner/token_budget.py` defines package-owned
    `TokenBudgetPolicy`, `TokenUsageRecord`, and `TokenEstimate` models plus
    `tiktoken`-backed prompt-token estimation.
  - `src/dynamic_agent_runner/executor.py` runs token preflight for `llm_step`
    nodes when node-level or manifest-level token-budget metadata is configured.
  - Default behavior remains pass-through with no estimation or blocking when no
    token budget is configured.
  - Over-budget prompts fail before the OpenAI adapter is called.
  - `WorkflowExecutionState.token_usage` records model, estimate, budget,
    encoding, fallback flag, and exceeded status.
  - Unknown models fall back to `cl100k_base`; automatic truncation remains
    unsupported.
  - `tests/test_token_budget.py` and `tests/test_executor.py` cover token
    estimation, fallback, parsing, over-budget failure, and disabled behavior.
- Slice 12 implementation from `7d950b7`:
  - `src/dynamic_agent_runner/behavior.py` derives effective per-node prompt and
    skill behavior without mutating loaded generated artifacts.
  - `src/dynamic_agent_runner/models.py` defines runtime behavior override models
    for prompt `replace` / `prepend` / `append`, inline skill overlays, and
    per-node skill binding `add` / `remove` / `only` operations.
  - `src/dynamic_agent_runner/artifacts.py` loads optional runtime behavior
    overrides from path, raw YAML, or parsed mapping inputs.
  - `src/dynamic_agent_runner/validation.py` validates override format, target
    nodes, prompt operations, skill references, and effective prompts before
    execution.
  - `execute_workflow(...)`, `load_agent_workflow(...)`, `run_agent_workflow(...)`,
    and the CLI now accept or apply runtime behavior overrides.
  - `tests/test_artifacts.py`, `tests/test_validation.py`,
    `tests/test_executor.py`, and `tests/test_cli.py` cover override loading,
    validation, prompt patching, skill add/remove/only behavior, node isolation,
    artifact immutability, CLI wiring, and invalid override failures.
- Slice 11 implementation from `ecb8115`:
  - `src/dynamic_agent_runner/tracing.py` defines package-owned `TraceEvent`,
    `TraceSink`, `InMemoryTraceSink`, and `WorkflowTracer` primitives.
  - `WorkflowExecutionState.trace_events` records ordered events during
    execution, and `execute_workflow(...)` / `run_agent_workflow(...)` accept
    optional trace sinks for live event delivery.
  - Trace events cover workflow start/completion, node start/completion, model
    request/response, token-budget checks, tool invocation/result, retry
    records, decisions, node errors, workflow errors, and final results.
  - `TraceEvent.redacted_payload()` and `TraceEvent.redacted()` support shallow
    redaction before external emission.
  - `tests/test_tracing.py` covers successful workflows, tool failures, model
    failures, and retry-attempt tracing with fake clients/tools only.
- Evaluation follow-up Slice E implementation from `bcd76d4`:
  - `src/dynamic_agent_runner/executor.py` now emits `tool_started` before direct
    tool invocation and `tool_finished` after tool results are recorded on both
    success and fail-closed error paths.
  - Existing `tool_invocation` and `tool_result` events remain available for
    compatibility.
  - Non-fatal fallback tool failures emit warning `status_notice` events with a
    stable code, human-readable message, tool id, and error detail.
  - `tests/test_tracing.py` covers tool lifecycle events, fail-closed tool
    lifecycle traces, and fallback status notices.
  - Validation: `ruff check src tests && ruff format --check src tests &&
    python -m pytest -q` — pass; 125 tests passed.
- Slice 13 implementation from `aed3b13`:
  - `src/dynamic_agent_runner/prompt_cache.py` defines provider-neutral
    `PromptCachePolicy` parsing and prompt-cache eligibility observation helpers.
  - `src/dynamic_agent_runner/validation.py` validates optional
    `execution_policy.prompt_cache` metadata before execution.
  - `src/dynamic_agent_runner/executor.py` records named rendered message parts,
    emits `prompt_cache_checked`, supports per-execution `prompt_cache=False`,
    and records `prompt_cache_provider_telemetry` when cached-token metadata is
    present in the model response.
  - `tests/test_prompt_cache.py` covers parsing, validation failures, eligible
    and ineligible prefixes, `x-` extension part names, missing token-estimator
    behavior, caller disable overrides, and provider cached-token telemetry.
  - Provider-specific prompt-cache request pass-through remains deferred until
    exact SDK/API support is verified.
- Evaluation follow-up Slice A implementation from `38929f1`:
  - `src/dynamic_agent_runner/context.py` defines `WorkflowExecutionContext` and
    `RunContext` as a stable execution envelope for a loaded workflow, optional
    tool registry, model adapter, max-step override, trace sink, and prompt-cache
    override.
  - `execute_workflow(...)` now accepts either a loaded workflow plus runtime
    keywords or a context object, and rejects ambiguous calls that combine both.
  - `run_agent_workflow(...)` accepts `execution_context=` for preloaded
    workflows while preserving existing artifact-loading keyword behavior.
  - `dynamic_agent_runner.__init__` exports `WorkflowExecutionContext` and
    `RunContext`.
  - `tests/test_executor.py` and `tests/test_import.py` cover context execution,
    ambiguity rejection, API wiring, and public exports.
  - Validation: `ruff check src tests && ruff format --check src tests &&
    python -m pytest -q` — pass; 108 tests passed.
- Evaluation follow-up Slice B implementation from `44b0847`:
  - `src/dynamic_agent_runner/registry.py` now normalizes tool `input_schema`
    definitions through one shared validation path for OpenAI tool exposure and
    invocation input validation.
  - The registry rejects non-mapping schemas, non-object schemas, non-mapping
    `properties`, non-list or non-string `required` entries, and unsupported
    top-level `oneOf` / `anyOf` / `allOf` combinators.
  - Model-facing OpenAI tool parameters omit top-level `$schema` metadata.
  - `tests/test_registry.py` covers malformed schema rejection and `$schema`
    stripping.
  - Validation: `ruff check src tests && ruff format --check src tests &&
    python -m pytest -q` — pass; 116 tests passed.
- Governing-docs update from `b73553f`:
  - `specs/dynamic-agent-runner/spec.md` records stricter tool input-schema
    acceptance criteria and Slice B consistency evidence.
  - `specs/dynamic-agent-runner/plan.md` records the registry schema-validation
    responsibility, Slice B implementation slice, and future combinator-expansion
    caveat.
  - `specs/dynamic-agent-runner/tasks.md` marks E3 complete with commit and
    validation evidence.
  - `cline-tasks/evaluation-follow-up-implementation-plan.md` marks Slice B
    complete and preserves validation evidence.
- Evaluation follow-up Slice C implementation from `61f1548`:
  - `src/dynamic_agent_runner/models.py` defines `ToolExposure` states
    `direct`, `deferred`, `direct_model_only`, and `hidden`.
  - `ToolPolicy` preserves side-effect, approval, sandbox, timeout, retry, and
    failure-behavior metadata separately from callable registry entries and
    node exposure decisions.
  - `src/dynamic_agent_runner/registry.py` exposes only `direct` and
    `direct_model_only` tools to model-facing OpenAI tool schemas, while
    `hidden` tools remain direct-callable but not model-exposed.
  - Direct `tool_use_step` validation and invocation reject `direct_model_only`
    and `deferred` tools as not directly callable.
  - `src/dynamic_agent_runner/validation.py` fails closed for unknown tool
    exposure values in runtime manifests and external tool indexes.
  - `tests/test_registry.py`, `tests/test_validation.py`, and
    `tests/test_import.py` cover exposure semantics, policy metadata, unknown
    exposure validation, direct-step callable checks, and public exports.
  - Validation: `ruff check src tests && ruff format --check src tests &&
    python -m pytest -q` — pass; 121 tests passed.
- Governing-docs update from `4996aaa`:
  - `specs/dynamic-agent-runner/spec.md` records explicit exposure states,
    `sandbox` policy metadata, and Slice C consistency evidence.
  - `specs/dynamic-agent-runner/plan.md` records `ToolExposure`, `ToolPolicy`,
    model-exposure filtering, direct-step callable checks, and related risks.
  - `specs/dynamic-agent-runner/tasks.md` marks E4 and E5 complete with commit
    and validation evidence.
  - `cline-tasks/evaluation-follow-up-implementation-plan.md` marks Slice C
    complete and preserves validation evidence.
- Governing-docs update from `ae9fc73`:
  - `specs/dynamic-agent-runner/spec.md` records the execution context as an
    accepted runtime input and adds acceptance criteria for context-aware
    execution and ambiguity rejection.
  - `specs/dynamic-agent-runner/plan.md` records the execution-envelope pattern
    and notes future caller-provided runtime envelope additions should attach to
    `WorkflowExecutionContext` / `RunContext` rather than mutable state.
  - `specs/dynamic-agent-runner/tasks.md` marks E1 complete with commit and
    validation evidence.
  - `cline-tasks/evaluation-follow-up-implementation-plan.md` marks Slice A
    complete and preserves the validation evidence.
- Interpreter middleware future spec from `e305b55`:
  - `specs/llm-step-interpreter-middleware/spec.md` records an optional future
    capability for attaching interpreter backends to `llm_step` nodes.
  - The spec proposes a caller-provided `InterpreterRegistry` /
    `RegisteredInterpreter` style interface so custom QuickJS, restricted
    Python, DSL, WebAssembly, or subprocess-backed adapters can be evaluated
    without hard-coding one backend.
  - Manifest-level `interpreters` metadata is explicitly non-executable; a
    caller-provided registry or approved source must supply executable adapters.
  - The packaged supporting reference was moved from `cline-tasks/` to
    `specs/llm-step-interpreter-middleware/references/`.
  - Backend selection, dependencies, prototypes, and benchmarks remain deferred.
- Slice 4 scope decisions from `07edab0`:
  - `tool-index.yaml` is optional metadata, not an execution prerequisite.
  - A required tool registry or approved registry source is authoritative for
    callable tool availability when tool use is expected.
  - Runtime tool overrides can add, replace, disable, or restrict tools globally
    or per `llm_step` without mutating generated artifacts.
  - Built-in default tools may exist only as explicit opt-in registry packs; the
    initial pack should be read-only `local_workspace` tools such as `read_file`,
    `list_files`, `search_files`, and `inspect_path`.
- Latest observed branch history includes:
  - `d9fa4ad docs(spec): record concurrency and async follow-ups`
  - `97fe320 docs(spec): record model capabilities slice`
  - `13c6dac feat(models): add model capabilities metadata`
  - `a82d10f docs(spec): record lifecycle hooks slice`
  - `bf18554 feat(executor): add lifecycle hooks`
  - `93ddb91 docs(spec): record trace vocabulary slice`
  - `bcd76d4 feat(tracing): add tool lifecycle trace events`
  - `521c288 docs(spec): record tool result facets slice`
  - `815f55a feat(registry): add tool result facets`
  - `4996aaa docs(spec): record tool exposure policy slice`
  - `61f1548 feat(registry): add tool exposure policy states`
  - `b73553f docs(spec): record tool schema validation slice`
  - `44b0847 fix(registry): validate OpenAI tool schemas`
  - `ae9fc73 docs(spec): record workflow context slice`
  - `38929f1 feat(executor): add workflow execution context`
  - `8013dc1 docs(cline-tasks): add evaluation follow-up plan`
  - `88dad33 docs(evaluations): add Codex and Cline follow-ups`
  - `aed3b13 feat(prompt-cache): add prompt cache intent tracing`
  - `7d950b7 feat(runtime): add behavior overrides`
  - `ecb8115 feat(executor): add workflow tracing hooks`
  - `d3a5c51 feat(executor): add token budget preflight`
  - `69b68ef feat(executor): validate output contracts`
  - `a274b8b feat(executor): add retry policy support`
  - `33632d4 docs(cline-tasks): add agent library evaluation source`
  - `a0b1490 docs(spec): add runtime hardening roadmap`
  - `da1848d fix(executor): fail on unsupported edge kinds`
  - `30a6b0a feat(cli): add workflow runner command`
  - `ef1fd38 test(fixtures): add agent pattern runtime packages`
  - `4ce8c67 feat(executor): add workflow execution engine`
  - `42f8d15 feat(openai): add client adapter boundary`
  - `cba3f43 feat(registry): add tool registry foundation`
  - `07edab0 docs(spec): expand slice 4 registry scope`
  - `3469d49 feat(validation): add artifact validation engine`
  - `64ad379 feat(artifacts): add workflow artifact loaders`
  - `db13d29 docs(spec): record supported agent patterns`
  - `d2766c0 feat(package): add initial runner scaffold`
  - `ea5a88a docs(spec): mark readiness checkpoint complete`
  - `2979342 docs(spec): record implementation readiness gate`
  - `bef8817 docs(memory-bank): record openai runtime direction`
  - `b247e11 docs(spec): use openai package runtime direction`
  - `4e69ea9 docs(memory-bank): refresh runtime direction context`
  - `c9cd13c docs(readme): document ai-tools runtime direction`
- Dependency/package metadata changes were reconciled and committed in
  `d2766c0`.

## Next Steps

- Await follow-up direction for the next deferred Codex/Cline follow-up slice.
  Remaining candidates in `specs/dynamic-agent-runner/tasks.md` include E9
  through E14.
- Use `specs/llm-step-interpreter-middleware/spec.md` as the durable reference
  before any interpreter middleware implementation or dependency selection.
- Keep runtime hardening additions behind package-owned interfaces and scoped
  requirements rather than broad framework adoption.
- Use the 11 hello-world pattern fixture packages as broad package-shape coverage
  when extending loader, executor, CLI, or compatibility tests.
- Preserve fake-client/fake-tool testing for CLI and executor coverage; do not
  introduce live OpenAI API calls into unit tests.
- Treat `parallel_join`, `parallel_fanout`, and broader multi-agent execution as
  unsupported runtime behavior until a later scoped slice implements them.
