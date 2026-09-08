# Workflow Input Converter Plugin Tasks

## Status

Planned. Complete slices in this dependency order: T1, T2, T3, T4, then T5.
Each implementation task requires its preceding RED test to fail for the
intended reason. Unit tests use fakes only: they must not download models,
execute a live converter, load a real model, or depend on a GPU.

Generated converter admission is blocked until T4.3 has passed. Trusted,
implementation-owned fixtures may exercise the private handoff before then,
but are not evidence of untrusted-code isolation.

## Identifier Rules

- `transformers-peft-single-image-v1` remains the preparation loader profile.
- `transformers-peft-v1` remains the built-in runner catalog ID.
- `transformers-generate-v1` is the exact converter-compatible runner contract.
  A manifest must use the latter; no aliases or fallback matching are allowed.

## T1 — Manifest and Immutable Workflow Binding

- [x] T1.1 [tests, RED/GREEN] Add focused descriptor and package-policy tests
  for one
  valid converter manifest and for missing, duplicate, malformed, unknown-field,
  stale-digest, and exact runner-contract-mismatch cases. Assert every invalid
  case fails before worker or model construction, and that prompt, bytes,
  filename, extension, media type, and generated text cannot select a
  converter.
- [x] T1.2 [implementation] Define the smallest immutable converter-manifest
  value and validator: converter ID, converter contract version, compatible
  runner contract ID, entrypoint, asset digest, and declared resource limits.
  Reject a live callable, runtime path, interpreter choice, undeclared asset,
  or arbitrary manifest extension.
- [x] T1.3 [implementation] Extend existing package validation and workflow
  registration to bind the converter manifest/asset digest, selected
  `transformers-generate-v1` contract, prepared-model recipe digest, and
  package digest. Reuse the current exact source and digest-validation pattern;
  do not create a plugin registry or discovery mechanism.
- [x] T1.4 [tests, GREEN] Prove a registered workflow cannot replace its
  converter and another workflow cannot reuse it without its own exact binding.
  Run focused package, registration, and host regressions.

## T2 — `transformers-generate-v1` Standard Runner

- [x] T2.1 [tests, RED/GREEN] Add fake-only runner tests for a private opaque packed
  value: exact contract acceptance, `model.generate(**inputs)`, bounded
  generation, generated-token suffix decoding, and clearing packed state after
  success, runner rejection, generation failure, timeout, and cancellation.
- [x] T2.2 [implementation] Extract from
  `workflow_host/transformers_peft_model.py` the Qwen base-model/PEFT loading
  and bounded-generation responsibilities into the first standard runner.
  Retain verified prepared-set resolution, local-only/remote-code-disabled
  loading, fixed placement behavior, and package-owned error redaction. Expose
  only the reviewed processor and contract-defined input-packing facilities to
  a converter; no paths, arbitrary files, host callbacks, environment, model
  selection, or model-loader controls.
- [x] T2.3 [tests, GREEN] Run focused runner, preparation, profile, and host
  regressions. Preserve the existing closed single-image adapter until T3 has
  migrated its profile; do not change client runners or other model recipes.

## T3 — Qwen Floorplan Converter and Opaque Ingress

- [x] T3.1 [tests, RED/GREEN] Add fake-only converter tests for one valid sealed
  Qwen image and empty, oversized, undecodable, and unsupported bytes. Prove
  image decoding and processor conversation/packing occur only in the
  converter, while DAR treats payload bytes as opaque.
- [x] T3.2 [implementation] Package one trusted immutable Qwen converter asset that
  targets exactly `transformers-generate-v1`, decodes its expected image input,
  builds the processor conversation and generation mapping, and returns only
  the private packed value.
- [x] T3.3 [implementation] Migrate the floorplan workflow ingress from the
  direct JPEG/PNG media-type switch and `bind_sealed_image` path to sealed
  bounded bytes delivered to the selected converter. Preserve generic
  byte-count and lifecycle limits; do not add DAR format detection or a media
  registry.
- [x] T3.4 [tests, GREEN] Prove payload and packed-state disposal, classified
  redacted outcomes, and no trace/API/workflow artifact exposure after converter
  rejection, runner rejection, cancellation, timeout, or worker failure. Run
  focused ingress, converter, runner, registration, and trace regressions.

## T4 — Isolated Worker Admission Gate

- [ ] T4.1 [tests, RED] Add deterministic adversarial tests for the candidate
  worker backend: caller-workspace and credential reads, inherited environment,
  network access, child-process execution, writes outside ephemeral scratch,
  symlink traversal, and timeout, output, memory, process-count, and
  scratch-space exhaustion.
- [ ] T4.2 [implementation] Implement or select the isolation backend required
  by [`local-tool-sandbox-hardening`](../local-tool-sandbox-hardening/spec.md)
  and its same-worker control protocol. Give a worker only verified read-only
  model material, reviewed converter dependencies and asset, prompt, sealed
  bytes, ephemeral scratch, and host-issued limits. Its external result is
  bounded normalized text or a classified redacted failure; `PackedModelInput`
  remains private. Do not use a same-process callback or the current permissive
  test `sandbox-exec` profile as the admission boundary.
- [ ] T4.3 [validation] Run positive and adversarial real-platform evidence
  for every supported backend platform. Enable generated converter admission
  only when the evidence satisfies every sandbox-hardening requirement;
  otherwise preserve refusal and record the backend as unavailable.

## T5 — Authoring, Acceptance, and Release

- [ ] T5.1 [tests, RED] Add Agent Engineering guidance tests that require a
  fixed converter asset for a standard runner or report the missing converter.
  Reject live callables, dependency installation, arbitrary paths, runtime
  package selection, and format-registry guidance.
- [ ] T5.2 [implementation] Update Agent Engineering guidance only to author
  the fixed package form and declare the compatible runner contract/resource
  needs. It cannot grant capabilities or bypass package validation and T4
  admission. Regenerate and validate the packaged plugin payload.
- [ ] T5.3 [validation] Run all focused suites, then `poetry run pytest -q`,
  `poetry run ruff check src tests`, and `git diff --check`.
- [ ] T5.4 [manual gate] With explicit authorization and only after T4.3,
  execute the durable prepared Qwen closure with a sealed site-plan image.
  Verify a bounded normalized response reaches workflow-local JSON-to-SVG
  tooling. Record only redacted identities, contract versions, and outcomes;
  DAR must neither parse that JSON nor validate SVG.
- [ ] T5.5 [release] Update validation evidence and feature status, then
  package/release only after every prior task is complete. Do not mark the
  feature production-ready while generated converter admission is disabled.
