# Context Management Prepare Stage Specification

## Metadata

- Feature slug: `context-management-prepare-stage`
- Mode: `light`
- Artifact type: authoritative SDD feature specification
- Status: implemented baseline documented; future expansion requires a new
  approved plan or task slice
- Related artifacts:
  - `specs/dynamic-agent-runner/spec.md`
  - `specs/dynamic-agent-runner/tasks.md`
  - `specs/internal-graph-mutation/spec.md`
  - `specs/async-session-memory-pipeline/spec.md`
  - `specs/context-management-prepare-stage/references/context-pruning-pipeline-summary.md`
  - `src/dynamic_agent_runner/executor.py`
  - `src/dynamic_agent_runner/graph_mutation.py`
  - `tests/test_executor.py`
- Reference implementation studied:
  - `/Users/roschuma/Repos/github/codex/codex-rs/core/src/session/turn.rs`
  - `/Users/roschuma/Repos/github/codex/codex-rs/core/src/compact.rs`
  - `/Users/roschuma/Repos/github/codex/codex-rs/core/src/compact_remote.rs`
  - `/Users/roschuma/Repos/github/codex/codex-rs/core/src/client.rs`
  - `/Users/roschuma/Repos/github/codex/codex-rs/protocol/src/openai_models.rs`
  - `/Users/roschuma/Repos/github/codex/codex-rs/core/src/state/auto_compact_window.rs`

## Objective

Define the package-owned context-management prepare stage that runs before a
model adapter call and owns three related prompt-shaping behaviors:

- session pruning
- context compaction
- hierarchical prompt-context injection

The feature keeps model adapters narrow, keeps long-term session memory out of
scope, and gives future context growth management a stable runtime-owned home.

## Problem Statement

The primary runtime spec already names `prepare_model_input(...)` as the seam
for future context management, and the task history records an OA3 implementation
for context compaction, session pruning, and hierarchical prompt injection.
However, that behavior does not have a standalone feature spec.

Without an owning feature package, context-growth work can drift into the wrong
places:

- long-term async-session memory, which should own session identity and durable
  continuity metadata, not per-call prompt shaping
- graph mutation, which owns internal derived workflow transforms and one
  context-pruning mutation path, not the general policy surface for prompt
  preparation
- model adapters, which should execute prepared requests rather than rewrite or
  summarize prompt history

This spec separates short-horizon context construction from long-term memory and
from lower-level model execution.

## Current Runtime Context

The implemented baseline already includes:

- `PreparedInputMetadata` fields for hierarchy application, included/pruned
  session messages, compaction, file context, and mutation diagnostics
- `prepare_model_input(...)` as the public internal seam that renders model
  messages before adapter invocation
- opt-in `runtime.execution_policy.prepare_model_input` policy handling
- hierarchy message injection through `prompt_hierarchy`
- bounded session-message retention and pruning
- compact summary-message insertion for pruned session history
- bounded file-context prompt injection with source provenance
- trace payload metadata through `model_input_prepared`

`internal-graph-mutation` can feed prepared context into the same prompt
rendering path, but it is not the owner of the general context-management policy.

`async-session-memory-pipeline` can declare future session identity and
history-retention metadata, but it is not the owner of live pruning,
compaction, or prompt-context injection.

## Scope

This feature specification covers:

1. pre-adapter prompt shaping inside `prepare_model_input(...)`
2. policy-controlled session-message pruning for the current run context
3. policy-controlled context compaction of pruned messages into a model-visible
   summary part
4. hierarchical system/developer prompt-context injection
5. file-backed prompt-context injection as an existing concrete hierarchy input
6. diagnostics that make prepared inputs auditable
7. future OpenAI-focused automatic context-window compaction triggered by model
   token usage and context-window metadata
8. future separation of summarizing compaction from explicit new-window reset
   behavior

## Non-Goals

This feature must not introduce:

- runner-owned durable session storage
- cross-run transcript replay
- vector memory, embedding search, or semantic retrieval
- background summarization jobs
- model-adapter-specific prompt rewriting
- automatic mutation of portable workflow package artifacts
- approval pause/resume behavior
- multi-agent shared memory semantics
- a public graph-mutation schema

## Policy Surface

The policy lives under:

```yaml
runtime:
  execution_policy:
    prepare_model_input:
      prompt_hierarchy:
        system:
          - "Stable system context..."
        developer:
          - "Developer context..."
      context_compaction:
        max_session_messages: 8
        summary_template: "Earlier context summary:\n{summary}"
      file_context:
        enabled: true
        roots:
          - docs
        max_depth: 2
        max_files: 20
        max_bytes: 8192
        max_tokens: 2048
        prompt_role: developer
        header: "Project file context:"
```

Exact field growth requires a future approved task, but any expansion should
remain under `prepare_model_input` unless it belongs to another owning spec.

## Codex Automatic Compaction Findings

The local Codex repository provides the closest OpenAI-focused reference for
automatic context-window compression. The design points below are treated as
requirements input for future slices, not as current implementation evidence in
this package.

### Model-derived thresholds

Codex stores `context_window`, `max_context_window`, and
`auto_compact_token_limit` in model metadata. When no explicit auto-compact
limit exists, it derives the threshold from 90% of the resolved context window.
When a configured limit exists, it clamps that limit to 90% of the resolved
context window.

For this package, future auto-compaction should use the OpenAI model-registry
capability seam where possible, with workflow policy overrides only narrowing
or disabling automatic behavior.

### Pre-turn and mid-turn phases

Codex runs automatic compaction in two phases:

- **pre-turn**: before the next model request when active context already
  exceeds the auto-compact threshold
- **mid-turn**: after a model response when additional model work or pending
  input remains and the threshold has been reached

For this package, pre-turn compaction is the safer first implementation because
the current runner already has a pre-adapter prepare stage. Mid-turn compaction
belongs to a later iterative-loop slice because it interacts with model-emitted
tool calls, follow-up turns, and approval pauses.

### Remote compaction and local fallback

Codex prefers provider-backed remote compaction when available, using a
first-class `/responses/compact` endpoint that returns replacement history.
When provider-backed compaction is unavailable, it falls back to an inline model
turn with a summarization prompt.

For this package, the OpenAI-focused path should model remote compaction as an
optional provider capability rather than silently assuming it exists. A local
summarization fallback may be added later, but it must be explicit, testable,
and bounded.

### Window identity and prefix baselines

Codex advances an auto-compaction window id each time history is replaced. It
also tracks a prefix baseline so policies can count either total active context
or growth after the carried prefix. This avoids repeated compaction immediately
after a compacted window is installed.

For this package, future compaction metadata should record a window id and a
token baseline when automatic compaction is enabled.

### Reset is not compaction

Codex has a separate model-callable `new_context_window` tool that starts a new
context window without summarizing conversation history. That is an explicit
reset, not compression.

For this package, any future reset behavior must be a separate policy/tool from
context compaction and must not be reported as successful compression.

### Diagnostics and lifecycle

Codex emits compaction lifecycle data: trigger, reason, phase, implementation,
status, tokens before/after, and errors. It also has pre/post compact hooks and
records compacted replacement history as a distinct history item.

For this package, future compaction must extend `PreparedInputMetadata`,
`TraceEvent` payloads, and capability/status reporting before being treated as
production-ready.

## Functional Requirements

### FR1 — Keep context management before the model adapter

Context shaping must run before adapter invocation and must produce ordinary
model messages plus metadata. Model adapters must receive already-prepared
messages and must not own pruning, compaction, or hierarchy injection policy.

Acceptance criteria:

- Given a workflow is prepared for an `llm_step`, when context-management policy
  is enabled, then `prepare_model_input(...)` applies the policy before the
  adapter call.
- Given a caller supplies a custom adapter, when context policy applies, then
  the adapter receives the prepared messages without needing adapter-specific
  context logic.

### FR2 — Prune session messages deterministically

The prepare stage must be able to include a bounded suffix of current-run
session messages and identify messages excluded by the policy.

Acceptance criteria:

- Given more session messages exist than the configured retention bound, when
  input is prepared, then only the retained suffix is included in the prepared
  input.
- Given session messages are pruned, when metadata is inspected, then included
  and pruned counts are available.

### FR3 — Compact pruned context explicitly

The prepare stage may convert pruned session history into an explicit
model-visible summary message only when policy asks for compaction.

Acceptance criteria:

- Given session messages were pruned and compaction is enabled, when input is
  prepared, then a summary part is inserted before retained session messages.
- Given no session messages were pruned, when input is prepared, then compaction
  must not fabricate a summary.
- Given compaction is applied, when metadata is inspected, then compaction is
  recorded explicitly.

### FR4 — Inject hierarchical prompt context before volatile history

The prepare stage must support stable system/developer context parts that appear
before session history and user prompt content.

Acceptance criteria:

- Given `prompt_hierarchy.system` or `prompt_hierarchy.developer` is configured,
  when input is prepared, then those parts are inserted in deterministic order.
- Given hierarchy injection is applied, when metadata is inspected, then
  hierarchy application is recorded.

### FR5 — Inject bounded file-backed context with provenance

File-backed prompt context must remain explicit, package-root bounded, and
auditable.

Acceptance criteria:

- Given `file_context.enabled` is true, when input is prepared for a
  package-root-backed workflow, then matching files are injected as prompt parts
  subject to configured file, byte, token, and depth limits.
- Given injected file context exists, when prepared input is inspected, then each
  source path is represented in metadata and the prompt content.
- Given a configured file-context root escapes the package root, when input is
  prepared or validated, then the runtime must fail closed.

### FR6 — Keep diagnostics first-class

Prepared input metadata and trace payloads must distinguish unmodified input
from hierarchy injection, file-context injection, session pruning, compaction,
and graph-mutation-prepared context.

Acceptance criteria:

- Given context-management policy changes the prepared input, when
  `model_input_prepared` is traced, then the trace contains non-sensitive
  diagnostic facts about which transformations applied.
- Given transformed content may contain user, session, or file data, when traces
  are emitted, then sensitive content is not copied into non-redacted trace
  fields.

### FR7 — Derive automatic compaction thresholds from model context windows

Future automatic compaction must derive safe thresholds from model metadata and
must never wait until a request is guaranteed to overflow.

Acceptance criteria:

- Given a model has a known context window, when automatic compaction is enabled
  without an explicit threshold, then the runtime derives a threshold at 90% of
  that context window.
- Given a workflow configures a threshold above 90% of the model context window,
  when policy is normalized, then the runtime clamps it to 90%.
- Given no reliable context-window metadata exists, when automatic compaction
  is requested, then the runtime must either fail closed in strict mode or
  report automatic compaction as unavailable.

### FR8 — Separate pre-turn and mid-turn compaction phases

Automatic compaction must make the phase explicit because pre-turn and mid-turn
compaction have different safety and ordering requirements.

Acceptance criteria:

- Given active context exceeds the threshold before a model request, when
  automatic compaction is enabled, then pre-turn compaction runs before the
  adapter call.
- Given an iterative model-tool loop needs more model work after a response and
  the threshold is reached, when mid-turn compaction is implemented, then it
  must preserve pending tool/approval state and record `phase: mid_turn`.
- Given mid-turn compaction is not implemented, when that condition occurs, then
  the runtime must fail or stop explicitly rather than silently dropping history.

### FR9 — Prefer OpenAI/provider remote compaction when available

OpenAI-focused automatic compaction should use a provider-owned compaction
capability when available and a local model summarization fallback only when
explicitly configured.

Acceptance criteria:

- Given a provider advertises remote compaction support, when compaction runs,
  then the runtime sends prepared history to that provider boundary and installs
  the returned replacement history only after validation.
- Given remote compaction is unavailable and no fallback is configured, when
  compaction is required, then execution fails with a package-owned error.
- Given local summarization fallback is configured, when it runs, then the
  summary prompt, maximum retained user/history tokens, and output placement are
  deterministic and covered by tests.

### FR10 — Track compaction windows and reset separately

Automatic compaction must distinguish summarized replacement history from an
explicit new context window reset.

Acceptance criteria:

- Given compaction installs replacement history, when metadata is recorded, then
  a compaction window id and token baseline are updated.
- Given a reset starts a new context window without summary, when metadata is
  recorded, then it is reported as reset/new-window behavior, not compaction.
- Given compaction has already installed a carried prefix, when later token
  accounting runs, then policy can count either total active context or growth
  after that prefix.

## Boundaries With Adjacent Specs

### Async session memory pipeline

`async-session-memory-pipeline` owns declarative session identity and
history-retention metadata for future cross-run continuity. It must not own live
pruning, compaction, or prompt-context injection.

This spec may consume current-run `WorkflowExecutionState.session_messages` and
future caller-provided messages, but it does not create a durable session store.

### Internal graph mutation

`internal-graph-mutation` owns internal derived workflow transforms, including a
context-pruning mutation that can render prepared context from declared sources.
This spec owns the general pre-adapter prompt preparation policy and diagnostics.

Graph mutation may produce an input for this prepare stage, but it should not
replace the `prepare_model_input` policy surface.

### Token budgeting

Token budgeting remains a separate preflight and accounting concern. This spec
may use token counts to bound injected context, but it does not redefine token
budget policy or model capability metadata.

### Model adapters

Model adapters remain transport/execution boundaries. They should not implement
context pruning, history compaction, file scanning, hierarchy injection, or
session-memory policy.

## Validation Checklist

- The spec keeps long-term memory and durable replay out of scope.
- The spec identifies `prepare_model_input(...)` as the owning runtime seam.
- The spec covers session pruning, context compaction, and hierarchical
  prompt-context injection.
- The spec distinguishes the general prepare-stage policy from the narrower
  internal graph-mutation context-pruning path.
- The spec gives future expansion a place to grow without changing model
  adapter contracts.

## Future Work

Future approved slices may add:

- turn-level rather than message-level pruning
- summary-generation adapters with explicit model/tool boundaries
- OpenAI/provider-backed remote compaction, including `/responses/compact` when
  available through the configured provider
- automatic pre-turn compaction derived from model context-window metadata
- mid-turn compaction for iterative model-tool loops
- explicit new-context-window reset behavior separate from summarizing
  compaction
- richer retention policies that preserve tool-call/result pairs
- prompt-cache-aware ordering rules
- capability-status reporting that distinguishes available context-management
  policies from metadata-only declarations
- host-provided context packets that are already summarized or ranked

Those future slices should start from this spec and update it before
implementation if their behavior changes these boundaries.
