# Prompt Cache Intent Handoff

## Goal

Provide repo-neutral guidance for consuming optional upstream prompt-cache intent
metadata in a dynamic-agent runtime.

## Handoff Role

- Type: internal resume handoff
- Audience: future dynamic-agent runtime implementation session
- Authority: supporting implementation handoff only; the target repository's
  active spec, tasks, and source code remain authoritative
- Paired artifacts: none

## Current Status

- Done: The upstream agent-development runtime package model now supports
  optional `execution_policy.prompt_cache` metadata as cache intent.
- Done: The upstream metadata is provider-neutral and keeps provider-specific
  behavior under optional `provider_hints`.
- Done: Current `dynamic-agent-runner` state was evaluated on `develop`; no
  downstream prompt-cache runtime support exists yet.
- Done: `specs/dynamic-agent-runner/tasks.md` includes Slice 13 as the
  concrete prompt-cache implementation slice.
- Done: Slice 13 now parses, validates, observes, and traces prompt-cache intent
  without blindly passing provider-specific fields.
- Remaining: Provider-specific prompt-cache request pass-through remains
  adapter-gated and deferred until exact SDK/API support is verified.

## Repository Context

- Target repository: dynamic-agent-runner or another runtime that consumes
  `agent-runtime.yaml` packages.
- Relevant downstream areas to inspect before implementation:
  - runtime manifest loader/model definitions
  - message rendering, especially `_render_messages(...)` or equivalent
  - token-budget or token-estimation support
  - trace/debug event models
  - OpenAI or provider adapter request construction
  - executor caller override/configuration paths

## Model Used

- The interface did not expose the exact model name.

## Branch and Integration State

- Current branch at latest check: `develop`.
- Branch status at latest check: `develop...origin/develop [ahead 3]`.
- Target branch: `develop` for follow-on local implementation unless the user
  selects a separate task branch or worktree.
- Relevant upstream change: implemented in `clinerules-roschuma`, not in this
  repository.
- Planned integration method: normal follow-on implementation slice in this
  runtime repository.
- Backup branches: none created.

## Files Reviewed

- `cline-tasks/prompt-cache-intent-handoff.md` — active supporting handoff note
  evaluated against current repository state.
- `specs/dynamic-agent-runner/spec.md` — existing assumptions already include
  token budgeting, package-owned tracing hooks, and runtime behavior overrides.
- `specs/dynamic-agent-runner/tasks.md` — Slice 13 is now complete and
  records prompt-cache implementation evidence.
- `src/dynamic_agent_runner/models.py` — preserves top-level
  `execution_policy` metadata used to carry optional `prompt_cache` intent.
- `src/dynamic_agent_runner/prompt_cache.py` — parses provider-neutral
  prompt-cache policy metadata and builds trace observation payloads.
- `src/dynamic_agent_runner/executor.py` — renders named message parts, emits
  prompt-cache eligibility traces, honors execution-level disable override, and
  records provider cached-token telemetry when present.
- `src/dynamic_agent_runner/token_budget.py` — provides the token estimator reused
  for stable-prefix token estimates.
- `src/dynamic_agent_runner/tracing.py` — provides trace events and redaction
  support for future cache-eligibility evidence.
- `src/dynamic_agent_runner/openai_client.py` — adapter boundary where any
  provider-gated cache pass-through would need to remain explicit.

## Files Changed

- `cline-tasks/prompt-cache-intent-handoff.md` — refreshed to reflect Slice 13
  implementation, validation, and remaining provider pass-through caveat.
- `specs/dynamic-agent-runner/tasks.md` — marks Slice 13 complete with
  implementation evidence.
- `src/dynamic_agent_runner/prompt_cache.py` — added prompt-cache policy and
  observation helpers.
- `src/dynamic_agent_runner/executor.py` — added prompt-cache trace and provider
  telemetry recording.
- `src/dynamic_agent_runner/api.py` — added optional `prompt_cache` execution
  override forwarding.
- `src/dynamic_agent_runner/validation.py` — validates prompt-cache metadata.
- `src/dynamic_agent_runner/__init__.py` — exports prompt-cache helper types and
  functions.
- `tests/test_prompt_cache.py` — covers Slice 13 behavior.

## Untouched Areas and Unrelated Local Changes

- Current untracked file before this refresh: this handoff note,
  `cline-tasks/prompt-cache-intent-handoff.md`.
- `cline-tasks/prompt-caching.md` is not present in the current checkout.
- `cline-tasks/give-your-agents-an-interpreter.md` is not present at its old
  path; the interpreter source reference now lives at
  `specs/llm-step-interpreter-middleware/references/give-your-agents-an-interpreter.md`.
- No unrelated source, spec, or memory-bank files were modified for this refresh.

## Upstream Manifest Shape

Generated packages may now include:

```yaml
execution_policy:
  prompt_cache:
    enabled: true
    strategy: stable_prefix
    min_prefix_tokens: 1024
    prefix_parts:
      - system
      - developer
      - skill_instructions
      - tool_schemas
    variable_parts:
      - user_prompt
      - run_state
    cache_key_hint: package_id
    provider_hints:
      openai:
        cache_key_strategy: package_id_and_version
        retention: auto
```

## Key Findings and Decisions

- Prompt-cache intent belongs upstream because stable cacheable material must be
  placed at the beginning of the request during package/prompt construction.
- Runtime implementations must not blindly trust upstream intent; they should
  validate the effective rendered request.
- Provider-specific fields should be optional adapter-level behavior, not part of
  the provider-neutral manifest contract.
- The downstream work fits the existing dynamic-agent-runner spec/tasks as a
  follow-on slice adjacent to token budgeting and tracing.

## Suggested Downstream Slice

This slice is represented in `specs/dynamic-agent-runner/tasks.md` as Slice
13 and is now complete.

```markdown
## Slice 13 — Prompt-cache intent and trace observation

- [ ] Read optional `execution_policy.prompt_cache` metadata from manifests.
- [ ] Preserve declared stable-prefix ordering during message rendering when it
      does not change prompt semantics.
- [ ] Estimate stable-prefix token count using existing token-budget support.
- [ ] Emit trace/debug fields for cache eligibility, prefix token estimate, and
      prefix hash.
- [ ] Record the rendered stable-prefix part names and the first variable part
      that ended cache eligibility so cache misses are explainable.
- [ ] Allow runtime callers to disable or override prompt-cache behavior.
- [ ] Pass provider-specific fields only when an adapter explicitly supports them.
- [ ] Record observed cached-token usage, cache-read status, or equivalent
      provider response metadata when the provider exposes it.
```

## Validation Performed

Upstream validation in `clinerules-roschuma`:

- `python -m pytest tests/test_agent_runtime_validator.py` — pass — 13 tests
  passed.
- `validate_agent_runtime.py simple-tool-agent-runtime.yaml --mermaid \
  simple-tool-agent-graph.mmd` — pass — example manifest validated. Full paths
  were under `skills/agent-development-skill/references/examples/`.

Downstream validation in this repository:

- `python -m pytest tests/test_token_budget.py tests/test_tracing.py -q` —
  pass — 11 tests passed in 3.46s. This validated nearby token-budget and
  tracing foundations before Slice 13 implementation.
- RED: `python -m pytest tests/test_prompt_cache.py -q` — fail — collection
  failed because `dynamic_agent_runner.prompt_cache` did not exist.
- GREEN: `python -m pytest tests/test_prompt_cache.py -q` — pass — 11 tests
  passed after adding prompt-cache parsing, validation, tracing, override,
  missing-estimator, and provider-telemetry support.
- Full validation: `ruff check src tests && ruff format --check src tests &&
  python -m pytest -q` — pass — 104 tests passed.

## Open Questions or Risks

- Confirm exact OpenAI SDK/API support before passing through explicit prompt
  cache request fields; Slice 13 intentionally records telemetry only and does
  not send provider-specific cache fields.
- Decide whether prompt-cache caller overrides are global, per workflow, per node,
  or per execution request.
- Decide trace field names and whether prefix hashes should be redacted or salted
  in sensitive deployments.
- Confirm whether declared `prefix_parts` can always be rendered before variable
  parts without changing prompt semantics.
- Decide how to represent runtime evidence when token estimation is unavailable,
  provider cache telemetry is absent, or an adapter intentionally ignores
  provider hints.
- Decide whether the missing historical `cline-tasks/prompt-caching.md` source
  note should be restored, superseded, or left unavailable.

## Next Steps

- [x] Evaluate this handoff against current repository status.
- [x] Add Slice 13 to `specs/dynamic-agent-runner/tasks.md` as the concrete
      prompt-cache follow-on slice.
- [x] Implement Slice 13 tasks T13.1 through T13.9.
- [ ] Commit the Slice 13 implementation and handoff/task updates.
- [ ] Restore, supersede, or intentionally ignore the missing historical
      `cline-tasks/prompt-caching.md` note before relying on it as source context.
- [ ] Decide whether to add adapter-gated provider-specific prompt-cache request
      pass-through after SDK/API support is verified.

## Resume Prompt

Continue from this handoff. Treat the upstream `execution_policy.prompt_cache`
manifest metadata as optional cache intent, not as an API mandate. Current repo
state has been verified on `develop`, and Slice 13 is implemented but may still
need committing if this note is read before the implementation commit. Continue
from the recorded validation and avoid blindly passing provider-specific prompt
cache request fields until exact SDK/API support is verified. Remaining
prompt-cache follow-up is provider pass-through policy, not provider-neutral
metadata parsing or trace observation.
