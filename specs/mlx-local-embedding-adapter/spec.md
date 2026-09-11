# macOS Generic MLX Embedding Execution Specification

## Metadata

- Feature slug: `mlx-local-embedding-adapter`
- Status: proposed
- Owner: dynamic-agent-runner local-model and embedding-capability boundaries
- Plan: `plan.md`
- Tasks: `tasks.md`
- Related specifications:
  - `specs/mlx-local-model-adapter/spec.md`
  - `specs/workflow-embedding-index-artifacts/spec.md`
  - `specs/workflow-model-materials/spec.md`
  - `specs/workflow-capability-requirements/spec.md`

## Objective

Provide a lazy, in-process, macOS-only embedding capability for a sealed
workflow. DAR supplies platform/dependency admission, a bounded generic MLX
encoder ABI, material-identity verification, and result validation. Workflow
construction supplies immutable model material and a sealed declarative encoder
descriptor. DAR does not select an upstream embedding model, architecture
configuration, tokenizer, pooling rule, normalization rule, or license.

The provider is optional: ordinary DAR imports, non-macOS hosts, CI, and
existing llama.cpp workflows require neither MLX nor Metal.

## Problem Statement

`mlx-lm` is generation-oriented. A durable workflow needs MLX embedding
execution without turning a trial model into a DAR release contract or allowing
untrusted package code to load arbitrary models.

## Architecture and Trust Boundary

### Sealed encoder descriptor

Each material-backed embedding workflow carries an `execution-descriptor.json`
bound to its `model-materials.json` lock and package digest. It is UTF-8
canonical JSON, immutable package data, and never an invocation input. Its
fixed v1 schema contains:

- a descriptor format version and a DAR-supported `architecture_abi` object
  with exact ID, version, and contract digest;
- a complete reference to locked material roles;
- tokenizer format, required roles, special-token semantics, bounded input
  policy, and maximum token count;
- tensor naming/shape/dtype predicate and bounded parser/allocation ceilings;
- pooling and normalization algorithm identifiers from the selected ABI;
- positive output dimension and batch/item/aggregate resource ceilings;
- MLX runtime compatibility; and
- synthetic conformance-vector recipe, precision, and tolerances.

The descriptor is data, not a loader function, import target, code blob,
endpoint, cache path, device preference, or free-form model configuration. Its
values must satisfy the selected ABI's finite schema and host maxima. A workflow
author chooses the model and records any license acceptance during construction;
DAR transports neither that choice nor the model weights in its distribution.

### Generic MLX encoder ABI

DAR owns versioned, reviewed execution ABIs, initially a BERT-style encoder ABI
implemented with public `mlx` and `mlx.nn` APIs. A runner capability resolves
one receiver-installed, pure descriptor-validator registry. That registry first
resolves the descriptor's exact ABI ID, version, and contract digest, then
validates its finite schema without importing a framework or reading material.
An ABI defines descriptor vocabulary and deterministic interpretation; it does
not name an upstream model. A workflow may use any locked model whose descriptor
validates against an installed ABI. A new architecture family needs a later
reviewed DAR ABI, but another model within an existing ABI does not require a
DAR release.

The backend shall:

- lazy-import `mlx` and `mlx.nn` only on the first eligible embedding call;
- receive only a verified private artifact set and parsed sealed descriptor;
- validate every declared artifact and tensor requirement before allocation;
- perform only descriptor-declared ABI operations; and
- materialize and validate results before returning them.

It must not execute model-supplied Python, invoke `trust_remote_code`, infer a
model from a Hub repository, scan directories, call an `mlx-lm` embedding API,
or silently substitute an ABI, tokenizer, loader, pooling rule, precision, or
normalization rule.

Tests inject a small private `MLXLocalEmbeddingBackend` protocol and never
import MLX. A real backend is admitted only by an explicitly authorized Darwin
competency run after fake conformance tests pass.

### Adapter and material binding

The public surface is separate from text generation:

```python
adapter = create_mlx_local_embedding_adapter(config)
result = adapter.embed(items)
```

It reuses DAR's `EmbeddingInputItem` and `EmbeddingBatchResult` contracts where
compatible. It has no chat, tool-calling, generation, or arbitrary loader
surface. The async form delegates the same synchronous validation/execution
path through a nonblocking wrapper.

The direct adapter accepts only a verified `PreparedArtifactSet` and parsed
descriptor from receiver-private material resolution. A workflow provider uses
the generic material execution binding plus `embedding.execute.v1`; neither
package nor caller selects an MLX implementation, package version, repository,
path, cache location, or provider. No fallback is allowed.

## Functional Requirements

### FR-1: macOS-only lazy availability

DAR import and adapter construction shall not import MLX. On a host other than
macOS 14-or-later on arm64, the first embedding call raises a package-owned
availability error before material resolution or dependency loading. On an
eligible host, missing, wrong-version, ABI-incompatible, or failed `mlx` import
raises a redacted package-owned dependency error. The initial supported runtime
is `mlx==0.32.2`; another version is rejected until characterized and approved.

There is no CPU, llama.cpp, remote, generation-model, or alternate-MLX
fallback.

### FR-2: descriptor and material admission

Before material access, tokenization, or MLX allocation, DAR shall canonicalize
and validate the descriptor through the exact receiver-installed ABI contract,
then bind its package-declared role references to the parsed material lock.
It validates every required role, path, hash, size ceiling, safe header, tensor
predicate, and tokenizer asset; and enforces ABI and host resource maxima. It
rejects unknown or wrong ABI ID/version/digest, schema mismatch, missing, extra,
malformed, oversized, wrong-shaped, wrong-identity, or incompatible material
with package-owned errors.

It shall not ambiently scan a model directory, resolve a branch or tag, accept
an invocation repository/path, download an unpinned revision, or execute model
code.

### FR-3: bounded exact embeddings

The adapter validates finite nonempty input batches using the existing contract,
tokenizes according to the descriptor's bounded policy, and returns exactly one
vector per input ID in input order. It applies only the declared ABI pooling and
normalization operations, explicitly materializes results, and rejects missing,
extra, duplicate, reordered, nonnumeric, nonfinite, empty, or wrong-dimensional
vectors.

Static configuration sets positive item-count, per-item-byte, aggregate-byte,
token-count, vector-dimension, and observed-memory limits. MLX in-process
execution provides no hard memory or timeout isolation guarantee; a workflow
may tighten but cannot relax host/provider limits.

### FR-4: conservative capability reporting

Static adapter metadata performs no material or dependency admission and reports
the provider unavailable. Receiver-private resolution may report local MLX
execution and `embeddings: True` only after platform, dependency, material, and
descriptor admission. It revalidates immediately before provider entry and
reports generation, tools, structured output, streaming, multimodal use, and
reranking unsupported. The generation adapter remains independently
`embeddings: False`.

### FR-5: reference conformance

Before a real backend is released for a descriptor ABI, maintainers shall retain
a redacted synthetic conformance fixture generated by a named pinned reference
implementation with `trust_remote_code=False`. It contains synthetic inputs,
expected token IDs/masks, precision/accumulation rule, expected vector values,
and coordinate/aggregate tolerance; it contains no user text, workflow output,
or model-supplied code. A digest alone is not a numerical conformance oracle.

The Darwin protocol proves padding, truncation, pooling, normalization, finite
output, dimension, and tolerance for that descriptor. A mismatch blocks use of
that descriptor/provider pairing.

### FR-6: workflow-provider conformance

The provider shall pass a fake-backend matrix covering capability identity,
exact generic execution-ABI/descriptor/material binding, changed availability,
selected provider identity, batch/vector validation, no fallback, redaction,
and pre-side-effect rejection. The generic embedding-index specification remains
authoritative for snapshots and index-bundle behavior.

## Acceptance Criteria

- Package import and public factories work without MLX; fake tests run on
  non-macOS without a model, Metal, or network.
- Platform and dependency failures occur before artifact resolution or backend
  loading; descriptor/material rejection occurs before tokenization, MLX
  allocation, or evaluation.
- Fake-backend tests prove ordered normalization and every invalid-vector
  outcome without an MLX import.
- Tests prove arbitrary locked models are accepted only through a supported
  declarative ABI, while generation MLX behavior is unchanged.
- A separately authorized Mac competency run proves one workflow-defined
  descriptor's semantics without retaining private input or vector data.
- Static and receiver-resolved metadata distinguish embedding from generation
  and llama.cpp without breaking lazy admission.

## Delivery Gate

Implementation begins only after `workflow-model-materials` defines the sealed
descriptor binding, pure ABI-validator admission, and a generic ABI's descriptor
schema. Provider registration
also requires the approved `embedding.execute.v1` contract and its sealed-runner
prerequisites. Model-specific experiments may live only in test/manual harness
assets and cannot become production runtime identities.
