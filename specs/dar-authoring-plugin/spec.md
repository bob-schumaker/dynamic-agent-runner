# DAR Authoring Plugin Specification

## Metadata

- Status: proposed; not implementation authorization
- Owner: dynamic-agent-runner
- Target: a Codex plugin that authors and runs selected DAR-compatible workflow
  packages, distributed from the approved Artifactory Python index
- Prerequisite specifications:
  - `specs/sandbox-workspace-runtime/spec.md` for trusted file ingress before
    file-backed workflow inputs
  - `specs/approval-interruption-resume/spec.md` for DAR's live pause boundary;
    the wrapper owns v1 `workflow_auto` and `--ask` decisions because durable
    continuation remains deferred
- Task breakdown: `specs/dar-authoring-plugin/tasks.md`

## Objective

Provide a Codex plugin named `dar-authoring` for designing, validating, and
executing selected Dynamic Agent Runner (DAR) workflow packages. The plugin
owns authoring policy and the full host-runtime integration; DAR remains the
generic graph executor.

## References

- [Connecting AI tools via Fastmail's MCP server](https://www.fastmail.help/hc/en-us/articles/15869557281295-Connecting-AI-tools-via-Fastmail-s-MCP-server)
- [An MCP server for Fastmail](https://www.fastmail.com/blog/an-mcp-server-for-fastmail/)

Fastmail is a non-normative example of a configured MCP connection. The plugin
does not contain Fastmail-specific runtime behavior: it operates any
human-configured MCP connection through its approved tool-surface snapshot.

## Problem Statement

DAR consumes generated `agent-design.md`, `agent-runtime.yaml`, and
`agent-graph.mmd` package artifacts, but it intentionally does not own package
authoring policy, MCP-server lifecycle, host credentials, local model lifecycle,
or evaluation infrastructure. A plugin is needed to make those authoring and
host responsibilities coherent without expanding DAR's runtime boundary.

## Scope

The Artifactory-published `dar-authoring` plugin shall include the adapted
skills, DAR support tools, and a pinned compatible `dynamic-agent-runner`
runtime dependency. Its MCP launcher uses an isolated `uvx` environment and a
verified exact plugin version. A workflow package is instead a local directory
or ZIP data artifact consumed by that plugin; it is not independently installed
or executed by `uvx`.

The plugin shall provide:

1. three DAR-scoped Codex skills;
2. templates for canonical DAR package artifacts;
3. one profile-backed MCP tool that invokes one prepared saved workflow; and
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
- Treating a local workflow directory or ZIP as executable code, an installable
  Python distribution, or an authority to modify the installed plugin runtime.
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
It must run a local stdio MCP server through a checked-in `uvx` launch contract,
resolve the exact plugin wheel only from the approved Artifactory index, and
must not depend on undocumented plugin-path interpolation. Release verification
must prove the published wheel contains all runtime package assets required for
a clean-directory MCP `initialize` response; a source checkout is not proof.

## Implementation Prerequisites and Release Gates

The plugin is not a DAR-only feature: it becomes executable only after the
following wrapper-owned tasks have passed their focused tests. A gate prevents
the named surface from being registered or advertised as live; it is not a
best-effort warning.

| Gate | Required task | Unlocks | Must remain unavailable before the gate passes |
| --- | --- | --- | --- |
| G0 | Packaging spike: Artifactory exact-version wheel, isolated `uvx` installation/discovery, packaged-runtime asset verification, and local stdio MCP server lifecycle. | Plugin discovery only. | `run_dar_workflow` and wrapper CLI execution. |
| G1 | Immutable workflow catalog, tenant/profile ownership checks, profile digest verification, bounded request/response schemas, and wrapper capability matrix. | Catalog preflight. | Arbitrary package paths, caller-selected runtime profiles, and workflows with missing wrapper collaborators. |
| G2 | Human-only connection control plane: credential storage, least-scope binding, approved MCP-surface snapshot creation/review, and passive run-time drift detection. | Optional MCP profile preparation. | MCP-backed workflows, snapshot refresh from the model-facing tool, and credential/provisioning arguments. |
| G3 | Generic execution runner: strict model selection, caller-supplied optional MCP bindings, DAR preflight plus wrapper checks, deep-redacted trace/audit store, and `--dry-run`. | Workflows with no external tools or with approved read-only tools. | Workflows whose profile, snapshot, model, or capability checks fail. |
| G4 | Trusted file ingress from `sandbox-workspace-runtime`: no-follow, bounded copy from a configured caller input root into a private workspace, with hash-bound opaque input artifacts. | File-backed workflow inputs. | A workflow invocation accepting a local file reference. |
| G5 | Model-directed external-tool runner: profile-bound `workflow_auto` audit path, `--ask` atomic broker, tool-set/budget enforcement, and file-ingress binding. | Workflows that may make external side effects. | Side-effecting calls lacking G4/G5 evidence, native-DAR-resume claims, and any tool outside the approved profile surface. |

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

### Natural-language authoring and workflow descriptor

The entry skill shall accept a user's natural-language description of the
desired workflow, together with any supplied examples, files, and documentation.
It shall use those materials to generate a canonical, immutable DAR workflow
package revision. The user is not required to write a descriptor. The generated
versioned `WorkflowDescriptor` is the package's authoring-to-runtime handoff and
records the design decisions the skill made; `run_dar_workflow` is not an
authoring or provisioning API. Every capability below is optional. A basic
reasoning workflow therefore needs only its purpose and model requirement; a
workflow with no MCP tools and no skills is valid.

```yaml
format_version: 1
workflow_id: document-helper
purpose: Answer questions about supplied documents.
dar_runtime:
  distribution: dynamic-agent-runner
  required_version: 0.1.0
model:
  profile_requirement: local-general-model
skills: []
tools: []
workspace:
  accepted_input_types: [text/plain]
  scratch_access: none
input_contract:
  mode: hybrid
  structured_input_schema: null
  additional_context_max_bytes: 8192
output:
  schema_ref: document-answer-v1
limits:
  max_steps: 8
```

The descriptor may additionally declare package-local skill identifiers,
MCP-connection requirements and approved remote tool identifiers, host tool
requirements, workspace input/scratch requirements, retrieval or embedding
requirements, guardrails, context/session requirements, output schema, and
resource limits. For a bounded task interface it may declare an
`input_contract` with a JSON structured-input schema and field-to-workflow
mapping. It always retains the original user prompt. Information that the
invoking model cannot place in the schema is preserved as a bounded plain-text
`additional_context` field; it is not discarded or silently turned into a tool
argument. Explicit user files are ingressed as opaque input artifacts. It names
stable host-managed references; it never contains an
MCP endpoint, credential, raw token, physical path, executable command, or an
unreviewed remote tool description. `agent-tool-contract-design` is used only
when `tools` is nonempty, and `agent-evaluation` only when formal evaluation is
requested.

The authoring result shall be a canonical package directory by default, with an
optional deterministic ZIP export containing the same package files. Both forms
must include `agent-design.md`, `agent-runtime.yaml`, `agent-graph.mmd`, the
generated descriptor, tool/evaluation artifacts when applicable, and a package
manifest with digests. A ZIP is a portable delivery format, not an executable
bundle; import extracts and validates it before registration.

The generated package records the descriptor digest, exact DAR runtime
compatibility requirement, and exact capability requirements. The preparation
path rejects a package whose DAR requirement does not match the runtime bundled
by the installed plugin. It then resolves a compatible immutable runtime profile
when the package is registered; the caller cannot replace its model, skills,
tools, or connection in a run request. The authoring result shall include the
package artifacts, a capability report, and any evaluation plan requested by the
generated descriptor.

Authoring may later use package-generation tools, but this specification does
not assume, expose, or require any such tool. Its v1 contract is the skill's
validated artifact output.

The package's graph and tool contracts define a specifically bounded task, not a
general-purpose interactive tool console. For every declared MCP or host tool,
the generated design records the task-specific invocation pattern, allowed
schemas, and limits. The generic wrapper only supplies the validated hybrid
input and dispatches the package's approved profile bindings; it does not add
service-specific instructions or tools.

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

### Package preparation is separate from execution

Before a package can run, the same authoring skill or a dedicated preparation
skill may be invoked with a package directory or ZIP and a user goal. It shall
validate/import the package, resolve and prepare its host-owned runtime profile,
and register an immutable `workflow_id`. Preparation is a trusted local
control-plane action, not a second model-facing MCP execution tool. It may ask a
human to complete connection authentication, choose an already configured
profile compatible with the package, or provide allowed input files. It must not
invent credentials, enable undeclared capabilities, or silently modify package
artifacts.

For example, a request to use `custom-email.zip` to send an email causes the
skill to import and prepare the package if necessary, ingest explicitly supplied
local inputs, derive the package's validated structured input and bounded
additional context without invoking a workflow tool, then call the generic
runner with its registered `workflow_id`. A later request can reuse that
registered workflow with the same hybrid input preparation.

### FR-4: Expose one narrow execution tool

The plugin shall expose exactly one model-facing MCP tool named
`run_dar_workflow`. It executes one selected saved workflow revision using the
runtime profile bound to that workflow. It is not a shell-command proxy for the
`dynamic-agent-runner` CLI.

The MCP server shall use DAR's library API because execution may require a
caller-provided tool registry, explicit MCP bindings, and a strict local model
adapter. The DAR CLI alone cannot supply those collaborators.

For a configured profile, the server shall perform the required execution setup
before calling DAR: validate the workflow revision and its bound profile,
construct the required model adapter, and, for each declared MCP connection,
validate its authenticated connection and approved surface snapshot, initialize
the configured MCP client, and passively compare live `tools/list` identity and
input schemas with that snapshot. It constructs `MCPToolBinding` handlers only
for declared snapshot tools. Workflows without MCP requirements perform none of
these connection steps. DAR receives only the validated workflow, registry, and
adapter. Runtime comparison cannot refresh, approve, or widen a snapshot.

The versioned request contract shall have this shape:

```json
{
  "format_version": 1,
  "workflow_id": "email-assistant",
  "input": {
    "original_prompt": "List my unread email.",
    "structured_input": {"query": "unread email"},
    "additional_context": "",
    "workspace_input_ids": []
  },
  "session_id": null
}
```

`workflow_id` is a closed-set identifier from a host-managed workflow catalog.
The `input` envelope retains `original_prompt`, optionally carries a
schema-validated `structured_input`, bounded `additional_context`, and optional
opaque workspace artifacts previously ingressed by a trusted local control
plane. It is workflow input, not a request to alter a package or profile. The
tool must reject arbitrary package paths, executable commands, model endpoints,
MCP endpoint values, skill sources, and profile identifiers in invocation
arguments. It shall not accept
authentication, provisioning, surface-refresh, model endpoint, or
approval-token flags from the model-facing request.

The wrapper-owned workflow catalog maps each `workflow_id` to an immutable
package revision, descriptor digest, bound runtime-profile digest, allowed tool
identifiers, hybrid input/output schemas, workspace policy, execution limits,
and approved runtime overrides. Trusted catalog storage pins and verifies the
package artifact, workflow record, profile, and required surface-snapshot
digests on every run, together with the configured publisher or trust root.

Responses shall use discriminated, versioned schemas with a non-secret run or
correlation ID and bounded payloads. Required response kinds are `completed`,
`authentication_required`, `surface_changed`, `approval_required`,
`capability_unavailable`, and `failed`.

### FR-5: Provision and bind optional configured MCP surfaces

The wrapper shall provision only named connections and profiles from the
host-managed catalog. A connection's transport, authentication method, and
least-privilege external scope are selected in the human control plane.

Each MCP connection requirement shall reference a versioned approved surface
snapshot. The snapshot maps stable DAR semantic identifiers to the exact remote
MCP tool names and schemas accepted by that connection. The wrapper performs
remote MCP discovery for snapshot creation and mutation only in the human
control plane, then validates and explicitly approves the discovered surface
before it creates or updates the snapshot. The run path may passively call
`tools/list` to detect a changed identity or input schema, but creates bindings
only from an already approved snapshot and cannot update it.

The wrapper shall return `authentication_required` when OAuth has not been
completed. It shall return `surface_changed` when a required remote tool is
missing or its material input/output schema has changed. It must not choose a
replacement tool automatically. A profile's surface can be refreshed only by an
explicit human-authorized provisioning request.

When OAuth is used, authorization-code flow shall use PKCE, an allowlisted
redirect URI, and validated state and nonce values. Tokens, authorization
headers, and raw MCP instructions must never appear in package artifacts, tool
requests/results, or traces. The control plane binds connections immutably to a
profile and approved scope. Scope escalation, connection replacement, and
revocation invalidate affected snapshots and pending approvals.

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
- A workflow requiring an MCP tool is unavailable until its required connection
  and snapshot pass preflight. A Fastmail email workflow is one example.

### FR-6: Enforce write approval in the wrapper and DAR boundary

The wrapper shall default to `workflow_auto` for every run of a pre-built,
approved workflow revision. The CLI exposes this policy as its default `auto`
mode. It is valid only while the resolved package revision, descriptor, bound
profile, MCP-surface snapshots, allowed tool set, model settings, and workspace
policy match their approved values. Under `workflow_auto`, the workflow model
may select any schema-valid exposed tool call, including a side-effecting call;
the wrapper enforces the approved tool set, schema, connection snapshot,
side-effect metadata, resource budgets, and call cardinality limits. It does
not require a predeclared argument projection. Any profile or surface drift
fails closed rather than silently widening that boundary.

The local wrapper CLI shall support these execution modes:

```text
dar-workflow-run --workflow <id> --prompt <text> \
  [--workspace-file <path>]... [--dry-run] [--ask]
```

- Default mode is `auto` (`workflow_auto`): execute schema-valid tool calls
  chosen by the workflow model within its declared, profile-allowed surface and
  record every external action in the audit trace.
- `--dry-run`: resolve workflow and bound-profile records, validate package
  artifacts, capability requirements, schemas, workspace-input policy, and
  cached surface snapshots, then emit the resolved configuration. It must not
  predict model-selected tool calls, initiate OAuth, refresh MCP discovery,
  invoke a model, or invoke a tool handler.
- `--ask`: send each side-effecting call to an interactive wrapper approval
  broker before its handler runs. The broker displays the normalized action and
  returns an allow/deny decision; it is not a model-provided approval token.

The model-facing `run_dar_workflow` tool uses the selected server policy and may
not request `auto`, `--ask`, or `--dry-run` through invocation arguments.

For `--ask`, the server-side approval record shall use a cryptographically
random, short-lived one-use token and an atomic compare-and-consume transition.
Its canonical action digest shall cover:

- workflow identifier and resolved package revision;
- run identifier and normalized final tool invocation;
- tenant, actor, profile, connection, and snapshot identity;
- applicable bounded execution parameters; and
- opaque input-artifact identifiers and protected content hashes.

The server shall reject changed, expired, replayed, cross-tenant, or mismatched
approvals. It never accepts a client-provided digest as authoritative. The same
canonical action is included in `workflow_auto` audit records, without creating
a pending approval record.

DAR does not currently expose a public continuation API that resumes an
interrupted execution at the pending tool call. The wrapper therefore creates
internal runtime bindings marked `approval_required: no` and owns both
`workflow_auto` and `--ask` enforcement in the handler boundary. The generated
package still declares side-effect and approval metadata for design, validation,
and audit.
Arbitrary model-tool calls and normal registry construction cannot use the
internal bindings; every handler verifies the workflow record, profile, policy,
allowed tool set, schema, and remaining call cardinality before external
invocation. Native DAR interruption plus durable resumption is follow-on DAR
work, not an implicit wrapper replay.

Acceptance criteria:

- Default `workflow_auto` execution invokes only declared, profile-allowed
  bindings and emits an audit record for every external action.
- A workflow running under `workflow_auto` can issue an email or other
  side-effecting request when its prompt and exposed tool schema lead the model
  to do so; it cannot call a tool absent from its approved profile surface.
- `--dry-run` invokes neither model nor external tool handler.
- `--ask` cannot reach a side-effecting handler without a matching, atomically
  consumed server-side approval record.
- Changing a subject, recipient group, package revision, or referenced body file
  after an `--ask` preview invalidates the approval.
- A valid `--ask` approval cannot be consumed twice or by another tenant or actor.

### FR-7: Profile-backed execution owns external collaborators

A host-managed profile is bound to a registered package revision and selects its
local model adapter, MCP bindings, tool handlers, allowed workspace roots, and
execution limits.
Profiles may also reference a local OpenAI-compatible, llama.cpp, or MLX
adapter, but the plugin shall not start or discover any of those model services.

Every request is bound to a server-authenticated principal and immutable tenant
identifier before catalog resolution. Profiles, connections, snapshots, package
revisions, sessions, approval records, group aliases, workspace roots, and trace
records are tenant-scoped and require server-side ownership and role checks.

Trusted local CLI file inputs are accepted only from a tenant-scoped allowlisted
input root and must pass G4 file ingress before they become workspace input
artifacts.
The wrapper shall reject traversal, symlinks, non-regular files, devices,
oversized files, and unsupported encoding. It shall use the hash-bound private
copy produced by ingress for the eventual send, preventing path substitution
after approval. The model-facing invocation accepts only an opaque input-artifact
identifier, never a physical path or workspace URI. Untrusted HTML must be
escaped or sandboxed in approval UI.

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
as live. A package that requires any of those tools must fail
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
- Profile capability choices are composable; an MCP-backed email workflow need
  not provision a vector store, and an embedding workflow need not obtain MCP
  access.
- A package requiring an unsupported extension or guardrail phase returns a
  clear, non-executing capability failure.
- Persisted trace tests prove raw email, recipients, bodies, OAuth tokens,
  authorization headers, and nested sensitive tool payloads are excluded unless
  an explicitly approved policy allows them.

Illustrative, not built-in, profiles are:

```text
email-local =
  package catalog + local model manager + configured email MCP connection
  + approval service + trace/session store

embedding-local =
  package catalog + host-registered embedding tool + document-root policy
  + vector-index/retrieval service + trace/session store
```

Delivery shall be staged, despite the full host contract:

1. v1 delivers package and workflow catalogs, local-model execution, optional
   configured read-only MCP surfaces, path policy, capability preflight, and
   redacted tracing.
2. v1.1 adds model-directed external side effects with default `workflow_auto`
   execution (the CLI's `auto` mode) and optional `--ask` brokerage through the
   FR-6 wrapper-only binding exception.
3. Later profile slices add positive fixtures for retrieval/embeddings, durable
   conversational sessions, guardrails/context management, and subagents. The
   first release has no subagent binding or delegation surface. A capability may
   not be advertised as live until its positive fixture passes.

The packaging spike is the first implementation deliverable. It shall select the
Codex manifest/config format, prove isolated installation and discovery, start
and stop the local stdio server, and prove that no undocumented plugin-path
interpolation is required.

## Example workflow descriptors and invocation

### Email workflow with an optional MCP connection

The authoring skill can produce a descriptor like this. `email_connection` is a
host-managed, approved MCP connection reference; the descriptor does not embed
Fastmail-specific behavior, an endpoint, or credentials.

```yaml
format_version: 1
workflow_id: email-assistant
purpose: Interact with the user's email using the configured email MCP tools.
model:
  profile_requirement: local-general-model
skills: [email-workflow-guidance]
tools:
  - kind: mcp
    connection_requirement: email_connection
    tool_ids: [search_mail, send_email]
  - kind: host
    tool_ids: [generate_image]
workspace:
  accepted_input_types: [text/html]
  scratch_access: none
input_contract:
  mode: hybrid
  structured_input_schema:
    type: object
    properties:
      recipient: {type: string}
      subject: {type: string}
      image_brief: {type: string}
    additionalProperties: false
  additional_context_max_bytes: 8192
limits:
  max_steps: 12
  max_external_tool_calls: 4
```

After the package has been designed and registered, the preparation skill
retains the prompt and derives only the schema fields it can validate; the
workflow design directs its allowed tool calls. The optional `generate_image`
declaration is needed only if the author wants image generation; an email MCP
connection alone cannot produce an image.

```json
{
  "format_version": 1,
  "workflow_id": "email-assistant",
  "input": {
    "original_prompt": "List all of my unread email.",
    "structured_input": {},
    "additional_context": "",
    "workspace_input_ids": []
  }
}
```

The local CLI ingresses a body file before it runs the workflow; the model sees
only the opaque workspace artifact named by the wrapper, never `./body.html`.

```text
dar-workflow-run --workflow email-assistant \
  --prompt 'Send the attached HTML body to email-group with subject
  "Subject".' \
  --workspace-file ./body.html
```

The preparation skill also supports the portable-package form of the same
experience:

```text
use the workflow custom-email.zip to send email to john@example.com with the
subject "happy birthday" and a randomly generated birthday image involving penguins
```

It imports and validates the ZIP if it is not registered, resolves only the
package's declared email and image capabilities, then runs the registered
workflow under its default `workflow_auto` policy. Likewise, a directory package
and text input can be prepared and invoked as:

```text
use the workflow in custom-email/ to send email to sally@example.com about
"Welcome to the neighborhood" with content from foo.txt
```

The preparation path ingresses `foo.txt`; the runner receives an opaque input
artifact, structured fields where derivable, bounded additional context, and the
original prompt—not the physical path.

### Embedding workflow

The authoring descriptor may instead declare a host-registered embedding tool
for `model/embedding-model`, a text workspace input, and a vector output schema.
MCP and skills remain empty. DAR's model adapter remains reserved for LLM nodes.

The package must not claim that DAR itself downloads, executes, or indexes the
embedding model. A profile or generated host harness owns that adapter and any
index.

```json
{
  "format_version": 1,
  "workflow_id": "embedding",
  "input": {
    "original_prompt": "Return an embedding for the attached document.",
    "structured_input": {},
    "additional_context": "",
    "workspace_input_ids": ["ingressed-input-artifact"]
  }
}
```

## Validation Plan

Implementation shall follow TDD. Before implementation, add focused tests that
initially fail for the required behavior.

1. Validate plugin manifest and skill discovery.
2. Load generated basic, MCP-backed email, and embedding fixture packages with DAR.
3. Execute a workflow with no tools and a workflow with fake MCP bindings using
   fake local model adapters.
4. Prove provisioning rejects an unauthenticated connection, a missing required
   tool, and a changed MCP surface snapshot.
5. Prove default `workflow_auto` execution rejects undeclared,
   profile-disallowed, and drifted tool bindings while recording each external
   action.
6. Prove `--dry-run` invokes neither a model nor an external tool handler.
7. Prove `--ask` rejects changed, expired, cross-tenant, and replayed approvals,
   and only invokes the handler after an atomic broker decision.
8. Prove a v1 side-effecting handler enforces its workflow profile and policy without
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
isolation, optional MCP surface validation, capability preflight, and redacted
observability. It must not expose file-backed writes, retrieval/embeddings,
durable sessions, broader guardrails/context, or subagents.

The deterministic-write extension is complete only when G4 and G5 also pass:
focused tests prove trusted file ingress, path containment, `workflow_auto`
audit binding, `--ask` replay resistance, and no claim of DAR graph continuation.
