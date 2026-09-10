# Workflow Embedding and Index Artifacts Specification

## Metadata

- Feature slug: `workflow-embedding-index-artifacts`
- Status: approved; implementation in progress
- Owner: dynamic-agent-runner workflow-package, model-material, and artifact boundaries
- Plan: `plan.md`
- Tasks: `tasks.md`
- Related specifications:
  - `specs/workflow-model-materials/spec.md`
  - `specs/workflow-capability-requirements/spec.md`
  - `specs/sandbox-workspace-runtime/spec.md`
  - `specs/local-tool-sandbox-hardening/spec.md`
  - `specs/authored-workflow-runtime-v1/spec.md`
  - `specs/llama-cpp-local-model/spec.md`

## Objective

Allow a durable sealed workflow package to transform one bounded, immutable
document-snapshot artifact into an opaque vector-index artifact using a locked
embedding model. The package may be sent to a compatible DAR receiver and run
without author-side services, model paths, setup commands, or indexing logic
provided at invocation time.

DAR owns package admission, sealed ingress and egress, model-material
verification, execution-capability selection, resource policy, tracing, and
result shaping. The workflow-local package owns document semantics, chunking,
metadata projection, vector-index format, and any optional semantic analysis.

## Problem Statement

The existing direct local embedding adapters let an application embed supplied
text, but they do not make embeddings available to a portable sealed workflow.
Nor does DAR have a generic contract for a multi-document input snapshot or an
opaque, durable index output. Letting a workflow select a live vector store,
read arbitrary directories, choose an embedding model, or write an arbitrary
destination would defeat the package's black-box and receiver-portability
boundaries.

This feature adds the narrow portable contract. It does not make DAR a
Markdown parser, a vector database, or a vault manager.

## Scope

This feature defines:

1. a versioned sealed document-snapshot input artifact;
2. an exact embedding execution capability and locked embedding material
   binding;
3. a bounded workflow-local embedding/index tool invocation boundary;
4. a versioned opaque index-bundle output artifact and manifest; and
5. deterministic incremental-rebuild identity and failure behavior.

Version 1 supports one input snapshot and one optional prior index bundle. It
produces one index bundle and one machine-readable coverage report. The host
may persist a returned bundle only through an explicit caller-side operation
after workflow completion; the workflow has no destination path or storage
credential.

## Non-Goals

This feature does not:

- prescribe Markdown, source-control, vault, filesystem-path, chunking,
  metadata, vector-store, SQLite, JSONL, embedding-dimension, or query API
  semantics;
- give a workflow arbitrary filesystem traversal, network access, subprocess
  access, database credentials, or a persistent destination;
- permit invocation-time selection of an embedding model, model revision,
  embedding provider, chunker, index format, or execution provider;
- make embeddings ordinary model-response text, traces, exceptions, or debug
  diagnostic content;
- require incremental updates, tag generation, source-note edits, or semantic
  annotation; or
- claim that every model-material profile supports embeddings.

## Terms and Trust Boundary

### Document snapshot

A document snapshot is a sealed invocation artifact. Its canonical manifest
contains opaque document IDs, content hashes, media types, byte lengths, and
the corresponding bounded document bytes. Document IDs are package-visible
identifiers, not host filesystem paths. The ingress host builds and validates
the snapshot before workflow code or model material is loaded.

The manifest is deterministically ordered by document ID and carries a
`snapshot_digest`, the SHA-256 of canonical manifest bytes plus the ordered
content hashes. A caller may retain its source/path mapping outside DAR; DAR
does not receive or return it.

### Index bundle

An index bundle is one opaque sealed workflow-result artifact. Its workflow
local bytes may contain vectors and any chosen index representation. Its
required generic manifest has only the following portable metadata:

- `format_version`;
- `snapshot_digest`;
- `embedding_material_lock_digest`;
- `embedding_capability_contract_digest`;
- `index_builder_digest`;
- `bundle_sha256`; and
- aggregate document, chunk, indexed, skipped, deleted, and error counts.

DAR validates the manifest shape, digest binding, byte limit, and relationship
to the invocation artifacts. It does not parse vectors or index contents.

The coverage report is a separately sealed, generic result artifact. It may
contain only its format version, the same binding digests, the prior-bundle
digest or `null`, aggregate counts, and a finite list of stable redacted error
classifications. It must not contain document IDs, paths, text, chunks,
vectors, index bytes, or workflow-local diagnostic fields.

### Embedding execution capability

`embedding.execute.v1` is a DAR capability contract, not workflow-provided
code. A compatible provider receives a locked embedding material binding and a
finite ordered batch of UTF-8 text items with caller-supplied opaque IDs. It
returns exactly one finite vector per ID, in input order, with a fixed positive
dimension for a single invocation. It exposes no provider path, credentials,
model-selection control, raw request, or raw response to workflow code.

The package declares this exact capability under
`workflow-capability-requirements`. The embedding material lock binds a
DAR-supported embedding runner/profile and immutable source material under
`workflow-model-materials`. The receiver resolves the provider before sealed
input ingress, model download, package-local tool load, or index materialization.

The package declares exactly one `embedding.execute.v1` requirement. It is not
an additional `bindings` entry: the capability ID itself identifies this
single-purpose operation, while the same material lock's existing `runner`
binding identifies the DAR-supported embedding runner/profile. DAR derives an
internal `EmbeddingExecutionBinding` from the material-execution binding and
the exact required capability contract. Its content is the material-lock and
runner/profile identities plus the embedding capability contract identity; it
contains no receiver provider ID, model path, or execution settings. The
receiver resolves that binding before ingress and revalidates the selected
provider immediately before embedding.

### E5.2 reference embedding material

The first authorized manual acceptance uses the following locked, local
llama.cpp material. This is an E5.2 fixture decision, not a version-1
requirement on other embedding-index workflow packages:

- repository: `ChristianAzinn/gte-small-gguf`;
- repository revision: `240acca7b64619cd22093a380dc266c4122d99b2`;
- file: `gte-small.Q4_K_M.gguf`; and
- SHA-256: `2b330c1579bac032397b48f5aa92b7b5ab2b94d72cc43cd15925db3ffd03fd61`.

The 29.2 MB Q4_K_M artifact is the upstream project's balanced recommended
quantization and is sufficient for a bounded functional acceptance run. DAR
must resolve it through the normal Hugging Face model cache, verify the pinned
file digest before use, and retain only its material-lock digest in acceptance
records. A caller may supply an explicit cache root, but this fixture does not
require a workflow-owned model copy or an invocation-time path.

### Workflow-local index builder

The package supplies one sealed, versioned index-builder asset and a sealed
descriptor that maps its exact asset digest to an approved index-builder host
ABI. The descriptor includes all chunking and index configuration; changing it
changes `index_builder_digest`. It cannot name an arbitrary module, provider,
filesystem path, network endpoint, subprocess, storage destination, or host
capability implementation.

DAR executes the asset only through the workflow-local tool sandbox and gives
it: the sealed snapshot records, optional prior-bundle bytes, bounded embedding
batches through the host-owned capability, and an empty bounded result
location. It returns the index-bundle bytes, manifest, and generic coverage
report only through that result location.

The descriptor's canonical bytes define `index_builder_digest`. It is an
identity, not executable configuration supplied by the caller.

## Functional Requirements

### FR-1: Sealed snapshot ingress

DAR shall admit only a declared snapshot artifact type with positive document,
per-document-byte, aggregate-byte, and media-type limits bound into the sealed
package policy. It shall reject duplicate IDs, noncanonical ordering, malformed
or mismatched hashes, unsupported media types, and excess limits before
workflow-local package import, model preparation, capability-provider load, or
index-builder execution. It shall not accept an invocation-time directory,
glob, URL, archive-extraction option, or source path.

### FR-2: Exact embedding binding

An embedding-index workflow shall declare one embedding model binding and an
exact `embedding.execute.v1` capability requirement. DAR shall verify its
model-material-lock digest, runner/profile compatibility, and selected provider
before every deferred side effect. Missing, disabled, changed, or
contract-incompatible providers fail closed with a redacted classification and
no fallback or package/model/index execution.

### FR-3: Bounded embedding batches

The host shall enforce package-declared positive limits, each no greater than a
DAR host ceiling, for items per batch, UTF-8 bytes per item, aggregate text
bytes, vector dimension, and total vectors per run. An embedding provider must
reject nonfinite vector values, wrong IDs, duplicate IDs, wrong order, varying
dimensions, and limit excess. Neither workflow code nor a provider can
override host resource, network, device, or model-cache policy.

### FR-4: Opaque index-bundle egress

The index builder may create only its empty bounded result location. DAR shall
read and seal exactly the declared index bundle and generic coverage report,
validate their byte limits and generic manifests, and return them as workflow
artifacts. The normal result, traces, diagnostics, and errors retain only
digests, counts, and redacted classifications. A caller may explicitly export
or persist a returned artifact after completion; DAR performs no automatic
destination write.

### FR-5: Incremental identity

When a package declares an optional prior index-bundle input, DAR shall bind it
by SHA-256 and supply it only as sealed bytes to the index builder. The builder
must record the prior bundle digest or `null` in its coverage report. DAR shall
require the resulting bundle manifest to bind the current snapshot digest,
embedding-material digest, capability-contract digest, and builder digest. A
changed binding is a rebuild boundary, not a compatible incremental update.

### FR-6: Determinism and resumability

Version 1 requires deterministic embedding execution. For identical package
bytes, snapshot bytes, optional prior bundle, locked material, provider
contract, and declared execution parameters, the workflow must emit identical
bundle and coverage-report bytes and manifest identities. A model/provider that
cannot meet that property is incompatible with version 1. A failed run returns
no partial index bundle. Resumption is a new run using a complete prior bundle,
never an unsealed mutable workspace.

### FR-7: Isolation and redaction

Package-local index-builder code remains subject to
`sandbox-workspace-runtime` and `local-tool-sandbox-hardening`. DAR has only a
host-only in-memory bounded result collector today. General-release and
untrusted-package execution require that collector to be wired through an
approved OS/runtime isolation backend. During personal scenario evaluation, an
explicit local host-owner opt-in may execute the exact sealed builder digest
through the experimental profile; it makes no isolation claim and does not
admit a package received from another party. Raw document content, chunks, vectors,
index bytes, and source-path mappings are sensitive artifacts and must not
enter ordinary traces, error text, capability reports, or debug diagnostics.

## Acceptance Criteria

- Fake-only tests prove malformed or oversized snapshots fail before any
  package import, capability resolution/provider load, model materialization,
  embedding call, or index-builder execution.
- Fake-only tests prove exact material/capability binding, batch limits,
  vector-result validation, and no-fallback failure behavior.
- Fake-only end-to-end tests prove a deterministic sealed snapshot produces a
  sealed index bundle and coverage report, without source paths, vectors, or
  bundle bytes appearing in ordinary results or traces.
- Incremental tests prove changed snapshot, model material, capability, or
  builder identity invalidates prior-bundle compatibility.
- The first real-model acceptance, if authorized later, records only package,
  artifact, provider-contract, and aggregate-count digests; it does not make a
  live model call from pytest or CI.

## Dependencies and Delivery Gate

Implementation depends on an approved extension of `workflow-model-materials`
for embedding runners/profiles, an approved `embedding.execute.v1` provider
contract in `workflow-capability-requirements`, and the artifact/result-location
isolation required by `sandbox-workspace-runtime`. This spec authorizes neither
those changes nor arbitrary package-local execution by itself.
