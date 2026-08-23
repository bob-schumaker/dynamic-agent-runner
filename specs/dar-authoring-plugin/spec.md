# DAR Authoring Plugin Specification

## Metadata

- Status: proposed; not implementation authorization
- Owner: dynamic-agent-runner
- Target: a Codex plugin that authors and runs selected DAR-compatible workflow
  packages

## Objective

Provide a Codex plugin named `dar-authoring` for designing, validating, and
executing selected Dynamic Agent Runner (DAR) workflow packages. The plugin
owns authoring policy and the full host-runtime integration; DAR remains the
generic graph executor.

## References

- [Connecting AI tools via Fastmail's MCP server](https://www.fastmail.help/hc/en-us/articles/15869557281295-Connecting-AI-tools-via-Fastmail-s-MCP-server)
- [An MCP server for Fastmail](https://www.fastmail.com/blog/an-mcp-server-for-fastmail/)

Fastmail documents its hosted MCP endpoint as `https://api.fastmail.com/mcp`.
Connection uses OAuth 2.0 by default, with an API-token option, and grants are
separated into read-only, write, and send access. The plugin must preserve those
external scopes and add its own operation-level approval boundary; it must not
broaden Fastmail access during workflow execution.

## Problem Statement

DAR consumes generated `agent-design.md`, `agent-runtime.yaml`, and
`agent-graph.mmd` package artifacts, but it intentionally does not own package
authoring policy, MCP-server lifecycle, host credentials, local model lifecycle,
or evaluation infrastructure. A plugin is needed to make those authoring and
host responsibilities coherent without expanding DAR's runtime boundary.

## Scope

The plugin shall provide:

1. three DAR-scoped Codex skills;
2. templates for canonical DAR package artifacts;
3. one profile-backed MCP tool that provisions and runs one configured workflow
   operation; and
4. host services for every DAR workflow feature the selected profile declares;
   and
5. safety controls for package selection, credentials, local file references,
   state, observability, and side-effecting operations.

The plugin shall be a package-authoring plugin. It shall not add authoring,
evaluation, credential, MCP discovery, or model-server lifecycle responsibilities
to the DAR library or CLI.

## Non-Goals

- Replacing DAR's graph executor, manifest loader, or validation engine.
- Discovering, installing, starting, or supervising arbitrary MCP servers.
- Accepting an arbitrary command, package path, model endpoint, or MCP endpoint
  from a model-facing tool call.
- Creating embeddings, vector indexes, or evaluation infrastructure inside DAR.
- Making live Fastmail or Hugging Face calls part of unit-test coverage.

## Plugin Structure

```text
dar-authoring/
  .codex-plugin/plugin.json
  .mcp.json
  skills/
    agent-development/SKILL.md
    agent-tool-contract-design/SKILL.md
    agent-evaluation/SKILL.md
  server/
    dar_workflow_server/
  templates/
    agent-design.md
    agent-runtime.yaml
    agent-graph.mmd
    tool-index.yaml
    eval-plan.md
```

The exact MCP packaging and installation mechanism is an implementation spike.
It must run a local stdio MCP server and must not depend on an undocumented
plugin-path interpolation mechanism.

## Skill Contracts

### FR-1: `agent-development` is the entry skill

The plugin shall expose `agent-development` as the primary authoring workflow.
It shall decide whether an agent is warranted, select the smallest suitable
DAR-supported pattern, and create the canonical package artifacts:

- `agent-design.md`
- `agent-runtime.yaml`
- `agent-graph.mmd`

It shall produce a package design that is compatible with DAR's primitive node
kinds, graph validation, model requirements, tool registry, and execution
bounds. It shall route to the companion skills only when their deeper work is
needed.

Acceptance criteria:

- A basic reasoning package and a bounded tool-use package can be authored from
  the templates and loaded by DAR.
- A workflow loop declares a finite iteration or step bound.
- The generated design identifies host-owned collaborators rather than implying
  that DAR starts servers or owns credentials.

### FR-2: `agent-tool-contract-design` defines host-owned tools

The plugin shall expose `agent-tool-contract-design` for workflows that need
tools, MCP bindings, or a CLI-like host contract. For each tool it shall define:

- canonical and model-facing identifiers;
- JSON input and normalized output schemas;
- side-effect class, approval requirement, timeout, retry, and failure policy;
- provenance and the required host profile binding; and
- model-visible data minimization and sensitive-field handling.

For MCP tools, the generated package shall use DAR's explicit,
caller-supplied binding model. A manifest or `tool-index.yaml` declaration alone
does not make a tool executable.

Acceptance criteria:

- An MCP declaration identifies the configured server and tool to which the host
  will bind it. Design does not contact the server or fabricate remote tool
  names; provisioning discovers and validates the exact remote surface.
- A side-effecting tool is marked approval-required in package metadata and is
  also enforced by the plugin server under FR-6.
- Tool registration is supplied by the host when executing the workflow.

### FR-3: `agent-evaluation` is a companion skill

The plugin shall expose `agent-evaluation` for formal package acceptance work.
It shall generate an evaluation plan, fixture cases, scoring rubric, and
regression gate for a workflow package.

Evaluation metadata may be preserved in package artifacts, but execution shall
run through tests or an external harness. DAR shall not become the evaluation
engine.

Acceptance criteria:

- Every generated evaluation plan distinguishes deterministic checks from
  judge-based checks and records the judge or human-review policy.
- Tests use fake model adapters, fake tool registries, or an external harness;
  they do not call Fastmail, Hugging Face, or a live model.

## MCP Execution Tool

### FR-4: Expose one narrow execution tool

The plugin shall expose exactly one model-facing MCP tool named
`run_dar_workflow`. It executes a selected operation from a configured saved
workflow, using a configured host profile. It is not a shell-command proxy for
the `dynamic-agent-runner` CLI.

The MCP server shall use DAR's library API because execution may require a
caller-provided tool registry, explicit MCP bindings, and a strict local model
adapter. The DAR CLI alone cannot supply those collaborators.

For a configured profile, the server shall perform the required execution setup
before calling DAR: obtain or validate the profile's authenticated connection,
initialize the configured MCP client, discover the remote tools, compare the
discovered surface with the profile's allowlist, construct `MCPToolBinding`
handlers, and construct the required model adapter. DAR receives only the
validated workflow, registry, and adapter.

The request contract shall have this logical shape:

```json
{
  "workflow_id": "email",
  "operation": "list_unread",
  "arguments": {"limit": 50},
  "model_profile": "local-mail-model",
  "max_steps": 12,
  "provisioning": {
    "allow_initial_auth": true,
    "allow_surface_refresh": false
  },
  "approval": null
}
```

`workflow_id` and `operation` are closed-set identifiers from a host-managed
workflow catalog. The tool must reject arbitrary package paths, executable
commands, model endpoints, and MCP endpoint values in invocation arguments.

### FR-5: Provision and bind a configured MCP surface

The wrapper shall only provision named profiles from the host-managed catalog.
The `fastmail` profile shall use the documented
`https://api.fastmail.com/mcp` endpoint, complete or reuse an OAuth/API-token
connection, and request the least sufficient Fastmail grant.

Each profile shall contain a versioned `fastmail-surface.json` capability
snapshot. The snapshot maps stable DAR semantic identifiers, such as
`fastmail.search_mail` and `fastmail.send_email`, to the exact Fastmail MCP tool
names and schemas accepted by that profile. The wrapper shall perform remote MCP
tool discovery only while provisioning the configured profile, then validate the
live surface against the snapshot before it creates a DAR registry.

The wrapper shall return `authentication_required` when OAuth has not been
completed. It shall return `surface_changed` when a required remote tool is
missing or its material input/output schema has changed. It must not choose a
replacement tool automatically. A profile's surface can be refreshed only by an
explicit user-authorized provisioning request.

Acceptance criteria:

- The wrapper creates DAR bindings only after all required remote capabilities
  and schemas match the approved snapshot.
- The first authenticated Fastmail connection records a capability snapshot
  without persisting a credential in the package artifacts.
- A later schema or tool-name change fails closed until explicitly refreshed.

### FR-6: Enforce write approval in the wrapper and DAR boundary

The server shall evaluate the selected operation's side-effect policy before
execution. Read-only operations may run immediately. A side-effecting operation
shall return a preview and an approval challenge on its first request.

The second request shall contain a valid one-use, expiring approval token and a
request digest matching the approved action. The digest shall cover:

- workflow identifier and resolved package revision;
- operation identifier;
- normalized arguments;
- selected model profile and bounded execution parameters; and
- content hashes of any referenced local files.

The server shall reject changed, expired, replayed, or mismatched approvals.
DAR also returns a `WorkflowInterruptedResult` before invoking an
approval-required registered tool. The wrapper shall persist and surface that
interruption rather than invoke the handler.

DAR does not currently expose a public continuation API that resumes an
interrupted execution at the pending tool call. Until such an API exists, a v1
write operation shall be an operation-specific deterministic tool step: the
wrapper validates the user-approved arguments before the run, provides a
per-invocation handler that independently verifies the one-use token, and
executes the tool only after that verification. A v1 write workflow must not
allow an LLM to alter the approved recipient, subject, or body after preflight.
Adding durable, graph-preserving DAR resumption is follow-on DAR work, not an
implicit wrapper replay.

Acceptance criteria:

- A send operation cannot reach its handler without a matching approval token,
  even if the handler is called outside DAR's normal approval interruption.
- Changing a subject, recipient group, package revision, or referenced body file
  after the preview invalidates the token.
- A valid token cannot be used twice.

### FR-7: Profile-backed execution owns external collaborators

A host-managed profile shall select the package revision, local model adapter,
MCP bindings, tool handlers, allowed workspace roots, and execution limits.
Profiles may also reference a local OpenAI-compatible, llama.cpp, or MLX
adapter, but the plugin shall not start or discover any of those model services.

File arguments are allowed only when their resolved paths remain under an
allowlisted workspace root. The server shall hash approved file contents before
the operation runs to prevent time-of-check/time-of-use substitution.

Acceptance criteria:

- A `body_html_path` outside an allowlisted root is rejected.
- A local-only profile uses strict adapter coverage and cannot silently fall back
  to the default hosted OpenAI adapter.
- Missing profile bindings fail before workflow execution.

### FR-8: Full workflow-host capability contract

The wrapper shall assemble and operate the caller-owned collaborators required
by a selected package. Before every execution, it shall load the package,
resolve its profile, inspect its requirements, and fail closed when a required
capability is absent or only represented as DAR metadata.

The profile contract shall use independently enabled capabilities; it shall not
claim that all profiles expose every integration:

| Host capability | Wrapper responsibility |
| --- | --- |
| Package catalog | Resolve an approved package revision, validate artifacts, apply only approved runtime overrides, and run capability preflight. |
| Model manager | Select matching local or hosted adapters, enforce strict coverage where required, preflight local assets, and apply bounded generation settings. |
| Tool manager | Assemble one registry from configured MCP, host, workspace, web, retrieval, embedding, and subagent bindings. |
| Secrets and files | Store credentials outside package artifacts; enforce workspace-root, size, type, and content-hash policies for file references. |
| State and sessions | Assign tenant and session identity; persist retained session state, approved checkpoints, and concurrency ownership outside DAR's in-memory objects. |
| Guardrails | Register declared live input and tool-input guardrail handlers, fail closed when required handlers are absent, and reject packages requiring unsupported phases. |
| Context manager | Supply declared context selection, local/provider compaction, summarization, token-budget, and prompt-cache policies. |
| Observability | Persist redacted traces, correlate run, workflow revision, and session IDs, stream status, and apply retention and audit policy. |
| Retrieval and embeddings | Own document ingestion, chunking, embedding execution, vector/index storage, permission filtering, freshness, caching, and retrieval tools. |
| Subagents | Provide bounded child-runner callbacks, presets, budgets, concurrency limits, and delegation policy. |

The wrapper shall use a capability matrix rather than treating manifest
declarations as proof that a feature is available. Examples of metadata-only or
otherwise unsupported features must be reported as unavailable before execution,
not silently ignored.

Acceptance criteria:

- A package requiring a missing tool, adapter, guardrail, retrieval backend,
  session store, or context component fails before its first node executes.
- Trace records identify the package revision, selected profile, active model
  adapter, and registered tool provenance without exposing secrets or raw
  sensitive payloads.
- Profile capability choices are composable; an email profile need not provision
  a vector store, and an embedding profile need not obtain Fastmail access.
- A package requiring an unsupported extension or guardrail phase returns a
  clear, non-executing capability failure.

Recommended initial profiles are:

```text
fastmail-local =
  package catalog + local model manager + Fastmail MCP manager
  + approval service + trace/session store

embedding-local =
  package catalog + local embedding adapter + document-root policy
  + vector-index/retrieval service + trace/session store
```

## Example Workflow Operations

### Email workflow

The `email` package may declare these operations:

- `list_unread`: read-only; Fastmail MCP binding; accepts an optional result
  limit.
- `send_email`: side-effecting; Fastmail MCP binding; accepts a subject,
  HTML-body file reference, and configured email-group identifier; requires the
  FR-6 approval handshake.

Example invocations:

```json
{"workflow_id":"email","operation":"list_unread","arguments":{"limit":50}}
```

```json
{
  "workflow_id":"email",
  "operation":"send_email",
  "arguments":{
    "group_id":"email-group",
    "subject":"Subject",
    "body_html_path":"./body.html"
  }
}
```

### Embedding workflow

The `embedding` package may declare `embed_document`, accepting a constrained
document reference. Its manifest shall express Hugging Face embedding model
requirements and its tool contract shall identify the host-owned embedding
adapter for `model/embedding-model`.

The package must not claim that DAR itself downloads, executes, or indexes the
embedding model. A profile or generated host harness owns that adapter and any
index.

```json
{
  "workflow_id":"embedding",
  "operation":"embed_document",
  "arguments":{"document_ref":"foo.txt"}
}
```

## Validation Plan

Implementation shall follow TDD. Before implementation, add focused tests that
initially fail for the required behavior.

1. Validate plugin manifest and skill discovery.
2. Load generated basic, email, and embedding fixture packages with DAR.
3. Execute read-only email behavior through fake Fastmail bindings and a fake
   local model adapter.
4. Prove provisioning rejects an unauthenticated profile, a missing required
   tool, and a changed Fastmail surface snapshot.
5. Prove the approval handshake rejects no-token, altered-digest, expired, and
   replayed write requests.
6. Prove a v1 send handler independently verifies its approved arguments and
   token without replaying an interrupted DAR execution.
7. Prove path containment and file-digest checks reject invalid or changed body
   files.
8. Verify a strict local profile never creates or uses a hosted fallback adapter.
9. Validate the embedding workflow's output shape and expected model identity
   with a fake embedding adapter.
10. Prove capability preflight rejects a workflow whose declared profile lacks a
    required guardrail, retrieval, session, context, or subagent collaborator.
11. Prove trace output is redacted and correlates the package revision, profile,
    adapter, and tool provenance.

## Completion Criteria

The work is complete when the plugin manifest validates, all three skills are
discoverable, generated fixture packages load under DAR, and the focused test
suite proves profile selection, read execution, write approval enforcement, path
containment, local-only model isolation, MCP surface validation, capability
preflight, and redacted observability.
