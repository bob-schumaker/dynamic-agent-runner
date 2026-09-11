# macOS Generalized MLX Embedding Execution Specification

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

Provide a lazy, in-process, macOS-only embedding execution implementation for
a sealed workflow. DAR supplies platform/dependency admission, a registry of
bounded generic MLX encoder ABIs, material-identity verification, and result
validation. Workflow construction supplies immutable material and a sealed
declarative encoder descriptor. DAR does not select an upstream embedding
model, architecture configuration, tokenizer, pooling rule, normalization
rule, or license.

The provider is optional: ordinary DAR imports, non-macOS hosts, CI, and
existing llama.cpp workflows require neither MLX nor Metal.

## Problem Statement

`mlx-lm` is generation-oriented. A durable workflow needs MLX embedding
execution without turning a trial model into a DAR release contract or allowing
untrusted package code to load arbitrary models.

### Generalized embedding-model support

The embedding support system is not a catalog of named models. A workflow
author selects and locks every source or prepared material file, revision,
license decision, tokenizer, and execution descriptor during construction.
The descriptor selects one exact receiver-supported architecture ABI. DAR
therefore supports a new compatible model without a DAR change when its locked
materials validate under an installed ABI; it needs a DAR change only for a
new architecture ABI or an incompatible ABI revision. `embedding.execute.v1`
is the architecture-neutral capability presented to workflow-local code. MLX
is one receiver implementation of that capability; other receiver
implementations may satisfy the same capability through their own supported
execution ABI without changing workflow semantics.

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

### Generic MLX encoder ABI registry

DAR owns versioned, reviewed execution ABIs, initially a BERT-style encoder ABI
implemented with public `mlx.core` APIs. A runner capability resolves
one receiver-installed, pure descriptor-validator registry. That registry first
resolves the descriptor's exact ABI ID, version, and contract digest, then
validates its finite schema without importing a framework or reading material.
An ABI defines descriptor vocabulary and deterministic interpretation; it does
not name an upstream model. A workflow may use any locked material set whose
descriptor validates against an installed ABI. A new architecture family needs
a later reviewed DAR ABI, but another model within an existing ABI does not
require a DAR release.

### Initial closed encoder ABI: `bert-encoder-mlx-v1`

The initial ABI is deliberately narrow. Its exact identity is
`{"id":"bert-encoder-mlx-v1","version":"1","contract_digest":"2179662461bf786c7f55d88d9e3454a3d4dc59f5e818a96e248847abc62e4420"}`.
It covers BERT encoder weights represented in the ABI's fixed safetensors
layout and a WordPiece tokenizer; it does not claim compatibility with every
encoder-like model.

For this ABI, `execution-descriptor.json` must declare exactly the sorted
material roles `tokenizer` and `weights`. Its `abi_fields` object has exactly
these keys:

```json
{
  "tokenizer": {
    "role": "tokenizer",
    "format": "wordpiece-json-v1",
    "normalization": "nfc" | "nfc-lowercase",
    "pre_tokenizer": "bert-basic-v1",
    "special_token_ids": {"cls": 101, "sep": 102, "pad": 0, "unk": 100},
    "truncation": "longest-first"
  },
  "encoder": {
    "weights_role": "weights",
    "tensor_layout": "bert-encoder-safetensors-v1",
    "dtype": "float16" | "bfloat16" | "float32",
    "vocab_size": 1,
    "hidden_size": 1,
    "layers": 1,
    "attention_heads": 1,
    "intermediate_size": 1,
    "max_positions": 1,
    "type_vocab_size": 1
  },
  "pooling": "cls" | "masked_mean",
  "normalization": "none" | "l2",
  "limits": {
    "max_items": 1,
    "max_item_bytes": 1,
    "max_aggregate_bytes": 1,
    "max_tokens": 1,
    "max_vectors": 1,
    "max_memory_bytes": 1,
    "max_tokenizer_bytes": 1,
    "max_weights_bytes": 1,
    "max_safetensors_header_bytes": 1,
    "max_conformance_fixture_bytes": 1
  },
  "conformance": {
    "fixture_filename": "conformance-fixture.json",
    "fixture_sha256": "<64 lowercase hexadecimal characters>",
    "precision": "float32",
    "metric": "max_abs",
    "max_error": 0.0
  }
}
```

All integer fields are plain JSON integers (never booleans) and positive except
the four non-negative token IDs. The special-token IDs are distinct and less
than `vocab_size`; `hidden_size` is divisible by `attention_heads`; and
`max_tokens` is no greater than `max_positions`. The validator bounds strings
at 128 bytes, accepts at most two material roles, and applies these ABI maxima:
`vocab_size` 500,000; `hidden_size` 4,096; `layers` 48;
`attention_heads` 64; `intermediate_size` 16,384; `max_positions` 4,096;
`type_vocab_size` 16; `max_items` 256; `max_item_bytes` 1 MiB;
`max_aggregate_bytes` 16 MiB; `max_tokens` 4,096; `max_vectors` 16,384; and
`max_memory_bytes` and `max_weights_bytes` 8 GiB; `max_tokenizer_bytes` and
`max_conformance_fixture_bytes` 16 MiB; and `max_safetensors_header_bytes`
16 MiB. `max_error` is finite, non-negative, and at most `0.1`.

The output vector dimension is exactly `encoder.hidden_size`; it is not a
separate descriptor setting.

`wordpiece-json-v1` is a closed tokenizer-asset grammar, not a request to
execute a tokenizer package. Its UTF-8 JSON root has `model`, `normalizer`,
and `pre_tokenizer` objects. `model` has `type: "WordPiece"`, a string
`unk_token`, and a `vocab` object mapping exactly `V` distinct nonempty token
strings to each integer in `[0, V)`, once. The token at the declared `unk` ID
equals `unk_token`. `normalizer` has `type: "BertNormalizer"` and a Boolean
`lowercase` that is false for `nfc` and true for `nfc-lowercase`.
`pre_tokenizer` has `type: "BertPreTokenizer"`. Unknown fields within those
three required objects may not alter these semantics; no tokenizer asset may
provide an import, executable callback, model path, or remote reference.

The ABI owns this complete safetensors tensor-key and shape grammar, where `H`,
`I`, `L`, `V`, `P`, and `T` are respectively `hidden_size`,
`intermediate_size`, `layers`, `vocab_size`, `max_positions`, and
`type_vocab_size`; every listed tensor uses the declared `dtype`:

| Keys | Shape |
| --- | --- |
| `embeddings.word_embeddings.weight` | `[V, H]` |
| `embeddings.position_embeddings.weight` | `[P, H]` |
| `embeddings.token_type_embeddings.weight` | `[T, H]` |
| `embeddings.LayerNorm.{weight,bias}` | `[H]` |
| `encoder.layer.{0..L-1}.attention.self.{query,key,value}.{weight,bias}` | `[H, H]` for `weight`; `[H]` for `bias` |
| `encoder.layer.{0..L-1}.attention.output.dense.{weight,bias}` | `[H, H]` for `weight`; `[H]` for `bias` |
| `encoder.layer.{0..L-1}.attention.output.LayerNorm.{weight,bias}` | `[H]` |
| `encoder.layer.{0..L-1}.intermediate.dense.{weight,bias}` | `[I, H]` for `weight`; `[I]` for `bias` |
| `encoder.layer.{0..L-1}.output.dense.{weight,bias}` | `[H, I]` for `weight`; `[H]` for `bias` |
| `encoder.layer.{0..L-1}.output.LayerNorm.{weight,bias}` | `[H]` |

No other tensor key is accepted. The descriptor provides no regex, expression,
arbitrary tensor predicate, import, loader, runtime-version, device, or provider
field. After verified material resolution, the backend validates the actual
tokenizer bytes and safetensors header against those byte ceilings and this
grammar before allocation. It computes with checked integer arithmetic the
declared parameter bytes plus `4 * max_items * max_tokens * hidden_size`
activation bytes and rejects an estimate greater than the tighter descriptor or
host memory ceiling before MLX allocation. This is a pre-allocation admission
bound, not a claim that in-process MLX gives a hard memory limit.

The fixture filename is exactly `conformance-fixture.json`, a unique regular
package-manifest entry; its SHA-256 and descriptor byte ceiling are verified
before it is parsed. It supplies synthetic inputs, masks, expected vectors, and
tolerance evidence but does not select a model or authorize the provider. The
receiver's MLX dependency/version admission remains host-owned, not descriptor
data.

The ABI fixes encoder math as follows: embed each token by summing word,
absolute-position, and token-type vectors, then apply LayerNorm with population
variance and epsilon `1e-12`; do not apply dropout. Convert a binary attention
mask to additive `0` for accepted keys and `-10000` for rejected keys. For each
layer, compute scaled dot-product attention as `QKᵀ / sqrt(H / heads)`, add the
mask, and softmax over the final (key) axis; apply the output dense layer,
residual, and the same LayerNorm. Apply the exact-error-function GELU
`0.5 * x * (1 + erf(x / sqrt(2)))` in the intermediate block, then output
dense, residual, and LayerNorm. `pooling: "cls"` returns the final hidden state
at position zero; it never uses a pooler projection, and a pooler tensor is not
accepted. `pooling: "masked_mean"` averages final hidden states over accepted
mask positions. Finally apply the declared normalization. These are ABI
constants, not descriptor settings.

The backend shall:

- lazy-import `mlx.core` only on the first eligible embedding call;
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

Before tokenization or MLX allocation/evaluation, DAR shall canonicalize and
validate the descriptor through the exact receiver-installed ABI contract, then
bind its package-declared role references to the parsed material lock.
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
- Tests prove arbitrary locked material sets are accepted only through a
  supported declarative ABI, while generation MLX behavior is unchanged.
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
