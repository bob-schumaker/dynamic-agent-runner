# Local Model Runner Interface Tasks

## T1 — Closed recipe contract

- [x] T1.1 [tests, RED] Add focused preparation tests for the closed
  `transformers-peft-single-image-v1` profile: exact base/adapter groups and
  roles, reserved runner ID, unknown/duplicate fields, profile-aware digest,
  and no loader eligibility for invalid closures.
- [x] T1.2 [implementation] Add the minimal typed loader-profile value to
  `local_model_preparation.py`; include it in recipe identity and reject every
  configuration outside the one v1 profile.
- [x] T1.3 [tests, GREEN] Prove the Qwen native recipe has the exact profile,
  complete grouped closure, and a profile-aware digest.

## T2 — Generic runner behavior

- [x] T2.1 [tests, RED] Add fake-only tests for `AutoProcessor`,
  `AutoModelForImageTextToText`, and `PeftModel` local-only/remote-code-disabled
  arguments; assert no loader call for rejected profiles or sets.
- [x] T2.2 [tests, RED] Add fake-only tests for one PNG/JPEG image, 8 MiB and
  32-megapixel limits, malformed media, the then-current 1..65536
  `max_new_tokens` ceiling, at most 32
  continuations, deterministic generation, prompt-token suffix slicing, empty
  output, and cleanup on every
  exception/cancellation path.
- [x] T2.3 [implementation] Add a framework-named generic runner/adapter that
  implements only `transformers-peft-single-image-v1` using in-memory image
  objects and DAR's current `ModelResponse` contract.
- [x] T2.4 [tests, GREEN] Run the new runner tests and existing local-model
  adapter regressions with no live model, Hub, or GPU dependency.

## T3 — Host integration and dependencies

- [x] T3.1 [tests, RED] Add host/catalog tests that reserve
  `transformers-peft-v1`, route the Qwen profile through DAR's built-in runner,
  reject client collisions, and retain client runners for nonstandard IDs.
- [x] T3.2 [implementation] Bind the Qwen profile and recipe to
  `transformers-peft-v1`; retain the exact model-specific adapter/recipe IDs
  and leave the legacy llama.cpp floorplan path unchanged.
- [x] T3.3 [implementation] Add the bounded optional `transformers-peft`
  dependencies in `pyproject.toml`; run `poetry lock` rather than editing the
  lockfile.
- [x] T3.4 [tests, GREEN] Run focused host/profile/preparation/runner tests.

## T4 — Validation and acceptance

- [x] T4.1 [validation] Run `poetry run pytest -q`,
  `poetry run ruff check src tests`, and `git diff --check`.
- [x] T4.2 [manual gate, attempted] With explicit authorization, install the
  optional extra and prepare the pinned Qwen closure. The sealed image run
  reached PEFT adapter loading but did not generate output because automatic
  placement disk-offloaded on the MPS-capable host. Record only redacted
  provenance in `validation.md`; do not treat this as acceptance.

## T5 — Generic MPS placement

- [x] T5.1 [tests, RED/GREEN] In `tests/test_transformers_peft_model.py`, add fake
  hardware-capability coverage for both closed branches. With MPS available,
  assert `from_pretrained` retains local-only/remote-code-disabled/automatic
  dtype arguments but omits `device_map`, calls the fake base model's
  `.to("mps")`, and only then calls fake `PeftModel.from_pretrained`. With MPS
  unavailable, retain the exact local-only, remote-code-disabled automatic
  path. Neither test may expose an authored or client placement option.
- [x] T5.2 [tests, RED/GREEN] Add a focused generation regression proving MPS-branch
  inputs target the wrapped model's MPS device and that existing sealed-input
  cleanup and package-owned error classification remain unchanged. Include one
  failure case for each new step—MPS move and adapter attachment—which clears
  the bound image, reports only DAR's redacted error without vendor exception
  text, prompt text, or artifact/image paths, and does not retry through
  CPU/disk offload. This is the observable no-offload contract; the authorized
  real gate, not a fake, proves actual Accelerate/PEFT dispatch behavior.
- [x] T5.3 [implementation] In the built-in generic runner only, implement
  the fixed host-detected MPS branch: load the base without `device_map`, move
  it to MPS, then attach PEFT; preserve automatic placement when MPS is
  unavailable. Do not add a scheduler, allocator, hardware scan, device
  setting, or model-specific branch.
- [x] T5.4 [tests, GREEN] Run the focused runner, preparation, and host
  regressions; then rerun `poetry run pytest -q`, `poetry run ruff check src
  tests`, and `git diff --check`.
- [x] T5.5 [manual gate] Re-run the already authorized pinned-closure test
  with one sealed floorplan image and pass the returned text to the
  workflow-local floorplan JSON parser. Record redacted provenance and its
  nonempty parseable result only after generation succeeds; DAR does not parse
  or validate that JSON.

T1–T5.4 require test-first implementation. T4.2 and T5.5 are intentionally
separate: they download multi-gigabyte artifacts and handle real image/model
execution.
