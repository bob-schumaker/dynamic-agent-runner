# Workflow Capability Requirements Specification

## Metadata

- Feature slug: `workflow-capability-requirements`
- Status: C1–C5.6 are implemented and verified.
- Owner: dynamic-agent-runner package, capability, and workflow-host boundaries
- Plan: `plan.md`
- Tasks: `tasks.md`
- Related specifications:
  - `specs/workflow-model-materials/spec.md`
  - `specs/local-model-runner-interface/spec.md`
  - `specs/workflow-input-converter-plugin/spec.md`
  - `specs/model-execution-plugin-interface/spec.md`

## Objective

Let a sealed workflow package declare the standard DAR capabilities it needs,
without shipping a provider implementation for model loading, preparation, or
other DAR behavior. A receiver with DAR imports the package, DAR evaluates
those requirements against its installed capability catalog, and the workflow
either runs with no per-workflow receiver configuration or fails before
consuming an input.

## Problem Statement

Model materials, conversion, local execution, input conversion, and platform
services need durable compatibility boundaries. A package that names host
functions, adapter IDs, recipes, Python modules, device settings, or download
commands is tied to the DAR installation that created it. A package that ships
arbitrary implementation code is portable only by making every receiver execute
unreviewed code.

DAR needs a public catalog of common behavior contracts. A workflow needs to
state what behavior it requires, while DAR chooses an installed compatible
implementation under its own platform and resource policy.

## Scope

This feature defines:

1. versioned DAR capability contracts and an installed capability catalog;
2. canonical package capability requirements and their package-identity binding;
3. matching, provider selection, availability, ordered admission, and failure
   behavior; and
4. the boundary between package-declared behavior and DAR-owned implementation.

## Non-Goals

This feature does not:

- let a package select a Python module, binary, native library, endpoint,
  device, cache path, environment variable, subprocess, or provider instance;
- let a workflow user add, remove, override, or relax a requirement at runtime;
- define a package manager, download arbitrary runtime code, or make a missing
  capability automatically installable from a package;
- make a capability promise that an arbitrary model has adequate resources or
  that a remote model artifact remains available; or
- replace material hashes, runner input/output contracts, package provenance,
  or host policy.

## Terms

### Capability contract

A capability contract is an immutable DAR-owned public contract with these
fields:

```text
capability_id
contract_version
contract_digest
features
```

`capability_id` is a namespaced nonempty string. `contract_version` is a
nonempty compatibility version. `contract_digest` is the SHA-256 of the
canonical published contract schema and semantics. `features` is a finite set
of contract-defined feature names.

A contract identifies behavior, not an implementation. DAR ships canonical
contract documents for its built-in contracts. Their UTF-8 canonical JSON bytes
use recursively lexicographically sorted object keys, no insignificant
whitespace, and only strings, arrays, and objects; the contract digest is the
lowercase SHA-256 of those bytes. Contract documents define their allowed
feature names and provider conformance vectors.

### Capability provider

A capability provider is receiver-local DAR state that advertises one or more
exact capability contracts and is selected only by DAR. Its provider identity,
platform constraints, optional-component state, and availability are not part
of a capability contract or package identity. It reports only the stable
availability classifications `available`, `disabled`,
`platform_incompatible`, or `optional_component_missing`; diagnostics contain
no host paths, credentials, or raw dependency errors.

### Package capability requirement

The package-root `workflow-descriptor.yaml` descriptor contains exactly one optional
`capability_requirements` mapping. Its required fields are `format_version: 1`,
`required_capabilities`, `capability_requirements_digest`, and `bindings`; it
has no other fields. Each item has exactly
`capability_id`, `contract_version`, `contract_digest`, and
`required_features`. Items sort by `capability_id`; a capability ID occurs
once; `required_features` sorts lexicographically and must be a subset of the
selected contract's published features.

`bindings` has exactly `runner` and optional `converter` mappings. Each has
exactly `capability_id`, which must name one declared requirement. The runner
binding is required whenever `model-materials.json` is present; the converter
binding is required exactly when an input-converter manifest is present. A
preparation operation continues to reference its requirement directly. The
selected capability contract defines which locked execution identity (a v1
runner/profile pair or v2 runner/descriptor binding) or converter
ABI it accepts; DAR rejects an incompatible or duplicate binding.

The requirement asks DAR for behavior. It does not name a provider, preference,
binary, download source, execution profile, or fallback. A package may require,
for example, a standard local GGUF multimodal runner, a standard deterministic
GGUF quantization operation, or a standard sealed-image conversion contract.

Some single-purpose operations do not require their own `bindings` entry
because their capability ID is their only valid role. In particular, an
embedding-index workflow declares one `embedding.execute.v1` requirement in
addition to the required runner capability named by `bindings.runner` for its
model-material declaration. DAR binds the two internally; the workflow does
not name a provider or add an `embedding` selector to `bindings`.

The proposed `model.generate.v1` operation is likewise single-purpose, but its
generic inference role binds to a sealed model-material-set entry rather than a
provider selector. `workflow-locked-inference-callback` owns callback limits
and value contracts; this specification continues to own exact capability
matching and receiver-local provider selection. A package declares the exact
generation requirement once; all of its inference roles reference that one
requirement and separately bind distinct material roles.

`model.generate.v1` version `1` currently publishes the required `structured`
feature. A conforming provider must satisfy DAR-owned fake vectors for bounded
I/O, deadline handling, structured-value validation, and redacted failure.
The capability is generic: it establishes no prompt, vocabulary, output-label,
or domain interpretation contract.

The canonical requirements bytes are the UTF-8 canonical JSON representation
of the `format_version`, `required_capabilities`, and `bindings` information
content, with recursively sorted object keys, no insignificant whitespace, NFC
normalized strings, unescaped non-ASCII UTF-8 characters, and no number except
the integer `format_version`. Arrays retain declared order. The digest field is
omitted to avoid circularity. For example:

```json
{
  "format_version": 1,
  "required_capabilities": [{
    "capability_id": "model.execution.llama-cpp.v1",
    "contract_version": "1",
    "contract_digest": "<64 lowercase hexadecimal characters>",
    "required_features": ["multimodal"]
  }],
  "bindings": {"runner": {"capability_id": "model.execution.llama-cpp.v1"}}
}
```

The literal descriptor mapping additionally contains the derived
`capability_requirements_digest` field; the example shows only the information
content that is hashed.

The descriptor's YAML spelling is not the canonical form. DAR parses the
mapping with duplicate-key detection before it is converted to a mapping,
rejects malformed, duplicate, unsorted, or unknown values, then derives these
canonical bytes and its digest. The declared
`capability_requirements_digest` must exactly equal that digest.

An absent `capability_requirements` mapping denotes the canonical empty v1
requirements record: `format_version: 1`, an empty requirements list, and no
bindings. New registration records bind its derived digest. Existing
pre-feature registration records remain valid under their recorded package
format and do not invoke the new resolver; re-registration under this feature
creates the empty-record binding. A package that declares the mapping must use
a DAR runtime version that supports this feature.

### Capability resolution

At admission and before any deferred side-effect boundary, DAR matches every
package requirement to an installed contract with the exact capability ID,
contract version, contract digest, and all requested features. DAR selects a
compatible available provider using only host policy. A package cannot observe
or influence that selection.

## Package Identity and Lifecycle

The canonical capability-requirements bytes have a lowercase SHA-256
`capability_requirements_digest`. Package registration binds that digest with
the package content digest, material-lock digest where present, converter asset
digest where present, and the existing DAR runtime compatibility declaration.

Package construction validates requirement syntax and known contract digests
from the construction DAR and writes the declared requirements digest in the
package descriptor. Registration persists that digest beside the existing
descriptor/package-content, material-lock, converter-asset, and DAR-runtime
bindings. Receiver admission recomputes and compares it after provenance and
content verification. Admission has this fixed order:

1. verify package provenance and content, then parse only generic descriptors;
2. validate capability-requirement syntax and canonical digest;
3. resolve every requirement to one available provider from one immutable host
   availability snapshot;
4. validate material, runner, and converter mappings and derive private binding;
5. only then permit material download, preparation, model loading, converter
   asset loading, or sealed-input ingress.

Receiver execution repeats provider availability validation immediately before
each deferred side-effect boundary. The private provider selected at admission
must remain available; DAR fails closed rather than selecting another provider.
A receiver may report all unsatisfied
capability IDs in one bounded redacted diagnostic, but it must not attempt a
fallback provider or partial execution.

## Functional Requirements

### FR-1: Exact contract matching

DAR shall satisfy a requirement only when capability ID, contract version,
contract digest, and every required feature exactly match an installed contract.
An installed contract may offer additional features; they neither invalidate a
match nor satisfy an absent ID, version, digest, or requested feature. A
provider unable to run the exact contract is unavailable. DAR shall not use
prefix, range, best-effort, inferred, or fallback matching.

### FR-2: DAR-owned provider selection

DAR shall choose the provider for a satisfied contract using host policy only.
The package may request behavior but cannot select CPU/MPS/GPU placement, an
endpoint, a runner class, a transform implementation, or any other provider
detail. All selected providers must preserve the contract's published
semantics and locked material/output integrity requirements.

### FR-3: Fail-closed execution

An unavailable, disabled, platform-incompatible, or contract-mismatched
requirement yields `capability_unavailable` before network material download,
preparation, model loading, converter execution, or sealed-input consumption.
The error may identify the capability ID and stable availability classification;
it must not disclose installed packages, host paths, raw loader errors,
credentials, or provider internals.

An exact contract mismatch is reported as `capability_unavailable` with the
requirement ID and no availability classification. A provider availability
failure may additionally report only its stable classification.

### FR-4: No package runtime implementation

A capability requirement cannot introduce executable runtime code. Model
preparation and model execution are performed only by a selected DAR capability
provider. Workflow-local code assets remain permitted only where another
approved sealed-asset contract explicitly allows them, such as an input
converter; they cannot implement, shadow, register, or extend a DAR capability.

### FR-5: Standard model capability integration

The following mapping is normative. Material transport, locked file download,
cache layout, credentials, and network policy remain universal DAR behavior and
are not package capability requirements. A preparation operation directly
references one requirement entry. A v1 runner/profile pair or v2
runner/descriptor binding maps to exactly one
required model-execution capability whose contract defines that pair and any
required features. A sealed converter manifest maps to exactly one required
converter-host capability whose contract defines its ABI and compatible runner
contract. DAR rejects a missing, duplicate, or incompatible mapping before it
loads a provider or package-owned converter asset. A preparation cache identity
may include the exact capability contract digest plus locked input and output
hashes; it must not include a host recipe ID or provider implementation identity.

Every provider of a contract shall pass that contract's DAR-owned fake-provider
conformance vectors before catalog admission. Vectors cover requested features,
declared output-integrity effects, resource-limit behavior, and redacted
unavailable/failure outcomes; they do not compare model text or provider-private
implementation details.

## Acceptance Criteria

- Given a package whose requirement exactly matches an available DAR capability,
  when it is imported and executed, then DAR selects a compatible provider
  without package or workflow-user configuration.
- Given a capability ID with a different contract digest, version, or a missing
  required feature, when the package is imported or run, then DAR returns
  `capability_unavailable` before materialization or input consumption.
- Given two host providers for one capability contract, when either is chosen
  under host policy, then the package observes the same declared behavior and
  locked output verification.
- Given a package declares an implementation path, provider preference,
  endpoint, device setting, or capability not in its canonical requirements,
  when DAR admits it, then admission fails.
- Given a receiver already has every required capability, when a user receives
  an accepted workflow ZIP, then no model-specific configuration or installation
  action is required from that user.

## Required Implementation Discipline

Implementation must follow TDD. C1–C3 and the C4.1 route inventory are
verified; C4.2 must complete fake-only RED/GREEN coverage for the remaining
deferred boundaries before C4.3 or C4.4 can be complete. The full suite covers
canonical contract and requirement bytes/digests, duplicate and malformed
requirements, exact contract matching, missing/digest/version/feature/provider
mismatch, provider selection isolation, published built-in-contract
conformance, runtime-version gating, pre-ingress failure, redaction, and
package-identity changes. Before admission implementation, every
package-loading route and its deferred-boundary test owner must be recorded.
The completed C4 matrix must prove that a requirement cannot cause
package-owned module or converter-asset read, hash, or import, subprocess
launch, network download, preparation, model load, or sealed-input ingress
before resolution passes. Unit tests must not install a runtime dependency,
download a model, or invoke a live provider.

## Supersession and Integration

This specification is the authoritative owner of generic package capability
requirements and DAR capability resolution. `workflow-model-materials` owns
locked model data and maps its materialization/preparation/runner needs to these
requirements. `local-model-runner-interface` owns the semantics of built-in
model runner capabilities. `workflow-input-converter-plugin` owns the semantics
of converter assets and maps them to converter-host capabilities. The existing
model-execution-plugin identity binding is replaced by a receiver-installed
provider of the applicable model-execution capability; provider identity remains
DAR-private audit state. Existing named host profiles and recipe IDs are legacy
implementation evidence only; new packages must not depend on them.
