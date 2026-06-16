# Context Management Prepare Stage Implementation Plan

Status: planning artifact created; no implementation is authorized by this
artifact alone

## Goal

Plan the next coherent expansion from the implemented
`prepare_model_input(...)` baseline toward OpenAI-focused automatic
context-window compaction while preserving the current separation between
prompt preparation, async-session metadata, graph mutation, and model adapters.

## Spec Trace

- Spec: `specs/context-management-prepare-stage/spec.md`
- Current code anchor: `src/dynamic_agent_runner/executor.py`
- Current test anchor: `tests/test_executor.py`
- Adjacent specs:
  - `specs/async-session-memory-pipeline/spec.md`
  - `specs/internal-graph-mutation/spec.md`
  - `specs/model-adapter-coverage/spec.md`

## Current Baseline

Already implemented:

- hierarchy prompt injection
- bounded current-run session-message pruning
- summary-message insertion for pruned session history
- bounded file-context injection
- prepared-input metadata and `model_input_prepared` diagnostics

Not implemented:

- model-derived automatic compaction thresholds
- provider-backed remote compaction
- compaction window ids or token baselines
- pre-turn automatic summarizing compaction
- mid-turn compaction inside iterative model-tool loops
- explicit new-context-window reset behavior

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

## Delivery Strategy

### Slice 1 — Policy and metadata contract

Define the policy shape and datamodel additions without live compaction:

- add normalized automatic compaction policy parsing
- derive thresholds from model capability metadata where available
- add metadata fields for compaction window id, phase, trigger, reason,
  implementation, threshold, tokens before/after, and reset-vs-compaction
- add validation coverage for invalid thresholds and unsupported automatic modes

### Slice 2 — Pre-turn remote compaction seam

Implement the safest automatic behavior first:

- run only before a model call
- use an injected/provider-owned remote compaction function in tests
- install replacement session history only after successful compaction
- recompute token accounting and emit trace diagnostics
- fail closed when compaction is required but no remote compaction capability is
  available

### Slice 3 — Local summarization fallback

Add explicit local fallback only after remote compaction is stable:

- deterministic summarization prompt
- bounded retained messages/tokens
- deterministic summary placement
- package-owned failure taxonomy
- no live model calls in unit tests

### Slice 4 — Mid-turn iterative-loop compaction

Add mid-turn behavior only after pre-turn behavior and iterative loops remain
stable:

- trigger after a model response only when additional model work remains
- preserve pending tool-call and approval state
- record `phase: mid_turn`
- reject or stop clearly when mid-turn compaction is unavailable

### Slice 5 — Reset/new-window behavior

If needed, add an explicit reset policy or tool separate from compaction:

- no summary generation
- replacement with canonical initial context only
- clear trace/status reporting as `reset`, not `compaction`

## Design Decisions

- The prepare stage owns prompt shaping; model adapters execute prepared model
  calls.
- Remote compaction is a provider capability, not an assumed OpenAI API surface.
- Automatic compaction should be opt-in until capability/status reporting can
  make live support visible.
- Pre-turn compaction is the first implementation target because it aligns with
  the existing pre-adapter seam.
- Mid-turn compaction is deferred because it interacts with iterative loops,
  tool calls, and approval interruption.
- Reset/new-window behavior remains separate from summarizing compaction.

## Validation Strategy

Focused validation should use fake adapters and injected compactors only:

- `poetry run pytest tests/test_executor.py -q`
- targeted future tests for policy normalization, threshold clamping,
  pre-turn compaction, trace diagnostics, and failure behavior

Full validation before a future implementation commit:

- `poetry run pytest -q`
- `poetry check`
- `poetry run ruff check src tests`

No unit test should call live OpenAI, `/responses/compact`, or any external
provider.
