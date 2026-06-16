# Context Pruning Pipeline Summary

## Purpose

Summarize the context-management implications of the external context-pruning
note in a portable repository-local reference.

## Source Note Summarized

- `Building a Context Pruning Pipeline for Long-Running Agents`

## Key Findings

### 1. Unbounded history is the practical pressure point

The source frames indefinite conversation growth as the practical problem behind
the need for pruning.

### 2. Sliding windows are often too weak

The source contrasts naive recency-only windows with more selective pruning that
retains:

- the most recent turn
- semantically relevant earlier turns
- the current prompt

### 3. Turn granularity matters

The source warns that selecting individual messages can distort natural
user/assistant turn structure.

### 4. Chronological reassembly matters

When older relevant turns are selected out of order, they should be reassembled
chronologically before final context construction.

### 5. Compression should be hierarchical

The source implies that pruning is only one layer of context management. A
stronger pipeline combines pinned instructions, current prompt, recent turns,
selected older turns, summaries, and bounded source/tool context rather than
treating the transcript as one flat queue.

### 6. Selection should happen before summarization

If older turns are still relevant to the current prompt, they should be retained
directly when budget allows. Summaries are best used for continuity across
evicted material, not as the only representation of all older context.

## Context-Management Implications

The source suggests future context-management work should remain broad enough
for policies beyond a simple sliding window. In particular, future protocol
growth may need to express:

- raw history versus summary continuity
- explicit budget lanes for pinned, current, recent, selected, summary, and
  source/tool context
- message-level versus turn-level retention semantics
- future pruning or selection strategy intent
- chronological reassembly after relevance selection
- rolling summaries that fold newly evicted turns without repeatedly
  re-summarizing the same prior summary

However, the source does **not** justify adding runner-owned durable session
storage, automatic cross-run replay, or long-term memory behavior.
