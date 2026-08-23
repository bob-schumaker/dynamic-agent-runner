# DAR Authoring Plugin Specification

## Metadata

- Status: proposed; not implementation authorization
- Owner: dynamic-agent-runner
- Target: a Codex plugin that authors and runs selected DAR-compatible workflow
  packages
- Prerequisite specifications:
  - `specs/sandbox-workspace-runtime/spec.md` for trusted file ingress before
    file-backed write operations
  - `specs/approval-interruption-resume/spec.md` for DAR's live pause boundary;
    the wrapper owns v1 `auto` and `--ask` decisions because durable continuation
    remains deferred
- Task breakdown: `specs/dar-authoring-plugin/tasks.md`

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
3. one profile-backed MCP tool that sets up execution and runs one configured
   workflow operation; and
4. staged host services for the DAR workflow features a selected profile
   declares; and
5. safety controls for package selection, credentials, local file references,
   state, observability, and side-effecting operations.

Profile creation, OAuth completion, external MCP-surface review, and credential
rotation are a human-only wrapper control plane (local settings UI, CLI, or
admin API), not model-facing MCP operations.

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
- Treating an interrupted DAR workflow as resumable before DAR exposes a public
  graph-preserving continuation API.

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

## Implementation Prerequisites and Release Gates

The plugin is not a DAR-only feature: it becomes executable only after the
following wrapper-owned tasks have passed their focused tests. A gate prevents
the named surface from being registered or advertised as live; it is not a
best-effort warning.

| Gate | Required task | Unlocks | Must remain unavailable before the gate passes |
| --- | --- | --- | --- |
| G0 | Packaging spike: manifest, isolated installation/discovery, and local stdio MCP server lifecycle. | Plugin discovery only. | `run_dar_workflow` and wrapper CLI execution. |
| G1 | Immutable package/operation catalog, tenant/profile ownership checks, profile digest verification, bounded request/response schemas, and wrapper capability matrix. | Catalog preflight. | Arbitrary package paths, profile selection without ownership checks, and every operation with missing wrapper collaborators. |
| G2 | Human-only Fastmail control plane: OAuth/API-token connection storage, least-scope binding, approved surface snapshot creation/review, and passive run-time drift detection. | Fastmail profile preparation. | Fastmail-backed operations, snapshot refresh from the model-facing tool, and credential/provisioning arguments. |
| G3 | Read-only execution runner: local-model selection with strict coverage, caller-supplied MCP bindings, DAR preflight plus wrapper checks, deep-redacted trace/audit store, and `--dry-run`. | `list_unread` and equivalent read-only catalog operations. | Read-only operations whose profile, snapshot, model, or capability checks fail. |
| G4 | Trusted file ingress from `sandbox-workspace-runtime`: no-follow, bounded copy from a configured caller input root into a private virtual workspace, with hash-bound virtual references. | File-backed operation inputs. | `send_email` or any operation accepting a local file reference. |
| G5 | Deterministic write runner: catalog-exact handler bindings, call-cardinality enforcement, `auto` audit path, `--ask` atomic broker, and file-ingress binding. | `send_email` and equivalent deterministic writes. | Model-directed writes, native-DAR-resume claims, and writes lacking G4/G5 evidence. |

Retrieval/embedding, durable conversational sessions, broader guardrail/context
profiles, and subagents are later profile slices. They require their own positive
fixtures and do not block G0–G5; none may be advertised as live in the first
release.

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

The plugin shall import the three upstream skills at a recorded source version,
remove dependencies on the upstream environment, and make the DAR-specific
artifact and host contracts authoritative. Fixture outputs from each adapted
skill must validate against the DAR package loader.

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
before calling DAR: validate the profile's authenticated connection and approved
surface snapshot, initialize the configured MCP client, passively compare the
live `tools/list` identity and input schemas with that snapshot, construct
`MCPToolBinding` handlers from it, and construct the required model adapter.
DAR receives only the validated workflow, registry, and adapter. This runtime
comparison cannot refresh, approve, or widen the snapshot.

The versioned request contract shall have this shape:

```json
{
  "format_version": 1,
  "workflow_id": "email",
  "operation": "list_unread",
  "profile_id": "fastmail-local",
  "arguments": {"limit": 50},
  "session_id": null
}
```

`workflow_id` and `operation` are closed-set identifiers from a host-managed
workflow catalog. The tool must reject arbitrary package paths, executable
commands, model endpoints, and MCP endpoint values in invocation arguments.
It shall not accept authentication, provisioning, surface-refresh, model
endpoint, or approval-token flags from the model-facing request.

The wrapper-owned operation catalog shall map each `workflow_id` and `operation`
pair to an immutable package revision, entrypoint/input construction contract,
JSON argument schema, eligible profile identifiers, allowed tool identifiers,
side-effect class, execution limits, and approved runtime overrides. The wrapper
constructs DAR's required non-empty prompt from this record and the validated
arguments; callers do not supply a free-form prompt for deterministic operations.
Trusted catalog storage shall pin and verify the package artifact digest,
operation-catalog digest, profile digest, and surface-snapshot digest on every
run, together with the configured publisher or trust root.

Responses shall use discriminated, versioned schemas with a non-secret run or
correlation ID and bounded payloads. Required response kinds are `completed`,
`authentication_required`, `surface_changed`, `approval_required`,
`capability_unavailable`, and `failed`.

### FR-5: Provision and bind a configured MCP surface

The wrapper shall only provision named profiles from the host-managed catalog.
The `fastmail` profile shall use the documented
`https://api.fastmail.com/mcp` endpoint, complete or reuse an OAuth/API-token
connection, and request the least sufficient Fastmail grant.

Each profile shall contain a versioned `fastmail-surface.json` capability
snapshot. The snapshot maps stable DAR semantic identifiers, such as
`fastmail.search_mail` and `fastmail.send_email`, to the exact Fastmail MCP tool
names and schemas accepted by that profile. The wrapper shall perform remote MCP
tool discovery for snapshot creation and mutation only in the human control
plane, then validate and explicitly approve the discovered surface before it
creates or updates the snapshot. The run path may passively call `tools/list` to
detect a changed identity or input schema, but creates bindings only from an
already approved snapshot and cannot update it.

The wrapper shall return `authentication_required` when OAuth has not been
completed. It shall return `surface_changed` when a required remote tool is
missing or its material input/output schema has changed. It must not choose a
replacement tool automatically. A profile's surface can be refreshed only by an
explicit human-authorized provisioning request.

OAuth authorization-code flow shall use PKCE, an allowlisted redirect URI, and
validated state and nonce values. Tokens, authorization headers, and raw MCP
instructions must never appear in package artifacts, tool requests/results, or
traces. The control plane shall bind connections immutably to a profile and
scope: read-only for unread-mail profiles and send-only for send profiles unless
additional access is independently justified. Scope escalation, connection
replacement, and revocation invalidate affected snapshots and pending approvals.

Snapshot comparison shall use canonical identity and input-schema digests plus a
pinned HTTPS server identity. The wrapper supplies host-authored semantic
descriptions to DAR rather than forwarding remote tool descriptions. It defines
normalized output contracts itself, then validates and bounds handler outputs
against those contracts, rejecting unexpected sensitive fields and untrusted
instructions.

Acceptance criteria:

- The wrapper creates DAR bindings only after all required remote capabilities
  and schemas match the approved snapshot.
- The human control plane explicitly reviews and records the first capability
  snapshot without persisting a credential in the package artifacts.
- A later remote tool-name or input-schema change fails closed until explicitly
  refreshed by the human control plane.
- `send_email` is unavailable until both G4 trusted file ingress and G5
  deterministic write-runner preflight have passed.

### FR-6: Enforce write approval in the wrapper and DAR boundary

The wrapper shall default to `auto` approval for every deterministic external
action declared by a pre-built, approved operation catalog entry and profile.
Auto approval is valid only while the resolved package revision, operation
catalog entry, profile, MCP-surface snapshot, allowed tool set, model settings,
and workspace roots match their approved values. Each auto-approved call must
match the catalog's exact tool identifier, argument projection from validated
request data, and call-cardinality limit. Any drift fails closed rather than
silently broadening the approval boundary.

Model-directed and dynamically selected side-effecting calls are not eligible
for `auto`; the wrapper rejects them or requires `--ask` brokerage. Read-only
model-directed tools remain subject to their profile budgets and schemas.

The local wrapper CLI shall support these execution modes:

```text
dar-workflow-run --workflow <id> --operation <id> [--dry-run] [--ask]
```

- Default mode is `auto`: execute all declared, profile-allowed tool calls
  that satisfy the deterministic catalog plan without per-call prompts and
  record their provenance in the audit trace.
- `--dry-run`: resolve catalog and profile records, validate package artifacts,
  capability requirements, schemas, path policy, and cached surface snapshot,
  then emit the bounded execution plan. It must not initiate OAuth, refresh MCP
  discovery, invoke a model, or invoke a tool handler.
- `--ask`: send each side-effecting call to an interactive wrapper approval
  broker before its handler runs. The broker displays the normalized action and
  returns an allow/deny decision; it is not a model-provided approval token.

The model-facing `run_dar_workflow` tool uses the selected server policy and may
not request `auto`, `--ask`, or `--dry-run` through invocation arguments.

For `--ask`, the server-side approval record shall use a cryptographically
random, short-lived one-use token and an atomic compare-and-consume transition.
Its canonical action digest shall cover:

- workflow identifier and resolved package revision;
- operation identifier;
- normalized arguments;
- tenant, actor, profile, Fastmail connection, snapshot, and sender identity;
- resolved ordered recipient set, bounded execution parameters, and group alias
  version; and
- exact body bytes or content hashes of referenced local files.

The server shall reject changed, expired, replayed, cross-tenant, or mismatched
approvals. It never accepts a client-provided digest as authoritative. The same
canonical action is included in `auto` audit records, without creating a pending
approval record.

DAR does not currently expose a public continuation API that resumes an
interrupted execution at the pending tool call. The wrapper therefore creates
internal runtime bindings marked `approval_required: no` and owns both `auto`
and `--ask` enforcement in the handler boundary. The generated package still
declares side-effect and approval metadata for design, validation, and audit.
Arbitrary model-tool calls and normal registry construction cannot use the
internal bindings; every handler verifies the operation catalog, profile, policy,
exact argument projection, and remaining call cardinality before external
invocation. Native DAR interruption plus durable resumption is follow-on DAR
work, not an implicit wrapper replay.

Acceptance criteria:

- Default `auto` execution invokes only declared, profile-allowed bindings and
  catalog-exact calls and emits an audit record for every external action.
- An auto-approved model cannot cause a side-effecting call absent from the
  deterministic operation plan.
- `--dry-run` invokes neither model nor external tool handler.
- `--ask` cannot reach a side-effecting handler without a matching, atomically
  consumed server-side approval record.
- Changing a subject, recipient group, package revision, or referenced body file
  after an `--ask` preview invalidates the approval.
- A valid `--ask` approval cannot be consumed twice or by another tenant or actor.

### FR-7: Profile-backed execution owns external collaborators

A host-managed profile shall select the package revision, local model adapter,
MCP bindings, tool handlers, allowed workspace roots, and execution limits.
Profiles may also reference a local OpenAI-compatible, llama.cpp, or MLX
adapter, but the plugin shall not start or discover any of those model services.

Every request is bound to a server-authenticated principal and immutable tenant
identifier before catalog resolution. Profiles, connections, snapshots, package
revisions, sessions, approval records, group aliases, workspace roots, and trace
records are tenant-scoped and require server-side ownership and role checks.

Trusted local CLI file inputs are accepted only from a tenant-scoped allowlisted
input root and must pass G3 file ingress before they become model-facing
operation arguments. The wrapper shall reject traversal, symlinks, non-regular
files, devices, oversized files, and unsupported encoding. It shall use the
hash-bound private copy produced by ingress for the eventual send, preventing
path substitution after approval. The model-facing operation accepts only that
virtual reference, never a physical path. Untrusted HTML must be escaped or
sandboxed in approval UI.

Acceptance criteria:

- A trusted CLI `body_html_path` outside an allowlisted input root is rejected.
- A local-only profile uses strict adapter coverage and cannot silently fall back
  to the default hosted OpenAI adapter.
- Missing profile bindings fail before workflow execution.
- A caller cannot read, select, approve, or execute another tenant's profile,
  connection, package, session, group alias, or trace.

### FR-8: Full workflow-host capability contract

The wrapper shall assemble and operate the caller-owned collaborators required
by a selected package. Before every execution, it shall load the package,
resolve its profile, invoke DAR's capability inspector with the provisioned
registry and adapters, merge the result with wrapper-owned capability checks,
and fail closed when a required capability is absent or only represented as DAR
metadata.

The profile contract shall use independently enabled capabilities; it shall not
claim that all profiles expose every integration:

| Host capability | Wrapper responsibility |
| --- | --- |
| Package catalog | Resolve an approved package revision, validate artifacts, apply only approved runtime overrides, and run capability preflight. |
| Model manager | Select matching local or hosted adapters, enforce strict coverage where required, preflight local assets, and apply bounded generation settings. |
| Tool manager | Assemble one registry from configured MCP, host, workspace, web, retrieval, and embedding bindings. |
| Secrets and files | Store credentials outside package artifacts; enforce workspace-root, size, type, and content-hash policies for file references. |
| State and sessions | Assign tenant and session identity; persist wrapper conversation and audit records, and own concurrency. Do not claim graph-state checkpoint restore or interrupted-run continuation until DAR supports it. |
| Guardrails | Register declared live input and tool-input guardrail handlers, fail closed when required handlers are absent, and reject packages requiring unsupported phases. |
| Context manager | Supply declared context selection, local/provider compaction, summarization, token-budget, and prompt-cache policies. |
| Observability | Deep-redact or allowlist persisted trace fields, correlate run, workflow revision, and session IDs, stream status, and apply retention and audit policy. DAR's top-level event redaction alone is insufficient. |
| Retrieval and embeddings | Own document ingestion, chunking, embedding execution, vector/index storage, permission filtering, freshness, caching, and host-registered retrieval or `embed_document` tool handlers. |

Subagent bindings are explicitly deferred from the first wrapper release. It
shall not configure `SubagentRunner` or `AskLLMRunner` collaborators, expose
`run_subagent`, `run_subagents`, or `ask_llm`, or advertise subagent capability
as live. A package or operation that requires any of those tools must fail
capability preflight before execution. A later slice may integrate the DAR
subagent tool pack only with explicit child-runner, preset, budget, concurrency,
tool-isolation, and delegation-policy configuration.

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
- Persisted trace tests prove raw email, recipients, bodies, OAuth tokens,
  authorization headers, and nested sensitive tool payloads are excluded unless
  an explicitly approved policy allows them.

Recommended initial profiles are:

```text
fastmail-local =
  package catalog + local model manager + Fastmail MCP manager
  + approval service + trace/session store

embedding-local =
  package catalog + host-registered embedding tool + document-root policy
  + vector-index/retrieval service + trace/session store
```

Delivery shall be staged, despite the full host contract:

1. v1 delivers package and operation catalogs, local-model execution, Fastmail
   read-only profiles, path policy, capability preflight, and redacted tracing.
2. v1.1 adds deterministic write operations with default `auto` execution and
   optional `--ask` brokerage through the FR-6 wrapper-only binding exception.
3. Later profile slices add positive fixtures for retrieval/embeddings, durable
   conversational sessions, guardrails/context management, and subagents. The
   first release has no subagent binding or delegation surface. A capability may
   not be advertised as live until its positive fixture passes.

The packaging spike is the first implementation deliverable. It shall select the
Codex manifest/config format, prove isolated installation and discovery, start
and stop the local stdio server, and prove that no undocumented plugin-path
interpolation is required.

## Example Workflow Operations

### Email workflow

The `email` package may declare these operations:

- `list_unread`: read-only; Fastmail MCP binding; accepts an optional result
  limit.
- `send_email`: side-effecting; Fastmail MCP binding; accepts a subject,
  hash-bound virtual HTML-body reference, and configured email-group identifier;
  defaults to FR-6 auto approval and supports `--ask` brokerage. The trusted
  local CLI ingests a physical body path before forming this operation request.

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
    "body_html_ref":"workspace://ws_opaque_id/body.html"
  }
}
```

Trusted local CLI invocation performs ingress before it submits the operation:

```text
dar-workflow-run --workflow email --operation send_email \
  --group-id email-group --subject Subject --body-html-path ./body.html
```

### Embedding workflow

The `embedding` package may declare `embed_document`, accepting a constrained
document reference. Its tool contract shall identify a host-registered
`embed_document` handler for `model/embedding-model` and define its vector
output schema. DAR's model adapter remains reserved for LLM nodes.

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
5. Prove default `auto` execution rejects undeclared, profile-disallowed, and
   drifted tool bindings while recording each external action.
6. Prove `--dry-run` invokes neither a model nor an external tool handler.
7. Prove `--ask` rejects changed, expired, cross-tenant, and replayed approvals,
   and only invokes the handler after an atomic broker decision.
8. Prove a v1 send handler enforces its operation catalog and policy without
   replaying an interrupted DAR execution.
9. Prove path containment and file-digest checks reject invalid or changed body
   files.
10. Verify a strict local profile never creates or uses a hosted fallback adapter.
11. Validate the embedding workflow's output shape and expected model identity
    with a fake embedding adapter.
12. Prove capability preflight rejects a workflow whose declared profile lacks a
    required guardrail, retrieval, session, context, or subagent collaborator;
    in the first release, every subagent collaborator is unavailable.
13. Prove trace output is redacted and correlates the package revision, profile,
    adapter, and tool provenance.

## Completion Criteria

The first release is complete only when G0–G3 pass: the plugin manifest and
skills are discoverable, generated fixture packages load under DAR, and focused
tests prove tenant/profile selection, read-only execution, local-only model
isolation, Fastmail surface validation, capability preflight, and redacted
observability. It must not expose file-backed writes, retrieval/embeddings,
durable sessions, broader guardrails/context, or subagents.

The deterministic-write extension is complete only when G4 and G5 also pass:
focused tests prove trusted file ingress, path containment, `auto` audit
binding, `--ask` replay resistance, and no claim of DAR graph continuation.
