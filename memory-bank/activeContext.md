# Active Context

## Current Focus

- No implementation slice is currently active.
- The latest completed repository work focused on making the OpenAI adapter work
  with default OpenAI/Codex auth, ChatGPT/Codex backend auth, authenticated model
  discovery, and omitted-model defaults.
- The latest documentation work added a ReAct/tool workflow guide under
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
  adapter coverage, and default OpenAI/Codex auth.
- Default OpenAI/Codex auth follow-ups are limited to separately specified
  personal-access-token or agent-identity support.
- Live runtime behavior is still deferred for approval pause/resume, writable
  sandbox/workspace execution, live MCP discovery/invocation, live guardrail
  enforcement, arbitrary `SKILL.md` loading, iterative model/tool loop runtime,
  and Power-Marimo host automation.

## Next Steps

- For implementation: select the next scoped feature spec or create a new
  task breakdown before editing runtime code.
- For OpenAI/Codex auth: only add PAT or agent-identity support after a separate
  provider/base-url/signing design is specified and tested.
- For ReAct/tool workflows: if runtime support is selected, consider resolving
  the current mismatch where `react_loop` validation expects a `loopback` edge
  but execution follows `sequential`/`branch` traversal.
- For validation: continue using fake clients/tools in unit tests; do not add
  live OpenAI, MCP, Marimo, Hugging Face, or local-model calls to core tests.
