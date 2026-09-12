# Workflow Input Converter Plugin Implementation Plan

## Status

S1 through S4 and the S5 JSON boundary, manually authorized floorplan gate, and
regression evidence are delivered. T5.6 has a verified local package build, but
an explicit unreleased version and publish target remain in
[`tasks.md`](tasks.md). DAR loads a sealed Python converter package through the
standard runner interface. OS-level isolation is future hardening owned by
`../local-tool-sandbox-hardening/spec.md`, not a converter-package admission
gate. Deadline-bounded worker co-location and generic runner-capability
migration are owned by `../model-generation-resource-budgets/`; they preserve
this plan's direct private `PackedModelInput` handoff. The Apple Metal addendum
implementation, fake-test slice, and authorized warm benchmark are delivered.

## Execution Order

Implement the closed binding, standard runner, and one Qwen converter first
(S1, S2, S3). Complete sealed package entry-point loading (S4), then complete
authoring and acceptance (S5).

## Goal

Deliver one workflow-sealed converter for the existing Qwen
`transformers-peft-single-image-v1` floorplan path, while establishing the
small private boundary that later converters need. The workflow user continues
to supply only a prompt and one sealed byte payload. DAR does not inspect its
format or the resulting framework objects.

## Identifier Boundaries

- `transformers-peft-single-image-v1` is the existing closed preparation loader
  profile.
- `transformers-peft-v1` is the existing built-in runner catalog ID.
- `transformers-generate-v1` is the new converter-compatible runner execution
  contract. Converter manifests match this ID exactly; it is not an alias for
  either existing identifier.

## Current-State Anchors

| Concern | Current owner | Planned change |
| --- | --- | --- |
| Sealed JPEG/PNG decode and generation | `workflow_host/transformers_peft_model.py` | Move image-specific decode and processor packing behind the first converter; retain model loading and bounded generation in the runner. |
| Prepared base and PEFT artifacts | `local_model_preparation.py` | Reuse verified, host-private prepared-set resolution. Do not add paths to a workflow invocation. |
| Sealed workspace ingress | `workflow_host/runner.py` | Generalize the private handoff from one sealed image to opaque bounded bytes; remove DAR media-type routing from this execution path. |
| Package binding and digest checks | package and registration control-plane modules | Add a package-contained converter manifest and bind its digest to the exact workflow, runner contract, and sealed model-material lock. |
| OS-level executable isolation | `local-tool-sandbox-hardening` | Future hardening for malicious package code; it is separate from sealed Python package loading. |

## Delivery Rules

- Every slice begins with focused fake-only RED tests, then the smallest GREEN
  implementation, then its focused regression suite.
- `PackedModelInput` never crosses the converter/runner boundary. It is neither
  serialized, traced, stored, nor returned from a DAR API.
- For the bounded generation-worker mode, the converter and compatible runner
  co-locate in that worker. The same no-serialization rule applies; the
  migration is owned by `model-generation-resource-budgets`, not a parallel
  converter execution route.
- Converter selection is exact: workflow binding, asset digest, converter
  contract, and runner contract must all match before a package is loaded.
- The first slice reuses the installed Transformers and PEFT dependencies. It
  adds no media registry, tensor format, dependency installer, converter
  marketplace, or generic cross-worker RPC.
- Full OS-level isolation remains deferred; this delivery path does not claim
  to constrain a sealed Python package beyond its standard interface.

## Apple Metal Execution Addendum

The existing `transformers-peft-v1` runner already selects PyTorch MPS when it
is available on macOS. The optimization slice remains inside that runner:
attach the PEFT adapter, place the complete inference model on MPS, set
evaluation mode, and use an inference-only generation context. Keep the
existing non-MPS `device_map="auto"` path unchanged. MPS unavailability or
failure must not select a remote model, change the prepared artifact set, or
change the terminal output contract.

Extend only the existing redacted model-generation metadata with MPS selection
and measured generation outcome for both direct and continuation responses;
never expose model tensors, sealed payloads, prompts, or completion fragments.
The outcome is limited to generated-token count when available and declared
chunk exhaustion, never timing or content. Fake-only tests must prove MPS
selection, adapter-before-placement ordering, evaluation mode, inference-only
generation, packed-input disposal, JSON/continuation preservation, direct and
continuation metadata redaction, and unchanged non-MPS loading behavior.

Do not add a workflow-visible device switch, MPS CPU fallback, MLX backend,
model conversion, quantized artifact, or `torch.compile` default. Retain the
existing dtype by default. Any optional Mac-only dtype or compilation experiment
requires a fixed-prepared-model, fixed-sealed-image, fixed-generation-limit warm
baseline and candidate. Retain only device selection, wall-clock duration,
generated-token count, and tokens per second; accept the experiment only with
identical terminal-contract behavior and a measured improvement.

## S6 — Apple Metal execution and benchmark

1. Add fake-only RED coverage for MPS availability, the unchanged non-MPS
   loader path, adapter-before-placement ordering, evaluation mode,
   inference-only generation, and redacted outcome metadata on direct and
   continuation responses. Do not load a model or require a GPU in these tests.
2. Make the MPS path Mac-only within the existing runner. It must attach the
   verified adapter before moving the completed model to MPS, retain the
   existing dtype, set evaluation mode, and generate under inference mode. It
   must neither add a workflow-visible execution choice nor introduce fallback,
   MLX, conversion, quantization, or compilation behavior.
3. With explicit authorization, benchmark a fixed prepared model, fixed sealed
   image, and fixed generation limit. The baseline uses the prior base-model
   MPS placement before PEFT attachment; the candidate attaches PEFT before
   placing the completed model on MPS. The benchmark limit must be independently
   fixed before either measurement and must produce the terminal contract; do
   not use the production `4096`-token ceiling after its five-minute warm-pass
   non-completion. Retain only device, duration, token count, and tokens per
   second. Adopt a dtype or compilation candidate only after the identical
   terminal contract and improved warm-run metric are both demonstrated. The
   fixed `1024`-token, zero-continuation floorplan benchmark reached the
   terminal contract. The candidate recorded 6.362699 tokens/sec for 994
   tokens, compared with 5.941363 tokens/sec for the prior loader order (a 7.1%
   improvement). No dtype or compilation candidate was introduced.

Exit: non-Mac and unavailable-MPS behavior is unchanged; the MPS path preserves
the sealed workflow contract and has a redacted, reproducible benchmark record.

## S1 — Closed contract, manifest, and registration binding

1. Write RED tests for a valid one-converter package; missing, duplicate,
   malformed, and digest-mismatched converter assets; and exact runner-contract
   mismatch. Assert that all failures occur before model-worker construction.
2. Define the minimal immutable converter manifest: converter ID, converter
   contract version, compatible runner contract ID, entrypoint, asset digest,
   and declared resource limits. Reject extra selection mechanisms such as a
   payload media type, filename, prompt directive, runtime path, or live
   callable.
3. Bind the validated manifest digest, selected runner contract,
   model-material-lock digest, and package digest in the existing workflow
   registration path.
   Preserve the existing package-source and no-fallback validation pattern.
4. Add package-only tests that prove a converter cannot be replaced after a
   workflow is registered or reused by another workflow without registration.

Exit: DAR can recognize exactly one immutable converter asset and reject every
ambiguous or stale binding without loading a model or parsing payload bytes.

## S2 — Standard `transformers-generate-v1` runner seam

1. Write RED fake-only tests for a runner that receives an opaque packed value,
   invokes `model.generate(**inputs)`, performs bounded generation and suffix
   decode, then clears the packed value on success or failure.
2. Extract the narrow loading and generation responsibilities from
   `TransformersPeftSingleImageAdapter` into the first standard runner
   contract. It continues to load only the verified base model and PEFT adapter
   from the prepared set, with the existing fixed placement and redaction
   behavior.
3. Give the converter only the reviewed processor and contract-defined
   input-packing facilities. It receives no model paths, arbitrary filesystem
   object, host callback, ambient environment, or model-selection authority.
4. Preserve focused regressions for the old closed adapter until the workflow
   profile is migrated. No other client runner or model profile changes in this
   slice.

Exit: one standard runner consumes a private processor-produced input mapping,
without DAR knowing whether the original sealed bytes were an image or another
binary format.

## S3 — Qwen floorplan converter and ingress migration

1. Write RED tests for the Qwen converter with one valid sealed image and for
   empty, oversized, undecodable, and unsupported image bytes. The converter,
   not DAR, performs decoding and model-specific processor packing.
2. Package one trusted immutable Qwen converter asset targeting
   `transformers-generate-v1`. It decodes the selected Qwen image input,
   constructs the processor conversation and generation inputs, and returns the
   private packed mapping.
3. Change workflow ingress so the host passes opaque bounded bytes into the
   selected converter. Remove the direct JPEG/PNG media-type switch and
   `bind_sealed_image` dependency from the migrated path.
4. Add fake-only lifecycle tests proving the payload and packed value are
   cleared after converter rejection, runner rejection, cancellation, timeout,
   or worker failure; traces contain only declared identities and classified
   outcomes.

Exit: the floorplan workflow invokes the standard runner through its sealed
converter, and DAR's invocation boundary is prompt plus bytes.

## S4 — Sealed Python converter package loading

1. Write RED fake-only tests for the exact manifest-bound Python entry point,
   contract attributes, restricted context, and package-load failure. Prove
   there is no module, entrypoint, or callable fallback.
2. Load that entry point through the standard converter interface and hand its
   private packed result directly to the compatible runner. Keep payload and
   packed-state cleanup on every terminal path.
3. Run focused package, runner, ingress, registration, and trace regressions.

Exit: a registered converter package is loaded only by its immutable manifest
binding and runs through the standard interface without exposing packed input.

## S5 — Authoring, acceptance, and release gate

1. Update Agent Engineering guidance only after S1–S4 work: author a converter
   asset in the fixed package form when the selected standard runner needs one,
   or report the missing implementation. It must not emit live callables,
   runtime dependency installs, paths, or a media taxonomy for DAR.
2. Run focused contract, worker, runner, ingress, registration, and authoring
   tests; then run `poetry run pytest -q`, `poetry run ruff check src tests`,
   and `git diff --check`.
3. Establish a generic JSON syntax boundary before the manual floorplan gate.
   The exact syntax-only declaration is `response_format: {type: json_object}`.
   A compatible runner advertises `json_mode: true` and constrains generation;
   an incompatible runner fails before consuming sealed input. Any bounded,
   deterministic JSON repair is workflow-owned, preserves raw and repaired
   text, digests, and a repair report as user-only diagnostics, and rejects
   truncation or invented structure. A package-declared private terminal
   processor edge carries admitted JSON directly to any workflow-local
   renderer; the boolean terminal validator cannot carry bytes or replace that
   edge. DAR owns neither floorplan JSON semantics nor repair as a default
   execution behavior.
4. Run a manually authorized floorplan acceptance with the durable prepared
   Qwen closure and sealed site-plan image. Verify strict JSON admission before
   sending the result to workflow-local JSON-to-SVG tooling; DAR neither parses
   floorplan JSON semantics nor validates SVG.
5. Record only redacted identities, contract versions, and outcomes in release
   evidence. Keep Docker and other full-isolation work in its future hardening
   specification.

Exit: the floorplan example executes from prompt plus sealed bytes with no
model path, converter choice, media-type choice, or packed input exposed to the
workflow user.

## Readiness Review

### Council Verdict

Panel: architecture triad — Aristotle (boundary classification), Ada (contract
invariants), and Feynman (minimal observable execution). Execution mode:
sequential fallback with reduced independence; no parallel reviewers were used.

The panel confirms that the converter remains a workflow-scoped Python package,
not a DAR media capability or general model-execution plugin. Its necessary
invariants are exact package/runner binding, private packed state, and
host-owned limits. Full OS-level isolation remains separate future hardening,
not an admission gate. The panel found the prior staged-implementation
conclusion obsolete: task and validation records conflicted after the successful
manual floorplan run, and the full suite initially exposed one stale prompt
assertion. The assertion now matches the declared contract and the full suite
passes. The current plan audit also found the two completed JSON task parents
unchecked and the Metal metadata requirement absent from its task wording; both
are now reconciled. MPS execution implementation is bounded to the existing
runner; the remaining review item is the authorized benchmark protocol.

### Ponytail Review

Keep one converter contract and one Qwen converter. Reuse the existing
prepared-set, adapter, package-validation, worker, and redacted-metadata seams.
Do not build a universal tensor serialization, converter marketplace, dependency
resolver, format detector, promotion workflow, separate model-runner interface,
or second Metal backend. Keep the MPS work limited to loader placement,
inference mode, redacted response metadata, and its fixed-input benchmark.

### Readiness Conclusion

The feature has passed T5.6 local package preparation but is not released. The
sealed converter boundary, strict JSON admission, terminal processor chain,
manual floorplan gate, regression evidence, and package integrity checks are
complete. Publication requires an explicit unreleased version and publish
target; the current `0.1.17` version is behind existing `0.1.31` repository
tags. The Apple Metal addendum is complete: its MPS placement-order benchmark
preserved the terminal contract and improved warm generation by 7.1%, without
introducing dtype or compilation changes.

## Deferred Decisions

- Choose the first portable OS-level isolation transport in
  `local-tool-sandbox-hardening`; do not assume a platform sandbox is
  sufficient because it starts a process.
- Specify converter dependency packaging only when the first Qwen converter
  cannot run from the existing standard runtime.
- Define an explicit host review/promotion workflow only when an instance
  converter needs reuse.
- Consider an advisory caller content label only after the core path works; it
  must never drive DAR routing or prove payload format.
