# Workflow Capability Requirements Implementation Plan

## Status

Reviewed specification and task sequence. C1–C5 are implemented and verified:
descriptor-only staging rejects malformed, digest-mismatched, and invalid
bindings; policy admission precedes runtime and asset loading; selected provider
IDs are private registration bindings; and unavailability fails closed before
converter load, model preparation/execution, and ingress. C5.6 makes the
existing receiver-local capability catalog a public `LocalWorkflowHost.open()`
composition input and propagates it to every host admission and revalidation
boundary. The capability catalog is a new package-level compatibility system.
It must not reinterpret the existing
string-only `WorkflowPolicy.required_capabilities`, which continues to describe
current workflow operational requirements.

## Readiness Review

Council architecture review found and resolved: canonical requirement encoding,
the contract/provider separation, no package-selected execution-plugin identity,
the normative model/runner/converter mapping, and ordered pre-side-effect
admission. The follow-up review found the required declared-digest binding,
duplicate-key-detecting YAML parse, descriptor-only admission phase, full
entrypoint inventory, and deferred-boundary test matrix; this plan incorporates
them before implementation.

Ponytail review: lean already. The plan adds one value/resolution module and
extends existing descriptor, policy, registration, and preflight seams; it does
not introduce a plugin manager, dependency installer, model registry, or new
runtime abstraction layer.

## Goal

Allow a sealed `workflow-descriptor.yaml` descriptor to require exact
DAR-owned capability contracts. DAR verifies a canonical requirements digest,
resolves only an
available host-selected provider, and stops before package-owned converter
imports, network materialization, model loading, or sealed-input ingress when a
requirement cannot be satisfied.

## Current-State Anchors

| Concern | Current owner | Planned change |
| --- | --- | --- |
| Package descriptor parsing | `workflow_host/descriptor.py:WorkflowDescriptor.from_mapping` | Add the optional `capability_requirements` mapping and strict parser without changing existing operational capability fields. |
| Registration policy and digest | `workflow_host/policy.py:compile_workflow_policy` | Store canonical capability requirements and their digest in `WorkflowPolicy` and its deterministic policy digest. |
| Existing availability check | `workflow_host/policy.py:resolve_capabilities` | Preserve this string-set preflight API; add a separate exact-contract resolver. |
| Package admission and preflight | `workflow_host/registration.py`, `workflow_host/preflight.py`, and package import path | Resolve capability requirements before any deferred model/converter side effect. |
| Built-in model runner/converter seams | `workflow_host/transformers_peft_model.py` and `workflow_converter_api` | Consume the new capability mapping only after the generic catalog/admission slice is proven. |

## Design Decisions

1. Add a narrow `workflow_host/capabilities.py` module for immutable capability
   contracts, receiver-local providers, canonical requirement encoding, exact
   resolution, and redacted unavailable results. Do not create a plugin manager,
   dependency installer, model registry, or device-selection API.
2. Keep contracts and providers separate. A contract is package-visible and
   digest-bound; provider identity, platform checks, availability, and host
   selection stay local to DAR.
3. `workflow-descriptor.yaml.capability_requirements` is the only package
   declaration. Its declared digest is calculated from normalized JSON
   information content, never from YAML bytes, and is recomputed by the
   receiver. The parser rejects unknown fields, duplicate YAML keys before
   mapping conversion, invalid ordering, invalid digests, and noncanonical
   feature lists.
4. Resolver success requires exact ID, version, digest, and all requested
   features. A provider may expose extra features. No version range, alias,
   profile fallback, or provider preference exists in package data.
5. Existing `WorkflowPolicy.required_capabilities` remains unchanged. The new
   `capability_requirements` and `capability_requirements_digest` are distinct
   fields to avoid silently widening or changing current preflight semantics.
6. Requirement resolution selects a provider from an immutable host snapshot.
   Its provider identity remains private, and a selected provider that becomes
   unavailable later fails closed instead of being replaced.

## Delivery Order

### S1 — Canonical contract and requirement values

1. Write fake-only RED tests for capability-contract canonical-byte/digest
   vectors; requirement vectors; duplicate IDs; unknown fields; malformed
   digests; unsorted requirements/features; NFC Unicode; and the
   absent-versus-empty-requirements case.
2. Add immutable value objects and canonical JSON helpers in
   `workflow_host/capabilities.py`. Include only contract ID/version/digest and
   features in the contract; model a provider separately with its local
   availability classification.
3. Publish at least one DAR-owned built-in contract definition with fixed
   positive and negative conformance vectors in the capability module and its
   focused tests. A provider is catalog-eligible only after its contract-level
   vectors pass; a nonempty package requirement record cannot be admitted by an
   empty built-in/provider catalog.

Exit: a package-independent test can reproduce every digest and reject every
noncanonical representation without importing a converter or model framework.

### S2 — Descriptor and policy binding

1. Write RED descriptor tests in `tests/test_dar_authoring_descriptor.py` for
   valid and invalid `workflow-descriptor.yaml.capability_requirements`
   mappings, including strict ordering, declared-digest mismatch, empty-list
   behavior, duplicate YAML keys, and invalid runner/converter bindings.
2. Add a duplicate-key-detecting descriptor loader before `WorkflowDescriptor`
   mapping conversion, then extend `WorkflowDescriptor` and `WorkflowPolicy`.
   Include canonical requirements and their declared/recomputed digest in
   `compile_workflow_policy`'s policy digest.
3. Update package writer, persisted registration record, and import verifier to
   bind the digest with existing package-content, material-lock, converter, and
   runtime compatibility values. Add cross-version fixtures proving legacy
   registrations remain valid and re-registration creates the canonical empty
   binding.
4. Enforce that a package declaring `capability_requirements` requires a DAR
   runtime version that supports this feature. Cover supporting and older
   receivers plus a legacy package with no mapping.

Exit: a registered package records one deterministic capability-requirements
digest and cannot be modified without invalidating its policy identity.

### S3 — Catalog resolution and provider conformance

1. Write RED fake-catalog tests for exact contract matching, requested-feature
   subset matching, mismatched version/digest, disabled provider,
   platform-incompatible provider, optional component absence, deterministic
   provider choice, unavailable-after-selection behavior, and redaction.
2. Implement the separate resolver and provider catalog. Its result carries
   requirement IDs and stable classification only; it exposes no provider ID,
   filesystem path, dependency detail, or host configuration.
3. Prove every registered provider passes the selected contract's conformance
   vectors before it is eligible for selection.

Exit: two conforming fake providers give identical contract-level outcomes;
every unavailable result is `capability_unavailable` and redacted.

### S4 — Ordered admission and deferred-boundary enforcement (inventory-gated)

1. C4.1 has inventoried every package-loading entrypoint, including
   staging, catalog, policy compilation, preflight, registration, host, runner,
   authoring-output, and preparation paths. Record which generic descriptor
   work may precede resolution and which package-owned asset/code loads must
   follow it. The route table, side-effect-boundary owner, and selected test
   file are recorded in `tasks.md`.
2. C4.2 has RED/GREEN integration coverage proving policy and
   preflight failure before runtime-manifest, converter-asset, and local-tool
   asset access; runner failure before artifact rematerialization, subprocess,
   network access, or model invocation; host failure before model preparation
   and ingress; and preparation failure before artifact verification. Provider
   revalidation occurs before runner manifest loading, preparation sealing, and
   ingress. The completed RED integration tests include
   sentinels for package converter asset
   read/open/hash and import, subprocess, network materialization, preparation,
   converter execution, model load, and sealed ingress, plus the bad
   provenance/content, duplicate/malformed requirement, digest mismatch,
   contract mismatch/unavailability, and binding-mismatch counter matrix for
   every boundary owner identified by the inventory.
3. C4.3 introduced one descriptor-only,
   provenance-verified admission phase before
   any workflow manifest, local asset, or converter validation. Route every
   inventory entrypoint through it, then perform canonical digest validation,
   provider resolution, binding validation, and only then asset/code loading.
4. C4.4 makes the C4.2 matrix green for a provider that becomes
   unavailable at each deferred boundary. Revalidate provider availability
   immediately before each boundary, fail closed without reselection, and
   preserve current preflight behavior for packages with no new requirements.

Exit: each unsatisfied requirement leaves every side-effect sentinel at zero;
no fallback or partial execution path remains.

### S5 — Model-material, runner, and converter integration (complete)

1. Approved `specs/workflow-model-materials/plan.md` and `tasks.md` named the
   lock/parser implementation and test seams before C5 implementation began.
2. Added fake-only mapping tests to the model-material path: preparation
   entries directly match one required preparation capability; v1 runner/profile
   pairs or v2 runner/descriptor bindings match one model-execution capability;
   converter manifests match one
   converter-host capability.
3. Updated `workflow-model-materials` implementation seams after S1–S4 and
   the approved model-material task dependency to
   bind the capability-requirements digest into `ModelExecutionBinding`; keep
   material transport, hashes, credentials, cache layout, and network policy
   universal DAR behavior rather than capabilities.
4. Updated runner and converter admission to request the resolver's private
   selected provider. Do not bind a receiver-installed execution-plugin
   identity into package data; retain it only in DAR-private audit records.

Exit: missing or incompatible preparation, runner, or converter-host capability
fails before its first corresponding side effect. Package-local converter assets
remain valid under their own sealed-asset contract but cannot provide a DAR
capability.

### S6 — Host capability-catalog composition (complete)

1. Added a keyword-only `capability_catalog` input to `LocalWorkflowHost.open()`.
   It remains receiver-local and is used by the host-owned registration
   admission.
2. Passed that same catalog to `WorkflowInvocationPreparationService` and
   `WorkflowRunner` without exposing or persisting selected provider identity.
3. Added fake-only host tests for the public open/register/prepare/run path, a
   requirements package without a catalog failing closed, and an unchanged
   legacy-package path.

Exit: an integration caller never mutates host-private attributes to execute a
sealed requirements package, and no catalog registry or configuration file is
introduced.

### S7 — Locked inference capability (planned)

1. Publish the exact `model.generate.v1` contract and conformance vectors
   without introducing a provider selector or domain output semantics.
2. Extend descriptor-only admission to bind an inference role to one sealed
   material-set role before asset import, material load, or input ingress.
3. Keep callback value schemas, resource limits, and sealed-asset delivery in
   `workflow-locked-inference-callback`; this plan owns only exact contract
   resolution and provider revalidation.

Exit: a package can require an exact generic inference behavior while only DAR
selects and revalidates its compatible receiver-local provider.

## Validation Strategy

Run focused tests after each slice, then run:

```text
poetry run pytest -q
poetry run ruff check src tests
git diff --check
poetry run pre-commit run --files <changed files>
```

All unit tests use fake contracts, providers, loaders, converters, and
side-effect sentinels. They must not download models, install dependencies,
load a framework, invoke a live provider, or run a model. A later manually
authorized model gate may verify a package requiring a real installed capability
only after S1–S5 pass fake-only coverage.

## Risks and Compatibility

- Existing workflow policy capability strings are not contract requirements;
  collapsing the two would change current package semantics. Keep both until an
  explicitly versioned migration is separately approved.
- Existing converter functionality remains implemented, but its capability
  catalog integration is pending C4.2–C5. Do not claim catalog-compliant
  package portability before the admission integration is delivered.
- A new capability contract is a DAR release artifact. A receiver without its
  contract/provider fails closed; package import must never install it.
- Nonstandard execution implementations remain reviewed receiver-installed
  providers. Their private identity is auditable but cannot be package-selected.
