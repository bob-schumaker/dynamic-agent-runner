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
- Deferred live-runtime areas now have separate future-feature specs under
  `specs/`; those specs capture known requirements and open decisions but do not
  authorize implementation by themselves.
- A June 2026 council roadmap now recommends making one safe live-action path
  real before broadening the platform: approval interruption plus sandboxed
  workspace mutation first, capability/status reporting second, then MCP and
  guardrails behind policy.
- Treat source code and tests as the authority for concrete API behavior.

## Open Product Questions

- Should the next active implementation slice be the council-recommended
  approval/sandbox live-action vertical slice?
- What exact capability/status report shape should help callers distinguish live
  behavior from metadata-only declarations?
- Which `NEEDS CLARIFICATION` items must be resolved before implementing live
  approval/resume, sandbox/workspace, MCP, guardrail, skill-source, loop, or
  generic host-integration behavior?
- What customer-facing commitments should be made for host-managed continuity
  before runner-owned session memory exists?
