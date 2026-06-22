# Product Context

## Product Status

- Product intent is documented in the root `README.md`.
- Source code, tests, docs, and a concrete public API/CLI surface now exist.

## Users and Use Cases

- Users need to execute agent workflows described by artifacts generated from
  the agent-development rule and skill in `clinerules-roschuma`.
- The library should let callers provide a user prompt, run the configured agent
  workflow through OpenAI-compatible interfaces, and receive the final result.

## User Goals

- Load a workflow definition from generated YAML, Mermaid, and tool-index
  artifacts.
- Execute the workflow using the official `openai` package through a local
  adapter plus a repository-owned tool registry.
- Return a final agent result to the caller.
- Keep the artifact-to-execution path clear enough to validate and test.

## Product Boundaries

- The confirmed runtime direction is an OpenAI-first adapter boundary plus a
  repository-owned tool registry; `ocihelper`, `ai-tools-core`, and
  `openai-tools-core` are intentionally out of scope for the current runtime.
- The exact package layout, public API, CLI shape, core workflow execution
  internals, approval interruption baseline, in-memory persistent sessions,
  session event streaming, host-tool integration helpers, and capability/status
  reporting are implemented. Durable approval resume, full sandbox/workspace
  runtime, provider-native streaming, and broader multi-agent behavior remain
  deferred.
- Deferred live-runtime areas now have separate future-feature specs under
  `specs/`; those specs capture known requirements and open decisions but do not
  authorize implementation by themselves.
- Treat source code and tests as the authority for concrete API behavior.

## Open Product Questions

- Which `NEEDS CLARIFICATION` items must be resolved before implementing live
  approval resume, full sandbox/workspace, MCP transports, output/tool
  guardrails, skill-source expansions, loop expansions, or generic
  host-integration behavior?
- What customer-facing commitments should be made for host-managed continuity
  before durable runner-owned session storage exists?
- Should `ToolSelector` descriptor budgeting become the next context-window
  efficiency slice, or remain behind provider/context follow-ups such as
  LiteLLM, provider-native streaming, and context compaction?
