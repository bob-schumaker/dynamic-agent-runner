# Local Model Availability API Tasks

Status: implemented through Slice A5.1

## Prerequisites

- Spec: `specs/local-model-availability-api/spec.md`
- Plan: `specs/local-model-availability-api/plan.md`
- Validation log: `specs/local-model-availability-api/validation.md`

## Scope Rule

Keep Slice A1 limited to read-only explicit-reference availability. Do not add
inventory scanning, broad Hugging Face cache introspection, model downloads,
adapter construction, model loading, execution, memory profiling, live network
tests, or downstream UI policy.

If inventory is added in a later slice, keep it restricted to DAR-owned/default
download cache locations and current caller-provided roots; do not scan or
manage arbitrary local model directories.

Slice A4 is that later slice. Keep it read-only, current-call scoped, and
filesystem-only.

## Slice A0 — Planning Checkpoint

- [x] A0.1 [planning] Create implementation plan, task list, and validation log.
  - Spec: Implementation Readiness
  - Files/components: `specs/local-model-availability-api/plan.md`,
    `specs/local-model-availability-api/tasks.md`,
    `specs/local-model-availability-api/validation.md`
  - Validation: `pre-commit run --files <planning artifacts>`

- [x] A0.2 [planning] Mark the spec and corpus index as prepared for Slice A1.
  - Spec: Metadata, Implementation Readiness
  - Files/components: `specs/local-model-availability-api/spec.md`,
    `specs/README.md`
  - Validation: `pre-commit run --files <planning artifacts>`

## Slice A1 — Public Contract and Local Checks

- [x] A1.1 [tests] Add RED import and shape coverage for the public
      availability contract.
  - Spec: FR-1, FR-5
  - Plan: Public Contract Decisions
  - Files/components: `tests/test_local_models.py`, `tests/test_import.py`,
    `src/dynamic_agent_runner/local_models.py`,
    `src/dynamic_agent_runner/__init__.py`
  - Validation:
    `poetry run pytest tests/test_local_models.py tests/test_import.py -q`
  - Expected RED: public value objects and
    `check_local_model_availability(...)` are missing.
  - RED:
    `poetry run pytest tests/test_local_models.py tests/test_import.py -q`
    failed because `LocalModelAssetReference` and package-root exports were
    missing.

- [x] A1.2 [implementation] Add availability value objects, status/source
      vocabularies, placeholder availability function, and package-root exports.
  - Spec: FR-1, FR-5
  - Plan: Public Contract Decisions
  - Files/components: `src/dynamic_agent_runner/local_models.py`,
    `src/dynamic_agent_runner/__init__.py`
  - Depends on: A1.1
  - Validation:
    `poetry run pytest tests/test_local_models.py tests/test_import.py -q`
  - GREEN:
    `poetry run pytest tests/test_local_models.py tests/test_import.py -q` —
    `32 passed in 0.21s`

- [x] A1.3 [tests] Add RED coverage for explicit local path availability,
      missing explicit paths, invalid GGUF paths, and no fallback from an
      explicit local-path reference.
  - Spec: FR-1, FR-2, FR-3
  - Plan: Availability Flow, Backend Validation Approach
  - Files/components: `tests/test_local_models.py`
  - Depends on: A1.2
  - Validation: `poetry run pytest tests/test_local_models.py -q`
  - Expected RED: the placeholder function does not implement local path
    checks or backend validation.
  - RED:
    `poetry run pytest tests/test_local_models.py -q` failed because explicit
    path and GGUF validation returned placeholder missing results.

- [x] A1.4 [implementation] Implement explicit local-path availability and
      minimal GGUF validation without model loading.
  - Spec: FR-1, FR-2, FR-3
  - Plan: Availability Flow, Backend Validation Approach
  - Files/components: `src/dynamic_agent_runner/local_models.py`
  - Depends on: A1.3
  - Validation: `poetry run pytest tests/test_local_models.py -q`
  - GREEN:
    `poetry run pytest tests/test_local_models.py -q` — `37 passed in 0.21s`

- [x] A1.5 [tests] Add RED coverage for explicit cache-root precedence, default
      cache-root fallback, local miss without remote metadata, and proof that no
      download helper is called.
  - Spec: FR-2, NFR-2
  - Plan: Availability Flow
  - Files/components: `tests/test_local_models.py`
  - Depends on: A1.4
  - Validation: `poetry run pytest tests/test_local_models.py -q`
  - Expected RED: cache-root lookup and no-download semantics are not complete.
  - RED:
    `poetry run pytest tests/test_local_models.py -q` failed because explicit
    and default cache-root hits returned placeholder missing results.

- [x] A1.6 [implementation] Implement no-download cache-root precedence for
      explicit cache root and default cache root.
  - Spec: FR-2, NFR-2
  - Plan: Availability Flow
  - Files/components: `src/dynamic_agent_runner/local_models.py`
  - Depends on: A1.5
  - Validation: `poetry run pytest tests/test_local_models.py -q`
  - GREEN:
    `poetry run pytest tests/test_local_models.py tests/test_import.py -q` —
    `38 passed in 0.17s`

## Slice A2 — MLX Validation and Remote Metadata

- [x] A2.1 [tests] Add RED coverage for MLX GGUF availability and converted MLX
      directory availability using temporary fixtures.
  - Spec: FR-3, FR-7
  - Plan: Backend Validation Approach
  - Files/components: `tests/test_mlx_models.py`,
    `src/dynamic_agent_runner/local_models.py`,
    `src/dynamic_agent_runner/mlx_models.py`
  - Depends on: A1.6
  - Validation:
    `poetry run pytest tests/test_mlx_models.py tests/test_local_models.py -q`
  - Expected RED: shared availability validation does not yet recognize
    converted MLX directories.
  - RED:
    `poetry run pytest tests/test_mlx_models.py tests/test_local_models.py -q`
    failed because incomplete converted MLX directories were accepted.

- [x] A2.2 [implementation] Add or share backend-aware validation for MLX GGUF
      files and converted MLX directories.
  - Spec: FR-3
  - Plan: Backend Validation Approach
  - Files/components: `src/dynamic_agent_runner/local_models.py`,
    `src/dynamic_agent_runner/mlx_models.py`
  - Depends on: A2.1
  - Validation:
    `poetry run pytest tests/test_mlx_models.py tests/test_local_models.py -q`
  - GREEN:
    `poetry run pytest tests/test_mlx_models.py tests/test_local_models.py`
    `tests/test_import.py -q` — `63 passed in 0.31s`

- [x] A2.3 [tests] Add RED coverage for injected remote metadata results:
      `would_download`, invalid/inaccessible remote reference, unavailable
      metadata, size reporting, and no metadata call when disabled.
  - Spec: FR-4, FR-7
  - Plan: Remote Metadata Seam
  - Files/components: `tests/test_local_models.py`,
    `tests/test_hugging_face_support.py`
  - Depends on: A2.2
  - Validation:
    `poetry run pytest tests/test_local_models.py`
    `tests/test_hugging_face_support.py -q`
  - Expected RED: the availability function does not call or interpret the
    injected metadata seam.
  - RED:
    `poetry run pytest tests/test_mlx_models.py tests/test_local_models.py -q`
    failed because `metadata_lookup` and `LocalModelRemoteMetadata` were
    missing.

- [x] A2.4 [implementation] Implement the injected remote metadata seam without
      adding live Hugging Face calls or downloads.
  - Spec: FR-4, NFR-4
  - Plan: Remote Metadata Seam
  - Files/components: `src/dynamic_agent_runner/local_models.py`
  - Depends on: A2.3
  - Validation:
    `poetry run pytest tests/test_local_models.py`
    `tests/test_hugging_face_support.py -q`
  - GREEN:
    `poetry run pytest tests/test_local_models.py`
    `tests/test_hugging_face_support.py -q` — `49 passed in 0.20s`

## Slice A3 — Documentation, Drift Check, and Completion Evidence

- [x] A3.1 [docs] Document the availability API near local model and Hugging
      Face discovery usage.
  - Spec: FR-5, Open Questions
  - Plan: Compatibility
  - Files/components: `docs/files/python-api.rst`,
    `docs/skills/dynamic-agent-runner/SKILL.md`
  - Depends on: A2.4
  - Validation: `pre-commit run --files docs/files/python-api.rst`
    `docs/skills/dynamic-agent-runner/SKILL.md`
  - GREEN:
    `pre-commit run --files docs/files/python-api.rst`
    `docs/skills/dynamic-agent-runner/SKILL.md` — passed

- [x] A3.2 [validation] Run focused affected tests and lint.
  - Spec: Validation Plan
  - Plan: Validation Strategy
  - Depends on: A3.1
  - Validation:
    `poetry run pytest tests/test_local_models.py tests/test_mlx_models.py`
    `tests/test_hugging_face_support.py tests/test_import.py -q`
  - Validation: `poetry run ruff check src tests`
  - GREEN:
    `poetry run pytest tests/test_local_models.py tests/test_mlx_models.py`
    `tests/test_hugging_face_support.py tests/test_import.py -q` —
    `71 passed in 0.27s`
  - GREEN: `poetry run ruff check src tests` — passed

- [x] A3.3 [validation] Run targeted pre-commit for changed implementation,
      test, docs, and spec files.
  - Spec: Validation Plan
  - Plan: Validation Strategy
  - Depends on: A3.2
  - Validation:
    `pre-commit run --files src/dynamic_agent_runner/local_models.py`
    `src/dynamic_agent_runner/mlx_models.py`
    `src/dynamic_agent_runner/__init__.py tests/test_local_models.py`
    `tests/test_mlx_models.py tests/test_import.py docs/files/python-api.rst`
    `docs/skills/dynamic-agent-runner/SKILL.md`
    `specs/local-model-availability-api/spec.md`
    `specs/local-model-availability-api/plan.md`
    `specs/local-model-availability-api/tasks.md`
    `specs/local-model-availability-api/validation.md specs/README.md`
  - GREEN: targeted pre-commit passed

- [x] A3.4 [spec-maintenance] Record exact validation evidence and update
      artifact statuses after A1-A3 complete.
  - Spec: Implementation Readiness
  - Plan: Validation Strategy
  - Files/components: `specs/local-model-availability-api/spec.md`,
    `specs/local-model-availability-api/tasks.md`,
    `specs/local-model-availability-api/validation.md`, `specs/README.md`
  - Depends on: A3.3
  - Validation: `pre-commit run --files <changed spec files>`
  - GREEN: completion status and evidence recorded in this task list and
    `validation.md`

## Slice A4 — Narrow Cached Inventory

- [x] A4.1 [tests] Add RED import and shape coverage for the public cached
      inventory contract.
  - Spec: FR-5, FR-8
  - Plan: Public Contract Decisions, Slice A4 Boundary
  - Files/components: `tests/test_local_models.py`, `tests/test_import.py`,
    `src/dynamic_agent_runner/local_models.py`,
    `src/dynamic_agent_runner/__init__.py`
  - Validation:
    `poetry run pytest tests/test_local_models.py tests/test_import.py -q`
  - Expected RED: `list_local_model_assets(...)` and inventory value objects
    are missing.
  - RED:
    `poetry run pytest tests/test_local_models.py tests/test_import.py -q`
    failed because `LocalModelInventory`, `LocalModelInventoryItem`, and
    `list_local_model_assets(...)` were missing.

- [x] A4.2 [implementation] Add inventory value objects, source/status
      vocabulary reuse or extension, package-root exports, and a placeholder
      `list_local_model_assets(...)`.
  - Spec: FR-5, FR-8
  - Plan: Public Contract Decisions
  - Files/components: `src/dynamic_agent_runner/local_models.py`,
    `src/dynamic_agent_runner/__init__.py`
  - Depends on: A4.1
  - Validation:
    `poetry run pytest tests/test_local_models.py tests/test_import.py -q`
  - GREEN:
    `poetry run pytest tests/test_local_models.py tests/test_import.py -q` —
    `43 passed in 0.21s`

- [x] A4.3 [tests] Add RED coverage for default cache-root inventory over
      direct GGUF files and converted MLX directories.
  - Spec: FR-3, FR-8
  - Plan: Inventory Flow, Inventory Classification Approach
  - Files/components: `tests/test_local_models.py`
  - Depends on: A4.2
  - Validation: `poetry run pytest tests/test_local_models.py -q`
  - Expected RED: default cache-root scanning and classification are missing.
  - RED:
    `poetry run pytest tests/test_local_models.py -q` failed because default
    cache-root inventory returned no direct GGUF or converted MLX assets.

- [x] A4.4 [implementation] Implement read-only default cache-root inventory
      using existing local validation helpers.
  - Spec: FR-3, FR-8, NFR-2, NFR-6
  - Plan: Inventory Flow, Inventory Classification Approach
  - Files/components: `src/dynamic_agent_runner/local_models.py`
  - Depends on: A4.3
  - Validation: `poetry run pytest tests/test_local_models.py -q`
  - GREEN:
    `poetry run pytest tests/test_local_models.py -q` — `43 passed in 0.22s`

- [x] A4.5 [tests] Add RED coverage for current caller-provided roots,
      root-order precedence, duplicate asset paths, missing/non-directory roots,
      and proof that roots are not persisted across calls.
  - Spec: FR-8, NFR-6
  - Plan: Inventory Flow, Risks and Tradeoffs
  - Files/components: `tests/test_local_models.py`
  - Depends on: A4.4
  - Validation: `poetry run pytest tests/test_local_models.py -q`
  - Expected RED: current-call root handling and de-duplication are missing.
  - RED:
    `poetry run pytest tests/test_local_models.py -q` failed because
    current caller-provided roots were not scanned and bad roots emitted no
    warnings.

- [x] A4.6 [implementation] Implement current caller-provided root scanning,
      deterministic root/path de-duplication, and bounded warnings.
  - Spec: FR-8, NFR-6
  - Plan: Inventory Flow
  - Files/components: `src/dynamic_agent_runner/local_models.py`
  - Depends on: A4.5
  - Validation: `poetry run pytest tests/test_local_models.py -q`
  - GREEN:
    `poetry run pytest tests/test_local_models.py -q` — `45 passed in 0.23s`

- [x] A4.7 [tests] Add RED safety coverage proving inventory does not scan
      arbitrary sibling/parent directories and does not invoke metadata lookup,
      download helpers, adapter construction, model loading, generation, or
      memory-fit profiling.
  - Spec: FR-7, FR-8, NFR-2
  - Plan: Slice A4 Boundary, Inventory Flow
  - Files/components: `tests/test_local_models.py`
  - Depends on: A4.6
  - Validation: `poetry run pytest tests/test_local_models.py -q`
  - Expected RED: safety guard coverage is not complete.
  - RED not observed:
    `poetry run pytest tests/test_local_models.py -q` passed because A4.4-A4.6
    already kept scanning shallow and avoided runtime/download helpers.

- [x] A4.8 [implementation] Tighten inventory safety behavior and warnings to
      satisfy read-only, no-network, no-execution boundaries.
  - Spec: FR-7, FR-8, NFR-2
  - Plan: Slice A4 Boundary, Inventory Flow
  - Files/components: `src/dynamic_agent_runner/local_models.py`
  - Depends on: A4.7
  - Validation: `poetry run pytest tests/test_local_models.py -q`
  - GREEN:
    No additional implementation change was required; safety coverage passed
    with `47 passed in 0.25s`.

- [x] A4.9 [docs] Document the cached inventory API next to local model
      availability preflight.
  - Spec: FR-5, FR-8
  - Plan: Compatibility
  - Files/components: `docs/files/python-api.rst`,
    `docs/skills/dynamic-agent-runner/SKILL.md`
  - Depends on: A4.8
  - Validation:
    `pre-commit run --files docs/files/python-api.rst`
    `docs/skills/dynamic-agent-runner/SKILL.md`
  - GREEN:
    Cached inventory API docs added next to local model availability preflight.

- [x] A4.10 [validation] Run focused affected tests, Ruff, targeted
      pre-commit, and update validation evidence.
  - Spec: Validation Plan
  - Plan: Validation Strategy
  - Files/components: `specs/local-model-availability-api/validation.md`,
    `specs/README.md`
  - Depends on: A4.9
  - Validation:
    `poetry run pytest tests/test_local_models.py tests/test_import.py -q`
  - Validation: `poetry run ruff check src tests`
  - Validation:
    `pre-commit run --files <changed implementation, test, docs, and spec files>`
  - GREEN:
    `poetry run pytest tests/test_local_models.py tests/test_import.py -q` —
    `48 passed in 0.22s`
  - GREEN: `poetry run ruff check src tests` — passed
  - GREEN: targeted pre-commit passed for changed implementation, test, docs,
    and spec files

## Slice A5 — Hugging Face Cache Default

- [x] A5.1 [tests/implementation] Replace DAR's default local-model cache root
      with Hugging Face's standard hub cache, and resolve declared Hub
      references through its snapshot layout before any download.
  - Implementation route: the repository's focused RED/GREEN
    `test-driven-development` workflow in `tests/test_local_models.py`, followed
    by the named focused/full validation commands below.
  - Decision: the default root is `Path.home() / ".cache" / "huggingface" /
    "hub"`; it is shared with the running vLLM-compatible model service. This
    replaces the unused `~/.ollama/models` default. Explicit model paths and
    explicit caller cache roots retain their existing precedence and behavior.
  - Files/components: `src/dynamic_agent_runner/local_models.py`,
    `src/dynamic_agent_runner/hugging_face_support.py`,
    `tests/test_local_models.py`, `tests/test_hugging_face_support.py`,
    `tests/test_mlx_models.py`, `specs/local-model-availability-api/spec.md`,
    `specs/llama-cpp-local-model/spec.md`, and affected public docs.
  - RED first: use temporary Hub-cache fixtures in the canonical
    `models--<org>--<repo>/snapshots/<revision>/` form, including a cached
    `mlx-community/Qwen2.5-Coder-7B-Instruct-4bit`-shaped converted MLX
    snapshot. Prove an exact configured file or snapshot reference resolves
    locally with `allow_network=False`, does not call either download helper,
    and reports the default-cache source. Also prove cache misses retain the
    existing explicit-path, explicit-cache-root, and offline failure semantics.
  - GREEN: add a narrow, reference-directed Hub-cache resolver with this exact
    order: explicit path, unchanged flat explicit caller root, declared default
    Hub snapshot, then the existing authorized Hub download/offline failure.
    For the declared repository only, resolve a supplied snapshot id directly;
    use a supplied symbolic ref or omitted `refs/main` only as a bounded ref
    pointer to an in-repository snapshot. Reject malformed/traversing
    repository, ref, filename, pointer, and escaping symlink data; do not accept
    a same-named flat file, foreign repository, or foreign revision. The later
    already-authorized Hub download receives the same default cache root so
    `huggingface_hub` reuses its own cache; A5.1 never calls it for a cache hit.
  - Inventory: update default-root inventory only to classify bounded,
    snapshot-backed Hub entries under that one default root. Do not scan other
    provider caches, follow arbitrary symlinks, persist roots, migrate or
    delete the former Ollama directory, load a model, configure/query a local
    endpoint, or add a live Hub/vLLM test. Tests monkeypatch the default home,
    assert an `.ollama/models` sentinel is untouched, and use fail-on-call
    download, loading, and endpoint seams.
  - Acceptance: the default cache consistently supports llama.cpp and MLX
    reference resolution, availability, and inventory without an Ollama
    dependency; explicit caller roots remain authoritative; a cache lookup
    never starts, configures, or queries the local vLLM endpoint.
  - Validation: focused RED then GREEN tests in the named modules; full
    `poetry run pytest -q`; `poetry run ruff check src tests`; formatter;
    targeted pre-commit; and a documentation/status refresh after the behavior
    is delivered.
  - RED: `poetry run pytest tests/test_local_models.py -q -k
    'declared_default_hub or only_default_hub_snapshots'` — 3 expected failures:
    the former Ollama root was still selected and Hub snapshots were not scanned.
  - GREEN: focused local-model/MLX/Hugging Face/import suite passed
    (`179 passed`); full `poetry run pytest -q` passed (`1478 passed, 1 skipped,
    6 deselected`); Ruff lint and format checks passed. Targeted pre-commit is
    recorded in the current A5.1 validation evidence.

- [ ] A5.2 [migration/validation] Reuse the existing Hugging Face-formatted
      test artifacts currently stored under `~/.ollama/models` without a model
      redownload.
  - Depends on: A5.1.
  - Scope: inventory only repository-cache entries with Hugging Face metadata,
    including the existing `Qwen/Qwen2.5-3B-Instruct-GGUF` GGUF artifact and
    `Qwen/Qwen3-4B-MLX-4bit` MLX safetensors snapshot. Do not treat the
    `sha256-*-partial` files or any actual Ollama-managed content as model
    artifacts to move.
  - Procedure: first perform a dry-run manifest that records source repository,
    revision/ref, required filenames, byte sizes, and content hashes. Reuse or
    copy only the identified repository-cache entries into the Hugging Face hub
    default root, validate the same manifest and DAR's offline A5.1 resolution
    afterward, then retain the source intact. Do not blindly rename the
    `.ollama/models` root, create symlinks, delete source data, or make a live
    model/vLLM call.
  - Acceptance: both artifacts resolve from the new default Hub cache with
    `allow_network=False` and zero download-helper calls; their model formats
    remain GGUF and converted MLX respectively; the recorded manifest proves
    content identity; and the source remains recoverable pending a separate
    human-authorized cleanup task.
  - Validation: dry-run manifest review; focused fake resolver tests; local
    offline post-copy preflight only after A5.1; and targeted pre-commit for
    changed task, implementation, test, and evidence files.
  - Readiness finding: the actual `Qwen/Qwen3-4B-MLX-4bit` snapshot is native
    safetensors/tokenizer JSON, not DAR's currently accepted converted-MLX
    layout. It cannot satisfy A5.2's converted-MLX acceptance without a separate
    approved native-MLX validation slice.
  - Gate: [`a5.2-dry-run-manifest.md`](a5.2-dry-run-manifest.md) records the
    read-only source inventory. A5.2 copy authority requires fresh human
    approval of its exact eligible entries and destination collision
    disposition; do not infer it from broad `.ollama` scanning.
