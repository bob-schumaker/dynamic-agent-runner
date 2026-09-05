# Fastmail Inbox Triage Decisions

## D1 — First-slice boundary

- Status: approved 2026-09-02
- Decision: deliver one saved, read-only inbox-triage workflow rather than a
  general mailbox-management agent.
- Rationale: every mutation needs its own current-surface, provenance,
  approval, and action-ledger boundary.

## D2 — Exact local-model binding

- Status: updated 2026-09-05
- Decision: bind strictly to direct in-process llama.cpp with
  `Qwen/Qwen2.5-3B-Instruct-GGUF` revision
  `7dabda4d13d513e3e842b20f0d435c732f172cbe` and
  `qwen2.5-3b-instruct-q4_k_m.gguf`.
- Rationale: it is the recorded downloaded Qwen Instruct GGUF and is eligible
  for DAR's llama.cpp adapter. No MLX, Apple, HTTP, or alternate-Qwen fallback
  preserves the selected local execution boundary.

## D3 — Query and result budget

- Status: approved 2026-09-02
- Decision: one `search_email` dispatch, five messages maximum, and a
  preceding-24-hours query window.
- Rationale: the cap limits model exposure and avoids claiming full-mailbox
  coverage.

## D4 — Draft output is not a side effect

- Status: approved 2026-09-02
- Decision: proposed replies are terminal output only.
- Rationale: a Fastmail draft/reply/send action needs a separately specified
  and authorized mutation feature.

## D5 — Current schema is host-owned

- Status: approved 2026-09-02
- Decision: name only the `search_email` semantic capability and depend on
  host current-surface revalidation for remote mapping and schema.
- Rationale: package files cannot substitute historical/redacted tool evidence
  for a reviewed current surface.

## D6 — Qwen tool-use evidence is a feature prerequisite

- Status: satisfied 2026-09-05
- Decision: the authorized local-only probe qualified the exact Qwen GGUF with
  `chatml-function-calling`: one schema-valid `search_email({})` call, zero
  continuation calls after the synthetic result, and valid terminal JSON. Its
  artifact SHA-256 and configuration fingerprint are recorded in
  `validation.md`.
- Rationale: model availability is not tool-use capability. The successful
  preflight used synthetic data only, before any Fastmail data could reach the
  model.

## D7 — Specification gate approval

- Status: approved 2026-09-05
- Decision: the owner approved the refreshed Qwen llama.cpp scope for gated
  implementation. P0 and Fastmail acceptance remain separately authorized.
