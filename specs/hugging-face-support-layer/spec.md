# Hugging Face Support Layer Specification

## Metadata

- Feature slug: `hugging-face-support-layer`
- Mode: `light`
- Artifact type: future internal infrastructure feature specification
- Status: proposed future internal refactor; current search and local-model
  download helpers each wrap `huggingface_hub` independently
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Related feature specs:
  - `specs/hugging-face-model-search/spec.md`
  - `specs/llama-cpp-local-model/spec.md`
- Related implementation surfaces:
  - `src/dynamic_agent_runner/hugging_face_models.py`
  - `src/dynamic_agent_runner/local_models.py`
  - `src/dynamic_agent_runner/errors.py`

## Objective

Define a small internal Hugging Face support layer that centralizes shared
`huggingface_hub` import, SDK-call, and error-normalization mechanics while
preserving the separate public contracts for model discovery and local-model
asset resolution.

## Problem Statement

The repository now has two Hugging Face touchpoints:

- `hugging_face_models.py` provides public read-only model discovery through
  `search_hugging_face_models(...)` and package-owned search results/errors.
- `local_models.py` resolves explicit local-model file and snapshot references
  using `hf_hub_download(...)` and `snapshot_download(...)` as part of
  llama.cpp-oriented local-model asset preparation.

Those touchpoints intentionally serve different contracts. Model search finds
candidate repositories and returns metadata. Local-model resolution downloads or
locates exact assets and reports local-model preparation failures.

The duplication worth removing is not the domain behavior; it is the low-level
SDK boundary mechanics: lazy importing `huggingface_hub`, calling read-only Hub
APIs, and translating SDK/import/network failures into package-owned errors with
consistent context.

## Scope

This feature covers:

1. an internal helper module for read-only Hugging Face SDK access
2. shared lazy import handling for `huggingface_hub`
3. shared read-only call wrappers for model search, file download, and snapshot
   download
4. consistent exception normalization hooks for callers that need
   domain-specific package errors
5. deterministic tests that use fakes and do not require live Hub network access

This feature does not cover:

1. replacing the public `search_hugging_face_models(...)` contract
2. making search results automatically drive local-model downloads
3. broadening the package into a general Hugging Face Hub SDK wrapper
4. authenticated write-side Hub operations
5. changing local-model cache precedence or offline-policy semantics
6. adding workflow-manifest fields for Hub search or download behavior

## Boundary Rules

- Model discovery remains owned by
  `specs/hugging-face-model-search/spec.md`.
- Local-model file and snapshot resolution remains owned by
  `specs/llama-cpp-local-model/spec.md`.
- The internal support layer owns shared mechanics only: import, SDK adapter
  calls, and low-level error wrapping.
- Public callers should continue using existing package APIs. The support layer
  should not be exported from the package root unless a later public API spec
  explicitly approves that.
- A discovered model repository id is not sufficient to download or run a model.
  Local-model resolution must still require explicit file or snapshot
  references and preserve offline policy.

## Functional Requirements

### FR-1: Centralize lazy Hugging Face SDK import

The repository should load `huggingface_hub` through one internal helper rather
than repeating import handling in every Hugging Face touchpoint.

Acceptance criteria:

- Given `huggingface_hub` is installed, when the support layer needs Hub SDK
  objects, then it returns the specific read-only callables needed by the
  caller.
- Given `huggingface_hub` is unavailable or fails to import, when discovery or
  download behavior uses the support layer, then the caller can translate the
  failure into its existing package-owned error type.
- Given package import happens without invoking Hugging Face behavior, then the
  support layer does not eagerly import or initialize the Hub SDK.

### FR-2: Preserve domain-specific public errors

Shared mechanics must not collapse all Hugging Face failures into one public
error type.

Acceptance criteria:

- Given model search fails, when the failure reaches callers, then the public
  boundary remains `HuggingFaceModelSearchError`.
- Given local-model download fails, when the failure reaches callers, then the
  public boundary remains `LocalModelResolutionError` or
  `LocalModelOfflinePolicyError` as appropriate.
- Given the support layer catches an SDK/import failure, when it reports that
  failure to domain code, then enough context is available to produce clear
  search or local-model messages.

### FR-3: Preserve separate discovery and asset-resolution semantics

The support layer must not make model search an implicit input to dynamic model
loading.

Acceptance criteria:

- Given `search_hugging_face_models(...)` returns a repo id, when local-model
  resolution is requested, then resolution still requires an explicit
  `HuggingFaceModelFileReference` or `HuggingFaceSnapshotReference`.
- Given a local-model file or snapshot reference is configured, when the asset is
  missing locally and network use is allowed, then download behavior may use the
  shared support layer without invoking model search.
- Given offline policy blocks network use, when local-model resolution reaches a
  Hugging Face reference, then it still fails before any support-layer download
  call is made.

### FR-4: Keep tests deterministic and live-network-free

The support layer must remain testable without contacting Hugging Face.

Acceptance criteria:

- Given unit tests cover support-layer search/download wrappers, when they run
  in CI, then they use fake callables or monkeypatching instead of live Hub
  traffic.
- Given existing model-search and local-model tests run after the refactor, then
  they still validate domain behavior rather than upstream network behavior.
- Given the helper adds internal abstractions, when tests assert behavior, then
  they cover both import-failure and SDK-call-failure translation paths.

## Design Constraints

- Keep the internal module small and boring; it should not introduce a client
  framework, registry, caching policy, or public abstraction layer.
- Prefer simple functions over classes unless tests prove a class removes real
  duplication.
- Do not change cache roots, filename matching, snapshot behavior, or result
  normalization except where required to route through the shared helper.
- Avoid making `hugging_face_models.py` depend on `local_models.py` or the
  reverse; both should depend only on the shared internal helper if this feature
  is implemented.

## Suggested Implementation Shape

A future implementation may add an internal module such as
`src/dynamic_agent_runner/hugging_face_support.py` with helpers similar to:

- `list_hub_models(...)`
- `download_hub_file(...)`
- `download_hub_snapshot(...)`
- `load_hugging_face_hub(...)`

Domain modules should wrap support-layer failures into their existing public
errors. The exact function names are intentionally not authoritative until a
plan/task artifact is approved.

## Validation Checklist

- [ ] `tests/test_hugging_face_models.py` still passes without live network.
- [ ] `tests/test_local_models.py` still passes without live network.
- [ ] New support-layer tests cover SDK import failure and SDK call failure.
- [ ] Package-root exports do not expose the internal support layer.
- [ ] Documentation continues to describe discovery and local-model loading as
      separate contracts.

## Open Questions

- Should the internal helper own a support-layer-specific private exception, or
  should it accept a caller-supplied error factory for each call?
- Should the default download helpers in `local_models.py` remain injectable at
  the local-model boundary after the support layer exists?
- Should support-layer tests live in a new `tests/test_hugging_face_support.py`
  file or be covered only through the two domain modules?
