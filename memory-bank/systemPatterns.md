<!-- markdownlint-disable MD013 -->
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
  - `src/dynamic_agent_runner/capabilities.py` owns preflight capability/status
    reporting for live, metadata-only, missing-collaborator, disabled, and
    invalid runtime surfaces
  - `src/dynamic_agent_runner/mcp.py` owns explicit caller-supplied MCP tool
    binding normalization into existing registry entries; it does not own live
    MCP transports or process lifecycle
  - `src/dynamic_agent_runner/guardrails.py` owns caller-registered guardrail
    result and registry primitives
  - `src/dynamic_agent_runner/openai_client.py` isolates the official OpenAI
    client behind a small fake-client-compatible adapter boundary
  - `src/dynamic_agent_runner/executor.py` composes loaded workflows, registry
    tools, retry policy, output validation, route validation, token-budget
    preflight, tracing hooks, opt-in iterative model-tool loops, and the OpenAI
    adapter into executable workflow runs through the async-first executor core
  - `src/dynamic_agent_runner/tracing.py` owns package trace event, trace sink,
    redaction, and in-memory tracing primitives
  - `src/dynamic_agent_runner/token_budget.py` owns `tiktoken`-backed prompt
    estimation and token-budget policy parsing
  - `src/dynamic_agent_runner/__pyinstaller/__init__.py` advertises
    package-owned PyInstaller hook directories, while
    `src/dynamic_agent_runner/__pyinstaller/` stores bundled freeze hooks such
    as `hook-openai_model_registry.py`
  - `src/dynamic_agent_runner/retry.py` owns retry policy parsing and
    Tenacity-backed bounded retry helpers
  - `src/dynamic_agent_runner/cli.py` exposes an injectable CLI implementation
    and console-script entry point for artifact-path workflow execution
  - `src/dynamic_agent_runner/errors.py` defines project-specific exception
    types, including guardrail execution errors
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
  executor/retry/output-contract/token-budget/tracing/behavior-override/
  capability-status/approval/MCP/guardrail/CLI behavior; follow-on runtime
  expansion should be planned as a new scoped slice.

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
- Capability/status reporting is a public preflight surface. It reports live
  behavior separately from preserved metadata, missing collaborators, disabled
  collaborators, and invalid packages. Metadata-only features should not be
  described as enabled.
- Approval interruption is implemented for direct `tool_use_step` actions whose
  effective registered tool policy requires approval. The executor returns a
  `WorkflowInterruptedResult` before lifecycle hooks, retry, registry
  invocation, output recording, or edge traversal, so no handler side effect
  occurs before approval.
- The high-level `run_agent_workflow*` APIs still represent completed workflows;
  they raise `WorkflowExecutionError` when execution pauses for approval. Use
  `execute_workflow*` to inspect structured interruption state.
- MCP v1 is explicit registry injection only. Caller-supplied `MCPToolBinding`
  values become `RegisteredTool` entries with MCP origin provenance and
  conservative hidden/approval-required defaults. There is no implicit
  discovery, process launch, transport, reconnect, or live schema cache.
- Guardrail v1 is input-only. Caller-registered input guardrails run once after
  `workflow_started` and before the first node starts. Missing adapters fail
  closed, abort decisions raise `GuardrailExecutionError`, and trace payloads
  mark inspected prompt content as sensitive.
- Iterative model-tool loops are opt-in only through
  `runtime.execution_policy.tool_use_completion.run_again: required`. Without
  that policy, model-emitted tool calls remain preserved metadata on
  `ModelResponse` and are not dispatched.
- Iterative loop v1 dispatches serial model-emitted tool calls through the
  existing `ToolRegistry`, appends model-facing `ToolResult` output to the next
  model request transcript, and stops on a final no-tool model response,
  `stop_on_tool`, max iteration exhaustion, tool failure, model failure, or
  approval interruption.
- Iterative loop v1 preserves safety boundaries: hidden/unavailable tools and
  malformed arguments fail closed, tool failures raise package-owned workflow
  errors, and approval-required model tools return `WorkflowInterruptedResult`
  before invocation. Durable approval resume for model tool calls remains
  deferred.
- The model-tool approval, lifecycle-hook, trace, state, registry, and
  result-shaping behavior currently lives in the executor's model-tool path.
  The Apple A2 and interpreter middleware specs require future non-model tool
  ingress to reuse or extract that behavior into one DAR-owned invocation
  coordinator; provider callbacks and interpreter bridges must not invoke raw
  handlers or the registry directly.
- The future interpreter model surface is one stable `run_interpreter` gateway
  rather than one generated tool per backend. Workflow metadata and package-local
  `INTERPRETER.md` content are descriptive and non-executable; callers supply
  executable adapters through an `InterpreterRegistry`, while node and runtime
  policy may only narrow the effective interpreter and tool sets.
- Loop traces use `model_tool_loop_*` events for start, turn start, tool call,
  stop reason, and final output selection, with arguments and final output
  marked sensitive.
- `openai_client.py` defines a protocol around `client.responses.create(...)`,
  so unit tests can inject fake clients without live OpenAI API calls.
- The OpenAI adapter default-provider path owns host-level OpenAI/Codex auth
  discovery. Caller-supplied clients, providers, provider config, `api_key`, and
  `base_url` stay authoritative. Ambient discovery is limited to trusted
  process/user sources such as `OPENAI_API_KEY` and `${CODEX_HOME}`.
- Codex user-level auth discovery supports ordered API-key/auth-token and
  ChatGPT auth selection. API-key/auth-token auth maps to the public
  OpenAI-compatible provider path; ChatGPT token auth maps to an explicit
  ChatGPT/Codex backend provider boundary in `openai_client.py` and is never
  copied into `OpenAIProviderConfig.api_key`.
- ChatGPT/Codex `/models` responses include provider metadata that must not be
  reduced to version-sorted IDs: priority controls ordering, visibility controls
  picker exposure, and the first visible entry is the default. Generic
  OpenAI-compatible providers may retain ID-only fallback behavior.
- ChatGPT/Codex request parity includes forwarding `ChatGPT-Account-ID` when
  the discovered auth record supplies an account identifier.
- The LiteLLM Codex wrapper keeps DAR-owned auth precedence, resolved
  endpoint, account id, `client_version` model listing, model aliases, and
  ambient-auth boundaries. LiteLLM Responses is the implemented opt-in
  transport;
  Chat Completions bridging is only a capability-gated fallback because it can
  lose Responses transcript, reasoning, tool-call, or streaming semantics.
- `OpenAIProviderConfig.codex_auth_preference` controls supported Codex auth
  ordering. The default is API-key/auth-token first; `chatgpt_first` chooses
  ChatGPT auth when it exists and falls back to API-key/auth-token auth when it
  does not.
- OpenAI request construction uses `input` messages plus optional `tools`,
  `tool_choice`, `response_format`, and extra model parameters.
- Tool schema conversion is currently aligned to `client.responses.create(...)`:
  function tools use top-level `type`, `name`, `description`, and `parameters`,
  not Chat Completions-style nested `function.name` payloads.
- Tool descriptor budgeting is future spec-only. The proposed package-owned
  `ToolSelector` should operate after registry exposure filtering, rank only
  eligible model-exposable tools, pack OpenAI-compatible descriptors within a
  token budget, and keep NLTK parser work as an optional benchmarked experiment.
- Memory-aware context pipeline is future spec-only. The proposed
  `metadata.memory_pipeline` surface is passive context policy for caller-owned
  durable agent/user memory, separate from active `metadata.rag_pipeline`
  retrieval. Active memory evidence retrieval remains an explicit caller-owned
  tool operation; the passive pipeline must not invoke it or implicitly persist
  RAG-retrieved content unless the workflow explicitly calls a caller-owned
  ingestion tool.
- Graphify semantic extraction is a package-owned, registry-mediated DAR tool
  that writes staged artifacts outside accepted `graphify-out/`; stock Graphify
  remains responsible for build, curation, validation, and promotion. The
  completed first release keeps deterministic fixed file-count chunks as the
  default. T7 adds opt-in token/file packing, adaptive bisection, summary-only
  reconciliation, and safety-constrained partial merge/duplicate repair.
  T8 is a pure advisory policy selector. T8.7 benchmark evidence retained fixed8
  as the runtime default; token-aware remains opt-in and must not silently
  change production chunking.
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
- Runtime collaborator pattern now includes model adapters, tool registries,
  guardrail registries, trace sinks, lifecycle hooks, and opt-in built-in packs.
  Future live features should fit this collaborator model instead of reading
  ambient host configuration from portable workflow packages.
- Graph mutation is the derived workflow-operation layer. The first completed
  checkpoint is an input-transform context-pruning attachment, but future graph
  mutation may own structural insertion, edge rewiring, or link-level operations
  such as inserting context management on a ReAct loopback. The
  `context-management-prepare-stage` spec owns the behavior of prompt/session/
  file context shaping, not the graph location where that behavior is attached.
- Freeze-time packaging support is isolated from runtime execution. PyInstaller
  hooks live under the package and are exposed through installed distribution
  entry points so downstream frozen clients collect required third-party data
  files and metadata automatically.
- OCI DevOps SCM remotes should use an auth-aware git routing pattern for
  remote verbs. For repositories whose `.git/config` contains
  `devops.scmservice`, run an OCI session check before `clone`, `fetch`,
  `pull`, `push`, or `remote`, and dispatch those verbs through `scm-git`;
  non-remote git verbs should continue to use `command git`. Session
  authentication is human-in-the-loop: `oci session authenticate` opens a
  browser login and may require the user to complete key/profile prompts.
- Local model support now has two distinct advisory fit layers in the specs:
  `llmfit-model-fit-filter` is pre-download Hugging Face candidate filtering,
  while `llama-cpp-memory-fit-profile` is post-resolution profiling for a
  concrete local GGUF model asset. Neither layer should replace the existing
  llama.cpp adapter contract or take ownership of model downloads, server
  lifecycle, or execution.

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

- Apple Foundation Models A1 is implemented and validated for standalone local text, structured output, and strict workflow paths. The pytest-native SDK harness remains a tracked follow-up because native status 255 can occur despite successful availability; keep A2 tool callbacks behind a separate coordinator and approval contract.
- Interpreter middleware has a resolved gateway and custom-adapter direction but
  is not implementation-ready. Prototype candidate backends and resolve safety,
  redaction, descriptor-budget, and nested approval/resume questions first.
- Use `specs/README.md` as the current spec inventory and completion matrix.
  Future live-runtime work should start from the relevant feature spec under
  `specs/` and resolve its `NEEDS CLARIFICATION` items before implementation.
- The current roadmap has capability status, approval/sandbox v1, MCP v1, guardrail v1, iterative loops, skill source resolution, host integration, local-model availability, Apple A1 implementation, and LiteLLM L1 plus opt-in Codex L2 slices complete. Apple pytest-native harness isolation, A2 callbacks, memory retrieval/persistence, and provider-backed compaction remain follow-up work; upstream LiteLLM publication and global default Codex replacement remain deferred.
- `specs/capability-status-report/spec.md` owns the implemented preflight
  reporting direction for live, metadata-only, missing-collaborator, disabled,
  unsupported, and invalid capabilities.
- Do not treat interpreter, Apple callback, durable memory, provider compaction,
  or other future metadata as live behavior merely because a spec or preserved
  declaration exists.
- Graphify semantic extraction is an implemented artifact-production concern:
  DAR provides a bounded, registry-mediated extractor and the
  `graphify-extract` console wrapper, while Graphify owns
  graph construction, curation, diagnostics, query, and promotion. Accepted
  `graphify-out/` snapshots must not be mutated by the extractor.
- Keep implementation aligned with the artifact-interpreter framing rather than
  expanding into a generic agent framework.
- Keep primitive runtime node kinds limited to `llm_step`, `tool_use_step`, and
  `decision_step` unless a later format version changes the contract.
- Treat the Slice 7 CLI as a thin public surface over existing API/executor
  seams; do not widen executor semantics from CLI work alone.
- Keep unsupported fixture features visible through expected-failure tests until
  a later scoped slice implements them.
- Keep the OpenAI-first adapter boundary for the core runtime, while the
  dedicated LiteLLM provider-adapter spec governs the bundled ordinary
  OpenAI-compatible transport and its deferred upstream/Responses follow-ups.
  Keep Watchfiles, Rich, and Diskcache deferred until a future scoped
  requirement justifies them.
- Preserve the OpenAI auth boundary: project-local `.codex/config.toml`,
  workflow packages, and generated artifacts must not choose auth sources or
  redirect user credentials. Future PAT or agent-identity support needs a
  separate provider/base-url/signing spec before implementation.
- If local-model support returns, follow the split authoritative specs:
  `specs/llama-cpp-local-model/spec.md` for local adapter design,
  `specs/internal-graph-mutation/spec.md` for derived workflow operations, and
  `specs/context-management-prepare-stage/spec.md` for prompt/session/file
  context shaping. Fit llama.cpp into the existing `model_adapter` contract
  rather than introducing a parallel runtime model interface.
- For the llama.cpp local-model slice specifically, preserve these boundaries:
  do not launch local servers in the runtime; use the OpenAI-compatible provider
  seam only when the caller already supplies a local server; direct in-process
  `llama_cpp.Llama` execution now exists without requiring server dependencies;
  use runtime-owned Hugging Face download/caching for missing referenced model
  assets; and default the adapter model-cache path to `~/.ollama/models` unless
  the caller provides an explicit cache folder.
- For llama.cpp memory-fit profiling, treat the profile as optional,
  read-only, and fail-open by default. It should operate on a resolved local
  model path, normalize profiler output into package-owned records, and suggest
  effective context settings without mutating `LlamaCppLocalModelConfig`. The
  prepared v1 boundary is injected evaluators only, no subprocesses, no cache,
  no automatic memory-budget discovery, and suggested kwargs limited to
  `{"n_ctx": value}`.
- Preserve the executor boundary during llama.cpp follow-up: direct adapters
  advertise `models` and `is_local=True`, and client intent should be expressed
  with `model_adapter_coverage="strict"` rather than revived `local_only`
  routing semantics.
- Expected validation surfaces for llama.cpp work are now explicit:
  `tests/test_local_models.py` for direct adapters, local-model helper,
  resolution, and failure taxonomy coverage; `tests/test_openai_client.py` for
  provider/helper behavior; and `tests/test_executor.py` for strict/augmented
  adapter coverage.
- Keep offline or no-network download policy runtime-owned above the portable
  workflow package, and treat model-identity mismatch checks as driven by
  runtime-owned adapter configuration such as declared alias, explicit local
  path, or explicit Hugging Face reference.
- Allow endpoint-backed local chat to ship before separate local embedding
  execution, while preserving the later embedding contract and keeping that
  deferred embedding work separate from first-slice graph-mutation delivery.
- The following areas now have dedicated feature specs and should not be
  implemented directly from the primary spec alone: capability status reporting,
  approval interruption/resume, sandbox/workspace runtime, MCP runtime
  integration, live guardrail execution, `SKILL.md` source resolution,
  iterative agent-loop runtime, context-management prepare stage,
  RAG orchestration contract, local-model advisory fit features, Power-Marimo
  downstream client boundary, async session memory, and interpreter middleware.
- Capability/status expansion is split by ownership: each feature spec owns the
  domain facts it contributes, while
  `specs/capability-status-report/spec.md` owns shared report shape, status
  vocabulary, redaction posture, and user-visible readiness assembly.
- RAG/context-management integration is split by ownership:
  `specs/rag-orchestration-contract/spec.md` owns RAG declarations,
  collaborator readiness, provenance/source/permission/cache/degraded metadata,
  and context-management handoff declarations;
  `specs/context-management-prepare-stage/spec.md` owns retrieved-context
  lanes, prompt packing, trimming, compression, omission diagnostics, and final
  prompt injection.
- Repository-local reference packaging is now being used for external guidance
  that should remain available inside this repo. The OpenAI Model Registry notes
  under `cline-tasks/references/openai-model-registry/` are supporting
  references, not executable runtime code or canonical spec artifacts.
- Use `tests/fixtures/agent-patterns/` as a reusable coverage source for future
  loader, executor, and CLI compatibility tests.
- Update this file as concrete modules, entry points, and architectural
  boundaries become real.
