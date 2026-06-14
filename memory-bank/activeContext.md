# Active Context

## Current Focus

- No implementation slice is currently active.
- The latest completed repository work added the optional
  `llama-cpp-memory-fit-profile` feature spec, refreshed stale
  `llama-cpp-local-model` SDD artifacts to mark direct in-process llama.cpp as
  implemented through Slice 3, and committed the spec changes as `11916b7`.
- The council roadmap promotes a narrow approval/sandbox live-action vertical
  slice plus a capability/status report before broader MCP, guardrail, loop, or
  interpreter runtime work.
- Earlier OpenAI adapter work made default OpenAI/Codex auth, ChatGPT/Codex
  backend auth, authenticated model discovery, and omitted-model defaults work.
- Earlier documentation work added a ReAct/tool workflow guide under
  `docs/files/react-tool-workflow.rst` and used it to drive upstream
  `agent-development-skill` improvements.

## Recent Completed Work

- Default OpenAI/Codex auth is implemented through the OpenAI adapter default
  provider path:
  - caller overrides remain authoritative
  - `OPENAI_API_KEY` is supported
  - trusted user-level Codex API-key/auth-token defaults are supported
  - ChatGPT/Codex token auth is supported through an explicit
    `chatgpt-codex` provider boundary in `openai_client.py`
  - `auth.json` `auth_mode` constrains eligible auth methods
  - `codex_auth_preference="chatgpt_first"` can prefer ChatGPT auth when both
    API-key/auth-token and ChatGPT auth exist
- ChatGPT/Codex live-backend compatibility is implemented:
  - model listing sends `client_version` from `${CODEX_HOME}/version.json`
  - Codex model catalogs using `models[].slug` are normalized
  - unsupported requested models fail before `responses.create`
  - system/developer prompt messages are translated into `instructions`
  - ChatGPT/Codex requests force `store=false` and `stream=true`
  - streamed response text is normalized into `ModelResponse`
- Upstream callers can now inspect model availability through:
  - `OpenAIClientAdapter.list_supported_models(...)`
  - `AsyncOpenAIClientAdapter.list_supported_models(...)`
  - `default_model(...)` on both adapters
- When no model is configured on the adapter or workflow, the runtime can choose
  the lowest versioned authenticated OpenAI model as the initial model.
- A live OpenAI/ChatGPT Codex smoke path was verified with the user's local
  Codex auth: model listing returned `gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini`, and
  `codex-auto-review`; an in-memory workflow using `gpt-5.4-mini` returned
  `pong`.
- ReAct/tool workflow guidance was added and validated:
  - `docs/files/react-tool-workflow.rst`
  - `make -C docs html`
  - in-memory runtime smoke of the documented route-gated graph
- Upstream `agent-development-skill` was checked after reinstallation:
  - it now has a conceptual external-runtime ReAct host example
  - stale `dynamic_agent_runner`-specific runner references were removed
  - the installed ReAct runtime example validates with the skill validator
- OpenAI tool schema compatibility was corrected:
  - `registry.openai_tool_schema(...)` now emits Responses API function tools
    with top-level `type`, `name`, `description`, and `parameters`
  - tests now assert the request shape sent through executor and registry paths
  - the production fix and test updates were committed separately as `ca6b065`
    and `6b9fe0c`
- Council roadmap/spec refresh completed:
  - `specs/capability-status-report/spec.md` now defines a future preflight
    report for live, metadata-only, missing-collaborator, disabled,
    unsupported, and invalid capabilities
  - `specs/README.md` and `specs/dynamic-agent-runner/tasks.md` now record the
    council-recommended implementation order
  - future-feature specs now include roadmap notes for approval, sandbox, MCP,
    guardrails, loops, interpreter middleware, sessions, llmfit, and
    Power-Marimo
- LlamaBarn local-model fit evaluation was reviewed for a possible package
  feature:
  - LlamaBarn's useful pattern is post-install/post-resolution memory
    feasibility profiling for concrete local GGUF assets, not generic model
    quality ranking
  - `specs/llama-cpp-memory-fit-profile/spec.md` now defines the future
    optional advisory profile surface for resident memory, context-growth cost,
    supported context tiers, maximum usable context, suggested kwargs, and
    fail-open diagnostics
  - `specs/llama-cpp-local-model/spec.md`, `plan.md`, `tasks.md`, and
    `validation.md` now reflect that direct in-process llama.cpp support already
    landed in `58136d9`

## Current Spec Authority Map

- Primary runtime contract:
  - `specs/dynamic-agent-runner/spec.md`
- Current feature/spec packages with implemented or checkpoint-complete work:
  - `specs/openai-compatible-provider-wrapper/spec.md`
  - `specs/default-openai-codex-auth/spec.md`
  - `specs/llama-cpp-local-model/spec.md`
  - `specs/internal-graph-mutation/spec.md`
  - `specs/hugging-face-model-search/spec.md`
  - `specs/async-session-memory-pipeline/spec.md`
  - `specs/model-adapter-coverage/spec.md`
  - `specs/hugging-face-support-layer/spec.md`
  - `specs/mlx-local-model-adapter/spec.md`
- Future investigation or future-feature specs:
  - `specs/llama-cpp-memory-fit-profile/spec.md`
  - `specs/capability-status-report/spec.md`
  - `specs/llmfit-model-fit-filter/spec.md`
  - `specs/llm-step-interpreter-middleware/spec.md`
  - `specs/approval-interruption-resume/spec.md`
  - `specs/sandbox-workspace-runtime/spec.md`
  - `specs/mcp-runtime-integration/spec.md`
  - `specs/live-guardrail-execution/spec.md`
  - `specs/skill-source-resolution/spec.md`
  - `specs/iterative-agent-loop-runtime/spec.md`
  - `specs/power-marimo-host-automation/spec.md`

## Current Status

- Core runtime implementation is complete through package-alignment P5, async-
  first execution, portable tool type alignment, prompt-cache metadata,
  provider-wrapper work, local-model adapters, graph-mutation checkpoint, model
  adapter coverage, default OpenAI/Codex auth, and Responses API function-tool
  schema compatibility.
- llama.cpp local-model support is implemented through Slice 3: endpoint
  helpers, local asset resolution, default Hub download wiring, identity
  validation, direct in-process sync/async adapters, and adapter coverage tests.
- Current spec roadmap recommendation is approval/sandbox live-action first,
  capability/status reporting second, then policy-bound MCP and guardrail work;
  loop and interpreter work remain prototype/benchmark-led.
- Default OpenAI/Codex auth follow-ups are limited to separately specified
  personal-access-token or agent-identity support.
- Live runtime behavior is still deferred for approval pause/resume, writable
  sandbox/workspace execution, live MCP discovery/invocation, live guardrail
  enforcement, arbitrary `SKILL.md` loading, iterative model/tool loop runtime,
  and Power-Marimo host automation.

## Next Steps

- For implementation: if following the council roadmap, create a scoped plan for
  the approval-interruption plus sandbox/workspace live-action vertical slice.
- For product visibility: plan `capability-status-report` before promoting broad
  live MCP, guardrail, loop, or interpreter behavior.
- For OpenAI/Codex auth: only add PAT or agent-identity support after a separate
  provider/base-url/signing design is specified and tested.
- For ReAct/tool workflows: if runtime support is selected, consider resolving
  the current mismatch where `react_loop` validation expects a `loopback` edge
  but execution follows `sequential`/`branch` traversal.
- For validation: continue using fake clients/tools in unit tests; do not add
  live OpenAI, MCP, Marimo, Hugging Face, or local-model calls to core tests.
- For OpenAI tool work: preserve Responses API request shape unless a separate
  adapter boundary explicitly targets another OpenAI-compatible API.
- For local-model fit work: keep `llmfit-model-fit-filter` as pre-download
  Hugging Face candidate filtering and `llama-cpp-memory-fit-profile` as
  post-resolution profiling for concrete local GGUF assets.
