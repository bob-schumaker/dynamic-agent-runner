# macOS Custom MLX GTE Tiny Embedding Adapter Specification

## Metadata

- Feature slug: `mlx-local-embedding-adapter`
- Status: proposed
- Owner: dynamic-agent-runner local-model and embedding-capability boundaries
- Plan: `plan.md`
- Tasks: `tasks.md`
- Related specifications:
  - `specs/mlx-local-model-adapter/spec.md`
  - `specs/llama-cpp-local-model/spec.md`
  - `specs/workflow-embedding-index-artifacts/spec.md`
  - `specs/workflow-model-materials/spec.md`
  - `specs/workflow-capability-requirements/spec.md`

## Objective

Provide a lazy, in-process, macOS-only embedding provider for exactly one
locked encoder: `TaylorAI/gte-tiny` at Hugging Face revision
`4cc5e73d86a67c601897257b467187234aa3bca3`. DAR shall implement the required
BERT encoder and sentence-embedding behavior on the public Python `mlx`
array/NN API. It shall not depend on, call, or emulate an undocumented Python
`mlx-lm` embedding interface.

The provider is optional: ordinary DAR imports, non-macOS hosts, CI, and
existing llama.cpp GGUF embedding workflows require neither MLX, Metal, nor
GTE Tiny materials.

## Problem Statement

The Python `mlx-lm` surface that DAR currently uses is generation-oriented.
MLX Swift's `MLXEmbedders` proves that an explicit encoder, tokenizer, pooling,
and model registry form a sound embedding boundary, but it is not a Python API
DAR can import. A custom Python implementation gives DAR a narrow, inspectable
path for one known BERT-family model without turning generic generation hidden
states into purported embeddings.

## Target Model Contract

The sole v1 model is `TaylorAI/gte-tiny`, a BERT-family sentence-transformer
with 22,713,216 parameters, a 512-token maximum sequence length, 384 output
dimensions, and masked mean pooling. MLE1 must verify these source facts from
the pinned revision and record the full artifact manifest. The model-material
declaration locks the repository revision above and SHA-256 of every required
source file at workflow construction time. It contains a closed role-to-relative
path map for the BERT `config.json`, `model.safetensors`, `tokenizer.json`,
tokenizer/special-token configuration, and `1_Pooling/config.json`.

For each bounded batch, the adapter shall tokenize with the locked tokenizer,
run the locked BERT encoder, compute the attention-mask-weighted mean of its
last hidden-state vectors, and produce one 384-dimensional finite vector per
input. Normalization is not implicit: `mlx-gte-tiny-v1` fixes it to `none`,
matching the pinned source pooling configuration; the adapter rejects material
whose parsed configuration does not match that fixed profile.

`thenlper/gte-small` is a later quality-comparison model, not an accepted v1
material set or implicit fallback. Supporting it requires a separately locked
profile and conformance evidence.

## Scope

This feature defines:

1. a dedicated sync/async MLX embedding adapter, separate from text generation;
2. a DAR-owned, narrow BERT encoder and GTE Tiny tokenizer/material loader;
3. exact locked-material, model-identity, pooling, vector, and resource-limit
   validation;
4. fake-only deterministic conformance tests and an explicitly authorized Mac
   competency protocol; and
5. an optional `embedding.execute.v1` provider once the generic workflow
   capability and sealed-runner prerequisites are complete.

## Non-Goals

This feature does not:

- add embeddings to `MLXLocalModelAdapter` or alter its `embeddings: False`
  capability claim;
- support arbitrary Hugging Face repositories, architectures, custom/remote
  code, GGUF, ONNX, Core ML, `mlx-lm` model directories, conversion recipes,
  or runtime model selection;
- implement a general Python port of all Swift `MLXEmbedders` models;
- create an MLX server, automatic download policy, model discovery service,
  vector store, document parser, chunker, index builder, reranker, or query
  API; or
- make a live MLX model run part of pytest or CI.

## Architecture and Trust Boundary

### Dedicated adapter boundary

The public surface is separate from generation:

```python
adapter = create_mlx_local_embedding_adapter(config)
result = adapter.embed(items)
```

It reuses DAR's existing `EmbeddingInputItem` and `EmbeddingBatchResult`
contracts where compatible. It has no `create_response`, chat-template,
tool-calling, or generation-parameter surface. The async form delegates the
same synchronous validation/execution path through `asyncio.to_thread` or an
equivalent nonblocking wrapper.

### Custom MLX encoder

The default backend is DAR-owned code with a deliberately closed contract:

- lazy-import `mlx` and `mlx.nn` only on the first Darwin embedding call;
- instantiate only the GTE Tiny BERT configuration after validating the locked
  configuration and all expected tensor names, shapes, and dtypes;
- load only the locked safetensors and tokenizer assets from normal
  model-material resolution; and
- perform only the specified masked mean pooling and any explicitly locked
  final normalization.

It must not call private APIs, derive a vector from a causal generation model,
execute model-supplied Python, or silently substitute a different loader,
model, pooling rule, tokenizer, or precision.

Tests inject a small private `MLXLocalEmbeddingBackend` protocol and never
import MLX. The real implementation is admitted only by a Darwin competency
run after fake tests establish all boundary behavior.

### Material and capability binding

The material lock binds the existing generic runner and loader-profile contracts,
the exact model revision, and source-role hashes. It does not acquire
GTE-specific fields. `mlx-gte-tiny-v1` is a closed DAR-owned profile whose
versioned runner/loader contracts fix 384 dimensions, 512 tokens, masked-mean
pooling, and no normalization; the adapter proves those facts by validating the
sealed source roles. A sealed package does not name MLX, Metal, a Python package
version, a model path, cache location, or a provider implementation.

The direct adapter accepts only a verified `PreparedArtifactSet` from the
receiver-private material resolver, never a repository, path, revision, or
pooling setting. A workflow provider uses the existing generic
`bindings.runner` material binding plus the `embedding.execute.v1` requirement
once a DAR-owned embedding runner/profile is available. It does not need an
MLX-specific manifest field or a parallel execution path. No provider fallback
is allowed.

## Functional Requirements

### FR-1: macOS-only lazy availability

Importing DAR or constructing the adapter shall not import MLX. On a host that
is not macOS 14-or-later on arm64, the first embedding call shall raise a
package-owned availability error before asset resolution or dependency loading.
On an eligible host, a missing, wrong-version, ABI-incompatible, or failed
`mlx` import shall raise a redacted package-owned dependency error. The initial
supported runtime is `mlx==0.32.2`; a different version is rejected until
separately characterized and approved.

There is no CPU, llama.cpp, remote, generation-model, or alternate-MLX fallback.

### FR-2: exact GTE Tiny assets and identity

The adapter shall use only the locked GTE Tiny material set. Before MLX tensor
allocation it shall validate source revision, required role/path/hash/byte-size
ceilings, safe safetensors header shape, BERT configuration compatibility,
expected tensor names/shapes/dtypes, and a strict WordPiece tokenizer
configuration. The tokenizer accepts only its fixed local assets, bounded UTF-8
input, declared Unicode/error handling, and the 512-token limit. It rejects an
absent, extra, malformed, oversized, wrong-shaped, or wrong-identity material
with package-owned errors before tokenization or model evaluation.

It shall not ambiently scan model directories, resolve a branch/tag, accept an
invocation-time repository/path, download an unpinned revision, or execute
remote/custom model code.

### FR-3: bounded, semantically exact batch embeddings

The adapter shall validate nonempty finite input batches using the existing
embedding input contract, tokenize input using the locked tokenizer with
truncation at 512 tokens, and return exactly one vector per input ID in the
same order. It shall apply masked mean pooling exactly as declared, followed by
only the locked normalization policy.

It shall explicitly materialize MLX results before it checks and returns them,
then reject missing, extra, duplicate, reordered, nonnumeric, nonfinite, empty,
or non-384-dimensional vectors. Static configuration shall set positive
item-count, per-item-byte, aggregate-byte, token-count, vector-dimension, and
observed-memory limits. MLX in-process execution provides no hard memory or
timeout isolation guarantee; a workflow binding may tighten, but cannot relax,
host/provider limits.

### FR-4: conservative capability reporting

Static adapter metadata shall not perform material or dependency admission and
therefore reports the provider unavailable. Receiver-private capability
resolution may report local in-process MLX execution and `embeddings: True`
only after platform, dependency, material, and profile admission succeed; it
revalidates availability immediately before provider entry. It reports text
generation, tool calling, structured output, streaming, multimodal use, and
reranking as unsupported. A generation adapter remains independently
`embeddings: False`.

### FR-5: reference-vector conformance

Before releasing the real backend, maintainers shall create a redacted
conformance fixture from the locked source model using a named, pinned reference
implementation with `trust_remote_code=False`. The fixture contains only stable
synthetic inputs, exact token IDs/attention masks, dtype and accumulation rule,
expected 384-dimensional float values, and coordinate and aggregate tolerance;
it contains no user text, vault content, model-supplied code, or live workflow
output. A digest alone is not a numerical conformance oracle.

The Darwin test protocol shall prove the custom backend matches the reference
pooling semantics within an explicitly recorded numerical tolerance, handles
padding and truncation, and emits finite 384-dimensional vectors. A mismatch
blocks provider registration.

### FR-6: workflow-provider conformance

After the generic binding extension is implemented, the MLX provider shall pass
its fake-backend conformance matrix: capability identity, exact runner/profile
and locked-material binding, changed availability, selected-provider identity,
batch/vector validation, no fallback, redaction, and pre-side-effect rejection.
The generic workflow spec remains authoritative for snapshots and index-bundle
behavior.

## Acceptance Criteria

- Package import and public factories work without MLX installed; fake tests
  run on non-macOS without a model, Metal, or network.
- Platform and dependency failures occur before asset resolution or backend
  loading; material rejection occurs before tokenization, MLX allocation, or
  evaluation.
- Fake-backend tests prove ordered normalization and every invalid-vector
  outcome in FR-3, without an MLX import.
- Tests prove only the GTE Tiny runner/model/profile is accepted, and that
  generation MLX behavior is unchanged.
- A separately authorized Mac competency run proves the locked model's vector
  dimension, mean-pooling semantics, padding/truncation behavior, finite
  output, and reference tolerance while retaining no private input or vector
  data.
- Static and receiver-resolved capability metadata distinguish the new embedding
  adapter from the generation adapter and from llama.cpp without breaking lazy
  admission.

## Delivery Gate

Implementation begins only after the material lock records the exact source
file hashes, parser ceilings, and reference-vector fixture/tolerance. Workflow
provider registration additionally requires an approved DAR-owned embedding
runner/profile, the approved `embedding.execute.v1` contract, and its
sealed-runner prerequisites.
