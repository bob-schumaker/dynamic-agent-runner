# Local Model Availability API Specification

## Metadata

- Feature slug: `local-model-availability-api`
- Mode: `light`
- Artifact type: proposed feature specification
- Status: v1 baseline implemented; Slice A4 prepared for implementation
- Version: `0.1`
- Date: 2026-06-22
- Owner: local-model adapter and Hugging Face support boundaries
- Downstream feature request:
  - `cline-tasks/local-model-availability-api-feature-request.md`
- Related feature specs:
  - `specs/dynamic-agent-runner/spec.md`
  - `specs/llama-cpp-local-model/spec.md`
  - `specs/mlx-local-model-adapter/spec.md`
  - `specs/hugging-face-model-search/spec.md`
  - `specs/hugging-face-support-layer/spec.md`
  - `specs/llama-cpp-memory-fit-profile/spec.md`
- Related implementation surfaces:
  - `src/dynamic_agent_runner/local_models.py`
  - `src/dynamic_agent_runner/mlx_models.py`
  - `src/dynamic_agent_runner/hugging_face_support.py`
  - `src/dynamic_agent_runner/hugging_face_models.py`
  - `src/dynamic_agent_runner/errors.py`
  - `src/dynamic_agent_runner/__init__.py`
  - `tests/test_local_models.py`
  - `tests/test_mlx_models.py`
  - `tests/test_hugging_face_support.py`
- Companion planning artifacts:
  - `specs/local-model-availability-api/plan.md`
  - `specs/local-model-availability-api/tasks.md`
  - `specs/local-model-availability-api/validation.md`

## Objective

Expose a public, read-only local-model availability API that lets callers inspect
whether a configured local model asset is already usable before constructing an
adapter, loading a model, starting execution, or triggering a download.

The feature should let downstream hosts such as Power Marimo present deliberate
local-model preflight status while preserving `dynamic-agent-runner` ownership of
cache-root precedence, Hugging Face reference handling, backend-aware local asset
validation, and package-owned failure semantics.

## Problem Statement

`dynamic-agent-runner` can already resolve local model assets for execution. The
current helper,
`resolve_local_model_path(LocalModelPathConfig, allow_network=...)`, follows the
approved precedence order for explicit paths, explicit cache roots, the default
cache root, and Hugging Face file or snapshot references.

That helper is intentionally runtime-facing. It returns a concrete path or raises
a package-owned error, and when network access is allowed it may download a
missing Hugging Face asset. It does not give product-facing callers a structured
answer to preflight questions such as:

- Is this exact local path, Hugging Face file, or Hugging Face snapshot already
  available on disk?
- Which source would runtime resolution use?
- Which cache root would be checked?
- Would first execution download the model?
- Is the local asset valid for the intended backend and model format?
- When metadata lookup is explicitly allowed, does the remote reference appear
  to exist and what size would the download likely be?

Downstream hosts can probe `~/.ollama/models`, Hugging Face cache directories,
or adapter construction themselves, but that duplicates runner-owned policy and
can drift from real execution behavior. A downstream UI may otherwise claim a
model is available when the runner would download, or claim a model is missing
when the runner would find it through an approved cache root.

## Downstream Request Synopsis

This spec is derived from the Power Marimo request captured in
`cline-tasks/local-model-availability-api-feature-request.md`.

Power Marimo is adding project-local model selection for OpenAI, llama.cpp, and
MLX-backed local models. Its project options dialog can search Hugging Face and
store selected model options, including GGUF artifacts intended for MLX local
execution. A concrete downstream live path selects:

```text
repo:     empero-ai/Qwythos-9B-Claude-Mythos-5-1M-GGUF
artifact: Qwythos-9B-Claude-Mythos-5-1M-Q4_K_M.gguf
```

The current runtime setup path works because Power Marimo can eventually call
DAR's local adapter factory and force model resolution during execution setup.
That is too late for a polished local-model options flow. The user should know
before saving or running a project whether a selected model is already present,
would download, is invalid for the selected backend, or points at a missing
asset.

## Existing Runtime Context

- `local_models.py` owns `LocalModelPathConfig`,
  `HuggingFaceModelFileReference`, `HuggingFaceSnapshotReference`,
  `resolve_local_model_path(...)`, default cache-root behavior, Hugging Face
  download helper routing, local endpoint helpers, direct llama.cpp adapter
  construction, and local model identity validation.
- The default local-model cache root is currently `Path.home() / ".ollama" /
  "models"`.
- `mlx_models.py` reuses `resolve_local_model_path(...)` and then validates
  resolved assets as explicit GGUF files or converted MLX model directories.
- `hugging_face_support.py` owns the lazy `huggingface_hub` import and
  package-owned error translation used by search and local-model downloads.
- `hugging_face_models.py` already exposes read-only public Hugging Face model
  search through repository-owned result objects.
- `llama-cpp-memory-fit-profile` is a post-resolution advisory feature for a
  concrete local GGUF asset. Availability preflight should stop at existence,
  source, and backend-format validity; memory-fit suitability remains separate.

## Scope

This feature covers:

1. public value objects for local model asset references and availability
   results
2. a public `check_local_model_availability(...)` API for one explicit reference
3. no-download local resolution checks that mirror existing runtime precedence
4. backend-aware local validation for llama.cpp GGUF, MLX GGUF, and converted
   MLX directory assets
5. optional remote metadata checks that can distinguish a valid remote missing
   local asset from an invalid or inaccessible remote reference
6. package-root exports and API documentation for the approved public surface
7. deterministic unit tests with fake local files and fake Hugging Face metadata
   adapters

This feature may include a small local cache inventory helper only if it is kept
to DAR-owned local-model cache locations: the package default cache root used
for downloads and current caller-provided roots for that inventory call. It must
not scan arbitrary caller directories. Broad provider cache introspection is
deferred unless an implementation plan explicitly narrows it to package-used
cache locations.

## Non-Goals

This feature must not introduce:

- model downloads during availability checks
- model loading, generation, tokenization, memory profiling, or adapter
  construction during availability checks
- runtime-managed server installation, launch, readiness, or shutdown
- downstream UI strings, confirmation dialogs, or Power Marimo-specific policy
- portable workflow manifest fields for machine-local paths, cache roots,
  Hugging Face revisions, or download policy
- general Hugging Face SDK wrapping beyond the metadata needed for this feature
- live Hugging Face, live model, llama.cpp, MLX, Marimo, or Power Marimo
  dependencies in unit tests
- automatic filesystem scans outside DAR-owned/default download cache locations
  and current caller-provided roots
- persistent registration, ownership, cleanup, or migration of caller-provided
  roots

## Proposed Public API

The implementation should prefer reusing existing local-model reference types
where doing so keeps the contract small. New value objects are acceptable if
they prevent callers from importing private runtime-resolution details.

A candidate package-level shape is:

```python
from dynamic_agent_runner import (
    LocalModelAssetReference,
    check_local_model_availability,
)

availability = check_local_model_availability(
    LocalModelAssetReference(
        provider="hugging_face",
        repo_id="empero-ai/Qwythos-9B-Claude-Mythos-5-1M-GGUF",
        filename="Qwythos-9B-Claude-Mythos-5-1M-Q4_K_M.gguf",
        model_format="gguf",
        backend="mlx",
    ),
    allow_network_metadata=True,
)
```

The result should be a repository-owned value object with stable fields such as:

```python
@dataclass(frozen=True)
class LocalModelAvailability:
    status: Literal["available", "missing", "would_download", "invalid", "unknown"]
    reference: LocalModelAssetReference
    resolved_path: Path | None = None
    cache_root: Path | None = None
    source: Literal[
        "explicit_path",
        "explicit_cache_root",
        "default_cache_root",
        "not_found",
    ] | None = None
    size_bytes: int | None = None
    message: str = ""
    warnings: tuple[str, ...] = ()
```

The exact names are not authoritative, but the public contract must preserve the
semantic distinction between:

- available locally and valid for the intended backend
- missing locally but likely downloadable when runtime resolution later allows
  network access
- missing locally with no remote reference to check
- invalid local asset or invalid remote reference
- unknown because optional metadata lookup was disabled or unavailable

The first slice should treat native Hugging Face cache introspection as optional
metadata support, not as a required source precedence level. Runtime resolution
currently owns explicit path, explicit cache root, default cache root, then
download-capable Hugging Face reference handling.

An inventory follow-up may add package-owned value objects and a public
`list_local_model_assets(...)` helper. That helper is read-only and scoped to
the roots supplied for the current call plus the default cache root; it is not a
registry of every model on the machine.

## Functional Requirements

### FR-1: Provide a public availability-check entry point

The package must expose a supported public API that checks one explicit local
model asset reference.

Acceptance criteria:

- Given a caller imports the package root, when the caller wants to preflight a
  local model reference, then a documented public entry point is available
  without importing private helpers from `local_models.py` or `mlx_models.py`.
- Given the caller provides an explicit local path, when availability is checked,
  then the result reports whether that path exists and whether it is valid for
  the requested model format and backend.
- Given the caller provides a Hugging Face file reference, when availability is
  checked, then the result checks local cache locations without downloading the
  file.
- Given the caller provides a Hugging Face snapshot reference, when availability
  is checked, then the result checks local snapshot availability without
  downloading the snapshot.
- Given the caller provides a Hugging Face file or snapshot reference, when
  availability is checked, then the reference identifies the concrete expected
  model artifact or validation target needed for local filesystem checks.
- Given the result is returned, when callers inspect it, then they can make a UI
  or smoke-test decision without parsing `LocalModelResolutionError` text.

### FR-2: Mirror runtime-owned resolution precedence without mutating state

Availability checks must use the same source precedence as runtime resolution
where practical, but must not perform the mutating download step.

Acceptance criteria:

- Given an explicit local path exists, when a matching cache file and remote
  reference also exist, then the result reports the explicit path as the source.
- Given no explicit local path is usable and an explicit cache root contains the
  requested filename, when availability is checked, then the result reports the
  explicit cache root hit.
- Given the explicit cache root misses and the default cache root contains the
  requested filename, when availability is checked, then the result reports the
  default cache root hit.
- Given local cache checks miss and a Hugging Face reference is configured, when
  `allow_network_metadata=False`, then the result does not contact the network
  and reports a missing or unknown remote-local state.
- Given local cache checks miss and a Hugging Face reference is configured, when
  `allow_network_metadata=True`, then optional metadata lookup may report
  `would_download` for a valid remote asset, but must still not download it.

### FR-3: Preserve backend-aware validation

Availability must distinguish mere filesystem presence from usability for the
intended backend and model format.

Acceptance criteria:

- Given a llama.cpp reference resolves to a local file, when `model_format` is
  `gguf` or `auto`, then the result validates enough local structure to reject a
  clearly non-GGUF asset.
- Given an MLX reference resolves to a GGUF file, when the selected backend is
  `mlx` and the requested format is `gguf`, then the result treats GGUF presence
  as a valid local asset if it passes the package's approved GGUF validation.
- Given an MLX reference resolves to a converted MLX directory, when the
  requested format is `mlx`, then the result validates the directory through the
  same converted-MLX structural expectations used by the adapter path.
- Given validation fails, when the result is returned, then status is `invalid`
  with a package-owned message and without raising for ordinary invalid user
  input.
- Given validation itself hits an unexpected implementation failure, when the
  check cannot classify the asset safely, then the result is `unknown` or raises
  a package-owned error according to the implementation plan's explicit error
  boundary.

### FR-4: Support optional remote metadata without downloads

Remote metadata lookup must be explicit, read-only, and fake-testable.

Acceptance criteria:

- Given `allow_network_metadata=False`, when a Hugging Face reference misses
  locally, then availability checking does not import or call live
  `huggingface_hub` metadata APIs.
- Given `allow_network_metadata=True`, when a fake metadata adapter reports a
  valid remote file with a size, then the result may report `would_download` and
  include `size_bytes`.
- Given `allow_network_metadata=True`, when a fake metadata adapter reports a
  missing, unauthorized, or inaccessible remote reference, then the result
  distinguishes invalid/inaccessible remote metadata from local cache absence.
- Given metadata lookup fails due to connectivity or optional dependency
  unavailability, when the caller has not requested strict failure behavior,
  then the result remains structured and does not require downstream exception
  text parsing.
- Given implementation adds strict metadata failure behavior, when strict mode is
  enabled, then failures must be package-owned exceptions and covered by tests.

### FR-5: Export repository-owned value objects

The public API must expose stable repository-owned value objects rather than raw
SDK or private implementation objects.

Acceptance criteria:

- Given availability succeeds, when a caller receives the result, then the
  result is a repository-owned dataclass or equivalent stable value object.
- Given the caller configured a Hugging Face file or snapshot reference, when
  the result is inspected, then the original reference identity is preserved.
- Given the result includes a resolved local path, when callers inspect it, then
  the path points to the source the runner would use for later runtime
  resolution.
- Given the result includes warnings, when callers inspect them, then the
  warnings are bounded strings suitable for diagnostics and do not expose raw SDK
  objects as the public contract.
- Given the API is added, when package exports are checked, then callers can
  import the approved entry point and value objects from `dynamic_agent_runner`.

### FR-6: Keep inventory narrow and optional

Local inventory support is secondary to explicit reference checks and must not
become broad provider discovery.

Acceptance criteria:

- Given implementation includes `list_local_model_assets(...)`, when it runs,
  then it only scans DAR-owned/default download cache locations and explicit
  current caller-provided roots.
- Given inventory scans a cache root, when unsupported or ambiguous files are
  found, then they are reported conservatively or skipped with bounded warnings.
- Given implementation cannot map Hugging Face cache internals reliably without
  provider-specific assumptions, when inventory is planned, then the first slice
  may defer Hugging Face cache enumeration and still satisfy this spec through
  `check_local_model_availability(...)`.
- Given callers need remote catalog search, when they want candidate models
  rather than local availability for a known reference, then they should use the
  existing Hugging Face model search API instead of inventory.

### FR-8: Provide narrow cached inventory for package-used roots

Inventory must list only local model assets visible through package-owned cache
roots for the current call. It must be a convenience over the same local
filesystem and validation semantics used by availability preflight, not a new
model-management subsystem.

Acceptance criteria:

- Given a caller invokes inventory without extra roots, when the default
  local-model cache root exists, then the result includes supported local model
  files and converted MLX directories directly under that root.
- Given the caller provides `model_cache_roots` for the current call, when those
  roots contain supported assets, then the result includes those assets and
  marks their source as a current caller-provided root.
- Given the same asset path is visible through multiple scanned roots, when the
  inventory result is returned, then the path appears once with deterministic
  precedence and bounded warnings if useful.
- Given an unsupported file, hidden file, nested provider cache internals, or
  malformed converted directory is encountered, when inventory runs, then it is
  skipped or reported as invalid according to the implementation plan without
  raising for ordinary local cache contents.
- Given inventory scans roots, when a root is missing, not a directory, or
  unreadable, then the result remains structured and contains bounded warnings
  instead of leaking raw filesystem exceptions.
- Given inventory runs, when tests observe calls, then no Hugging Face metadata,
  download helper, model adapter construction, model load, generation, or memory
  profiling path is invoked.
- Given package exports are checked, when callers import the inventory helper
  and value objects from `dynamic_agent_runner`, then the approved public names
  are available.

### FR-7: Keep tests deterministic and live-network-free by default

Availability behavior must be testable without live model dependencies.

Acceptance criteria:

- Given unit tests run, when availability checks cover cache hits, cache misses,
  invalid paths, file references, and snapshot references, then tests use
  temporary files and fake metadata adapters only.
- Given optional remote metadata behavior is tested, when the test simulates
  remote existence, size, unauthorized access, or missing assets, then it uses a
  fake metadata callable rather than live Hugging Face.
- Given backend validation is tested, when tests cover GGUF and converted MLX
  validation, then they use small fixtures or temporary structures and do not
  import real MLX, llama.cpp, or load model weights.
- Given package exports are added, when import tests run, then they verify the
  public surface without requiring optional Hugging Face dependencies.

## Non-Functional Requirements

### NFR-1: Preserve ownership boundaries

Availability logic must live with the runner-owned local-model and Hugging Face
support boundaries, not in downstream hosts or portable workflow packages.

### NFR-2: Preserve read-only preflight semantics

Availability checks must be safe to call from UI refreshes, smoke-test
preconditions, and offline planning paths. They must not mutate model caches,
download files, load models, or trigger execution.

### NFR-3: Preserve architecture continuity

The feature must extend existing local-model reference, validation, and support
seams rather than creating a parallel local-model execution family or new
executor branch.

### NFR-4: Preserve fake-test-friendly design

All external dependencies, including Hugging Face metadata lookup and backend
validation helpers, must be injectable or otherwise fakeable in focused unit
tests.

### NFR-5: Preserve conservative public API growth

The first implementation should prefer the smallest public surface that supports
explicit reference preflight. Broader inventory, cache introspection, and richer
metadata should be added only when justified by a separate plan slice.

### NFR-6: Preserve current-call inventory ownership

Inventory may accept caller-provided roots only for the current call. The package
must not remember those roots, claim ownership of them, clean them up, migrate
them, or scan sibling/parent directories.

## Edge and Error Cases

- If an explicit local path does not exist, availability should report a
  structured missing or invalid result rather than attempting fallback unless the
  public reference explicitly includes fallback sources.
- If a cache root exists but contains a directory where a GGUF file is expected,
  the result should be invalid or missing according to the requested model
  format.
- If a converted MLX directory is present but lacks required files, the result
  should be invalid with a backend-aware message.
- If both a Hugging Face file reference and snapshot reference are provided,
  implementation must either define a clear precedence consistent with runtime
  resolution or reject the ambiguous reference.
- If a Hugging Face snapshot reference does not identify enough information to
  locate the intended model artifact locally, availability should return a
  structured unknown or invalid result rather than scanning the whole snapshot
  heuristically.
- If `allow_network_metadata=True` but the optional Hugging Face support extra is
  unavailable, the result must remain structured unless strict failure behavior
  is explicitly requested.
- If remote metadata reports a file size but local validation later rejects a
  stale or partial local cache hit, the local invalid state is authoritative for
  the availability result.
- If cache layout assumptions change, availability and runtime resolution must be
  updated together so preflight does not drift from execution.
- If a caller-provided inventory root is also the default cache root, inventory
  should de-duplicate the root and keep default-cache source reporting.
- If a caller-provided inventory root contains nested directories, inventory
  should only descend far enough to identify supported converted MLX directories
  and direct supported model files unless a later approved slice defines a
  narrower nested layout.
- If inventory cannot validate an asset cheaply, it should prefer a structured
  invalid or warning-bearing result over loading the asset.

## Boundaries

### In Scope

- Public availability preflight for one explicit local path, Hugging Face file
  reference, or Hugging Face snapshot reference.
- Source and cache-root reporting that mirrors runtime local-model resolution.
- Backend-aware validation for llama.cpp GGUF, MLX GGUF, and converted MLX
  directory assets.
- Optional, read-only remote metadata lookup with explicit caller opt-in.
- Narrow cached inventory for the default local-model cache root and current
  caller-provided roots.
- Package-owned result objects, messages, warnings, and errors.

### Out of Scope

- Downloading, loading, executing, profiling, converting, or deleting models.
- UI policy, confirmation dialogs, progress displays, and downstream project
  option storage.
- Local server process management.
- Broad provider inventory across arbitrary Hugging Face or Ollama internals, or
  arbitrary local model directories outside package-used cache roots.
- Persistent local-model inventory registry, cache cleanup, or directory
  management.
- Workflow manifest schema changes.
- Live-network unit-test requirements.

### Always Do

- Reuse the existing local-model resolution precedence and validation rules.
- Keep availability checks read-only.
- Keep public results structured.
- Keep optional remote metadata lookup explicit and fake-testable.
- Keep implementation separable from memory-fit profiling and model execution.
- Keep cached inventory rooted in the same local validation helpers used by
  explicit-reference availability.

### Ask First

- Making inventory scanning part of the first required implementation slice.
- Expanding inventory beyond DAR-owned/default download cache locations and
  current caller-provided roots.
- Remembering current caller-provided inventory roots across calls.
- Adding new portable workflow fields for local-model availability.
- Treating metadata lookup as enabled by default.
- Raising exceptions for ordinary missing or invalid user-selected assets.
- Depending on live Hugging Face, real MLX, real llama.cpp, or real model
  weights in default tests.

### Never Do

- Download during an availability check.
- Instantiate a local model adapter during an availability check.
- Load a model file to perform generation-time validation.
- Let downstream hosts duplicate runner cache-root precedence as the supported
  path.
- Scan or manage arbitrary local model directories as part of inventory.
- Treat current caller-provided inventory roots as package-owned locations after
  the call returns.
- Expose raw Hugging Face SDK objects as the public availability contract.

## Dependencies and Assumptions

### Dependencies

- `specs/llama-cpp-local-model/spec.md` remains authoritative for local-model
  resolution precedence, llama.cpp adapter boundaries, and local-model failure
  taxonomy.
- `specs/mlx-local-model-adapter/spec.md` remains authoritative for converted
  MLX and MLX GGUF adapter behavior.
- `specs/hugging-face-support-layer/spec.md` remains authoritative for lazy Hub
  import and package-owned Hugging Face support error translation.
- `specs/hugging-face-model-search/spec.md` remains authoritative for remote
  model catalog search.
- `specs/llama-cpp-memory-fit-profile/spec.md` remains authoritative for
  post-resolution memory-fit advisories.

### Assumptions

- The first valuable slice was explicit-reference availability checking; the
  next planned slice is narrow cached inventory for package-used roots.
- Snapshot and file availability checks are for known references with an
  intended concrete asset, not open-ended repository browsing.
- Power Marimo and similar downstream hosts can own UI wording and project
  storage once DAR returns structured availability results.
- Runtime execution may still download when caller-owned execution policy allows
  it. This spec only controls the preflight availability API.
- Existing cache-root behavior should remain unchanged unless the local-model
  spec is explicitly revised.

## Open Questions and Next Planning Decisions

- Should the first implementation reuse `LocalModelPathConfig` plus existing
  Hugging Face reference types, or add a distinct public
  `LocalModelAssetReference` optimized for availability checks?
- Should ordinary invalid local assets return `LocalModelAvailability(status=
  "invalid")` exclusively, or should there also be a strict mode that raises
  package-owned exceptions?
- Which exact converted MLX directory files are required for availability
  validation, and should that validation reuse private helpers from
  `mlx_models.py` or move them into a shared local-model validation seam?
- How much Hugging Face metadata should be supported in the first slice: remote
  existence only, file size, sibling file listing, or snapshot-level metadata?
- Should package docs show this API near Hugging Face model search, local-model
  adapter construction, or both?
- Should inventory return only valid assets, or include invalid entries with
  status and warnings? Slice A4 should choose one behavior and lock it in tests.
- What should the public inventory item be named:
  `LocalModelInventoryItem`, `LocalModelCachedAsset`, or a more availability-
  aligned name?

## Validation Plan

Implementation planning should produce focused tests before code changes. The
minimum validation set is:

- RED tests for package-root exports of the availability entry point and value
  objects.
- RED tests for explicit local path available, missing, and invalid cases.
- RED tests for explicit cache root precedence over default cache root.
- RED tests for default cache root hit before remote metadata lookup.
- RED tests proving no download callable is invoked during availability checks.
- RED tests for Hugging Face file and snapshot local misses with
  `allow_network_metadata=False`.
- RED tests for fake remote metadata returning `would_download`, `invalid`, and
  unknown/unavailable states.
- RED tests for backend-aware GGUF and converted MLX validation.
- RED tests for narrow cached inventory over the default cache root and current
  caller-provided roots.
- RED tests proving inventory does not scan arbitrary sibling/parent
  directories and does not persist caller-provided roots across calls.
- RED tests proving inventory is read-only and does not invoke downloads,
  metadata lookup, adapter construction, model loading, generation, or memory
  profiling.
- GREEN focused run for local-model, MLX, Hugging Face support, and import
  tests.

Suggested commands after implementation:

```bash
poetry run pytest \
  tests/test_local_models.py \
  tests/test_mlx_models.py \
  tests/test_hugging_face_support.py \
  tests/test_import.py \
  -q
poetry run ruff check src tests
```

## Implementation Readiness

The v1 baseline is implemented through Slices A1-A3. Slice A4 is prepared for
implementation as narrow cached inventory over DAR-owned/default download cache
locations and current caller-provided roots. Broad inventory, native Hugging
Face cache introspection, persistent root management, and strict exception
behavior remain deferred unless this spec is revised.
