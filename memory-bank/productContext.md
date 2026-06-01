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
- The exact package layout, public API, CLI shape, and core workflow execution
  internals are implemented, but broader multi-agent behavior, approval/resume
  engines, sessions, and sandbox/workspace runtime separation remain deferred.
- Treat source code and tests as the authority for concrete API behavior.

## Open Product Questions

- What exact schema is used by the generated definition YAML?
- What parts of the Mermaid diagram are execution-relevant versus documentation?
- What shape does the tool index use, and how are tool calls resolved?
- How should approval-required tool interruption and resumable run state be
  represented in OA7?
- What future session, MCP, sandbox/workspace, and broader agent-loop semantics
  should be added beyond the current metadata-preservation slices?
