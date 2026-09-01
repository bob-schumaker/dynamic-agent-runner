# Agent-Engineering Plugin Migration Tasks

## Status

The cross-repository transfer is complete. The remaining task is a full
successor clean-Codex author-then-run acceptance suite covering every supported
authored-workflow capability. It must not revive the retired `dar-authoring`
plugin or create a generic plugin-acceptance framework.

## Successor Clean-Codex Acceptance

- [ ] RED: add `tests/fixtures/m4-4-successor-coverage.json` and scenario-
      contract tests. Its versioned entries map every matrix capability ID to
      one or more scenario IDs, `expected_status` (`pass`,
      `expected_capability_unavailable`, or `expected_refusal`), configured
      fixture IDs, missing-fixture IDs, and expected terminal status. Configured
      fixture IDs equal the referenced scenario's `required_host_fixtures`; a
      missing-fixture entry omits one of those IDs. Require positive coverage for
      `supported`, positive with the listed fixture and unavailable without it
      for `conditional`, and unavailable/refusal for `deferred`. Make coverage
      checking fail for an unmapped or unknown ID, a status mismatch, a scenario
      not represented in the manifest, or a missing required fixture. Allow one
      scenario to cover multiple related capability IDs.
- [ ] GREEN: add the complete successor scenario corpus and coverage checker.
      Each `supported` capability has at least one deterministic, fake-backed
      full end-to-end case; each `conditional` capability has both configured
      positive and missing-fixture negative coverage; each `deferred` capability
      has its declared negative case. Preserve all 13 original M4.4 scenario
      contracts as the minimum regression corpus, including `document-summary-v1`
      and `council-request-v1`. Keep expansion capability-oriented, not
      combinatorial across every option combination.
- [ ] RED: update the clean-Codex harness unit tests to require a temporary
      marketplace exposing only `agent-engineering`, the visible
      `agent-development` skill, and no plugin MCP or broker configuration.
      Verify that legacy plugin/skill identities are rejected.
- [ ] GREEN: migrate the harness's copied-plugin, skill-path, and prompt
      construction logic from `dar-authoring` to `agent-engineering`. Preserve
      the clean process, scrubbed environment, declared fixture inputs, and
      redacted receipt parsing. Stage the DAR wheel only in the test-owned
      environment and expose `dar-package` on `PATH`; neither its wheel nor its
      physical path may appear in a model-visible prompt. Do not widen DAR's CLI
      or runtime surface.
- [ ] RED: add deterministic tests for the successor author prompt. It must
      explicitly target DAR and provide only the declared fixture inputs. It
      must not name `dar-authoring`, copy the DAR runtime profile's command
      recipe, or supply a package path, broker, MCP configuration, or source
      handle. A bare DAR mention must remain outside the DAR-profile path.
- [ ] GREEN: prove that the successor-only marketplace plus the minimal
      DAR-targeted prompt produces the bounded package/finalization route and
      preserves refusal boundaries. Treat generated package and receipt
      validation as evidence; do not claim insight into model reasoning.
- [ ] RED/GREEN: add and pass fixture-backed contract tests for two separately
      launched clean Codex actors: author/finalize, then saved-package invoke.
      The second actor receives only the finalized package name and text request;
      it cannot select, register, recreate, or configure the package.
- [ ] RED/GREEN: run every successor scenario through the external acceptance
      harness. Positive scenarios must author, finalize, stage/register, prepare,
      and invoke their workflows through deterministic fake host collaborators.
      Negative scenarios must prove their declared terminal boundary and zero
      downstream registration, preparation, model execution, tool dispatch, or
      side effect where required. `document-summary` and `council-request`
      remain mandatory regression cases.
- [ ] Record redacted successor evidence that binds plugin/skill identities,
      marketplace manifest digest, scenario/prompt/harness versions,
      package/catalog/registration/preparation linkage, terminal status, and
      dispatch count. Retain no prompt bodies, material content, credentials,
      or physical paths.
- [ ] Update this record, `specs/README.md`, and the historical v1 acceptance
      wording only after the external successor run is reviewed and accepted.

## Validation

- Focused unit tests are written first and must fail before each corresponding
  harness change.
- Ordinary unit tests use deterministic fakes and make no live Codex, OpenAI,
  MCP, or other network calls.
- The external clean-Codex run is a separate, explicitly authorized acceptance
  command; it supplements rather than replaces the fake-backed test suite.
