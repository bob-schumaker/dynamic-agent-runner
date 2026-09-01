# Agent-Engineering Plugin Migration Record

## Metadata

- Status: Complete; commit authorized
- Owner: dynamic-agent-runner
- Governing transfer plan: `../ai-environment-roschuma/work-items/plans/dar-plugin-skill-ownership-migration-plan.md`
- Successor plugin: `.agents/plugins/agent-engineering`

## Delivery Record

This record is the DAR-side evidence for the single cross-repository transfer.
It is not an additional implementation plan or delivery gate.

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

## Completion Evidence

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
- Commit authorization: granted for this completed transfer.
