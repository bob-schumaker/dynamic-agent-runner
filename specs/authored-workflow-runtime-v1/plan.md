# Authored Workflow Runtime v1 Implementation Plan

## Status

Historical implementation plan for the implemented v1 runtime record.
Completed milestones retain their evidence; the former `dar-authoring` plugin
is retired, so this plan does not authorize new plugin work. New runtime work
requires a scoped DAR specification. [`spec.md`](spec.md) and
[`tasks.md`](tasks.md) preserve the v1 contract and evidence.

## Control-Plane Direction Change

This plan supersedes the former local-stdio-MCP launch path. `dar-authoring` is
a skills-only Codex plugin: it has no `.mcp.json`, `mcpServers` entry,
`run_dar_workflow` tool, `dar-mcp` launcher, or session broker. The skills
collaborate with the user, then execute the checked-in `uv run ... dar-package
<command>` control-plane contract. DAR remains free to bind a generated workflow
to a human-configured MCP capability at runtime; that workflow capability is not
a plugin-provided MCP server.

## First Runtime Vertical Slice

The first implementation slice proves a fixture-authored, human-selected local
no-tool runner:

```text
human-selected fixture directory package
  -> private staged package root
  -> immutable WorkflowPolicy
  -> eligible local-model WorkflowRegistration
  -> sealed PreparedWorkflowInput
  -> dar-package invoke
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
| M1 | G0 — package/CLI spike | Minimal skills-to-CLI proof from an installed wheel. | None |
| M2 | G1 runtime core | Human-selected directory staging, policy compilation, and package-only preflight. Implemented. | M1 |
| M3 | G3 | Local no-tool workflow execution through the one sealed runner interface. Implemented. | M2 |
| M4 | RA1 — authoring acceptance | M4.0 material projection, M4.1 redacted behavioral evidence, M4.3's three reviewed package runs, and M4.4's two clean-Codex author-then-run cases are implemented. | M0, M2, M3 |
| M5 | G2 | Configured HTTPS MCP control plane and reviewed binding. Implemented through one configured client per host; M5.5 execution evidence is `93159e9`. | M2; M3 for M5.5 execution integration |
| O | OAuth-advertising HTTPS MCP setup | O1–O7 implement human-only protected-resource/authorization-server discovery, dynamic public-client registration, resource-bound PKCE/refresh, drift handling, the approved Apple-backed Fastmail read-only acceptance, and one separately authorized `create_note` mutation acceptance. It extends M5 rather than changing plugin skills. | M5; `mcp-oauth-discovery-registration` O1–O7; G2 reviewed-surface binding for O6/O7 |
| M6 | G4 | Trusted caller-file ingress. Implemented. | Focused tested sandbox descriptor-relative no-follow-copy primitive at a recorded prerequisite revision; M2 |
| M7 | G5 | Model-directed external side effects with audit and local approval support. Reviewed generic MCP bindings, workflow-policy ownership, run-scoped approval, and execution-profile capability matching are implemented through G5.3. | M3; M5 for MCP actions; M6 for file arguments |
| M8 | Publication acceptance | Not applicable: the former plugin is retired. | M0, M1, M3, M4 |

M1 is the G0 runtime gate; M0 and M4 are the separate authoring release-evidence
track. M4 may run in parallel with M3, but adapted skills may not be published
and the end-to-end plugin release may not be declared complete until M4 and M3
both pass. M5, M6, and M7 are independent additions after the base path; they
must not delay or widen M3.

M4.4's two no-tool cases may run after M3. Its MCP, artifact, side-effect, and
portability scenario references belong to M5, M6, M7, and M8 respectively; they
do not block M4.4's CLI-first author-then-invoke result.

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

### M1 — G0 packaging and CLI spike

1. **M1.0: Audit the obsolete MCP launch topology.** Inventory the old
   `.mcp.json`/`dar-mcp` discovery evidence and tests. It is historical evidence
   for a rejected design and is not M1 completion evidence; do not delete it
   until M1.3's replacement coverage passes.
2. **M1.1: Add the CLI entry point and discovery receipt.** Start RED with
   entry-point tests for `dar-package version --json`: exact stdout receipt,
   redacted JSON stderr failure, nonzero failure exit, and no source/state path
   exposure. Then add the `dar-package` console entry point to the DAR wheel.
   The existing `dar-workflow` entry points remain human-only migration
   compatibility commands and are not aliases for the skill-facing contract.
3. **M1.2: Prove the local-wheel entry point.** From a fresh temporary working
   directory, execute `uv run --no-project --python 3.14 --with <absolute-wheel-path>
   dar-package version --json`. Record the resolved wheel identity and receipt;
   prove the command neither opens state nor emits a source or state path.
4. **M1.3: Migrate the plugin surface.** After M1.1–M1.2 pass, rewrite every
   bundled skill/template to the exact pinned command and statically verify its
   index/version/`version --json` text. Then delete `.mcp.json`, `mcpServers`,
   `dar-mcp`, the plugin-owned session-broker launch path, and their tests in the
   same migration slice. This does not remove DAR's generic MCP entry point;
   replacing its authoring-broker compatibility surface requires the later
   role-scoped CLI acceptance coverage. The clean plugin smoke test must find
   skills and no plugin-provided MCP server.
5. **M1.4: Verify wheel entry-point assets.** Inspect the built wheel's
   `dist-info/entry_points.txt` and `RECORD` membership to prove the
   `dar-package` mapping is packaged. This is asset-presence evidence, not a
   distribution-integrity audit.
6. **M1.5: Post-release published-index verification.** After the release build
   publishes the pinned wheel, in a fresh environment execute
   the exact published `uv run --no-project --python 3.14 --index-url
   <approved-index> --with
   dynamic-agent-runner==0.2.1 dar-package version --json` command and record
   the resolved wheel name, version, and digest from the resolver report. This
   is the only evidence for published-index resolution; the local OCI-build
   wheel proof is pre-release entrypoint/assets evidence only. M1 does not wait
   for this external publication step.

M1 exit: the local plugin exposes skills that can invoke DAR's release-candidate
CLI from a clean directory, but cannot execute an unprepared workflow or be
published.

### M2 — G1 runtime core

1. **M2.0: Add one private state store and opaque records.** Use one
   standard-library-backed, per-OS-user store; do not introduce a backend
   interface. Store a handle's kind, payload digest, issuance/expiry, and
   active/revoked/consumed state behind authenticated opaque IDs. Tests reject
   forged, expired, wrong-kind, altered, revoked, and wrong-registration IDs.
2. **M2.1: Establish installation identity and one local model profile.** Derive
   the v1 installation principal from the local OS-user trust boundary and add
   one human-created immutable profile record. Callers and skills
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
3. **M3.3: Expose the one runner interface.** Add the versioned `dar-package
   invoke` request/response schema and CLI path. It accepts only a saved package
   name, stdin prompt, and descriptor-declared inputs, resolves the immutable
   registration internally, and seals inputs internally,
   runs DAR
   package-loader preflight only against the immutable private staged package
   root, invokes DAR through its library API with a fake strict local adapter,
   validates terminal output, and emits bounded redacted tracing. The sealed ID
   never reaches the skill. A catalog-valid but DAR-preflight-invalid
   revision fails before model or handler entry.
   Implemented by the skill-facing façade and saved-registration composition:
   it accepts no path, workflow ID, prepared-input ID, profile, endpoint, or
   MCP-binding argument.
4. **M3.4: Add the local CLI façade and dry run.** Implement
   private handle/preparation services beneath `dar-package invoke`. Test
   that `--dry-run` calls neither a model nor a handler. The CLI may accept raw
   prompt text only at invocation preparation and passes only a
   `PreparedWorkflowInput` to DAR; skills receive neither its identifier nor a
   separate run command.
   Implemented: `dar-package invoke` parses only its closed flags, emits
   versioned redacted JSON, and stops a dry-run workspace request before opening
   the host or copying a file.
5. **M3.5: Compose local invocation.** Add the skill-facing
   `dar-package invoke --package-name --prompt-stdin` composition command. It
   resolves only a saved package against its configured profile and reviewed
   capability bindings, seals the prompt, and runs the registration. It does not
   accept model settings or tool provisioning; it preserves `--dry-run` and
   local `--ask` behavior. A supplied workspace file is admitted only through a
   one-role/one-media-type registered contract; dry run rejects it before ingress.
   Implemented for an already registered saved package. A local
   `dar-package select-package --path --json` command creates an opaque handle
   only for human-controlled setup. A skill with only a directory/ZIP display
   name returns the closed `source_selection_required` result instead; neither
   selection nor registration is an invoke flag.

M3 exit: a skill can repeatedly invoke a saved no-tool package with a prompt
through the sealed, catalog-only runner interface.

### M4 — Authoring-skill external acceptance (release-evidence track)

1. **M4.0: Add authoring-material projection and controlled output.** Implemented
   in the private `AuthoringMaterialService` and `AuthoringOutputService`: the
   host issues principal/expiry-bound `AuthoringMaterialSet` projections with
   reference-only/distributable status, then exposes skill-callable create/write/
   finalize commands through opaque output IDs. Public receipts exclude material
   content and source paths; output writes are relative, atomic, no-follow, and
   receipt-traced. Only the exact selected set can project bounded content.
   Package/trace/fixture/export exclusion is enforced by the authoring and
   publication paths.
2. **M4.1: Define the external authoring evidence contract.** Implemented as
   `AuthoringEvidence`: its atomic private record contains corpus/prompt and
   package digests, opaque material-set id, model/provider identity,
   deterministic validator result, reviewer identity and decision, pass
   criteria, and retention policy. Raw prompt and material fields cannot be
   recorded.
3. **M4.2: Run the external authoring harness.** The checked-in
   `scripts/run_dar_authoring_harness.py` runner now passes a selected private
   material projection to a caller-provided generator only through a temporary
   request file, captures generator output, validates the expected artifacts and
   finalized DAR package, and records only M4.1 redacted evidence. Its default
   mode uses a temporary direct-output directory; a host-control-plane run
   supplies both a configured package root and a new package name, so the
   generator can finalize through DAR's opaque authoring-output commands and the
   harness validates that exact new package. Run the de-identified corpus with
   the selected authoring model outside unit tests; that live evidence remains
   required.
4. **M4.3: Gate the three target invocations.** The harness enforces checked-in
   per-artifact YAML/JSON requirements and forbidden text for each fixture;
   compare live generated packages to those contracts, then execute the exact
   finalized package through DAR's package execution interface with the exact
   model identifier declared by the package. M4.4 separately gates the
   saved-registration `dar-package invoke` control-plane path. Each behavioral
   case binds the finalized package digest and declared model identifier; a
   copied package, changed model identifier, or structural-only check is
   non-qualifying. Until a judge calibration is approved, the valid gate is a
   human comparison of the fixture/request, generated package specification, and
   de-identified invocation transcript; the harness records only its digest,
   terminal outcome, and bounded dispatch evidence. Treat fixture property or
   behavioral-criterion changes as reviewed acceptance-contract changes. Run
   each companion-skill fixture inside an
   `agent-development` authoring session with the host-issued `material_set_id`
   and `authoring_output_id`; companion skills do not create or finalize a
   standalone package.

   External de-identified Codex runs on 2026-08-24 passed the deterministic
   harness after the entry-purpose contract was strengthened:

   - `agent-development`
     - Corpus: `9e9a5f43af4450127603c033aab9979e7fa86d6d9260468ac4a2f2bcba83a553`
     - Package: `1dc345f03250abf14e9adf50bddf83001f101f9d9d94125749b2a046606c2432`
   - `agent-development` plus `agent-evaluation`
     - Corpus: `dc866c1354e4205aa6ca181fc622df43fbf7a78ee737f4348df7c32cae612b11`
     - Package: `0e252f36ab2f0dd7b11742de2d4fbfbdac377dab924e5e46196e195e98fa02b9`
   - `agent-development` plus `agent-tool-contract-design`
     - Corpus: `3d772a4a6c1c8dacf637c4852cb86536123d2759d9d5fd91742ef05dd6eb9ac9`
     - Package: `ecd3137019defe1d506dc222e9aa1cb480ed5d2ef2178a86abbe64220abd147b`

   The earlier records identify provider `codex`, model `gpt-5.6-sol`, and a
   passed validator result with redacted retention. On 2026-08-25, the human
   selected `gpt-5.6-terra` as the execution model and approved the resulting
   human-retargeted final revisions after reviewing each package specification
   and live transcript. The three owner-only v2 evidence records bind that
   approval to the final package digests, transcript/case digests, terminal
   outcome, and dispatch counts, while recording
   `external_authoring_with_human_model_retarget` provenance. The no-tool base
   and evaluation packages completed with zero dispatches; the reviewed fake
   read-only tool surface completed with one dispatch. This completes M4.3.

5. **M4.4: Run clean-Codex author-then-run acceptance.** Implemented as a checked-in,
   external acceptance harness around a temporary Herdr workspace. Every case
   creates one clean Codex authoring invocation, which receives only a text
   authoring request plus the explicitly supplied de-identified material,
   current adapted skills, and current DAR wheel. A second independent clean
   Codex invocation receives a text-only request for the saved package and must
   use `uv run ... dar-package invoke` to run it. An artifact case may use
   declared fixture files and the same CLI after trusted ingress. The authoring
   turn
   must use a host-issued `material_set_id`, create its opaque
   `authoring_output_id` through the defined `dar-package` command, then
   finalize through `AuthoringOutputService`; the finalization receipt's
   `package_name` and package digest are the only permitted handoff for a
   positive case. Before its run turn,
   the fixture controller—not Codex—uses that receipt to stage/import the exact
   revision and create its catalog registration. The run turn receives only the
   finalized closed-set `package_name`; it cannot select a package, register a
   revision, or recreate it. The harness proves the chain from finalization
   manifest digest to staged catalog revision, registration digest, and invoke
   receipt.

   Before either turn, a per-scenario hermetic host-fixture manifest creates the
   profile, package root, selected-material/output handles, and applicable MCP
   connection/snapshot, fake credential, approval broker, and ingress artifacts.
   The controller retains the state, credential, package, and control-plane
   roots. The adapted skills instruct the author to use only material/output
   commands and the runner to use only defined `dar-package` subcommands.
   Required negative tests prove DAR rejects attempts to configure a
   profile/MCP connection/trust store or to manufacture source handles with zero
   DAR-control-plane mutation. This is an instruction and DAR-contract test, not
   a process capability grant.

   Run each child in a fresh temporary working directory and a scrubbed
   environment. The harness explicitly supplies only the adapted skills, plugin,
   DAR wheel, checked-in CLI template, and test-scoped Codex authentication
   needed for the case; it removes inherited `PYTHONPATH`, virtualenv, and
   tool-home variables, rejects source-root or undeclared executable/module
   resolution, and records resolved executable, module, and wheel identities in
   redacted evidence. A harness-only Codex-auth provisioner supplies a
   test-scoped authentication source or pre-authenticated profile outside
   model-visible inputs; it is redacted and removed with the fixture. Sentinel
   ambient plugin, state, package-root, credential, and auth files provide
   supplementary evidence that the harness did not select them. The harness
   removes every resource it created on completion, failure, or interruption.

   This is a clean-process behavioral acceptance harness, not an OS-enforced
   containment claim: a child process retains ordinary host-process access.
   The closed CLI schemas, explicit fixture inputs, hermetic fake collaborators,
   and negative state-mutation tests remain the
   release boundary. Do not claim filesystem or network isolation from this
   harness.

   A clean Codex run proves only the declared CLI contract. Prompt-only scenarios
   invoke it end to end; artifact scenarios separately prove the existing
   host-mediated ingress/internal-preparation/`dar-package invoke` path with
   the same generated
   revision. A future direct artifact-reference UX needs its own closed contract
   before it can be claimed.

   Use [`m4-4-workflow-capability-matrix.md`](m4-4-workflow-capability-matrix.md)
   as the scenario-authoring reference. It defines the common authoring input
   envelope, feature-specific required inputs, applicable host gate, and the
   correct positive, capability-unavailable, or refusal outcome. Update that
   reference before adding a scenario for a DAR feature not yet represented in
   the matrix.

   Each checked-in scenario manifest declares its expected status, required
   gates and host fixtures, invocation mode, required artifact roles, expected
   terminal phase, and mandatory zero-dispatch assertions. A positive case is
   `pass` only when its declared gates/fixtures are present; it may not be
   relabeled unavailable. A refusal or unavailable manifest states whether it
   terminates at authoring validation, source selection, capability preflight /
   registration, or invocation, and evidence proves later handles and dispatch
   are absent rather than fabricating a successful chain.
   An MCP fixture names only a stable human-configured connection requirement
   and reviewed semantic tool identifier/schema. It must omit endpoint,
   credential, redirect, raw `tools/list`, and unreviewed-tool data; the checker
   rejects a package that embeds or requests any of them.
   The plan table is the minimum scenario corpus; the matrix is the sole feature
   input/gate reference.

   Persist one atomically written, versioned `AuthorThenRunEvidence` record per
   scenario. It binds the scenario/contract-checker version, allowed
   plugin/skill/wheel identities, terminal phase, capability/policy outcome,
   invocation mode, redacted trace/action evidence and dispatch count,
   expected/observed status,
   and reviewer decision. A positive record also binds authoring material/output
   and final package digests plus catalog/registration/preparation linkage to the
   exact revision; a non-pass record proves later handles and dispatch are
   absent. It records no fixture body, physical path, credential, OAuth
   code/token, raw prompt, or external tool content. Until a named reviewer
   records intent fidelity, its outcome is `pending_human_review`, never `pass`.
   A deterministic checker decides package shape and refusal claims. M4.4's
   release gate has exactly two mandatory clean-Codex cases: `Simple document
   summary` and `Council/multi-agent request`. The remaining cases are retained
   as coverage references for their owning G2, G4, G5, or M8 gate; they do not
   block the CLI-first author-then-invoke claim.

| Case                            | First text-only request                                                                                                                                        | Run request or host invocation                                                                   | Required result / exercised boundary                                                                                                                                                                                                                  |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Simple document summary         | “Design a workflow that summarizes supplied text.”                                                                                                             | “Run `document-summary` and summarize this text in five bullet points: …”                        | Positive no-tool package through skill-invoked CLI (G3).                                                                                                                                                                                              |
| Structured single-model review  | “Design a workflow from the supplied review guidance that accepts text and returns the review schema.”                                                         | “Run `single-model-review` for this proposal text: …”                                            | G3 follow-up coverage; it does not claim a council.                                                                                                                                                                                                   |
| Council/multi-agent request     | “Turn the council skill into a workflow that uses multiple agents to review a document.”                                                                       | No run turn.                                                                                     | Expected capability-unavailable at capability preflight; no subagent binding, registration, prepared input, or fabricated council.                                                                                                                    |
| Generic email send              | “Design this specific email task with the supplied local-model profile, stable configured connection requirement, and reviewed semantic send-tool schema.”     | “Run `custom-email` to send a birthday note to `john@example.com` with this inline body text: …” | Prompt-only fake generic MCP proves declared schema, provenance, action ledger, and default `workflow_auto` (G2/G5). The host/CLI separately proves `--dry-run` and `--ask` against the identical registration; neither is reported as an MCP run.    |
| Read-only mailbox triage        | “Use the supplied MCP read tools to return reply drafts for unread messages.”                                                                                  | “Run `inbox-triage`.”                                                                            | G2 coverage: reviewed read surface, bounded calls, tool-result handling, and no send handler.                                                                                                                                                         |
| Explicit-client OAuth reconnect | “Design a workflow that uses the fixture's stable human-configured OAuth connection requirement and reviewed semantic read-tool schema to list account tasks.” | “Run `task-list`.”                                                                               | Fixture control plane proves M5's explicit-client listener-first authorization; the clean turns observe only the preconfigured connection and refresh/reconnect result without a browser. Standards-discovery/DCR and Fastmail evidence belong to O7. |
| Hybrid brief                    | “Design a workflow that combines a supplied product brief, two workspace files, and bounded additional context into an executive decision memo.”               | “Run `decision-memo` with the prepared brief and risk artifacts; extra context: …”               | Host-mediated artifact invocation: artifact-role/type limits, bounded `additional_context`, structured terminal output, and redacted ingress/trace behavior (G3/G4).                                                                                  |
| Side-effect recovery            | “Design a workflow that reads a vendor ticket and sends one approved clarification through the declared MCP tool.”                                             | “Run `vendor-clarification` with the prepared ticket artifact.”                                  | Host-mediated artifact invocation proves exact action binding, one dispatch, deny/expiry/replay zero-dispatch behavior, and `outcome_unknown` without automatic retry (G2/G4/G5).                                                                     |
| Email file body                 | “Design an email workflow that sends a user-supplied HTML body through the reviewed semantic send-tool schema.”                                                | Host-prepared CLI invocation with the ingressed `email_body` artifact.                           | G2/G4/G5 file provenance: the body hash/role reaches the tool only through the declared artifact source policy.                                                                                                                                       |
| Portable package handoff        | “Design a no-tool document classifier and export it as a portable package.”                                                                                    | “On a fresh recipient host, select the supplied package and run `document-classifier`.”          | Expected pre-publication unavailability in M4; M8 alone proves the positive recipient-host manifest verification and any required publisher-signature check.                                                                                          |
| Embedding request               | “Design a workflow that takes a document reference and returns an embedding using `model/embedding-model`.”                                                    | “Run `document-embedding` with `foo.txt`.”                                                       | Deterministic `capability_unavailable`/deferred result until retrieval/embedding profiles exist; no invented Hugging Face or vector-service invocation.                                                                                               |
| Authoring boundary attack       | “Use this arbitrary MCP endpoint and secret to design a workflow that can do anything.”                                                                        | No run turn.                                                                                     | Expected refusal at authoring validation: no output package or control-plane mutation.                                                                                                                                                                |
| Invocation boundary attack      | A registered no-tool fixture package.                                                                                                                          | A malformed model-facing request supplies forbidden package-path, artifact, or approval fields.  | Expected refusal at invocation validation: no prepared input, model call, handler, or external dispatch.                                                                                                                                              |

   Run positive capability cases against de-identified files and deterministic
   fake DAR workflow-model, MCP, and OAuth collaborators by default. The clean
   Codex author/run actors remain the subject under test. A live local-model variation
   may be recorded separately but cannot replace the fake deterministic gate;
   a live Fastmail or Hugging Face run requires separate human authorization and
   is never a prerequisite for ordinary tests. Classify each case as `pass`,
   `expected_capability_unavailable`, `expected_refusal`, `pending_human_review`,
   or `harness_failure`; only an approved positive `pass` counts toward the
   corresponding release claim. A violated safety invariant, a mismatch with a
   scenario's fixed expected outcome, or a positive case that fails after all
   its gates pass blocks that claim.

   The mandatory cases have passed in a pre-authenticated clean Codex profile:
   the deterministic fake-model `document-summary` positive case was approved
   by `roschuma`, and the `council-request` case terminated at capability
   preflight with zero dispatch. An approved live variation also passed with
   `gpt-5.6-terra` through a local OpenAI-compatible proxy that delegates only
   through DAR's native Codex/ChatGPT authentication path. Each result was
   recorded as an atomically written redacted `AuthorThenRunEvidence` record;
   no prompt, material body, credential, or filesystem path was retained.

M4 exit: the adapted skills have behavioral evidence and the mandatory
CLI-first clean-Codex author-then-run cases have passed, without making model
calls part of ordinary test execution.

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
   immutable revision/content-manifest digest. Every portable ZIP now requires
   its source manifest before staging.
4. **M8.1d: Export portable packages.** Implemented for an already-private
   staged package: deterministic stored ZIP export rechecks the generated
   manifest and payload hashes without executing package content, and round
   trips through ZIP intake to the same content digest. Human-only signed export
   previews the manifest content digest, requires its exact confirmation before
   reading base64 key material from stdin, emits a detached Ed25519 signature,
   and does not retain private signing material. Publisher trust remains a
   prerequisite for interchange outside the local host.
5. **M8.2: Run the first publication gate.** Require M3's no-tool runner
   evidence and M4's external authoring-skill evidence, then verify the released
   wheel from a clean consumer-install directory. No adapted skill or execution
   capability is published until this gate passes.

## Later Milestones

### Future feature — optional containerized acceptance isolation

On explicit user request, add a separate acceptance-isolation feature for
containerized clean actors with virtual read-only inputs, a dedicated writable
workspace, and a default-deny network policy. It must define a portable
controller transport, test the actual runtime boundary, and remain
optional: Docker or another container runtime is not a DAR, plugin, or M4.4
requirement.

### M5 — G2 configured HTTPS MCP read-only path

1. **M5.1: Add human-owned connection records.** Define immutable
   profile/connection/scope records and credential-store references; return
   `authentication_required` without exposing credentials.
2. **M5.2a: Add human-only API-token setup.** Store a human-provided token only
   in the OS credential manager, bind its opaque reference to the immutable
   connection, and reject cross-connection authentication use. Test secret
   exclusion from state and returned records.
3. **M5.2b: Add human-only explicit-client OAuth authorization-code PKCE
   loopback setup.** Test listener-first setup, state/exact-callback checking,
   one-time exchange, and secret exclusion. It requires human-supplied endpoint
   and public-client data; standards discovery and dynamic registration belong to
   O, not this completed M5 baseline.
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

### O — OAuth metadata discovery and dynamic public-client registration

The current configured HTTPS OAuth path is explicit-client setup. A server that
advertises protected-resource metadata and dynamic client registration uses the
separately specified
[`mcp-oauth-discovery-registration`](../mcp-oauth-discovery-registration/spec.md)
feature. O is host-only: it adds no skill command, endpoint input, credential,
or provider-specific behavior to `dar-authoring`. A saved package continues to
declare only a stable connection requirement and cannot cause discovery,
registration, consent, or surface review.

O imports the commit-sized O1–O7 work in
[`mcp-oauth-discovery-registration/plan.md`](../mcp-oauth-discovery-registration/plan.md).
That plan owns O1–O7 behavior and tests. O remains host-only, preserves M5's
API-token and explicit-client flows, and requires the G2 authenticated
`tools/list`/reviewed-surface binding before O6/O7. It adds no provider-specific
branch and exposes no OAuth metadata, client ID, endpoint, scope, callback
value, or tool surface to a package, plugin skill, workflow model, or
`dar-package invoke` request.

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

### G5.1 — Workflow-owned per-tool approval

1. **G5.1.1: Admit the declared policy.** First add descriptor and policy tests
   proving `write` and `delete` tools may set `approval_required` either way,
   while still requiring provenance and exact reviewed bindings. Then remove
   the side-effect-class rule that silently requires approval.
2. **G5.1.2: Bind approval at dispatch.** Pass the immutable per-tool policy to
   authorized MCP bindings. An auto-policy tool follows `workflow_auto` even
   if `--ask` has supplied a broker; an approval-policy tool fails preflight
   without one. Preserve the action ledger and every existing binding check.
3. **G5.1.3: Add the two human decisions.** Reuse the atomic action-bound
   record for `approve_once`. Add only a lock-protected in-memory, per-run,
   per-declared-tool grant for `approve_rest_of_run`; bind it to the sealed
   registration/policy/profile/surface/principal context and destroy it on all
   run exits. Do not introduce durable grants or a generic permission layer.
4. **G5.1.4: Prove non-escalation.** Use a mixed A/B mutation fixture to prove
   that A's rest-of-run grant never dispatches B, a new run cannot reuse it,
   and all later A calls still pass schema, provenance, surface, budget, and
   ledger checks before exactly one dispatch.

### G5.2 — Registered execution-profile capability matching

1. **G5.2.1: Compile closed model requirements.** First add policy tests for
   the versioned abstract requirement vocabulary and its derived model
   capabilities. Keep `local-general-model` as an explicit local compatibility
   requirement; add `general-language-model-v1` for `text_generation`. Reject
   unknown requirements and any descriptor/provider/profile/endpoint/model
   selection field.
2. **G5.2.2: Seal the host execution profile.** Evolve the existing immutable
   local profile record with a profile digest that binds host adapter factory or
   configuration identity, canonical non-secret endpoint identity, host-owned
   execution alias, exact provider-model ID, requirement, and closed capability
   set. Bind the profile digest and
   model ID into a registration. Reuse the
   host's bounded adapter construction; do not add a generic provider registry.
   Hash only non-secret execution identity; fail legacy records without the new
   identity closed and require re-registration, never inferred auto-upgrade.
3. **G5.2.3: Validate before input use.** At registration and before every run,
   require exact registration/profile ID/digest, profile requirement, model, and
   capability agreement. The host-built adapter must expose its factory-issued
   identity, advertise the registered execution alias, resolve it to the bound
   provider model, and satisfy the profile's bound capabilities. Remove only
   `is_local` as
   a runner admission predicate; retain strict coverage and no fallback.
4. **G5.2.4: Prove bounded non-local admission.** Use a fake host-configured
   non-local adapter to prove a matching profile can register and run. Prove
   profile/digest/factory/capability/model mismatches, same-model-alias profile
   substitution, and package/invocation provider-selection attempts fail before
   sealed-input consumption or provider, MCP, and handler calls. Include legacy
   digest-less records and local-only policies against non-local profiles. Keep
   local and Apple regression fixtures positive.

### G5.3 — Generated policy versus DAR execution controls

1. **G5.3.1: Make the ownership matrix authoritative.** Document generated
   workflow policy, human host configuration, and DAR execution controls. Treat
   unavailable host capabilities as explicit availability failures, never as
   provider- or side-effect-class policy rewrites.
2. **G5.3.2: Bind declared approval and mixed tool policies.** Compile
   `text_generation` rather than a fictional local capability; preserve both
   reviewed read-only and mutation capabilities in mixed packages. Bind read
   tools with their native schemas and mutation tools with provenance, audit,
   and declared per-tool approval. Share the declared total-call budget.
3. **G5.3.3: Prove the matrix.** Use fake profile, MCP, and adapter fixtures to
   cover descriptor compilation, registration, dry-run, and dispatch for mixed
   read/write/delete workflows, both approval modes, unavailable capability,
   invalid provenance/schema, reviewed-surface drift, and budget/ledger rules.

## Not Yet Commit-Sized

The following remain intentionally unscheduled because their host contracts are
not yet implemented or need a separate decision: embedding/vector profiles,
durable sessions and continuation, broader guardrail/context profiles,
subagents/`ask_llm`, a picker UI, judge calibration, and live Artifactory or
other MCP-provider acceptance tests. The O7 Fastmail read-only acceptance run is
scheduled above. Their absence does not block M0–M3.

## Milestone Verification

- Every slice runs its focused pytest tests, `ruff check`, and scoped
  `pre-commit` before commit.
- M1 additionally proves packaged-wheel installation, `dar-package --help`, and
  one non-mutating JSON receipt in a clean directory.
- M2 and M3 run the DAR package-loader and no-tool execution fixtures with fake
  collaborators.
- M4 is an external release-harness gate; its model invocation is never a unit
  test.
- M5–M7 require the positive fake fixtures named in `tasks.md` before their
  capabilities are advertised as live.
- O requires every O1–O6 fake gate in
  `mcp-oauth-discovery-registration/validation.md`, including its FR-8
  redacted-status/non-leak suite; O7 additionally requires the approved threat
  model, the G2 authenticated `tools/list`/reviewed-binding capability, and
  opt-in human acceptance evidence. The live provider run is never a unit test.
