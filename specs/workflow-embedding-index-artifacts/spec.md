# Workflow Embedding and Index Artifacts Specification

## Metadata

- Feature slug: `workflow-embedding-index-artifacts`
- Status: E1–E5 experimental bridge complete; portable package-runtime work is planned
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
  - `specs/workflow-locked-inference-callback/spec.md`

## Objective

Allow a durable sealed workflow package to transform one bounded, immutable
document-snapshot artifact into an opaque vector-index artifact using a locked
embedding material set. The package may be sent to a compatible DAR receiver
and run without author-side services, model paths, setup commands, or indexing
logic provided at invocation time.

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

Version 1 supports one input snapshot and one optional prior index-bundle
result pair: opaque bundle bytes plus their required generic manifest. It
produces one index-bundle result pair and one machine-readable coverage report.
The host may persist returned artifacts only through an explicit caller-side
operation after workflow completion; the workflow has no destination path or
storage credential.

## Non-Goals

This feature does not:

- prescribe Markdown, source-control, vault, filesystem-path, chunking,
  metadata, vector-store, SQLite, JSONL, embedding-dimension, or query API
  semantics;
- give a workflow arbitrary filesystem traversal, network access, subprocess
  access, database credentials, or a persistent destination;
- permit invocation-time selection of embedding material, model revision,
  architecture ABI, embedding provider, chunker, index format, or execution
  provider;
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

### Index-bundle result pair

An index bundle is one opaque sealed workflow-result artifact. Its workflow
local bytes may contain vectors and any chosen index representation. Its
required companion index manifest is a separately sealed JSON artifact with
only the following portable metadata:

- `format_version`;
- `snapshot_digest`;
- `embedding_material_lock_digest`;
- `embedding_capability_contract_digest`;
- `index_builder_digest`;
- `bundle_sha256`; and
- aggregate document, chunk, indexed, skipped, deleted, and error counts.

DAR validates the manifest shape, the `bundle_sha256` binding to the opaque
bundle bytes, byte limits, and its relationship to the invocation artifacts.
It does not parse vectors or index contents. The bundle and manifest are one
logical result and are always sealed and published together.

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
`workflow-capability-requirements`. The embedding material lock binds immutable
source material and a workflow-owned sealed execution descriptor interpreted by
a DAR-supported generic embedding ABI under
`workflow-model-materials`. The ABI, rather than a named model, determines
compatible execution. The receiver resolves the provider before sealed input
ingress, material download, package-local tool load, or index materialization.

The package declares one `embedding.execute.v1` requirement and, because it
has a model-material declaration, one additional DAR-owned runner capability
requirement named by `capability_requirements.bindings.runner`. The runner
requirement identifies the compatible generic execution ABI; it is not an `embedding`
binding or a provider selector. DAR derives an internal
`EmbeddingExecutionBinding` from that generic material-execution binding and
the exact embedding capability contract. Its content is the material-lock,
execution-descriptor, descriptor-ABI, and runner-ABI identities plus the
embedding capability contract identity; it
contains no receiver provider ID, model path, or execution settings. The
receiver resolves that binding before ingress and revalidates the selected
provider immediately before embedding.

### Workflow-local index builder

The package supplies one sealed, versioned index-builder asset and a sealed
descriptor that maps its exact asset digest to an approved index-builder host
ABI. The descriptor includes all chunking and index configuration; changing it
changes `index_builder_digest`. It cannot name an arbitrary module, provider,
filesystem path, network endpoint, subprocess, storage destination, or host
capability implementation.

DAR executes the asset only through the workflow-local tool sandbox and gives
it: the sealed snapshot records, an optional validated prior index-bundle
result pair, bounded embedding batches through the host-owned capability, and
an empty bounded result location. It returns the index-bundle bytes, manifest,
and generic coverage report only through that result location.

The descriptor's canonical bytes define `index_builder_digest`. It is an
identity, not executable configuration supplied by the caller.

### Portable package runtime

E1–E5 provide a host-private experimental bridge, not a portable workflow
package path. A portable package uses the generic
`sealed-artifact-runner.json` descriptor and its normal package manifest. The
outer descriptor declares only generic artifact roles, media types, schemas,
limits, the sealed asset, and bounded callback requirements. It declares:

- required `snapshot` JSON input;
- optional `prior_bundle` opaque-bytes and `prior_index_manifest` JSON inputs,
  which are both present or both absent;
- required `coverage_report` JSON, `index_bundle` opaque-bytes, and
  `index_manifest` JSON outputs in the generic descriptor's lexical role
  order; and
- exactly one `embed` callback whose capability requirement is
  `embedding.execute.v1`.

The package manifest lists the sealed builder asset, the descriptor, all JSON
schemas, and the canonical child-contract record. Builder configuration is
sealed in the asset bytes. The v1 builder child-contract body has exactly
`embed_request_schema_digest` and `embed_response_schema_digest`, each naming
one declared JSON schema; it defines only the embedding callback payloads. DAR
interprets only the child contract's common generic envelope. The child
contract's digest, together with the outer asset digest, defines the portable
builder identity as
the SHA-256 of the canonical JSON object
`{"asset_digest": asset_digest, "builder_contract_digest": child_contract_digest}`.
That value is the `index_builder_digest` bound into the index manifest and
coverage report. The package's existing locked material declaration supplies
the embedding material role, while the outer callback requires the exact
capability. DAR verifies those declarations and resolves all required
capabilities/materials before it loads the asset or accepts the input.

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

An embedding-index workflow shall declare one embedding material/execution
binding, the runner capability required by that material declaration, and an
exact `embedding.execute.v1` capability requirement. DAR shall verify its
model-material-lock digest, execution-descriptor/runner-ABI compatibility, and
selected provider
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
read and atomically seal exactly the declared `coverage_report`, `index_bundle`,
and `index_manifest` outputs, validate their byte limits and generic JSON
schemas, and return them as workflow artifacts only after the consumer verifies
the bundle checksum and common invocation bindings. The normal result, traces,
diagnostics, and errors retain only digests, counts, and redacted
classifications. A caller may explicitly export or persist a returned artifact
after completion; DAR performs no automatic destination write.

### FR-5: Incremental identity

When a package declares incremental operation, DAR shall admit a paired prior
index bundle and index manifest, validate the manifest's bundle checksum and
binding identities, and supply both only as sealed bytes to the index builder.
The builder must record the prior bundle digest or `null` in its coverage
report. DAR shall require the resulting bundle manifest to bind the current
snapshot digest, embedding-material digest, capability-contract digest, and
builder digest. A changed binding is a rebuild boundary, not a compatible
incremental update.

### FR-6: Determinism and resumability

Version 1 requires deterministic embedding execution. For identical package
bytes, snapshot bytes, optional prior result pair, locked material, provider
contract, and declared execution parameters, the workflow must emit identical
bundle, manifest, and coverage-report bytes and identities. A model/provider
that cannot meet that property is incompatible with version 1. A failed run
returns no partial index-bundle result pair. Resumption is a new run using a
complete validated prior result pair, never an unsealed mutable workspace.

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

### FR-8: Portable invocation

DAR shall admit an embedding-index ZIP only when its generic descriptor binds
the complete artifact and builder contract, all material/capability bindings
resolve before package-asset loading, and the exact package/asset has the
required runtime authorization. The experimental profile may serve an
explicitly owner-authorized package; foreign/untrusted package execution stays
gated on the approved isolation backend.

## Acceptance Criteria

- Fake-only tests prove malformed or oversized snapshots fail before any
  package import, capability resolution/provider load, model materialization,
  embedding call, or index-builder execution.
- Fake-only tests prove exact material/capability binding, batch limits,
  vector-result validation, and no-fallback failure behavior.
- Fake-only end-to-end tests prove a deterministic sealed snapshot produces an
  atomically sealed bundle, index manifest, and coverage report, without source
  paths, vectors, or bundle bytes appearing in ordinary results or traces.
- Incremental tests prove changed snapshot, model material, capability, or
  builder identity invalidates prior-bundle compatibility.
- The first real-model acceptance, if authorized later, records only package,
  artifact, provider-contract, and aggregate-count digests; it does not make a
  live model call from pytest or CI.
- ZIP round-trip vectors prove receiver invocation uses the sealed descriptor,
  never an injected builder or caller-supplied model configuration.

## Dependencies and Delivery Gate

Implementation depends on an approved DAR-owned generic embedding execution ABI
using
the existing `workflow-model-materials` and `bindings.runner` contract, an
approved `embedding.execute.v1` provider contract in
`workflow-capability-requirements`, and the artifact/result-location isolation
required by `sandbox-workspace-runtime`. This spec authorizes neither those
changes nor arbitrary package-local execution by itself.
