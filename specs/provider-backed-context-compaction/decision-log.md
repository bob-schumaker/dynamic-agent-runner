# Provider-Backed Context Compaction Decisions

## D1 — First-slice phase boundary

- Status: resolved for implementation
- Decision: support thresholded pre-turn preparation and one-shot overflow
  retry only; defer mid-turn and iterative tool-loop compaction.
- Rationale: current prepare and retry seams are explicit and fake-testable,
  while a tool-call/result pair needs additional transcript safety rules.

## D2 — Collaborator ownership and shape

- Status: resolved for implementation
- Decision: use a new typed, caller-owned synchronous provider-compactor
  contract rather than the untyped `ContextCompactor` callback or provider
  adapter transport.
- Rationale: synchronous preparation is an existing public seam; typed request,
  result, capability, and replacement invariants prevent an escape hatch.

## D3 — Failure policy

- Status: resolved for implementation
- Decision: first-slice fallback is deterministic `basic` or fail-closed
  `error`; model-summary fallback is excluded.
- Rationale: the existing model-summary path has separate collaborator and
  policy semantics, so combining it would make provider failure ambiguous.

## D4 — Window identity

- Status: resolved for implementation
- Decision: DAR emits a generated compaction-window id and treats any provider
  id as redacted provenance metadata only.
- Rationale: provider ids are neither portable nor safe trace identifiers.
