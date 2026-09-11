# macOS Generic MLX Embedding Execution Plan

## Delivery Rules

- Implement a generic sealed-descriptor MLX embedding ABI registry, not a
  model registry or an extension of the text-generation adapter.
- Use fake-only RED/GREEN cycles. MLX is not a base dependency and no unit test
  imports MLX or downloads a model.
- The workflow construction process locks material, descriptor, tokenizer,
  pooling, normalization, and source-license decision. Receiver DAR verifies
  and executes that data but does not choose it.
- A real model runs only under explicit authorization after deterministic
  admission and conformance tests pass.

## S0 — Generalized execution-ABI prerequisite

1. Extend the generic model-material contract with a descriptor digest and a
   fixed ABI-neutral `execution-descriptor.json` file. Its descriptor does not
   contain the material-lock digest, avoiding a circular construction.
2. Define the initial closed BERT-style `architecture_abi` identity (ID,
   version, contract digest) and its finite vocabulary for exact tokenizer,
   tensor-layout, pooling, normalization, bounds, and synthetic-conformance
   fields. The ABI owns tensor grammar; a descriptor cannot carry predicates,
   expressions, imports, loader settings, runtime versions, or a model ID.
3. Resolve the exact ABI through a pure receiver-installed validator registry
   before material/framework work, then bind descriptor digest into private
   model and embedding execution bindings without an MLX-specific manifest.

Exit: another workflow can select another locked material set that validates
against an installed ABI without a DAR model registry or source change. A new
architecture remains an explicit later ABI addition, not a workflow-provided
loader.

## S1 — Direct adapter admission

1. Add fake-only RED tests for lazy factory/import behavior, macOS-14+/arm64
   checks, exact MLX dependency admission, generic descriptor/material
   rejection, and injected-backend reachability.
2. Implement dedicated sync/async configuration and factories using existing
   embedding input/result and package-owned errors.
3. Prove the generation adapter's interface and metadata do not change.

Exit: the direct adapter reaches a conforming backend only after platform,
dependency, descriptor, and locked-material admission.

## S2 — Generic BERT-style encoder and conformance

1. Add RED tests for descriptor parser ceilings, role/tensor/tokenizer rules,
   truncation, padding, pooling, materialization, normalization, bounds, IDs,
   order, and invalid vectors.
2. Implement the ABI interpreter with public `mlx.core` APIs only.
3. Add fake-only batch, async-parity, capability, redaction, and no-fallback
   tests.

Exit: deterministic tests establish the generic ABI without a live model;
per-model arithmetic is the only remaining Darwin work.

## S3 — Manual competency

1. With explicit authorization, run one workflow-defined descriptor and locked
   materials on a compatible Mac.
2. Compare its synthetic reference vectors within declared tolerance and check
   truncation, padding, order, finite dimensions, duration, and memory.
3. Record only package/descriptor/material digests, versions, aggregate
   measurements, and redacted pass/fail results.

Exit: that sealed descriptor is eligible for provider registration; any mismatch
returns work to S0–S2.

## S4 — Generic workflow provider

1. After S0 and `embedding.execute.v1` prerequisites, add RED provider and
   descriptor/material-binding tests.
2. Register the generic MLX execution ABI provider through the capability
   catalog, never a model-specific provider.
3. Prove unavailable/changed providers fail before materialization, model
   execution, builder import, or artifact egress.
4. Run focused suites, full pytest, Ruff, and `git diff --check`.

Exit: a compatible Mac receiver can satisfy any sealed descriptor supported by
an installed MLX ABI; other providers and platforms remain unchanged.
