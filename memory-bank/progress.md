# Progress

## Working

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

## In Flight

- No source implementation work is currently in flight after implementation
  commit `13c6dac` and governing-docs commit `97fe320`.
- Remaining deferred Codex/Cline follow-ups include E9 through E12; no next
  candidate slice has been selected after E2/Slice G.

## Remaining

- Await follow-up direction for the next scoped runtime slice, adapter-gated
  prompt-cache provider pass-through, deferred library-evaluation follow-up,
  remaining Codex/Cline deferred follow-ups, or interpreter middleware prototype
  work.
- Extend from the completed loader, validation, registry, OpenAI adapter,
  executor, CLI, behavior-override, and all-pattern fixture foundation into the
  next scoped slice.
- Use the all-pattern hello-world fixtures as the broad pattern test surface for
  future compatibility coverage, including expected-failure coverage for pattern
  features that are represented in artifacts but not yet implemented.
- Update the memory bank after each future meaningful implementation
  milestone.

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
- Codex/Cline follow-ups E1, E2, E3, E4, E5, E6, E7, and E8 are implemented.
  Remaining follow-ups are deferred backlog items, not implemented runtime
  behavior. They should be introduced through package-owned contracts before broad
  integrations such as MCP, plugins, shell hooks, app-server protocols, or
  multi-provider routing.
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
