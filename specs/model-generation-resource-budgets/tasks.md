# Model Generation Resource Budgets Tasks

## Status

Ready for implementation. Runtime changes remain gated by the RED-first tasks
below; no implementation is complete yet.

## S1 — Canonical Contract and Admission

- [ ] T1.1 [tests, RED] Add fake-only execution-descriptor ABI and resolver
  vectors for the exact seven-field immutable `generation_budget` record:
  positive integers, Boolean rejection, zero only for `max_continuations`, no
  aliases or extra fields, canonical material-lock binding, and fieldwise
  minimum resolution across every declared, material/profile, runner, host,
  and enclosing sealed-artifact source.
- [ ] T1.2 [implementation] Add the immutable budget and host resolver at the
  generic model-execution boundary. Resolve the minimum of sealed declaration,
  material/profile limit, receiving-runner capability, host ceiling, and any
  enclosing sealed-artifact runtime/memory cap; do not add domain paging
  semantics.
- [ ] T1.3 [tests, GREEN] Prove missing/incompatible runner capability and
  invalid/unavailable budget produce the exact
  `generation_budget_invalid`/`generation_budget_unavailable` classifications.
  Prove legacy request fields can only reduce per-fragment/continuation limits,
  cannot alter any other dimension, and cannot bypass any effective limit.

## S2 — Runtime Enforcement

- [ ] T2.1 [tests, RED] Add fake built-in and receiver-installed runner tests
  that measure packed input plus requested output against effective and
  runner-supported context, reduce a fragment to remaining aggregate-token
  allowance, stop continuation when its remaining budget cannot admit a
  fragment including for insufficient remaining deadline before backend
  dispatch, and reject an oversized assembled UTF-8 candidate before terminal
  processing.
- [ ] T2.2 [implementation] Enforce canonical budgets around every generation
  fragment; dispose of partial candidates and clear sealed, packed, and
  request-scoped generation/KV-cache state on every failure, cancellation, or
  timeout.
- [ ] T2.3 [tests, GREEN] Rerun the S2 RED vectors and prove raw continuation
  rejects after actual packed-context measurement but before backend dispatch
  when over its effective ceiling, does not silently compress history, and never
  routes partial output to terminal processing.

## S3 — Memory Reservation and Lifecycle

- [ ] T3.1 [tests, RED] Define fake `MemoryReservationProvider` cases. Prove it
  receives only the declared
  material-lock/runner identities, selected execution device, context and
  requested-token bounds, memory ceiling, and deadline; prove unavailable and
  excessive reservations fail with
  `generation_memory_budget_unavailable`, while every acquired reservation is
  released exactly once.
- [ ] T3.2 [implementation] Add receiver-owned reservation admission and
  cleanup with the selected execution device; reject a selected runner that
  cannot honor a memory-bounded request.
- [ ] T3.3 [tests, RED] Add fake cancellation and deadline tests for a
  cancellation-capable runner, a terminable isolated worker, a
  noninterruptible runner, and late output. Prove only the first two may run,
  the deadline begins before invocation-scoped model work, timeout/late output
  is discarded, request-scoped cleanup is recorded before reservation release
  on every terminal path, and the noninterruptible runner is unavailable.
- [ ] T3.4 [implementation] Start the deadline before invocation-scoped model
  work, propagate cancellation or terminate the isolated worker, and classify
  a noninterruptible runner as unavailable; record cleanup before releasing a
  reservation.
- [ ] T3.5 [tests, RED] Add fake debug and normal-run telemetry vectors for
  authorized retention, required per-fragment facts, aggregate-only normal
  results, and prohibited-content redaction.
- [ ] T3.6 [implementation] Add the authorized-debug retention gate and
  redacted telemetry/result shaping without exposing model content or host
  internals.
- [ ] T3.7 [tests, GREEN] Rerun every S3 RED vector and prove only authorized
  debug runs retain per-fragment index, context/generated-token counts, output
  bytes, exhaustion, elapsed time, and stop classification. Prove debug and
  normal paths never expose prompts, fragments, token IDs, sealed bytes,
  tensors, paths, or reservation internals; normal traces and results expose
  only allowed aggregate/redacted facts.

## S4 — Migration and Evidence

- [ ] T4.1 [tests, RED] Migrate the Transformers/PEFT continuation path from
  hard-coded `1_000_000`/`32` ceilings to the resolved canonical budget.
- [ ] T4.2 [implementation] Remove duplicate generation-limit ownership from
  converter and local-runner paths while retaining temporary compatibility
  aliases at the public request boundary.
- [ ] T4.3 [tests, GREEN] Run focused converter, local-runner,
  sealed-artifact, and model-budget suites without a live model or GPU.
- [ ] T4.4 [manual gate] With explicit authorization, run one supported local
  model under a declared bounded budget and record only redacted effective
  limits, aggregate facts, and either a bounded terminal result or a redacted
  pre-dispatch budget rejection. An OS memory kill fails this gate.
- [ ] T4.5 [validation] Run `poetry run pytest -q`,
  `poetry run ruff check src tests`, and `git diff --check`; update the related
  spec statuses and remove compatibility aliases only after all consumers have
  migrated.
