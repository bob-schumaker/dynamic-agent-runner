# Workflow Input Converter Plugin Tasks

## Status

T1 through T4 and T5.1--T5.3 are complete. T5.4 must establish a generic,
strict JSON output boundary before the floorplan acceptance can resume. T5.5
remains blocked by the documented floorplan model/inference result; T5.6 cannot
start before it.
Each implementation task requires its preceding RED test to fail for the
intended reason. Unit tests use fakes only: they must not download models,
execute a live converter, load a real model, or depend on a GPU.

The current delivery path is a sealed Python converter package loaded through
the standard runner interface. Docker and OS-level isolation are deferred to
`../local-tool-sandbox-hardening/spec.md` and do not gate package admission.

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

## T4 — Sealed Python Converter Package Loading

- [x] T4.1 [tests, RED/GREEN] Add fake-only tests for manifest-bound package entry
  point loading: exact asset and entrypoint, contract attributes, restricted
  runner context, package-load failure, and no fallback module or callable.
- [x] T4.2 [implementation] Load and invoke the manifest-bound Python package
  entry point through the standard converter interface. Pass only prompt,
  sealed bytes, and `RestrictedRunnerInputContext`; preserve direct private
  `PackedModelInput` handoff to `transformers-generate-v1`.
- [x] T4.3 [tests, GREEN] Prove package, payload, and packed-state cleanup plus
  classified redacted outcomes on load failure, converter rejection, runner
  rejection, timeout, and cancellation. Run focused package, runner, ingress,
  registration, and trace regressions.

## T5 — Authoring, Acceptance, and Release

- [x] T5.1 [tests, RED/GREEN] Add Agent Engineering guidance tests that
  require a fixed converter asset for a standard runner or report the missing
  converter.
  Reject live callables, dependency installation, arbitrary paths, runtime
  package selection, and format-registry guidance.
- [x] T5.2 [implementation] Update Agent Engineering guidance only to author
  the fixed package form and declare the compatible runner contract/resource
  needs. It cannot bypass package validation or choose runtime configuration.
  Regenerate and validate the packaged plugin payload.
- [x] T5.3 [validation] Run all focused suites, then `poetry run pytest -q`,
  `poetry run ruff check src tests`, and `git diff --check`.
- [ ] T5.4 [JSON output boundary] Establish a generic syntax-only JSON path
  before floorplan-specific rendering. It may constrain decoding through the
  already-rendered `response_format` contract when the selected runner supports
  it, but it must fail closed when that runner cannot honor the contract. DAR
  must not acquire a floorplan schema, inspect floorplan fields, or repair
  semantic content.
  - [x] T5.4.1 [design] Define the exact declared JSON constraint and its
    supported-runner capability check. Define the workflow-owned bounded repair
    fallback separately: it may make only deterministic syntax repairs, must
    preserve the original completion and an auditable repair report, and must
    reject truncated or structurally invented output. Do not make repair a DAR
    default or a substitute for a runner that cannot honor a required JSON
    constraint.
  - [ ] T5.4.2 [tests, RED] Add fake-only standard-runner tests proving an
    exact JSON constraint reaches a capable backend, is rejected before
    generation by an incapable backend, and leaves unstructured generation
    unchanged. Prove no prompt text, sealed payload, raw completion, or repair
    artifact is exposed in DAR traces or API results.
  - [ ] T5.4.3 [implementation] Implement only the generic runner seam and
    capability binding required by T5.4.2. Reuse `response_format`; do not add
    a floorplan branch, a general schema language, or a model-specific prompt
    rewrite.
  - [ ] T5.4.4 [tests, RED/GREEN] Add workflow-owned post-processing tests for
    strict JSON validation and the declared bounded repair policy. Retain the
    original and repaired completion as user-only diagnostic artifacts with
    digests and a repair report; accept only strict JSON after processing. The
    processor must reject incomplete or semantically ambiguous output rather
    than invent structure.
  - [ ] T5.4.5 [validation] Run focused runner and workflow-local processor
    regressions, then `poetry run pytest -q`, `poetry run ruff check src tests`,
    and `git diff --check`.
- [ ] T5.5 [manual gate] With explicit authorization and after T5.4,
  execute the durable prepared Qwen closure with a sealed site-plan image.
  Verify the retained raw completion and any declared repair result first pass
  strict JSON admission, then verify the admitted JSON reaches workflow-local
  JSON-to-SVG tooling. Record only redacted identities, contract versions, and
  outcomes; DAR must neither parse floorplan semantics nor validate SVG.
- [ ] T5.6 [release] Update validation evidence and feature status, then
  package/release only after every prior task is complete. Record OS isolation
  as deferred future hardening rather than a release blocker.
