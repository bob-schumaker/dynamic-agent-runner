# Provider-Backed Context Compaction Tasks

Status: implemented first slice; provider transport remains deferred

## Slice 0 — Contract and RED Tests

- [x] T0.1 Add RED import and shape tests for typed provider-compaction request,
      result, and caller-owned protocol exports.
- [x] T0.2 Add RED validation tests for provider policy, required capability,
      fallback, bounded replacement count, and unsupported combinations.
- [x] T0.3 Add RED executor tests for pre-turn and overflow-retry success,
      missing collaborator/capability, malformed/protected-boundary replacement,
      `basic` fallback, `error` failure, and redacted trace metadata.
- [ ] T0.4 Add RED capability-report tests for disabled, metadata-only, missing
      collaborator, missing capability, fallback, and live provider compaction.

## Slice 1 — Typed Boundary and Policy

- [x] T1.1 Add `context_compaction.py` public contract and package-root exports.
- [x] T1.2 Thread the collaborator through direct/context execution without
      weakening context keyword exclusivity or existing callback behavior.
- [x] T1.3 Validate the provider-only policy shape and reject unsupported
      fallback or mid-turn policy claims.

## Slice 2 — Runtime Enforcement

- [x] T2.1 Invoke a capable collaborator at thresholded pre-turn preparation;
      validate and install only an eligible replacement.
- [x] T2.2 Reuse the typed boundary for one-shot overflow retry without a
      second retry loop or raw provider trace payload.
- [x] T2.3 Apply deterministic `basic` fallback or fail-closed `error`, emit
      redacted metadata, and report capability status.

## Slice 3 — Completion Evidence

- [x] T3.1 Run focused tests, Ruff, full pytest, package build, and docs build.
- [x] T3.2 Update `spec.md`, `validation.md`, and `specs/README.md` only with
      observed implementation evidence; keep deferred phases explicit.
