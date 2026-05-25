# Active Context

## Current Focus

- Slice 6 workflow executor is complete and committed in `4ce8c67`; Slice 7 CLI
  and documentation is next.

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
- In progress:
  - No source implementation work is currently in progress.
- Not started:
  - CLI implementation.

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
  implementation. Slices 0, 1, 2, 3, 4, 5, and 6 are complete; Slice 7 is the
  next active implementation slice.
- Supported agent patterns from the upstream agent-development skill are now
  treated as manifest metadata, not as new primitive runtime node kinds. Slice 2
  now preserves `patterns_present`, `participant_groups`, `modes`, `phases`, and
  `roles` metadata during loading.
- `load_agent_workflow(...)` loads artifacts without execution and validates
  loaded artifacts before returning them. `run_agent_workflow(...)` now loads,
  validates, executes, and returns the final workflow result.
- Slice 3 validation currently checks required manifest fields, supported enum
  values, node ID uniqueness, edge endpoint references, tool-use references, LLM
  prompt presence, and external tool-index structure. Slice 4 must reconcile
  execution semantics so callable registry entries, not manifest/tool-index
  metadata alone, determine tool availability.
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

- Begin Slice 7 — CLI and documentation.
- Add a CLI entry point for loading artifacts and running a workflow from a
  prompt.
- Support CLI options for runtime YAML, optional design/graph/tool-index inputs,
  registry configuration, and prompt input.
- Update README with concrete API and CLI usage once the CLI shape is real.
