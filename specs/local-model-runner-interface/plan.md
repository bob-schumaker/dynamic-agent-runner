# Local Model Runner Interface Plan

## Goal

Deliver one DAR-owned closed `transformers-peft-single-image-v1` profile for
the Qwen floorplan recipe. Keep the existing client-runner catalog only for
nonstandard profiles; do not build the future plugin interface or a resource
scheduler in this slice. T1–T4.2 are implemented or recorded; this plan's
generic MPS placement is implemented through T5; this plan records its
completed delivery evidence.

1. Add the closed loader-profile value to preparation recipes and canonical
   digests. Validate exact groups, roles, no unknown configuration, and the
   reserved built-in runner ID before a framework import.
2. Add the optional `transformers-peft` extra with bounded versions:
   Transformers `>=5.0.0,<6.0.0`, PEFT `>=0.19.1,<0.20.0` (the pinned
   adapter declares PEFT 0.19.1), Torch
   `>=2.9.0,<3.0.0`, Pillow `>=11.0.0,<12.0.0`, and a Torchvision
   release compatible with the locked Torch release.
3. Implement one framework-named runner module around the exact standard APIs
   in the profile. Use only in-memory sealed images, deterministic generation,
   generated-token suffix decoding, package-owned errors, and the fixed
   host-detected placement rule: when MPS is available, load the base without
   an Accelerate map, move it to MPS, then attach PEFT and target wrapped-model
   device inputs; otherwise retain bounded automatic placement. If the MPS move
   or adapter attachment fails, clear sealed input, return a package-owned
   redacted error, and do not retry through CPU/disk offload.
4. Reserve `transformers-peft-v1` in the host catalog, migrate the Qwen
   profile/recipe to that ID, and reject client collisions. Preserve client
   runners for other IDs and the existing llama.cpp floorplan path unchanged.
5. Validate fake-only behavior first. The authorized manual run installed the
   optional extra and prepared the pinned closure, but exposed that automatic
   placement disk-offloads on an MPS-capable host before PEFT can apply the
   adapter. T5 must first prove both observable placement branches, their
   exact loader/adapter order, input-device placement, and failure cleanup.
   It must then rerun the sealed manual test and pass the returned text to the
   workflow-local floorplan JSON parser. DAR does not parse or validate JSON.

## T5 Execution Sequence

1. In `tests/test_transformers_peft_model.py`, write failing fake-only tests
   for both closed branches. The MPS branch must omit `device_map`, call
   `base.to("mps")`, then call `PeftModel.from_pretrained`; it retains
   local-only, remote-code-disabled, and automatic-dtype arguments. The
   unavailable-MPS branch retains `device_map="auto"` with the same offline
   invariants. No authored or client placement setting is introduced.
2. Write failing fake-only generation and failure-path tests. MPS generation
   inputs must target the wrapped model's device. A failed MPS move and a
   failed adapter attachment must each clear sealed input, surface only DAR's
   package-owned redacted error—without vendor exception text, prompt text, or
   artifact/image paths—and make no CPU/disk-offload retry.
3. Change only
   `src/dynamic_agent_runner/workflow_host/transformers_peft_model.py`'s
   built-in loader seam to select the fixed host-detected branch. Do not change
   the client-runner catalog, add a scheduler/allocator/hardware scan, or add a
   model-specific branch.
4. Run the focused runner, preparation, and host regressions, then `poetry run
   pytest -q`, `poetry run ruff check src tests`, and `git diff --check`.
5. Re-run the already authorized prepared-closure test with one sealed image.
   Record only redacted provenance and a nonempty response accepted by the
   workflow-local floorplan JSON parser. SVG rendering and validation remain
   workflow-local.

## Risks and Limits

`torch_dtype="auto"` remains fixed. The runner uses the observable base-load,
MPS-move, then PEFT-attach sequence only when the host reports MPS available;
otherwise `device_map="auto"` remains the bounded fallback. Fake tests prove
that sequence and the no-retry error boundary, not an assertion about
Accelerate internals; the authorized manual gate proves framework behavior.
This is not a claim of cross-platform performance, MPS capacity, or model
residency/resource scheduling. A model that needs custom code, another
auto-model class, multiple images/video, a nonstandard processor flow, or
bespoke decoding is rejected and belongs to a client runner or later profile.
