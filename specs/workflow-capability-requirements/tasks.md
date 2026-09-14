# Workflow Capability Requirements Tasks

Status: C1–C5.6 are complete and verified. Implementation was fake-only and
test-first; completion evidence is recorded under each task.
`WorkflowPolicy.required_capabilities` remains the existing string-set
preflight contract; these tasks add a separate exact-contract path.

## C0 — Readiness and Scope

- [x] C0.1 [review] Reconcile the package descriptor name with the current
  implementation: capability requirements belong in
  `workflow-descriptor.yaml`, the file named by
  `workflow_host/policy.py:DESCRIPTOR_FILENAME`.
- [x] C0.2 [review] Review the specification and plan with Council and
  Ponytail. The resolved findings require canonical requirement bytes,
  contract/provider separation, no package-selected provider identity, and
  admission before package-owned converter import or other side effects. The
  follow-up review additionally requires a declared receiver-comparable digest,
  duplicate-key-detecting YAML parse, entrypoint inventory, descriptor-only
  admission, and side-effect/revalidation test matrices.
  - Council: accepted the distinct immutable contract and receiver-local
    provider model, exact manifest location, and deferred-boundary ordering.
  - Ponytail: accepted one capability module plus extensions to existing
    descriptor/policy/preflight seams; rejected a new plugin manager, model
    registry, dependency installer, or parallel policy system.
- [x] C0.3 [review] Review task execution order and evidence with Council and
  Ponytail. Add the required C4.1 dependency and route-table evidence, concrete
  host/runner/preparation sentinel owners, converter asset-read sentinel,
  built-in contract publication, runtime-version gate, and explicit C5 planning
  blocker/runner-converter admission tasks.
  - Council: accepted the revised dependency chain; no task may claim C4
    admission coverage before its inventoried boundary owner is named.
  - Ponytail: lean already. The added lines make existing required behavior
    executable; they add no production abstraction or parallel workflow.

## C1 — Canonical Capability Values

- [x] C1.1 [tests, RED] Add `tests/test_workflow_capabilities.py` coverage for
  capability-contract and requirement canonical JSON/digest vectors; malformed
  64-hex digests; unknown fields; duplicate IDs; duplicate or unsorted features;
  unsorted requirements; NFC Unicode; declared-digest mismatch; and
  absent-versus-empty requirements.
  - Spec: Capability contract; Package capability requirement; FR-1.
  - Files: `tests/test_workflow_capabilities.py`.
  - Gate: no package descriptor, converter, framework, subprocess, network, or
    model import is allowed in these tests.
- [x] C1.2 [implementation] Add the minimal immutable contract, requirement,
  provider-availability, and redacted-resolution values plus canonical JSON
  helpers and DAR-owned built-in capability-contract definitions in
  `src/dynamic_agent_runner/workflow_host/capabilities.py`.
  - Spec: Capability contract; Capability provider; FR-1 and FR-3.
  - Depends on: C1.1.
  - Gate: contracts contain only ID/version/digest/features; canonicalization
    has exactly the documented Unicode and integer behavior; provider identity,
    platform state, and availability are receiver-local.
- [x] C1.3 [tests, GREEN] Make C1.1 pass and add fixed positive/negative
  publication and conformance vectors for every built-in contract declared by
  this slice. Assert that each declared built-in provider has a published
  contract, and that a nonempty requirement record cannot be admitted by an
  empty built-in/provider catalog.
  - Files: `tests/test_workflow_capabilities.py`.
  - Depends on: C1.2.
  - Validation: `poetry run pytest tests/test_workflow_capabilities.py -q`.

## C2 — Descriptor and Policy Identity

- [x] C2.1 [tests, RED] Extend `tests/test_dar_authoring_descriptor.py` with a
  valid `workflow-descriptor.yaml.capability_requirements` mapping and invalid
  format version, unknown field, malformed requirement, duplicate ID, and
  ordering cases. Add raw-YAML fixtures with duplicate top-level and nested
  keys to prove rejection before mapping conversion.
  - Spec: Package capability requirement; Package Identity and Lifecycle.
  - Files: `tests/test_dar_authoring_descriptor.py`.
  - Gate: an absent mapping preserves existing v1 package behavior; it does not
    synthesize a legacy string capability.
- [x] C2.2 [implementation] Add duplicate-key-detecting descriptor loading in
  `src/dynamic_agent_runner/workflow_host/policy.py` before
  `WorkflowDescriptor.from_mapping`, extend parsing in
  `src/dynamic_agent_runner/workflow_host/descriptor.py`, then add separate
  canonical requirements and requirements digest fields to `WorkflowPolicy`.
  - Spec: Package capability requirement; Package Identity and Lifecycle.
  - Depends on: C1.3, C2.1.
  - Gate: include the requirements digest in `policy_digest`; leave
    `required_capabilities` and `resolve_capabilities` unchanged.
- [x] C2.3 [tests/implementation, GREEN] Update the package writer, persisted
  registration record, and import verifier; extend
  `tests/test_dar_authoring_policy.py`, `tests/test_dar_authoring_registration.py`,
  and package import/export fixtures to prove a requirements change changes
  binding, receiver digest recomputation rejects tampering, legacy registrations
  remain valid, and re-registration creates the empty-record binding.
  - Depends on: C2.2.
  - Validation: `poetry run pytest tests/test_dar_authoring_descriptor.py
    tests/test_dar_authoring_policy.py tests/test_dar_authoring_registration.py
    tests/test_dar_authoring_package_export.py -q`.
- [x] C2.4 [tests/implementation, GREEN] Enforce the declared
  `dar_runtime.required_version` gate for packages that contain
  `capability_requirements`. Add construction/admission fixtures for a
  supporting receiver, an older receiver, and a legacy package without the new
  mapping.
  - Spec: Package capability requirement; Package Identity and Lifecycle.
  - Depends on: C2.3.
  - Gate: an unsupported receiver rejects before catalog resolution or package
    asset access; legacy package compatibility remains unchanged.

## C3 — Exact Catalog Resolution

- [x] C3.1 [tests, RED] Add fake-catalog tests for exact ID/version/digest
  matching, requested-feature subset matching, extra provider features,
  disabled provider, platform incompatibility, optional-component absence,
  deterministic host-policy choice, unavailable-after-selection behavior, and
  redacted unavailable results.
  - Spec: Capability provider; FR-1, FR-2, FR-3.
  - Files: `tests/test_workflow_capabilities.py`.
  - Gate: tests may observe only the requirement ID and stable classification,
    never provider identity or host-private details.
- [x] C3.2 [implementation] Add an exact contract resolver and receiver-local
  provider catalog to `workflow_host/capabilities.py`; expose it separately
  from the existing `resolve_capabilities` string-set function.
  - Depends on: C3.1, C2.3.
  - Gate: no aliases, ranges, fallback, or package provider preference.
- [x] C3.3 [tests, GREEN] Add fake provider-conformance vectors for every
  built-in capability contract and prove a provider failing features, integrity
  effects, resource limits, or redacted failure outcomes is ineligible before
  selection or any provider lifecycle action.
  - Spec: FR-2; Standard model capability integration.
  - Depends on: C3.2.
  - Validation: `poetry run pytest tests/test_workflow_capabilities.py -q`.

Latest validation: `poetry run pytest -q` (1,967 passed, 1 skipped,
7 deselected), `poetry run ruff check src tests`, `git diff --check`, and the
targeted pre-commit hooks passed on 2026-09-09.

## C4 — Ordered Admission and Revalidation

- [x] C4.1 [discovery] Inventory all package-loading entrypoints in staging,
  catalog, policy compilation, preflight, registration, host, runner,
  authoring-output, and preparation paths. Classify generic descriptor parsing
  versus package-owned asset/code loading, then identify the shared
  descriptor-only provenance-verified admission seam.
  - Spec: Package Identity and Lifecycle; FR-3.
  - Evidence: record the complete route table, side-effect boundary owner, and
    selected test file in this task before C4.2 begins. At minimum include
    `artifacts.py`, `workspace_ingress.py`, `preparation.py`, `runner.py`, and
    `host.py` in addition to staging, catalog, policy, preflight, and
    registration.
  - Gate: no implementation begins until every route to workflow manifest,
    converter, local asset, model, or ingress behavior is accounted for.
  - Inventory evidence (2026-09-09):

    | Route | Current descriptor/package entry | First deferred boundary | Owner to route through descriptor-only admission | C4.2 test owner |
    | --- | --- | --- | --- | --- |
    | Source staging | `PrivatePackageStager.stage` | `load_agent_package_workflow` while staging | `staging.py` / `catalog.py` | `tests/test_dar_authoring_staging.py`, `tests/test_dar_authoring_catalog.py` |
    | Non-executing preflight | `PackagePreflightService.preflight` | policy compilation after stage/catalog | `preflight.py` | `tests/test_dar_authoring_preflight.py` |
    | Registration and MCP binding | `LocalWorkflowHost.register` and `.bind_mcp_package` | local asset/converter validation in policy compilation | `host.py` / `registration.py` | `tests/test_dar_authoring_registration.py`, `tests/test_dar_authoring_host.py` |
    | Authoring-output validation | `_load_package_contract` | runtime-manifest load before descriptor validation | `authoring_output.py` | `tests/test_dar_authoring_authoring_output.py` |
    | Prepared-input sealing | `WorkflowInvocationPreparationService.prepare` | sealed artifact verifier `load` | `preparation.py` | `tests/test_dar_authoring_prepared_inputs.py` |
    | File ingress | `LocalWorkflowHost.ingress_file` and `.ingress_default_file` | caller file copy via `WorkspaceIngressService.ingress` | `host.py` / `workspace_ingress.py` | `tests/test_dar_authoring_workspace_ingress.py`, `tests/test_dar_authoring_host.py` |
    | Artifact materialization | `materialize_workspace_artifacts/images/binaries` | private artifact bytes become handler values | `preparation.py` / `artifacts.py` | `tests/test_dar_authoring_prepared_inputs.py` |
    | Runner and dry run | `DARWorkflowRunner._preflight`, `.run`, and `.dry_run` | converter asset/package load, sealed payload/image materialization, then model execution | `runner.py` | `tests/test_dar_authoring_runner.py` |
    | Saved workflow convenience path | `LocalWorkflowHost.invoke_saved` | model preparation, ingress, then runner | `host.py` | `tests/test_dar_authoring_host.py`, `tests/test_dar_authoring_runner.py` |

    The shared seam must sit after staged provenance/content verification but
    before the current `load_agent_package_workflow`, local asset hash/read,
    converter load, artifact materialization, model preparation/load, or
    workspace ingress calls. C4.2 must place sentinels at every listed first
    deferred boundary; C4.3 must route all rows through that seam.
- [x] C4.2 [tests, RED/GREEN] Add
  registration/preflight/host/runner/preparation tests
  with sentinels for package converter asset read/open/hash and module import,
  subprocess creation, network materialization, preparation, converter
  load/execution, model load/execution, and sealed-input ingress. For every
  unsatisfied contract requirement, assert all counters remain zero.
  - Spec: Package Identity and Lifecycle; FR-3; Required Implementation
    Discipline.
  - Files: `tests/test_dar_authoring_preflight.py`,
    `tests/test_dar_authoring_registration.py`,
    `tests/test_dar_authoring_host.py`, `tests/test_dar_authoring_runner.py`,
    and the preparation test identified by C4.1.
  - Gate: matrix bad provenance/content, duplicate/malformed requirement,
    digest mismatch, contract mismatch/unavailability, and binding mismatch.
    Every case leaves package-owned import, subprocess, network, preparation,
    model load, converter load, and ingress counters at zero.
  - Depends on: C4.1.
  - RED/GREEN evidence (2026-09-09):
    `tests/test_dar_authoring_policy.py` first observed the missing
    `capability_catalog` admission argument, then proves an unsatisfied exact
    requirement leaves runtime-manifest load, converter asset validation, and
    local-tool asset validation untouched. `tests/test_dar_authoring_preflight.py`
    proves the public preflight entrypoint returns a redacted failure before
    policy binding. `tests/test_dar_authoring_runner.py` proves runner
    recompilation rejects before re-materializing a sealed artifact, invoking
    the fake model, creating a subprocess, or opening a network connection;
    it also proves provider reselection fails closed before model execution.
    `tests/test_dar_authoring_prepared_inputs.py` proves preparation rejects
    before artifact verification. `tests/test_dar_authoring_host.py` proves
    host ingress and saved-workflow model preparation reject before their
    side effects. `runner.py`, `preparation.py`, and `host.py` revalidate the
    registration-bound private provider selection. Descriptor-only staging
    tests cover malformed, digest-mismatched, and invalid-binding requirements;
    staging tests cover source-manifest and publisher-provenance failure.
    Focused C4 validation passed 220 tests with Ruff and `git diff --check`.
- [x] C4.3 [implementation] Route exact contract resolution through the shared
  descriptor-only provenance-verified admission seam identified by C4.1. Apply
  it to every inventoried route before workflow-manifest, local-asset, or
  converter validation; then enforce canonical digest validation, provider
  resolution, binding validation, and side-effect eligibility.
  - Depends on: C3.3, C4.1, C4.2.
  - Gate: packages with no `capability_requirements` retain current behavior;
    provider availability is checked again before every deferred side effect.
  - Implementation evidence (2026-09-09): registration records now
    persist private selected provider IDs and include them in the registration
    digest. Runner, preparation, ingress, and saved-workflow preparation
    compare a fresh catalog resolution to that private binding and revalidate
    the bound IDs; a changed host priority fails closed rather than reselecting
    a provider. The saved-workflow path admits and revalidates before local
    model preparation; staging, catalog, policy, preflight, registration, host,
    runner, authoring-output, and preparation routes follow the ordered seam.
- [x] C4.4 [tests, GREEN] Make C4.2 pass, including a provider that becomes
  unavailable immediately before download/preparation, converter asset
  load/execution, model load/execution, and sealed ingress. Assert a redacted
  `capability_unavailable`, no fallback, and no action at that boundary. Add a
  legacy-package regression proving it invokes neither catalog nor conformance
  machinery.
  - Depends on: C4.3.
  - Validation: `poetry run pytest tests/test_dar_authoring_preflight.py
    tests/test_dar_authoring_registration.py tests/test_dar_authoring_policy.py
    tests/test_workflow_capabilities.py -q`.
  - Evidence: an available provider becoming disabled rejects before converter
    load, model execution, artifact verification, file ingress, and saved-model
    preparation. Reordered provider priority rejects before model execution;
    legacy packages do not invoke the capability catalog. The package CLI maps
    saved-host failures to redacted `capability_unavailable`.

## C5 — Model and Converter Integration

- [x] C5.1 [workflow-model-materials planning] Create and approve
  `specs/workflow-model-materials/plan.md` and `tasks.md` that implement its
  model-material lock/parser contract. This task remains blocked until those
  artifacts name the lock/parser test and implementation seams.
  - Evidence: `plan.md` and `tasks.md` name the lock/parser test and
    implementation seams; the user approved both on 2026-09-09.
- [x] C5.2 [workflow-model-materials implementation] Add RED mapping
  tests when the model-material lock/parser implementation exists: each
  preparation operation directly matches one required preparation capability;
  each v1 runner/profile pair or v2 runner/descriptor binding matches one
  model-execution capability; and each
  converter manifest matches one converter-host capability.
  - Spec: FR-5; `../workflow-model-materials/spec.md`; and
    `../workflow-input-converter-plugin/spec.md`.
  - Depends on: C4.4, C5.1, and the approved
    `workflow-model-materials/tasks.md` implementation task.
  - Gate: cover missing and duplicate bindings, wrong execution identity or
    converter-ABI contract, and mapping rejection before provider load or
    converter asset import. Material transport, download, cache, credentials,
    and network policy stay universal DAR behavior, never requirements.
  - Evidence: policy admission now checks every preparation operation against
    its exact declared requirement and derives the exact execution identity and
    converter-capability binding before package-owned runtime loading.
- [x] C5.3 Bind the requirements digest into the private model
  execution binding and use only the selected DAR provider. Remove any
  package-bound receiver execution-plugin identity; retain it only in private
  audit data.
  - Depends on: C5.2.
  - Evidence: `ModelExecutionBinding` includes the canonical requirements
    digest and registration persists/hashes its digest without provider identity.
- [x] C5.4 Update runner and converter admission to obtain and
  revalidate the resolver's selected private provider before converter asset
  read/load/execution and runner/model load/execution. Add GREEN coverage for
  those paths and the no-fallback behavior.
  - Spec: FR-3; FR-5.
  - Depends on: C5.2.
  - Evidence: policy recompilation derives/revalidates the exact sealed binding
    before package-owned converter loading; `WorkflowRunner` resolves only the
    host-injected exact registry before sealed-input loading. The C5.4 runner
    regression proves a missing registry leaves sealed-input loading untouched.
- [x] C5.5 [validation] After C5.3 and C5.4, run the focused capability, descriptor,
  policy, registration, preflight, model-material, runner, and converter tests;
  then run `poetry run pytest -q`, `poetry run ruff check src tests`,
  `git diff --check`, and `poetry run pre-commit run --files <changed files>`.
  - Manual gate: only with explicit authorization, run a sealed package that
    requires a real installed capability. Record redacted outcome only; it is
    outside unit tests and does not unblock C1–C4.
  - Evidence: final fake-only validation passed on 2026-09-09: 2,000 passed,
    1 skipped, 7 deselected; Ruff, diff checks, and all pre-commit hooks pass.
- [x] C5.6 [tests, RED/GREEN] Make the receiver capability catalog a supported
  `LocalWorkflowHost.open()` composition input. Retain that exact catalog in
  the host for registration admission, and pass it to invocation preparation
  and the workflow runner. Remove the need for callers or integration harnesses
  to mutate private host attributes after opening the host. Add focused host
  tests proving a sealed package with exact capability requirements registers,
  prepares, and runs using only the public `open()` input; prove an absent
  catalog preserves legacy package behavior and fails closed for a package that
  declares requirements.
  - Spec: Capability resolution; Package Identity and Lifecycle; FR-1; FR-3.
  - Files: `src/dynamic_agent_runner/workflow_host/host.py`,
    `tests/test_dar_authoring_host.py`.
  - Depends on: C5.4.
  - Gate: the exact receiver-local catalog snapshot must be shared by every
    admission/revalidation boundary; no package data, host-private provider
    identity, fallback, private post-construction mutation, registry, or
    persisted host configuration is introduced.
  - Readiness review (2026-09-09): Council (Aristotle, Ada, Feynman; reduced-
    independence sequential review) accepted the composition-root boundary
    after clarifying that registration admission—not `WorkflowRegistrationService`
    construction—uses the catalog. Ponytail accepted the minimal propagation
    path and rejected a catalog registry, discovery mechanism, or new config
    file.
  - Evidence (2026-09-09): RED observed
    `LocalWorkflowHost.open()` reject the `capability_catalog` keyword. GREEN
    proves the same catalog is retained by host registration, preparation, and
    runner services; a requirements package registers, prepares, and executes
    through that public input; an absent catalog rejects that package before
    registration; and existing legacy host coverage remains catalog-free.
    Focused host tests and the full suite pass.

## C6 — Locked Inference Capability

- [x] C6.1 [design] Publish the exact `model.generate.v1` capability contract,
  feature set, and provider conformance vectors with
  `workflow-locked-inference-callback`.
  - Evidence: the v1 contract requires the generic `structured` feature and
    bounded-I/O, deadline, structured-value, and redacted-failure conformance.
    The 2026-09-10 Council (Aristotle, Ada, Feynman) and Ponytail review also
    approved one fresh policy/revision-bound execution factory per invocation:
    it uses only the registration-selected provider, rereads sealed role assets,
    and never exposes a provider selector or creates a parallel callback path.
- [x] C6.2 [tests, RED] Add descriptor/admission vectors for inference-role
  requirement/material-role mismatches that leave all asset, model, provider,
  ingress, and result actions at zero.
  - Evidence: `tests/test_dar_authoring_policy.py` mutates both a
    sealed inference schema and its material-set role in a catalog revision and
    proves each fails before runtime-manifest loading. The real receiving-host ZIP
    test additionally mutates a staged sealed instruction and proves policy
    compilation stops before callback resolution, handle ingress, provider
    entry, collector allocation, or publication.
- [x] C6.3 [implementation] Resolve and revalidate the selected private
  provider only through the generic inference binding; do not expose provider
  selection or domain output interpretation to package data.
  - Evidence: `LocalWorkflowHost.open()` composes the sealed callback resolver
    only from a receiver-owned catalog, inference-provider registry, and finite
    host limits. `LockedInferenceExecutionFactory` creates a fresh
    invocation-local service from the recompiled policy and trusted revision,
    verifies each role's material-set digest against its derived binding,
    rereads and verifies sealed role assets, resolves only the previously
    selected `model.generate.v1` provider by canonical requirement order, and
    revalidates that exact executable immediately before provider entry.
- [x] C6.4 [tests, GREEN] Prove exact matching, role isolation, no fallback,
  and legacy requirements-package compatibility.
  - Evidence: the sealed-runner integration invokes only the factory-created
    service using verified revision assets and the registration-selected
    receiver provider. Factory and registry tests cover contract mismatch,
    role isolation, selection revalidation, and no fallback; existing legacy
    host coverage remains catalog-free.
