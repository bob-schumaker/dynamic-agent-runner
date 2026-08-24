# DAR Authoring Plugin Implementation Tasks

## Status

This task breakdown implements the release gates in `spec.md`. Complete each
task test-first. G3 depends on G0/G1; G2 and G4 are additive G0/G1 extensions;
G5 depends on G0/G1/G3 plus G2 for MCP actions or G4 for file-backed arguments.
A capability cannot be implemented or advertised as live before its applicable
gate passes.

## G0: Package and Server Spike

- [ ] RED: plugin-manifest discovery, approved-Artifactory immutable artifact
      resolution, hash-pinned dependency-lock verification, and isolated-`uvx`
      installation tests.
- [ ] GREEN: create the `dar-authoring` plugin bundle and local stdio MCP server
      entrypoint without undocumented path interpolation; include the DAR
      support runtime and all required package assets in the released wheel.
- [ ] RED/GREEN: start/stop lifecycle test that proves the server exposes no
      execution tool before G1–G3 are configured.
- [ ] RED/GREEN: clean-directory released-wheel test verifies its archive asset
      hashes and receives a valid MCP `initialize` response without source-tree
      paths or undeclared package indexes.
- [ ] RED/GREEN: launcher verifies the selected plugin/DAR wheel bytes against
      signed release metadata, rejects unexpected indexes or a replaced artifact,
      and records the resolved dependency identities at startup.

## G1: Catalog, Profile, and Capability Boundary

- [ ] RED/GREEN: authoring tests accept a `WorkflowDescriptor` with no MCP
      tools and no skills, and emit the canonical DAR package artifacts plus a
      descriptor digest; separately prove optional declared capabilities become
      package requirements.
- [ ] RED/GREEN: map generated nonempty skill declarations to DAR's
      `skill-bundle/`, `bundled_path`, `skill_refs`, and enabled
      `skill_source_resolution` metadata; prove external skill paths fail.
- [ ] RED/GREEN: package fixtures declare a bounded task-specific tool
      invocation pattern and hybrid input contract; reject a package whose
      graph exposes an undeclared general-purpose tool console.
- [ ] RED/GREEN: validate `task_invocation` tool sets, finite total-call limits,
      permitted structured fields and artifact roles, and terminal
      output schema before DAR executes a node.
- [ ] RED/GREEN: validate each final tool argument against its declared source
      policy. Destination, authorization, capability-selection, and external
      identity fields reject `additional_context`, tool-result, and remote
      instruction flow; adversarial prompt-injection fixtures prove rejection.
- [ ] RED/GREEN: authoring skill fixtures turn natural-language requests plus
      supplied examples/files/documentation into a validated package directory;
      deterministic ZIP export/import preserves the manifest and artifact
      digests without executing package content.
- [ ] RED/GREEN: ZIP import rejects traversal, duplicate, link, special, and
      over-limit entries; verify manifest file paths, bytes, hashes, schema, and
      DAR compatibility before immutable registration. Require recorded local
      trust for locally authored packages and a configured trusted-publisher-key
      signature for received packages.
- [ ] RED/GREEN: directory import makes the same private no-follow staging copy
      before validation; registration identity is `package_id` plus immutable
      `revision_digest`, with installation-local workflow aliases, idempotent
      reimport,
      explicit collision handling, and retained prior revisions.
- [ ] RED/GREEN: canonical-manifest-v1 Ed25519 export/import fixtures prove
      signer/key-id binding, rejection of an unknown locally trusted publisher
      key, and a recipient-host signed-package import. Explicitly selected
      distributable authoring material is included; private source material is
      absent.
- [ ] RED/GREEN: `WorkflowPreparationService` imports a
      directory or ZIP only through a pre-issued source handle, resolves a
      compatible host profile, compiles an immutable `WorkflowRegistration`, and
      registers its workflow alias before the single runner tool is exposed.
- [ ] RED/GREEN: `WorkflowRegistration` compilation is the sole policy derivation
      path: descriptor/task policy plus profile/snapshot capabilities produce one
      registration digest, while any mismatched duplicated field is rejected.
- [ ] RED/GREEN: `dar-workflow prepare --json` authenticates the caller and
      returns only registered workflow/package/revision/registration identifiers
      plus a sealed prepared-input identifier and expiry; LLM skills cannot mint
      them.
- [ ] RED/GREEN: preparation accepts only local-principal/expiry-bound opaque
      package-source handles. A human-selected local CLI path resolves to a
      handle before preparation; LLM skills and MCP callers cannot select an
      arbitrary host path or redirect an existing handle.
- [ ] RED: versioned `run_dar_workflow` request/response schema tests for
      closed-set workflow identifiers plus an opaque sealed prepared-input ID;
      raw hybrid-input fields are rejected.
- [ ] RED/GREEN: preparation derives only schema-valid structured fields without
      workflow-tool access, preserves unmapped information within the declared
      `additional_context` bound, and rejects over-limit or malformed inputs.
- [ ] RED/GREEN: preparation seals the original prompt, structured projection,
      additional context, local principal, registration digest, and expiry into
      `PreparedWorkflowInput`; reject raw or cross-principal, cross-registration,
      changed, or expired input at the runner.
- [ ] RED/GREEN: validate preparation-service issuer/key, canonical schema, and
      registration binding. Reusable read-only inputs require an explicit bounded
      profile policy.
- [ ] GREEN: immutable package/workflow catalog maps each alias only to its
      registration digest; reject arbitrary package paths, endpoints, commands,
      profile selections, and model-provided provisioning/approval fields.
- [ ] RED/GREEN: `InstallationIdentityProvider` supplies a stable local principal
      to CLI, MCP server, preparation, and runner. Cross-client and restart tests
      prove requests cannot provide or override it.
- [ ] RED/GREEN: produce one deterministic `CapabilityResolution` from the
      registration, profile, active gates, and DAR inspection; reject
      metadata-only or missing wrapper requirements before execution.

## G2: Optional MCP Connection Control Plane and Surface Binding

- [ ] RED: a workflow that requires an unauthenticated least-scope connection returns
      `authentication_required`.
- [ ] GREEN: human-only OAuth/API-token connection flow with secret storage
      outside package artifacts and immutable profile/scope binding.
- [ ] RED/GREEN: approved MCP surface snapshot creation/review plus passive
      `tools/list` identity/input-schema drift detection on the run path.
- [ ] RED/GREEN: plugin-owned `MCPConnectionClient` fixtures cover configured
      transport initialization, strict/unavailable startup, timeout,
      cancellation, reconnect, bounded output, and cleanup; no untested
      transport is advertised.
- [ ] RED/GREEN: bind every handler to one transport-specific identity,
      connection generation, and surface snapshot; reconnect, rotation, or
      drift before dispatch fails closed rather than widening a live binding.
- [ ] RED/GREEN: disconnect/reconnect or peer failover between preflight and
      handler dispatch returns `surface_changed` or `capability_unavailable` and
      never invokes a replacement client under the prior authorization.
- [ ] RED/GREEN: construct host-authored, caller-supplied `MCPToolBinding`
      handlers only from an approved snapshot; fake MCP tests only.
- [ ] RED/GREEN: a read-only MCP registration is unavailable until both G2 and
      G3 pass; then execute it through the shared capability resolution path.

## G3: Read-Only Workflow Runner

- [ ] RED/GREEN: select a strict local model adapter and reject hosted fallback.
- [ ] RED/GREEN: execute a no-tools workflow through its registration, capability
      resolution, bounded result shaping, and deep-redacted tracing.
- [ ] RED/GREEN: `dar-workflow-run` resolves handles, invokes preparation, then
      sends exactly the resulting sealed request to `run_dar_workflow`; prove no
      CLI path passes a raw prompt or file path to DAR.
- [ ] RED/GREEN: validate terminal workflow output against the registered output
      schema and return bounded redacted failure for malformed or excess output.
- [ ] RED/GREEN: `--dry-run` validates catalog/profile/snapshot/path policy but
      invokes neither a model nor an MCP handler, and does not ingress/copy a
      caller file or authorize later ingress from its observation.

## G4: Trusted File Ingress

- [ ] RED: source files outside the configured caller input root, symlinks,
      devices, non-regular files, oversized content, invalid encoding, and
      parent-swap races are rejected.
- [ ] GREEN: use the sandbox specification's descriptor-relative no-follow
      primitive to copy the exact opened source into a fresh private workspace;
      return only an opaque input-artifact identifier, protected hash, and byte
      count.
- [ ] RED/GREEN: `WorkspaceIngressService` is the sole sandbox-copy caller;
      profile roots and descriptor roles/types determine its acceptance, and
      preparation receives only its opaque artifact record.
- [ ] RED/GREEN: prove physical paths and raw body content are absent from model
      inputs, tool results, traces, audit records, and approval displays.
- [ ] RED/GREEN: extend preparation only after ingress with opaque artifact IDs
      and versions; it never reads a physical path or performs its own copy.

## G5: Model-Directed External-Tool Workflow Runner

- [ ] RED: undeclared, schema-invalid, drifted, or over-cardinality writes fail
      before their external handler runs; a schema-valid model-directed call on
      the approved surface is permitted.
- [ ] GREEN: use wrapper-private bindings whose handlers verify the immutable
      registration context, schema, snapshot, and G4 hash-bound file ingress
      where applicable.
- [ ] RED/GREEN: registration compilation proves each `AuthorizedToolBinding`
      metadata matches the package tool contract before DAR receives it.
- [ ] RED/GREEN: default `workflow_auto` (the CLI's `auto` mode) records the
      canonical external action; `--ask` uses a short-lived, one-use,
      local-principal-bound atomic approval decision.
- [ ] RED/GREEN: changing the package revision, recipient alias, subject, body
      hash, profile, or snapshot invalidates an outstanding `--ask` decision.
- [ ] RED/GREEN: local `--ask` blocks only at the wrapper handler boundary;
      approve invokes exactly once, while deny, cancel, and expiry produce a
      terminal non-executing result with no DAR continuation token or replay.
- [ ] RED/GREEN: action ledger writes durable `intent` before dispatch and
      records `dispatched` plus a terminal status. Audit-store failure blocks
      dispatch; post-dispatch timeout/cancellation/reconnect is
      `outcome_unknown` and is never retried automatically. Retry a mutation
      only through a remote idempotency contract bound to the action digest.
- [ ] RED/GREEN: atomically consume a side-effect-capable prepared input at run
      creation. Concurrent/replayed consumption fails; prompt-only actions pass
      without G4, while file-backed actions require G4.

## Deferred After the First Release

- [ ] Retrieval/embedding profiles and host vector/index services.
- [ ] Durable conversational sessions and durable DAR interruption continuation.
- [ ] Guardrail phases beyond DAR's live input and tool-input handlers, and
      broader context-management profiles.
- [ ] Subagent and `ask_llm` integration.

## Focused Validation

- [ ] All unit tests use fake model adapters, MCP handlers, approval stores,
      and filesystem primitives; no live Fastmail, Hugging Face, or model call.
- [ ] A positive fixture is required before a gate's capability is reported live.
- [ ] G5 may run after G0, G1, and G3; it additionally requires G2 for MCP
      actions and G4 for file-backed arguments. It must not replay a DAR approval
      interruption or claim graph-preserving continuation.
