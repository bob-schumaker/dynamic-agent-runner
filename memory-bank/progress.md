# Progress

## Working

- Core runtime supports package-directory workflow loading and execution,
  async-first APIs, sync wrappers, tool registry/overrides, OpenAI-compatible
  adapters/providers, retry, output contracts, token budgeting, tracing, hooks,
  prompt preparation, validation, runtime behavior overrides, model adapter
  coverage, local model helpers, and metadata-only future surfaces.
- Default OpenAI/Codex auth discovery is implemented and hardened through live
  ChatGPT/Codex backend compatibility.
- ChatGPT/Codex supported models can be listed and surfaced to callers;
  unsupported models fail before request dispatch.
- ChatGPT/Codex Responses calls use backend-required `instructions`,
  `store=false`, and streaming normalization.
- Registry-provided model tools now use OpenAI Responses API function-tool
  shape with top-level `name`, avoiding the previous Chat Completions-style
  nested `function.name` payload.
- OpenAI adapters expose supported model listing and default-model selection;
  missing workflow models can use the lowest versioned authenticated model.
- ReAct/tool workflow guidance exists in authored docs and documents
  route-gated tool execution.

## Latest Milestones

- `29bbe19` recorded the council roadmap in specs, added
  `specs/capability-status-report/spec.md`, and annotated future-feature specs
  with the recommended sequencing.
- `86c287c`, `f50262f`, `1764bc2`, and `d782279` refined Codex config/auth
  parsing and spec alignment.
- `d2c9805`, `6981b60`, and `9ba5c24` added ChatGPT/Codex authenticated model
  preflight.
- `f2783f2`, `19e8a49`, and `024122c` added ChatGPT/Codex live backend request
  compatibility and documented it.
- `de2af7e`, `4ed64a1`, and `5efa2e0` exposed supported model listing to
  upstream callers and updated specs.
- `f8d0346`, `4c5363d`, and `f384731` added omitted-model default selection and
  spec/tasks coverage.
- `fac19ca` added `docs/files/react-tool-workflow.rst`; docs build and
  in-memory ReAct smoke passed.
- Upstream `agent-development-skill` was updated/reinstalled with conceptual
  ReAct external-runtime examples. Installed-skill checks showed the stale
  dynamic-agent-runner-specific runner removed and the conceptual pseudocode
  reference clean.
- `ca6b065` fixed `registry.openai_tool_schema(...)` to emit Responses API
  function tools with top-level `name`, `description`, and `parameters`.
- `6b9fe0c` updated registry and executor tests to expect the Responses API
  tool schema.

## Remaining

- Council-recommended next slice: a narrow approval/sandbox live-action vertical
  slice with explicit workspace grants, approval interruption records, redacted
  traces, and one safe mutating workspace capability.
- Capability/status reporting: future preflight/public report to distinguish
  live, metadata-only, missing-collaborator, disabled, unsupported, and invalid
  runtime capabilities.
- Optional llama.cpp embedding follow-up: separate local embedding
  configuration, if explicitly scheduled.
- Personal-access-token and agent-identity Codex auth remain deferred until a
  separate provider/base-url/signing design is specified and tested.
- Future richer Hugging Face Hub behavior beyond read-only model discovery; this
  requires a separate feature spec.
- Future richer Hugging Face Hub behavior and local-model evaluation workflows
  require scoped specs/tasks.
- Live approval interruption/resume engine and serialized resume state,
  preferably first as part of the approval/sandbox vertical slice.
- Writable sandbox/workspace runtime, write/patch/shell tools, and command
  approval policy, preferably first as part of the approval/sandbox vertical
  slice.
- Live MCP source discovery, lifecycle management, registry injection, and tool
  invocation.
- Live guardrail adapter execution and abort/reject behavior.
- Trusted `SKILL.md` body loading, source precedence, and prompt injection.
- Iterative model/tool loop runtime and stop policy.
- Power-Marimo live host automation, Marimo-session tools, domain adapters, and
  optional PyQt-widget automation.

## Risks or Follow-ups

- Do not treat future-feature specs as implementation approval; create a scoped
  plan/task slice first.
- Do not promote live MCP, guardrail execution, iterative loops, or interpreter
  middleware before approval/sandbox/status boundaries are clear enough to
  prevent high-risk tools from bypassing policy.
- Keep Power-Marimo continuity host-managed until a concrete workflow justifies
  runner-owned durable session memory.
- Keep ChatGPT/Codex token auth separate from public OpenAI API-key provider
  semantics.
- Preserve caller-configured model order when adapters explicitly provide
  models; only sort authenticated discovered models for default choice.
- ReAct runtime currently uses `sequential` executable return edges plus
  `loopback` metadata; direct executable `loopback` traversal remains a
  potential runtime cleanup.
- OpenAI-compatible local endpoints or future adapters may not all accept the
  same tool schema; keep schema conversion owned by the adapter/request boundary
  if another API shape is needed.
- Full executor-suite validation may require avoiding or pre-caching `tiktoken`
  network downloads in sandboxed environments.
