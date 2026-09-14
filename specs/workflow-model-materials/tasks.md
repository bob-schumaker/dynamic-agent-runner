# Workflow Model Materials Tasks

Status: implemented through M8. Runtime implementation remained fake-only and
test-first; completion evidence is recorded under each task.

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

- [x] M4.1 [tests, RED] Add fake binding tests for exact v1 runner/profile or
  v2 runner/descriptor,
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

- [x] M6.1 [tests, RED] Add focused regression tests proving a workflow with a
  locked multimodal material, standard runner capability, and sealed converter
  can be admitted through public generic contracts without importing
  `floorplan_vision_model` or calling a floorplan-named host, profile, or CLI
  API.
  - Evidence: `tests/test_floorplan_cleanup.py` was introduced red before the
    legacy imports were removed. The generic multimodal profile regression and
    the existing sealed-converter/locked-runner vectors in
    `tests/test_dar_authoring_runner.py` pass without a scenario constructor.
- [x] M6.2 [implementation] Remove
  `workflow_host/floorplan_vision_model.py`, both floorplan preparation recipe
  declarations, floorplan profile and host constructors, floorplan-specific CLI
  commands, and `workflow_host/qwen25_vl_3b_grpo_converter.py`. Preserve only
  generic model-material, runner, converter, ingress, and result-shaping
  contracts.
  - Evidence: the two production modules, both preparation recipes, named
    profile/host/CLI paths, and named adapter mappings are removed. A generic
    declared multimodal profile remains supported through the standard local
    endpoint runner contract.
- [x] M6.3 [implementation] Rehome only the scenario assets currently under
  production source—its model-lock/recipe declarations and Qwen converter—to
  test-harness-only locations. Leave existing test fixture images, renderer,
  schema, and manual acceptance assets in place. No production module, package
  descriptor, or generic specification may select or interpret those values.
  - Evidence: the Qwen converter is now a test-fixture asset and the two
    historical pinned recipes are retained only as
    `tests/fixtures/natural-language-workflow-authoring/floorplan-svg/legacy-model-recipes.json`.
- [x] M6.4 [tests, GREEN] Add a production-source boundary scan that fails if
  `src/` contains any of:
  `qwen25-vl-3b-floorplan-grpo`, `floorplan-vision-llama-cpp-adapter-v1`,
  `qwen-floorplan-input-v1`, `svg_floorplan`, `floorplan_vision_model`, or
  `qwen25_vl_3b_grpo_converter`. Permit them only under `tests/`.
  - Evidence: `test_production_source_has_no_floorplan_scenario_identity`
    scans every production Python module for all six identifiers.
- [x] M6.5 [verification] Run the focused migration regressions,
  `poetry run pytest -q`, `poetry run ruff check src tests`, `git diff --check`,
  and `poetry build`; verify the built wheel has no floorplan-specific files or
  strings.
  - Evidence: on 2026-09-10, focused migration vectors passed; the full suite
    passed with 2,038 passed, 1 skipped, and 7 deselected. Ruff and diff checks
    passed. A successful `poetry build` and source/wheel scan completed earlier
    in the migration; the final build retry was blocked by an unavailable
    Artifactory mirror before wheel creation. Both source and the previously
    built wheel had no floorplan or Qwen-converter match.

## M7 — Material Sets for Locked Inference

- [x] M7.1 [design] Approve canonical ordered named material-set syntax and
  legacy single-lock compatibility with `workflow-locked-inference-callback`.
  - Evidence: `ModelMaterialSets v1` is a separate canonical declaration; it
    leaves the legacy single-lock artifact unchanged and requires distinct named
    role bindings before deferred execution.
- [x] M7.2 [tests, RED] Add parser/package/registration vectors for duplicate,
  missing, reordered, and substituted material roles before any cache, load,
  provider, or package asset action.
  - Evidence: `tests/test_workflow_material_sets.py` rejects malformed,
    reordered, duplicate, and substituted roles; the ZIP export/import vector
    binds the canonical set digest; and the registration vector proves a set
    digest is persisted and changes the immutable registration identity.
- [x] M7.3 [implementation] Bind the material-set digest and exact inference
  role/material role relation into package policy and private execution binding.
  - Evidence: `ModelMaterialSets` and `InferenceRoles` derive distinct private
    `LockedInferenceBinding` values before runtime package loading; policy,
    deterministic ZIP manifests, and registrations bind the material-set and
    inference-role digests.
- [x] M7.4 [tests, GREEN] Prove role isolation and unchanged legacy package
  import/export behavior.
  - Evidence: focused fake-only material-set/inference-role parser and binding
    tests prove distinct role isolation; staging/export regression coverage
    proves deterministic legacy single-lock and new material-set ZIP behavior.

## M8 — Sealed Declarative Execution Descriptors

- [x] M8.1 [tests, RED] Add v2 lock/package/binding vectors for non-circular
  lock/descriptor construction, descriptor canonical bytes and digest,
  lock/descriptor mismatch, unknown or wrong ABI ID/version/digest,
  ABI-schema mismatch, unknown fields, duplicate descriptor assets, v1/v2
  mixing, and pre-side-effect rejection.
  - Evidence: focused model-material, descriptor, binding, policy, export, and
    staging tests cover canonical lock-to-descriptor digest binding, malformed
    or unavailable exact ABIs, v1/v2 closure, duplicate descriptor ZIP assets,
    and failed v2 admission before runtime package loading.
- [x] M8.2 [implementation] Resolve an exact descriptor ABI through a pure
  receiver-installed validator registry, then parse and bind the v2 execution
  descriptor as immutable package data; preserve v1 parser, identity, and
  runner behavior.
- [x] M8.3 [tests, GREEN] Prove a v2 descriptor reaches only an exact
  receiver-installed generic execution ABI through the pure validator registry
  and cannot select a model registry entry, loader profile, factory, import,
  endpoint, path, device, or provider except where a reviewed exact ABI
  explicitly defines a field.
  - Evidence: exact-registry and closed-ABI tests prove no fallback or generic
    provider selection; all deferred recompile boundaries receive the same
    receiver-owned registry and reject before handle ingress or runtime load.
- [x] M8.4 [tests, GREEN] Prove two model descriptors using one ABI remain
  isolated and production source/package construction contain no named
  upstream embedding-model material, dimension, role table, or model-loader
  identity; receiver-owned architecture ABI grammar remains allowed.
  - Evidence: distinct same-ABI descriptor bindings and exact provider binding
    tests preserve descriptor isolation; the production-source cleanup test
    excludes named embedding experiment identities while allowing generic ABI
    implementations.

## M9 — Floorplan Successor Reconciliation

- [x] M9.1 [tests, RED] Restore the M6 production-source boundary: named
  floorplan recipe, profile, and CLI preparation identities must not occur
  under `src/`, while a generic sealed multimodal package remains admissible.
  - Files/components: `tests/test_floorplan_cleanup.py`, generic package
    admission and local-runner seams.
  - Acceptance: the present source allowlist fails before implementation; no
    live model, download, converter, or MPS access occurs.

- [x] M9.2 [implementation, GREEN] Remove the remaining named static floorplan
  recipe, profile constructor, and `dar-package prepare --model` path; retain
  only generic package-bound material admission and runner binding.
  - Depends on: M9.1.
  - Acceptance: package locks are the sole material-selection authority and no
    compatibility fallback selects a named model or artifact set.

- [x] M9.3 [design/spec reconciliation] Define the authoritative floorplan
  completion witness: admitted model-output JSON, final workflow SVG, or both
  as separately named stages. Set the matching sealed generation budget and
  update the successor, historical, and fixture contracts together.
  - Depends on: M9.2.
  - Boundary: do not use a live model run to decide the contract and do not
    repair malformed model JSON.

- [x] M9.4 [tests, RED] Add fixture-derived package tests for the M9.3 contract.
  A stale budget, output-stage schema, material lock, converter, validator, or
  asset digest must fail before ingress or runner creation.
  - Depends on: M9.3.
  - Files/components: `tests/test_floorplan_svg_fixture.py` and sealed-package
    admission tests.
  - Boundary: fake-only; no model import, MPS, network, or artifact download.

- [ ] M9.5 [implementation, GREEN] Reseal the floorplan fixture package and
  descriptor/assets through existing construction paths to implement M9.3.
  Preserve generic DAR boundaries and workflow-local JSON-to-SVG processing
  when selected.
  - Depends on: M9.4.
  - Acceptance: all package identities are recomputed, not hand-edited; no
    model-specific DAR API is introduced.

- [ ] M9.6 [validation] Run focused cleanup, material, descriptor, generic
  runner, and floorplan fixture suites. Record deterministic results and leave
  WMS3.3 as the sole live MPS acceptance gate.
  - Depends on: M9.5.
  - Validation: `poetry run pytest -q tests/test_floorplan_cleanup.py
    tests/test_floorplan_svg_fixture.py tests/test_workflow_model_materials.py
    tests/test_transformers_peft_model.py` and `poetry run ruff check src tests`.
