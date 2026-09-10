# macOS MLX Local Embedding Adapter Specification

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

Provide a lazy, in-process, macOS-only MLX embedding adapter that can serve as
an optional DAR provider for a generic locked embedding-material binding. It
must preserve the existing direct caller-owned embedding API pattern and must
not require MLX, Metal, an embedding model, or macOS in ordinary DAR installs
or CI.

The adapter is an execution provider, not an index builder. It receives bounded
text batches and returns validated vectors; document parsing, chunking, index
formats, persistence, and workflow package semantics remain outside this spec.

## Problem Statement

DAR's MLX adapter supports text generation only and explicitly advertises
`embeddings: False`. The direct llama.cpp embedding adapter provides a useful
shape for validated, local batch embeddings, but a portable embedding workflow
also needs an MLX-native provider for users whose locked model is available in
MLX format on Apple silicon.

Adding an `embed` method to the existing generation adapter would mix two
different model contracts, model formats, backend APIs, result types, and
capability claims. A dedicated embedding adapter has a smaller public surface
and can fail clearly when the selected MLX runtime or model does not implement
the required embedding behavior.

## Scope

This feature defines:

1. sync and async caller-owned MLX embedding adapter/config/factory surfaces;
2. a small injected backend protocol for load and batched embedding;
3. lazy macOS/MLX dependency, asset-resolution, and identity validation;
4. strict batch/vector normalization and capability metadata; and
5. an optional provider mapping to `embedding.execute.v1` when that generic
   contract is approved.

The initial implementation supports explicit converted-MLX directories and
locked model references that a selected upstream MLX embedding API can load.
GGUF support is permitted only after API characterization proves embeddings are
available and semantically compatible for the exact selected runtime/model
format.

## Non-Goals

This feature does not:

- alter `MLXLocalModelAdapter`, add embeddings to its generation contract, or
  change its conservative `embeddings: False` capability claim;
- create an MLX server, remote embedding endpoint, model conversion pipeline,
  model discovery service, or automatic model download policy;
- run on Linux, Windows, or non-MLX backends;
- select model paths, revisions, providers, device placement, batch limits, or
  model formats from a workflow invocation;
- implement reranking, multimodal embeddings, indexing, document chunking,
  vector stores, index persistence, or query/retrieval APIs; or
- make a live MLX model run part of pytest or CI.

## Architecture and Trust Boundary

### Dedicated adapter boundary

The public adapter is separate from text generation:

```python
adapter = create_mlx_local_embedding_adapter(config)
result = adapter.embed(items)
```

`items` and `result` reuse DAR's existing `EmbeddingInputItem` and
`EmbeddingBatchResult` contracts where compatible. The adapter has no
`create_response`, tool-calling, chat-template, or generation-parameter API.
The async form uses `asyncio.to_thread` or an equivalent nonblocking wrapper
around the same synchronous validation/execution path.

### Backend seam

One private `MLXLocalEmbeddingBackend` protocol accepts a resolved model
location and returns ordered vectors for a batch of text. Tests inject this
backend and never import MLX. The default dependency loader lazily imports only
the exact upstream package/API selected by the upstream-characterization gate.
It must reject a model that cannot produce sentence/document embeddings rather
than infer embeddings from a generation-only model's hidden states.

### Material and capability binding

Once `workflow-embedding-index-artifacts` supplies the generic contract, MLX
registers as one `embedding.execute.v1` provider under a DAR-owned embedding
runner/profile. A sealed package locks the model materials and requires the
exact capability contract; it never names MLX loader code, an MLX package
version, a device, a cache path, or a provider implementation. DAR capability
resolution selects an installed conforming MLX provider or fails before model
materialization or workflow-local execution.

## Functional Requirements

### FR-1: Mac-only lazy availability

Importing DAR or constructing the adapter shall not import MLX. On a non-Darwin
platform, the first embedding call shall raise a package-owned macOS-only error
before resolving assets or loading a dependency. On Darwin, a missing selected
MLX dependency shall raise a package-owned dependency error rather than an
unwrapped import error. There is no CPU, llama.cpp, remote, or generation-model
fallback.

### FR-2: Explicit assets and identity

The adapter shall use only an explicit local model path or existing locked
model-material resolution. It shall validate the resolved artifact layout and
the observed identity against the configured/locked expected model identity.
It shall not ambiently scan model directories, resolve a branch/tag, or accept
an invocation-time path or repository reference.

### FR-3: Validated bounded batch embeddings

The adapter shall validate nonempty finite input batches using the existing
embedding input contract, pass ordered plain text to the backend, and return
exactly one vector per input ID in the same order. It shall reject missing,
extra, duplicate, reordered, nonnumeric, nonfinite, empty, or
inconsistently-dimensioned vectors with a package-owned embedding error.

The direct adapter's static configuration shall set positive item-count,
per-item-byte, aggregate-byte, and vector-dimension limits. A workflow binding
may impose stricter limits but cannot relax the host/provider limits.

### FR-4: Conservative capability reporting

The adapter shall report local in-process MLX execution and `embeddings: True`
only after it has a backend conforming to the selected embedding API. It shall
report text generation, tool calling, structured output, streaming,
multimodal, and reranking as unsupported. A generation adapter remains
independently `embeddings: False`.

### FR-5: Upstream characterization gate

Before any default backend implementation, maintainers shall record the exact
upstream MLX/MLX-LM package release, public loading and embedding symbols,
accepted converted-model layout, result shape, pooling/normalization behavior,
model identity source, batch behavior, and failure taxonomy. The record must
use a fixed approved local artifact or upstream documentation and contain no
private prompts or model outputs.

If no public, stable embedding API is found, the feature remains unimplemented;
it must not call private internals or synthesize embeddings from generation
logits/hidden states.

### FR-6: Workflow-provider conformance

When the generic embedding capability is implemented, the MLX provider shall
pass its conformance matrix with a fake backend: capability identity, locked
material binding, availability changes, batch/vector validation, no fallback,
redaction, and pre-side-effect rejection. The generic workflow spec remains
the authority for snapshot and index-bundle behavior.

## Acceptance Criteria

- Package import and public factories work without MLX installed; fake tests
  run on non-macOS without a model or Metal.
- Unsupported-platform and missing-dependency failures occur before asset
  resolution or backend loading.
- Fake-backend tests prove ordered batch normalization and every invalid vector
  outcome in FR-3.
- Model identity/path tests reuse existing local-model failure taxonomy and
  never use a network call without injected test doubles.
- Capability metadata distinguishes the new embedding adapter from the existing
  generation adapter.
- A separately authorized Mac competency run records only model material,
  adapter/runtime version, batch sizes, dimension, latency, and aggregate
  error outcomes; vector values and input text are not retained.

## Delivery Gate

Implementation is blocked until the upstream-characterization record confirms a
public stable embedding API and `workflow-embedding-index-artifacts` has an
approved generic `embedding.execute.v1` contract. The direct caller-owned
adapter may be delivered first if its contract is useful independently, but it
must not claim workflow capability conformance until both gates are satisfied.
