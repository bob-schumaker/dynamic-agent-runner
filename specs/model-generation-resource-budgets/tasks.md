# Model Generation Resource Budgets Tasks

## Status

Implementation has begun. T3.2a and T3.2b now cover the reviewed CPU and
Darwin/MPS controller variants; the remaining runtime migration work stays
gated by the RED-first tasks.

## S1 — Canonical Contract and Admission

- [ ] T1.1 [tests, RED] Add fake-only execution-descriptor ABI and resolver
  vectors for the exact seven-field immutable `generation_budget` record:
  positive integers, Boolean rejection, zero only for `max_continuations`, no
  aliases or extra fields, canonical material-lock binding, strict partial
  material/profile cap records, the typed runner capability, host ceiling, and
  the outer runtime/memory-only cap mapping. Prove missing required sources and
  malformed optional sources fail with the specified finite classification.
- [ ] T1.2 [tests, RED] Add capability-record and registration vectors for
  DAR-owned and `LocalModelRunnerCatalog` runners: exact identity binding,
  duplicate runner/capability rejection, exactly one worker-only factory bound
  to each worker capability and none for cancellation capability, reviewed
  controller identity bound to the selected worker runner/device pair,
  both/neither lifecycle forms,
  missing/incompatible pre-packing containment, missing worker generation-stage
  hard limit, and a selected device the containment cannot cover.
- [ ] T1.3 [implementation] Add the immutable budget/host resolver and
  `GenerationRunnerCapability` validation at the generic model-execution and
  local-runner catalog boundaries. Resolve the fieldwise minimum of sealed
  declaration, material/profile cap, receiving-runner capability, host ceiling,
  and outer runtime/memory cap; do not add domain paging semantics.
- [ ] T1.4 [tests, GREEN] Rerun T1.1–T1.2 vectors. Prove
  missing/incompatible capability and invalid/unavailable budget produce the
  exact finite classifications; prove legacy request fields can only reduce
  per-fragment/continuation limits, cannot alter any other dimension, and
  cannot bypass an effective limit.

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
  `generation_memory_budget_unavailable`; prove concurrent requests are
  atomically admitted or rejected in the material-lock/runner/device namespace;
  and prove every acquired reservation is released exactly once. Add built-in,
  cancellation-capable in-process, and receiver-installed runner vectors that
  require declared pre-packing containment or reject before sealed input. Prove
  in-process shared residency is not charged to an invocation reservation and a
  per-invocation hard-limit worker with shared residency is rejected pre-load.
- [ ] T3.2 [tests, RED] Add deterministic fake-child launcher vectors: the
  bootstrap cap is no greater than the effective memory ceiling, covers host and
  selected-device allocation, begins before packing, and rejects attempted
  packing-phase model/accelerator entry before model load; prove launch enters
  the cap before child execution and the monotonic deadline starts before
  launch/packing. Prove only reviewed runner/device containment with bounded
  reap confirmation admits execution; unsupported combinations fail before
  sealed-input ingress with `generation_memory_budget_unavailable`.
- [x] T3.2a [tests, RED] Add CPU-controller vectors for the general-purpose
  `multiprocessing` + POSIX `resource` path: CPU-only registration, address-space
  cap installation before the fixed child entry point, redacted readiness, and
  bounded terminate/kill/reap confirmation.
- [x] T3.2b [tests, RED] Add macOS-controller vectors for the Metal/MPS path:
  Darwin-only registration, exact MPS runner/device binding, and a reviewed
  Metal memory-envelope capability that must install before launch. Reject an
  unavailable platform, device mismatch, or unenforceable MPS envelope before
  sealed-input ingress with `generation_memory_budget_unavailable`.
- [ ] T3.3 [tests, RED] Add a `generation-worker-v1` transcript suite. Cover
  every message identity and transition: missing/wrong invocation ID or fragment
  index, duplicate/out-of-order authorization, an unauthorized receipt result,
  malformed/stale/repacked receipt, stale completion after timeout, and every
  finite failure classification. Distinguish control receipts/scalars from
  private admitted candidate bytes; prove tensors, token IDs, objects, paths,
  and workflow-visible partial output never cross.
- [ ] T3.3a [tests, RED] Add typed launch-descriptor vectors before worker
  implementation: exact versioned bounded wire mapping, required identities and
  fragment binding, opaque controller-issued handles only, parent-only factory,
  fixed entry-point revalidation before asset resolution, and rejection of
  paths, callables, arbitrary imports, loader code, or unknown identities.
- [ ] T3.4 [tests, RED] Add scalar/frame accounting vectors. Prove the worker's
  exact generated-token attestation is bound to receipt/fragment identity;
  reject a count over its authorization, aggregate/fragment mismatch, or bad
  continuation count; accept exact boundaries; recompute received byte counts;
  bound launch-descriptor mappings and candidate/aggregate bytes; and prove
  oversized candidate bytes never enter IPC.
- [ ] T3.5 [tests, RED] Add deadline/lifecycle vectors: cancellation-capable,
  noninterruptible, and worker runners; a controlled no-model real child that
  blocks after ready; expiry during generation and during reap; no admitted late
  frame or zombie; cleanup before exactly one reservation release; and stable
  deadline classifications.
- [ ] T3.6 [implementation] Add reservation admission and selected-device
  pre-packing containment for every runner; implement
  `GenerationWorkerLauncher` and `generation-worker-v1`, including its scalar
  attestation/frame checks, deadline/reap escalation, and shared-residency
  rejection. Do not implement tensor or converter-state serialization,
  thread-only timeout, reusable workers, or a generation-worker-specific
  untrusted-code sandbox in this slice. Record that this process uses the
  current sealed workflow-asset trust model and must migrate with converters
  and sealed artifacts when DAR adds its common approved isolation backend.
  Bind the reviewed controller and worker-only factory to the selected worker
  registration. On every normal, exceptional, cancellation, and deadline path
  close frame admission, discard candidate/private state, reap as applicable,
  record cleanup, and release the reservation only after reap confirmation.
- [ ] T3.7 [tests, GREEN] Rerun T3.1–T3.5 vectors against the implementation.
  Prove the exact bootstrap -> pack receipt -> reserve -> authorize ->
  generate-result sequence for every fragment; exactly one reap and reservation
  release; persistent generation-stage limit across continuations; pre-load
  rejection for unavailable runner/device containment; and all finite terminal
  classifications and protocol failures are redacted and deterministic.
- [ ] T3.8 [tests, RED] Add fake debug and normal-run telemetry vectors for
  authorized retention, required per-fragment facts, aggregate-only normal
  results, and prohibited-content redaction.
- [ ] T3.9 [implementation] Add the authorized-debug retention gate and
  redacted telemetry/result shaping without exposing model content or host
  internals.
- [ ] T3.10 [tests, GREEN] Rerun every S3 RED vector and prove only authorized
  debug runs retain per-fragment index, context/generated-token counts, output
  bytes, exhaustion, elapsed time, and stop classification. Prove debug and
  normal paths never expose prompts, fragments, token IDs, sealed bytes,
  tensors, paths, or reservation internals; normal traces and results expose
  only allowed aggregate/redacted facts.

## S4 — Migration and Evidence

- [x] T4.1 [tests, RED] Migrate the generic converter-capable model-adapter
  continuation path from hard-coded `1_000_000`/`32` ceilings to the resolved
  canonical budget. Keep the current Transformers/PEFT single-image workflow
  only as a conformance fixture.
- [ ] T4.2 [tests, RED] Add converter/plugin migration vectors. Prove a bounded
  worker co-locates the exact digest-verified converter and compatible runner,
  loads the converter through the existing sealed creator-asset loader and
  restricted converter context rather than a worker-specific loader contract,
  never serializes `PackedModelInput`, admits the registered
  `GenerationRunnerCapability`, and rejects a missing/incompatible receiver
  capability before launch. Reuse the S3 descriptor/factory conformance suite.
- [ ] T4.3 [implementation] Remove duplicate generation-limit ownership from
  the generic converter-capable adapter, converter, and local-runner paths
  while retaining temporary compatibility aliases at the public request
  boundary. Implement the worker co-location seam and generic adapter
  worker-child factory contract; amend converter, local-runner, and
  model-execution-plugin contracts to the generic capability record. Keep
  model-family and modality-specific code in conformance fixtures. The adapter
  obtains the selected registration, invokes the worker-only factory solely
  through the fixed DAR entry point, and retains aggregate accounting, redacted
  telemetry, and terminal response shaping in the parent.
- [ ] T4.4 [tests, GREEN] Rerun T4.1–T4.2 and T3.3a. Prove all built-in and
  receiver-installed runners register `GenerationRunnerCapability`, legacy
  aliases exist only at the public boundary, and obsolete per-runner limit
  ownership is absent.
- [ ] T4.5 [tests, GREEN] Run focused converter, worker transport,
  local-model-runners, execution-plugin, local-runner, sealed-artifact, and
  model-budget suites without a live model or GPU.
- [ ] T4.6 [manual gate] With explicit authorization, run one supported local
  model under a declared bounded budget and record only redacted effective
  limits and aggregate facts. For the worker lifecycle form, also record a
  supported receipt showing bootstrap, authorization, and reap; for the
  cancellation lifecycle form, record bounded terminal cleanup. An unsupported
  machine may additionally record a redacted pre-dispatch rejection; an OS
  memory kill fails this gate.
- [ ] T4.7 [validation] Run `poetry run pytest -q`,
  `poetry run ruff check src tests`, and `git diff --check`; update the related
  spec statuses and remove compatibility aliases only after all consumers have
  migrated.
