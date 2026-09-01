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
- [x] RED: update the clean-Codex harness unit tests to require a temporary
      marketplace exposing only `agent-engineering`, the visible
      `agent-development` skill and DAR runtime profile, and no plugin MCP or
      broker configuration. Verify that legacy plugin/skill identities are
      rejected, and that a copied marketplace plugin declaring an MCP surface or
      broker artifact is rejected rather than silently omitted.
- [x] GREEN: migrate the harness's copied-plugin, skill-path, and prompt
      construction logic from `dar-authoring` to `agent-engineering`. Preserve
      the clean process, scrubbed environment, declared fixture inputs, and
      redacted receipt parsing. Stage the DAR wheel only in the test-owned
      environment and expose `dar-package` on `PATH`; neither its wheel nor its
      physical path may appear in a model-visible prompt. Do not widen DAR's CLI
      or runtime surface.
- [x] RED: add deterministic tests for the successor author prompt. It must
      explicitly target DAR and provide only the declared fixture inputs. It
      must not name `dar-authoring`, copy the DAR runtime profile's command
      recipe, or supply a package path, broker, MCP configuration, or source
      handle. A bare DAR mention must remain outside the DAR-profile path.
- [ ] GREEN: prove that the successor-only marketplace plus the minimal
      DAR-targeted prompt produces the bounded package/finalization route and
      preserves refusal boundaries. Treat generated package and receipt
      validation as evidence; do not claim insight into model reasoning.
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
      no OpenAI, MCP, credential, or other network call.
- [ ] RED/GREEN: add and pass fixture-backed contract tests for two separately
      launched clean Codex actors: author/finalize, then saved-package invoke.
      The second actor receives only the finalized package name and text request;
      it has a separate workspace and cannot select, register, recreate, or
      configure the package, access author state, or receive controller
      credentials or tool roots. The controller provides narrow authoring and
      invoke-only launchers that mediate private state without exposing a
      state-root path or state-root environment variable to either actor.
- [x] RED/GREEN: add and pass a deterministic, fake-backed scenario runner for
      every successor scenario. It must execute each positive case through
      authoring, finalization, staging/registration, preparation, and invocation;
      each negative case must prove its declared terminal boundary and zero
      downstream registration, preparation, model execution, tool dispatch, or
      side effect where required. It makes no live Codex, OpenAI, MCP, or other
      network call. `document-summary` and `council-request` remain mandatory
      regression cases.
- [ ] RED/GREEN: add per-scenario redacted evidence tests and writer support.
      Each record binds plugin/skill identities, marketplace digest,
      scenario/prompt/harness versions, package/catalog/registration/preparation
      linkage, terminal status, and dispatch count; it rejects prompt bodies,
      material content, credentials, tool roots, and physical paths. Write one
      record per unique scenario ID into a fresh evidence directory and a
      versioned aggregate manifest that binds coverage/scenario-plan digests
      plus every record digest and status; reject missing, duplicate, or unknown
      records.
- [ ] RED/GREEN: add the separately authorized external clean-Codex acceptance
      command that composes the manifest admission, deterministic controller,
      two isolated actors, ordinary-runner assertions, and redacted evidence.
      This command is the live-Codex successor-acceptance gate; ordinary tests
      do not invoke it.
- [ ] Record reviewed redacted successor evidence from one complete external
      manifest replay. Do not mark acceptance until that review is approved.
- [ ] Update this record, `specs/README.md`, and the historical v1 acceptance
      wording only after the external successor run is reviewed and accepted.

## Validation

- Focused unit tests are written first and must fail before each corresponding
  harness change.
- Ordinary unit tests use deterministic fakes and make no live Codex, OpenAI,
  MCP, or other network calls.
- The external clean-Codex run is a separate, explicitly authorized acceptance
  command; it supplements rather than replaces the fake-backed test suite.
