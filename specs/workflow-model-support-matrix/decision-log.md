# Workflow Model Support Matrix Decision Log

## Decisions

- 2026-09-13 — Model support is represented as a capability-gated cell rather
  than a Cartesian product of provider names. — Existing adapters, tool paths,
  embedding ABIs, hosts, and sealed materials are not interchangeable.
- 2026-09-13 — Fastmail and embedding workflow families remain one planning
  component. — They share support classification, receipt, and non-transferable
  material-evidence rules.
- 2026-09-13 — Fastmail live probes remain separate human-authorized operations.
  — Ordinary tests must remain offline and retain no mailbox data.
- 2026-09-13 — Floorplan SVG, structured output after tool use, stateful
  context, and tool-pack composition join this matrix as profiles rather than
  separate feature specs. — They share the same capability classification and
  redacted receipt contract.
- 2026-09-13 — Proposed or intentionally deferred runtime features are explicit
  exclusions, not empty matrix rows. — A row requires an implemented owning
  contract before it can be classified honestly.

## Rejected Options

- Treat every unsupported profile as a test failure — rejected because it would
  conflate intentional capability boundaries with regressions.
- Reuse a Fastmail Qwen receipt for arbitrary models — rejected because sealed
  model material and package identity are part of the evidence claim.

## Drift Events

- None.

## Gate History

- Discovery gate: waived by explicit request to create the artifact set.
- Spec gate: waived by explicit request to create the artifact set.
- Plan gate: waived by explicit request to create the artifact set.
- Task gate: waived by explicit request to create the artifact set.
- Validation gate: not applicable; no implementation was authorized.
