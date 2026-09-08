# Workflow Input Converter Plugin Implementation Plan

## Status

S1 through S4 are delivered. DAR loads a sealed Python converter package
through the standard runner interface. OS-level isolation is future hardening
owned by `../local-tool-sandbox-hardening/spec.md`, not a converter-package
admission gate. S5 remains in [`tasks.md`](tasks.md).

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
| Package binding and digest checks | package and registration control-plane modules | Add a package-contained converter manifest and bind its digest to the exact workflow, runner contract, and model recipe. |
| OS-level executable isolation | `local-tool-sandbox-hardening` | Future hardening for malicious package code; it is separate from sealed Python package loading. |

## Delivery Rules

- Every slice begins with focused fake-only RED tests, then the smallest GREEN
  implementation, then its focused regression suite.
- `PackedModelInput` never crosses the converter/runner boundary. It is neither
  serialized, traced, stored, nor returned from a DAR API.
- Converter selection is exact: workflow binding, asset digest, converter
  contract, and runner contract must all match before a package is loaded.
- The first slice reuses the installed Transformers and PEFT dependencies. It
  adds no media registry, tensor format, dependency installer, converter
  marketplace, or generic cross-worker RPC.
- Full OS-level isolation remains deferred; this delivery path does not claim
  to constrain a sealed Python package beyond its standard interface.

## S1 — Closed contract, manifest, and registration binding

1. Write RED tests for a valid one-converter package; missing, duplicate,
   malformed, and digest-mismatched converter assets; and exact runner-contract
   mismatch. Assert that all failures occur before model-worker construction.
2. Define the minimal immutable converter manifest: converter ID, converter
   contract version, compatible runner contract ID, entrypoint, asset digest,
   and declared resource limits. Reject extra selection mechanisms such as a
   payload media type, filename, prompt directive, runtime path, or live
   callable.
3. Bind the validated manifest digest, selected runner contract, model recipe
   digest, and package digest in the existing workflow registration path.
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

The panel agrees that the converter is a workflow-scoped Python package, not a
DAR media capability or a general model-execution plugin. The necessary
invariants are exact package/runner binding, private packed state, and
host-owned limits. Full OS-level isolation is a separate hardening decision;
it is not an S4 admission gate for the standard package interface.

### Ponytail Review

Keep one converter contract and one Qwen converter first. Reuse the existing
prepared-set, adapter, package-validation, and worker seams. Do not build a
universal tensor serialization, converter marketplace, dependency resolver,
format detector, promotion workflow, or separate model-runner interface in
this feature. Add those only when a second concrete runner or converter proves
the first closed contract insufficient.

### Readiness Conclusion

The design is ready for staged implementation. S1, S2, and S3 are bounded
against existing code; S4 completes exact sealed-package loading before
authoring and acceptance. OS-level isolation remains future work.

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
