# Workflow Input Converter Plugin Implementation Plan

## Status

Planned. The contract and delivery order are ready for implementation. DAR may
admit only trusted implementation-owned fixtures until the isolation gate in
S4 has passed; it is not production-ready for generated converter assets.
The executable checklist is [`tasks.md`](tasks.md).

## Execution Order

Implement the closed binding, standard runner, and one trusted Qwen converter
first (S1, S2, S3). This proves the floorplan path without admitting generated
code. Complete the isolation gate (S4) before authoring or registering a
generated converter, then complete S5.

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
| Executable-asset confinement | `local-tool-sandbox-hardening` | Reuse its approved backend. Do not substitute a same-process Python callback or the current test-only `sandbox-exec` profile. |

## Delivery Rules

- Every slice begins with focused fake-only RED tests, then the smallest GREEN
  implementation, then its focused regression suite.
- `PackedModelInput` never crosses the isolated worker boundary. It is neither
  serialized, traced, stored, nor returned from a DAR API.
- Converter selection is exact: workflow binding, asset digest, converter
  contract, and runner contract must all match before a worker starts.
- The first slice reuses the installed Transformers and PEFT dependencies. It
  adds no media registry, tensor format, dependency installer, converter
  marketplace, or generic cross-worker RPC.
- Generated or authoring-produced converter code remains refused outside the
  approved isolation backend. Trusted test fixtures do not establish that
  approval.

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

## S4 — Isolated model-worker admission gate

1. Write RED adversarial tests against the selected candidate backend for host
   file reads, inherited credentials and environment, network access, process
   spawning, writes beyond ephemeral scratch, symlink traversal, timeouts, and
   output/resource exhaustion.
2. Implement or select the backend required by
   [`local-tool-sandbox-hardening`](../local-tool-sandbox-hardening/spec.md)
   and its same-worker control protocol. Its worker input is limited to
   verified read-only model material, converter asset and reviewed dependencies,
   prompt, sealed bytes, and host-issued limits. The only external result is
   normalized text or a classified redacted failure; packed input remains in
   worker memory.
3. Record real-platform positive and adversarial evidence. Until every required
   enforcement property holds, leave generated converter admission disabled and
   run only implementation-owned test fixtures.

Exit: DAR distinguishes trusted fixtures from untrusted converter assets and
refuses the latter unless the backend has demonstrated the required boundary.

## S5 — Authoring, acceptance, and release gate

1. Update Agent Engineering guidance only after S1–S4 work: author a converter
   asset in the fixed package form when the selected standard runner needs one,
   or report the missing implementation. It must not emit live callables,
   runtime dependency installs, paths, or a media taxonomy for DAR.
2. Run focused contract, worker, runner, ingress, registration, and authoring
   tests; then run `poetry run pytest -q`, `poetry run ruff check src tests`,
   and `git diff --check`.
3. Run a manually authorized floorplan acceptance with the durable prepared
   Qwen closure and sealed site-plan image. Verify a bounded normalized model
   response reaches the workflow-local JSON-to-SVG tooling; DAR neither parses
   that JSON nor validates SVG.
4. For a generated converter, require the S4 real-platform evidence before
   registration. Record only redacted identities, contract versions, and
   outcomes in release evidence.

Exit: the floorplan example executes from prompt plus sealed bytes with no
model path, converter choice, media-type choice, or packed input exposed to the
workflow user.

## Readiness Review

### Council Verdict

Panel: architecture triad — Aristotle (boundary classification), Ada (contract
invariants), and Feynman (minimal observable execution). Execution mode:
sequential fallback with reduced independence; no parallel reviewers were used.

The panel agrees that the converter is a workflow-scoped executable asset, not
a DAR media capability or a general model-execution plugin. The necessary
invariants are exact package/runner binding, same-worker-only packed state, and
host-owned limits. It rejects declaring the feature production-ready from the
existing opaque Python interface or test-only sandbox. The remaining decision
is not whether to add a format registry; it is selection and evidence for a
real isolated-worker backend. This plan makes that an explicit S4 admission
gate.

### Ponytail Review

Keep one converter contract and one Qwen converter first. Reuse the existing
prepared-set, adapter, package-validation, and worker seams. Do not build a
universal tensor serialization, converter marketplace, dependency resolver,
format detector, promotion workflow, or separate model-runner interface in
this feature. Add those only when a second concrete runner or converter proves
the first closed contract insufficient.

### Readiness Conclusion

The design is ready for staged implementation. S1, S2, and S3 are bounded
against existing code; S4 is a hard prerequisite for admitting generated
assets. The overall feature remains non-production until S4's enforcement
evidence passes.

## Deferred Decisions

- Choose the first portable isolated-worker transport through S4 evidence; do
  not assume a platform sandbox is sufficient because it starts a process.
- Specify reviewed converter dependency packaging only when the first Qwen
  converter cannot run from the existing runner environment.
- Define an explicit host review/promotion workflow only when an instance
  converter needs reuse.
- Consider an advisory caller content label only after the core path works; it
  must never drive DAR routing or prove payload format.
