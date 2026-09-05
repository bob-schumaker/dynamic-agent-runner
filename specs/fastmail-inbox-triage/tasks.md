# Fastmail Inbox Triage Tasks

## Status

The owner authorized this complete goal on 2026-09-05, including current-surface
review, package authoring, and one bounded read-only acceptance dispatch.

## P0 — Qwen protocol qualification

- [x] T001 [tests] Write fake-only tests for strict Qwen artifact identity,
  SHA-256 preflight, immutable alias/configuration fingerprint, no-network
  resolution, and synthetic two-turn tool-loop mechanics.
- [x] T001a [tests] Add sync/async executor RED tests proving that the initial
  request alone exposes the required tool and the post-result continuation has
  `tools=()` and no tool choice.
- [x] T002 [implementation] Add the host-owned immutable local-model preflight
  and triage binding T001 requires: verified local path/SHA/fingerprint with
  failing download seams, plus an empty-schema `search_email` wrapper that
  rejects arguments, constructs unread/24-hour/five limits after reviewed-surface
  revalidation, and projects bounded attachment-free results. Do not reuse the
  generic remote-schema-forwarding binding unchanged.
- [x] T002a [tests/implementation] Add sync/async phase-specific executor tool
  exposure: after the one result, requests carry no tools and no choice.
- [x] T003 [manual gate] After explicit authorization, run the local-only
  synthetic probe against the recorded Qwen GGUF. It must record redacted
  version/configuration fingerprints, one schema-valid call, zero continuation
  calls, and valid terminal JSON. It must not construct an MCP client or use
  Fastmail data.
  - Depends on: T001, T001a, T002, T002a and focused suites passing.
  - Receipt: artifact SHA-256
    `626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d`;
    configuration fingerprint
    `8f5619a7dd6215ced444ecc4966b849f453e7ba89376e046c4a08c4f0de34bcb`;
    one valid `search_email({})` call; zero continuation calls; valid terminal
    JSON. The probe used only synthetic data and did not construct MCP or access
    Fastmail, credentials, or the network.

## P1 — Package policy

- [x] T004 [tests] Add fake reviewed-surface and package-policy tests for
  unread/24-hour/five-message host constraints, one semantic dispatch, bounded
  attachment-free result projection, adversarial content, and zero mutation.
- [x] T005 [implementation] Add a de-identified fixture and only the package
  validation/runtime support proven necessary by T004.

## P2 — Package and acceptance

- [x] T006 [authoring] After T003-T005 and T002a, issue the host-internal
  material receipt from the owner's approved current-surface context, then
  generate and validate the four-file package through the host authoring path.
- [x] T007 [manual gate] After T006 and T008, perform the owner's authorized
  redacted acceptance using the pinned Qwen artifact, the reviewed Fastmail
  connection, and one bounded read-only dispatch.
  - Evidence: current reviewed-surface identity/schema receipt, one-or-zero
    dispatch count, empty mutation ledger, matching P0 fingerprint, and no raw
    email, OAuth, or schema data in retained evidence.

## Final Gate

- [x] T008 [validation] Before acceptance, run focused tests, full pytest,
  Ruff, changed-file pre-commit, and `git diff --check`; record results in
  `validation.md`.
