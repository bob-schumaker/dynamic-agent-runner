# DAR Authoring Plugin Implementation Tasks

## Status

This task breakdown implements the release gates in `spec.md`; `plan.md` groups
the known work into milestones and commit-sized slices. Complete each task
test-first. G3 depends on G0/G1; G2 and G4 are additive G0/G1 extensions; G5
depends on G0/G1/G3 plus G2 for MCP actions or G4 for file-backed arguments. A
capability cannot be implemented or advertised as live before its applicable gate
passes.

## Direction Change: Skills-Only CLI Control Plane

The former plugin-provided stdio MCP server, `run_dar_workflow` model-facing
tool, and broker path are superseded. Generated workflows may still declare and
use a human-configured MCP capability through DAR's host runtime; that does not
make the Codex plugin an MCP server.

- [ ] RED/GREEN: define and test role-scoped `dar-package` CLI schemas:
      `agent-development` uses material issue/project and authored-package
      create/write/finalize; a later invocation skill uses only `invoke`; the
      companion skills produce package artifacts only. Human-only selection and
      DAR-internal registration/preparation are not skill commands. Every
      non-projection response is one versioned, redacted JSON receipt or error
      and uses opaque IDs for host resources.
- [ ] RED/GREEN: define `project-authoring-materials` as the sole transient
      content-returning exception: it returns only the selected bounded
      projection to stdout, is never trace-recorded, and has explicit member and
      byte limits. Add a human-only material-ingress schema that rejects raw
      paths from a skill and proves unselected/reference-only content is absent.
- [ ] RED/GREEN: update each adapted skill and target-invocation fixture to use
      the exact checked-in `uv run ... dar-package <command>` template. The entry
      skill collaborates with the user to close missing workflow semantics,
      finalizes a task-specific package, and hands its saved package name/receipt
      to a later invocation request.
- [ ] RED/GREEN: remove the plugin `.mcp.json`, plugin-manifest `mcpServers`
      entry, `scripts/dar-mcp`, MCP session-broker implementation, and their
      tests only after CLI acceptance coverage replaces them. This does not remove
      the local `--ask` approval broker. Verify a clean plugin install exposes
      skills and no plugin-provided MCP server.
- [ ] RED/GREEN: replace the M4.4 run actor with a clean Codex skill invocation
      that issues the defined `uv run ... dar-package` commands. It must prove
      finalization and later saved-package invocation from text-only prompts;
      the harness controller may provide only declared fixture inputs and fake
      host collaborators.

## G0: Package and CLI Spike

- [x] RED: add checked-in target invocation fixtures for all three adapted skills
      before copying or rewriting them. Each fixture defines a user request,
      fixture schema version, selected non-secret inputs, expected artifact
      properties, expected capability/refusal state, and private-material
      exclusion rules.
- [x] GREEN: copy `agent-development`, `agent-tool-contract-design`, and
      `agent-evaluation` from `ai-environment-roschuma` at recorded immutable
      source revisions; remove upstream-environment dependencies and rewrite
      their instructions so DAR package, wrapper, and evaluation contracts are
      authoritative. Add `adapted-skill-provenance.yaml` with source locator,
      revision, license/notice, redistribution review, copied path, and DAR
      modification summary for every copied skill.
- [x] RED/GREEN: plugin skill-discovery and target-invocation fixture tests prove
      each adapted skill, provenance entry, source revision, copied-path coverage,
      redistribution review, and fixture schema is present; lint declared artifact
      interfaces and unsafe-input expectations. These static tests do not claim
      model routing or refusal behavior and do not invoke a model.
- [x] RED/GREEN: canonical basic-reasoning and bounded read-only-MCP templates
      load through DAR; the declared tool is task-specific, read-only, and capped
      at three calls. Both templates ship as plugin assets.
- [x] RED/GREEN: plugin starter assets cover the tool-index and evaluation
      artifact contracts promised by the three adapted skills; their empty v1
      structures are deterministic and make no live-provider claim.
- [ ] RED: plugin skill-discovery, exact approved-Artifactory DAR-version
      resolution, and isolated `uv run` CLI invocation tests.
- [x] RED/GREEN: add the `dar-package` console entry point before any plugin
      smoke test. `dar-package version --json` returns exactly one receipt with
      `format_version`, `status`, `distribution`, and `version`; error output is
      one redacted JSON object with `format_version`, `status`, and `error_code`
      on stderr with nonzero exit. Cover unknown subcommand, missing/invalid
      `--json`, and internal failure; focused tests prove no source path, state
      root, credential, or host configuration appears.
- [x] GREEN: create the `dar-authoring` skills-only plugin bundle and checked-in
      CLI command template without undocumented path interpolation; DAR provides
      `dar-package` and includes all required runtime assets in its released
      wheel.
- [x] RED/GREEN: developer local-wheel verifier executes
      `dar-package version --json` from a freshly built DAR wheel through
      `uv run --no-project --python 3.14` in an isolated temporary directory.
      Prove it neither opens state
      nor emits source/state paths. This proves entrypoint/assets only, not
      Artifactory resolution or publication integrity.
- [x] RED/GREEN: built-wheel asset check proves `dist-info/entry_points.txt`
      maps `dar-package` and that this asset appears in `RECORD`. This is only
      packaging-presence evidence; release-integrity auditing remains deferred.
- [x] RED/GREEN: clean Codex plugin smoke test proves the temporary marketplace
      plugin installs its skills, does not register an MCP server, and lets a
      skill issue the checked-in CLI discovery command without a configured host.
- [ ] RED/GREEN: independently resolve the pinned DAR version from the approved
      Artifactory index and record resolved wheel name, version, and digest.
      Do not use a local-wheel result as index-resolution evidence.

## G1: Catalog, Profile, and Capability Boundary

- [x] RED/GREEN: accept a task-specific declared read-only MCP tool set with
      unique IDs, exact `allowed_tool_ids`, and finite total-call limit; reject
      undeclared runtime tools and every non-read side effect before G5.
- [x] RED/GREEN: authoring tests accept a `WorkflowDescriptor` with no MCP
      tools and no skills, and emit the canonical DAR package artifacts plus a
      descriptor digest; separately prove optional declared capabilities become
      package requirements.
- [x] RED/GREEN: map generated nonempty skill declarations to DAR's
      `skill-bundle/`, `bundled_path`, `skill_refs`, and enabled
      `skill_source_resolution` metadata; prove external skill paths fail.
- [x] RED/GREEN: package fixtures declare a bounded task-specific tool
      invocation pattern and hybrid input contract; reject a package whose
      graph exposes an undeclared general-purpose tool console.
- [x] RED/GREEN: validate `task_invocation` tool sets, finite total-call limits,
      permitted structured fields and artifact roles, and terminal
      output schema before DAR executes a node.
- [x] RED/GREEN: validate each final tool argument against its declared source
      policy. Destination, authorization, capability-selection, and external
      identity fields reject `additional_context`, tool-result, and remote
      instruction flow; adversarial prompt-injection fixtures prove rejection.
- [x] RED/GREEN: directory import makes the same private no-follow staging copy
      before validation; package identity is `package_id` plus immutable
      `revision_digest`, with idempotent reimport, explicit collision handling,
      and retained prior revisions. G3 creates installation-local workflow aliases
      only for executable registrations.
- [x] RED/GREEN: `PackagePreflightService` imports a directory or ZIP only
      through a pre-issued source handle and compiles an immutable
      `WorkflowPolicy`. G1 validates requirements but creates neither a live
      profile binding nor an executable workflow alias.
- [x] RED/GREEN: `WorkflowPolicy` compilation is the sole logical policy
      derivation path. Descriptor/task policy produces one policy digest; any
      mismatched duplicated field is rejected.
- [x] RED/GREEN: capability resolution returns a non-executing unavailable result
      for a required G2/deferred collaborator. Only the eligible gate binds a
      `WorkflowPolicy` to profile/snapshot data as `WorkflowRegistration`.
- [x] RED/GREEN: package-only preflight returns the package/policy identifiers
      and a deterministic unavailable-capability result where required; it cannot
      accept invocation input or return a workflow alias, registration, or
      prepared input before G3 and the applicable capability gate pass.
- [x] RED/GREEN: preflight accepts only local-principal/expiry-bound opaque
      package-source handles. A human-selected local CLI path resolves to a
      handle before preparation; LLM skills cannot select an arbitrary host path
      or redirect an existing handle.
- [x] RED/GREEN: `PackageSourceSelectionPolicy` records human-managed allowed
      roots and rejects absent root configuration, noncanonical paths, and
      no-follow validation failures before it issues a package-source handle.
- [ ] RED/GREEN: when a skill names a local package without a source handle,
      return only `source_selection_required`; a human-only picker or
      `dar-package select-package` issues the handle without exposing its path
      to the skill.
- [x] RED/GREEN: `InstallationIdentityProvider` supplies a stable local principal
      from the local OS-user trust boundary to CLI, preparation, and
      runner. Restart and forged-principal tests prove requests cannot provide or
      override it; same-user processes are one v1 authority boundary.
- [x] RED/GREEN: one private per-user state store and authenticated opaque-record
      format define handle kind, owner, payload digest, issuance/expiry,
      active/revoked/consumed state, restart persistence, cleanup, and revocation
      before any source, catalog, registration, or prepared-input handle is issued.
- [x] RED/GREEN: human-only `ProfileCapabilityRecord` creation/update establishes
      immutable local profile capability records before resolution; callers and
      skills cannot supply or alter them.
- [x] RED/GREEN: produce one deterministic `CapabilityResolution` from the
      `WorkflowPolicy`, declared profile capabilities, active gates, and DAR
      inspection; reject metadata-only or missing requirements before binding.

## RA1: Authoring Release Evidence

- [x] RED/GREEN: issue principal/expiry-bound `AuthoringMaterialSet` receipts
      with opaque references, role, digest, and reference-only/distributable
      disposition. Project only the selected bounded text to a skill; public
      receipts expose neither content nor paths, and wrong-owner/expired sets
      fail closed. Package, trace, fixture, and export enforcement follows with
      the authoring and publication paths.
- [x] RED/GREEN: expose the skill-callable local authoring control plane:
      issue selected JSON material through stdin, project only an opaque
      material-set ID, and create/write/finalize a DAR-valid directory beneath
      the configured package root through an opaque output handle. Writes are
      atomic, path-contained, no-follow, and receipt-traced; finalization
      excludes `reference_only` material before writing its deterministic
      manifest. It cannot configure profiles, credentials, MCP connections, or
      approval policy. The later invocation command accepts the saved opaque
      package name without exposing the configured output-root path.
- [x] RED/GREEN: define an external authoring-evidence record containing only
      corpus/prompt/package digests, opaque material-set ID, provider/model,
      deterministic validator outcome, reviewer identity and decision, pass
      criteria, and retention policy. Persist it atomically with owner-only
      permissions; raw prompts and material content have no record fields. A
      failed validator may record no valid package digest; a passed result must
      identify its package.
- [x] RED/GREEN: deterministic external-authoring output validation accepts only
      a DAR-valid, descriptor-valid, symlink-free controlled package directory
      with a host-generated canonical package manifest, and returns redacted
      package/descriptor digests. It rejects embedding any `reference_only`
      `AuthoringMaterialSet` member before evidence recording; the manifest is
      accepted by the existing portable-package staging boundary.
- [x] RED/GREEN: the validating external-harness adapter gives a package
      generator only its `ExternalAuthoringHarnessRequest`, validates its
      directory output against the selected material projection, and returns
      only a passed package digest or a redacted failed outcome.
- [ ] RED/GREEN: authoring skill fixtures turn natural-language requests plus an
      `AuthoringMaterialSet` projection into a validated package directory;
      unselected/private material cannot enter package, trace, evaluation fixture,
      or export.
- [ ] RED/GREEN: run a de-identified checked-in authoring corpus through an
      external release harness. Record corpus/prompt/package digests, authoring
      model/provider, deterministic validator result, redacted evidence, named
      reviewer decision, and explicit pass/fail criteria.
- [ ] RED/GREEN: execute the three target skill invocation fixtures through the
      external authoring harness. Require the resulting artifacts to satisfy the
      same checked-in property contracts and behavioral routing/refusal
      expectations; review fixture-schema or expected-property changes as
      acceptance-contract changes. Execute companion fixtures inside an
      `agent-development` session with host-issued material/output handles; do
      not treat companion output as a standalone finalized package.
- [ ] RED/GREEN: build the M4.4 clean-Codex author-then-run acceptance harness.
      Implement it per plan.md M4.4 and
      `m4-4-workflow-capability-matrix.md`. The mandatory v1 cases are one
      no-tool document-summary author→finalize→saved-package-invoke success and
      one subagent/council capability-unavailable refusal; use hermetic fixtures,
      redacted evidence, and deterministic fakes. G2/G4/G5/M8 own the remaining
      feature cases.

## G2: Optional MCP Connection Control Plane and Surface Binding

- [x] RED/GREEN: a workflow that requires an unauthenticated least-scope
      connection returns `authentication_required` without a session, secret,
      binding, or remote-tool dispatch.
- [x] GREEN: human-only API-token connection flow with secret storage outside
      package artifacts and immutable profile/scope binding. The token is held
      only by the OS credential manager; the private state store keeps an opaque
      connection-bound credential reference.
- [x] GREEN: human-only OAuth authorization-code PKCE loopback connection flow
      with secret storage outside package artifacts and immutable profile/scope
      binding.
- [x] RED/GREEN: implement the first generic remote HTTPS MCP adapter with OAuth
      PKCE or a locally stored API token, pinned peer identity, and fake fixtures
      for scoped read/write/send-like surfaces. No other transport is advertised.
- [x] RED/GREEN: the HTTPS connection definition's human-only
      `oauth_authorization_code_pkce_loopback` handler binds an ephemeral local
      callback before launching the browser, verifies PKCE/state/exact redirect,
      accepts one callback, exchanges its code once, and returns only connection
      status. Tokens, code, callback query, and listener details never reach a
      skill, package, trace, or model-facing tool.
- [x] RED/GREEN: make an already-authorized OAuth connection reusable without
      human intervention. Persist only host-owned refresh configuration and a
      credential-store refresh token; refresh an expired access token before
      reconnect, or once after setup authentication failure, atomically replace
      the secret, and revalidate the same peer/snapshot. A failed or unavailable
      refresh returns `authentication_required` without opening a browser and
      never retries a possibly dispatched remote tool call.
- [x] RED/GREEN: approved MCP surface snapshot creation/review plus passive
      `tools/list` identity/input-schema drift detection on the run path.
- [x] RED/GREEN: DAR-host-owned `MCPConnectionClient` fixtures cover configured
      transport initialization, strict/unavailable startup, timeout,
      cancellation, reconnect, bounded output, and cleanup; no untested
      transport is advertised.
- [x] RED/GREEN: persist a non-executing binding from a policy's declared
      read-only MCP tools to exactly one authenticated client generation and
      current human-reviewed surface; neither this record nor its control plane
      constructs a remote tool handler.
- [x] RED/GREEN: bind every handler to one transport-specific identity,
      connection generation, and surface snapshot; reconnect, rotation, or
      drift before dispatch fails closed rather than widening a live binding.
- [x] RED/GREEN: disconnect/reconnect or peer failover between preflight and
      handler dispatch returns `surface_changed` or `capability_unavailable` and
      never invokes a replacement client under the prior authorization.
- [x] RED/GREEN: construct host-authored `HostToolBinding` handlers only from
      an approved current snapshot and opaque capability binding; before G5,
      reject every non-read-only side-effect class and prove a fake send-like
      handler is not invoked.
- [x] RED/GREEN: a tool-bearing registration requires a current opaque
      read-only MCP binding whose exact tool map matches the compiled policy;
      the runner derives its host registry from that record, executes one fake
      read-only workflow through shared capability resolution, and rejects
      generation drift before model or remote-tool dispatch.
- [x] RED/GREEN: a read-only MCP registration requires G1's bounded task-
      invocation / declared-MCP-tool policy and a current G2 binding before it
      can execute through the shared capability-resolution path.

## G3: Read-Only Workflow Runner

- [x] RED/GREEN: select a strict local model adapter and reject hosted fallback.
- [x] RED/GREEN: when `CapabilityResolution` is available, bind a
      `WorkflowPolicy` to the selected profile as an immutable
      `WorkflowRegistration` and map its workflow alias only to that registration
      digest. Reject arbitrary package paths, endpoints, commands, profile
      selections, and model-provided provisioning/approval fields.
- [x] RED/GREEN: DAR's internal preparation service authenticates the caller and
      binds workflow/package/revision/registration identifiers plus a sealed
      prepared-input identifier and expiry. It never returns that identifier to
      the skill.
- [ ] RED/GREEN: versioned `dar-package invoke` request/response schema accepts
      only a closed-set saved package name, prompt, and descriptor-declared
      inputs; it internally seals input and rejects caller-supplied prepared IDs
      or undeclared hybrid-input fields before preparation or execution.
- [ ] RED/GREEN: human/skill invocation composes local package-source
      selection, immutable registration, sealed preparation, and one run. It
      accepts only an already reviewed opaque MCP binding, preserves `--dry-run`
      and local `--ask`.
- [ ] RED/GREEN: `dar-package invoke --workspace-file` ingresses only under an
      unambiguous registered one-role/one-media-type contract; ambiguous packages
      require explicit ingress and dry runs reject files before any copy.
- [x] RED/GREEN: `WorkflowInvocationPreparationService` alone seals no-tool
      prompts and bounded `additional_context`, local principal, registration
      digest, and expiry into `PreparedWorkflowInput`. Raw structured input and
      raw/cross-principal/cross-registration/changed/expired input are rejected
      at the runner. Inputs are single-use by default; structured mapping remains
      a later descriptor-specific slice.
- [x] RED/GREEN: execute a no-tools workflow through its registration, capability
      resolution, bounded result shaping, and deep-redacted tracing.
- [x] RED/GREEN: DAR's internal runner accepts exactly the sealed workflow and
      prepared-input identifiers produced by local preparation; prove no public
      CLI path passes a raw prompt or file path directly to DAR.
- [x] RED/GREEN: validate terminal workflow output against the registered output
      contract and return bounded redacted failure for malformed or excess output.
- [x] RED/GREEN: `--dry-run` validates catalog, DAR private-package preflight,
      profile, and sealed-input policy but invokes neither a model nor a handler,
      and does not consume the input. Snapshot/file-ingress checks remain gated
      on G2/G4.

## G4: Trusted File Ingress

- [x] RED: source files outside the configured caller input root, symlinks,
      devices, non-regular files, oversized content, invalid encoding, and
      parent-swap races are rejected.
- [x] GREEN: use the sandbox specification's descriptor-relative no-follow
      primitive to copy the exact opened source into a fresh private workspace;
      return only an opaque input-artifact identifier, protected hash, and byte
      count.
- [x] RED/GREEN: `WorkspaceIngressService` is the sole sandbox-copy caller;
      profile roots and descriptor roles/types determine its acceptance, and
      preparation receives only its opaque artifact record.
- [x] RED/GREEN: prove physical paths and raw body content are absent from model
      inputs, tool results, and traces. G5 audit records and approval displays
      do not yet exist; their own acceptance tests must preserve this invariant.
- [x] RED/GREEN: extend preparation only after ingress with opaque artifact IDs
      and versions; it never reads a physical path or performs its own copy.

## G5: Model-Directed External-Tool Workflow Runner

- [x] RED/GREEN: require an `ArgumentProvenanceEnvelope` for every model-facing
      tool argument. Verify v1 canonical serialization, UTF-8 byte spans,
      normalization identifiers, sealed/artifact/constant references, and typed
      transform inputs; reject raw/unverifiable values and remote-output or
      additional-context references in a model transform.
- [x] RED: undeclared, schema-invalid, drifted, or over-cardinality writes fail
      before their external handler runs; a schema-valid model-directed call on
      the approved surface is permitted.
- [x] GREEN: use wrapper-private bindings whose handlers verify the immutable
      registration context, schema, snapshot, and G4 hash-bound file ingress
      where applicable.
- [x] RED/GREEN: registration compilation proves each `AuthorizedToolBinding`
      metadata matches the package tool contract before DAR receives it.
- [x] RED/GREEN: default `workflow_auto` (the CLI's `auto` mode) records the
      canonical external action; `--ask` uses a short-lived, one-use,
      local-principal-bound atomic approval decision.
- [x] RED/GREEN: changing the package revision, recipient alias, subject, body
      hash, profile, or snapshot invalidates an outstanding `--ask` decision.
- [x] RED/GREEN: local `--ask` blocks only at the wrapper handler boundary;
      approve invokes exactly once, while deny, cancel, and expiry produce a
      terminal non-executing result with no DAR continuation token or replay.
- [x] RED/GREEN: action ledger writes durable `intent` before dispatch and
      records `dispatched` plus a terminal status. Audit-store failure blocks
      dispatch; post-dispatch timeout/cancellation/reconnect is
      `outcome_unknown` and is never retried automatically. Retry a mutation
      only through a remote idempotency contract bound to the action digest.
- [x] RED/GREEN: atomically consume a side-effect-capable prepared input at run
      creation. Concurrent/replayed consumption fails; prompt-only actions pass
      without G4, while file-backed actions require G4.

## M8: Publication Hardening

- [x] RED/GREEN: ZIP intake accepts only a human-selected archive from the
      configured root, opens it no-follow, rejects traversal, duplicate,
      symlink, special, over-file-limit, and declared-byte-limit members,
      extracts it only to a fresh private temporary directory, and passes that
      directory through the existing staged-package boundary and DAR validation.
- [x] RED/GREEN: the private staged copy gains a deterministic owner-only
      content manifest that records the package ID, staged content digest, and
      every source payload path, byte count, and SHA-256. It is generated only
      after DAR validates the private copy and is not counted as source payload.
- [x] RED/GREEN: when a source supplies the canonical manifest, the staged
      payload's package ID, file paths, bytes, hashes, and content digest must
      reproduce its exact canonical bytes; a mismatch fails before publication.
- [x] RED/GREEN: every portable ZIP import requires a source-supplied canonical
      manifest before it reaches the staged-package boundary; the manifest must
      reproduce the exact staged payload inventory and digest.
- [x] RED/GREEN: enforce a bounded 100:1 ZIP compression ratio per member and
      across the declared archive before extraction.
- [x] RED/GREEN: canonical-manifest-v2 binds the runtime and descriptor schema
      versions plus the descriptor's exact DAR distribution/version requirement;
      a descriptor/package identity mismatch fails before publication.
- [x] RED/GREEN: an Ed25519 primitive signs and verifies exact canonical
      manifest bytes, binds a bounded publisher key ID, and rejects unknown
      publishers, altered manifests, malformed signatures, and malformed key
      material. It does not persist keys or authorize import on its own.
- [x] RED/GREEN: each human-selected local source carries an explicit
      `human_selected_local` decision through staging and records it against
      the immutable catalog revision/content-manifest digest; an unrecognized
      staged trust value fails closed at catalog import.
- [x] RED/GREEN: a local owner-only publisher store accepts only valid Ed25519
      public keys under bounded human-configured IDs, prevents silent
      replacement, exposes redaction-safe identities, and supports explicit
      key revocation through local CLI control-plane commands.
- [x] RED/GREEN: an explicitly selected publisher-signed ZIP must supply a
      source manifest that exactly matches the staged payload and a detached
      Ed25519 signature from a currently trusted local key before catalog import;
      the immutable catalog revision records `publisher_signature` plus the
      signing key ID. The recipient-host CLI fixture proves trust, selection, and
      registration end to end.
- [x] RED/GREEN: canonical-manifest-v2 Ed25519 export/import fixtures prove
      signer/key-id binding, rejection of an unknown locally trusted publisher
      key, and a recipient-host signed-package import. Explicitly selected
      distributable authoring material is included; private source material is
      absent.
- [x] RED/GREEN: deterministic local ZIP export rechecks the private staged
      manifest and payload digests without executing package content, and a
      ZIP round trip preserves the content digest.
- [ ] RED/GREEN: a clean consumer installation verifies the locally installed
      plugin, the published DAR wheel, bundled plugin assets, and a trusted
      portable package exchange.

## Deferred After the First Release

- [ ] Evaluate signed release metadata, transitive dependency locks, and custom
      key revocation as publication hardening after a concrete threat model;
      ordinary v1 relies on the approved Artifactory release and exact DAR pin.
- [ ] Retrieval/embedding profiles and host vector/index services.
- [ ] Durable conversational sessions and durable DAR interruption continuation.
- [ ] Guardrail phases beyond DAR's live input and tool-input handlers, and
      broader context-management profiles.
- [ ] Subagent and `ask_llm` integration.
- [ ] Optional containerized acceptance isolation with virtual input paths and
      default-deny network. This is deferred until explicitly requested; M4.4
      is a clean-process behavioral harness and does not require Docker.

## Focused Validation

- [ ] All unit tests use fake model adapters, MCP handlers, approval stores,
      and filesystem primitives; no live Fastmail, Hugging Face, or model call.
- [ ] A positive fixture is required before a gate's capability is reported live.
- [ ] G5 may run after G0, G1, and G3; it additionally requires G2 for MCP
      actions and G4 for file-backed arguments. It must not replay a DAR approval
      interruption or claim graph-preserving continuation.
