# Workflow Model Materials Implementation Plan

## Status

Approved 2026-09-09. This plan unlocks capability-requirements C5. All
implementation remains fake-only and test-first.

## Goal

Add the sealed `model-materials.json` lock/parser boundary described in
`spec.md`, bind its digest to package identity and registration, and defer all
download, preparation, framework import, and runner work until generic package
admission has accepted the exact capability requirements.

## Delivery Order

### M1 — Canonical lock values and parser

1. Add immutable lock/source/preparation value objects, canonical JSON bytes,
   lock digest, transformation digest, and strict JSON parser.
2. Validate exact keys, sorted source roles, fixed hash/revision shapes,
   ordered preparation inputs, role closure, cycles, orphan outputs, and no
   non-string scalars other than `format_version`.
3. Publish fixed positive and negative digest vectors. No model transport,
   framework, converter, subprocess, or network import is permitted here.

### M2 — Descriptor, manifest, and registration identity

1. Require a root `model-materials.json` only for packages that declare the
   corresponding material-backed runner binding; preserve legacy packages that
   lack it.
2. Bind the lock digest into package manifest/export/import verification,
   `WorkflowPolicy`, registration persistence, and registration digest.
3. Reject lock/descriptor/capability binding mismatches before any material
   cache lookup or package-owned converter asset access.

### M3 — Verified material admission

1. Introduce one generic material admission value that accepts only the parsed
   lock, a selected private capability provider, and host-owned material policy.
2. Validate sources and preparation operations against exact declared
   capabilities; bind the lock runner/profile pair to the exact runner
   capability. Do not admit recipe IDs, paths, endpoints, commands, or provider
   identities from package data.
3. Reuse a verified cache only after recomputing the lock/transformation hashes;
   perform download/preparation only after provider revalidation.

### M4 — Generic runner and converter integration

1. Derive a private `ModelExecutionBinding` from the validated lock, capability
   requirements digest, runner/profile contract, and sealed converter binding.
2. Route generic runner and converter admission through it. Preserve unrelated
   compatibility paths only until their separately scoped migrations; do not
   add new domain-named constructors.
3. Prove missing/incompatible material, runner, or converter capabilities fail
   before download, preparation, framework import, converter asset access,
   model load, or sealed ingress.

### M6 — Remove legacy floorplan host paths

1. Add regression tests that exercise the generic material, runner, and
   converter contracts without importing floorplan-named production modules or
   configuring a domain-named host profile.
2. Remove the floorplan vision module, fixed preparation recipes, named
   profile/host constructors, CLI configuration commands, and the in-tree Qwen
   GRPO converter. Rehome only scenario assets currently under production
   source; leave existing test-harness assets in place.
3. Prove production source and distributable package artifacts contain none of
   the enumerated floorplan model, adapter, converter, schema, renderer, or
   module identifiers. Allow those identifiers only under `tests/`.
4. Run focused regressions, the full suite, Ruff, `git diff --check`, and the
   package build to confirm generic package construction still works.

### M7 — Material sets for locked inference

1. Extend the canonical lock declaration to an ordered named material set while
   preserving v1 single-lock parsing and package identity.
2. Bind each inference role to exactly one material role; reject duplicate,
   missing, or cross-role substitution before any load or package asset import.
3. Coordinate the exact generation capability mapping with
   `workflow-locked-inference-callback`; do not add domain model names or
   provider configuration.

## Validation

Run focused tests per slice, then `poetry run pytest -q`,
`poetry run ruff check src tests`, `git diff --check`, and targeted pre-commit.
Unit tests must use fake transport, cache, provider, preparation, runner, and
converter collaborators only.
