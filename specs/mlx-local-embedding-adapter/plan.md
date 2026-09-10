# macOS MLX Local Embedding Adapter Plan

## Delivery Rules

- Keep this adapter separate from `MLXLocalModelAdapter` and the generation
  backend protocol.
- Begin each implementation slice with focused fake-only RED tests, then make
  the smallest GREEN change.
- Do not add an MLX dependency to the base package or import MLX in tests.
- Do not run a live embedding model without explicit authorization after all
  deterministic contract tests pass.

## S1 — Upstream capability characterization

1. Inspect the selected supported MLX/MLX-LM release and one approved local
   embedding artifact or official API documentation.
2. Record exact public loading/embedding APIs, model layouts, batch/result
   shapes, pooling/normalization, identity behavior, and incompatibilities.
3. Decide whether converted MLX directories alone are supported initially; add
   GGUF only if the public API demonstrates equivalent embedding behavior.
4. Stop if no stable public embedding API exists.

Exit: the repository has a redacted, versioned discovery record sufficient to
write an injected backend protocol without inferring undocumented behavior.

## S2 — Direct adapter contract

1. Add RED tests for package imports, public config/factories, macOS-only lazy
   failure, missing dependency, and fake backend injection.
2. Implement sync/async config and factories in a dedicated MLX embedding
   module, using existing embedding input/result and local-model error types.
3. Add RED then GREEN tests for identity and explicit asset resolution with
   injected download/load doubles only.
4. Verify no change to the text-generation MLX adapter capability metadata.

Exit: callers can use an injected backend through a small direct embedding API
without MLX on CI.

## S3 — Batch normalization and default loader

1. Add RED tests for every invalid result shape, ordering, ID, finite-value,
   dimension, and resource-limit failure.
2. Implement shared bounded batch normalization and the default lazy loader
   using only the characterized public upstream API.
3. Add fake-only metadata and async parity tests.
4. Run focused MLX, local-model, import, and capability suites.

Exit: a conforming MLX backend has the same bounded direct embedding guarantees
as the existing local embedding path.

## S4 — Generic workflow-provider integration

1. After approval of `embedding.execute.v1`, add RED provider-conformance and
   sealed material-binding tests.
2. Implement the MLX runner/profile/provider registration without exposing
   provider selection to workflow inputs.
3. Prove unavailable or changed providers fail before model materialization,
   embedding execution, workflow-local builder import, or artifact egress.
4. Run relevant full tests, Ruff, and `git diff --check`.

Exit: compatible receivers may satisfy a locked generic embedding capability
with MLX, while other platforms/providers continue to use their own paths.

## Manual Acceptance

With explicit authorization, run a fixed approved local embedding model on an
eligible Mac and compare only shape, ordering, finite values, bounded batch
behavior, duration, and memory use against the characterized contract. Retain
no source text or vector values.
