# Provider-Backed Context Compaction Specification

## Metadata

- Feature slug: `provider-backed-context-compaction`
- Mode: `light`
- Artifact type: future feature specification
- Status: prepared for future implementation planning
- Owner: context-management prepare stage plus model-provider adapters
- Primary predecessor:
  - `specs/context-management-prepare-stage/spec.md`
- Related artifacts:
  - `specs/openai-compatible-provider-wrapper/spec.md`
  - `specs/litellm-provider-adapter/spec.md`
  - `specs/capability-status-report/spec.md`
  - `src/dynamic_agent_runner/executor.py`
  - `src/dynamic_agent_runner/openai_client.py`
  - `tests/test_executor.py`

## Objective

Add an optional provider-backed context compaction path for automatic
context-window handling, including provider/window replacement metadata such as
compaction window ids and token baselines.

The first target is an OpenAI-compatible remote compaction capability, such as a
provider endpoint shaped like `/responses/compact` when the configured provider
supports it. The runtime must treat that capability as optional and
capability-gated, not as a universal model feature.

## Problem Statement

The implemented prepare stage already supports threshold metadata,
deterministic basic compaction, rolling summaries, injected pre-turn and
mid-turn compaction seams, reset diagnostics, and one-shot overflow retry.

What remains missing is a first-class provider-backed replacement-history path:

- the provider receives prepared active history for compaction
- the provider returns validated replacement history
- the runtime installs that replacement history as the active context
- metadata records the provider compaction window and token baseline so later
  threshold checks do not immediately compact the same carried prefix again

Without a dedicated spec, provider-backed compaction could leak into model
adapter request code, persistent-session storage, or ad hoc executor retries.
This feature keeps the ownership split explicit.

## Scope

This feature covers:

1. provider capability discovery for remote context compaction
2. a package-owned provider-compaction request and response contract
3. a context-management call path that invokes provider compaction only when
   policy and provider capability both allow it
4. validation of replacement history before installation
5. compaction window id and token-baseline metadata
6. pre-turn and eligible mid-turn use through existing compaction phases
7. redacted trace and capability/status reporting
8. fake-provider unit tests only

## Non-Goals

This feature must not introduce:

- live OpenAI, LiteLLM, or provider calls in unit tests
- runner-owned durable session storage
- cross-run transcript replay
- model-backed summary fallback behavior; that belongs to
  `model-backed-context-summaries`
- semantic selection or embedding retrieval; that belongs to
  `semantic-context-profiles`
- raw provider compaction payloads in traces
- automatic use of remote compaction without explicit policy and capability
  checks

## Proposed Policy Shape

The policy should extend the existing `context_compaction.auto` shape without
replacing it:

```yaml
runtime:
  execution_policy:
    prepare_model_input:
      context_compaction:
        auto:
          enabled: true
          implementation: provider
          strategy: provider_remote
          trigger: token_threshold
          threshold_ratio: 0.9
          remote:
            provider_capability: responses_compact
            require_remote: false
            fallback: basic
            max_replacement_messages: 32
            preserve_system_messages: true
            window_baseline: carried_prefix
```

Names are draft. Implementation planning should keep the public policy compact
and avoid exposing provider-specific wire details.

## Functional Requirements

### FR1 — Gate Remote Compaction by Capability

Given remote compaction is configured, when the selected provider does not
advertise the required compaction capability, then the runtime must either use
the configured fallback or fail with a package-owned error.

Remote compaction must never be inferred solely from provider name.

### FR2 — Validate Replacement History Before Installation

Given a provider returns replacement history, when the runtime receives it, then
the runtime must validate that messages are ordered, typed, non-empty where
required, and compatible with the selected provider request shape before using
them for the next model call.

Malformed replacement history must fail closed.

### FR3 — Preserve Pinned and Active Turn Boundaries

Given pinned system/developer context, approval state, pending tool state, or
the current user turn exists, when provider compaction runs, then the runtime
must preserve those boundaries or reject the replacement.

Provider compaction may summarize older history; it must not silently rewrite
the active instruction hierarchy or break an in-progress tool-call/result pair.

### FR4 — Track Window Ids and Token Baselines

Given provider compaction installs replacement history, when metadata is
recorded, then the runtime must record a compaction window id, phase, trigger,
provider capability, tokens before/after, baseline token count, and whether
future threshold checks should count total context or growth after the carried
prefix.

The window id may be generated by the runtime when the provider does not return
one.

### FR5 — Keep Reset Separate from Compaction

Given a workflow requests a new context window without summarized replacement
history, when metadata is recorded, then the runtime must report reset behavior,
not provider-backed compaction success.

### FR6 — Redact Diagnostics

Given provider compaction runs, when trace or stream metadata is emitted, then
the runtime must expose only non-sensitive facts such as status, phase, token
counts, capability name, baseline id, and error class. It must not expose raw
conversation content or provider replacement payloads by default.

## Acceptance Criteria

- Provider-backed compaction is unavailable unless both workflow policy and
  provider capability allow it.
- Replacement history is validated before installation.
- Window id and baseline metadata are emitted after successful replacement.
- Pre-turn compaction can replace over-threshold prepared input through the
  remote provider path.
- Mid-turn compaction remains opt-in and preserves iterative-loop safety.
- Fallback behavior is deterministic: `basic`, `model_summary`, or fail-closed.
- Unit tests use fake provider compaction collaborators only.

## Implementation Planning Notes

- Start with RED tests around `prepare_model_input(...)` and executor retry
  paths before adding provider contracts.
- Reuse the existing `context_compactor` seam only if it can carry provider
  capability and baseline metadata without becoming an untyped escape hatch.
- Add capability/status reporting in the same slice or explicitly mark it
  metadata-only until implemented.
- Coordinate with `litellm-provider-adapter` before binding any LiteLLM-specific
  transport shape.

## Validation Checklist

Future implementation should include:

- validation tests for supported and unsupported remote-compaction policy
- executor tests for provider compaction success, missing capability, malformed
  replacement history, fallback, and fail-closed behavior
- tests proving pinned hierarchy/current turn/tool pairs are preserved
- tests proving window id and baseline metadata are present and redacted
- capability/status tests for live, missing-collaborator, fallback, and disabled
  states

Suggested commands:

```bash
poetry run pytest \
  tests/test_validation.py tests/test_executor.py tests/test_capabilities.py -q
poetry run ruff check src tests
```

## Open Questions

- Should the provider-compaction collaborator live in `openai_client.py`, a new
  context-management module, or a provider capability registry?
- Should the runtime support provider-returned window ids directly, or always
  wrap them in package-owned ids?
- Should fallback to model-backed summaries be allowed in the same run, or only
  in a separately configured policy?
