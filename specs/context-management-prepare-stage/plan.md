# Context Management Prepare Stage Implementation Plan

Status: implemented through Slice 9; Slice 10 planned for pruning-context
injection behavior used by graph mutation

## Goal

Plan the next coherent expansion from the implemented
`prepare_model_input(...)` baseline toward provider-neutral hierarchical
compression while preserving the current separation between prompt preparation,
async-session metadata, graph mutation, and model adapters.

## Spec Trace

- Spec: `specs/context-management-prepare-stage/spec.md`
- Current code anchor: `src/dynamic_agent_runner/executor.py`
- Current test anchor: `tests/test_executor.py`
- Adjacent specs:
  - `specs/async-session-memory-pipeline/spec.md`
  - `specs/internal-graph-mutation/spec.md`
  - `specs/model-adapter-coverage/spec.md`

## Implemented Baseline

Implemented before this expansion:

- hierarchy prompt injection
- bounded current-run session-message pruning
- summary-message insertion for pruned session history
- bounded file-context injection
- prepared-input metadata and `model_input_prepared` diagnostics

Implemented by this plan:

- turn-aware history grouping
- explicit lane-budget prompt assembly
- deterministic older-turn relevance selection
- rolling structured summary folding
- model-derived automatic compaction thresholds
- deterministic basic compaction for local or non-OpenAI models
- manual-vs-automatic compaction modes
- pre-turn automatic summarizing compaction
- mid-turn compaction inside iterative model-tool loops
- explicit new-context-window reset behavior
- lifecycle-stage diagnostics
- segment/turn scoring metadata
- quality and efficiency metrics such as lane utilization, information density,
  redundancy ratio, coverage completeness, and summary fidelity proxies

Still future:

- provider-backed remote compaction, including `/responses/compact` when
  available through the configured provider
- compaction window ids and provider token baselines
- model-backed summary-generation adapters
- richer profile-specific lane priority behavior
- semantic selection through injected collaborators

## Codex Reference Summary

The Codex repo shows a mature design that should guide, not dictate, this
package's implementation:

- derive the automatic compaction threshold from model metadata, defaulting to
  90% of context window and clamping configured limits to that value
- compute token status before model calls and after model responses
- run pre-turn compaction before the next request if the active context is over
  threshold
- run mid-turn compaction only when more model work is needed after a response
- use remote `/responses/compact` when the provider supports it
- fall back to a local summarization turn only when explicitly supported
- advance a compaction window id after replacement history is installed
- track a prefix baseline so policy can count growth after carried context
- keep "new context window without summary" as reset behavior, separate from
  compaction
- record trigger, reason, phase, implementation, status, and token deltas

## Cline Reference Summary

The Cline repo adds provider-neutral and local-model guidance that should shape
the non-OpenAI path:

- expose strategy modes for `basic`, `agentic`, and `off`
- default local/CLI-style compaction to deterministic `basic` truncation
- support `reserve_tokens` as an alternative to threshold-ratio triggers
- separate `auto` compaction from manual host/user-triggered compaction
- protect the latest typed user turn during deterministic compaction
- remove linked tool-call/tool-result pairs atomically
- trim oversized tool-result and file-content blocks before summarization
- fold repeated summaries by carrying prior compaction summary metadata forward
- classify provider context-overflow errors as a later defensive retry signal,
  not as the primary trigger mechanism

## LCWMS Taxonomy Summary

The `llm-context-management-specifications` repo contributes useful vocabulary
for lifecycle, metadata, and metrics, but does not change this package's
ownership boundaries:

- adopt lifecycle names for validate, segment, score, place, select, assemble,
  compress, omit, and report diagnostics
- record stable segment/turn ids, lane assignment, selection status, selection
  reason, importance score, relevance score, and caller-provided access history
  when available
- report quality and efficiency metrics such as lane utilization, information
  density, redundancy ratio, coverage completeness, compression ratio,
  processing duration, and summary fidelity or retention proxies
- keep semantic/vector retrieval as a future injected selector only
- do not adopt runner-owned durable active/working/long-term memory storage

## Delivery Record

### Slice 1 — Policy, turn model, and metadata contract

Status: complete.

Defined the policy shape and datamodel additions without live compaction:

- add normalized automatic compaction policy parsing
- add turn-unit grouping for user/assistant/tool-call/tool-result history
- add lane-budget policy parsing for pinned, current, recent, summary,
  selected older-turn, and file/tool lanes
- add named compression-profile parsing for `balanced`, `fast`, `exact`,
  `semantic`, `recency_weighted`, and `instruction_weighted`
- add lifecycle-stage vocabulary, stable turn/segment ids, scoring metadata,
  and metric field names
- derive thresholds from model capability metadata where available
- add metadata fields for compaction window id, phase, trigger, reason,
  implementation, lane usage, threshold, tokens before/after, quality metrics,
  segment scores, lifecycle stage status, and reset-vs-compaction
- add validation coverage for invalid thresholds and unsupported automatic modes
- add validation coverage for strategy, mode, reserve-token, and
  threshold-ratio policy combinations
- add validation coverage for unsupported profiles and future node-level profile
  overrides

### Slice 2 — Lane-based prompt assembly

Status: complete.

Implemented the preferred compression skeleton before summarization:

- preserve pinned hierarchy and current turn first
- preserve a bounded recent-turn suffix uncompressed
- place rolling summary before recent and selected older turns
- enforce independent lane budgets and lane-utilization metadata
- resolve `balanced`, `fast`, `exact`, `recency_weighted`, and
  `instruction_weighted` profiles into lane priority and ordering behavior
- keep selected older-turn lane empty until Slice 3
- keep rolling summary generation disabled until Slice 4

### Slice 3 — Deterministic older-turn selection

Status: complete.

Added the first relevance-aware retention path without embeddings or live
models:

- select older turns by deterministic overlap with current prompt, file paths,
  symbols, state keys, tool names, error markers, and decision markers
- reassemble selected older turns chronologically
- report selected, rejected, and omitted turn counts, scores, and reasons in
  metadata
- keep an injected selector seam for later semantic selection without adding a
  runner-owned vector or embedding backend
- resolve `semantic` profile behavior through the injected selector seam only

### Slice 4 — Deterministic basic compaction

Status: complete.

Implemented the provider-neutral fallback before live summarization:

- run only before a model call
- preserve the latest typed user turn and protected tool work
- remove tool-call/tool-result pairs atomically
- trim oversized retained tool results and file blocks deterministically
- emit metadata for strategy, mode, trigger, token counts, and trimmed content
- require fake token estimators and fake message histories in tests

### Slice 5 — Rolling summary compaction

Status: complete.

Added summary continuity after lane assembly and deterministic selection are
stable:

- deterministic summarization prompt
- repeated-summary folding from prior compaction summary metadata
- file/source provenance carry-forward
- bounded retained messages/tokens
- deterministic summary placement
- compression ratio and summary fidelity or information-retention proxy
  metadata
- package-owned failure taxonomy
- no live model calls in unit tests

### Slice 6 — Pre-turn compaction seam

Status: complete.

Implemented the safest automatic behavior first:

- run only before a model call
- use an injected compaction function in tests
- install replacement session history only after successful compaction
- recompute token accounting and emit trace diagnostics
- fail closed when compaction is required but no remote compaction capability is
  available

### Slice 7 — Mid-turn iterative-loop compaction

Status: complete.

Added mid-turn behavior only after pre-turn behavior and iterative loops
remained stable:

- trigger after a model response only when additional model work remains
- preserve pending tool-call and approval state
- record `phase: mid_turn`
- reject or stop clearly when mid-turn compaction is unavailable

### Slice 8 — Reset/new-window behavior

Status: complete.

Added explicit reset metadata separate from compaction:

- no summary generation
- replacement with canonical initial context only
- clear trace/status reporting as `reset`, not `compaction`

### Slice 9 — Context-overflow error classification

Status: complete.

Added defensive error handling after pre-turn compaction became available:

- classify provider context-window errors into package-owned reasons
- keep classification separate from retry policy
- make retry-after-compaction opt-in and one-shot only
- preserve original provider error context in diagnostics

### Slice 10 — Pruning-context injection behavior

Status: planned.

Add the prepare-stage behavior needed when graph mutation attaches or inserts
pruning context around eligible `llm_step` interactions. This slice should use
the existing session-message, lane-budget, deterministic selection, rolling
summary, and injected compactor seams before adding new mechanisms.

This slice should:

- consume supplied `WorkflowExecutionState.session_messages`
- prepare bounded context before the target `llm_step` prompt is rendered
- preserve current behavior when no pruning-context policy is enabled
- report included/pruned/compacted/omitted context through redacted diagnostics
- remain independent from durable memory, embedding retrieval, and graph
  attachment mechanics

Use TDD. The first changes should be RED tests in `tests/test_executor.py`; only
add implementation once the expected failure has been observed.

## Design Decisions

- The prepare stage owns prompt shaping; model adapters execute prepared model
  calls.
- Turn-aware lane assembly is the core compression scheme.
- Relevance ranking is only a selection mechanism; final selected-turn order is
  chronological.
- Deterministic overlap selection comes before embedding-backed or model-backed
  semantic selection.
- Remote compaction remains a future provider capability, not an assumed OpenAI
  API surface.
- Deterministic `basic` compaction is the fallback when summary generation is
  unavailable or disabled and must not make live model calls.
- Automatic compaction remains opt-in so callers choose when prepared context
  may be rewritten.
- Pre-turn compaction is the first implementation target because it aligns with
  the existing pre-adapter seam.
- Provider overflow classification is a defensive fallback, not the primary
  trigger for compaction.
- Mid-turn compaction is opt-in and runs only through the injected compactor
  seam when iterative-loop follow-up context crosses policy thresholds.
- Reset/new-window behavior remains separate from summarizing compaction.
- RAG orchestration declares retriever and evidence requirements; this prepare
  stage owns retrieved-context lane packing, budget enforcement, compression,
  omission diagnostics, and final prompt injection.

## Validation Strategy

Focused validation uses fake adapters and injected compactors only:

- `poetry run pytest tests/test_executor.py -q`
- targeted tests for policy normalization, threshold clamping, turn grouping,
  lane budgets, deterministic selection, reserve-token triggers,
  lifecycle-stage diagnostics, scoring metadata, quality metrics, basic
  compaction, pre-turn compaction, trace diagnostics, and failure behavior
- targeted tests for RAG retrieved-context lane assembly using caller-supplied
  fake evidence mappings only
- targeted Slice 10 tests for pruning-context injection from supplied
  `session_messages`

Full validation for completed implementation slices:

- `poetry run pytest -q`
- `poetry check`
- `poetry run ruff check src tests`

No unit test should call live OpenAI, `/responses/compact`, local-model
summarizers, embedding/vector retrieval, or any external provider.
