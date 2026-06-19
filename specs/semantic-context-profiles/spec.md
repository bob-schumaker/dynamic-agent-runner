# Semantic Context Profiles Specification

## Metadata

- Feature slug: `semantic-context-profiles`
- Mode: `light`
- Artifact type: partially implemented feature specification
- Status: partial v1 baseline; richer semantic selectors deferred
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

The implemented prepare stage already supports named profile values and
deterministic older-turn selection. The names exist, but richer
profile-specific behavior remains intentionally deferred:

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

The partial v1 baseline is implemented in `src/dynamic_agent_runner/executor.py`
for exact and `hybrid_exact_semantic` older-turn selection.

Completed:

- exact-token preservation for issue keys, filenames, tool ids, function names,
  quoted strings, and similar identifiers
- `hybrid_exact_semantic` selection-policy support
- selected/omitted/rejected metadata for older-turn selection
- tests proving exact identifier preservation

Deferred:

- injected semantic selector collaborator
- profile-specific lane priority for `semantic`, `recency_weighted`, and
  `instruction_weighted`
- memory-kind hints, access-frequency scoring, stale/redundant omission, and
  prompt-cache-aware ordering
- RAG lane borrowing policies beyond existing retrieved-context lane packing
- capability/status reporting for semantic selector availability and fallback

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

- Start with RED tests that prove `balanced`, `fast`, `exact`, and `semantic`
  produce different selected/omitted metadata on the same fixture.
- Add a tiny selector protocol only when tests require semantic scoring.
- Keep selector input redacted or bounded; selectors should receive structured
  candidates, not arbitrary internal executor state.
- Treat profile behavior as context-management policy, not graph mutation.

## Validation Checklist

Implemented partial-v1 validation includes:

- validation tests for supported profile and selection policy values
- tests for exact identifier preservation

Deferred validation should include:

- executor tests for each profile's visible behavior
- fake semantic-selector tests for selected/omitted diagnostics
- RAG lane composition tests
- capability/status tests for semantic selector live, missing, fallback, and
  disabled states

Relevant commands:

```bash
poetry run pytest \
  tests/test_validation.py tests/test_executor.py -q
poetry run ruff check src tests
```

## Open Questions

- Should semantic selector collaborators be registered through the same
  mechanism as retrievers, or through a context-management-specific registry?
- Should prompt-cache-aware ordering be its own later feature if provider/model
  metadata becomes complex?
- Should memory-kind labels be accepted only from caller-supplied context
  packets, or can session messages carry those labels too?
