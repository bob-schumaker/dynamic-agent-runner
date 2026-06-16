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
  - `/Users/roschuma/Repos/github/cline/sdk/packages/core/src/extensions/context/compaction.ts`
  - `/Users/roschuma/Repos/github/cline/sdk/packages/core/src/extensions/context/basic-compaction.ts`
  - `/Users/roschuma/Repos/github/cline/sdk/packages/core/src/extensions/context/agentic-compaction.ts`
  - `/Users/roschuma/Repos/github/cline/sdk/packages/core/src/extensions/context/compaction-shared.ts`
  - `/Users/roschuma/Repos/github/cline/sdk/packages/core/src/types/config.ts`
  - `/Users/roschuma/Repos/github/cline/apps/vscode/src/core/context/context-management/context-error-handling.ts`
  - `/Users/roschuma/Repos/github/llm-context-management-specifications/specifications/llm-context-management-spec.md`
  - `/Users/roschuma/Repos/github/llm-context-management-specifications/research/current-techniques.md`
  - `/Users/roschuma/Repos/github/llm-context-management-specifications/examples/basic_context_manager.py`
- Evaluated context-management survey notes:
  - `Strategies and Techniques for Managing Context Windows.md`
  - `Top techniques to Manage Context Lengths in LLMs.md`

## Objective

Define the package-owned context-management prepare stage that runs before a
model adapter call and owns provider-neutral prompt construction for long
sessions:

- session pruning
- context compaction
- hierarchical prompt-context injection
- relevance-aware prompt-context selection
- rolling summary continuity

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
7. turn-aware prompt assembly that preserves atomic tool-call/result structure
8. budget lanes for pinned context, current turn, recent turns, rolling summary,
   selected older turns, and bounded file/tool context
9. relevance-aware selection of older turns with chronological reassembly
10. future automatic context-window compaction triggered by model token usage
    and context-window metadata
11. future deterministic non-LLM compaction for constrained models
12. future separation of summarizing compaction from explicit new-window reset
    behavior

## Non-Goals

This feature must not introduce:

- runner-owned durable session storage
- cross-run transcript replay
- runner-owned vector memory, embedding search, or semantic retrieval backends
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
      context_compression:
        enabled: true
        trigger:
          threshold_ratio: 0.9
          reserve_tokens: 16384
        lanes:
          pinned_tokens: 2048
          current_turn_tokens: 8192
          recent_turn_tokens: 32768
          summary_tokens: 4096
          selected_turn_tokens: 16384
          file_context_tokens: 2048
        selection:
          strategy: deterministic_overlap
          max_selected_turns: 8
          chronological_reassembly: true
        rolling_summary:
          enabled: true
          max_tokens: 4096
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

## Recommended Compression Architecture

The preferred implementation is provider-neutral hierarchical compression, not
simple truncation and not whole-transcript summarization. The target model is:

1. normalize history into atomic turns
2. validate and score turn/lane candidates
3. reserve explicit token budget lanes
4. preserve pinned hierarchy and the current turn first
5. preserve a bounded recent-turn suffix uncompressed
6. carry a rolling structured summary for older work
7. select older relevant turns before summarizing the remainder
8. reassemble selected older turns chronologically before final prompt rendering
9. trim oversized tool/file blocks deterministically as a final fallback

### Atomic turn model

Compression must operate on turn units before it operates on individual
messages. A turn may include the user request, assistant response, model-emitted
tool calls, tool results, and related retry/error records. Tool-call/result
pairs are atomic: any policy that cannot preserve a valid pair must leave the
pair out or fail closed.

### Budget lanes

The prepared prompt should be assembled from explicit lanes with independent
budgets:

- pinned hierarchy: system/developer/package context
- current turn: the latest user prompt and in-progress tool/approval state
- recent turns: a bounded uncompressed suffix
- rolling summary: structured continuity for compacted older turns
- selected older turns: relevant older turns selected for the current prompt
- file/tool context: bounded source material and tool outputs with provenance

Lane metadata must report requested, estimated, included, trimmed, and omitted
token counts where practical.

Lane policy should distinguish required context from optional context. Pinned
hierarchy, the current user request, in-progress tool/approval state, and
provider-required message structure are required lanes. Recent turns, selected
older turns, rolling summaries, examples, and file/tool context are optional or
degradable lanes unless a future policy marks them required. Required lanes are
not candidates for lossy trimming; optional lanes are candidates for selection,
compression, omission, or exact bounded inclusion.

Reserve-token policy should be treated as output and continuation headroom, not
as vague unused space. Future automatic compression must account for the fact
that input tokens, model output tokens, and any provider/tool-call overhead
share the same context window.

Prompt ordering should account for primacy, recency, and lost-in-the-middle
risk. The default lane order preserves stable instructions early, keeps current
turn state late, and avoids burying the highest-value selected context in the
middle of large low-priority blocks.

### Lifecycle stages

Prepared-input diagnostics should use stable lifecycle stage names so future
implementations can be compared without leaking prompt content:

- validate
- segment
- score
- place
- select
- assemble
- compress
- omit
- report

Each stage may report status, reason, duration, counts, and non-sensitive
policy identifiers. Stage names are a diagnostic vocabulary, not a requirement
to split implementation into separate public APIs.

### Segment and turn metadata

Normalized turns and injected context segments should carry stable metadata
where practical:

- segment or turn id
- source kind and source path when applicable
- lane assignment
- importance score when policy or caller input provides one
- relevance score when selection computes one
- selection reason
- access count or last-selected timestamp when supplied by caller-provided
  history
- compression ratio and summary fidelity/retention proxy when compression runs

The runtime may compute deterministic scores locally. It must not create a
runner-owned durable memory store to maintain access history.

### Rolling structured summary

Summarization should maintain a structured continuation note rather than a free
form transcript digest. Required summary sections are:

- goal
- current state
- completed work
- decisions and constraints
- files read or modified
- tool outcomes
- open questions or blockers
- next steps

Repeated compaction should fold only newly evicted turns into the existing
summary. The runtime must not repeatedly summarize the same prior summary as raw
history.

### Relevance-aware older-turn selection

Before older turns are summarized or omitted, the prepare stage should select
older turns that are relevant to the current prompt. The first implementation
should be deterministic: path overlap, symbol/name overlap, tool-name overlap,
state-key overlap, explicit mention overlap, and recent error/decision markers.
Embedding-backed or model-backed selectors may be added later only through an
injected selector boundary.

Selected older turns must be reassembled chronologically. Relevance ranking is a
selection mechanism, not the final prompt order.

### Quality and efficiency metrics

Context management should report a small metric vocabulary for tuning and
regression tests:

- lane utilization
- information density
- redundancy ratio
- coverage completeness
- compression ratio
- summary fidelity or information-retention proxy
- processing duration
- memory overhead where practical

These metrics are best-effort diagnostics unless a future slice defines exact
calculation rules. Unit tests should verify presence and monotonic behavior for
implemented metrics rather than relying on live model judgment.

Validation should include overflowing-history fixtures that compare strategies
such as deterministic truncation, lane-based selection, rolling summary, exact
retrieval through injected selectors, and fallback compaction. Passing a token
limit is not sufficient; validation should also check whether required facts,
decisions, constraints, and current-turn state survive prompt preparation.

### Deterministic fallback trimming

If the assembled prompt remains over budget, the runtime should trim in this
order:

1. oversized tool-result and file-content blocks
2. lowest-priority selected older turns
3. oldest recent turns beyond the protected suffix
4. summary detail below the required structured headings

The runtime must preserve pinned hierarchy, current turn state, valid tool
pairs, and explicit diagnostics.

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

## Cline Non-OpenAI Compaction Findings

The local Cline repository provides a useful reference for provider-neutral and
local-model context management. The design points below are treated as
requirements input for future slices, not as current implementation evidence in
this package.

### Strategy modes

Cline separates compaction into explicit strategies:

- `basic`: deterministic truncation with no summarizer call
- `agentic`: LLM-backed summarization using a configured provider/model
- `off`: explicit disablement

For this package, future policy should distinguish deterministic `basic`
compaction from summarizing compaction. `basic` is the safer non-OpenAI/local
model fallback because it does not require `/responses/compact`, a live
summarizer, or provider-specific summary support.

### Reserve-token triggers

Cline supports both a threshold ratio and a reserved-token trigger. If
`reserveTokens` is configured, the trigger is `maxInputTokens - reserveTokens`;
otherwise it defaults through a 90% threshold with a conservative output
reserve.

For this package, future automatic compaction should support a reserve-token
policy alongside ratio-based thresholds. Workflow overrides may narrow the
usable input budget, but must not silently expand past model capability
metadata.

### Manual and automatic modes

Cline distinguishes automatic compaction from manual compaction. Manual
compaction can use a more aggressive target ratio while still using the same
strategy machinery and diagnostics.

For this package, manual compaction should be modeled separately from automatic
context-pressure compaction. Manual compaction is user/host-triggered
preparation, not proof that the runtime detected an overflow risk.

### Tool-pair safety

Cline's deterministic compaction preserves message validity by removing
linked `tool_use` and `tool_result` messages atomically. It also protects the
latest typed user turn and its tool work so an in-progress turn is not broken.

For this package, any deterministic or summarizing compaction must preserve
tool-call/result pairing. Compaction must fail closed or leave history
unchanged rather than creating orphaned provider messages.

### Oversized tool-result trimming

Cline truncates large tool-result text and file blocks before either basic
compaction or agentic summarization. This prevents a single huge tool result
from dominating the context window or the summarization request.

For this package, future compaction should include bounded tool-result and
file-content trimming as a deterministic preprocessing step with metadata.

### Summary folding

Cline's agentic compaction detects the latest prior compaction summary and
folds only newer messages into the next summary. It also extracts file read and
modified paths so summaries retain operational context.

For this package, repeated summarizing compaction should merge prior summary
metadata and carry file/source provenance forward instead of repeatedly
summarizing already-compacted history as raw transcript.

### Overflow error classification

Cline has provider-specific context-window error detection across OpenAI,
OpenRouter, Anthropic, Cerebras, Bedrock, Vercel-wrapped providers, and related
400-error shapes.

For this package, overflow-error classification should be a defensive later
slice. It may support one retry after compaction, but first-pass behavior should
remain preflight/pre-turn compaction rather than relying on provider failures.

## LCWMS Taxonomy Findings

The `llm-context-management-specifications` repository is useful as a taxonomy
for lifecycle, metadata, and metrics. It is not adopted as this package's
storage architecture.

The useful additions are:

- lifecycle names for validation, segmentation, scoring, placement, retrieval
  or selection, assembly, compression, eviction or omission, and reporting
- segment metadata for ids, source metadata, timestamps, relevance scoring,
  access counts, and compression ratios
- quality metrics such as information retention, semantic similarity,
  structural preservation, key-concept coverage, coherence, and relevance
- efficiency metrics such as compression ratio, processing time, memory
  overhead, context utilization, information density, redundancy ratio, and
  coverage completeness

The three-tier active/working/long-term memory model is intentionally not
adopted here because this feature must not own durable storage. Semantic or
vector retrieval remains a future injected selector boundary only; the runner
must not create or call a built-in embedding/vector backend as part of prompt
preparation.

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

### FR2 — Prune session history at turn granularity

The prepare stage must be able to group current-run session history into
turn-like atomic units before pruning or compression.

Acceptance criteria:

- Given session history contains user messages, assistant messages, tool calls,
  and tool results, when input is prepared, then the runtime identifies
  protected atomic turns before dropping or trimming content.
- Given a retention bound applies, when input is prepared, then retained and
  pruned history is counted by turn as well as by message.
- Given pruning would split a tool-call/result pair, when input is prepared,
  then the runtime keeps the pair together, omits the pair together, or fails
  closed.

### FR3 — Maintain rolling structured summary continuity

The prepare stage may convert pruned or evicted older turns into an explicit
model-visible rolling summary only when policy asks for compaction.

Acceptance criteria:

- Given older turns are evicted and compaction is enabled, when input is
  prepared, then a structured summary part is inserted before retained session
  history.
- Given a previous compaction summary exists, when new turns are compacted, then
  the runtime folds only newly evicted turns into the summary.
- Given no turns were pruned or evicted, when input is prepared, then
  compaction must not fabricate a summary.
- Given compaction is applied, when metadata is inspected, then compaction is
  recorded explicitly with source-turn counts and summary provenance.

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
- Given lifecycle diagnostics are emitted, when metadata is inspected, then
  stage names use the stable validate, segment, score, place, select, assemble,
  compress, omit, and report vocabulary.
- Given lane or compression metrics are computed, when traces are emitted, then
  they include non-sensitive quality and efficiency metrics such as lane
  utilization, compression ratio, information density, redundancy ratio,
  coverage completeness, and summary fidelity/retention proxies.
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

### FR9 — Treat provider compaction as an optional capability

Automatic compaction may use a provider-owned compaction capability when
available, but provider compaction is an optimization rather than the core
compression scheme.

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

### FR11 — Provide deterministic basic compaction for non-OpenAI models

The prepare stage should support a deterministic compaction strategy that
reduces context without calling a summarizer.

Acceptance criteria:

- Given a non-OpenAI or local model lacks provider-backed compaction, when
  `basic` compaction is enabled and context exceeds the trigger, then the
  runtime reduces older context without making a live model call.
- Given history contains tool calls and tool results, when deterministic
  compaction removes any part of a pair, then it removes the linked pair
  atomically or fails closed.
- Given a latest typed user turn exists, when deterministic compaction runs,
  then that turn and its associated tool work remain protected.
- Given a retained tool result or file-content block exceeds configured bounds,
  when compaction prepares messages, then that block is trimmed with metadata
  rather than silently copied in full.

### FR12 — Distinguish compaction trigger modes

Compaction policy should distinguish automatic context-pressure compaction from
manual host/user-triggered compaction.

Acceptance criteria:

- Given automatic compaction is enabled, when token usage exceeds a ratio or
  reserve-token trigger, then metadata records `mode: auto` and the trigger
  source.
- Given manual compaction is requested, when compaction runs, then metadata
  records `mode: manual` and does not report an automatic overflow trigger.
- Given both `threshold_ratio` and `reserve_tokens` are configured, when policy
  is normalized, then precedence is deterministic and represented in metadata.

### FR13 — Classify context-overflow errors defensively

Provider context-overflow errors should be classified explicitly before any
retry behavior is added.

Acceptance criteria:

- Given a provider returns a structured or text-only context-window overflow
  error, when the runtime handles the failure, then it classifies the failure
  with a package-owned reason without losing the original error context.
- Given retry-after-compaction is enabled in a future slice, when the first
  provider call fails with a classified overflow, then the runtime may compact
  once and retry once.
- Given the retry also fails, when the runtime reports the error, then it must
  not loop or silently drop more history.

### FR14 — Assemble prompt context from budget lanes

The prepare stage must construct model input from explicit context lanes rather
than from a single undifferentiated transcript budget.

Acceptance criteria:

- Given context compression is enabled, when input is prepared, then the runtime
  allocates separate budgets for pinned hierarchy, current turn, recent turns,
  rolling summary, selected older turns, and file/tool context.
- Given one lane exceeds its configured budget, when input is prepared, then
  the runtime trims or omits that lane without silently consuming another lane's
  budget unless policy allows borrowing.
- Given prepared-input metadata is inspected, then each lane reports included,
  omitted, trimmed, and estimated token counts where practical.

### FR15 — Select relevant older turns before summarizing the rest

The prepare stage should retain older turns that are relevant to the current
prompt before falling back to summary-only continuity.

Acceptance criteria:

- Given older turns mention paths, symbols, state keys, tools, errors, or
  decisions related to the current prompt, when relevance selection is enabled,
  then the runtime may include those turns in the selected older-turn lane.
- Given selected older turns are ranked out of chronological order, when final
  prompt messages are assembled, then selected turns are reassembled
  chronologically.
- Given no selector backend is configured, when selection runs, then the runtime
  uses deterministic overlap rules only and makes no live model or embedding
  call.
- Given a future injected selector is configured, when it selects older turns,
  then its selected turn ids and scores are reflected in metadata without
  exposing sensitive prompt content in traces.

### FR16 — Record segment lifecycle and scoring metadata

The prepare stage should make segment and turn handling inspectable without
requiring callers to reconstruct pruning decisions from rendered prompt text.

Acceptance criteria:

- Given input is prepared, when metadata is inspected, then normalized turns and
  injected context segments have stable ids, lane assignments, and selection
  status where practical.
- Given policy or caller-provided history includes importance, relevance,
  access-count, or last-selected metadata, when selection runs, then those
  values are preserved or incorporated without creating runner-owned durable
  storage.
- Given deterministic selection computes relevance, when metadata is emitted,
  then selected and omitted turns include non-sensitive scores or reasons.
- Given compression runs, when metadata is emitted, then compression ratio and
  summary fidelity or information-retention proxy fields are reported where
  practical.
- Given no semantic selector is injected, when older-turn selection runs, then
  no live embedding, vector search, or model-backed retrieval call occurs.

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

### Model routing

Routing to a larger context-window model can preserve full context without
compression, but it is a model-selection concern rather than prompt-preparation
ownership. This spec may report when prepared context exceeds the current
model's safe budget; it must not silently swap the selected model.

### Retrieval and exact context

RAG, vector search, and exact retrieval can be useful for large document or
regulated workflows, especially when summarization would risk losing
source-critical wording. This spec may consume host-provided or injected
retrieval results as bounded prompt-context segments, but it must not own
embedding, indexing, vector storage, or durable retrieval infrastructure.

### Model adapters

Model adapters remain transport/execution boundaries. They should not implement
context pruning, history compaction, file scanning, hierarchy injection, or
session-memory policy.

## Validation Checklist

- The spec keeps long-term memory and durable replay out of scope.
- The spec identifies `prepare_model_input(...)` as the owning runtime seam.
- The spec covers session pruning, context compaction, and hierarchical
  prompt-context injection.
- The spec identifies turn-aware lane budgeting, rolling summaries, and
  relevance-aware older-turn selection as the preferred compression scheme.
- The spec adopts lifecycle, scoring, and metrics vocabulary without adopting
  runner-owned durable memory or vector storage.
- The spec distinguishes the general prepare-stage policy from the narrower
  internal graph-mutation context-pruning path.
- The spec gives future expansion a place to grow without changing model
  adapter contracts.

## Future Work

Future approved slices may add:

- turn-level rather than message-level pruning
- explicit lane-budget policy and metadata
- deterministic older-turn relevance selectors
- injected semantic selectors behind fake-only unit tests
- lifecycle-stage diagnostics, segment scoring metadata, and quality/efficiency
  metrics
- required-vs-optional lane policy and lost-in-the-middle-aware ordering
- overflowing-history evaluation fixtures that check retained facts, decisions,
  constraints, and current-turn state, not just final token counts
- summary-generation adapters with explicit model/tool boundaries
- OpenAI/provider-backed remote compaction, including `/responses/compact` when
  available through the configured provider
- deterministic `basic` compaction for non-OpenAI and local models
- automatic pre-turn compaction derived from model context-window metadata
- mid-turn compaction for iterative model-tool loops
- explicit new-context-window reset behavior separate from summarizing
  compaction
- richer retention policies that preserve tool-call/result pairs
- provider context-overflow error classification with at most one explicit
  compaction/retry path
- prompt-cache-aware ordering rules
- capability-status reporting that distinguishes available context-management
  policies from metadata-only declarations
- host-provided context packets that are already summarized or ranked

Those future slices should start from this spec and update it before
implementation if their behavior changes these boundaries.
