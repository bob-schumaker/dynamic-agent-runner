# Semantic Context Profiles Slice S1 Plan

## Metadata

- Feature slug: `semantic-context-profiles`
- Slice: S1 injected semantic selector
- Status: prepared for implementation
- Date: 2026-06-22
- Owning spec: [`spec.md`](spec.md)

## Objective

Add the smallest useful semantic selector seam to the existing
`prepare_model_input(...)` older-turn selection path. S1 should let a caller
inject a fake-testable selector for semantic older-turn ranking, report bounded
diagnostics, and preserve exact identifier behavior without adding runner-owned
embeddings, vector stores, memory stores, or retrieval infrastructure.

## Current Fit

The current runtime already provides the right base:

- `prepare_model_input(...)` assembles context lanes and metadata in
  `src/dynamic_agent_runner/executor.py`.
- `WorkflowExecutionContext` groups reusable runtime collaborators.
- Existing policy validation accepts named profiles including `semantic` and
  selection strategies including `injected_semantic`.
- `_selected_older_turn_parts(...)` already handles deterministic overlap,
  `exact`, and `hybrid_exact_semantic` older-turn selection.
- Retrieved RAG evidence already has a separate retrieved-context lane.

S1 should extend this path rather than introduce a new context subsystem.

## Proposed API Shape

Add a small package-owned selector contract, preferably in a new focused module
such as `src/dynamic_agent_runner/context_selection.py`:

```python
@dataclass(frozen=True)
class ContextSelectionCandidate:
    turn_id: str
    text: str
    roles: tuple[str, ...]
    exact_match_count: int
    token_estimate: int | None = None


@dataclass(frozen=True)
class ContextSelection:
    turn_id: str
    score: float
    reason: str = "injected_semantic"


ContextSelector = Callable[
    [str, tuple[ContextSelectionCandidate, ...], Mapping[str, object]],
    Iterable[ContextSelection],
]
```

The implementation may adjust names to fit local style, but the contract should
remain:

- selector input is structured, bounded, and limited to older session turns
- selector output identifies candidates by `turn_id`
- invalid or unknown selector results are rejected with metadata, not raw
  exceptions leaked into traces
- exact identifier matches remain protected before optional semantic ranking

## Data Flow

1. Caller supplies `context_selector` through direct execution kwargs or
   `WorkflowExecutionContext`.
2. `_execute_llm_step_async(...)` passes it to `prepare_model_input(...)`.
3. `prepare_model_input(...)` builds older-turn candidates from pruned session
   turns only.
4. For `strategy: injected_semantic`, the selector scores candidates.
5. The selector output is capped by `max_selected_turns`; selected turns are
   chronologically reassembled by default.
6. Prepared-input metadata reports selector status, fallback status, selected
   turns, omitted turns, rejected turns, and bounded score/reason fields.

## Missing Selector Behavior

If `profile: semantic` or `strategy: injected_semantic` is configured without a
selector:

- default behavior should degrade to deterministic overlap and record
  `selector_status: missing` plus `fallback_strategy: deterministic_overlap`
- if policy later adds an explicit fail-closed flag, that flag must be tested
  separately; S1 does not need to add a new strict-mode policy

## Non-Goals

- No embeddings, vector stores, graph stores, or memory stores.
- No live model, embedding, retrieval, or network calls in unit tests.
- No RAG lane borrowing; retrieved context remains in the retrieved-context
  lane.
- No memory-kind labels, access-frequency scoring, stale/redundant omission, or
  prompt-cache-aware ordering.
- No capability/status extension unless it falls out naturally from the
  collaborator contract.

## Expected Touch Points

- `src/dynamic_agent_runner/context_selection.py`
- `src/dynamic_agent_runner/context.py`
- `src/dynamic_agent_runner/executor.py`
- `src/dynamic_agent_runner/__init__.py`
- `tests/test_executor.py`
- `tests/test_import.py`
- README and `docs/files/python-api.rst` only if public kwargs/exports are added

## Compatibility

Existing workflows without `context_selector` must preserve current behavior.
Existing deterministic overlap, `exact`, and `hybrid_exact_semantic` tests must
continue to pass.
