# Local Model Runner Interface Specification

## Metadata

- Feature slug: `local-model-runner-interface`
- Mode: guided
- Status: implemented through the T5 manual gate; canonical generation-budget
  migration remains pending
- Owner: dynamic-agent-runner local-model and workflow-host boundaries
- Plan: `plan.md`
- Tasks: `tasks.md`
- Validation: `validation.md`
- Related: `specs/local-model-preparation/spec.md`
- Related: `specs/workflow-model-materials/spec.md`
- Related: `specs/workflow-capability-requirements/spec.md`
- Future extension: `specs/workflow-input-converter-plugin/spec.md`

## Objective

Make a DAR-prepared local model executable through its reviewed runtime without
exposing runtime paths or framework choices to a workflow user. DAR owns the
generic built-in `transformers-peft-v1` and `llama-cpp-v1` runners. A
nonstandard runner is available only as a receiver-installed, reviewed plugin;
it is never executable code supplied by a workflow package.

`qwen25-vl-3b-floorplan-grpo` is the first native material declaration. It uses
the generic runner; DAR contains no floorplan prompt, output schema, SVG rule, or
model-specific generation branch.

## Boundaries

DAR owns material-lock/profile resolution, the generic runner registry,
verified artifact materialization, optional runtime dependencies, local model
loading, sealed text/image translation, generation limits, cleanup, tracing,
and normalized model responses. The sealed workflow model-material declaration
owns immutable base/adapter closures and the closed loader-profile ID. The
receiving host owns placement, cache, network, endpoint, and resource policy.
The workflow owns floorplan prompting, JSON/SVG contracts, and domain tooling.

New packages declare the exact standard runner capability required by their
material lock under `workflow-capability-requirements`. This specification
defines the observable runner semantics behind that capability. The runner and
profile IDs below constrain material compatibility; they do not select a class,
native library, device, or provider implementation.

The first slice deliberately does not add a plugin ABI, a model scheduler, a
GPU allocator, user-configurable placement, remote code support, or support for
arbitrary Transformer architectures. It does include one fixed, host-detected
MPS placement rule so a supported profile can avoid Accelerate disk offload on
an MPS-capable host. Those broader capabilities belong to later work only when
a concrete model requires them.

## Closed `transformers-peft-v1` Profile

The only built-in native profile in this slice is
`transformers-peft-single-image-v1`. A material declaration may select it only
when all of the following are true:

| Concern | Required v1 behavior |
| --- | --- |
| Runner ID | `transformers-peft-v1` |
| Base group | Group `base` contains the complete pinned base checkpoint, processor/tokenizer metadata, shard index, and every indexed shard. |
| Adapter group | Group `adapter` contains `adapter_config.json` and adapter weights pinned to the declared base. |
| Model API | `AutoModelForImageTextToText.from_pretrained` with `local_files_only=True`, `trust_remote_code=False`, and `torch_dtype="auto"`. On an available MPS backend, DAR loads the base without an Accelerate device map, moves that base to MPS, then attaches PEFT; otherwise it uses `device_map="auto"` before attaching PEFT. Generation inputs target the wrapped model's device in either branch. |
| Processor API | `AutoProcessor.from_pretrained` with `local_files_only=True` and `trust_remote_code=False`. |
| Adapter API | `PeftModel.from_pretrained` against the verified adapter group, `is_trainable=False`, and local-only loading. |
| Image runtime | The optional runtime includes a Torchvision release compatible with the locked Torch release; Qwen's processor requires it even for one image. |
| Input | One nonempty user text prompt and exactly one sealed PNG or JPEG image no larger than 8 MiB or 32 megapixels. |
| Generation | Disabled sampling. Current compatibility validation accepts `max_new_tokens` from 1 through 1,000,000 and at most 32 continuations. Canonical per-fragment, aggregate output, context, deadline, and memory limits are owned by `specs/model-generation-resource-budgets/spec.md`. |
| Decode | Remove the prompt-token prefix, batch-decode the generated suffix with special tokens skipped, and reject an empty result. |

The standard multimodal chat-template flow receives only an in-memory decoded
image object and user text. It never receives a file path, URL, base64 source,
or arbitrary additional message/media item. The generated response is returned
through DAR's existing `ModelResponse` contract.

### Future converter-backed execution

The closed profile above remains the implemented compatibility baseline. A
future `transformers-generate-v1` execution contract extracts byte decoding and
input packing into a workflow-sealed input converter plugin. Its standard
Transformers/PEFT runner then receives only private packed model inputs. That
future path is governed by `specs/workflow-input-converter-plugin/spec.md`; it
does not broaden the current built-in profile or change its recorded evidence.

The material-lock digest includes the runner ID, loader-profile ID, all
group/role members, immutable revisions and hashes, and transformation (if
any). Unknown
loader-profile fields, missing roles, duplicate roles, a base/adapter mismatch,
or a prepared-set material-lock/digest mismatch are incompatible before any framework
import or loader call.

## Requirements

### FR-1: Exact registry selection

After exact capability resolution, DAR selects `transformers-peft-v1` or
`llama-cpp-v1` only for a sealed ModelExecutionBinding with the matching closed
profile. Built-in IDs are reserved: a package or external plugin cannot
register or shadow them. The registry must not infer a runner from extensions,
imports, filenames, adapter IDs, or fallback ordering.

### FR-2: Offline, verified loading

The runner resolves only the prepared set's `base` and `adapter` roots after
their identity and group membership validate. Every framework load path is
local-only and remote code is disabled. A framework import, Hub resolution, or
client-runner fallback must not occur for a rejected profile or set.

### FR-3: Sealed input and bounded execution

The runner accepts exactly one verified image and one text prompt. It validates
media type, byte count, decodability, and pixel count before preprocessing;
image bytes and decoded state are cleared after success, loader failure,
generation failure, or cancellation. Errors and traces use package-owned
classifications and never include sealed bytes, image paths, prompt text,
artifact paths, or vendor exception text.

### FR-4: Receiver-installed runner extension

A nonstandard runner is installed and reviewed by the receiving DAR
installation before package admission. It gets the same sealed binding, lazy
verified-set resolver, and host policy as a built-in runner; it does not
receive an authored path or authority to download. It cannot override or shadow
a DAR-owned runner ID, and a workflow package cannot contain its factory or
native dependency.

### FR-5: Generic MPS placement

The built-in runner detects whether MPS is available without an authored or
client-supplied placement setting. When it is available, the runner must use a
direct MPS placement path: load the base without an Accelerate `device_map`,
move the base to MPS, and only then apply the verified adapter. It must not
introduce CPU/disk offload before PEFT applies that adapter. Generation inputs
target the resulting wrapped model's device. When MPS is unavailable, the
runner retains its bounded automatic placement path. This is a fixed
compatibility rule for the closed profile, not a scheduler, allocator, hardware
inventory, or user-selectable device policy. A failed MPS move or adapter
attachment is a normal package-owned failure: DAR clears sealed input and does
not retry through CPU/disk offload.

## Acceptance Criteria

- Fake-only tests prove the exact base/adapter closure, loader arguments,
  network-free rejection, generated-token slicing, and response normalization.
- Fake-only tests prove no loader or runner runs for an invalid profile, wrong
  closure, duplicate/reserved ID, invalid media, or exhausted limit.
- Fake-only tests prove sealed image cleanup on every success and failure path.
- Fake-only tests prove that MPS availability selects the direct MPS path and
  that an unavailable MPS backend retains the bounded automatic path, without
  changing the offline or remote-code-disabled loader invariants. They prove
  observable loader/placement/adapter order; the authorized real-model gate
  remains the evidence that the framework avoids offloaded dispatch state.
- Fake-only tests prove an MPS move or adapter-attachment failure clears sealed
  input, yields a package-owned redacted error, and never retries through
  CPU/disk offload.
- The Qwen material declaration/profile use `transformers-peft-v1`, its digest
  changes when
  its loader profile or any closure member changes, and no floorplan-specific
  branch exists in the runner.
- With explicit authorization, one pinned Qwen closure processes one sealed
  floorplan image and returns nonempty text that the workflow-local floorplan
  JSON parser accepts after the MPS placement slice. SVG rendering and
  validation remain workflow-local acceptance, not runner acceptance.
