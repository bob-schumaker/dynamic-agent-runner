# Product Context

## Product Status

- Product intent is now documented in the root `README.md`.
- Source code and concrete public API are still expected to be added.

## Users and Use Cases

- Users need to execute agent workflows described by artifacts generated from
  the agent-development rule and skill in `clinerules-roschuma`.
- The library should let callers provide a user prompt, run the configured agent
  workflow through OpenAI-compatible interfaces, and receive the final result.

## User Goals

- Load a workflow definition from generated YAML, Mermaid, and tool-index
  artifacts.
- Execute the workflow using OpenAI-compatible model/tool interfaces and
  `ai-tools-core` tool handling.
- Return a final agent result to the caller.
- Keep the artifact-to-execution path clear enough to validate and test.

## Product Boundaries

- The confirmed runtime direction is OpenAI-compatible model/tool interfaces
  using `ai-tools-core` first; `ocihelper` is intentionally removed because it is
  poorly supported.
- The exact Python package layout, public API, CLI shape, and workflow execution
  internals are not implemented yet.
- Treat future source code and tests as the authority for concrete API behavior.

## Open Product Questions

- What exact schema is used by the generated definition YAML?
- What parts of the Mermaid diagram are execution-relevant versus documentation?
- What shape does the tool index use, and how are tool calls resolved?
- What public Python API should callers use?
- Should a CLI be added in addition to the library API?
- What safety, authentication, or external-system boundaries apply?
