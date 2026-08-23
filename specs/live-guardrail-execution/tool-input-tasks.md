# Tool-Input Guardrail V2 Tasks

Status: implementation-ready; no V2 runtime changes completed

## Slice 0 — Tests and Contract

- [ ] T0.1 [tests] Add RED direct and model-loop tests for declared tool-input
      guardrail pass, abort, missing-adapter, result-mismatch, and ordered
      multiple-declaration behavior.
- [ ] T0.2 [tests] Assert abort emits redacted guardrail events and invokes no
      approval, hook, retry, registry handler, state result, or node output.
  - Verify the handler subject contains only the copied, validated fields named
      in `spec.md`; no raw provider or interpreter object is exposed.

Start this slice by writing and running the focused RED tests. Do not begin
implementation until those failures distinguish the absent V2 boundary from the
implemented V1 input-guardrail baseline.

## Slice 1 — Coordinator Integration

- [ ] T1.1 [implementation] Thread caller-supplied guardrail registry through
      the internal coordinator without widening package-root APIs.
- [ ] T1.2 [implementation] Execute only validated tool-input pass/abort
      decisions before approval; fail closed on missing/mismatched/error
      results; and preserve unguarded and pass-path behavior.

## Slice 2 — Completion Evidence

- [ ] T2.1 [validation] Run focused guardrail, executor, tracing, capability,
      import, full-suite, lint, package-build, and docs-build gates.
- [ ] T2.2 [docs] Record observed V2 behavior and leave deferred phases
      explicitly deferred.
