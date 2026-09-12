# Model Generation Resource Budgets Plan

## Goal

Replace scattered model-generation ceilings with one generic, host-capped
budget resolved before a model runner executes.

## Design

1. Extend the sealed `execution-descriptor.json` ABI fields with one strict
   seven-field `generation_budget` record, then introduce an immutable canonical
   budget value and host-policy resolver. Resolve the effective value as the
   minimum of that sealed declaration, material/profile limit, receiving-runner
   capability, host ceiling, and enclosing sealed-artifact runtime/memory cap.
   Preserve legacy request fields only as reducing compatibility aliases.
2. Pass the resolved value—not raw workflow request fields—through built-in and
   plugin runner boundaries. Measure packed input plus requested output against
   the lesser of the effective and runner-supported context, and count generated
   tokens, assembled UTF-8 bytes, fragments, and elapsed time at each boundary.
   Reduce a fragment request to the remaining aggregate token allowance; reject
   an oversized assembled-byte candidate before terminal processing, and dispose
   of every partial candidate.
3. Add a receiver-owned memory-reservation interface. A runner without a hard
   limit, platform allocation control, or conservative reviewed reservation
   estimator is unavailable for a memory-bounded invocation. Supply it only the
   material-lock and runner identities, selected execution device, packed-context
   and requested-new-token bounds, effective memory ceiling, and deadline.
   Acquire the opaque reservation before model work and release it exactly once
   on every terminal path after request-scoped cleanup is recorded.
4. Apply enclosing sealed-artifact runtime/memory ceilings as additional caps;
   do not reimplement artifact I/O, callback, or output-slot accounting.
5. Start an invocation deadline before invocation-scoped load or generation.
   Admit only runners that support cancellation or execute in a terminable
   isolated worker; classify a noninterruptible runner as unavailable rather
   than reporting a timeout after it returns. Discard late output and clear
   request-scoped sealed, packed, generation, and KV-cache state.
6. Retain per-fragment telemetry only for authorized debug runs: fragment index,
   packed-context and generated-token counts, output bytes, exhaustion, elapsed
   time, and budget-stop classification. Keep normal traces and results to
   safe aggregate counters and redacted classifications.
7. Migrate Transformers/PEFT raw continuation first. It rejects context growth
   rather than compressing it. Workflow components remain responsible for
   independently valid paged output and deterministic merging.

## Verification

Use fake-only unit tests to establish each rejection boundary, cleanup, and
redaction behavior. Run focused budget, Transformers runner, sealed-artifact,
and converter suites, then `poetry run pytest -q`,
`poetry run ruff check src tests`, and `git diff --check` after implementation.
