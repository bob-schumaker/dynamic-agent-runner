# Workflow Input Converter Plugin Tasks

## Status

T1 through T5.5 are complete. T5.6 has a verified local package build but
requires a release-version and publish-target decision before publication. T5.7
is the bounded Mac-only Metal addendum. T5.8 specifies host-owned debug
diagnostic retention for sealed converter runs.
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
  `transformers-generate-v1` contract, sealed model-material-lock digest, and
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
- [x] T5.4 [JSON output boundary] Establish a generic syntax-only JSON path
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
  - [x] T5.4.2 [tests, RED] Add fake-only standard-runner tests proving an
    exact JSON constraint reaches a capable backend, is rejected before
    generation by an incapable backend, and leaves unstructured generation
    unchanged. Prove no prompt text, sealed payload, raw completion, or repair
    artifact is exposed in DAR traces or API results.
  - [x] T5.4.3 [implementation] Implement only the generic runner seam and
    capability binding required by T5.4.2. Reuse `response_format`; do not add
    a floorplan branch, a general schema language, or a model-specific prompt
    rewrite.
  - [x] T5.4.4 [tests, RED/GREEN] Add workflow-owned post-processing tests for
    strict JSON validation and the declared bounded repair policy. Retain the
    original and repaired completion as user-only diagnostic artifacts with
    digests and a repair report; accept only strict JSON after processing. The
    processor must reject incomplete or semantically ambiguous output rather
    than invent structure.
    The implementation uses a fixed private terminal-processor edge, not the
    existing boolean terminal validator: it passes bounded bytes only between
    declared package assets, retains authenticated local-user diagnostics, and
    exposes only final rendered output plus redacted admission metadata.
    - [x] T5.4.4.1 [tests, RED/GREEN] Add fake-only standard-runner tests for
      bounded continuation generation when a JSON completion exhausts its
      declared chunk ceiling. Prove fragments are concatenated exactly,
      continuation stops on a non-exhausted chunk, the declared continuation
      budget fails closed, and neither fragments nor continuation prompts enter
      traces or API results.
    - [x] T5.4.4.2 [implementation] Extend the selected standard runner and
      its fixed converter contract with bounded, deterministic continuation
      generation. Preserve the original conversation and image ingress, append
      only the model's exact prior fragment for each continuation request, and
      return the assembled completion solely to the existing private
      post-processing edge. Do not add schema-specific stitching, semantic
      repair, or a public partial-output path.
    - [x] T5.4.4.3 [evidence] Evaluate the retained simple-floorplan completion
      `sha256:4db4b642a049a28c42c9bd1d1187b6596ea343ea5d4580ba20b139bd7b721734`.
      Record only the observed contract: a strict JSON object with `walls` and
      `rooms`; walls have `id`, `start`, `end`, `thickness`, `curvature`, and
      `openings`; rooms have `label` and wall IDs. Do not infer room polygons:
      the observed room references are not complete topology.
    - [x] T5.4.4.4 [tests, RED/GREEN] Add workflow-local processor tests for
      strict JSON-object admission and a deterministic JSON-to-SVG renderer.
      Cover the observed wall/opening fields, malformed or incomplete JSON,
      unknown opening types, and non-geometric room labels. Assert rendering
      never invents walls, room polygons, or semantic repair.
    - [x] T5.4.4.5 [implementation] Package a fixed terminal-processor chain
      for the floorplan workflow: strict JSON admission followed by a
      workflow-owned wall/opening SVG renderer. Preserve the original JSON and
      processor report as private diagnostics; emit only SVG after successful
      rendering. DAR remains unaware of floorplan fields and SVG semantics.
    - [x] T5.4.4.6 [tests, RED/GREEN] Add strict admission coverage for a
      complete JSON object and the retained truncated completion
      `sha256:3705485ac5628c30f03e93c1b434097958d9f53b23b68bfb995e96a6825fcd7a`.
      It must admit only a complete object and must retain/reject, never repair,
      EOF-truncated output before rendering.
    - [x] T5.4.4.7 [implementation] Put the strict JSON admission processor
      before the workflow-owned renderer. Preserve valid bytes exactly, emit no
      public partial output, and rely on the existing private processor
      diagnostic for rejected originals.
    - [x] T5.4.4.8 [tests, RED/GREEN] Restore the observed floorplan JSON
      contract in the fixture prompt and declare `response_format:
      {type: json_object}`. Cover tuple endpoints, opening widths, room wall
      references, and the coordinate normalization rule so later prompt edits
      cannot silently weaken the renderer contract.
    - [x] T5.4.4.9 [tests, RED/GREEN] When a declared JSON response is
      incomplete at the end of a generated chunk, request the bounded exact
      continuation even if the backend did not mark the chunk exhausted.
      Reject at the continuation limit; never route partial JSON to terminal
      processing.
    - [x] T5.4.4.10 [tests, RED/GREEN] Emit redacted-safe model-generation
      metadata for chunk count, token counts when available, and each chunk's
      exhaustion outcome in the existing `model_response` trace event. Do not
      expose completion fragments or continuation prompts.
  - [x] T5.4.5 [validation] Run focused runner and workflow-local processor
    regressions, then `poetry run pytest -q`, `poetry run ruff check src tests`,
    and `git diff --check`.
    - [x] T5.4.5.1 [test maintenance] Align the floorplan package prompt
      assertion with the declared detailed JSON contract, then rerun the full
      validation commands. Do not weaken the fixture prompt or remove the
      contract assertion to make the suite pass.
- [x] T5.5 [manual gate] With explicit authorization and after T5.4,
  execute the durable prepared Qwen closure with a sealed site-plan image.
  Verify the retained raw completion and any declared repair result first pass
  strict JSON admission, then verify the admitted JSON reaches workflow-local
  JSON-to-SVG tooling. Record only redacted identities, contract versions, and
  outcomes; DAR must neither parse floorplan semantics nor validate SVG.
  Recorded 2026-09-08: run `22a6d05c-5fc9-4f73-a55d-65ff82510672` completed;
  retained raw digest `542480e5b328509e60c0552c01806cc2afb8769bff63c4f3f6a0babc8409f57f`
  was admitted as `189d07a5449fe548c2ad7559f93f541e79d92be2807e72eef1eafbed8a3f41e0`
  with `none,none` processor reports, then returned validated SVG.
- [ ] T5.6 [release] Update validation evidence and feature status, then
  package/release only after every prior task is complete. Record OS isolation
  as deferred future hardening rather than a release blocker.
  - [x] T5.6.1 [local package] Build `dynamic-agent-runner==0.1.18` with
    `poetry build` and verify the generated sdist and wheel. This proves only
    local package integrity; it does not authorize a publish.
  - [ ] T5.6.2 [release decision] Select an unreleased PEP 440 runtime version
    and explicit publish target before publication. The checked-out `0.1.18`
    version is already behind repository tag `0.1.31`; do not publish it or
    infer a version bump from this task. The configured candidates are
    `global-release-pypi` and `global-dev-pypi`; this task does not choose
    between them.
  - [ ] T5.6.3 [publish] Publish only the approved version to the explicit
    target, then record the immutable artifact identity and release receipt.

## T5.7 — Apple Metal Execution Addendum

- [x] T5.7.1 [tests, RED/GREEN] Add fake-only loader tests proving MPS is
  selected only when PyTorch reports it available; preserve the current
  non-MPS `device_map="auto"` behavior exactly. Prove PEFT attachment precedes
  MPS placement, evaluation mode is set, and generation uses an inference-only
  context without changing JSON, continuation, cleanup, or redaction behavior.
  Prove direct and continuation responses expose only MPS selection and measured
  generation outcome metadata, never tensors, sealed payloads, prompts, or
  completion fragments.
- [x] T5.7.2 [implementation] Make the existing `transformers-peft-v1` MPS
  path explicit and Mac-only: attach the verified PEFT adapter, place the
  completed model on MPS, set evaluation mode, and use inference-only
  generation. Extend only the existing redacted model-generation metadata with
  MPS selection and measured generation outcome on direct and continuation
  responses. Do not add a workflow-controlled device option, CPU fallback, MLX
  backend, model conversion, quantized artifact, or compilation default.
- [x] T5.7.3 [benchmark] With explicit authorization, run a fixed-input warm
  baseline and candidate on an eligible Mac. Retain only device selection,
  wall-clock duration, generated-token count, and tokens per second. Adopt a
  Mac-only dtype or compilation experiment only if it preserves the terminal
  contract and improves the measured warm-run result; otherwise retain the
  current MPS configuration. The baseline is the prior loader order that moves
  the base model to MPS before PEFT attachment; the candidate attaches PEFT
  before moving the completed model to MPS. Both use the same prepared model,
  sealed image, prompt, and declared generation limit.
  - [x] T5.7.3.1 [benchmark fixture] Select a fixed benchmark generation limit
    that reaches the terminal contract for the simple floorplan image. The
    production `4096`-token workflow did not complete its MPS warm pass within
    five minutes on 2026-09-08, so it is not a practical warm benchmark limit.
    Use the selected limit unchanged for baseline and candidate; do not infer it
    from partial output or change it during a measurement. The selected limit
    was `1024` tokens with zero continuations. It reached the terminal contract
    in the authorized floorplan run, then produced warm MPS measurements of
    994 generated tokens in 167.301665 seconds (5.941363 tokens/sec) for the
    prior loader order and 994 in 156.223020 seconds (6.362699 tokens/sec) for
    the candidate. No dtype or compilation experiment was adopted.

## T5.8 — Host-owned Debug Diagnostic Retention

- [x] T5.8.1 [design] Define one explicit local-principal debug invocation
  capability, separate debug-run/retrieval surface, and authenticated diagnostic
  run identifier distinct from the ordinary run ID. It must not be a workflow
  manifest field, converter parameter, model parameter, or normal workflow
  result option. Define fixed aggregate retention and expiration limits,
  authenticated retrieval and deletion behavior, and the classified outcome
  when the retention limit is reached for both completed and failed runs.
- [x] T5.8.2 [tests, RED] Add fake-only runner and host tests proving a debug
  run retains every model-output fragment in order, per-chunk token/exhaustion
  metadata, reached terminal-processor artifacts, and the classified final
  outcome. Cover strict-JSON success, EOF continuation, malformed JSON,
  terminal-processor rejection, timeout, and cancellation. Prove normal runs
  retain none of these artifacts, and no trace, API result, workflow-visible
  output, or exception text exposes the debug identifier or content. Prove the
  recorder observes a generated fragment before strict JSON rejection and before
  deciding whether to request a continuation.
- [x] T5.8.3 [implementation] Add the smallest host-owned diagnostic store and
  explicit debug-run/retrieval seam. Reuse the existing authenticated local
  terminal-diagnostic ownership and lifecycle pattern where possible. Install a
  per-run recorder at the standard runner/adapter boundary only for an active
  debug run, before JSON validation and continuation branching. Enforce
  aggregate byte and TTL limits, retain no sealed payload, decoded media,
  tensors, arbitrary process output, or environment data, and preserve existing
  payload/packed-state cleanup on every path.
- [x] T5.8.4 [tests, GREEN] Prove authentication, isolation between local
  principals and run IDs, expiry, aggregate-limit failure, ordered fragment
  retention, and ordinary redaction/cleanup regressions. Run focused tests,
  then `poetry run pytest -q`, `poetry run ruff check src tests`, and
  `git diff --check`.
- [x] T5.8.5 [manual gate] With explicit authorization, run the cleaned
  Japan-home floorplan under the debug capability. Verify retained fragments
  explain whether continuation stopped because of EOF truncation, malformed
  JSON, or the declared continuation limit, while the normal run result and
  traces remain redacted. Record only diagnostic identity, declared limits, and
  classified outcome in validation evidence.

## T5.9 — Generic generation safety bounds

This completed compatibility ceiling is superseded as the canonical generation
policy by `specs/model-generation-resource-budgets/spec.md`. It remains in
place until that specification's migration tasks remove duplicate ownership.

- [x] T5.9.1 [tests, RED/GREEN] Raise the generic `transformers-peft-v1`
  per-fragment `max_tokens` validation ceiling from 65,536 to 1,000,000 while
  retaining the existing 32-continuation ceiling. Prove the inclusive 1,000,000
  boundary is accepted and 1,000,001 is rejected. Document that these are DAR
  safety bounds rather than a context-length claim for every locked model set.
  Focused fake-only runner tests passed on 2026-09-09.
