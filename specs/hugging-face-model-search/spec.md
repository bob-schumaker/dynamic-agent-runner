# Hugging Face model search specification

## Metadata

- Feature slug: `hugging-face-model-search`
- Mode: `guided`
- Artifact type: authoritative SDD feature specification
- Status: future feature spec
- Version: `1.0`
- Owner: repository maintainers and future implementers of public Hugging Face
  discovery support
- Next gate: planning approval before any implementation begins
- Approval state: user-directed authoritative feature spec for public Hugging
  Face model discovery
- Related artifacts:
  - `specs/dynamic-agent-runner/spec.md`
  - `specs/llama-cpp-local-model/spec.md`
  - `src/dynamic_agent_runner/local_models.py`
  - `src/dynamic_agent_runner/__init__.py`
  - `src/dynamic_agent_runner/api.py`

## Objective

Expose a repository-owned public API for searching Hugging Face models so
clients can discover candidate models through `dynamic-agent-runner` without
reaching into the package's internal local-model download wiring or depending on
`huggingface_hub` directly.

## Problem Statement

The repository already has a narrow Hugging Face integration seam in
`src/dynamic_agent_runner/local_models.py`, but that seam is strictly internal to
local-model asset resolution:

- it supports runtime-owned file and snapshot references
- it lazily imports `huggingface_hub` only for downloads
- it does not expose Hub search or repository discovery through the public
  package surface
- it does not give downstream callers a stable repository-owned way to inspect
  available models before configuring local endpoints or model assets

That leaves callers with two bad options: either they bypass the package and use
`huggingface_hub` directly, or they guess model identifiers from documentation
and examples. The repository needs a public, minimal, repository-owned discovery
surface that lets clients look for models while preserving the existing package
boundary and without turning the library into a full general-purpose Hugging Face
SDK replacement.

## Users

- Downstream Python callers that use `dynamic-agent-runner` as their integration
  surface and need to discover candidate Hugging Face models.
- Runtime maintainers who want a stable public package API for Hugging Face
  discovery rather than ad hoc imports from private modules.
- Future local-model workflows that need a documented discovery seam before
  runtime-owned model download or endpoint configuration happens.

## User Stories

- As a client of `dynamic-agent-runner`, I want to search Hugging Face models
  through the package's public API, so I do not need to add my own direct Hub
  dependency just to discover model ids.
- As a runtime maintainer, I want Hugging Face discovery to use repository-owned
  response types and error boundaries, so external SDK details do not leak into
  the package contract.
- As a caller preparing local-model execution, I want enough model metadata to
  shortlist candidate models, so I can choose a repo id before configuring
  downloads or local endpoint aliases.

## Existing Runtime Context

- `specs/dynamic-agent-runner/spec.md` defines a package-directory-first runtime
  with explicit public API boundaries and a preference for repository-owned
  contracts over direct third-party leakage.
- `specs/llama-cpp-local-model/spec.md` already treats Hugging Face as a source
  of model assets for local execution, but only through download references and
  not through caller-visible model discovery.
- `src/dynamic_agent_runner/local_models.py` currently exposes:
  - `HuggingFaceModelFileReference`
  - `HuggingFaceSnapshotReference`
  - runtime-owned download helper loading through `huggingface_hub`
- `src/dynamic_agent_runner/__init__.py` currently exports local endpoint helper
  APIs but does not export any Hugging Face search/discovery surface.
- The current package direction favors small repository-owned seams like
  `OpenAIProviderConfig` and `create_local_openai_adapter(...)` instead of making
  callers depend on raw provider SDK interfaces.

## Scope

This feature specification covers:

1. a public repository-owned API for searching Hugging Face models
2. repository-owned result dataclasses or equivalent stable value objects for
   caller-visible model search metadata
3. repository-owned error translation for Hugging Face discovery failures
4. public package exports for the approved discovery surface
5. tests and documentation for the public discovery contract

This feature specification does not cover:

1. model downloads beyond the existing local-model asset-resolution behavior
2. a general wrapper for all Hugging Face Hub endpoints
3. authentication, upload, delete, repo creation, or write-side Hub operations
4. automatic local-model endpoint configuration from search results
5. workflow-manifest schema changes for embedding Hub discovery directly into
   runtime package artifacts

## Assumptions and Clarifications

- This feature is about **public model discovery/search** for library clients,
  not about exposing every raw `huggingface_hub` capability.
- "Expose the Hugging Face API outside of our package" is interpreted here as
  creating a supported public package surface for the subset needed to let
  clients look for models.
- The first approved discovery surface should remain read-only.
- Search should be useful without forcing callers to understand internal download
  helper wiring or private module paths.
- If later work needs richer Hub functionality, that work requires a separate
  follow-up spec rather than broadening this feature silently.

## Authoritative Boundary

- This artifact is the authoritative SDD spec for public Hugging Face model
  discovery in this repository.
- Future planning and implementation work for this feature must derive from this
  spec rather than from ad hoc chat history or private-module behavior.
- This spec owns **what** public Hugging Face discovery must do and **why** the
  repository should expose it; later `plan.md`, `tasks.md`, and `validation.md`
  artifacts should own technical approach, execution order, and evidence.
- Existing internal download behavior in `local_models.py` is supporting context
  only and is not the authoritative public contract for this feature.

## Functional Requirements

### FR-1: Provide a public model-search entry point

The package must expose a supported public API that lets callers search Hugging
Face models through `dynamic-agent-runner`.

Acceptance criteria:

- Given a client imports the package root or another approved public module, when
  the client needs to search for models, then a documented public entry point is
  available without importing private helpers from `local_models.py`.
- Given a caller provides a free-text search query, when the discovery API runs,
  then the package returns matching model results using a repository-owned public
  contract.
- Given the repository keeps its current public-surface discipline, when this API
  is added, then the package documents which function or class is the canonical
  discovery entry point.

### FR-2: Return repository-owned model metadata objects

The public discovery API must return repository-owned model metadata rather than
leaking raw Hugging Face SDK objects as the primary contract.

Acceptance criteria:

- Given a search call succeeds, when results are returned, then each result is
  represented by a repository-owned value object or equivalent mapping contract
  with stable fields.
- Given callers need to identify a model for later runtime configuration, when a
  result is inspected, then the contract includes the model's repository id.
- Given callers are choosing among search results, when a result is inspected,
  then the contract includes a small approved metadata set sufficient for
  discovery decisions, such as display name, pipeline/task hints, tags, likes,
  download counts, or similar repository-approved summary fields.
- Given upstream SDK payloads may contain many more fields, when the repository
  shapes public results, then unsupported fields remain optional or excluded
  rather than automatically becoming part of the public contract.

### FR-3: Support useful caller-side filtering without full SDK exposure

The discovery surface must support a minimal approved filter set that materially
helps callers find relevant models.

Acceptance criteria:

- Given a caller wants narrower results, when the public API is invoked, then it
  supports a repository-approved subset of search inputs beyond the free-text
  query.
- Given filter support is implemented, when the feature is documented, then the
  allowed filter set is explicit and intentionally limited rather than described
  as a transparent pass-through for all upstream SDK parameters.
- Given filter inputs are omitted, when a basic query is executed, then sensible
  default search behavior still returns discovery results.

### FR-4: Translate Hugging Face discovery failures into package-owned errors

The public discovery surface must preserve repository-owned failure semantics.

Acceptance criteria:

- Given the `huggingface_hub` dependency is unavailable, when a caller invokes
  the public discovery API, then the package raises a repository-owned error with
  a clear message instead of exposing an opaque import failure as the primary
  contract.
- Given the upstream discovery call fails due to connectivity, service, or
  protocol issues, when the package surfaces the failure, then callers receive a
  repository-owned exception or clearly documented error boundary.
- Given search fails, when a caller handles the error, then the failure message
  indicates that the problem occurred during Hugging Face model discovery.

### FR-5: Preserve a read-only discovery boundary

This feature must expose read-only model search and must not silently broaden
into write-side Hub operations.

Acceptance criteria:

- Given this feature lands, when clients use the new public API, then the API is
  limited to search/discovery and related read-only metadata retrieval approved
  by this spec.
- Given future work needs authenticated mutation or full Hub management, when
  that need arises, then it is treated as a new feature rather than included
  implicitly here.

### FR-6: Keep testing deterministic and live-network-free by default

The discovery API must be testable without live Hugging Face network access.

Acceptance criteria:

- Given unit tests for the public discovery surface, when they run in CI, then
  they use fakes, stubs, or monkeypatched discovery helpers instead of live Hub
  traffic.
- Given the implementation wraps `huggingface_hub`, when tests validate request
  shaping or result normalization, then those tests assert repository-owned
  behavior rather than upstream network behavior.
- Given documentation examples are added, when they are validated in tests or
  doctest-like checks, then they do not require live remote access.

## Non-Goals

- No commitment to expose every `huggingface_hub` search parameter.
- No promise to expose raw upstream result objects as a stable public API.
- No direct integration of Hub search into workflow execution or runtime
  manifest loading in this feature.
- No implementation of local endpoint startup, model downloading, or GGUF file
  selection from search results in this feature.
- No automatic compatibility guarantee that every discovered model is runnable by
  this runtime.

## Design Constraints

- Follow the repository's existing pattern of small, repository-owned public
  seams instead of broad third-party SDK passthroughs.
- Keep the first public discovery surface minimal and reviewable.
- Prefer additive public API changes over breaking changes to existing local-model
  helpers.
- Preserve separation between model discovery and model execution.
- Preserve the current internal download path in `local_models.py` unless a later
  approved plan explicitly refactors it.

## Risks and Compatibility Notes

- Hugging Face search payloads may evolve, so the public contract should be a
  normalized subset rather than a mirror of upstream objects.
- Some search metadata may be incomplete or absent for certain repos, so result
  fields may need optionality.
- A too-broad pass-through API would create long-term compatibility burden for
  every upstream Hub search option; this spec deliberately avoids that.
- Callers may incorrectly assume that discovered models are automatically
  compatible with existing local-model helpers; documentation must separate
  discovery from execution compatibility.

## Open Questions for Planning

- Which exact public entry point shape should be canonical: a function, a small
  client object, or both?
- Which result fields are the minimum stable set for useful model discovery in
  this repository?
- Which limited filter parameters should the repository support in the first
  slice?
- Should the package add a dedicated Hugging Face discovery error hierarchy or
  reuse existing model/runtime error types with clearer messages?
- Should a separate lightweight module own public discovery behavior, or should
  it live alongside `local_models.py` while keeping download internals private?
