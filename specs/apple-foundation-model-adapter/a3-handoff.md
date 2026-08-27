<!-- markdownlint-disable MD013 -->
# A3 Implementation Handoff

## Status

The Apple Foundation Models sealed-host integration is complete through C2.
C3 is the next implementation slice.

## Completed commits

- `86dd78b` — define the A3 specification, plan, task list, and Fastmail O7
  dependency.
- `830cd5d` — characterize the existing synchronous sealed-run bridge to an
  injected async adapter and narrow A3 accordingly.
- `47bee84` — add session-free Apple platform, SDK, and system-model
  eligibility preflight.
- `30ad60e` — add immutable Apple profiles without HTTP transport fields.
- `a16574c` — add the human-only `configure-apple-model` command and redacted
  setup failures.
- `f677c0f` — bind sealed workflows to their configured Apple profiles.

## C2 completion — 2026-08-27

C2 is complete. The host selects the existing HTTP adapter or the canonical
Apple async adapter from the configured profile; the Apple path receives only
the stored model alias. The sealed runner now accepts either existing adapter
type, enforces exact profile-registration binding before consuming prepared
input, and passes strict adapter coverage to DAR.

Focused fake-backed tests cover exact Apple alias construction, same-alias
HTTP-to-Apple profile mismatch, strict no-fallback coverage, sealed prompt
consumption, terminal-output shaping, trace redaction, async error propagation,
and cancellation propagation. The focused suite passed 29 tests; the full suite
passed 1207 tests with one skipped and six deselected. Ruff and `git diff
--check` passed. Council and ponytail reviews found no supported findings.

## Authoritative artifacts

- [A3 specification](spec.md), especially FR-17.
- [A3 plan](a3-plan.md).
- [Canonical A3 task list](a3-tasks.md).
- [C0 boundary analysis](a3-c0-analysis.md).

## C2 objective

Make the sealed saved-workflow host select and bind the configured Apple
profile without introducing an Apple HTTP service, a generic provider registry,
or a second host execution API.

### Required implementation

1. `LocalWorkflowHost.open()` selects its model adapter from the configured
   profile:
   - `strict-local-adapter-v1` uses the existing `create_local_adapter()`.
   - `apple-foundation-models-adapter-v1` uses
     `create_apple_foundation_model_async_adapter()` with only the stored model
     alias.
2. `WorkflowRunner` accepts the existing
   `OpenAIClientAdapter | AsyncOpenAIClientAdapter` union. The existing
   synchronous `run_agent_workflow()` already bridges to async execution.
3. The runner receives the active configured `profile_id` and rejects a
   registration bound to any other profile before sealed input consumption,
   model/provider work, MCP initialization, or handler dispatch.
4. The runner passes `model_adapter_coverage="strict"` to
   `run_agent_workflow()` so an unmatched package model cannot receive an
   augmented/default adapter fallback.
5. Preserve all existing HTTP host behavior.

### Required focused evidence

- An Apple adapter is constructed with exactly the configured alias.
- A same-alias HTTP/Apple cross-profile registration fails before consuming
  prepared input.
- A package-requested model alias outside strict coverage cannot fall back.
- Existing HTTP saved workflow execution remains green.
- A fake Apple saved run preserves sealed prompt consumption, terminal-output
  shaping, and redacted tracing.

## Important current facts

- `workflow_host/profiles.py` provides `create_apple()` with adapter ID
  `apple-foundation-models-adapter-v1` and `base_url=None`.
- `apple_foundation_models.py` provides
  `preflight_apple_foundation_models()`.
- `workflow_host/host.py` provides `configure_apple_local_host()`.
- `workflow_host/cli.py` exposes `configure-apple-model`.
- `WorkflowRegistration` already persists `profile_id`.
- `WorkflowRunner` currently accepts only `OpenAIClientAdapter`, calls
  `run_agent_workflow()` without strict coverage, and validates only localness
  and model alias.
- Do not add an async host entry point or nested-loop workaround. Generic
  synchronous-wrapper behavior owns that boundary.

## Required working discipline

1. Read `AGENTS.md` and `AGENTS.local.md`.
2. Use CodeGraph before source exploration and GitNexus impact before source
   edits.
3. Work test-first in small, honest slices.
4. For each slice, run focused tests, Ruff, and `git diff --check`; obtain
   council and ponytail reviews; address supported findings; run
   `gitnexus detect-changes`; commit; then run `gitnexus analyze`.
5. Do not make live Apple, Fastmail, or other external calls from unit tests.
6. Do not mark C2, C3, or C4 complete without their stated evidence.
