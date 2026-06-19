# Model-Backed Context Summaries Specification

## Metadata

- Feature slug: `model-backed-context-summaries`
- Mode: `light`
- Artifact type: implemented feature specification
- Status: implemented v1 baseline
- Owner: context-management prepare stage plus caller-supplied summarizer
  adapters
- Primary predecessor:
  - `specs/context-management-prepare-stage/spec.md`
- Related artifacts:
  - `specs/provider-backed-context-compaction/spec.md`
  - `specs/model-adapter-coverage/spec.md`
  - `specs/capability-status-report/spec.md`
  - `src/dynamic_agent_runner/executor.py`
  - `tests/test_executor.py`

## Objective

Add explicit model-backed summary adapters for context compaction when
deterministic `basic` compaction is insufficient and provider-backed remote
compaction is unavailable, disabled, or configured as non-required.

The runtime should own the summary contract, prompt boundaries, diagnostics, and
installation rules. The caller or provider layer should supply the summarizer
adapter.

## Implementation Status

The v1 baseline is implemented in `src/dynamic_agent_runner/executor.py` through
the `context_summarizer` collaborator and `model_summary` compaction strategy.

Completed:

- explicit injected summarizer collaborator
- fail-closed missing-summarizer behavior
- bounded summary output insertion into prepared input
- summary metadata in prepared-input compaction data
- fake summarizer tests with no live model calls

Deferred:

- richer prior-summary folding for model-backed summaries
- source/file/tool provenance diagnostics beyond the current bounded metadata
- explicit fallback-order policy across provider remote compaction, model
  summary, deterministic summary, and fail
- capability/status reporting for missing/live summarizer coverage

## Problem Statement

The current prepare stage can compact deterministically and can fold structured
rolling summaries without making a live model call. That is safe and testable,
but it cannot produce high-quality natural-language summaries of complex older
context.

Adding model-backed summaries directly to the executor without a spec would
blur three boundaries:

- context management decides what needs summarizing and where the summary lands
- model adapters execute model calls but should not invent context policy
- persistent sessions retain bounded state but should not create background
  summary jobs

This feature defines a narrow collaborator model for summarization without
creating runner-owned durable memory or live-model unit tests.

## Scope

This feature covers:

1. a caller-supplied or provider-supplied summarizer collaborator
2. summary prompt templates and input limits
3. summary output validation and placement
4. prior-summary folding across repeated compaction
5. source/file/tool provenance preservation
6. fail-closed behavior for missing or failed summarizers
7. metadata and trace diagnostics
8. fake summarizer tests only

## Non-Goals

This feature must not introduce:

- live model calls in unit tests
- background summarization jobs
- durable memory stores
- automatic session transcript replay
- semantic/vector retrieval
- provider-backed remote compaction; that belongs to
  `provider-backed-context-compaction`
- general evaluation agents or critic loops
- raw summary source transcript in default traces

## Proposed Policy Shape

```yaml
runtime:
  execution_policy:
    prepare_model_input:
      context_compaction:
        strategy: model_summary
        model_summary:
          enabled: true
          summarizer: default
          prompt_template: continuity_summary_v1
          max_source_tokens: 24000
          max_summary_tokens: 2048
          prior_summary_slot: rolling_summary
          source_provenance_slot: source_provenance
          require_summarizer: true
          preserve_tool_pairs: true
```

Names are draft. The first implementation should prefer a compact
package-owned dataclass or protocol over arbitrary callback dictionaries.

## Functional Requirements

### FR1 — Use an Explicit Summarizer Collaborator

Given model-backed summary compaction is enabled, when no matching summarizer
collaborator is supplied, then the runtime must fail closed or use an explicitly
configured fallback. It must not silently call the main model adapter.

### FR2 — Bound Summary Inputs and Outputs

Given older context is selected for summarization, when the runtime invokes the
summarizer, then the source transcript, tool results, file blocks, and prior
summary must be bounded by policy before the summarizer call.

Given the summarizer returns content, then the runtime must validate maximum
summary size before inserting it into prepared input.

### FR3 — Preserve Prior Summary and Provenance

Given a prior summary exists, when a new summary is generated, then the runtime
must fold the prior summary forward as summary context rather than treating it
as raw transcript.

Given source provenance exists, then the summary metadata must retain safe
provenance handles without copying raw file content into traces.

### FR4 — Preserve Active Turn and Tool Safety

Given the latest user turn, pending tool state, or approval state exists, when
summary compaction runs, then the runtime must preserve those active boundaries
outside the summary or fail closed.

### FR5 — Report Summary Quality Proxies

Given model-backed summarization succeeds, when metadata is inspected, then the
runtime should report non-sensitive quality and efficiency proxies such as
source token count, summary token count, compression ratio, retained turn count,
provenance count, and summary strategy.

## Acceptance Criteria

- Missing summarizer behavior is explicit and tested.
- The main workflow model is not used as an implicit summarizer.
- Summary source material and output are bounded.
- Prior summaries fold forward without recursive raw transcript growth.
- Summary insertion is represented in `PreparedInputMetadata` and
  `model_input_prepared` traces without raw transcript leakage.
- Tool-call/result pairing and current-turn protection are preserved.

## Implementation Planning Notes

- Start with tests extending the current rolling-summary and basic-compaction
  coverage in `tests/test_executor.py`.
- Consider a small `ContextSummaryAdapter` protocol with sync and async support
  only if async execution needs it in the first slice.
- Keep provider-specific summary models behind caller configuration or adapter
  injection.
- Coordinate with `provider-backed-context-compaction` so fallback order is
  explicit: provider remote, model summary, basic, or fail.

## Validation Checklist

Implemented v1 validation includes:

- validation tests for `model_summary` policy shape
- tests proving no live provider/model calls are made
- executor tests for successful injected summarization and missing summarizer
  failure

Deferred validation should include:

- failed summarizer, oversized source, oversized summary, richer prior-summary
  folding, and provenance retention tests
- trace redaction tests
- capability/status tests for missing/live summarizer coverage

Relevant commands:

```bash
poetry run pytest \
  tests/test_validation.py tests/test_executor.py -q
poetry run ruff check src tests
```

## Open Questions

- Should summary adapters be registered separately from model adapters, or can a
  model adapter opt into a summary capability through metadata?
- Should model-backed summaries run inside `prepare_model_input(...)`, or should
  long-running summaries become an explicit graph operation in a later
  structural graph-mutation slice?
- Should summary quality checks be local heuristics only in v1, or should
  evaluator/critic models require a separate feature spec?
