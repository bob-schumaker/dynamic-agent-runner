# Workflow Model Materials Specification

## Metadata

- Feature slug: `workflow-model-materials`
- Status: proposed; no implementation is authorized by this document alone
- Owner: dynamic-agent-runner workflow-package and local-model boundaries
- Related specifications:
  - `specs/local-model-preparation/spec.md`
  - `specs/local-model-runner-interface/spec.md`
  - `specs/model-execution-plugin-interface/spec.md`
  - `specs/workflow-input-converter-plugin/spec.md`

## Objective

Make a durable sealed workflow package self-describing with respect to its exact
model material. A workflow author supplies a complete immutable model-material
declaration when DAR constructs the package. A recipient who has DAR can run
that package with only its declared runtime inputs; DAR reuses verified local
material or fetches, verifies, prepares, and executes the locked material when
host policy permits.

The declaration is package data, not executable setup code. DAR retains control
of downloading, cache layout, hash verification, deterministic preparation,
runner selection, device placement, resource limits, sealed ingress, tracing,
and result shaping.

## Problem Statement

The current local-model-preparation contract keeps model recipes in a host
catalog and lets a workflow name only a logical requirement. That makes a
package depend on the particular DAR installation that constructed it: the
same ZIP cannot necessarily be executed by another DAR installation that lacks
that catalog entry. A portable black-box workflow instead needs to carry the
precise dependency lock that DAR can independently verify and materialize.

Putting arbitrary loader or setup code in the package would replace that
portability problem with a supply-chain and host-control problem. The required
boundary is therefore a sealed declarative material lock interpreted only by
DAR's reviewed runners and preparation implementations.

## Scope

This feature defines:

1. a versioned, sealed workflow model-material declaration;
2. construction-time validation and package-digest binding of that declaration;
3. receiver-side verified cache reuse, download, and deterministic preparation;
4. exact binding from material declaration to a DAR-owned runner/profile; and
5. failure, portability, and validation requirements for an executable package.

## Non-Goals

This feature does not:

- allow runtime callers, prompts, or sealed payloads to select or change model
  material;
- permit invocation-time repositories, branches, filenames, commands, Python
  modules, loader functions, environment variables, cache paths, device
  policies, or `trust_remote_code` settings to replace sealed material;
- permit a declaration to introduce a runner or model-execution plugin that is
  not supplied and supported by the receiving DAR installation;
- make model weights part of the ordinary workflow ZIP;
- guarantee that a remote artifact remains published or that a receiving
  machine has enough compatible hardware; or
- move workflow-local domain conversion, output validation, or rendering into
  DAR.

## Terms and Trust Boundary

### Workflow author and workflow user

The workflow author is trusted during DAR package construction. The receiving
host must accept the sealed package under its package-origin/registration policy
before it materializes anything; this specification does not make an unsolicited
ZIP trusted. The workflow user invokes an accepted sealed package and supplies
only its declared runtime inputs. A user has no authority to edit the material
declaration, provide a model path, select a revision, or select a runner.

### Model-material declaration

A model-material declaration is the immutable dependency lock for one model
execution binding. It names a DAR-supported runner and loader profile, and
enumerates every required source and generated artifact. Every source member
has a role, repository identifier, immutable revision, filename, and SHA-256.
Every generated member has an approved preparation-recipe identifier, declared
inputs, output role, filename, and SHA-256.

The declaration may include a logical display name, but that name has no
selection authority. The exact declaration digest is the identity used for
preparation and execution.

### Preparation recipe

A preparation recipe is DAR-owned code/configuration identified by a stable
approved identifier. It defines a deterministic transformation that DAR knows
how to execute. A workflow declaration may select a compatible identifier and
pin its expected input/output hashes; it cannot supply converter commands,
containers, packages, or executable code.

### Material-lock digest

The material-lock digest is the canonical digest of the validated declaration.
DAR binds it to the workflow package digest, runner ID, loader-profile ID, and
any workflow-sealed converter digest at construction and registration. A change
to any of those values creates a different workflow identity and requires a new
package construction and seal.

## Declarative Shape

The eventual serialization is an implementation decision, but its information
content shall be equivalent to:

```yaml
model_materials:
  version: 1
  runner_id: transformers-peft-v1
  loader_profile_id: transformers-peft-single-image-v1
  artifacts:
    - role: base_weight_shard_00001
      group: base
      repository: example-org/example-model
      revision: <immutable revision>
      filename: model-00001-of-00002.safetensors
      sha256: <64 lowercase hexadecimal characters>
  preparation: []
```

DAR shall reject a declaration with unknown fields, duplicate roles, incomplete
required groups, non-immutable revisions, malformed or unsupported-artifact-
transport repository references, missing hashes, an unknown runner/profile, or
a transformation that is not approved for that runner/profile. It shall not
infer missing members from a Hub snapshot, filename convention, model card, or
similarly named artifact.

## Functional Requirements

### FR-1: Construction-time admission and sealing

DAR shall accept a model-material declaration only during authorized workflow
construction. Before sealing, it shall validate declaration syntax, exact
runner/profile compatibility, required groups and roles, hash format, approved
preparation-recipe compatibility, and package-contained converter compatibility
when a converter is present.

The resulting workflow package shall contain the canonical declaration and its
digest. Registration shall bind the package digest and material-lock digest.
Changing either after construction shall be rejected before material resolution
or sealed-input consumption.

### FR-2: Receiver-side materialization

Before loading the selected runner, DAR shall resolve the sealed declaration.
It shall reuse only cached source or prepared artifacts whose role, hash, and
declaration digest validate. If material is absent, DAR shall download only the
declared files and only when the receiving host's network/preparation policy
authorizes it. It shall verify each source hash before use and each generated
artifact's hash after deterministic preparation.

Materialization is a private prerequisite of workflow execution. It may run as
part of an invocation; no workflow user supplies a preparation receipt,
material-set identifier, cache path, or follow-up command. A host may expose a
separate prefetch operation as a convenience, but it must resolve the same
sealed declaration and cannot accept a caller-supplied replacement declaration.

### FR-3: Exact runner binding

DAR shall load model material only through the runner and loader profile locked
in the sealed declaration. The runner shall receive only a verified,
host-private prepared artifact set. It must retain its own local-only loading,
remote-code prohibition, device selection, resource limits, cancellation,
cleanup, tracing, and normalized-response obligations.

No model-execution plugin, converter, or runner may be fetched or selected from
the declaration at invocation time. A nonstandard model requires a separately
installed and registered DAR plugin whose identity is also bound at package
construction.

### FR-4: Fail-closed portability

DAR shall fail before model loading and before sealed-input consumption when
the package/DAR compatibility range, material-lock digest, runner/profile,
source availability, source hash, preparation output hash, or required runtime
dependency is invalid or unavailable. It shall not fall back to a different
revision, branch, file, model, runner, plugin, or cache location.

Failures may identify a stable classification such as `material_unavailable`,
`material_integrity_failed`, `material_preparation_failed`,
`runner_unavailable`, or `host_policy_denied`. They must not reveal credentials,
raw upstream errors, cache paths, source paths, shell commands, sealed payloads,
or model tensors.

### FR-5: Portable package boundary

The normal workflow ZIP contains the sealed workflow code/assets and its
material declaration, not model weights or machine-specific state. A recipient
with a compatible DAR installation may execute it by obtaining the exact locked
files through DAR's approved artifact source and cache mechanisms.

An offline artifact-cache bundle may be specified later as a separately
transported collection of the same hash-verified files. It must not alter the
normal package identity, bypass declaration verification, or become a runtime
input supplied by the workflow user.

## Acceptance Criteria

- Given a sealed package and an empty permitted cache, when host policy permits
  materialization, then DAR downloads exactly the declared files, validates
  hashes, performs only the declared preparation, and invokes the locked runner.
- Given a complete verified cache, when that package executes, then DAR makes
  no network call and uses only material matching its material-lock digest.
- Given a changed declaration, package, runner/profile binding, source hash, or
  generated-artifact hash, when execution begins, then DAR rejects it before
  loading a model or consuming the sealed input.
- Given a runtime caller provides a model name, path, revision, runner, or
  material declaration, when invoking a sealed workflow, then DAR rejects or
  ignores that value; it cannot change the locked material.
- Given an unrecognized preparation-recipe ID or a package-provided executable
  setup value, when DAR constructs or loads the workflow, then admission fails.
- Given the same workflow ZIP on another compatible DAR installation, when its
  locked artifacts are downloadable and host policy permits, then it resolves
  the same verified material without requiring an authoring-time host catalog.

## Required Implementation Discipline

Any implementation must follow TDD. Add fake-only RED tests first for
construction-time validation, canonical material-lock binding, cache hits,
authorized and denied downloads, per-file hash validation, preparation-output
validation, no-fallback behavior, invocation-time materialization, and
redaction. Unit tests must not download Hugging Face artifacts, load a live
model, or run a real converter. A separately authorized manual gate may run a
sealed package with declared model material and record only redacted outcomes.

## Supersession

This specification supersedes the model-material ownership provisions of
`specs/local-model-preparation/spec.md`: model pins and artifact closures are
now sealed workflow construction-time data rather than entries in a receiving
host's static recipe catalog. That specification remains authoritative for the
host-private cache, verification, deterministic-preparation, and artifact-set
mechanics until implementation work updates both specifications together.
