# Agent-Engineering Plugin Migration Tasks

## Status

The cross-repository transfer is complete. The remaining task is a full
successor clean-Codex author-then-run acceptance suite covering every
`supported`, `conditional`, and `deferred` authored-workflow capability. It
must not revive the retired `dar-authoring` plugin or create a generic
plugin-acceptance framework.

## Successor Clean-Codex Acceptance

- [x] RED: add `tests/fixtures/m4-4-successor-coverage.json` and scenario-
      contract tests. Its versioned entries map every matrix capability ID to
      one or more scenario IDs, `expected_status` (`pass`,
      `expected_capability_unavailable`, or `expected_refusal`), configured
      fixture IDs, missing-fixture IDs, and expected terminal status. Configured
      fixture IDs for a positive entry equal the referenced scenario's
      `required_host_fixtures`; a missing-fixture negative entry references a
      distinct immutable scenario contract and omits exactly one prerequisite.
      Require positive coverage for `supported`, positive with the listed fixture
      and unavailable without it for `conditional`, and unavailable/refusal for
      `deferred`. Bind every entry to the scenario's gates, fixture set, terminal
      phase, and its capability-specific assertions; a label alone is not
      coverage. Make coverage checking fail for an unmapped or unknown ID, a
      status or terminal-phase mismatch, an under-gated capability, a scenario
      not represented in the manifest, or a missing required fixture. Allow one
      scenario to cover multiple related capability IDs.
- [x] GREEN: add the complete successor scenario corpus and coverage checker.
      Each `supported` capability has at least one deterministic, fake-backed
      full end-to-end case; each `conditional` capability has both configured
      positive and missing-fixture negative coverage; each `deferred` capability
      has its declared negative case. Preserve all 13 original M4.4 scenario
      contracts as the minimum regression corpus, including `document-summary-v1`
      and `council-request-v1`. Cover the valid `input` and `tool_input`
      guardrail phases and their missing-registry-fixture boundaries. Keep
      expansion capability-oriented, not combinatorial across every option
      combination.
- [x] RED: establish the direct-skill baseline harness: a temporary marketplace
      exposes only `agent-engineering`, the visible `agent-development` skill,
      and its DAR runtime profile, with no plugin MCP or broker configuration.
      Verify that legacy plugin/skill identities are rejected, and that a copied
      marketplace plugin declaring an MCP surface or broker artifact is rejected
      rather than silently omitted. This is baseline-only evidence, not routed
      successor acceptance.
- [x] GREEN: migrate the harness's copied-plugin, skill-path, and prompt
      construction logic from `dar-authoring` to `agent-engineering`. Preserve
      the clean process, scrubbed environment, declared fixture inputs, and
      redacted receipt parsing. Stage the DAR wheel only in the test-owned
      environment and expose `dar-package` on `PATH`; neither its wheel nor its
      physical path may appear in a model-visible prompt. Do not widen DAR's CLI
      or runtime surface. This is direct-skill baseline harness work; routed
      successor staging is specified below.
- [x] RED: add deterministic tests for the successor author prompt. It must
      explicitly target DAR and provide only the declared fixture inputs. It
      must not name `dar-authoring`, copy the DAR runtime profile's command
      recipe, or supply a package path, broker, MCP configuration, or source
      handle. A bare DAR mention must remain outside the DAR-profile path.
- [x] RED/GREEN: make manifest admission fail when any member of the checked-in
      original 13-scenario ID set is missing or replaced; require that invariant
      for both the direct timing baseline and generated-root replay.
- [ ] Capture and freeze the complete-manifest direct-skill timing baseline and
      its plugin-tree digest before router-source restructuring. Retain it only
      as test-owned comparison collateral, never as a successor marketplace
      source.
- [ ] RED/GREEN: define the canonical router-packaging source layout. Keep the
      private `agent-engineering-direct` build-input manifest and icon collateral
      source-owned; make the `agent-development`
      router member instruction-only; move general agent-development and DAR
      workflow-authoring guidance into named private modules; and classify every
      remaining canonical artifact as a declared payload or explicit exclusion.
      Test that no support subtree is visible beneath the router member.
- [ ] RED/GREEN: add a native-routed packager invocation and focused
      generated-tree contract tests. It must retain the canonical public plugin
      identity, version, author, description, interface metadata, branding paths,
      marketplace selector, and `agent-development` identifier; only internal
      routing topology may differ. Assert exactly one visible router `SKILL.md`,
      private module instructions below `references/modules/`, complete
      source-map coverage, declared payload ownership, and deterministic payload,
      release-metadata, and source-map proof artifacts. The source manifest is
      an internal `agent-engineering-direct` packager input; only the generated
      manifest is the public `agent-engineering` marketplace contract.
- [ ] RED/GREEN: plan then apply the router packaging into a disposable
      generated root without rewriting, publishing, installing, or cleaning the
      canonical source tree. Test plan/apply receipt agreement, public-manifest
      and icon preservation, and rejection of undeclared support-file ownership.
- [ ] RED/GREEN: extend the clean-Codex harness to stage only the generated
      routed root. Statically prove that the router is the sole initial visible
      skill surface, then prove DAR-targeted bounded author/finalize/invoke
      behavior through packages, receipts, and traces without claiming a private
      module-load event.
- [ ] GREEN: prove that the successor-only marketplace plus the minimal
      DAR-targeted prompt, using the generated routed root, produces the bounded
      package/finalization route and preserves refusal boundaries. Treat
      generated package and receipt validation as evidence; do not claim insight
      into model reasoning.
- [x] RED/GREEN: make the external command coverage-manifest-first. Add focused
      tests that load the versioned successor coverage manifest, derive its
      complete scenario set, reject a scenario-only or partial-manifest request,
      and retain the checked-in scenario contract and capability assertions for
      each replayed entry. Add a versioned external scenario-plan fixture that
      maps each unique scenario ID to its package name, workflow ID, author
      request, run request, and declared fixture set; reject unknown, missing,
      duplicate, or fixture-mismatched plan entries before launching Codex.
- [ ] RED/GREEN: add a deterministic external-harness controller for the
      complete manifest. It owns fake model, MCP/tool, approval, ingress,
      guardrail, and capability collaborators and passes only declared fixture
      inputs to each scenario. Unit tests must prove that this controller makes
      no OpenAI, MCP, credential, or other network call. Controller preflight
      alone is insufficient: the actor-side authoring and invocation commands
      must use the controller-provisioned collaborators rather than the
      default `dar-package` state-root path, which has no MCP, approval,
      ingress, or guardrail collaborator injection. Construct the reviewed MCP
      client through a narrow controller-only host-construction seam with a
      deterministic local transport; do not monkeypatch the external command
      or expose transport configuration to either actor. Configure trusted
      ingress from a controller-private input root and pass only the resulting
      opaque artifact IDs through invocation. The fixture inventory is not
      acceptance evidence by itself: the deterministic model must emit the
      scenario-bound tool/continuation sequence needed to drive each supported
      fixture through the controller, not one generic text or tool response.
- [ ] RED/GREEN: add and pass fixture-backed contract tests for two separately
      launched clean Codex actors against the generated routed root:
      author/finalize, then saved-package invoke.
      The second actor receives only the finalized package name and text request;
      it has a separate workspace and cannot select, register, recreate, or
      configure the package, access author state, or receive controller
      credentials or tool roots. The controller provides narrow authoring and
      invoke-only launchers that mediate private state without exposing a
      state-root path or state-root environment variable to either actor. The
      test must launch both actor commands as subprocesses and prove the
      registered invocation receives only the finalized package name, text,
      and controller-injected opaque fixture artifacts.
- [x] RED/GREEN: add and pass a deterministic, fake-backed scenario runner for
      every successor scenario. It must execute each positive case through
      authoring, finalization, staging/registration, preparation, and invocation;
      each negative case must prove its declared terminal boundary and zero
      downstream registration, preparation, model execution, tool dispatch, or
      side effect where required. It makes no live Codex, OpenAI, MCP, or other
      network call. `document-summary` and `council-request` remain mandatory
      regression cases.
- [ ] RED/GREEN: add per-scenario redacted evidence tests and writer support.
      Each record binds canonical/generated plugin identities, generated-manifest
      and marketplace digests, router/payload/source-map/release receipt digests,
      scenario/prompt/harness/controller versions,
      package/catalog/registration/preparation linkage, terminal status, and
      dispatch count; it rejects prompt bodies, material content, credentials,
      tool roots, and physical paths. Write one record per unique scenario ID
      into a fresh evidence directory and a versioned aggregate manifest that
      binds coverage/scenario-plan digests plus every record digest and status;
      reject missing, duplicate, or unknown records.
- [ ] RED/GREEN: add the separately authorized external clean-Codex acceptance
      command that stages only the generated root and composes manifest
      admission, deterministic controller, two isolated actors, ordinary-runner
      assertions, and redacted evidence. This command is the live-Codex
      successor-acceptance gate; ordinary tests do not invoke it.
- [ ] RED/GREEN: preserve complete-manifest progress when an individual live
      Codex actor fails or times out. Record its actual failure phase and allow
      that terminal record through scenario validation; retain exact planned
      terminal-phase matching for passing and expected-unavailable records.
- [ ] Replay the complete manifest against the generated routed root and compare
      it with the frozen direct-skill baseline. Use identical coverage/scenario-
      plan digests, prompts, fixtures, controller, actor/Codex/model
      configuration, and timeout; bind the frozen input digest; record redacted
      aggregate actor durations and comparison provenance, excluding generation
      and marketplace staging. Do not use the router result to authorize source
      cleanup or plugin publication.
- [ ] Record reviewed redacted successor evidence from one complete external
      generated-root manifest replay. Review aggregate completeness, public
      interface parity, and router/payload/source-map/release proof receipts;
      do not mark acceptance until that review is approved.
- [ ] Update this record, `specs/README.md`, and the historical v1 acceptance
      wording only after the external successor run is reviewed and accepted.

## Validation

- Focused unit tests are written first and must fail before each corresponding
  harness change.
- Ordinary unit tests use deterministic fakes and make no live Codex, OpenAI,
  MCP, or other network calls.
- The external clean-Codex run is a separate, explicitly authorized acceptance
  command; it supplements rather than replaces the fake-backed test suite.
