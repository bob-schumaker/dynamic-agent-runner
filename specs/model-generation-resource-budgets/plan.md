# Model Generation Resource Budgets Plan

## Goal

Replace scattered model-generation ceilings with one generic, host-capped
budget resolved before a model runner executes.

## Design

1. Extend the sealed `execution-descriptor.json` ABI fields with one strict
   seven-field `generation_budget` record, then introduce an immutable canonical
   budget value and host-policy resolver. Define the typed field applicability
   matrix: workflow and host records cover all fields; material/profile records
   are strict partial records; runner capability bounds context and declares
   lifecycle/memory support; the outer artifact descriptor caps only runtime and
   memory. Add `GenerationRunnerCapability` schema, identity binding, and
   duplicate-rejecting registration to both DAR-owned and `LocalModelRunnerCatalog`
   boundaries. Worker-capable registrations additionally bind exactly one
   parent-only worker-child factory to that runner/capability contract;
   cancellation-capable registrations bind none. Resolve the fieldwise minimum
   and preserve legacy request fields only as reducing compatibility aliases.
2. Pass the resolved value—not raw workflow request fields—through built-in and
   plugin runner boundaries. Measure packed input plus requested output against
   the lesser of the effective and runner-supported context, and count generated
   tokens, assembled UTF-8 bytes, fragments, and elapsed time at each boundary.
   Reduce a fragment request to the remaining aggregate token allowance; reject
   an oversized assembled-byte candidate before terminal processing, and dispose
   of every partial candidate.
3. Add a receiver-owned memory-reservation interface and pre-packing
   containment declaration. Every runner enters its platform/device-enforceable
   bootstrap envelope before decode or packing. After a worker returns a
   validated packing receipt—or an in-process runner has measured packed
   context—the host atomically obtains the generation reservation before model
   load or generation. A runner without both containment and one FR-3 admission
   method is unavailable. Release each reservation exactly once after
   request-scoped cleanup.
   Admit a runner/device only when it supplies a reviewed containment
   implementation for its bootstrap and generation-stage envelopes; unsupported
   combinations fail before sealed-input ingress. A worker-capable registration
   binds its reviewed controller and parent-only factory to that pair; a
   cancellation-capable adapter instead uses the direct bounded path. A pair
   unable to guarantee bounded reap confirmation is unavailable before ingress.
4. Apply enclosing sealed-artifact runtime/memory ceilings as additional caps;
   do not reimplement artifact I/O, callback, or output-slot accounting.
5. Start an invocation deadline before worker launch, invocation-scoped packing,
   load, or generation.
   Admit only runners that support cancellation or execute in a terminable
   isolated worker; classify a noninterruptible runner as unavailable rather
   than reporting a timeout after it returns. Implement the spec's
   `GenerationWorkerLauncher` and `generation-worker-v1` state machine: install
   bootstrap limits before pack; validate a receipt; reserve; authorize; then
   load/generate. The launcher withholds host loader/device handles during pack;
   unsupported containment fails closed. Before framing a candidate, the worker
   checks aggregate bytes; the parent recomputes bytes and rejects inconsistent
   frames; generated-token counts are receipt-bound compatible-runner
   attestations checked for budget/protocol consistency without transporting
   token IDs. The generation-stage limit remains installed across continuation
   admissions. Implement the worker-state contract in the specification through
   the registration-bound controller and fixed entry point. On every terminal
   path, the parent closes frame admission, discards candidate/private state,
   reaps as applicable, records cleanup, then releases its reservation only
   after reap confirmation. This is resource containment, not untrusted-code
   isolation; worker reuse remains deferred.
6. Retain per-fragment telemetry only for authorized debug runs: fragment index,
   packed-context and generated-token counts, output bytes, exhaustion, elapsed
   time, and budget-stop classification. Keep normal traces and results to
   safe aggregate counters and redacted classifications.
7. Migrate converter/plugin execution so the child co-locates the converter and
   compatible runner, while registrations expose the generic capability and
   worker-only factory.
8. Migrate the generic converter-capable model-adapter boundary: it obtains the
   selected registration, invokes a worker-only factory only through the fixed
   entry point, and retains aggregate accounting, telemetry, and terminal
   response shaping. It rejects context growth rather than compressing it.

## Verification

Use fake-only unit, deterministic fake-child-process conformance, and one
controlled no-model real-child termination/reap test to establish each rejection
boundary, limit-installation ordering, cleanup, and redaction behavior. Include
built-in, receiver-installed/plugin, in-process, and worker capability rejection
vectors. Run focused budget, worker transport, local-model-runners,
converter-capable adapter, execution-plugin, sealed-artifact, and converter suites,
then `poetry run pytest -q`,
`poetry run ruff check src tests`, and `git diff --check` after implementation.
