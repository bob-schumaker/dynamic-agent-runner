# Local Model Preparation Specification

## Metadata

- Feature slug: `local-model-preparation`
- Status: ready for implementation
- Owner: dynamic-agent-runner
- Implementation plan: `plan.md`
- Task list: `tasks.md`
- Related specifications:
  - `specs/natural-language-workflow-authoring/spec.md`
  - `specs/llama-cpp-local-model/spec.md`
  - `specs/hugging-face-support-layer/spec.md`
  - `specs/local-model-availability-api/spec.md`
  - `specs/workflow-input-converter-plugin/spec.md`

## Objective

Make a workflow's declared logical local-model requirement executable without
exposing model paths, cache layout, artifact handles, or conversion steps to the
workflow author or user.

For a known model/runtime pair, DAR resolves a reviewed, pinned recipe to the
complete artifact set required by that runtime. It reuses valid cached artifacts,
downloads missing source artifacts when preparation is authorized, performs any
declared deterministic transformation, verifies the completed set, and makes it
available under the original logical model name.

A recipe may declare a standard runtime compatibility profile. The first native
profile is `transformers-peft-v1`: a complete grouped base checkpoint and PEFT
adapter closure loaded by DAR's generic local runner. The profile is generic;
the recipe remains model-specific and may be rejected when it requires custom
code or nonstandard preprocessing.

For example, the requirement `qwen25-vl-3b-floorplan-grpo` with the llama.cpp
vision adapter resolves to a pinned Qwen2.5-VL base GGUF, its matching vision
projector, and the converted floorplan LoRA GGUF. The workflow and its prompt
continue to name only `qwen25-vl-3b-floorplan-grpo`.

## Problem Statement

Current local-model resolution supports one model file and a caller-provided
configuration. Multimodal and adapter-tuned models may require several mutually
compatible files and, in some cases, a deterministic conversion before they can
be passed to a runtime. Requiring a user to find and pass those paths is both
opaque and error-prone. Embedding paths in a workflow package would make a
portable workflow machine-specific and could grant the model information about
the caller's filesystem.

The natural-language authoring flow therefore needs a DAR-owned preparation
capability. It must be narrow: a model name in a workflow is not authority to
download an arbitrary Hub repository, execute arbitrary conversion code, or
choose a substitute model.

## Scope

This feature defines:

1. host-owned, reviewed recipes mapping a logical model requirement and adapter
   to a pinned multi-file artifact set;
2. preparation-time cache lookup, download, conversion, validation, and
   redacted readiness reporting;
3. resolution of a prepared artifact set to the exact adapter configuration at
   workflow invocation; and
4. the first recipe for `qwen25-vl-3b-floorplan-grpo` on llama.cpp vision; and
5. preparation requirements for its reviewed `transformers-peft-v1` native
   closure, whose execution contract is specified by
   `specs/local-model-runner-interface/spec.md`.

## Non-Goals

This feature does not:

- infer a model requirement from arbitrary prompt text at execution time;
- put Hub revisions, hashes, cache roots, artifact paths, or conversion commands
  in a portable workflow package;
- discover, prepare, or substitute arbitrary Hugging Face models based only on a
  package-provided repository name;
- own llama.cpp installation, server lifecycle, GPU selection, or model quality
  evaluation;
- translate the floorplan model's structured JSON into SVG or validate SVG;
- expose a preparation receipt, `material_set_id`, generated artifact ID, or
  filesystem path as a value the user must supply to a later step;
- delete or broadly scan caller-owned model directories; or
- make live Hub, model, or conversion calls in unit tests.

## Terms and Boundaries

### Logical model requirement

A workflow declares a stable model identifier, required adapter, and required
capabilities. For the floorplan workflow these are
`qwen25-vl-3b-floorplan-grpo`, the llama.cpp vision adapter, and
`multimodal_input`. This declaration is portable and contains no physical
artifact location.

### Preparation recipe

A preparation recipe is a host-owned reviewed mapping for one exact logical
model requirement and adapter. It declares every source artifact by immutable
repository revision, filename, expected digest, role, and compatible runtime
format. It may also declare a deterministic transformation with a pinned tool
version and input/output roles.

Recipes are implementation configuration, not workflow-authored data. A
workflow may select only a recipe already known to the host for its exact model
and adapter. Unknown requirements are unavailable; DAR must not use Hub search
or a similarly named model as fallback.

### Prepared artifact set

A prepared artifact set is the verified, runtime-ready result of one recipe.
It may contain multiple files, such as `base_model`, `vision_projector`, and
`adapter`. Its paths and cache representation remain host-private. The only
stable user-facing reference is the original logical model requirement.

### Reference floorplan recipe

The first reviewed recipe is fixed as follows. The implementation may express
these values in a host-owned typed catalog or equivalent reviewed configuration,
but it must not move them into the workflow package.

| Role | Source | Revision | File | SHA-256 |
| --- | --- | --- | --- | --- |
| base model | `ggml-org/Qwen2.5-VL-3B-Instruct-GGUF` | `5037fcf163dd95d1e41d1974465f0898ed108ca2` | `Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf` | `d02fe9b69ad8cadbbd228e387667af66612c44bed29ffc8eb1e7caf9ac486c12` |
| vision projector | `ggml-org/Qwen2.5-VL-3B-Instruct-GGUF` | `5037fcf163dd95d1e41d1974465f0898ed108ca2` | `mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf` | `980c9b2f78c04e6cff93d277ada09e768394f112d75db3b4e9dea8a69f9fb904` |
| source LoRA | `mudasir13cs/qwen25-vl-3b-floorplan-grpo` | `784b8bf4705939887122bcfba029a6fce13e9ff4` | `adapter_model.safetensors` | `089892a8815310bce15d6bf6d1fb082926f46a135b9550c6381ac192901d0132` |
| LoRA metadata | `mudasir13cs/qwen25-vl-3b-floorplan-grpo` | `784b8bf4705939887122bcfba029a6fce13e9ff4` | `adapter_config.json` | `d4378af112087c3421851cb9ebde13fee0abc0ee1f001e0499d8febe62caf729` |
| base configuration metadata | `Qwen/Qwen2.5-VL-3B-Instruct` | `66285546d2b821cf421d4f5eb2576359d3770cd3` | `config.json` | `7ed3eed5be6924cc800e8a5e53fc405c1aab1aaf36bad65c33403b36c56827f5` |

The source LoRA declares `Qwen/Qwen2.5-VL-3B-Instruct` as its base. Conversion
uses the llama.cpp converter at commit
`465e49b9cea78a68b9c244ffb48d0ee24a82873d`, produces F16 GGUF, and expects
the resulting artifact SHA-256
`ed95fb7aed5e44d075fe028fc58a5b478019f52960a5bebc1a8dd1d15fa93138`.
The implementation shall pin the converter's isolated dependency environment
as part of the reviewed recipe; an ambient Python environment is not a recipe
input.

### Native Transformers + PEFT closure

The same logical Qwen floorplan model may have a distinct native recipe with
`runner_id` `transformers-peft-v1`. It enumerates the full base checkpoint,
processor/tokenizer metadata, weight-shard index and shards, and PEFT adapter
metadata/weights in separate verified groups. It has no conversion output.

Preparation does not infer compatibility from `.safetensors` filenames. The
recipe declares the reviewed standard loader profile; a set is ready only when
every declared member validates. A native recipe that requires remote code is
not eligible for this profile. A recipe that uses standard loading but needs
custom preprocessing or nonstandard media packing may use a compatible workflow
input converter plugin; a model that also needs custom loading, generation, or
output decode requires a separately reviewed model-execution plugin.

### Reference workflow output boundary

`qwen25-vl-3b-floorplan-grpo` is trained to emit structured floorplan JSON:
walls with nested openings followed by rooms that reference those walls. DAR's
acceptance boundary for this recipe is a complete, parseable instance of that
declared JSON contract. JSON-to-SVG rendering and SVG validation are
workflow-local deterministic tooling implemented outside DAR; they consume the
model result after DAR has completed the generic sealed-artifact invocation.

## Functional Requirements

### FR-1: Resolve declared requirements, not prompt text

Before invoking a local adapter, DAR shall resolve the registered workflow's
declared model requirement and adapter against the host recipe catalog. The
model prompt, generated workflow prose, and workspace input must not influence
recipe selection.

Acceptance criteria:

- A floorplan workflow resolves its declared model and llama.cpp vision adapter
  to the floorplan recipe.
- A missing recipe yields a stable unavailable result before model loading or
  network activity.
- A same-named model with a different adapter, revision, or capability is not a
  fallback.

### FR-2: Prepare a complete pinned artifact set

The host shall provide a preparation operation for a declared logical
requirement. It shall first reuse already verified artifacts from DAR-owned
preparation storage or the standard Hugging Face cache. If required sources are
absent and preparation is authorized, it shall download only the recipe's
pinned files. It shall not download an entire snapshot when a recipe declares
specific files.

The operation returns readiness or a redacted actionable failure under the same
logical model name. It does not return a path or a newly minted identifier that
the caller must retain.

Acceptance criteria:

- A cache-complete artifact set performs no network operation.
- A partial artifact set downloads only missing recipe inputs.
- An unavailable, gated, or integrity-failing source reports a stable failure
  without leaking credentials, local paths, or raw upstream exceptions.
- A later invocation of the same declared model resolves the verified set
  without repeating preparation.

### FR-3: Execute declared deterministic transformations

When a recipe declares a transformation, DAR shall execute only that reviewed
operation with its declared inputs and output location. It shall validate input
digests before conversion and output format and digest after conversion. A
failed or interrupted transformation leaves no artifact eligible for execution.

The first floorplan recipe shall convert its pinned PEFT LoRA into a
llama.cpp-compatible GGUF using its pinned converter and base configuration
metadata. It shall use:

- the pinned Qwen2.5-VL base GGUF and matching projector as runtime inputs;
- the converted LoRA only with that declared base/model family; and
- the configured precision recorded by the recipe.

Acceptance criteria:

- Fake-only tests demonstrate that the converter receives only declared inputs
  and that failed conversion does not produce a ready set.
- A digest mismatch in a source or converted artifact rejects the set.
- A valid converted LoRA is passed to the llama.cpp adapter as its adapter/LoRA
  setting, alongside the matching base-model and projector paths.

### FR-4: Keep physical locations host-private

Adapter construction may receive resolved physical paths, but no path may enter
a workflow descriptor, model prompt, user-facing preparation result, trace, or
saved workflow metadata. The adapter receives only the exact files declared by
the selected recipe.

Acceptance criteria:

- A model adapter receives its base, projector, and LoRA paths only from a
  verified prepared artifact set.
- Model messages and user-facing output contain neither cache roots nor those
  paths.
- A caller cannot cause DAR to load an arbitrary path by putting it in a prompt
  or workflow artifact.

### FR-5: Integrate preparation into the simple workflow flow

Natural-language workflow authoring may determine the logical model requirement
from the user's explicit request. It remains declarative: it neither downloads
artifacts nor runs a converter. A host composition with preparation authority
may request the preparation operation before registration or execution. The
authoring conversation shall not ask for model filenames, converter choices,
cache locations, or a handle produced by preparation.

Workflow invocation resolves the registered logical requirement automatically.
It must not silently make a network download. A caller or host policy must
authorize the separate preparation operation. When the set is not prepared,
invocation returns a concise ready-to-prepare/unavailable result rather than a
misleading model-load error.

Acceptance criteria:

- The floorplan authoring request requires no model-location clarification.
- After preparation, the floorplan workflow can be invoked using its saved
  workflow name and sealed image input; no artifact paths or preparation ID are
  supplied by the user.
- A policy that disallows download leaves an incomplete set unavailable without
  attempting Hub access.

### FR-6: Preserve cache and supply-chain boundaries

DAR may inspect only its own preparation cache, its existing default Hugging
Face cache, and explicit caller-provided cache roots already permitted by the
local-model resolution boundary. It must not scan arbitrary directories or
delete source artifacts owned by another cache manager.

Each ready set shall retain enough host-private provenance to revalidate its
recipe, source digests, transformation inputs, and output digest before use.
Changing any of those values invalidates readiness for that recipe.

Acceptance criteria:

- Cache lookup is limited to approved roots.
- A stale or mismatched prepared set is revalidated or rejected before adapter
  construction.
- Re-preparing one recipe does not modify unrelated cached model artifacts.

## Interface Direction

The exact public API and CLI spelling are implementation-plan decisions. The
user-facing shape must be equivalent to:

```text
prepare <logical-model-requirement>
invoke <saved-workflow-name>
```

The second operation resolves the model requirement already declared by the
saved workflow. It does not require `--model-path`, `--projector-path`, or
`--lora-path`. A programmatic host API may expose these values only inside a
host-private prepared-artifact-set value used to build the adapter.

## Failure Semantics

Preparation failures shall distinguish, without leaking private details:

- no reviewed recipe for the declared model/runtime;
- preparation not authorized by the current host policy;
- source artifact unavailable or access required;
- source or output integrity failure;
- incompatible runtime/adapter; and
- deterministic conversion failure.

They must not present a raw subprocess command, source path, cache path,
credential, access token, or opaque internal receipt.

## Required Validation

Implementation must add deterministic, fake-only tests for recipe selection,
cache hit/miss behavior, download policy, per-file pinning, conversion input and
output validation, cache invalidation, and path redaction. One manually gated
acceptance run shall prepare and compose the floorplan base GGUF, projector, and
converted LoRA through llama.cpp with a sealed image, then validate the
workflow's structured JSON terminal output. This acceptance run is not a unit
test and must record only redacted artifact identities and verification
outcomes.

## Completion Criteria

This feature is complete when the floorplan workflow can name only
`qwen25-vl-3b-floorplan-grpo`, DAR can deterministically prepare and verify its
complete llama.cpp artifact set under host policy, and saved-workflow invocation
uses that set without user-provided paths, conversion commands, or opaque
handoff identifiers.
