# macOS Custom MLX GTE Tiny Embedding Adapter Plan

## Delivery Rules

- Implement one closed `mlx-gte-tiny-v1` runner; do not generalize it into a
  model registry or reuse the text-generation MLX adapter.
- Use test-first, fake-only RED/GREEN cycles. MLX must not be imported by unit
  tests or added as a base dependency.
- Material locks, not invocation data, select every model file, tokenizer,
  pooling rule, normalization rule, and runtime version.
- Do not run a real model until deterministic material/admission tests pass and
  the user explicitly authorizes the Mac competency protocol.

## S0 — Confirm generic binding prerequisites

1. Reconcile the generic model-material, capability, and embedding-index
   artifacts: a package with `model-materials.json` requires a declared runner
   capability named by `bindings.runner`, while `embedding.execute.v1` remains
   a separate single-purpose requirement.
2. Add generic provider admission that proves the selected embedding provider
   supports the sealed runner/profile/material binding before provider entry;
   existing embedding-provider resolution validates only its capability.

Exit: the MLX provider uses the existing generic package binding and creates no
MLX-specific manifest field or parallel execution path; a capability-compatible
but binding-incompatible embedding provider fails before model entry.

## S1 — Lock the GTE Tiny profile

1. Record the source-model identity: `TaylorAI/gte-tiny` revision
   `4cc5e73d86a67c601897257b467187234aa3bca3`, BERT architecture, 384
   dimensions, 512-token limit, and masked-mean pooling.
2. At workflow construction, resolve and hash the complete required material
   set; define closed roles, paths, byte ceilings, safe parse order, and the
   `mlx-gte-tiny-v1` runner/loader-profile contracts.
3. Specify the reference implementation, synthetic inputs, precision, and
   output tolerance; final normalization is fixed to `none`.

Exit: every runtime-relevant artifact is immutable and the adapter has a
reference conformance target without receiving raw user content.

## S2 — Direct adapter admission boundary

1. Add fake-only RED tests for import/factory behavior, lazy macOS-14+/arm64
   checks, `mlx==0.32.2` dependency admission, material role/hash/identity
   validation, and injected-backend behavior.
2. Implement a dedicated sync/async configuration and factory using existing
   embedding input/result and package-owned error types.
3. Prove the text-generation MLX adapter's interface and metadata do not
   change.

Exit: the direct adapter reaches an injected conforming backend only after
platform, dependency, and locked-material admission.

## S3 — Custom BERT encoder and result conformance

1. Add RED tests for parser ceilings before MLX allocation, required
   configuration fields, tensor keys/shapes/dtypes, tokenizer Unicode/error
   behavior, 512-token truncation, masked mean pooling, padding,
   materialization, normalization policy, and all invalid output cases.
2. Implement the private GTE Tiny BERT module and tokenizer loader using only
   public `mlx` / `mlx.nn` APIs and locked safetensor/tokenizer assets.
3. Add fake-only batch, async-parity, capability, redaction, and no-fallback
   tests.

Exit: deterministic tests establish the whole contract without MLX or live
weights; only a Darwin conformance run remains for model arithmetic.

## S4 — Manual Mac competency

1. With explicit authorization, run the locked materials on a compatible Mac.
2. Compare synthetic reference vectors within the approved tolerance and check
   truncation, padding, order, finite 384-dimensional results, duration, and
   memory.
3. Record only versions, material-lock digest, aggregate measurements, and
   redacted pass/fail results.

Exit: the real runner is eligible for provider registration; any numerical or
material mismatch returns work to S1–S3.

## S5 — Generic workflow provider

1. After S0, `embedding.execute.v1`, and sealed-runner prerequisites are
   approved, add RED provider/material-binding tests.
2. Register `mlx-gte-tiny-v1` as an optional DAR provider selected only by the
   capability catalog.
3. Prove unavailable/changed providers fail before model materialization,
   embedding execution, builder import, or artifact egress.
4. Run focused suites, the full suite, Ruff, and `git diff --check`.

Exit: a compatible Mac receiver can satisfy a locked generic embedding binding;
other providers and platforms remain unchanged.
