# Progress

## Working

- OA5 implementation/spec work is complete in commit `3d33bbb`
  (`feat(runtime): add deferred tool-use completion policy`).
- OA5 adds a metadata-first, fail-closed `runtime.execution_policy.tool_use_completion`
  surface preserved on `RuntimeManifest` and `ExecutionPlan` for future
  iterative agent-loop runtimes, covering `run_again`, `stop_on_tool`,
  `final_output`, and `final_output_state_key`.
- OA5 focused validation passed with `poetry run pytest tests/test_validation.py
  tests/test_executor.py -q 2>&1` (83 passed) and scoped `pre-commit` on the
  OA5 code/spec files.
- The next active follow-up slice is OA6.
- Baseline project configuration exists:
  - Python/Poetry package metadata in `pyproject.toml`
  - dependency lock file in `poetry.lock`
  - mise local environment configuration in `.mise.toml`
  - shell environment helper in `env_setup`
  - lint and pre-commit configuration files
- Product intent and current implementation-readiness state are documented in
  `README.md`.
- Project configuration commit exists:
  `ad3eb90 chore(config): add project configuration`.
- Build configuration commit exists:
  `ed7917f build: add OCI build configuration`.
- Memory-bank baseline commit exists:
  `c7f292b docs(memory-bank): add project memory baseline`.
- SDD spec commit exists:
  `b1182e9 docs(spec): add dynamic agent runner specification`.
- README runtime-direction commit exists:
  `c9cd13c docs(readme): document ai-tools runtime direction`.
- Memory-bank runtime-direction refresh commit exists:
  `4e69ea9 docs(memory-bank): refresh runtime direction context`.
- Spec update commit exists:
  `b247e11 docs(spec): use openai package runtime direction`.
- Memory-bank OpenAI runtime direction refresh commit exists:
  `bef8817 docs(memory-bank): record openai runtime direction`.
- Implementation-readiness gate commit exists:
  `2979342 docs(spec): record implementation readiness gate`.
- Slice 0 completion commit exists:
  `ea5a88a docs(spec): mark readiness checkpoint complete`.
- Slice 1 package scaffold commit exists:
  `d2766c0 feat(package): add initial runner scaffold`.
- Supported pattern metadata planning update commit exists:
  `db13d29 docs(spec): record supported agent patterns`.
- Slice 2 artifact loader commit exists:
  `64ad379 feat(artifacts): add workflow artifact loaders`.
- Slice 3 validation engine commit exists:
  `3469d49 feat(validation): add artifact validation engine`.
- Slice 4 registry scope update commit exists:
  `07edab0 docs(spec): expand slice 4 registry scope`.
- Slice 4 registry foundation commit exists:
  `cba3f43 feat(registry): add tool registry foundation`.
- Slice 5 OpenAI client adapter commit exists:
  `42f8d15 feat(openai): add client adapter boundary`.
- Slice 6 workflow executor commit exists:
  `4ce8c67 feat(executor): add workflow execution engine`.
- Agent-pattern fixture commit exists:
  `ef1fd38 test(fixtures): add agent pattern runtime packages`.
- Slice 7 CLI implementation commit exists:
  `30a6b0a feat(cli): add workflow runner command`.
- Unsupported-edge failure hardening commit exists:
  `da1848d fix(executor): fail on unsupported edge kinds`.
- Runtime hardening roadmap spec commit exists:
  `a0b1490 docs(spec): add runtime hardening roadmap`.
- Agent library evaluation source commit exists:
  `33632d4 docs(cline-tasks): add agent library evaluation source`.
- Slice 8 retry policy support commit exists:
  `a274b8b feat(executor): add retry policy support`.
- Slice 9 output contract validation commit exists:
  `69b68ef feat(executor): validate output contracts`.
- Slice 10 token budget preflight commit exists:
  `d3a5c51 feat(executor): add token budget preflight`.
- Slice 11 workflow tracing hooks commit exists:
  `ecb8115 feat(executor): add workflow tracing hooks`.
- Slice 12 runtime behavior override commit exists:
  `7d950b7 feat(runtime): add behavior overrides`.
- Future interpreter middleware spec commit exists:
  `e305b55 docs(specs): add llm step interpreter middleware spec`.
- Slice 13 prompt-cache intent tracing commit exists:
  `aed3b13 feat(prompt-cache): add prompt cache intent tracing`.
- Codex/Cline evaluation follow-up commit exists:
  `88dad33 docs(evaluations): add Codex and Cline follow-ups`.
- Evaluation follow-up implementation plan commit exists:
  `8013dc1 docs(cline-tasks): add evaluation follow-up plan`.
- Evaluation follow-up Slice A implementation commit exists:
  `38929f1 feat(executor): add workflow execution context`.
- Evaluation follow-up Slice A governing-docs commit exists:
  `ae9fc73 docs(spec): record workflow context slice`.
- Evaluation follow-up Slice B implementation commit exists:
  `44b0847 fix(registry): validate OpenAI tool schemas`.
- Evaluation follow-up Slice B governing-docs commit exists:
  `b73553f docs(spec): record tool schema validation slice`.
- Evaluation follow-up Slice C implementation commit exists:
  `61f1548 feat(registry): add tool exposure policy states`.
- Evaluation follow-up Slice C governing-docs commit exists:
  `4996aaa docs(spec): record tool exposure policy slice`.
- Evaluation follow-up Slice D implementation commit exists:
  `815f55a feat(registry): add tool result facets`.
- Evaluation follow-up Slice D governing-docs commit exists:
  `521c288 docs(spec): record tool result facets slice`.
- Evaluation follow-up Slice E implementation commit exists:
  `bcd76d4 feat(tracing): add tool lifecycle trace events`.
- Evaluation follow-up Slice E governing-docs commit exists:
  `93ddb91 docs(spec): record trace vocabulary slice`.
- Evaluation follow-up Slice F implementation commit exists:
  `bf18554 feat(executor): add lifecycle hooks`.
- Evaluation follow-up Slice F governing-docs commit exists:
  `a82d10f docs(spec): record lifecycle hooks slice`.
- Evaluation follow-up Slice G / E2 implementation commit exists:
  `13c6dac feat(models): add model capabilities metadata`.
- Evaluation follow-up Slice G / E2 governing-docs commit exists:
  `97fe320 docs(spec): record model capabilities slice`.
- Concurrency and async follow-up governing-docs commit exists:
  `d9fa4ad docs(spec): record concurrency and async follow-ups`.
- E13 concurrent invocation implementation commit exists:
  `2e45888 feat(executor): add concurrent run correlation`.
- E13 governing-docs commit exists:
  `a4fe7e9 docs(spec): record concurrent invocation support`.
- E14 decision-docs commit exists:
  `56ddb9b docs(spec): record async execution decisions`.
- E14 OpenAI source-checkout docs commit exists:
  `4b17a4f docs(spec): record openai async source checkout`.
- E14 implementation-plan commit exists:
  `c22c239 docs(cline-tasks): plan async execution implementation`.
- E14 spec-plan reference commit exists:
  `781f451 docs(spec): reference async implementation plan`.
- E14 Slice I.1 async OpenAI client boundary implementation commit exists:
  `acca9da feat(openai-client): add async adapter boundary`.
- E14 Slice I.1 governing-docs commit exists:
  `e750f3b docs(spec): record async client boundary slice`.
- E14 Slice I.2 async retry helper implementation commit exists:
  `f2296e9 feat(retry): add async retry helper`.
- E14 Slice I.2 governing-docs commit exists:
  `bb96b54 docs(spec): record async retry helper slice`.
- E14 Slice I.3 async tool dispatch implementation commit exists:
  `ff144f5 feat(registry): add async tool dispatch`.
- E14 Slice I.3 governing-docs commit exists:
  `804e1af docs(spec): record async tool dispatch slice`.
- E14 Slice I.4 async lifecycle hook dispatch implementation commit exists:
  `2b9271b feat(hooks): add async lifecycle hook dispatch`.
- E14 Slice I.4 governing-docs commit exists:
  `a204898 docs(spec): record async lifecycle hook slice`.
- E14 Slice I.5 async executor core implementation commit exists:
  `72c28dd feat(executor): add async workflow core`.
- E14 Slice I.5 governing-docs commit exists:
  `09a2900 docs(spec): record async executor core slice`.
- E14 Slice I.6 public async API implementation commit exists:
  `4f279ff feat(api): add public async workflow wrappers`.
- E14 Slice I.6 governing-docs commit exists:
  `b698de9 docs(spec): record async public api slice`.
- E14 Slice I.7 async validation implementation/test commit exists:
  `7990503 test(concurrency): validate async cancellation correlation`.
- E14 Slice I.7 governing-docs commit exists:
  `27f409b docs(spec): record async validation completion`.
- OpenAI Agents SDK Python evaluation/spec follow-up commit exists:
  `322ce13 docs(agent-patterns): add OpenAI Agents SDK evaluation`.
- Runtime-package simplification analysis commit exists:
  `c710490 docs(agent-runtime): analyze package simplification`.
- First-customer runtime-support prioritization commit exists:
  `0af68ab docs(spec): prioritize power-marimo runtime support`.
- Runtime-package simplification Slice S1 implementation commit exists:
  `695c0cc feat(models): support grouped runtime manifests`.
- Runtime-package simplification S1 plan/task evidence commit exists:
  `0f795ee docs(plan): record grouped manifest slice`.
- Runtime-package simplification Slice S2 implementation commit exists:
  `b315c96 feat(executor): add prepared execution plan`.
- Runtime-package simplification S2 plan/task evidence commit exists:
  `1f91804 docs(plan): record prepared execution slice`.
- Runtime-package simplification Slice S3 implementation commit exists:
  `33096b5 feat(executor): add prepared model input seam`.
- Runtime-package simplification S3 plan/task evidence commit exists:
  `b730592 docs(plan): record prepared model input slice`.
- Runtime-package simplification Slice S4 implementation commit exists:
  `a46bb5a feat(registry): add tool source provenance`.
- Runtime-package simplification S4 plan/task evidence commit exists:
  `2d30581 docs(plan): record tool source provenance slice`.
- Runtime-package simplification S5 design-decision commit exists:
  `a084f2d docs(plan): record marimo-pair agent-as-tool decision`.
- Runtime-package simplification Slice S5 implementation commit exists:
  `84dfd31 test(power-marimo): add runtime package fixture`.
- Runtime-package simplification S5 plan/task evidence commit exists:
  `387b574 docs(plan): record power-marimo fixture slice`.
- Runtime-package simplification S5 governing spec commit exists:
  `89926d8 docs(spec): record power-marimo fixture completion`.
- Package-alignment backlog refresh commit exists:
  `8308cd6 docs(specs): update package-alignment backlog`.
- Package-alignment Slice P1 implementation commit exists:
  `63403d3 feat(loader): add package-directory workflow loader`.
- Package-alignment Slice P2 implementation commit exists:
  `a1880e7 feat(loader): validate bundled package assets`.
- Llama.cpp / graph-mutation feature-spec commit exists:
  `1346458 docs(spec): capture llama.cpp and graph mutation feature`.
- OpenAI Model Registry reference-notes commit exists:
  `7a7a54e docs(references): add openai model registry notes`.
- Package-alignment backlog is refreshed and committed in `8308cd6`: the local
  task list now tracks immutable base package directories, `skill-bundle/`
  validation, provider-neutral `model_requirements`, ReAct-style `react_loop`
  manifests, RAG / GraphRAG metadata, and `evidence_loop` alignment with the
  latest upstream `agent-development-skill` runtime-package reference.
- Package-alignment Slice P1 is complete in `63403d3`: the runtime now supports
  canonical package-directory loading through `load_agent_package(...)` and
  `load_agent_package_workflow(...)`, requires `agent-runtime.yaml` at the
  package root, records `package_root` on `LoadedAgentWorkflow`, and resolves
  fixed sibling `agent-design.md` / `agent-graph.mmd` artifacts when present.
- Package-alignment Slice P2 is complete in `a1880e7`: package-loaded workflows
  now preserve optional `skill_bundle_root`, canonical package loading fails
  closed for missing `agent-design.md` / `agent-graph.mmd`, and package
  validation now checks `skills[*].bundled_path` and
  `skills[*].support_files[*].bundled_path` against the configured
  `skill-bundle/` directory while failing clearly for missing or escaping
  bundled files.
- Package-alignment Slice P3 is complete in `a46cd13`: the runtime now exposes
  `CompiledAgentWorkflow`, package and loaded-workflow compile helpers, and
  compiled-workflow acceptance through the public API, execution context, and
  executor while preserving immutable loaded base workflows. Focused validation
  passed with `poetry run pytest tests/test_artifacts.py tests/test_executor.py
  tests/test_validation.py -q` (82 passed).
- Package-alignment Slice P4 is complete in `3e622d2`: the public API now
  treats `package_directory` as the canonical input, the CLI now uses a
  package-directory-first `--package` contract, compatibility file-by-file base
  artifact inputs remain available as lower-level seams, and package validation
  now requires a package `skill-bundle/` directory only when bundled skill or
  support-file paths are actually declared.
- Focused P4 validation passed with `poetry run pytest tests/test_cli.py
  tests/test_executor.py tests/test_import.py -q` (64 passed) and `poetry run
  pre-commit run --files src/dynamic_agent_runner/api.py
  src/dynamic_agent_runner/cli.py src/dynamic_agent_runner/validation.py
  src/dynamic_agent_runner/__init__.py tests/test_cli.py tests/test_executor.py
  tests/test_import.py README.md docs/files/cli.rst docs/files/python-api.rst
  specs/dynamic-agent-runner/tasks.md`.
- Package-alignment Slice P5 implementation commit exists:
  `7e9a33e feat(runtime): align manifest taxonomy metadata`.
- Governing-doc alignment for the newer upstream runtime-package surface now
  exists in commit `cf66be2 docs(spec): align runtime-package surface guidance`.
- SDD artifact consistency refresh is now committed in `3c5e2e9`
  (`docs(spec): reconcile active SDD artifact state`):
  `specs/dynamic-agent-runner/spec.md`, `plan.md`, and `tasks.md` now agree
  that planned implementation through package-alignment P5 is complete, there
  is no active implementation slice, the canonical API/CLI surface is
  package-directory-first, and future work should begin from deferred follow-up
  items or a new scoped spec update.
- Active evaluation follow-up ordering is now committed in `adba462`
  (`docs(spec): order active evaluation follow-ups`):
  `specs/dynamic-agent-runner/tasks.md` and `plan.md` now promote the remaining
  E/OA backlog into one active ordered queue with `OA2` as the next active
  slice, followed by OA3, OA1, OA4+E9, E11, OA5, OA6, OA7, OA10, OA9, OA8,
  and OA11.
- OA2 implementation/spec progress is now committed in `d2cc6b2`
  (`feat(registry): add tool provenance origins`): `ToolSource` now carries a
  higher-level provenance `origin` alongside the existing low-level source
  `kind`, defaulting manifest/tool-index/caller-registered tools to
  `registered`, built-ins to `built_in`, runtime overrides to `override`, and
  preserving explicit future `mcp` and `agent_as_tool` origins. The SDD docs
  now mark OA2 complete and advance the next active slice to OA3.
- Focused OA2 validation passed with `poetry run pytest tests/test_registry.py
  tests/test_artifacts.py tests/test_validation.py 2>&1` (68 passed) and
  `poetry run pre-commit run --files src/dynamic_agent_runner/models.py
  src/dynamic_agent_runner/registry.py tests/test_registry.py
  specs/dynamic-agent-runner/tasks.md specs/dynamic-agent-runner/plan.md 2>&1`.
- OA3 implementation/spec progress is now committed in `093ab47`
  (`feat(executor): add prepare-model-input stage`):
  `prepare_model_input(...)` now applies an explicit pre-adapter preparation
  stage that can inject hierarchical system/developer prompt parts, prune
  session-history messages, and compact pruned history into a summary message
  while `PreparedModelInput` preserves preparation metadata describing the
  transformation.
- Focused OA3 validation passed with `poetry run pytest tests/test_executor.py
  -q 2>&1` (47 passed) and `poetry run pre-commit run --files
  src/dynamic_agent_runner/executor.py tests/test_executor.py
  specs/dynamic-agent-runner/tasks.md specs/dynamic-agent-runner/plan.md 2>&1`.
- The next active follow-up slice is now OA1, with the active order updated to
  OA1, OA4+E9, E11, OA5, OA6, OA7, OA10, OA9, OA8, then OA11.
- Deferred backlog de-duplication across Codex/Cline and OpenAI Agents SDK
  Python follow-ups is now recorded in `specs/dynamic-agent-runner/tasks.md`:
  E10 is marked complete with overlap tracked in OA3, E12 is marked complete
  with overlap tracked in OA6, E9 is narrowed to unique MCP registry-source
  scope with OA4/OA2 covering the overlapping portions, and E11 is narrowed to
  unique hierarchical file-backed prompt-context scope with OA3 covering the
  broader prepare-stage overlap.
- Slice P5 is complete: the runtime now documents and validates
  `execution_policy.model_capabilities`, `execution_policy.model_map`,
  provider-neutral `llm_step.model_requirements`, ReAct-style `react_loop`
  manifests, package-declared RAG/GraphRAG classifications, and
  `evidence_loop` metadata using the existing primitive node taxonomy.
- `src/dynamic_agent_runner/validation.py` now enforces a minimal `react_loop`
  contract with positive `runtime.execution_policy.max_iterations`, loopback
  control flow, `runtime.state` observation metadata, and both `llm_step` and
  `tool_use_step` nodes.
- `tests/test_validation.py` covers failing and passing `react_loop` shapes, and
  `tests/test_executor.py` now covers the default async OpenAI adapter contract
  when no explicit adapters are provided for capability routing.
- The governing spec artifacts now explicitly track the newer upstream grouped
  contract boundaries: `runtime`, `metadata`, and `extensions` remain the shared
  manifest surface; future portable tool taxonomy is treated as semantic metadata
  rather than provenance; `handoff` vs `agent-as-tool` remains metadata rather
  than a new primitive node kind; portable approval/interruption metadata stays
  distinct from runtime-enforced approval engines; and concrete MCP discovery,
  injection, lifecycle, and extension-schema details remain downstream-owned.
- `specs/dynamic-agent-runner/tasks.md` now records OA11 as a deferred follow-up
  for mapping any future upstream portable tool-type taxonomy into local
  registry/policy handling without treating it as an MCP/source injection
  contract.
- Focused P5 validation passed with `poetry run pytest tests/test_validation.py
  tests/test_executor.py tests/test_model_capabilities.py tests/test_artifacts.py
  -q` (90 passed) and `poetry run pre-commit run --files
  src/dynamic_agent_runner/validation.py tests/test_validation.py
  tests/test_executor.py docs/files/artifact-package.rst
  docs/files/runtime-policies.rst README.md specs/dynamic-agent-runner/tasks.md`.
- The next active work item is no longer P5; the next slice should be chosen
  explicitly from the remaining backlog.
- A separate feature-spec track now exists for local llama.cpp support plus an
  internal graph-mutation/context-pruning layer, but the prototype code was
  intentionally reverted after spec capture. Current repository state preserves
  the design artifacts without active llama.cpp runtime code.
- Packaged local supporting references for OpenAI Model Registry capabilities,
  parameter validation, and advanced usage now exist under
  `cline-tasks/references/openai-model-registry/`. They were normalized to match
  repository markdown expectations before commit.
- Artifact loading now works for runtime YAML, optional Mermaid graph, optional
  `agent-design.md`, and optional `tool-index.yaml` inputs.
- `load_agent_workflow(...)` now loads generated artifacts without executing
  workflows, validates loaded artifacts, and returns the validated bundle.
- Validation now covers required manifest fields, supported enum values, node ID
  uniqueness, edge references, tool-use references, LLM prompt presence, and
  external tool-index structure. Slice 4 planning now clarifies that execution
  requires callable registry entries, with `tool-index.yaml` acting as optional
  metadata.
- The OpenAI adapter boundary now supports fake-client-compatible Responses API
  calls, request construction from rendered messages and optional tool schemas,
  response normalization, and `ModelExecutionError` wrapping.
- The workflow executor now supports execution state, LLM steps, tool-use steps,
  `llm_route` decisions, sequential and branch control flow, public
  `run_agent_workflow(...)` final-result execution, and fake-client/fake-tool
  executor tests.
- The repository now has hello-world runtime package fixtures for all 11
  documented supported agent patterns under `tests/fixtures/agent-patterns/`,
  with load/validation coverage in `tests/test_agent_pattern_fixtures.py`.
- CLI behavior now exists in `src/dynamic_agent_runner/cli.py`, with a
  `dynamic-agent-runner` console script, artifact path options, prompt input
  modes, opt-in read-only local workspace registry roots, stdout final-result
  output, and stderr/non-zero error reporting.
- `tests/test_cli.py` covers CLI execution with fixture artifacts and fake OpenAI
  clients only.
- `tests/test_cli.py` now runs the CLI across every currently executable
  hello-world pattern fixture with fake registry tools and fake OpenAI clients.
- Unsupported fixture behavior is explicit: `multi-agent-collaboration` fails
  clearly because `parallel_join` is not yet implemented by the executor.
- The spec now includes follow-on runtime hardening requirements for bounded
  retries, output-contract validation, token budgeting, and package-owned
  tracing hooks.
- Slice 8 adds `tenacity`, package-owned retry policy models, bounded retry
  execution for retryable model and tool failures, and retry outcome records
  on `WorkflowExecutionState`.
- Slice 9 validates `llm_step` output contracts and `llm_route` decision
  paths before trusting model output or traversing branches.
- Slice 10 adds `tiktoken`, package-owned token budget models, prompt-token
  preflight for configured `llm_step` calls, and `token_usage` records on
  `WorkflowExecutionState`.
- Slice 11 adds package-owned trace events, optional trace sinks, shallow
  redaction helpers, and `trace_events` records on `WorkflowExecutionState`.
- Slice 12 adds runtime behavior override support for per-node prompt patches and
  inline skill bindings without mutating generated artifacts.
- `specs/llm-step-interpreter-middleware/spec.md` now records a future optional
  interpreter middleware feature. It proposes caller-registered custom
  interpreters attachable to `llm_step` nodes and packages the original Deep
  Agents source note under the spec `references/` directory.
- Slice 13 adds provider-neutral prompt-cache intent support: optional
  `execution_policy.prompt_cache` metadata is parsed and validated, eligibility
  evidence is emitted as trace data, `prompt_cache=False` can disable behavior per
  execution, and provider cached-token telemetry is recorded when present.
- Runtime-package simplification Slice S4 adds `ToolSource` provenance metadata:
  manifest declarations, external tool-index entries, built-in local workspace
  tools, runtime overrides, and caller-registered tools now carry diagnostic
  source information. Model-request traces include `tool_sources` metadata for
  model-exposed tools without changing callable dispatch or exposure semantics.
  Full validation passed with 168 tests.
- Codex and Cline read-only evaluations are preserved under `cline-tasks/`, and
  `cline-tasks/codex-cline-combined-package-proposal.md` synthesizes acceptable
  package additions. The consolidated deferred follow-up backlog now lives in
  `specs/dynamic-agent-runner/tasks.md` rather than the spec body.
- Evaluation follow-up Slice A is complete: `WorkflowExecutionContext` /
  `RunContext` now groups loaded workflows and runtime collaborators,
  `execute_workflow(...)` and `run_agent_workflow(...)` accept context objects,
  ambiguous duplicate runtime arguments are rejected, and public exports/tests are
  updated. Full validation passed with 108 tests.
- Evaluation follow-up Slice B is complete: registry tool `input_schema`
  definitions are normalized through a shared validation path for OpenAI tool
  exposure and invocation input validation. Malformed object schemas, invalid
  `properties` / `required`, top-level schema combinators, and model-facing
  `$schema` metadata are handled explicitly. Full validation passed with 116
  tests.
- Evaluation follow-up Slice C is complete: `ToolExposure` now defines
  `direct`, `deferred`, `direct_model_only`, and `hidden`; model-facing tool
  schema exposure is filtered by exposure state; direct tool-step validation
  rejects model-only/deferred tools; `ToolPolicy` preserves side-effect,
  approval, sandbox, timeout, retry, and failure metadata separately from
  callable registration. Full validation passed with 121 tests.
- Evaluation follow-up Slice D is complete: `ToolResult` now has model-facing,
  raw, log-preview, event-payload, and sensitive-field facets; handlers can
  return structured `ToolResult` objects directly; downstream prompt/state
  references use model-facing output when present; and `tool_result` trace events
  include raw/log/event facets with sensitive-field metadata. Full validation
  passed with 123 tests.
- Evaluation follow-up Slice E is complete: tool execution now emits
  `tool_started` before direct tool invocation and `tool_finished` after tool
  results are recorded on both success and fail-closed error paths; existing
  `tool_invocation` and `tool_result` events remain for compatibility; fallback
  tool failures emit warning `status_notice` events. Full validation passed with
  125 tests.
- Evaluation follow-up Slice F is complete: `WorkflowLifecycleHooks` and stable
  hook context objects now support trusted in-process observations for node,
  model, tool, permission-boundary, and workflow lifecycle points. Hooks pass
  through `WorkflowExecutionContext`, `execute_workflow(...)`, and
  `run_agent_workflow(...)`; trusted hooks may raise project errors to abort
  execution, while shell hooks, plugin loading, and untrusted hook sources remain
  out of scope. Full validation passed with 129 tests.
- Evaluation follow-up Slice G / E2 is complete: `ModelCapabilities` now preserves
  context-window, structured-output, reasoning, modality, and parallel-tool-call
  support metadata from runtime `execution_policy.model_capabilities` on
  `RuntimeManifest`. The model is exported publicly and remains metadata-only for
  now, so capability declarations do not alter OpenAI request parameters. Full
  validation passed with 132 tests.
- E13 concurrent invocation support is implemented for the first planned
  customer scenario: `../power-marimo/`, a PySide6/qtpy application expected to
  run multiple QThreads with agents. The runtime now preserves per-run
  `WorkflowExecutionState` isolation, adds `run_id` correlation to execution
  state, trace events, and lifecycle hook contexts, and synchronizes current
  package-owned in-memory/shared helper surfaces.
- E14 async-first execution decisions are recorded in `56ddb9b`: future
  implementation should add first-class `execute_workflow_async(...)` and
  `run_agent_workflow_async(...)` APIs, make existing sync APIs wrappers that
  reject already-running event loops, use one async-canonical model-client
  protocol, inspect sync/async tool handlers and lifecycle hooks during
  registration/setup, attempt best-effort cancellation propagation, and preserve
  E13 run correlation for concurrent async runs. The local OpenAI Python SDK
  checkout at `/Users/roschuma/Repos/github/openai-python/` is available for E14
  async adapter and cancellation-behavior inspection.
- E14 implementation sequencing is recorded in
  `cline-tasks/evaluation-follow-up-implementation-plan.md`: async OpenAI client
  boundary, async retry helper, async-capable tool registry dispatch,
  async-capable lifecycle hook dispatch, async executor core, public async API and
  sync wrappers, then cancellation and concurrent async validation. Slices I.1
  through I.7 are complete; the planned E14 async-first implementation and
  validation sequence is complete.
- E14 Slice I.1 adds the async OpenAI client boundary: async protocol types,
  `AsyncOpenAIClientAdapter`, `create_default_async_openai_client()`, package
  exports, and fake-client tests while preserving shared request construction and
  response normalization. Focused validation passed with 11 tests.
- E14 Slice I.2 adds `run_with_retry_async(...)` using Tenacity async retry
  support, preserves async retry attempt counts, exports the helper publicly, and
  verifies that `asyncio.CancelledError` propagates without retry. Focused
  validation passed with 32 tests.
- E14 Slice I.3 adds async-capable tool dispatch: `RegisteredTool` records
  handler callable shape, `ToolRegistry` exposes `invoke_tool_async(...)`, async
  handlers are awaited directly, sync handlers run through `asyncio.to_thread(...)`,
  and async handler exceptions still become failed `ToolResult` values. Focused
  validation passed with 39 tests.
- E14 Slice I.4 adds async-capable lifecycle hook dispatch:
  `WorkflowLifecycleHooks` records configured callback shape in
  `RegisteredLifecycleHook` metadata, `invoke_lifecycle_hook_async(...)` invokes
  sync hooks or awaits async hooks, and the current sync executor compatibility
  path awaits async hooks when no event loop is already running. Focused
  validation passed with 39 tests.
- E14 Slice I.5 adds the async executor core: `execute_workflow_async(...)` now
  drives an async workflow loop and async node helper paths, awaits async model
  calls through `AsyncOpenAIClientAdapter`, awaits direct tool dispatch through
  `ToolRegistry.invoke_tool_async(...)`, awaits lifecycle hooks through
  `invoke_lifecycle_hook_async(...)`, preserves existing retry, token-budget,
  prompt-cache, output-contract, tracing, route, and state behavior, and originally
  rejected async model adapters from the synchronous executor path. Targeted
  validation passed with 101 tests.
- E14 Slice I.6 adds public async API and sync wrapper wiring:
  `run_agent_workflow_async(...)` loads, validates, executes through
  `execute_workflow_async(...)`, and returns the final result; package root exports
  `execute_workflow_async(...)` and `run_agent_workflow_async(...)`; sync
  `execute_workflow(...)` and `run_agent_workflow(...)` wrap the async semantic
  path through `_run_async_from_sync(...)`; sync wrappers call `asyncio.run(...)`
  only when no event loop is active and raise `WorkflowExecutionError` from an
  already-running event loop. Targeted validation passed with 55 tests; broader
  async-adjacent validation passed with 122 tests.
- E14 Slice I.7 completes cancellation and concurrent async validation:
  `tests/test_concurrency.py` now covers in-flight async workflow cancellation
  propagation, workflow cancellation trace and `after_workflow` hook observations,
  concurrent async runs reusing one execution context with distinct run IDs,
  shared trace-sink and hook run correlation, and sync/async public API parity for
  final results and trace event shapes. Focused validation passed with 43 tests;
  broader async-adjacent validation passed with 129 tests.
- OpenAI Agents SDK Python evaluation from `322ce13` adds
  `cline-tasks/openai-agents-python-evaluation.md` and records deferred OA1-OA10
  follow-ups in `specs/dynamic-agent-runner/spec.md` and `tasks.md`.
  The new deferred concepts cover guardrail metadata, tool provenance,
  prepare-model-input seams, MCP lifecycle diagnostics, tool-use completion
  policy, handoff versus agent-as-tool metadata, approval interruption/resume
  state, session protocols, optional callable-to-tool helpers, and
  sandbox/workspace runtime separation.
- Runtime-package simplification analysis from `c710490` adds
  `cline-tasks/agent-runtime-package-simplification-analysis.md` and
  `cline-tasks/agent-development-skill-runtime-package-feature-request.md`.
  The analysis recommends keeping the primitive graph executor, grouping manifest
  complexity into `runtime`, `metadata`, and `extensions`, adding internal
  `ExecutionPlan` / `PreparedNode` and `PreparedModelInput` seams, and deferring
  sessions, approvals, sandbox/workspace runtime, and iterative agent-loop
  semantics until explicitly scoped.
- First-customer prioritization from `0af68ab` adds
  `specs/dynamic-agent-runner/references/power-marimo-agent-support-analysis.md`
  and updates `spec.md` / `tasks.md` to make runtime-package simplification the
  next active sequence.
- Runtime-package simplification Slice S1 is complete in `695c0cc`:
  `RuntimeManifest` now preserves grouped `runtime`, `metadata`, and
  `extensions` maps, derives convenience accessors from grouped sections,
  indexes array-shaped `output_contracts`, validates extension envelopes,
  rejects legacy flat optional root fields, and migrates agent-pattern fixtures
  plus tests to the grouped shape. Full validation passed with 164 tests.
- Plan/task evidence for S1 is recorded in `0f795ee`.
- Runtime-package simplification Slice S2 is complete in `b315c96`:
  `ExecutionPlan` and `PreparedNode` now provide an internal prepared execution
  view with node lookup, outgoing-edge indexes, max-step defaults, per-node
  model/tool/decision fields, output-contract references, token/retry policy
  values, and optional unsupported extension visibility. The executor routes
  finite graph behavior through prepared nodes while preserving public behavior.
  Full validation passed with 165 tests.
- Plan/task evidence for S2 is recorded in `1f91804`.
- Runtime-package simplification Slice S3 is complete in `33096b5`:
  `PreparedModelInput` captures rendered messages plus named prompt parts, and
  `prepare_model_input(...)` centralizes prompt rendering, prompt-cache
  observation, token-budget preflight, and behavior override integration for
  `llm_step` execution. Full validation passed with 166 tests.
- Plan/task evidence for S3 is recorded in `b730592`.
- Runtime-package simplification Slice S4 is complete in `a46bb5a`:
  `ToolSource` / `ToolSourceKind` now preserve diagnostic provenance for
  manifest declarations, external tool-index entries, built-in local workspace
  tools, runtime overrides, and caller-registered tools. Model-request traces
  include `tool_sources` metadata for model-exposed tools without changing
  callable dispatch or exposure semantics. Full validation passed with 168 tests.
- Plan/task evidence for S4 is recorded in `2d30581`.
- S5 planning records that `marimo-pair` should be modeled as an agent-as-tool
  invocation backed by `../power-marimo/skills/marimo-pair/SKILL.md`, not as a new
  primitive runtime node kind or durable handoff-style multi-agent pattern.
- Runtime-package simplification Slice S5 is complete in `84dfd31`: a
  placeholder-safe Power-Marimo runtime package fixture now represents a
  supervised bounded workflow-orchestration agent, records `marimo-pair` as a
  SKILL-backed agent-as-tool `tool_use_step`, defines placeholder Marimo/domain
  tools, and exercises the bounded happy path with fake tools and fake model
  responses. Targeted validation passed with 4 tests.
- Plan/task evidence for S5 is recorded in `387b574`; governing spec documents
  were refreshed for S5 completion in `89926d8`; runtime-package simplification
  S1-S5 is complete.

## In Flight

- E11 memory-bank refresh is in flight after implementation/spec-doc commit
  `3cdc7e9` (`feat(executor): add bounded file context preparation`).
- Remaining active follow-up work is now explicitly ordered: OA5, OA6, OA7,
  OA10, OA9, OA8, then OA11.

## Remaining

- Choose the next scoped follow-up before broader E9, OA, MCP, durable session,
  approval-resume, or PyQt-widget automation work.
- Use `8308cd6` as the current planning checkpoint for package-alignment work
  against the upstream runtime-package contract before selecting the next
  implementation slice.
- Preserve the S5 `marimo-pair` shape as an agent-as-tool/SKILL-backed bounded
  Marimo operation while keeping primitive node kinds unchanged.
- Extend from the completed grouped manifest, prepared execution plan,
  prepared model input, tool provenance, loader, validation, registry, OpenAI
  adapter, executor, CLI, behavior-override, and all-pattern fixture foundation
  into the next scoped slice.
- Use the all-pattern hello-world fixtures as the broad pattern test surface for
  future compatibility coverage, including expected-failure coverage for pattern
  features that are represented in artifacts but not yet implemented.
- Update the memory bank after each future meaningful implementation
  milestone.
- Record the OA1 memory-bank checkpoint after the separate docs(memory-bank)
  commit is created.

## Risks or Follow-ups

- Loader, validation, registry, OpenAI adapter, executor, and CLI source now
  exist, but architecture sections should remain conservative until the next
  scoped runtime behavior is planned.
- Slice 7 is complete, but unrestricted runtime implementation should still
  proceed slice-by-slice from the committed task list or an updated follow-on
  plan.
- The library-evaluation roadmap prioritizes Tenacity-style retries,
  output-contract enforcement, tiktoken-based token budgeting, and package-owned
  tracing hooks. Those runtime hardening slices are now complete. LiteLLM,
  Watchfiles, Rich, and Diskcache are deferred unless a later scoped
  requirement justifies them.
- Future sessions should verify artifact schemas before implementing parser or
  execution behavior.
- Supported agent-pattern IDs are preserved by loader/model work; full executor
  support still depends on later primitive node, edge, tool, policy, and adapter
  implementation.
- Future implementation should start with the official `openai` package and a
  repository-owned tool registry pattern; `ocihelper`, `ai-tools-core`, and
  `openai-tools-core` are intentionally not required by the latest spec.
- Slice 4 preserves the distinction between optional tool-index metadata and
  executable registry tools; metadata-only tools cannot satisfy runtime tool
  dependencies.
- Slice 5 preserves the OpenAI SDK behind a small adapter boundary and keeps unit
  tests free of live model calls.
- Slice 6 implements minimal executor semantics only; more advanced edge kinds,
  policies, approvals, and tool-call loops remain future extension areas.
- Slice 7 implements a minimal CLI over existing public seams; richer registry
  configuration, live-model ergonomics, and production packaging behavior remain
  future extension areas.
- Slice 8 implements retry/resilience for model and tool call sites only;
  broader output repair, token budgeting, trace sinks, and advanced workflow
  policies remain future slices.
- Slice 9 implements output contract and route validation only; model-assisted
  repair, Instructor-style retries, richer JSON Schema validation, and route
  repair remain future extension areas.
- Slice 10 implements token estimation and fail-fast budget enforcement only;
  automatic truncation, summarization, and CLI token-reporting UX remain future
  extension areas.
- Slice 11 implements package-owned trace events and optional trace sinks only;
  external Logfire/OpenTelemetry integration, deep recursive redaction, and
  richer production observability remain future extension areas.
- Slice 12 implements inline skill instructions and prompt-role placement only;
  arbitrary `SKILL.md` source-path resolution remains deferred until trust,
  packaging, and precedence rules are specified.
- Slice 13 intentionally stops short of provider-specific prompt-cache request
  pass-through; that remains adapter-gated until exact SDK/API support is
  verified.
- Codex/Cline follow-ups E1, E2, E3, E4, E5, E6, E7, E8, E13, and E14 are
  implemented. Backlog de-duplication now marks E10 and E12 complete by
  directing their overlap to OA3 and OA6 respectively, leaving E9 and E11 as
  the remaining unique deferred Codex/Cline follow-ups to introduce through
  package-owned contracts before broad integrations such as MCP, plugins, shell
  hooks, app-server protocols, or multi-provider routing.
- OpenAI Agents SDK Python follow-ups OA1-OA11 are deferred design inputs, not
  current implementation scope. Guardrails, approval pause/resume state, sessions,
  sandbox/workspace execution, and iterative agent-loop completion policy should
  each require a fresh scoped spec/update before implementation.
- Runtime-package simplification S1-S5 is complete, driven by the `power-marimo`
  first-customer analysis and reflected in governing spec documents through
  `89926d8`. S1 grouped manifest support, S2 `ExecutionPlan` / `PreparedNode`
  normalization, S3 `PreparedModelInput` / `prepare_model_input(...)`, S4
  `ToolSource` provenance, and S5 placeholder-safe Power-Marimo fixture coverage
  are complete. Live Marimo-session, MCP, broader agent-as-tool registry sources,
  and durable handoff/resume behavior remain out of scope until a new scoped
  follow-up selects them.
- The latest upstream `agent-development-skill` runtime-package reference now
  materially extends local package-alignment scope beyond package-directory
  loading: future alignment work should preserve provider-neutral
  `model_requirements`, ReAct `react_loop` structure, `metadata.rag_pipeline`
  for RAG / GraphRAG shapes, and `evidence_loop` metadata without adding new
  primitive node kinds unless a later scoped runtime slice explicitly requires
  them.
- Generated RAG, embedding-backed retrieval, graph retrieval, and GraphRAG
  package shapes are now supported at the metadata/validation layer. This does
  not add executable vector-store, graph-store, retrieval, reranking, or indexing
  integrations; those remain future scoped implementation work.
- E13 is complete for the current package-owned contract: run correlation,
  synchronized current in-memory/shared helpers, lazy adapter initialization
  protection, registry mutation/read behavior, and concurrent tests.
  Caller-provided mutable tool handlers and lifecycle hooks remain
  caller-managed for synchronization.
- E14 async-first implementation work is complete through the planned slice
  sequence: true async public APIs, sync wrappers that reject already-running event
  loops, one async-canonical model-client protocol, registration/setup-time
  callable-shape inspection for tools and hooks, best-effort cancellation
  propagation, and acceptance coverage for async model calls, async tools, async
  hooks, cancellation, sync wrapper compatibility, and concurrent async runs.
  Slices I.1 through I.7 completed the async OpenAI adapter, retry, tool-dispatch,
  lifecycle-hook, async executor-core, public API/sync-wrapper, cancellation, and
  concurrent async validation boundaries.
- Interpreter middleware is specified only as a future feature; custom
  interpreter interface details, dependency availability, safety gates,
  benchmark fixtures, and backend selection remain unresolved.
- `parallel_join`, `parallel_fanout`, and broader multi-agent execution are still
  unsupported runtime behavior. The CLI test suite now checks that this fails
  clearly instead of silently succeeding.
- The all-pattern fixtures validate package shape and pattern metadata coverage;
  they now also provide CLI coverage for currently executable fixture shapes, but
  they still do not prove full runtime execution support for every
  pattern-specific behavior.
- Memory-bank pre-commit validation for this refresh should be recorded in the
  commit result.
