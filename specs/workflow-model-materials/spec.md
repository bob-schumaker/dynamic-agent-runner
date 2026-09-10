# Workflow Model Materials Specification

## Metadata

- Feature slug: `workflow-model-materials`
- Status: implementation in progress
- Owner: dynamic-agent-runner workflow-package and local-model boundaries
- Plan: `plan.md` (approved 2026-09-09)
- Tasks: `tasks.md` (approved 2026-09-09)
- Related specifications:
  - `specs/local-model-preparation/spec.md`
  - `specs/workflow-capability-requirements/spec.md`
  - `specs/local-model-runner-interface/spec.md`
  - `specs/llama-cpp-local-model/spec.md`
  - `specs/model-execution-plugin-interface/spec.md`
  - `specs/workflow-input-converter-plugin/spec.md`

## Objective

Make a durable sealed workflow package self-describing with respect to its exact
model material. A workflow author supplies a complete immutable model-material
declaration when DAR constructs the package. A recipient who has DAR can run
that package with only its declared runtime inputs; DAR reuses verified local
material or fetches, verifies, prepares, and executes the locked material when
host policy permits.

The declaration is sealed package data, not an invocation-time setup channel.
DAR retains control of downloading, cache layout, hash verification,
capability/provider selection, runner selection, device placement, resource
limits, sealed ingress, tracing, and result shaping.

## Problem Statement

The current local-model-preparation contract keeps model recipes in a host
catalog and lets a workflow name only a logical requirement. That makes a
package depend on the particular DAR installation that constructed it: the
same ZIP cannot necessarily be executed by another DAR installation that lacks
that catalog entry. A portable black-box workflow instead needs to carry the
precise dependency lock that DAR can independently verify and materialize.

An unrestricted setup command would replace that portability problem with a
supply-chain and host-control problem. The required boundary is a sealed
material lock that declares a standard DAR preparation capability when
preparation is needed.

## Scope

This feature defines:

1. a versioned, sealed workflow model-material declaration;
2. construction-time validation and package-digest binding of that declaration;
3. receiver-side verified cache reuse, download, and deterministic preparation;
4. exact binding from material declaration to a DAR-owned runner/profile; and
5. generic runner-registry and host-policy boundaries; and
6. failure, portability, and validation requirements for an executable package.

Version 1 supports only the existing Hugging Face per-file transport, complete
closure validation owned by a versioned DAR loader profile, a finite ordered
list of deterministic preparation operations selected through required DAR
capabilities, and the built-in
`transformers-peft-v1` and `llama-cpp-v1` runner contracts defined below. An
embedding workflow may use the same lock format with a DAR-supported embedding
runner/profile; its distinct execution operation is governed by the exact
`embedding.execute.v1` requirement under `workflow-embedding-index-artifacts`.
It
does not standardize a general model registry, a transform graph language, or
an unrestricted execution environment.

The proposed locked-inference callback requires a canonical material set:
ordered named roles each hold one existing immutable lock, and a declared
inference role binds to exactly one material role. Existing single-lock
packages remain valid unchanged. Roles do not expose receiver providers,
execution settings, or model paths. The inference descriptor owns inference
role names; material-role names are separately unique, and each inference role
maps to one distinct material role.

## Non-Goals

This feature does not:

- allow runtime callers, prompts, or sealed payloads to select or change model
  material;
- permit invocation-time repositories, branches, filenames, commands, Python
  modules, loader functions, environment variables, cache paths, device
  policies, or `trust_remote_code` settings to replace sealed material;
- permit a declaration to introduce a runner or model-execution plugin that is
  not supplied and supported by the receiving DAR installation;
- permit a declaration to select an artifact endpoint, credentials, redirects,
  a download command, transform dependency environment, transform
  implementation, or provider;
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

### Compatible receiver

A compatible receiver has accepted the package through DAR's existing package
source and signature policy, supports the package's existing
`dar_runtime.required_version`, and satisfies every sealed capability
requirement. A package-local input converter remains governed by
`workflow-input-converter-plugin`; a model-execution provider is a
receiver-installed DAR capability, never loader code fetched from this package.

### Model-material declaration

A model-material declaration is the immutable dependency lock for one model
execution binding. It names a DAR-supported runner and loader profile, and
enumerates every required source and generated artifact. Every source member
has a role, repository identifier, immutable revision, filename, and SHA-256.
Every generated member has one required preparation capability, declared inputs,
output role, filename, SHA-256, and a recomputable transformation digest.

The declaration's logical model ID is the package-local model-binding name. DAR
validates it against the package's model declaration at construction and exposes
it only as the locked adapter alias. It is never an artifact resolver key or a
mechanism for selecting a host adapter. The exact declaration digest is the
identity used for preparation and execution.

### Preparation operation and transformation digest

A preparation operation references one required DAR preparation capability. DAR
selects its provider under `workflow-capability-requirements`; a workflow cannot
select code, dependencies, a recipe ID, binary, command, or provider. The
provider receives only verified declared input artifacts and an empty bounded
output location, and operates under DAR's network, filesystem, process, and
resource policy.

The transformation digest is the lowercase SHA-256 of the canonical
transformation record with its own `transformation_digest` field omitted. It
binds the required capability ID, contract version, and contract digest; the
ordered input roles and their locked hashes; and the declared output role,
group, filename, and SHA-256. It is a cache and trace identity, not a symbolic
recipe ID or provider identity. DAR calculates it during construction and a
receiver recomputes it before every cache reuse or preparation attempt.

### Package binding

The package content digest is DAR's existing deterministic package-manifest
content digest. The material-lock digest is separate: it is the SHA-256 of the
canonical `model-materials.json` bytes. Package content includes that file, so
the package digest changes when the lock changes; lock bytes never include
either digest. Registration stores and hashes this non-circular tuple:

```text
(package_content_digest, material_lock_digest, capability_requirements_digest,
 runner_contract, loader_profile_contract, converter_asset_digest?,
 converter_host_capability_contract?)
```

The existing package `runtime_format_version`, `descriptor_format_version`, and
`dar_runtime` fields remain the package-compatibility contract. The lock adds no
parallel package-version mechanism.

## ModelDependencyLock v1

The lock is the package-root file `model-materials.json`. It is UTF-8 JSON with
no byte-order mark. Its canonical bytes use recursively lexicographically
sorted object keys, no insignificant whitespace, UTF-8 string characters, and
integer `format_version`; all other scalar values are strings. `sources` sort
by `role`, and `preparation` order is significant. Its digest is the lowercase
SHA-256 hex digest of those canonical bytes. DAR shall publish fixed positive
and negative canonical-byte/digest test vectors.

The only permitted top-level keys are `format_version`, `logical_model_id`,
`runner_contract`, `loader_profile_contract`, `sources`, and `preparation`.
For v1, `format_version` is `1`; `logical_model_id` is the sealed package-local
adapter alias, never an artifact resolver key. The information content is
exactly:

```json
{
  "format_version": 1,
  "logical_model_id": "example-model",
  "runner_contract": {"id": "transformers-peft-v1", "version": "1"},
  "loader_profile_contract": {
    "id": "transformers-peft-single-image-v1", "version": "1"
  },
  "sources": [{
    "role": "base_weight_shard_00001", "group": "base",
    "source_type": "huggingface_file",
    "repository": "example-org/example-model",
    "revision": "<40 lowercase hexadecimal commit id>",
    "filename": "model-00001-of-00002.safetensors",
    "sha256": "<64 lowercase hexadecimal characters>"
  }],
  "preparation": []
}
```

Each source has exactly the displayed keys. A source role is globally unique;
`group` is required by the locked profile; `source_type` is exactly
`huggingface_file`; `revision` is a full lowercase 40-hex commit identifier;
and `sha256` is lowercase 64-hex. DAR uses its configured Hugging Face transport
only, with host-owned credentials and network policy. It must not use snapshot
discovery, branch/tag resolution, redirects to another endpoint, or inferred
files.

Each `preparation` item has exactly `capability_id`, `contract_version`,
`contract_digest`, `inputs`, `output`, and `transformation_digest`. `inputs` is
a nonempty ordered list of earlier unique roles. The capability fields must
exactly match one entry in the package's canonical `required_capabilities`
list. The lock's `runner_contract` and `loader_profile_contract` must match the
package `capability_requirements.bindings.runner` contract. `output` has
exactly `role`, `group`, `filename`, and `sha256`; its role
is new and its hash is lowercase 64-hex. A transformation may consume source or
earlier output roles only. DAR rejects cycles, orphan outputs, duplicate roles,
unconsumed nonterminal outputs, absent or mismatched capability requirements,
or a transformation incompatible with the locked runner/profile.

DAR computes the transformation digest at construction after authoring
preparation succeeds, records it with the expected output hash, and recomputes
it from the lock before every receiver-side cache lookup or execution. A
receiver never creates an authoritative digest for an undeclared capability.

For example, a single sealed transformation has this information content:

```json
{
  "capability_id": "model.prepare.gguf.quantize.q4-k-m.v1",
  "contract_version": "1",
  "contract_digest": "<64 lowercase hexadecimal characters>",
  "inputs": ["base_model_f16"],
  "output": {
    "role": "base_model",
    "group": "base",
    "filename": "model-q4_k_m.gguf",
    "sha256": "<64 lowercase hexadecimal characters>"
  },
  "transformation_digest": "<64 lowercase hexadecimal characters>"
}
```

The loader-profile contract owns exact required groups, roles, and loader
arguments. DAR rejects incomplete, additional, or incompatible closure members
before a framework import. It shall not infer members from a filename, Hub
snapshot, model card, or similarly named artifact.

## Built-in llama.cpp Profiles

`llama-cpp-v1` is a DAR-built runner contract for verified local GGUF
execution through the existing llama.cpp adapter boundary. It is not a general
purpose loader-config or constructor-argument channel. Every profile below
requires `runner_contract` to be exactly `{"id": "llama-cpp-v1", "version":
"1"}` and maps only the stated terminal artifacts from the verified private
artifact set:

| Loader profile | Required terminal roles | DAR-owned adapter mapping | Payload capability |
| --- | --- | --- | --- |
| `llama-cpp-text-v1` | `base_model` in group `base` | `model_path` | text only |
| `llama-cpp-multimodal-v1` | `base_model` in `base`; `vision_projector` in `vision` | `model_path`; `clip_model_path` | sealed payload through `llama-cpp-chat-v1` |
| `llama-cpp-multimodal-lora-v1` | `base_model` in `base`; `vision_projector` in `vision`; `adapter` in `adapter` | `model_path`; `clip_model_path`; `lora_path` | sealed payload through `llama-cpp-chat-v1` |

The `base_model` artifact must be a hash-verified GGUF file. The projector and
adapter artifacts are exact, hash-verified files consumed only by their stated
profile; DAR never discovers a companion file from the Hub, a directory, or a
filename convention. The profile must reject every missing, duplicate, or extra
terminal role before importing llama.cpp.

For a multimodal profile, `llama-cpp-chat-v1` is the corresponding
workflow-input-converter runner execution contract. Its sealed converter may
produce only the private, validated llama.cpp chat-message representation for
the one request; it cannot select material or pass arbitrary llama.cpp
constructor arguments. The text profile does not require a converter when the
workflow has no sealed payload.

The material lock must not contain a local path, cache root, endpoint,
credential, `n_ctx`, `n_batch`, `n_gpu_layers`, thread count, GPU/Metal/CUDA
selection, seed, verbosity, arbitrary `model_kwargs`, or a `chat_format` value.
DAR owns those host-policy settings. The profiles rely on GGUF chat-template
metadata; supporting a model that needs another immutable prompt-format choice
requires a new reviewed profile version rather than a free-form lock field.

## Sealed Execution Binding and Runner Registry

At package admission, DAR first resolves the package's required capabilities
under `workflow-capability-requirements`, then derives one immutable
`ModelExecutionBinding` from the package descriptor, material lock, and any
sealed converter asset. It is a host-private value, not an additional
caller-facing package format. Its exact content is the package-local logical
model ID, runner contract, loader-profile contract, material-lock digest,
capability-requirements digest, and converter binding when the profile requires
one. The Package binding includes its deterministic digest.

DAR resolves that binding through one `ModelRunnerRegistry`, after capability
resolution has succeeded. The material lock's exact runner/profile pair maps to
the `capability_requirements.bindings.runner` required model-execution
capability under `workflow-capability-requirements`; the registry chooses an
available provider
of that contract. A selected provider receives the binding, a lazy resolver for
the verified private artifact set, and the receiving host's policy; it never
receives a workflow-supplied path, constructor mapping, or unrestricted package
object.

The receiving host supplies a separate `HostRunnerPolicy`: cache and network
permission, local endpoint configuration where applicable, hardware placement,
resource limits, and dependency availability. It is not serialized into the
workflow ZIP and cannot change a package's material lock, runner contract,
loader profile, or converter binding.

A workflow creator may require any standard DAR capability contract and may
include workflow-local converter, postprocessor, and domain-tool assets only
where their own contracts permit them. A workflow package must not supply a
preparation implementation, runner factory, framework import target, loader
function, or native library. A non-built-in runner is a receiver-installed,
reviewed DAR capability with an exact public contract verified during package
admission.

An embedding workflow retains this runner/profile binding and additionally
declares exactly one `embedding.execute.v1` requirement. That operation does
not add a descriptor `bindings` key: its capability ID is unambiguous. DAR
derives its host-private embedding binding from the material execution binding
and the exact embedding capability requirement, then resolves a deterministic
provider before sealed document ingress. This does not make a direct local
embedding adapter a package-selected loader.

DAR's package-import and registration control plane is generic. It accepts a
package's descriptor, material lock, and declared sealed assets, validates the
binding, and records the resulting workflow identity. It must not expose a
model-, model-family-, or domain-named `configure-*` command for new packages.
Generic host configuration may still set HostRunnerPolicy or configure a
caller-owned OpenAI-compatible endpoint; neither operation chooses package
material or names a package-specific adapter.

The named Fastmail and floorplan profile constructors in the current host are
legacy compatibility paths, not future package architecture. New packages use
the generic bindings: a text lock for the former Fastmail model; a
`llama-cpp-multimodal-lora-v1` lock plus sealed converter for the former
llama.cpp floorplan model; and the locked Transformers/PEFT profile for the
former native floorplan model. Before this specification is complete, DAR must
remove the floorplan-named host code, configuration commands, preparation
recipes, and package-construction paths. The scenario's model lock, converter,
renderer, fixtures, and acceptance runner belong only in the test harness. DAR
must not construct a new package from a named domain adapter ID.

A model-specific converter implementation is a workflow asset, even when it is
not domain-specific. For example, the present Qwen image decoder and
chat-template packer belong in the workflow package that locks that Qwen
profile, not in `workflow_host`. The asset is sealed and admitted under the
public converter ABI defined by `workflow-input-converter-plugin`; it must not
import DAR's private `workflow_host` modules.

## Functional Requirements

### FR-1: Construction-time admission and sealing

DAR shall accept `model-materials.json` only during authorized workflow
construction. Before sealing, it shall validate canonical bytes, schema, exact
runner/profile compatibility, profile closure, source pins, preparation order,
required capability contracts, recomputed transformation digests, and
package-contained converter compatibility.

The resulting package manifest shall include the lock file and its content hash.
Import/registration verifies package provenance and package content first, then
parses and hashes the lock, verifies receiver compatibility, and persists the
Package binding. Changing any bound value is rejected before download, model
load, ingress, prepared-input issue, or sealed-input consumption.

### FR-2: Receiver-side materialization

Material resolution is mandatory before ingress or prepared-input issue, even
for direct host APIs. Its only eligible states are `absent`, `source_verified`,
and `prepared_verified`; downloads and transforms use private temporary state.
DAR serializes materialization per material-lock digest and transformation
digest, atomically promotes only hash-verified members, and removes or
quarantines partial, cancelled, stale, or mismatched members. A failure never
makes a partial set eligible.

DAR reuses only cache members whose role, hash, material-lock digest, and any
applicable transformation digest validate. If material is absent, it downloads
only locked source files when the receiving host's network/preparation policy
authorizes it. It verifies each source hash before use, resolves the required
preparation capability, recomputes each transformation digest, and verifies
each transform output hash after preparation.

Materialization is a private prerequisite of workflow execution. It may run as
part of an invocation; no workflow user supplies a preparation receipt,
material-set identifier, cache path, or follow-up command. A host may expose a
separate prefetch operation as a convenience, but it must resolve the same
sealed declaration and cannot accept a caller-supplied replacement declaration.

### FR-3: Exact runner binding

DAR shall derive and validate one ModelExecutionBinding, then load model
material only through the exact runner and loader profile resolved from the
ModelRunnerRegistry. The runner shall receive only the binding, a verified
host-private prepared artifact set, and HostRunnerPolicy. It must retain its
own local-only loading, remote-code prohibition, device selection, resource
limits, cancellation, cleanup, tracing, and normalized-response obligations.

No model-execution provider, converter, or runner may be fetched or selected
from the declaration at invocation time. A nonstandard model requires a
separately installed and registered DAR provider of the exact required
model-execution capability. Its identity, version, and distribution digest are
DAR-private audit state, not package binding. A package cannot shadow a
built-in runner or register its own runner factory.

### FR-4: Fail-closed portability

DAR shall fail before model loading and before sealed-input consumption when
package provenance, package/DAR compatibility, material-lock digest,
runner/profile contract, source availability, source hash, preparation output
hash, or required runtime dependency is invalid or unavailable. It shall not
fall back to a different revision, branch, file, model, runner, plugin, or cache
location.

Failures may identify a stable classification such as `material_unavailable`,
`material_integrity_failed`, `material_preparation_failed`,
`runner_unavailable`, or `host_policy_denied`. They must not reveal credentials,
raw upstream errors, cache paths, source paths, shell commands, sealed payloads,
or model tensors.

### FR-5: Portable package boundary

The normal workflow ZIP contains only DAR-admitted package assets and its lock,
not model weights or machine-specific state. A recipient with a compatible DAR
installation may execute it by obtaining the exact locked files through DAR's
approved artifact source and cache mechanisms.

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
- Given a caller supplies a model name, path, revision, runner, or material
  declaration, then the invocation schema rejects it; no override is ignored.
- Given an unavailable or mismatched preparation capability, malformed
  transformation digest, or package-provided preparation implementation, when
  DAR constructs or loads the workflow, then admission fails.
- Given locked source artifacts and a declared preparation capability, when a
  receiver first needs its output, then DAR recomputes the transformation
  digest, reuses only a matching verified cache entry, or invokes the
  DAR-selected provider and verifies the declared output hash before promotion.
- Given a `llama-cpp-v1` lock, when its profile closure is verified, then DAR
  maps only the profile's verified terminal roles to the local adapter and does
  not discover sibling artifacts or accept package-provided constructor
  settings.
- Given a multimodal llama.cpp profile, when a workflow consumes sealed bytes,
  then only a sealed converter declaring `llama-cpp-chat-v1` may pack the
  request; text, bytes, or converter output cannot select model material,
  hardware configuration, or a llama.cpp adapter.
- Given a sealed ModelExecutionBinding, when DAR creates an adapter, then it
  resolves the exact runner/profile through ModelRunnerRegistry and passes only
  the binding, verified artifacts, and HostRunnerPolicy; no domain adapter ID
  or package-supplied factory participates in dispatch.
- Given a workflow requires a non-built-in execution capability, when the
  receiver has no available reviewed provider for it, then DAR rejects the
  package before materialization, ingress, or framework import.
- Given a legacy named host profile, when a new workflow package is
  constructed, then DAR rejects it as a package model binding; only explicit
  read-only compatibility for an already-issued profile may remain.
- Given package import or registration, when the package selects a built-in
  runner/profile, then the generic control plane admits it without invoking a
  model- or domain-named configuration command.
- Given the same workflow ZIP on another compatible DAR installation, when its
  locked artifacts are downloadable and host policy permits, then it resolves
  the same verified material without requiring an authoring-time host catalog.
- Given a rejected package, lock, profile, cache member, or materialization
  policy, then downloader, model-loader, and ingress counters remain zero.
- Given cancellation or concurrent materialization for one lock, then no
  partial member becomes eligible and every later run revalidates the promoted
  set before use.

## Required Implementation Discipline

Any implementation must follow TDD. Add fake-only RED tests first for fixed
canonical-byte/digest vectors, malformed/cyclic closure rejection, non-circular
Package binding, package provenance/compatibility rejection, profile/plugin
contract mismatch, cache hits, authorized and denied downloads, per-file hash
validation, preparation-output validation, cancellation/concurrency cleanup,
pre-ingress rejection, no-fallback behavior, and redaction. Add fake-only
coverage for each llama.cpp profile's exact closure, role-to-adapter mapping,
multimodal converter-contract mismatch, and rejection of package-provided
hardware or constructor settings. Add RED coverage for canonical
transformation-digest vectors, receiver-side recomputation, unavailable or
mismatched capability rejection, cache-key separation for distinct capability
contracts over the same source, and rejection of a missing or stale output. Add
RED coverage for generic registry dispatch, built-in runner reservation,
reviewed-plugin identity mismatch,
HostRunnerPolicy isolation, and rejection of named legacy adapter IDs during
new package construction. Add a fake-only registration test proving that a
package-owned converter imports only the public converter ABI and that a
converter importing `workflow_host` is rejected. Unit tests must not download
Hugging Face artifacts, load a live model, or run a real converter. A separately
authorized manual gate may run a sealed package with declared model material and
record only redacted outcomes.

## Supersession

This specification supersedes the model-material ownership provisions of
`specs/local-model-preparation/spec.md`: model pins and artifact closures are
now sealed workflow construction-time data rather than entries in a receiving
host's static recipe catalog. It also supersedes that specification's
DAR-owned preparation-recipe identifier: required DAR preparation capabilities
and their recomputed transformation digests are the portable transformation
contract.
That specification remains authoritative for host-private cache, verification,
preparation isolation, and artifact-set mechanics until implementation work
updates both specifications together.
