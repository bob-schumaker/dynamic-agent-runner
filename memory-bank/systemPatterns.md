# System Patterns

## Current Architecture

- The repository now has an initial `src/` package scaffold:
  - `src/dynamic_agent_runner/__init__.py` reserves public exports
  - `src/dynamic_agent_runner/api.py` exposes `load_agent_workflow` for artifact
    loading while reserving `run_agent_workflow` for later executor slices
  - `src/dynamic_agent_runner/artifacts.py` loads generated workflow artifacts
    and optional runtime behavior override artifacts
  - `src/dynamic_agent_runner/models.py` preserves internal artifact metadata
    and runtime behavior override models
  - `src/dynamic_agent_runner/behavior.py` derives effective per-node prompt and
    skill behavior without mutating generated artifacts
  - `src/dynamic_agent_runner/validation.py` validates loaded artifact
    relationships and supported `format_version: 1` enum values
  - `src/dynamic_agent_runner/openai_client.py` isolates the official OpenAI
    client behind a small fake-client-compatible adapter boundary
  - `src/dynamic_agent_runner/executor.py` composes loaded workflows, registry
    tools, retry policy, output validation, route validation, token-budget
    preflight, tracing hooks, and the OpenAI adapter into executable workflow
    runs through the async-first executor core
  - `src/dynamic_agent_runner/tracing.py` owns package trace event, trace sink,
    redaction, and in-memory tracing primitives
  - `src/dynamic_agent_runner/token_budget.py` owns `tiktoken`-backed prompt
    estimation and token-budget policy parsing
  - `src/dynamic_agent_runner/retry.py` owns retry policy parsing and
    Tenacity-backed bounded retry helpers
  - `src/dynamic_agent_runner/cli.py` exposes an injectable CLI implementation
    and console-script entry point for artifact-path workflow execution
  - `src/dynamic_agent_runner/errors.py` defines project-specific exception
    types
- Tests currently contain an import smoke test at `tests/test_import.py`,
  artifact loader tests at `tests/test_artifacts.py`, validation tests at
  `tests/test_validation.py`, registry tests at `tests/test_registry.py`, OpenAI
  adapter tests at `tests/test_openai_client.py`, executor tests at
  `tests/test_executor.py`, tracing tests at `tests/test_tracing.py`, and CLI
  tests at `tests/test_cli.py`. Pattern fixture coverage lives in
  `tests/test_agent_pattern_fixtures.py`.
- `tests/fixtures/agent-patterns/` contains 11 hello-world runtime packages, one
  for each documented supported agent pattern. Each fixture package has
  `agent-design.md`, `agent-runtime.yaml`, and `agent-graph.mmd`.
- Current repository structure has loader/model/validation/registry/adapter/
  executor/retry/output-contract/token-budget/tracing/behavior-override/CLI
  behavior; follow-on runtime expansion should be planned as a new scoped slice.

## Observed Patterns

- Python package managed with Poetry.
- Source layout uses `src/dynamic_agent_runner/` as configured in
  `pyproject.toml`.
- Local development environment managed by mise.
- `env_setup` adds `lib`, `src`, and `bin` to `PYTHONPATH`/`PATH` when those
  directories exist.
- Ruff, flake8, isort, and pre-commit are configured.
- `load_agent_workflow(...)` loads generated workflow artifacts without
  executing them, then validates the loaded bundle before returning it.
- `run_agent_workflow_async(...)` now loads, validates, executes through
  `execute_workflow_async(...)`, and returns the final workflow result.
  `run_agent_workflow(...)` and `execute_workflow(...)` remain synchronous
  compatibility wrappers over the async semantic path.
- Error taxonomy starts with a base `DynamicAgentRunnerError` and specific
  loading, validation, registry, model, and workflow execution errors.
- Runtime artifact design preserves documented supported agent-pattern IDs as
  manifest metadata instead of expanding the primitive node taxonomy.
- The all-pattern fixture surface is intentionally package-shape coverage: it
  validates that every supported pattern ID can be represented by a portable
  runtime package, but it does not imply full executor support for every
  pattern-specific behavior.
- Pattern-specific structures should be modeled through `patterns_present`,
  `participant_groups`, `roles`, `modes`, `phases`, declared tools, state,
  execution policy, and control-flow edges.
- Artifact inputs support path, raw-string, and already-parsed mapping forms for
  runtime manifests and tool indexes. Mermaid graphs and agent designs support
  path or raw-string inputs.
- Validation fails closed for missing required manifest fields, unsupported
  manifest/tool-index enum values, duplicate or missing node IDs, bad edge
  endpoints, unknown metadata tool references, and LLM nodes without prompt or
  prompt-source metadata. With an effective registry, tool-use dependencies can
  be validated against callable registry entries.
- `registry.py` defines runtime tool overrides as overlay inputs that can add,
  replace, disable, or restrict tools globally or per `llm_step` without mutating
  generated artifacts.
- Built-in default tools are explicit opt-in registry packs; the current
  `local_workspace` pack is read-only and not an ambient global capability.
- `openai_client.py` defines a protocol around `client.responses.create(...)`,
  so unit tests can inject fake clients without live OpenAI API calls.
- OpenAI request construction uses `input` messages plus optional `tools`,
  `tool_choice`, `response_format`, and extra model parameters.
- OpenAI response normalization extracts text and function calls into internal
  `ModelResponse` / `ModelToolCall` structures while preserving the raw response.
- `executor.py` maintains `WorkflowExecutionState` with prompt, node inputs,
  node outputs, tool results, execution records, retry records, token usage,
  trace events, errors, and final result.
- Executor control flow currently supports sequential edges and branch edges for
  `decision_step` nodes with `decision_subtype: llm_route`, with optional
  `decision_contract.allowed_paths` validation before branch traversal.
- Executor control flow fails explicitly for unsupported outgoing edge kinds such
  as `parallel_join` instead of silently treating those nodes as terminal.
- Executor unit tests use fake OpenAI clients and fake registry tools only;
  no live OpenAI API calls are required.
- CLI tests use the injectable `main(...)` seam, fixture artifact paths, fake
  OpenAI clients, and in-memory streams so command behavior is covered without
  live model calls or subprocess setup.
- CLI tests now cover all currently executable hello-world pattern fixtures and
  explicit expected-failure behavior for the unsupported
  `multi-agent-collaboration` fixture.
- CLI registry configuration is currently intentionally narrow: `--workspace-root`
  enables only the read-only `local_workspace` built-in tool pack. Broader
  registry configuration remains a future extension area.
- Runtime hardening proceeded through package-owned interfaces rather than broad
  framework adoption. Slice 8 completed retry/resilience, Slice 9 completed
  output-contract and route validation, Slice 10 completed token budgeting, Slice
  11 completed trace hooks, Slice 12 completed runtime behavior overrides, and
  E14 completed async-first execution APIs plus cancellation/concurrent async
  validation.
- Trace events are emitted to `WorkflowExecutionState.trace_events` and an
  optional `TraceSink`; sensitive payload keys can be shallow-redacted before
  external emission. Run IDs distinguish concurrent sync and async executions.
- Async execution supports async model adapters, async tool handlers, async
  lifecycle hooks, cancellation propagation, and concurrent shared-context runs
  while preserving per-run execution state isolation.

## Boundaries and Unknowns

- Runtime manifest model: implemented for loader/model scope.
- Artifact loading behavior: implemented for Slice 2 scope.
- Supported pattern metadata preservation: implemented for loader/model scope.
- Validation engine: implemented for Slice 3 scope.
- Tool registry protocol and concrete registry: implemented for Slice 4 scope.
- OpenAI client adapter: implemented for Slice 5 scope.
- Workflow executor: implemented for Slice 6 scope.
- CLI: implemented for Slice 7 scope.
- Retry/resilience: implemented for Slice 8 scope.
- Output contracts and route validation: implemented for Slice 9 scope.
- Token budgeting and context preflight: implemented for Slice 10 scope.
- Execution tracing and observability hooks: implemented for Slice 11 scope.
- Runtime behavior overrides for prompts and skills: implemented for Slice 12
  scope.
- Async-first execution APIs and sync wrappers: implemented for E14 scope through
  Slice I.7 validation.

## Guidance for Future Work

- Await follow-up direction for the next scoped runtime slice; no next active
  implementation slice is currently defined in
  `specs/dynamic-agent-runner/tasks.md`.
- Keep implementation aligned with the artifact-interpreter framing rather than
  expanding into a generic agent framework.
- Keep primitive runtime node kinds limited to `llm_step`, `tool_use_step`, and
  `decision_step` unless a later format version changes the contract.
- Treat the Slice 7 CLI as a thin public surface over existing API/executor
  seams; do not widen executor semantics from CLI work alone.
- Keep unsupported fixture features visible through expected-failure tests until
  a later scoped slice implements them.
- Defer LiteLLM, Watchfiles, Rich, and Diskcache until a future scoped requirement
  justifies them; the current OpenAI-first adapter boundary remains in force.
- If local-model support returns, prefer fitting llama.cpp into the existing
  `model_adapter` contract rather than introducing a parallel runtime model
  interface. The committed feature spec also recommends treating future
  context-pruning attachment as an internal compile-time graph-mutation layer,
  ideally starting with input transformation on `llm_step` nodes before any
  true node/edge graph surgery.
- Repository-local reference packaging is now being used for external guidance
  that should remain available inside this repo. The OpenAI Model Registry notes
  under `cline-tasks/references/openai-model-registry/` are supporting
  references, not executable runtime code or canonical spec artifacts.
- Use `tests/fixtures/agent-patterns/` as a reusable coverage source for future
  loader, executor, and CLI compatibility tests.
- Update this file as concrete modules, entry points, and architectural
  boundaries become real.
