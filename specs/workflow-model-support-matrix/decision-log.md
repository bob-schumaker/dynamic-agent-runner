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
- 2026-09-13 — Fastmail probes must resolve a registered workflow ID and derive
  the sealed package/material facts from the configured host. — The verified
  owner-local registration maps `fastmail-inbox-triage-qwen-v4` to package
  `fastmail-inbox-triage-qwen`; treating one CLI value as both identities makes
  the current live command unsatisfiable. State-root paths, targets,
  credentials, mailbox data, and session transcripts remain unrecorded.
- 2026-09-13 — Static registration inspection and dynamic reviewed-surface
  validation remain separate. — `inspect_saved_workflow` returns registration,
  compiled policy, and model profile without composing an MCP client; the
  configured host must therefore revalidate its reviewed MCP surface before
  tool dispatch rather than adding a duplicate probe validator.
- 2026-09-13 — A stale registered policy is a manual reconciliation gate, not a
  reason to weaken probe admission. — WMS5.2 read-only inspection returned
  `saved package policy does not match` for the owner-local Fastmail workflow;
  WMS5.4 must re-establish the same package/revision/binding relationship before
  any fresh live authorization is used.

## Rejected Options

- Treat every unsupported profile as a test failure — rejected because it would
  conflate intentional capability boundaries with regressions.
- Reuse a Fastmail Qwen receipt for arbitrary models — rejected because sealed
  model material and package identity are part of the evidence claim.

## Drift Events

- 2026-09-13 — Reconciled stale draft/open status and MLE8 evidence claims.
  — WMS1--WMS4 are complete, and the MLE8 package, fixture, Darwin receipt,
  and non-transferable support row are recorded alongside MLE6 and MLE7.
- 2026-09-13 — Verified that the owner-local Fastmail host configuration remains
  available; no configuration was lost. — WMS5 tracks the command-interface
  defect rather than treating the absent live receipt as missing configuration.

## Gate History

- Discovery gate: waived by explicit request to create the artifact set.
- Spec gate: waived by explicit request to create the artifact set.
- Plan gate: waived by explicit request to create the artifact set.
- Task gate: waived by explicit request to create the artifact set.
- Validation gate: passed; WMS1--WMS4 focused and full regression, lint, docs,
  and changed-file checks are recorded in `validation.md`.
