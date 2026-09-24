# DAR Embedding Adapter Protocol Specification

## Metadata

- Feature slug: `embedding-adapter-protocol`
- Artifact type: new public interface specification
- Status: proposed
- Owner: dynamic-agent-runner embedding and model-provider boundaries
- Related artifacts:
  - [`external-model-adapter-protocol`](../external-model-adapter-protocol/spec.md)
  - [`mlx-local-embedding-adapter`](../mlx-local-embedding-adapter/spec.md)
  - [`llama-cpp-local-model`](../llama-cpp-local-model/spec.md)
  - [`workflow-model-materials`](../workflow-model-materials/spec.md)

## Objective

Define an exported, fail-closed BYOM protocol for text embedding models. The
protocol gives MLX, llama.cpp, and future embedding providers one host-facing
contract while keeping vector-index authority, material preparation, and
publication outside the adapter.

## Why this is separate

`DARExternalAdapterProtocol` is a text-generation protocol. Embeddings have a
different request/response shape, batching behavior, dimensionality contract,
and data-handling risk. Adding embedding fields to the generation protocol
would make both interfaces shallower and would weaken capability admission.

## Proposed public contract

The exported protocol is named `DAREmbeddingAdapterProtocol` with wire ID
`dar.embedding-adapter.v1`. It must provide:

```python
class DAREmbeddingAdapterProtocol(Protocol):
    adapter_id: str
    protocol_id: Literal["dar.embedding-adapter.v1"]
    protocol_version: Literal["1.0"]

    def describe(self) -> EmbeddingAdapterDescriptor: ...
    def health(self) -> EmbeddingAdapterHealth: ...
    def embed(
        self,
        request: EmbeddingRequest,
        *,
        context: DAREmbeddingRequestContext,
    ) -> EmbeddingBatchResult: ...
```

The exact Python names may be refined during planning, but the semantics below
are normative.

## Descriptor and admission

The immutable descriptor binds adapter ID, provider ID, canonical model ID,
execution location, vector dimension, dtype/normalization declaration,
maximum batch size, maximum input tokens, and a contract digest. Dimension,
normalization, and model/material identity are exact admission facts; callers
cannot override them per request.

Health is bounded and redacted. A ready adapter must have verified the exact
model/material binding and runtime ABI required by its descriptor.

## Request and response

Requests contain an ordered finite batch of text items, per-call deadline and
cancellation context, and no workflow tools, credentials, raw filesystem
paths, or vector-index handles. Responses contain one finite vector per input,
the exact descriptor identity, and aggregate scalar telemetry only.

The adapter must reject empty, oversized, malformed, or dimensionally invalid
requests before provider dispatch. It must preserve input order and reject
partial or duplicate result batches. NaN, infinity, non-finite values, and
unexpected vector dimensions are invalid responses.

## Ownership and safety

DAR owns request validation, admission, cancellation, redaction, tracing,
batch limits, and response-shaping. The provider owns tokenization, native
runtime calls, and provider-specific model loading. The vector-index host owns
corpus extraction, index construction, publication, retention, and deletion.
The adapter never receives a separately supplied corpus, prior generation, or
index profile.

## Provider migration slices

- Adapt the existing MLX embedding adapters without changing their sealed
  material or ABI contracts.
- Adapt the existing llama.cpp embedding adapter under the same descriptor and
  result rules.
- Add deterministic fake-backed parity tests and support-matrix rows.
- Keep provider-native embedding factories available during migration.

## Non-goals

- No text generation or tool calling.
- No multimodal embeddings in v1.
- No automatic model downloads or arbitrary cache scanning.
- No index construction, vector search, persistence, or publication.
- No cross-provider vector compatibility claim merely because dimensions match.
- No live model or external-service calls in unit tests.

## Acceptance criteria

- A descriptor with a changed dimension, normalization, ABI, or material digest
  is rejected before dispatch.
- A malformed or oversized batch fails without invoking the provider.
- A valid batch returns ordered, finite vectors with the declared dimension.
- Cancellation and deadlines prevent a second request or fallback.
- Provider errors become redacted package-owned embedding errors.
- MLX and llama.cpp parity tests pass using controlled fakes, and no receipt is
  transferable across provider, model, ABI, or material identity.
