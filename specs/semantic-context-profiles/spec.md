# Semantic Context Profiles Specification

## Metadata

- Feature slug: `semantic-context-profiles`
- Mode: `light`
- Artifact type: partially implemented feature specification
- Status: implemented through Slice S1; richer profile behavior deferred
- Owner: context-management prepare stage plus caller-supplied selectors
- Primary predecessor:
  - `specs/context-management-prepare-stage/spec.md`
- Related artifacts:
  - `specs/rag-orchestration-contract/spec.md`
  - `specs/internal-graph-mutation/spec.md`
  - `specs/model-backed-context-summaries/spec.md`
  - `specs/capability-status-report/spec.md`
  - `src/dynamic_agent_runner/executor.py`
  - `tests/test_executor.py`

## Objective

Define richer context compression profiles and semantic selection behavior for
the prepare stage without making the runner own embeddings, vector stores,
semantic memory, or retrieval infrastructure.

The runtime should expose stable policy names and diagnostics, while callers
provide semantic selectors or retrieved/context packets when semantic ranking is
needed.

## Problem Statement

The implemented prepare stage supports named profile values, deterministic
older-turn selection, exact/hybrid identifier preservation, and injected
semantic older-turn selection. Richer profile-specific behavior remains
intentionally deferred:

- `semantic` should use caller-supplied semantic signals, not built-in vector
  retrieval
- `recency_weighted` and `instruction_weighted` should alter scoring and lane
  priority in auditable ways
- exact identifiers and high-priority constraints should not be lost in purely
  semantic scoring
- retrieved RAG evidence and session history need predictable lane interaction

This feature makes those policy meanings explicit while tracking the partial v1
implementation now present in the prepare stage.

## Implementation Status

The partial v1 baseline and Slice S1 are implemented in
`src/dynamic_agent_runner/executor.py`, with the public selector contract in
`src/dynamic_agent_runner/context_selection.py`.

Completed:

- exact-token preservation for issue keys, filenames, tool ids, function names,
  quoted strings, and similar identifiers
- `hybrid_exact_semantic` selection-policy support
- `injected_semantic` selection-policy support through caller-supplied
  `ContextSelector`
- direct execution and `WorkflowExecutionContext` support for
  `context_selector`
- missing-selector fallback to deterministic overlap with visible metadata
- exact identifier protection before injected semantic scores
- retrieved RAG evidence exclusion from selector candidate inputs
- selected/omitted/rejected metadata for older-turn selection
- tests proving exact identifier preservation, injected selection,
  missing-selector fallback, RAG lane separation, execution-context threading,
  and public exports

Deferred:

- profile-specific lane priority for `recency_weighted` and
  `instruction_weighted`
- memory-kind hints, access-frequency scoring, stale/redundant omission, and
  prompt-cache-aware ordering
- RAG lane borrowing policies beyond existing retrieved-context lane packing
- capability/status reporting for semantic selector availability and fallback
  remains deferred until a concrete caller needs preflight visibility

## Implemented Slice S1

Slice S1 implemented a small fake-testable selector seam for older-turn
selection while preserving the exact/hybrid identifier baseline and keeping
embeddings, vector stores, memory stores, and retrieval infrastructure out of
DAR.

Implemented scope:

1. Added an injected semantic context selector collaborator for
   `prepare_model_input(...)` older-turn selection.
2. Supported `context_compression.selection.strategy: injected_semantic` through
   the injected selector only.
3. Reported selector status, fallback path, selected/omitted/rejected counts, and
   bounded scoring hints in prepared-input metadata.
4. Preserved exact identifiers and required current/pinned lanes before semantic
   ranking.
5. Kept retrieved RAG evidence in the existing retrieved-context lane and out of
   selector candidate inputs.

Out of scope for S1:

- runner-owned embeddings, vector stores, graph stores, or memory stores
- live retriever, model, or embedding calls in unit tests
- memory-kind labels, access-frequency scoring, stale/redundant omission, RAG
  lane borrowing, and prompt-cache-aware ordering
- capability/status reporting for selector availability unless the
  implementation can reuse existing capability report plumbing without a second
  report type

Implementation artifacts:

- [`plan.md`](plan.md)
- [`tasks.md`](tasks.md)
- [`validation.md`](validation.md)

## Scope

This feature covers:

1. profile-specific lane priority and scoring semantics
2. caller-supplied semantic selector contracts
3. exact-plus-semantic hybrid selection rules
4. optional memory-kind labels such as semantic, episodic, procedural, and
   source-context as selection hints
5. access-frequency, recency, and last-selected metadata as optional scoring
   inputs
6. redundant/stale context omission policy
7. prompt-cache-aware ordering rules where available from model metadata
8. diagnostics for included, selected, omitted, rejected, and trimmed context

## Non-Goals

This feature must not introduce:

- runner-owned embedding models
- runner-owned vector databases or graph stores
- background memory indexing
- automatic long-term memory creation
- provider-backed remote compaction
- model-backed summary generation
- public graph-mutation schemas
- live retriever or embedding calls in unit tests

## Proposed Policy Shape

```yaml
runtime:
  execution_policy:
    prepare_model_input:
      context_compression:
        enabled: true
        profile: semantic
        lanes:
          pinned_tokens: 2048
          current_turn_tokens: 8192
          recent_turn_tokens: 12000
          selected_turn_tokens: 20000
          retrieved_context_tokens: 16000
        selection:
          strategy: hybrid_exact_semantic
          selector: default
          max_selected_turns: 12
          protect_exact_matches: true
          chronological_reassembly: true
          stale_context_policy: omit_redundant
          prompt_cache_ordering: preserve_prefix
```

Names are draft. The first implementation should keep policy small and add
profile behavior only where tests prove a visible difference.

## Profile Semantics

### `balanced`

Default profile. Preserve pinned instructions, current turn, recent turns, and
retrieved evidence before selecting older turns. Use deterministic scoring when
no selector is supplied.

### `fast`

Prefer deterministic recency and simple overlap scoring. Do not call semantic
selectors or summarizers.

### `exact`

Protect exact identifiers, file names, quoted strings, tool ids, issue keys,
function names, and caller-marked constraints before semantic scoring.

### `semantic`

Use a caller-supplied selector for relevance scoring. If no selector is
available, fail closed in strict mode or degrade to `balanced` with capability
metadata.

### `recency_weighted`

Bias toward newer turns while still allowing older exact matches and
caller-marked durable constraints to survive.

### `instruction_weighted`

Bias toward developer/system constraints, explicit user requirements, safety
instructions, and output contract details.

## Functional Requirements

### FR1 — Keep Semantic Selection Injected

Given the `semantic` profile is configured, when semantic ranking is required,
then the runtime must use a caller-supplied selector. It must not create or call
an embedding backend by default.

### FR2 — Preserve Exact and Required Context

Given exact identifiers, pinned instructions, current-turn state, or
caller-marked required context exists, when profile scoring runs, then those
items must be protected before optional semantic or recency scoring.

### FR3 — Report Profile Decisions

Given profile-specific selection changes prepared input, when metadata is
inspected, then the runtime must report profile, strategy, selector status,
included counts, omitted counts, rejection reasons, and scoring hints without
raw context leakage.

### FR4 — Compose with RAG Evidence

Given caller-owned RAG metadata supplies retrieved context, when semantic
profile selection runs, then retrieved evidence must stay in its lane and must
not be silently mixed with session transcript scoring unless policy explicitly
allows cross-lane borrowing.

### FR5 — Support Prompt-Cache-Aware Ordering

Given model metadata or caller policy indicates prompt-cache-sensitive ordering,
when context lanes are assembled, then stable pinned prefixes should be
preserved before variable selected context where that does not violate current
turn or safety constraints.

## Acceptance Criteria

- Profile names map to documented behavior.
- Missing semantic selector behavior is explicit and tested.
- Exact matches and required context survive semantic scoring.
- RAG evidence, file context, and session history remain separate lanes unless
  policy allows borrowing.
- Metadata reports profile decisions and degradation paths.
- Unit tests use fake selectors and no embedding/vector backends.

## Implementation Planning Notes

- Start with RED tests that prove `semantic` plus an injected selector can select
  an older turn with low lexical overlap, and that missing selector behavior is
  explicit in metadata.
- Add a tiny selector protocol only for older-turn scoring.
- Keep selector input redacted or bounded; selectors should receive structured
  candidates, not arbitrary internal executor state.
- Treat profile behavior as context-management policy, not graph mutation.

## Validation Checklist

Implemented partial-v1 validation includes:

- validation tests for supported profile and selection policy values
- tests for exact identifier preservation
- Slice S1 executor tests for injected selector behavior and missing-selector
  fallback diagnostics
- fake semantic-selector tests for selected/omitted/rejected diagnostics
- execution-context and direct-kwarg tests for `context_selector`
- RAG lane composition tests proving retrieved context is not passed to the
  selector
- import tests for public selector contract exports

Deferred validation should include:

- capability/status tests for semantic selector live, missing, fallback, and
  disabled states in a later slice only if selector availability becomes
  preflightable

Relevant commands:

```bash
poetry run pytest \
  tests/test_validation.py tests/test_executor.py -q
poetry run ruff check src tests
```

## Open Questions

- Resolved for Slice S1: semantic selector collaborators should use a
  context-management-specific injected callable/protocol, not the tool registry
  or RAG retriever registry.
- Should prompt-cache-aware ordering be its own later feature if provider/model
  metadata becomes complex?
- Should memory-kind labels be accepted only from caller-supplied context
  packets, or can session messages carry those labels too?
