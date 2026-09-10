# Workflow Model Materials Tasks

Status: approved 2026-09-09. Runtime implementation may begin and remains
fake-only and test-first.

## M1 — Canonical Lock Parser

- [x] M1.1 [tests, RED] Add `tests/test_workflow_model_materials.py` vectors for
  canonical lock/transformation bytes and digests; malformed hashes/revisions;
  unknown fields; duplicate/unsorted roles; invalid scalars; cycles; orphan
  outputs; and absent-versus-present locks.
- [x] M1.2 [implementation] Add the immutable lock, source, preparation, and
  transformation values plus strict parser in a new generic workflow-host
  material module.
- [x] M1.3 [tests, GREEN] Make M1.1 pass without importing transport,
  framework, runner, converter, subprocess, or network dependencies.
  - Evidence: 12 focused fake-only vectors pass on 2026-09-09; the parser module
    imports only standard-library canonicalization and value-object support.

## M2 — Package Identity

- [x] M2.1 [tests, RED] Add descriptor/package/export/import/registration tests
  for a valid lock, lock-digest tampering, descriptor binding mismatch, and
  legacy packages without a lock.
  - Evidence: focused model-material package-export and policy vectors failed
    before binding enforcement on 2026-09-09.
- [x] M2.2 [implementation] Bind the material-lock digest into manifest,
  policy, registration, and import verification while preserving legacy records.
  - Evidence: authored/staged/exported manifest, policy, registration, and
    import paths now bind the canonical lock digest; missing locks remain
    optional for legacy records.
- [x] M2.3 [tests, GREEN] Prove a lock change changes every relevant immutable
  identity before cache or converter access.
  - Evidence: 58 focused fake-only parser/policy/registration/export vectors
    pass on 2026-09-09; lock changes alter policy and registration digests,
    while export rejects declared lock-digest tampering.

## M3 — Material Admission

- [x] M3.1 [tests, RED] Add fake transport/cache/provider tests for exact source
  locks, transformation input/output hashes, cache reuse, provider mismatch,
  and revalidation before download/preparation.
  - Evidence: focused fake-only admission vectors failed before the host-private
    material-admission boundary existed on 2026-09-09.
- [x] M3.2 [implementation] Add generic material admission and host-private
  binding validation; use only host-owned transport, filesystem, process, and
  resource policy.
  - Evidence: `ModelMaterialAdmission` accepts only a parsed lock, exact
    selected provider contracts, revalidation callback, and host policy.
- [x] M3.3 [tests, GREEN] Prove failed admission leaves download, subprocess,
  preparation, framework import, and model load counters at zero.
  - Evidence: five focused fake-only vectors pass on 2026-09-09. Unavailable
    providers and failed revalidation leave cache, transport, and promotion
    counters at zero; no framework, subprocess, or model collaborator exists.

## M4 — Runner and Converter Binding

- [x] M4.1 [tests, RED] Add fake binding tests for exact lock runner/profile,
  model-execution capability, and converter-host capability mappings.
  - Evidence: focused binding vectors failed before the sealed binding module
    existed on 2026-09-09.
- [x] M4.2 [implementation] Derive `ModelExecutionBinding` and route generic
  runner/converter admission through it without package-bound provider identity.
  - Evidence: generic `ModelExecutionBinding` derives exact lock and capability
    identity; `ModelRunnerRegistry` accepts only an exact receiver-installed
    runner contract and profile tuple. The host injects the registry and the
    runner resolves it before sealed-input or converter/model work.
- [x] M4.3 [tests, GREEN] Prove no fallback and no converter/model/ingress side
  effect when a material, runner, or converter requirement is unavailable.
  - Evidence: focused fake-only binding vectors pass on 2026-09-09; missing
    converter capability and empty runner registry fail closed before a runner
    provider can be selected; the runner regression proves sealed-input loading
    remains untouched when a locked runner is unavailable.

## Validation

- [x] M5.1 Run focused material tests, full pytest, Ruff, diff checks, and
  targeted pre-commit after M1–M4 pass.
  - Evidence: `poetry run pytest -q` completed with 2,000 passed, 1 skipped,
    and 7 deselected; `poetry run ruff check src tests`, `git diff --check`,
    and `poetry run pre-commit run --all-files` passed on 2026-09-09.

## M6 — Remove Legacy Floorplan Host Paths

- [ ] M6.1 [tests, RED] Add focused regression tests proving a workflow with a
  locked multimodal material, standard runner capability, and sealed converter
  can be admitted without importing a floorplan-named production module or
  calling a floorplan-named host/profile/CLI API.
- [ ] M6.2 [implementation] Remove
  `workflow_host/floorplan_vision_model.py`, floorplan-specific preparation
  recipes, floorplan profile and host constructors, and floorplan-specific CLI
  commands. Preserve only generic model-material, runner, converter, ingress,
  and result-shaping contracts.
- [ ] M6.3 [implementation] Move the floorplan scenario's model lock,
  converter, renderer, schema, input images, and manual acceptance runner into
  test-harness-only locations. No production module, package descriptor, or
  generic specification may select or interpret those values.
- [ ] M6.4 [tests, GREEN] Add a production-boundary scan that fails if `src/`,
  package build output, or generic workflow fixtures contain floorplan-specific
  model IDs, adapter IDs, converter IDs, schema names, or renderer references.
  Allow the values only under the dedicated test harness.
- [ ] M6.5 [verification] Run the focused migration regressions,
  `poetry run pytest -q`, `poetry run ruff check src tests`, `git diff --check`,
  and `poetry build`; verify the built wheel has no floorplan-specific files or
  strings.
