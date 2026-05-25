# Active Context

## Current Focus

- Slice 8 retry and resilience policy is complete and committed in `a274b8b`.
  The executor now supports package-owned bounded retry policy metadata for
  model and tool call sites, backed by Tenacity and recorded in execution
  state. The next active implementation slice is Slice 9 — output contracts
  and route validation.

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
- In progress:
  - No source implementation work is currently in progress.
- Not started:
  - Slice 9 output contracts and route validation.

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
- A Council review and a 3-round debate both concluded the artifact set was
  ready only for slice-by-slice implementation, not unrestricted runtime
  implementation. Slices 0 through 8 are complete; the next active
  implementation slice is Slice 9 — output contracts and route validation.
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

- Continue with Slice 9 — output contracts and route validation — from
  `specs/dynamic-agent-runner/tasks.md` when implementation resumes.
- Keep runtime hardening additions behind package-owned interfaces and scoped
  requirements rather than broad framework adoption.
- Use the 11 hello-world pattern fixture packages as broad package-shape coverage
  when extending loader, executor, CLI, or compatibility tests.
- Preserve fake-client/fake-tool testing for CLI and executor coverage; do not
  introduce live OpenAI API calls into unit tests.
- Treat `parallel_join`, `parallel_fanout`, and broader multi-agent execution as
  unsupported runtime behavior until a later scoped slice implements them.
