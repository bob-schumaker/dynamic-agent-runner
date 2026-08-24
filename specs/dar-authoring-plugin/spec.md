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
- Implementation plan: `specs/dar-authoring-plugin/plan.md`

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
verified exact plugin version. Release metadata is verified from a configured
trusted signing-key root, has an expiry and minimum accepted version, and can
revoke a signing key or artifact version; an expired, revoked, or below-floor
otherwise-valid release is rejected. A workflow package is instead a local
directory or ZIP data artifact consumed by that plugin; it is not independently
installed or executed by `uvx`.

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
    adapted-skill-provenance.yaml
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
| G1 | Immutable package catalog, installation identity, profile capability records, `WorkflowPolicy` compilation, and bounded preparation schemas. | Package-only preparation and catalog preflight. | Arbitrary package paths, caller-selected runtime profiles, executable aliases, and workflows with missing wrapper collaborators. |
| G2 | Human-only connection control plane: credential storage, least-scope binding, approved MCP-surface snapshot creation/review, plugin-owned client lifecycle, and passive run-time drift detection. | Optional MCP profile preparation. | MCP-backed workflows, snapshot refresh from the model-facing tool, and credential/provisioning arguments. |
| G3 | Generic execution runner: strict model selection, DAR preflight plus wrapper checks, deep-redacted trace/audit store, and `--dry-run`. | Workflows with no external tools. An MCP-backed read-only workflow also requires G2. | Workflows whose model or capability checks fail. |
| G4 | Trusted file ingress from `sandbox-workspace-runtime`: no-follow, bounded copy from a configured caller input root into a private workspace, with hash-bound opaque input artifacts. | File-backed workflow inputs. | A workflow invocation accepting a local file reference. |
| G5 | Model-directed external-tool runner: profile-bound `workflow_auto` audit path, `--ask` atomic broker, and tool-set/budget enforcement. | Workflows that may make external side effects. MCP side effects also require G2; file-backed arguments also require G4. | Side-effecting calls lacking the applicable gate evidence, native-DAR-resume claims, and any tool outside the approved profile surface. |

G3 depends only on G0 and G1. G2 and G4 each depend on G0 and G1; they are
additive rather than serial prerequisites. G5 depends on G0, G1, and G3, plus G2
or G4 only when the selected registration requires MCP or file-backed arguments.
Retrieval/embedding, durable conversational sessions, broader guardrail/context
profiles, and subagents are later profile slices. They require their own positive
fixtures and do not block the base release; none may be advertised as live before
its gate passes.

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

`skills/adapted-skill-provenance.yaml` shall cover every copied skill with its
upstream repository/source locator, immutable revision, copied path, applicable
license or bundled notice, recorded redistribution review, and concise
DAR-specific modification summary. It is the reproducible adaptation baseline;
the plugin must reject a copied skill missing that coverage.

Acceptance criteria:

- A basic reasoning package and a bounded tool-use package can be authored from
  the templates and loaded by DAR.
- A workflow loop declares a finite iteration or step bound.
- The generated design identifies host-owned collaborators rather than implying
  that DAR starts servers or owns credentials.

### Natural-language authoring and workflow descriptor

The entry skill shall accept a user's natural-language description of the
desired workflow, together with explicitly supplied examples, files, and
documentation. Inline prompt text is intentional authoring input. Referenced
material is instead supplied through a human-issued `AuthoringMaterialSet` of
opaque, bounded, versioned artifact references. Each member is reference-only or
explicitly distributable; skills receive only the approved content projection and
metadata, never a physical path. The set is principal- and expiry-bound. It shall
use those materials to generate a canonical, immutable DAR workflow package
revision. The user is not required to write a descriptor. The generated versioned
`WorkflowDescriptor` is the package's authoring-to-runtime handoff and records
the design decisions the skill made; `run_dar_workflow` is not an authoring or
provisioning API. Every capability below is optional. A basic reasoning workflow
therefore needs only its purpose and model requirement; a workflow with no MCP
tools and no skills is valid.

```yaml
format_version: 1
package_id: document-helper
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
  field_precedence: original_prompt
task_invocation:
  entrypoint: answer_document_question
  allowed_tool_ids: []
  max_total_tool_calls: 0
  allowed_structured_input_fields: []
  allowed_artifact_roles: [document]
  terminal_output_schema_ref: document-answer-v1
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

`skills` maps to DAR's existing package-local skill contract: generated skill
bodies live under `skill-bundle/`, manifest entries use `bundled_path`, eligible
nodes name them through `skill_refs`, and the generated runtime explicitly opts
into `skill_source_resolution`. The package must use DAR's existing deterministic
prompt order and byte limits; an identifier alone never authorizes an external
skill source.

The authoring result shall be a canonical package directory by default, with an
optional deterministic ZIP export containing the same package files. Both forms
must include `agent-design.md`, `agent-runtime.yaml`, `agent-graph.mmd`, the
generated descriptor, tool/evaluation artifacts when applicable, and a package
manifest with digests. A ZIP is a portable delivery format, not an executable
bundle; import extracts and validates it before registration.

Import first streams an archive into a fresh private staging root. It rejects
absolute, parent-traversal, duplicate, symlink, hard-link, device, and special
entries; enforces configured entry-count, uncompressed-byte, per-file, and
compression-ratio limits; and uses descriptor-relative no-follow writes. Its
canonical manifest enumerates every regular file path, byte count, and SHA-256,
the package/schema version, and DAR compatibility requirement. Extraction is
accepted only when the enumerated files and digests match exactly. A locally
authored package requires an explicit local trust confirmation recorded against
its manifest digest; a package received from another publisher requires a valid
signature from a recipient-configured trusted publisher key. Registration never
overwrites an existing revision; a changed package creates a new revision after
review.

Directory import uses the same bounded, descriptor-relative no-follow staging
copy and validation as ZIP import; trust is never attached to a mutable source
directory. A package identity is the portable `package_id` plus its manifest
`revision_digest`. Once G3 and the applicable capability gates bind that policy,
host registration creates an installation-local `workflow_id` alias bound
immutably to that executable registration. Re-import of the same digest is
idempotent; an alias collision fails unless the caller explicitly registers a new
alias; prior revisions remain addressable for trace/audit retention and are never
silently rebound.

The signed payload is canonical-manifest-v1: the complete manifest file list,
file hashes and byte counts, package/schema/DAR compatibility versions, and
`package_id`. V1 accepts Ed25519 signatures carrying a key ID. Each installation
keeps an explicit local allowlist of trusted publisher key fingerprints; an
unknown key rejects a received package. The authoring skill cannot access signing
keys. A separate local signing control plane may sign an explicitly selected
export after displaying its manifest digest.

Authoring inputs are private by default. An `AuthoringMaterialSet` member may be
copied into a distributable package only when the human marks that exact versioned
reference distributable and the package manifest records its role and digest.
The skill may retain only redacted provenance in traces. Unselected or
reference-only authoring material, credentials, and source paths must not become
package files, package-local skills, traces, evaluation fixtures, or exports.

The generated package records the descriptor digest, exact DAR runtime
compatibility requirement, and exact capability requirements. The preparation
path rejects a package whose DAR requirement does not match the runtime bundled
by the installed plugin. G1 compiles the descriptor and tool contracts into an
immutable `WorkflowPolicy`; it validates logical requirements without contacting
or binding a live profile, MCP connection, or deferred capability. A later
capability-eligible preparation binds one compatible profile and approved surface
snapshots to that policy as an immutable `WorkflowRegistration`; the caller cannot
replace its model, skills, tools, or connection in a run request. The authoring
result shall include the package artifacts, a capability report, and any
evaluation plan requested by the generated descriptor.

Authoring may later use package-generation tools, but this specification does
not assume, expose, or require any such tool. Its v1 contract is the skill's
validated artifact output.

The package's graph and tool contracts define a specifically bounded task, not a
general-purpose interactive tool console. For every declared MCP or host tool,
the generated design records the task-specific invocation pattern, allowed
schemas, and limits. The generic wrapper only supplies the validated hybrid
input and dispatches the package's approved profile bindings; it does not add
service-specific instructions or tools.

`task_invocation` is a required generated, machine-validated package artifact.
For every task entrypoint it declares a closed tool-id set, a total call limit,
allowed structured-input fields, allowed artifact roles, and terminal output
schema. A workflow can remain model-directed inside that finite DAR graph, but
it cannot add a tool, accept an undeclared argument source, exceed its declared
cardinality, or expose an unbounded interactive tool loop. DAR graph validation
and wrapper preflight must reject a package with missing or non-finite
`task_invocation` rules.

For every allowed tool argument, `task_invocation` also declares an
`argument_sources` policy: a sealed structured field, a cited original-prompt
span, a named artifact role, a package constant, or an explicitly permitted
model-generated transform. It rejects every other source. Destination,
authorization, capability-selection, and external-identity fields may use only
sealed structured fields, cited original-prompt spans, or package constants;
they may never derive from `additional_context`, tool output, or remote/MCP
instructions. The authoring skill must label any permitted model-generated
transform, and wrapper dispatch validates this policy against the final
normalized tool invocation.

The model-facing representation of a final tool call is an
`ArgumentProvenanceEnvelope v1`, not an unannotated JSON object. Its canonical
UTF-8 JSON serialization carries a format version, normalized argument values,
and exactly one typed source proof per argument. V1 prompt spans use UTF-8 byte
offsets into the sealed original prompt and one normalization identifier from the
versioned wrapper registry (`identity` or `trim_ascii_whitespace`). The wrapper
recomputes the span and normalization before it accepts the value. A sealed
field, artifact, or package constant is represented by an opaque reference that
the wrapper resolves server-side.

V1 model-generated content uses a short wrapper-owned transform registry with
typed inputs and outputs; it is permitted only for non-authority content fields.
`compose_content_v1` is the initial transform: the wrapper supplies only its
declared sealed/artifact/constant inputs to a bounded model composition context
and records the transform identifier and input references. It is not a proof of
semantic derivation, so it can never supply destination, authorization,
capability-selection, or external-identity fields. Tool output and
`additional_context` are not transform inputs. `AuthorizedToolBinding` verifies
canonical serialization, source proofs, normalization, transform identifier, and
typed inputs; it removes source metadata and dispatches only normalized
remote-tool arguments. A raw value or unverifiable source proof fails before
handler entry.

`WorkflowPolicy` is the immutable, gate-independent compilation of portable
descriptor and tool-index policy: package/descriptor digests, task policy,
workspace policy, limits, and required capability declarations. It contains no
live host binding. `WorkflowRegistration` is the later executable authorization
record: it binds one `WorkflowPolicy` to a compatible profile, model selection,
and, when G2 applies, approved surface snapshots. The descriptor is the sole
source for logical task policy; the profile only supplies reusable host
capabilities. The catalog maps a local `workflow_id` alias only to an executable
registration. Preparation and handlers reference that digest rather than
independently reconfiguring policy; binding rejects a policy/profile mismatch.

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
- Authoring publication acceptance includes a de-identified, checked-in corpus
  covering basic, MCP, ambiguous, supplied-material, and adversarial tool-policy
  requests. Deterministic package, schema, task-policy, and provenance checks
  must all pass. An external harness records the authoring model, prompt, and
  package revision; until an automated judge is calibrated against human review,
  a human reviews every release-corpus package for intent fidelity and task scope.

### Target skill invocation patterns

Before wrapper implementation, the plugin shall build and test its three adapted
skills against checked-in target invocation fixtures. These fixtures are the
initial contract to meet and may be revised through a reviewed spec/task change
when implementation evidence finds a defect or ambiguity. They do not require a
live model in unit tests.

| Skill | Target invocation | Required result |
| --- | --- | --- |
| `agent-development` | “Design a bounded DAR workflow that answers questions about supplied text using this local model and these examples.” | Canonical DAR artifacts, `WorkflowDescriptor`, finite `task_invocation`, capability report, and no undeclared tools. |
| `agent-tool-contract-design` | “Add this approved connection requirement and reviewed MCP tool surface to the workflow; define its normalized schema, limits, approval class, and permitted argument sources.” | `tool-index.yaml`/descriptor changes with a host-managed connection requirement, reviewed semantic tool identifiers and schemas, side-effect metadata, and `ArgumentProvenanceEnvelope` policy. It refuses endpoint, OAuth, credential, or live-discovery design input. |
| `agent-evaluation` | “Create acceptance cases and a regression gate for this package, including tool failure and prompt-injection behavior.” | Evaluation plan, deterministic fixtures, rubric/judge policy, and a regression gate that does not execute live external services. |

The fixture corpus shall use a versioned schema and contain the request, selected
non-secret `AuthoringMaterialSet` projections, expected artifact properties,
expected refusal/capability result, and private-material exclusion rules.
Deterministic tests validate fixture property contracts and package loading. A
separate external release harness executes the adapted skills with the chosen
authoring model and compares their artifacts with those properties; it supplies
no unselected material. No test requires byte-identical prose or a live
Fastmail, Hugging Face, or model call.

## MCP Execution Tool

### Package preflight and invocation preparation are separate from execution

Before a package can run, `PackagePreflightService` validates/imports it from an
already-issued package-source handle and compiles its `WorkflowPolicy`.
`CapabilityResolution` then determines whether the currently passed gates can
bind that policy to a compatible profile as an executable
`WorkflowRegistration` with a local `workflow_id` alias. A package with an MCP,
embedding, or other unavailable requirement returns a non-executing capability
result; G1 never fabricates a live binding. Preflight is a trusted local
control-plane action, not a second model-facing MCP execution tool. An authoring
or preparation skill may request the service and interpret its result, but it
never receives a package path or ZIP, performs the import, or selects a profile.
The later applicable capability control plane may ask a human to complete
connection authentication or select an already configured compatible profile.
Neither path may invent credentials, enable undeclared capabilities, or silently
modify package artifacts.

The trusted control plane exposes this preflight contract to skills and the
local CLI, not as a second model-facing MCP tool:

```text
dar-workflow preflight --package-source <opaque-source-handle> \
  --json
```

When an authoring skill receives a natural-language package reference such as
`custom-email.zip` but has no source handle, it returns a non-executing
`source_selection_required` result containing only the requested display name.
The local plugin client then presents a human file/directory picker or the local
CLI command below; only a confirmed selection creates a handle. The picker and
path are never exposed to the skill.

```text
dar-workflow select-package --path <human-selected-path> --json
```

Its authenticated request binds the local principal and package-source handle.
A trusted local CLI/control plane creates a package-source handle only after a human
selects a directory or ZIP from an allowlisted root and it has performed the
bounded no-follow source check. The handle is principal/expiry-bound and cannot
be redirected to another path. Direct local `--package` and
`--workspace-file` conveniences resolve to these handles before preparation
after G4 passes; they are not available to an LLM skill or model-facing MCP
caller. Package preflight returns only `package_id`, `revision_digest`,
`workflow_policy_digest`, and a discriminated capability result. It cannot
accept invocation input, create a registration or alias, issue a prepared input,
or call the runner. The authoring/preparation LLM may request this operation and
interpret its result, but cannot perform its security-sensitive validation,
select an arbitrary host path, or manufacture its identifiers.

For example, a request to use `custom-email.zip` to send an email causes the
skill to request preflight with a previously issued package-source handle. The
service imports and compiles the package policy. If the required MCP
capability is not live, it returns `capability_unavailable`; it neither provisions
nor registers the package. Once the relevant gates are live, invocation
preparation derives the package's validated structured input and bounded
additional context without invoking a workflow tool, binds the policy, and calls
the generic runner with its registered `workflow_id`. After G4, it may also bind
explicitly ingressed local inputs. A later request can reuse that registered
workflow with a new invocation preparation.

After executable registration, authenticated non-model
`WorkflowInvocationPreparationService` is the sole issuer of a local-principal-,
registration-digest-, and expiry-bound `PreparedWorkflowInput`:

```text
dar-workflow prepare --workflow <registered-workflow-id> --prompt <text> --json
```

It contains the original prompt, only schema-valid structured fields, bounded
`additional_context`, opaque artifact identifiers and versions when G4 is live,
issuer/key ID, canonical schema version, and a canonical digest. It is sealed
with a service key unavailable to skills. The structured fields are an explicitly
labeled projection of the original prompt, not a more authoritative instruction
source; the package's `field_precedence` rule applies before prompt construction.
It may only project explicit user prompt/artifact data through declared mappings:
it must not invent or transform external-action values, call a workflow tool, or
read credentials. Prepared input is single-use by default; reusable read-only
input requires an immutable bounded profile policy.

### FR-4: Expose one narrow execution tool

The plugin shall expose exactly one model-facing MCP tool named
`run_dar_workflow`. It executes one selected saved workflow revision using the
runtime registration bound to that workflow. It is not a shell-command proxy for
the `dynamic-agent-runner` CLI.

The MCP server shall use DAR's library API because execution may require a
caller-provided tool registry, explicit MCP bindings, and a strict local model
adapter. The DAR CLI alone cannot supply those collaborators.

For a resolved registration, the server shall perform the required execution
setup before calling DAR: validate the registration and its bound profile,
construct the required model adapter, and, for each declared MCP connection,
validate its authenticated connection and approved surface snapshot, initialize
the configured MCP client, and passively compare live `tools/list` identity and
input schemas with that snapshot. It constructs `MCPToolBinding` handlers only
for declared snapshot tools. Workflows without MCP requirements perform none of
these connection steps. DAR receives only the validated workflow, registry, and
adapter. Runtime comparison cannot refresh, approve, or widen a snapshot.

The plugin owns a versioned `MCPConnectionClient` adapter boundary; DAR receives
only its resulting `MCPToolBinding` handlers. A profile declares one supported
transport and its lifecycle policy, including connect/initialize, per-call and
overall timeouts, cancellation behavior, reconnect policy, bounded output,
cleanup, and strict-versus-unavailable failure behavior. No transport, schema
discovery, or lifecycle behavior is advertised until a positive adapter fixture
proves it. This is wrapper functionality, not a claim that DAR's current MCP
runtime opens live transports.

V1's first live external transport is configured HTTPS MCP. It supports the
human control plane's OAuth authorization-code flow with PKCE or a locally stored
API token, and binds the resulting authenticated HTTPS peer to the approved
surface snapshot. This is a generic transport contract, not a Fastmail feature;
the references above demonstrate an HTTPS endpoint with OAuth and scoped
read/write/send consent. Stdio and any other transport remain unavailable until
their own adapter fixtures and lifecycle policy pass.

Connection identity is transport-specific: an HTTPS profile pins its validated
TLS/server identity, while any future stdio profile must pin a configured
executable identity and process policy. A handler is bound to one connection
generation, snapshot digest, and identity attestation. It rechecks that binding
immediately before every dispatch as the exact tuple `{connection_id,
client_generation, authenticated_peer_identity, snapshot_digest}` against the
live initialized client. Reconnect, credential rotation, or snapshot drift
invalidates the generation and returns `surface_changed` or
`capability_unavailable`; it never transparently replaces or widens a live
binding during an authorized side-effect dispatch. Cancellation is
capability-negotiated. A cancelled non-cancellable external mutation has an
indeterminate outcome and cannot be retried automatically.

The versioned request contract shall have this shape:

```json
{
  "format_version": 1,
  "workflow_id": "email-assistant",
  "prepared_input_id": "prepared_input_opaque_id"
}
```

`workflow_id` is a closed-set identifier from a host-managed workflow catalog.
`prepared_input_id` resolves only to an unexpired sealed input for that local
principal and exact registration digest; the runner verifies the service
issuer/key ID and canonical digest before use.
A side-effect-capable workflow atomically consumes its prepared input at run
creation, so it cannot be replayed or concurrently reused; a read-only profile
may declare a bounded reusable-input policy. The model-facing runner never
accepts raw prompts, structured fields, additional context, or artifact
identifiers. It is workflow input, not a request to alter a package or profile.
The tool must reject
arbitrary package paths, executable commands, model endpoints, MCP endpoint
values, skill sources, profile identifiers, and unsealed hybrid-input fields in
invocation arguments. It shall not accept
authentication, provisioning, surface-refresh, model endpoint, or
approval-token flags from the model-facing request.

The wrapper-owned workflow catalog maps each `workflow_id` only to an immutable
`WorkflowRegistration` digest. Trusted catalog storage pins and verifies the
registration, package artifact, profile, and required surface-snapshot digests
on every run, together with the configured publisher key. Handlers receive the
resolved registration as their authorization context and do not independently
resolve policy from the descriptor or profile.

Responses shall use discriminated, versioned schemas with a non-secret run or
correlation ID and bounded payloads. Required response kinds are `completed`,
`authentication_required`, `surface_changed`, `approval_required`,
`capability_unavailable`, and `failed`.

`completed` contains only output validated against the package terminal-output
schema and bounded by its response policy. Schema failure or excess output is a
non-executing/failed result with a redacted diagnostic. In v1,
`approval_required` means a required local broker is unavailable at preflight;
it never includes an executable continuation, approval token, or resumable DAR
state. Denial, cancellation, and broker timeout are terminal `failed` results
with stable codes `approval_denied`, `approval_cancelled`, and
`approval_timeout`.

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
missing or its material input schema has changed. The normalized output contract
is wrapper-owned and is separately validated and bounded after invocation; it is
not inferred from remote `tools/list` data. The wrapper must not choose a
replacement tool automatically. A profile's surface can be refreshed only by an
explicit human-authorized provisioning request.

When OAuth is used, authorization-code flow shall use PKCE, an allowlisted
redirect URI, and validated state and nonce values. Tokens, authorization
headers, and raw MCP instructions must never appear in package artifacts, tool
requests/results, or traces. The control plane binds connections immutably to a
profile and approved scope. Scope escalation, connection replacement, and
revocation invalidate affected snapshots and pending approvals.

An HTTPS MCP connection definition may select the generic
`oauth_authorization_code_pkce_loopback` authorization handler. Its human-only
control-plane operation launches the provider authorization URL, after first
binding a fresh loopback listener on an ephemeral port. It uses a registered
`http://localhost/<provider-specific-path>` redirect template, a high-entropy
PKCE verifier/challenge and state value, accepts exactly one callback, verifies
the state and exact callback URI, exchanges the one-time code, and stores the
result only in the connection credential store. It returns a bounded connection
status, never a code, token, or callback query to a skill or model-facing tool.
The handler is available only when the provider registration explicitly permits
loopback redirects; otherwise the connection definition must choose a different
human-approved redirect handler. This is part of the generic MCP connection
definition, not Fastmail-specific workflow behavior.

Snapshot comparison shall use canonical identity and input-schema digests plus a
pinned HTTPS server identity. The wrapper supplies host-authored semantic
descriptions to DAR rather than forwarding remote tool descriptions. It defines
normalized output contracts itself, then validates and bounds handler outputs
against those contracts, rejecting unexpected sensitive fields and untrusted
instructions.

Before G5 passes, capability resolution and binding shall reject every MCP tool
whose declared side-effect class is not `read_only`, even when its connection,
scope, and surface snapshot are approved. G2 may create its reviewed metadata,
but it must not construct a dispatchable send/write/delete handler.

Acceptance criteria:

- The wrapper creates DAR bindings only after all required remote capabilities
  and schemas match the approved snapshot.
- The human control plane explicitly reviews and records the first capability
  snapshot without persisting a credential in the package artifacts.
- A later remote tool-name or input-schema change fails closed until explicitly
  refreshed by the human control plane.
- A workflow requiring an MCP tool is unavailable until its required connection
  and snapshot pass preflight. A Fastmail email workflow is one example.
- A send-like fake tool remains unavailable and its handler is not invoked under
  G2 + G3 before G5 passes.

### FR-6: Enforce write approval in the wrapper and DAR boundary

The wrapper shall default to `workflow_auto` for every run of a pre-built,
approved workflow revision. The CLI exposes this policy as its default `auto`
mode. It is valid only while the resolved registration, package revision, bound
profile, MCP-surface snapshots, model settings, and workspace policy match their
approved values. Under `workflow_auto`, the workflow model
may select any schema-valid exposed tool call, including a side-effecting call;
the wrapper enforces the approved tool set, schema, connection snapshot,
side-effect metadata, resource budgets, and call cardinality limits. It does
not require predeclared argument values, but it requires every final argument
to satisfy the package `argument_sources` policy. Any profile or surface drift
fails closed rather than silently widening that boundary.

The local wrapper CLI shall support these execution modes:

```text
dar-workflow-run --workflow <id> --prompt <text> \
  [--workspace-file <path>]... [--dry-run] [--ask]
```

`dar-workflow-run` is a convenience façade, not a second execution path. For a
real run it resolves permitted local paths into handles (and uses G4 ingress for
`--workspace-file`), calls `WorkflowInvocationPreparationService`, then invokes
only `run_dar_workflow` with the returned `workflow_id` and
`prepared_input_id`. It
must never pass its raw prompt or file path directly to DAR. Before G4, it
rejects `--workspace-file` rather than attempting a local copy.

- Default mode is `auto` (`workflow_auto`): execute schema-valid tool calls
  chosen by the workflow model within its declared, profile-allowed surface and
  record every external action in the audit trace.
- `--dry-run`: resolve the registration, validate package artifacts,
  `CapabilityResolution`, schemas, workspace-input policy, and cached surface
  snapshots, then emit the resolved configuration. It must not
  predict model-selected tool calls, initiate OAuth, refresh MCP discovery,
  invoke a model, invoke a tool handler, or ingress/copy caller files. It may
  validate a supplied source path read-only; a real run repeats trusted ingress
  and cannot reuse a dry-run observation or digest as an artifact authorization.
- `--ask`: send each side-effecting call to an interactive wrapper approval
  broker before its handler runs. The broker displays the normalized action and
  returns an allow/deny decision; it is not a model-provided approval token.

The model-facing `run_dar_workflow` tool uses the selected server policy and may
not request `auto`, `--ask`, or `--dry-run` through invocation arguments.

`--ask` is a local CLI/control-plane-only synchronous mode: the wrapper holds
the current handler boundary while the broker decides, then dispatches exactly
once or denies it. Broker cancellation, expiry, or timeout terminates the run
with a non-executing `failed`/`approval_timeout` result and records the terminal
audit state. It never returns a resumable DAR approval to the model-facing MCP
caller. A server profile that requires interactive approval but lacks a local
broker fails preflight with `approval_required`; it creates no continuation
token, pending executable action, or later replay path.

For `--ask`, the server-side approval record shall use a cryptographically
random, short-lived one-use token and an atomic compare-and-consume transition.
Its canonical action digest shall cover:

- workflow identifier and resolved package revision;
- run identifier and normalized final tool invocation;
- local principal, profile, connection, and snapshot identity;
- applicable bounded execution parameters; and
- opaque input-artifact identifiers and protected content hashes.

The server shall reject changed, expired, replayed, cross-principal, or mismatched
approvals. It never accepts a client-provided digest as authoritative. The same
canonical action is included in `workflow_auto` audit records, without creating
a pending approval record.

Every external action uses a durable wrapper action ledger. Before dispatch the
wrapper writes an `intent` record containing the canonical action digest,
connection generation, and trace correlation. It then records `dispatched` and
one terminal status: `completed`, `denied`, `cancelled`, `failed`, or
`outcome_unknown`. The audit store must acknowledge intent before dispatch; an
audit failure fails closed before a side effect. A timeout, disconnect,
cancellation, or transport failure after dispatch is `outcome_unknown`, not
success. Mutations are at-most-once by default and receive no automatic retry.
Retry is permitted only when the approved remote contract supports an
idempotency key derived from and bound to the action digest; an unknown outcome
is never automatically replayed. Audit records and result shaping expose no raw
body, credentials, or sensitive tool payload.

DAR does not currently expose a public continuation API that resumes an
interrupted execution at the pending tool call. The wrapper therefore creates an
`AuthorizedToolBinding` from the immutable `WorkflowRegistration`, marked
`approval_required: no` only for DAR compatibility, and owns both `workflow_auto`
and `--ask` enforcement in the handler boundary. Registration compilation must
prove the binding metadata equals the package tool contract. The generated
package still declares side-effect and approval metadata for design, validation,
and audit.
Arbitrary model-tool calls and normal registry construction cannot use the
internal bindings; every handler verifies its immutable registration context,
schema, and remaining call cardinality before external invocation. Native DAR
interruption plus durable resumption is follow-on DAR work, not an implicit
wrapper replay.

Acceptance criteria:

- Default `workflow_auto` execution invokes only declared, profile-allowed
  bindings, validates `argument_sources`, and emits a durable action-ledger
  record for every external action.
- A workflow running under `workflow_auto` can issue an email or other
  side-effecting request when its prompt and exposed tool schema lead the model
  to do so; it cannot call a tool absent from its approved profile surface.
- `--dry-run` invokes neither model nor external tool handler.
- `--ask` cannot reach a side-effecting handler without a matching, atomically
  consumed server-side approval record.
- Changing a subject, recipient group, package revision, or referenced body file
  after an `--ask` preview invalidates the approval.
- A valid `--ask` approval cannot be consumed twice or by another local principal.
- An audit-store failure prevents dispatch; an uncertain post-dispatch outcome is
  recorded as `outcome_unknown` and cannot be automatically replayed.
- A reconnect, identity change, or snapshot drift between planning and dispatch
  fails before handler invocation.

### FR-7: Profile-backed execution owns external collaborators

A host-managed profile is reusable collaborator configuration: it selects its
local model adapter, MCP bindings, tool handlers, and allowed workspace roots.
`WorkflowRegistration` binds that profile to one package revision and its
execution limits.
Profiles may also reference a local OpenAI-compatible, llama.cpp, or MLX
adapter, but the plugin shall not start or discover any of those model services.

Before it issues any package-source, catalog, registration, or prepared-input
handle, the wrapper shall provide one private per-user state store and an
authenticated opaque-record format. Each record has a kind, local-OS-user owner,
payload digest, issuance and expiry, active/revoked/consumed state,
persistence/restart behavior, cleanup, and revocation semantics. A handle is
rejected when its kind, owner, digest, state, or expiry does not match the
operation. V1 does not claim isolation between processes that act as the same OS
user; a storage interface is deferred until a second backend is required.

`InstallationIdentityProvider` establishes the installation's authenticated local
principal before catalog resolution and supplies it to the control plane and
runner; no CLI or MCP request can provide or override it. V1's trust boundary is
the same local OS user: protected plugin state is per-user, and any process able
to act as that OS user is inside that boundary. The plugin rejects remote serving
until an explicit remote identity extension is specified. Profiles, connections,
snapshots, package revisions, approval records, group aliases, workspace roots,
and trace records are local-principal scoped. Multi-tenant roles and isolation
are a later deployment slice.

Trusted local CLI file inputs are accepted only from a local-principal allowlisted
input root and must pass G4 file ingress before they become workspace input
artifacts.
`WorkspaceIngressService` is the sole caller of the sandbox's no-follow copy
primitive. The profile supplies input-root limits, the descriptor supplies
accepted roles and types, and preparation receives only the resulting opaque
artifact record; it never reads a physical path or copies a file itself.
The wrapper shall reject traversal, symlinks, non-regular files, devices,
oversized files, and unsupported encoding. It shall use the hash-bound private
copy produced by ingress for the eventual send, preventing path substitution
after approval. `PreparedWorkflowInput` alone carries the opaque input-artifact
identifiers; the model-facing invocation accepts neither a physical path,
workspace URI, nor a raw artifact identifier. Untrusted HTML must be
escaped or sandboxed in approval UI.

Acceptance criteria:

- A trusted CLI `body_html_path` outside an allowlisted input root is rejected.
- A local-only profile uses strict adapter coverage and cannot silently fall back
  to the default hosted OpenAI adapter.
- Missing profile bindings fail before workflow execution.
- A caller cannot read, select, approve, or execute another local principal's
  profile, connection, package, group alias, or trace.
- A caller cannot supply, forge, or replace the OS-derived installation principal
  across CLI, MCP, preparation, or runner requests.

### FR-8: Capability resolution contract

Before binding, the wrapper shall create one versioned `CapabilityResolution`
from the `WorkflowPolicy`, declared profile capability records, active gates,
DAR's capability inspector, and wrapper-owned checks. It returns deterministic
eligibility or non-executing unavailability, reason codes, and source provenance
for every requirement. Only an eligible resolution can bind the policy to a
`WorkflowRegistration`; before every execution, the wrapper rechecks that same
resolution against the registration's selected profile and required surface
snapshots. All entry surfaces consume this result; they do not separately
reinterpret descriptor metadata. Execution fails closed when a required
capability is absent or only represented as DAR metadata.

The supported v1 capability contract contains only independently enabled live
capabilities; it does not imply that every profile exposes every integration:

| Host capability | Wrapper responsibility |
| --- | --- |
| Package catalog | Compile and retain immutable `WorkflowPolicy` records; resolve an executable `WorkflowRegistration` only after capability preflight. |
| Model manager | Select matching local adapters, enforce strict coverage, preflight local assets, and apply bounded generation settings. Hosted adapters are a later profile slice. |
| Tool manager | Assemble declared host bindings; configured MCP bindings require G2. |
| Secrets and files | Store credentials outside package artifacts. File references require G4 ingress and enforce workspace-root, size, type, and content-hash policies. |
| State and audit | Persist wrapper audit records and own concurrency. Do not claim graph-state checkpoint restore or interrupted-run continuation until DAR supports it. |
| Observability | Deep-redact or allowlist persisted trace fields; correlate run, registration, adapter, and tool provenance, and apply retention and audit policy. DAR's top-level event redaction alone is insufficient. |

Future capability taxonomy, not a v1 wrapper commitment: guardrails, context
management, retrieval/embeddings, durable sessions, hosted adapters, and
subagents. A descriptor requiring one of these returns a capability failure
until its later slice supplies a positive fixture.

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
- Trace records identify the registration, package revision, selected profile,
  active model adapter, and registered tool provenance without exposing secrets
  or raw sensitive payloads.
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

Delivery shall be staged:

1. v1 base delivers package and workflow catalogs, local-model no-tool execution,
   capability preflight, and redacted tracing. Configured read-only MCP profiles
   are an additive G2 extension, and file inputs are an additive G4 extension.
2. v1.1 adds model-directed external side effects with default `workflow_auto`
   execution (the CLI's `auto` mode) and optional `--ask` brokerage through the
   FR-6 wrapper-only binding exception.
3. Later profile slices add positive fixtures for retrieval/embeddings, durable
   conversational sessions, hosted model adapters, guardrails/context management,
   and subagents. The
   first release has no subagent binding or delegation surface. A capability may
   not be advertised as live until its positive fixture passes.

The packaging spike is the first implementation deliverable. It shall select the
Codex manifest/config format, prove isolated installation and discovery, start
and stop the local stdio server, and prove that no undocumented plugin-path
interpolation is required.

## Example workflow descriptors and invocation

| Requested outcome | Availability |
| --- | --- |
| Design and run a local no-tool workflow | v1 base (G0, G1, G3) |
| Run a configured read-only email workflow | G2 + G3 |
| Send email from prompt-only content | G2 + G5 |
| Send email using a local body file | G2 + G4 + G5 |
| Return a document embedding | Deferred until an embedding profile and host adapter ship |

### Email workflow with an optional MCP connection

The authoring skill can produce a descriptor like this. `email_connection` is a
host-managed, approved MCP connection reference; the descriptor does not embed
Fastmail-specific behavior, an endpoint, or credentials.

```yaml
format_version: 1
package_id: email-assistant
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
  field_precedence: original_prompt
task_invocation:
  entrypoint: send_or_search_email
  allowed_tool_ids: [search_mail, generate_image, send_email]
  max_total_tool_calls: 4
  allowed_structured_input_fields: [recipient, subject, image_brief]
  allowed_artifact_roles: [email_body]
  argument_sources:
    search_mail:
      query: [cited_original_prompt_span]
    generate_image:
      prompt: [sealed_structured_field:image_brief, model_generated_transform]
    send_email:
      recipient: [sealed_structured_field:recipient]
      subject: [sealed_structured_field:subject]
      body: [artifact_role:email_body]
  terminal_output_schema_ref: email-assistant-result-v1
limits:
  max_steps: 12
  max_external_tool_calls: 4
```

After the package has been designed and registered,
`WorkflowInvocationPreparationService`
retains the prompt and derives only the schema fields it can validate; the
workflow design directs its allowed tool calls. The optional `generate_image`
declaration is needed only if the author wants image generation; an email MCP
connection alone cannot produce an image.

```json
{
  "format_version": 1,
  "workflow_id": "email-assistant",
  "prepared_input_id": "prepared_input_opaque_id"
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

The preparation service supports the portable-package form of the same
experience when the authoring skill requests it with a pre-issued source handle:

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
original prompt—not the physical path. It seals these as one
`PreparedWorkflowInput`; only its opaque identifier reaches `run_dar_workflow`.

### Embedding workflow

This is a deferred profile example, not a v1 availability claim.

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
  "prepared_input_id": "prepared_input_opaque_id"
}
```

## Validation Plan

Implementation shall follow TDD. Before implementation, add focused tests that
initially fail for the required behavior.

1. **G0:** Validate plugin manifest and skill discovery.
2. **G1:** Load generated basic, MCP-backed email, and embedding fixture packages
   with DAR; compile descriptors into `WorkflowPolicy` records, return
   non-executing unavailability for unavailable collaborators, and reject every
   mismatched projected policy field. G2/G3 bind eligible policies to profiles.
3. **G3:** Execute a no-tools workflow with a fake local model adapter and prove
   `--dry-run` invokes neither model nor tool handler.
4. **G2 + G3:** Execute a fake read-only MCP workflow and prove provisioning
   rejects an unauthenticated connection, a missing required tool, and a changed
   MCP surface snapshot.
5. **G4:** Prove path containment and file-digest checks reject invalid or changed
   body files.
6. **G5:** Prove default `workflow_auto` rejects undeclared, profile-disallowed,
   and drifted tool bindings while recording each external action; prove `--ask`
   rejects changed, expired, cross-principal, and replayed approvals.
7. **G5:** Prove a v1.1 side-effecting handler enforces its registration policy
   without replaying an interrupted DAR execution.
8. **G1/G3:** Verify a strict local profile never creates or uses a hosted fallback
   adapter, and trace output is redacted and correlates registration, adapter,
   and tool provenance.
9. **Deferred slices:** Validate an embedding workflow only when its host adapter
   is live. Until then, prove capability resolution rejects packages requiring a
   missing guardrail, retrieval backend, session store, context component, or
   subagent collaborator.

## Completion Criteria

The v1 base release is complete when G0, G1, and G3 pass: the plugin manifest
and skills are discoverable, generated no-tool fixture packages load under DAR,
and focused tests prove local-principal selection, local-only model isolation,
capability preflight, and redacted observability. G2 read-only MCP and G4 file
input extensions are independently complete only when their required gate and
positive fixtures pass. V1 must not expose side effects, retrieval/embeddings,
durable sessions, broader guardrails/context, or subagents.

The v1.1 side-effect extension is complete when G5 passes, plus G2 for an
MCP-backed action and G4 for a file-backed argument. Focused tests prove the
applicable ingress, `workflow_auto` audit binding, `--ask` replay resistance,
and no claim of DAR graph continuation.
