# DAR Authoring Plugin Implementation Plan

## Status

Active implementation plan. Completed milestones record their implementation
evidence below; unscheduled items still require a scoped slice before work
begins. [`spec.md`](spec.md) and [`tasks.md`](tasks.md) remain the controlling
contracts.

## First Runtime Vertical Slice

The first implementation slice proves a fixture-authored, human-selected local
no-tool runner:

```text
human-selected fixture directory package
  -> private staged package root
  -> immutable WorkflowPolicy
  -> eligible local-model WorkflowRegistration
  -> sealed PreparedWorkflowInput
  -> run_dar_workflow / dar-workflow-run
```

It deliberately excludes adapted-skill behavior, ZIP import/export, package
signatures, tool-argument provenance, caller-file ingress, MCP, and side
effects. It supports a saved, task-specific workflow with no external tools and
uses fake local-model adapters and host collaborators. M4 and M8 remain the
only path to an end-to-end authoring-plugin publication claim.

## Milestones and Dependencies

| Milestone | Gate | Outcome | Depends on |
| --- | --- | --- | --- |
| M0 | RA0 — authoring baseline | Static adapted-skill provenance, fixture contracts, and canonical basic/tool package templates are implemented. | None |
| M1 | G0 — package/server spike | Minimal install/discovery proof, then release-integrity proof. | None |
| M2 | G1 runtime core | Human-selected directory staging, policy compilation, and package-only preflight. Implemented. | M1 |
| M3 | G3 | Local no-tool workflow execution through the one sealed runner interface. Implemented. | M2 |
| M4 | RA1 — authoring acceptance | M4.0 material projection and M4.1 redacted evidence contract are implemented; external adapted-skill behavior remains. | M0, M2 |
| M5 | G2 | Configured HTTPS MCP control plane and reviewed binding. Implemented through one configured client per host; M5.5 execution evidence is `93159e9`. | M2; M3 for M5.5 execution integration |
| M6 | G4 | Trusted caller-file ingress. Implemented. | Focused tested sandbox descriptor-relative no-follow-copy primitive at a recorded prerequisite revision; M2 |
| M7 | G5 | Model-directed external side effects with audit and local `--ask`. Implemented for reviewed generic MCP bindings; multi-client composition requires a follow-up slice. | M3; M5 for MCP actions; M6 for file arguments |
| M8 | Publication acceptance | Portable package exchange and published plugin evidence. | M0, M1, M3, M4 |

M1 is the G0 runtime gate; M0 and M4 are the separate authoring release-evidence
track. M4 may run in parallel with M3, but adapted skills may not be published
and the end-to-end plugin release may not be declared complete until M4 and M3
both pass. M5, M6, and M7 are independent additions after the base path; they
must not delay or widen M3.

## Commit-Sized Slices

Each slice begins by adding or updating focused tests and records the observed
RED failure before its implementation. A commit includes its tests and only the
documentation required to describe that finished boundary.

### M0 — Reproducible authoring baseline

Before M0.2, record the source locator `../ai-environment-roschuma`, one selected
immutable revision for each source skill, applicable license/notice evidence,
and an explicit redistribution reviewer decision. Copying is blocked until this
record exists; current checkout state is not an immutable source revision.

1. **M0.1: Freeze target-invocation fixtures.** Add versioned, de-identified
   fixtures for the three adapted skills, including selected
   `AuthoringMaterialSet` projections, expected property/refusal states, and
   private-material exclusions. Add a fixture-schema validator; it does not call
   a model. These are static contract projections, not production-issued material
   sets; issuance is implemented in M2.4.
2. **M0.2: Adapt and prove skill provenance.** Copy the three upstream skills at
   immutable revisions, record every copied path and redistribution review in
   `adapted-skill-provenance.yaml`, and add discovery/provenance coverage tests.
   Rewrite only their DAR-specific contract text.
3. **M0.3: Add deterministic authoring artifact checks.** Add canonical package
   templates and tests that validate fixture-produced artifacts with DAR's
   existing loader. Static checks assert declared interfaces and unsafe-input
   refusal requirements; behavioral routing stays in M4.

M0 exit: all three skill assets have reproducible provenance and deterministic
fixture-contract validation; publication remains blocked on M4 and M8.

### M1 — G0 packaging spike

1. **M1.1: Prove the minimal plugin launch.** Against the target Codex build,
   prove a checked-in manifest can start a local stdio server from an installed
   artifact without source-path interpolation. Record the supported manifest
   fields, installation path, environment contract, and clean-directory MCP
   `initialize` evidence. The server advertises no execution tool. Stop here if
   the launch topology is unsupported.
2. **M1.2: Lock the launcher supply chain.** After M1.1 succeeds, implement the
   checked-in `uvx`
   launch contract and verification of the selected plugin/DAR artifacts against
   signed release metadata from a configured trusted-key root, with configured
   expiry and minimum-version floor. Tests reject an unexpected index, non-exact
   version, altered plugin or DAR wheel bytes, an unpinned transitive dependency,
   expired metadata, untrusted or revoked signing keys, revoked artifact
   versions, and a version below the floor; startup records all resolved
   dependency identities without requiring an Artifactory network call.
3. **M1.3: Prove release-candidate wheel isolation.** Build the plugin wheel
   and test it from a clean directory: assets are present, startup records resolved
   dependencies, and no source-tree path or execution tool is exposed.

M1 exit: a release-candidate plugin starts as a local stdio MCP server and is
safe to discover, but cannot execute a workflow or be published.

### M2 — G1 runtime core

1. **M2.0: Add one private state store and opaque records.** Use one
   standard-library-backed, per-OS-user store; do not introduce a backend
   interface. Store a handle's kind, payload digest, issuance/expiry, and
   active/revoked/consumed state behind authenticated opaque IDs. Tests reject
   forged, expired, wrong-kind, altered, revoked, and wrong-registration IDs.
2. **M2.1: Establish installation identity and one local model profile.** Derive
   the v1 installation principal from the local OS-user trust boundary and add
   one human-created immutable profile record. Callers, skills, and MCP requests
   cannot supply or override either value.
3. **M2.2: Define no-tool descriptor and task-policy validation.** Add the
   smallest `WorkflowDescriptor`/`task_invocation` contract needed for a no-tool
   workflow, with finite graph/step limits and terminal output schema. Reject an
   undeclared tool console before DAR execution.
4. **M2.3: Select and stage a directory package.** Define one human-managed
   allowed root and issue an opaque source handle only after canonical no-follow
   validation. Make a private descriptor-relative no-follow copy, test bounded
   streaming/hash, parent-swap and symlink replacement, then validate DAR
   compatibility against that staged copy. ZIP selection is deferred to M8.
5. **M2.4: Add the immutable local package catalog.** Retain the staged package
   identity by `package_id` and manifest digest, test idempotent reimport and
   explicit alias collision behavior, and retain prior revisions. This slice
   produces package identity, not an executable alias.
6. **M2.5: Compile `WorkflowPolicy` and resolve capabilities.** Compile the
   no-tool descriptor into one immutable policy and produce deterministic
   eligible or non-executing unavailable `CapabilityResolution` results. No
   profile is bound and no workflow alias exists in this slice.
7. **M2.6: Add package-only preflight.** Implement `PackagePreflightService`
   for an opaque package handle only. Its closed `PackagePreflightResult`
   contains `{package_id, revision_digest, workflow_policy_digest,
   capability_resolution}` or a discriminated unavailable result. It cannot
   accept invocation input, create a registration or alias, issue a prepared
   input, or call the runner.

M2 exit: a trusted local package can be imported and inspected as portable
policy, while packages requiring absent collaborators fail closed without live
provisioning.

### M3 — G3 local no-tool runner

1. **M3.1: Bind eligible policy to a local profile.** Consume M2's
   `InstallationIdentityProvider` and profile capability record. Define a
   `LocalModelProfile` with an allowlisted adapter implementation and model IDs;
   the wrapper determines eligibility rather than trusting an adapter label or
   caller input. Create immutable `WorkflowRegistration` and local alias mapping.
   Tests reject hosted fallback, caller-selected profiles, and aliases not bound
   to an eligible policy.
2. **M3.2: Seal prepared workflow input.** Add
   `WorkflowInvocationPreparationService`, the sole issuer of
   `PreparedWorkflowInput`, after eligible registration binding. It seals the
   prompt, structured projection, bounded `additional_context`, local
   principal, registration digest, and expiry. Test raw, cross-principal,
   cross-registration, changed, and expired input rejection. Prepared inputs are
   single-use by default; reuse requires an immutable read-only profile policy
   with explicit maximum uses and expiry.
3. **M3.3: Expose the one runner interface.** Add the versioned
   `run_dar_workflow` request/response schema and server path. It accepts only a
   catalog workflow id plus opaque prepared-input id, runs DAR package-loader
   preflight only against the immutable private staged package root, invokes DAR
   through its library API with a fake strict local adapter, validates terminal
   output, and emits bounded redacted tracing. A catalog-valid but DAR-preflight-
   invalid revision fails before model or handler entry.
4. **M3.4: Add the local CLI façade and dry run.** Implement
   `dar-workflow select-package`, `dar-workflow prepare`, and
   `dar-workflow-run` as handle/preparation façades over the same runner. Test
   that `--dry-run` calls neither a model nor a handler. The CLI may accept raw
   prompt text only at invocation preparation and passes only a
   `PreparedWorkflowInput` to DAR; `run_dar_workflow` accepts only workflow and
   sealed-input identifiers.

M3 exit: a human can repeatedly prepare and run a saved no-tool package with a
prompt through the sealed, catalog-only runner interface.

### M4 — Authoring-skill external acceptance (release-evidence track)

1. **M4.0: Add authoring-material projection.** Implemented in the private
   `AuthoringMaterialService`: it issues principal/expiry-bound
   `AuthoringMaterialSet` projections with reference-only/distributable status.
   Public receipts exclude content and paths; only the exact selected set can
   project bounded content. Package/trace/fixture/export exclusion is enforced
   by the later authoring and publication paths.
2. **M4.1: Define the external authoring evidence contract.** Implemented as
   `AuthoringEvidence`: its atomic private record contains corpus/prompt and
   package digests, opaque material-set id, model/provider identity,
   deterministic validator result, named reviewer decision, pass criteria, and
   retention policy. Raw prompt and material fields cannot be recorded.
3. **M4.2: Run the external authoring harness.** Run the checked-in,
   de-identified corpus with the selected authoring model outside unit tests and
   record evidence through the M4.1 contract.
4. **M4.3: Gate the three target invocations.** Compare generated packages to
   fixture property contracts, require a human intent-fidelity review until a
   judge calibration is approved, and treat fixture property changes as reviewed
   acceptance-contract changes.

M4 exit: the adapted skills have behavioral evidence without making model calls
part of ordinary test execution.

### M8 — Publication acceptance

1. **M8.1a: Accept bounded ZIP package intake.** Implemented: a human-selected
   `.zip` from the same allowlisted root as a directory package is opened
   no-follow, rejects traversal, duplicate, symlink, special, over-file-limit,
   and declared-size-limit entries, extracts only to a fresh private temporary
   directory, and then uses the existing descriptor-relative directory stager.
   It does not create a second runner path.
2. **M8.1b: Generate the staged content manifest.** Implemented: after DAR
   validates the private copy, write a deterministic owner-only
   `package-manifest.json` that binds the package ID, content digest, and every
   source payload path, byte count, and SHA-256. The generated manifest is not
   yet a source-supplied or publisher-signed trust assertion.
3. **M8.1c: Verify portable package trust.** Source-supplied manifests, when
   present, are compared byte-for-byte to the canonical private payload
   inventory before publication. A human can explicitly select a
   publisher-signed ZIP; it must supply that exact manifest plus a detached
   Ed25519 signature from a currently trusted local publisher key before staging
   or catalog import, and its revision records the signing key ID. Each ordinary
   human-selected local source records `human_selected_local` against its
   immutable revision/content-manifest digest. The remaining trust work is to
   require source manifests for every portable ZIP exchange, enforce the ZIP
   compression-ratio limit, and complete a signing-export path.
4. **M8.1d: Export portable packages.** Implemented for an already-private
   staged package: deterministic stored ZIP export rechecks the generated
   manifest and payload hashes without executing package content, and round
   trips through ZIP intake to the same content digest. Publisher trust remains
   a prerequisite for interchange outside the local host.
5. **M8.2: Run the first publication gate.** Require M3's no-tool runner
   evidence and M4's external authoring-skill evidence, then verify the released
   wheel from a clean consumer-install directory. No adapted skill or execution
   capability is published until this gate passes.

## Later Milestones

### M5 — G2 configured HTTPS MCP read-only path

1. **M5.1: Add human-owned connection records.** Define immutable
   profile/connection/scope records and credential-store references; return
   `authentication_required` without exposing credentials.
2. **M5.2a: Add human-only API-token setup.** Store a human-provided token only
   in the OS credential manager, bind its opaque reference to the immutable
   connection, and reject cross-connection authentication use. Test secret
   exclusion from state and returned records.
3. **M5.2b: Add human-only OAuth authorization-code PKCE loopback setup.** Test
   listener-first setup, state/exact-callback checking, one-time exchange, and
   secret exclusion.
4. **M5.2c: Reuse and refresh OAuth credentials on reconnect.** Persist only
   immutable host-owned refresh configuration plus a credential-store token
   bundle. Test refresh before reconnect, one setup-authentication-failure
   refresh retry, atomic credential replacement, and the no-browser,
   `authentication_required` failure path. Do not retry a remote tool call that
   may already have been dispatched.
5. **M5.3: Add the HTTPS MCP lifecycle adapter.** Implement configured HTTPS
   initialization, peer-identity pinning, timeout/cancellation/reconnect/cleanup,
   and bounded output with fake transport fixtures only.
6. **M5.4a: Persist reviewed MCP surfaces.** Create approved snapshot records
   from identity/input-schema metadata and passive drift detection. Remote prose
   and annotations are untrusted and not retained as approval authority.
7. **M5.4b: Retrieve and revalidate MCP surfaces.** Extend the configured HTTPS
   client with bounded `tools/list`, then verify the current identity/input
   schema surface before binding or dispatch.
8. **M5.4c: Persist a non-executing capability binding.** Bind a compiled
   read-only policy only to its exact authenticated client generation and a
   current human-reviewed surface. This opaque record has no remote handler;
   reconnect or drift invalidates the attempted binding.
9. **M5.5a: Construct a read-only host handler.** Reload the opaque binding,
   derive `HostToolBinding` schema and identity only from the reviewed current
   surface, and revalidate it immediately before bounded `tools/call` dispatch.
   A send-like tool is neither constructed nor dispatched.
10. **M5.5b: Integrate a read-only binding with M3.** After the G1 bounded
    task-invocation and declared-MCP-tool policy can compile a tool-bearing
    package without opening a general-purpose console, register it only with a
    current opaque binding, derive its host registry, and execute one fake
    read-only MCP workflow. A fake send-like tool remains unavailable and its
    handler does not run; generation drift before execution fails before model or
    remote-tool dispatch.

Do not add stdio or any unreviewed transport in this milestone.

### M6 — G4 trusted file ingress

1. **M6.1: Accept the sandbox ingress prerequisite.** Begin only after the
   sandbox spec's descriptor-relative no-follow copy primitive has focused proof
   of bounded streaming/hash, atomic private copy, and opaque artifact
   `{id, hash, byte_count}` output. Record the prerequisite revision in the
   implementation evidence; the interactive scratch workspace is not required.
2. **M6.2: Add `WorkspaceIngressService`.** Apply profile roots and descriptor
   role/type limits to the sandbox primitive; reject outside-root, symlink,
   non-regular, encoding, size, and parent-swap cases.
3. **M6.3: Integrate opaque input artifacts.** Extend preparation only with
   hash-bound artifact IDs and versions. Prove physical paths and raw content are
   absent from model inputs, tool results, traces, audit records, and approvals.

### M7 — G5 side-effecting tools

1. **M7.1: Add tool-argument provenance.** Implement
   `ArgumentProvenanceEnvelope v1` parsing and verification: canonical JSON,
   UTF-8 spans, registered normalizations, opaque source references, and the
   non-authority `compose_content_v1` transform. Tests include remote-output and
   `additional_context` laundering attempts.
2. **M7.2: Add side-effect binding enforcement.** Validate every
   `AuthorizedToolBinding` against the registration, schema, snapshot,
   provenance envelope, and call budget before handler entry.
3. **M7.3: Add `workflow_auto` action ledger.** Write durable intent before
   dispatch, record dispatch and terminal outcome, and enforce at-most-once / no
   automatic retry after uncertain outcomes.
4. **M7.4: Add local `--ask` brokerage.** Bind a short-lived approval to the
   canonical action, principal, revision, profile, snapshot, and artifact hash;
   atomically consume it at the handler boundary.
5. **M7.5: Consume side-effect prepared inputs.** Atomically consume a
   side-effect-capable prepared input at run creation and reject concurrent or
   replayed use. Add fake MCP mutation only after M5 and file-backed mutation
   coverage only after M6.

Each M7 slice includes fake-handler proof that exactly one approved schema-valid
action dispatches once; undeclared, schema-invalid, drifted, over-budget,
audit-store-failed, denied, cancelled, expired, or replayed actions dispatch
zero times; post-dispatch uncertainty is `outcome_unknown` and is not retried;
and concurrent prepared-input consumption has exactly one winner.

This milestone must not simulate DAR continuation or replay an interrupted
graph.

## Not Yet Commit-Sized

The following remain intentionally unscheduled because their host contracts are
not yet implemented or need a separate decision: embedding/vector profiles,
durable sessions and continuation, broader guardrail/context profiles,
subagents/`ask_llm`, a picker UI, judge calibration, and live Artifactory or MCP
provider acceptance tests. Their absence does not block M0–M3.

## Milestone Verification

- Every slice runs its focused pytest tests, `ruff check`, and scoped
  `pre-commit` before commit.
- M1 additionally proves packaged-wheel installation and MCP `initialize` in a
  clean directory.
- M2 and M3 run the DAR package-loader and no-tool execution fixtures with fake
  collaborators.
- M4 is an external release-harness gate; its model invocation is never a unit
  test.
- M5–M7 require the positive fake fixtures named in `tasks.md` before their
  capabilities are advertised as live.
