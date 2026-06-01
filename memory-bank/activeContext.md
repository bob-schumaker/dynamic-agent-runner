# Active Context

## Current Focus

- E14 async-first execution is complete through the planned Slice I.7
  validation sequence. Slice I.7 completed cancellation and concurrent async
  validation in commit `7990503`; governing docs were refreshed in `27f409b`.
  OpenAI Agents SDK Python was evaluated in `322ce13`, adding deferred OA1-OA10
  follow-ups. Runtime-package simplification analysis was added in `c710490`,
  including an upstream feature-request handoff for the agent-development skill
  repo. The first-customer `../power-marimo` fit analysis and grouped-manifest
  spec/task update were committed in `0af68ab`. Runtime-package
  simplification Slice S1 completed in `695c0cc`, with plan/task evidence
  recorded in `0f795ee`. Slice S2 completed in `b315c96`, with plan/task
  evidence recorded in `1f91804`. Slice S3 completed in `33096b5`, with
  plan/task evidence recorded in `b730592`. Slice S4 completed in `a46bb5a`,
  plan/task evidence recorded in `2d30581`. The S5 design decision that
  `marimo-pair` is an agent-as-tool invocation backed by
  `../power-marimo/skills/marimo-pair/SKILL.md` was recorded in `a084f2d`. Slice
  S5 completed in `84dfd31`, with plan/task evidence recorded in `387b574` and
  governing spec documents refreshed in `89926d8`; the runtime-package
- Package-alignment Slice P1 is complete in commit `63403d3`, Slice P2 is
  complete in commit `a1880e7`, Slice P3 is complete in commit `a46cd13`, Slice
  P4 is complete in commit `3e622d2`, and Slice P5 is now complete in commit
  `7e9a33e`. P2 adds strict canonical
  package validation:
  package-loaded workflows now preserve optional `skill_bundle_root`,
  `load_agent_package(...)` fails closed for missing canonical sibling artifacts
  (`agent-design.md`, `agent-graph.mmd`), and workflow validation now checks
  package-local `skills[*].bundled_path` plus
  `skills[*].support_files[*].bundled_path` entries against the configured
  package `skill-bundle/` directory.
- P3 adds an explicit compiled-workflow layer: `CompiledAgentWorkflow` now
  preserves an immutable loaded base workflow while package and loaded-workflow
  compile helpers layer caller-owned runtime overrides into the final
  execution-ready workflow. Public API, execution context, and executor entry
  points now accept the compiled workflow form without mutating the base package.
- P4 makes the package directory the canonical public API and CLI contract:
  `load_agent_workflow(...)`, `run_agent_workflow(...)`, and
  `run_agent_workflow_async(...)` now accept `package_directory` as the main
  public input, the CLI now uses `--package`, and docs describe the immutable
  base package + caller override + compiled workflow model. Compatibility
  file-by-file artifact inputs remain available as lower-level seams.
- Package validation now requires the package `skill-bundle/` directory only
  when bundled skill or support-file paths are actually declared, matching the
  existing canonical fixture contract for packages that set
  `packaging.skill_bundle_dir` but use referenced-only skills.
- P5 aligns the public contract with the newer upstream runtime-package
  taxonomy: docs and validation now explicitly cover
  `execution_policy.model_capabilities`, `execution_policy.model_map`,
  provider-neutral `llm_step.model_requirements`, ReAct-style `react_loop`
  manifests, package-declared RAG/GraphRAG classifications, and
  `evidence_loop` metadata.
- `src/dynamic_agent_runner/validation.py` now validates `react_loop` manifests
  as primitive-node workflows with positive
  `runtime.execution_policy.max_iterations`, at least one `loopback` edge,
  `runtime.state` observation metadata, and both `llm_step` and `tool_use_step`
  nodes.
- `tests/test_executor.py` now documents the default model-adapter contract:
  when callers do not provide explicit adapters and a node does not require
  capability-based routing, the executor constructs the default async OpenAI
  adapter for the requested model name. Capability-aware or local-only routing
  requires explicit manifest-driven metadata.
- Package-alignment backlog review against the latest upstream
  `agent-development-skill` runtime-package reference is now committed in
  `8308cd6`. `specs/dynamic-agent-runner/tasks.md` now records that package-
  alignment must cover not only immutable base package directories and
  `skill-bundle/` handling, but also provider-neutral `model_requirements`,
  ReAct-style `react_loop` manifests, RAG/GraphRAG metadata, and the upstream
  `evidence_loop` pattern.
- The active SDD artifact set was reconciled in commit `3c5e2e9`
  (`docs(spec): reconcile active SDD artifact state`). `spec.md`, `plan.md`,
  and `tasks.md` now agree that planned implementation through package-
  alignment P5 is complete.
- Active follow-up ordering was first committed in `adba462`
  (`docs(spec): order active evaluation follow-ups`). `tasks.md` and `plan.md`
  promoted the remaining Codex/Cline and OpenAI Agents SDK Python follow-up
  work into one explicit active backlog, OA2 implementation/spec progress is now
  recorded in `d2cc6b2` (`feat(registry): add tool provenance origins`), and
  OA3 implementation/spec progress is now recorded in `093ab47`
  (`feat(executor): add prepare-model-input stage`).
- OA2 is now complete in `d2cc6b2`: `ToolSource` preserves the existing
  low-level source `kind` while adding a higher-level `origin` bucket that
  distinguishes registered, built-in, override, and future MCP or
  agent-as-tool origins without collapsing provenance into any future portable
  tool-type taxonomy.
- OA3 is now complete in `093ab47`: `prepare_model_input(...)` is now the
  dedicated pre-adapter preparation seam for hierarchical prompt injection,
  session-message pruning, and summary-style context compaction, and
  `PreparedModelInput` preserves metadata describing those transformations.
- OA1 is now complete in `a834a90`: `RuntimeManifest` preserves deferred
  guardrail declarations from `extensions.guardrails.declarations`, covering the
  `input`, `output`, `tool_input`, and `tool_output` phases plus `abort` and
  `reject_content` tripwire behavior metadata.
- OA4+E9 is now complete in `20f20d1`: `RuntimeManifest` preserves deferred MCP
  registry-source metadata from `extensions.mcp_registry_sources.sources` and
  deferred MCP lifecycle diagnostics metadata from
  `extensions.mcp_lifecycle_diagnostics`, covering source visibility/status,
  tool-cache policy, disabled state, operation-locking, memory-pollution,
  strict/degraded startup, reconnect policy, cleanup timeout, and state keys for
  active/failed servers plus error maps.
- E11 is now complete in `3cdc7e9`: `prepare_model_input(...)` supports an
  opt-in `runtime.execution_policy.prepare_model_input.file_context` policy for
  package-root-backed workflows, adding deterministic file-context prompt parts,
- OA5 is now complete in `3d33bbb`: `RuntimeManifest` and `ExecutionPlan` now
  preserve deferred `runtime.execution_policy.tool_use_completion` metadata for
  future iterative agent-loop runtimes, covering `run_again`, `stop_on_tool`,
  `final_output`, and `final_output_state_key` without changing current executor
  semantics.
- OA5 validation passed with `poetry run pytest tests/test_validation.py
  tests/test_executor.py -q 2>&1` (83 passed) and scoped `pre-commit` on the
  OA5 code/spec files.
- OA6 is now complete in `d5f4114`: `RuntimeManifest` preserves grouped
  `metadata.handoffs`, `RuntimeNode` / `PreparedNode` preserve typed node-local
  `agent_as_tool` / `agent_tool` metadata, and `ExecutionPlan` carries both
  metadata surfaces forward without changing current executor semantics.
- OA6 validation passed with `poetry run pytest tests/test_artifacts.py
  tests/test_validation.py tests/test_executor.py tests/test_power_marimo_fixture.py
  -q 2>&1` (106 passed) and scoped `pre-commit` on the OA6 code/spec files.
- The next active implementation slice is now `OA7` — design workflow
  interruption and resumable run state for approval-required tools.
- The current active follow-up order is:
  OA7, OA10, OA9, OA8, then OA11.
- Current runtime implementation work narrows the new model-routing changes to
  better fit the spec: multiple adapters and manifest-driven
  `runtime.execution_policy.model_map` selection remain, but premature public
  `model_map` override exposure was removed and capability mismatches now fail
  closed instead of inventing implicit local fallback adapters.
- A new feature-spec checkpoint is now committed in `1346458` for
  llama.cpp-backed local-model support and an internal graph-mutation layer for
  context pruning. The implementation prototype itself was intentionally
  reverted after the spec/design capture, leaving the repository code in its
  prior OpenAI-first state while preserving:
  - `specs/llama-cpp-graph-mutation/spec.md`
  - `specs/dynamic-agent-runner/references/graph-mutation-interface-design.md`
- Packaged OpenAI Model Registry reference notes are now committed in `7a7a54e`
  under `cline-tasks/references/openai-model-registry/`. Those imported notes
  required repository-local markdown normalization to satisfy pre-commit before
  commit, and now serve as local supporting reference material for future model
  capability, parameter-validation, and advanced-usage work.
- The upstream runtime-package reference at
  `../clinerules-roschuma/skills/agent-development-skill/references/agent-runtime-package.md`
  now explicitly defines grouped manifest taxonomy, provider-neutral
  `model_requirements`, ReAct loop conventions, RAG/GraphRAG metadata guidance,
  and `evidence_loop` packaging guidance. Local package-alignment planning should
  stay synchronized to that upstream contract before selecting the next runtime
  slice.
- The latest governing-doc refresh commit is `cf66be2`
  (`docs(spec): align runtime-package surface guidance`). It updates
  `specs/dynamic-agent-runner/spec.md`, `plan.md`, and `tasks.md` so the local
  docs explicitly track the current upstream grouped-contract surface and the
  ownership split around:
  - grouped `runtime` / `metadata` / `extensions` usage
  - portable tool-type taxonomy as future shared semantic metadata
  - `handoff` vs `agent-as-tool` as grouped manifest metadata, not a new
    primitive node kind
  - portable approval/interruption metadata versus runtime-enforced approval
    engines
  - concrete MCP discovery, injection, lifecycle, and extension-schema details
    remaining downstream-owned
- `specs/dynamic-agent-runner/tasks.md` has now been de-duplicated across the
  deferred Codex/Cline (`E*`) and OpenAI Agents SDK Python (`OA*`) follow-up
  sections so overlap is tracked in one place:
  - E10 is now marked complete with completion tracked in OA3.
  - E12 is now marked complete with completion tracked in OA6.
  - E9 now keeps only its unique MCP registry-source scope, with lifecycle
    diagnostics tracked in OA4 and provenance distinctions tracked in OA2.
  - E11 now keeps only its unique hierarchical file-backed prompt-context scope,
    while the broader prepare-stage/context-compaction design is tracked in OA3.

## Current Status

- Done:
  - Committed packaged OpenAI Model Registry reference notes in `7a7a54e`.
  - Committed the feature-spec/design checkpoint for llama.cpp local-model
    support and graph mutation in `1346458`.
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
  - Completed E13 concurrent invocation support in `2e45888`, adding `run_id`
    correlation and synchronized package-owned shared helpers for QThread-style
    callers.
  - Updated governing spec/plan/task documents for completed E13 support in
    `a4fe7e9`.
  - Updated governing spec/plan/task documents for E14 async-first execution
    decisions in `56ddb9b`.
  - Updated governing spec/plan documents with the local OpenAI Python SDK source
    checkout for E14 async feasibility inspection in `4b17a4f`.
  - Added detailed E14 implementation sequencing to
    `cline-tasks/evaluation-follow-up-implementation-plan.md` in `c22c239`.
  - Updated governing spec/plan/task documents to reference the E14 plan and
    recommended first slice in `781f451`.
  - Completed E14 Slice I.1 async OpenAI client boundary in `acca9da`, adding
    async OpenAI protocol types, `AsyncOpenAIClientAdapter`,
    `create_default_async_openai_client()`, package exports, and fake-client tests.
  - Updated governing spec/plan/task documents and the E14 implementation plan for
    Slice I.1 completion evidence in `e750f3b`.
  - Completed E14 Slice I.2 async retry helper in `f2296e9`, adding
    `run_with_retry_async(...)`, public exports, attempt-count tests, and
    cancellation propagation coverage.
  - Updated governing spec/plan/task documents and the E14 implementation plan for
    Slice I.2 completion evidence in `bb96b54`.
  - Completed E14 Slice I.3 callable-shape metadata for tools in `ff144f5`, adding
    `RegisteredTool.handler_is_async`, `invoke_tool_async(...)`, awaited async
    handlers, and `asyncio.to_thread(...)` dispatch for sync handlers.
  - Updated governing spec/plan/task documents and the E14 implementation plan for
    Slice I.3 completion evidence in `804e1af`.
  - Completed E14 Slice I.4 callable-shape metadata for lifecycle hooks in
    `2b9271b`, adding `RegisteredLifecycleHook`, recorded hook callable-shape
    metadata, `invoke_lifecycle_hook_async(...)`, package exports, and executor
    compatibility support that awaits async hooks when no event loop is running.
  - Updated governing spec/plan/task documents and the E14 implementation plan for
    Slice I.4 completion evidence in `a204898`.
  - Completed E14 Slice I.5 async executor core in `72c28dd`, adding
    `execute_workflow_async(...)`, async workflow/node helper paths, awaited async
    model calls, awaited direct tool dispatch, awaited lifecycle hook dispatch,
    and a sync-path guard for async model adapters.
  - Updated governing spec/plan/task documents and the E14 implementation plan for
    Slice I.5 completion evidence in `09a2900`.
  - Completed E14 Slice I.6 public async API and sync wrappers in `4f279ff`,
    adding `run_agent_workflow_async(...)`, exporting public async APIs, converting
    sync entry points into wrappers over the async semantic path, and rejecting
    already-running event loops from sync wrappers.
  - Updated governing spec/plan/task documents and the E14 implementation plan for
    Slice I.6 completion evidence in `b698de9`.
  - Completed E14 Slice I.7 cancellation and concurrent async validation in
    `7990503`, adding tests for in-flight async workflow cancellation propagation,
    workflow cancellation trace/hook observations, concurrent async shared-context
    run correlation, and sync/async public entry-point parity.
  - Updated governing spec/plan/task documents and the E14 implementation plan for
    Slice I.7 completion evidence in `27f409b`.
  - Added OpenAI Agents SDK Python evaluation and deferred OA1-OA10 spec/task
    follow-ups in `322ce13`.
  - Added runtime-package simplification analysis and an upstream
    agent-development skill feature-request handoff in `c710490`.
  - Added first-customer `power-marimo` agent-support analysis and prioritized
    runtime-package simplification follow-up S1-S5 in `0af68ab`.
  - Completed runtime-package simplification Slice S1 in `695c0cc`, adding
    grouped `runtime`, `metadata`, and `extensions` manifest parsing,
    array-shaped `output_contracts`, extension-envelope validation, legacy
    flat-root rejection, and grouped agent-pattern fixtures. Full validation
    passed with 164 tests.
  - Updated `specs/dynamic-agent-runner/tasks.md` and
    `cline-tasks/power-marimo-implementation-plan.md` for S1 completion evidence
    and next active S2 in `0f795ee`.
  - Completed runtime-package simplification Slice S2 in `b315c96`, adding
    internal `ExecutionPlan` / `PreparedNode` preparation models and routing
    executor behavior through prepared nodes while preserving finite graph
    behavior. Full validation passed with 165 tests.
  - Updated `specs/dynamic-agent-runner/tasks.md` and
    `cline-tasks/power-marimo-implementation-plan.md` for S2 completion evidence
    and next active S3 in `1f91804`.
  - Completed runtime-package simplification Slice S3 in `33096b5`, adding
    `PreparedModelInput` and `prepare_model_input(...)` as the model-input
    preparation seam for `llm_step` execution while preserving prompt rendering,
    prompt-cache observation, token-budget preflight, and behavior override
    semantics. Full validation passed with 166 tests.
  - Updated `specs/dynamic-agent-runner/tasks.md` and
    `cline-tasks/power-marimo-implementation-plan.md` for S3 completion evidence
    and next active S4 in `b730592`.
  - Completed runtime-package simplification Slice S4 in `a46bb5a`, adding
    `ToolSource` / `ToolSourceKind` provenance metadata for manifest,
    tool-index, built-in, runtime override, and caller-registered tools.
    Model-request traces now include diagnostic `tool_sources` for exposed
    tools, and full validation passed with 168 tests.
  - Updated `specs/dynamic-agent-runner/tasks.md` and
    `cline-tasks/power-marimo-implementation-plan.md` for S4 completion evidence
    and next active S5 in `2d30581`.
  - Recorded the S5 `marimo-pair` design decision in `a084f2d`: the fixture should
    model `marimo-pair` as an agent-as-tool invocation backed by
    `../power-marimo/skills/marimo-pair/SKILL.md`, distinct from primitive node
    kinds and handoff-style multi-agent metadata.
  - Completed runtime-package simplification Slice S5 in `84dfd31`, adding a
    placeholder-safe Power-Marimo runtime package fixture and fake-tool execution
    coverage for the bounded happy path.
  - Updated `specs/dynamic-agent-runner/tasks.md` and
    `cline-tasks/power-marimo-implementation-plan.md` for S5 completion evidence
    and runtime-package simplification completion in `387b574`.
  - Updated governing spec documents in `89926d8` to record S5 completion, the
    placeholder-safe Power-Marimo fixture, and that no next active slice is
    selected after S5.
  - Added uncommitted RAG/embedding manifest support for generated runtime
    packages: model metadata preserves an `embeddings` capability,
    `RuntimeManifest` preserves `metadata.rag_pipeline`, `RuntimeNode` /
    `PreparedNode` preserve `llm_step.model_requirements`, validation checks RAG
    pipeline and model-requirement consistency, and docs/tests cover the new
    manifest shape.
- In progress:
  - Memory-bank refresh is being prepared to record OA6 completion commit
    `d5f4114` and the next active slice transition to OA7.
- Not started:
  - Provider-specific prompt-cache request pass-through is deferred until exact
    SDK/API support is verified; Slice 13 records metadata and telemetry only.
  - Interpreter middleware implementation is not started; the future spec
    explicitly defers backend selection until prototypes and benchmarks exist.
- Remaining active follow-up work is now explicitly ordered rather than left
    as a generic deferred pool. The current sequence is OA2, OA3, OA1,
    OA4+E9, E11, OA5, OA6, OA7, OA10, OA9, OA8, then OA11. E14 Slices I.1
    through I.7 remain complete.

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
  C, D, E, F, G, H / E13, E14, and runtime-package simplification
  S1-S5 are complete; E9, E10, E11, and E12 remain deferred follow-up
  candidates.
- `cline-tasks/codex-cli-evaluation.md`, `cline-tasks/cline-evaluation.md`, and
  `cline-tasks/openai-agents-python-evaluation.md` capture read-only external
  runtime-pattern evaluations. The Codex/Cline synthesized proposal lives at
  `cline-tasks/codex-cline-combined-package-proposal.md`.
- `cline-tasks/agent-runtime-package-simplification-analysis.md` captures the
  analysis that runtime-package complexity should be organized into core
  executable fields, runtime policy, design metadata, and extension capability
  declarations.
- `cline-tasks/agent-development-skill-runtime-package-feature-request.md`
  packages that analysis as an upstream feature-request handoff for the
  `clinerules-roschuma` agent-development skill repository.
- `specs/dynamic-agent-runner/tasks.md` commit `8308cd6` updates the local
  package-alignment backlog to track upstream runtime-package guidance for
  immutable package directories, `skill-bundle/` validation, provider-neutral
  `model_requirements`, ReAct-style `react_loop` manifests, RAG / GraphRAG
  metadata, and `evidence_loop` pattern handling.
- `specs/dynamic-agent-runner/references/power-marimo-agent-support-analysis.md`
  records `../power-marimo` as the first downstream consumer fit: a supervised,
  bounded workflow-orchestration agent for AI-assisted Marimo notebook power
  experiments, not a free-form autonomous notebook agent.
- S5 models the downstream `marimo-pair` capability as an agent-as-tool
  invocation backed by `../power-marimo/skills/marimo-pair/SKILL.md`, not as a
  new primitive runtime node kind or durable handoff-style multi-agent pattern.
  The fixture is placeholder-safe and uses fake tools, synthetic domain output,
  and placeholder Marimo metadata only.
- `specs/dynamic-agent-runner/tasks.md` now contains `Active Codex/Cline
  evaluation follow-ups` and `Active OpenAI Agents SDK Python evaluation
  follow-ups`, with `OA2` selected as the next active slice and an explicit
  recommended active implementation order recorded near the top of the file. E1
  is complete and checked off with
  implementation commit `38929f1`, E3 is complete and checked off with
  implementation commit `44b0847`, E4/E5 are complete and checked off with
  implementation commit `61f1548`, E6 is complete and checked off with
  implementation commit `815f55a`, E7 is complete and checked off with
  implementation commit `bf18554`, E8 is complete and checked off with
  implementation commit `bcd76d4`, and E2 is complete and checked off with
  implementation commit `13c6dac`. `spec.md`, `plan.md`, `tasks.md`, and
  `cline-tasks/evaluation-follow-up-implementation-plan.md` were refreshed for
  Slice G / E2 in `97fe320`.
  E13 is complete in `2e45888` and documented in `a4fe7e9`: execution state now
  carries per-run `run_id`, trace events and lifecycle hook contexts are
  run-correlated, and package-owned in-memory/shared helpers are synchronized for
  concurrent QThread-style callers. E14 decisions are now recorded in `56ddb9b`:
  true async execution is the first-class runtime path, sync APIs are wrappers
  that reject already-running event loops, model clients are async-canonical,
  tools and hooks are inspected during registration/setup, cancellation is
  best-effort, and concurrent async runs must preserve E13 run correlation. The
  local OpenAI Python SDK checkout at `/Users/roschuma/Repos/github/openai-python/`
  was inspected for the async adapter boundary. The detailed E14 implementation
  plan is in `cline-tasks/evaluation-follow-up-implementation-plan.md`; Slices
  I.1 through I.7 are complete in `acca9da`, `f2296e9`, `ff144f5`, `2b9271b`,
  `72c28dd`, `4f279ff`, and `7990503`; the planned E14 async-first
  implementation and validation sequence is complete.
  The backlog review now treats OA3/OA4/OA6 as the canonical source for
  the overlapping prepare-stage, MCP-lifecycle-diagnostics, and handoff-vs-agent-
  as-tool design work; E10 and E12 are marked complete to point at those OA
  items, while E9 and E11 retain only their unique residual scope.
- Supported agent patterns from the upstream agent-development skill are now
  treated as manifest metadata, not as new primitive runtime node kinds. Slice 2
  now preserves `patterns_present`, `participant_groups`, `modes`, `phases`, and
  `roles` metadata during loading.
- RAG, embedding-backed retrieval, graph retrieval, and GraphRAG from the
  agent-development skill remain represented with existing primitive node kinds.
  The runner now supports their generated metadata shape by preserving
  `metadata.rag_pipeline` and validating RAG pattern consistency instead of adding
  new primitive runtime node kinds.
- `llm_step.model_requirements` is provider-neutral selection guidance. It may
  require capabilities such as `embeddings`, structured output, long context,
  tool calling, or citation generation, but it must not be passed through as a
  provider API request parameter.
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
- Evaluation follow-up Slice H / E13 implementation from `2e45888`:
  - `execute_workflow(...)` and `run_agent_workflow(...)` now accept optional
    caller-provided `run_id` values and otherwise generate per-run IDs.
  - `WorkflowExecutionState`, `TraceEvent`, and lifecycle hook context objects
    carry run-correlation metadata for interleaved executions.
  - `InMemoryTraceSink`, `WorkflowTracer`, `OpenAIClientAdapter` lazy default
    client initialization, and `InMemoryToolRegistry` read/mutation helpers use
    synchronization for package-owned shared surfaces.
  - Caller-provided mutable tool handlers and lifecycle hook implementations
    remain responsible for synchronizing their own shared state.
  - `tests/test_concurrency.py` covers shared-context concurrent runs,
    run-correlated traces/hooks, public API `run_id` propagation, synchronized
    registry registration/invocation, and lazy-client initialization across
    threads.
  - Validation: `poetry run pytest -q && poetry run python -m compileall -q src
    tests && pre-commit run --files ...` — pass; 136 tests passed.
- Governing-docs update from `a4fe7e9`:
  - `specs/dynamic-agent-runner/spec.md`, `plan.md`, and `tasks.md` mark E13
    complete, record the current thread-safety contract, and leave E14 async
    interface work deferred.
- Governing-docs update from `56ddb9b`:
  - `specs/dynamic-agent-runner/spec.md`, `plan.md`, and `tasks.md` record E14 as
    a future async-first implementation slice with first-class
    `execute_workflow_async(...)` and `run_agent_workflow_async(...)` APIs.
  - Existing sync APIs should become wrappers that raise a clear project error
    when called from an already-running event loop.
  - The model-client contract should be async-canonical, with native OpenAI async
    behavior verified from official SDK behavior or source before implementation.
  - Tool handlers and lifecycle hooks should be inspected during registration or
    setup so dispatch can invoke or await each callable correctly.
  - Cancellation is best-effort and acceptance evidence must cover async model
    calls, async tools, async hooks, cancellation, sync wrapper compatibility, and
    concurrent async runs that preserve E13 run correlation.
- Governing-docs update from `4b17a4f`:
  - `specs/dynamic-agent-runner/spec.md` and `plan.md` now record
    `/Users/roschuma/Repos/github/openai-python/` as the local OpenAI Python SDK
    checkout to inspect before finalizing E14 async client and cancellation
    behavior.
- E14 implementation plan from `c22c239`:
  - `cline-tasks/evaluation-follow-up-implementation-plan.md` adds Slice I for
    E14 async-first execution APIs and wrappers.
  - Planned sequence: async OpenAI client boundary, async retry helper,
    async-capable tool registry dispatch, async-capable lifecycle hook dispatch,
    async executor core, public async API and sync wrappers, then cancellation and
    concurrent async validation.
- Governing-docs update from `781f451`:
  - `specs/dynamic-agent-runner/spec.md`, `plan.md`, and `tasks.md` point to the
    E14 implementation plan and original recommended first slice.
- E14 Slice I.1 implementation from `acca9da`:
  - `src/dynamic_agent_runner/openai_client.py` defines
    `AsyncOpenAIResponsesResource`, `AsyncOpenAIClientProtocol`,
    `AsyncOpenAIClientAdapter`, and `create_default_async_openai_client()`.
  - `AsyncOpenAIClientAdapter.create_response(...)` awaits
    `client.responses.create(...)` and preserves shared response normalization and
    `ModelExecutionError` wrapping.
  - `src/dynamic_agent_runner/__init__.py` exports the async adapter/protocol
    boundary.
  - `tests/test_openai_client.py` covers fake async client awaiting, async model
    failure wrapping, and the default `openai.AsyncOpenAI` factory path without
    live API calls.
  - Validation: `poetry run pytest tests/test_import.py tests/test_openai_client.py
    -q` — pass; 11 tests passed. Targeted pre-commit passed for the changed
    source/test files.
- Governing-docs update from `e750f3b`:
  - `specs/dynamic-agent-runner/spec.md`, `plan.md`, `tasks.md`, and
    `cline-tasks/evaluation-follow-up-implementation-plan.md` record Slice I.1
    completion and identify Slice I.2 async retry helper as the next E14 slice.
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
  - `781f451 docs(spec): reference async implementation plan`
  - `c22c239 docs(cline-tasks): plan async execution implementation`
  - `4b17a4f docs(spec): record openai async source checkout`
  - `56ddb9b docs(spec): record async execution decisions`
  - `a4fe7e9 docs(spec): record concurrent invocation support`
  - `2e45888 feat(executor): add concurrent run correlation`
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

- Runtime-package simplification S1-S5 is complete and recorded in governing
  spec documents through `89926d8`. Choose a new scoped follow-up before starting
  broader E9, OA, MCP, durable session, approval-resume, or PyQt-widget
  automation work.
- After committing the current RAG/embedding manifest support, record the commit
  hash in the memory bank and continue treating RAG/GraphRAG as metadata plus
  existing-node workflow shapes unless a future scoped slice explicitly adds
  executable retrieval/index integrations.
- Use the refreshed package-alignment backlog in `8308cd6` as the planning
  checkpoint before choosing the next post-S5 runtime slice.
- Preserve the S5 Power-Marimo fixture as placeholder-safe coverage: no live
  Marimo server calls, real SLD data, or live `power-tetris-sdk` calls.
- Keep representing `marimo-pair` as an agent-as-tool/SKILL-backed bounded
  Marimo operation, distinct from primitive node kinds and handoff metadata.
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
