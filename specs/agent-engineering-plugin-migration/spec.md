# Agent-Engineering Plugin Migration Record

## Metadata

- Status: Transfer complete; successor clean-Codex acceptance pending
- Owner: dynamic-agent-runner
- Governing transfer plan: `../ai-environment-roschuma/work-items/plans/dar-plugin-skill-ownership-migration-plan.md`
- Successor plugin: `.agents/plugins/agent-engineering`
- Task breakdown: `tasks.md`

## Delivery Record

This record is the DAR-side evidence for the single cross-repository transfer
and its remaining successor-acceptance gate. It does not authorize a generic
plugin-acceptance framework or DAR runtime changes.

- Source corpus revision: `6d43f44568dd82b778668f9392148083283d5676`
- DAR baseline revision: `1212667975af529a57b19604af13ed57ec0a0c9a`
- Marketplace: `dynamic-agent-runner` / `Dynamic Agent Runner`
- Runtime profile: retained as supplemental guidance under
  `references/dar-runtime-profile.md`
- Legacy disposition: the former `dar-authoring` plugin moved to
  `legacy-dar-authoring/` as historical migration evidence. Its implemented
  host/runtime contract is retained as the live
  [`authored-workflow-runtime-v1`](../authored-workflow-runtime-v1/spec.md)
  capability record; the marketplace exposes only the successor.

## Completed Transfer Evidence

- Delivered plugin: `agent-engineering` `0.1.0`
- Successor validation:
  - `poetry run python <plugin-creator>/scripts/validate_plugin.py
    .agents/plugins/agent-engineering` — passed
  - `poetry run pytest -q` — 1637 passed, 1 skipped, 7 deselected; seven
    existing unknown-mark warnings
  - `poetry run ruff check tests/test_agent_engineering_plugin.py
    tests/test_dar_authoring_live_capability_fixtures.py` — passed
- Runtime specification disposition: retained under
  [`authored-workflow-runtime-v1`](../authored-workflow-runtime-v1/spec.md) as
  the live v1 capability record; plugin-migration indexes point to this record.
- Commit authorization: granted for the completed transfer.

## Successor Clean-Codex Acceptance

The retired `dar-authoring` M4.4 harness proves the former plugin's
CLI-first author-then-run contract. It does not prove that a clean Codex
process can discover and follow the successor `agent-engineering` skill.

The migration is complete only when the successor has full bounded
end-to-end acceptance evidence. The test corpus must cover every `supported`
or `conditional` capability in
[`authored-workflow-runtime-v1`](../authored-workflow-runtime-v1/m4-4-workflow-capability-matrix.md)
with at least one clean-Codex author-then-run scenario. Each deferred capability
must have a clean-Codex scenario that reaches its declared refusal or
`capability_unavailable` boundary without fabricating a positive workflow.

Each scenario is a full end-to-end chain:

1. A clean Codex authoring process receives only a text request that explicitly
   targets DAR and the declared fixture inputs. Its temporary marketplace exposes
   only `agent-engineering`, which supplies `agent-development` and its DAR
   runtime profile; the prompt must not name the retired plugin or embed the
   profile's CLI recipe. The harness may stage DAR's wheel in a test-scoped
   environment and expose its `dar-package` console script on `PATH`, but that
   wheel, path, and installation mechanism are not model-visible inputs.
2. A separate clean Codex invocation receives only the finalized saved package
   name and text run request. It must use `dar-package invoke`; it cannot select
   a package, register a revision, configure a profile or connection, or access
   the first process's state.
3. The harness verifies the generated package, finalization receipt, staged
   catalog revision, registration/preparation linkage, invocation receipt, and
   tool/approval traces against the checked-in scenario contract. Success is
   not inferred from model text or a claimed skill invocation.

The capability matrix assigns a stable ID and support status to each row. The
checked-in `tests/fixtures/m4-4-successor-coverage.json` manifest has a version
and, for every matrix ID, one or more entries containing the scenario ID,
`expected_status` (`pass`, `expected_capability_unavailable`, or
`expected_refusal`), configured fixture IDs, missing-fixture IDs, and expected
terminal status. A configured positive entry's fixture IDs must equal the
referenced scenario's `required_host_fixtures`; a missing-fixture negative entry
must point to a distinct immutable scenario contract and omit exactly one
prerequisite. Each entry binds the capability to its scenario's required gates,
fixture set, terminal phase, and capability-specific assertions; a capability
label alone is not evidence. The scenario checker must fail when a supported row
has no positive end-to-end scenario, a conditional row lacks configured positive
or missing-fixture negative coverage, a deferred row is treated as positive, an
entry is under-gated or mismatches its terminal phase, or a scenario claims a
capability absent from the matrix. Guardrails require configured `input` and
`tool_input` phase coverage and their missing-fixture boundaries.

The original 13 M4.4 scenario contracts remain the regression minimum,
including `document-summary-v1` as a positive case and `council-request-v1` as
an unavailable case; successor coverage may add scenarios but may not replace
or reduce that baseline.

The harness must expose only `agent-engineering` in its temporary marketplace.
It must reject the retired plugin name, legacy skill paths, plugin-provided MCP
or broker configuration, inherited model credentials, and undeclared package,
state, credential, or tool roots. It may use a test-scoped clean Codex
authentication source outside model-visible inputs, but live model calls remain
outside ordinary unit tests.

The acceptance record must bind the successor plugin and skill-bundle identities,
marketplace manifest digest, scenario/prompt/harness versions, final package
digest, staged catalog revision, registration/preparation linkage, terminal
result, and dispatch count without persisting prompt bodies, material content,
credentials, or physical paths.

This proves the externally observable contract of a clean successor-only Codex
environment; it does not claim access to unobservable model reasoning or a
private “skill loaded” event.

Ordinary tests run the full scenario lifecycle through deterministic fake model,
tool, connection, approval, and host collaborators for every manifest entry;
they make no network or live-Codex call. A separately authorized external
clean-Codex command replays the complete versioned manifest with the same fake
host collaborators and two clean actors. It rejects partial-manifest runs and
records only the redacted acceptance evidence described above.

Until this gate passes, `agent-engineering` is the only marketplace successor,
but the migration record must not claim successor clean-Codex author-then-run
acceptance.
