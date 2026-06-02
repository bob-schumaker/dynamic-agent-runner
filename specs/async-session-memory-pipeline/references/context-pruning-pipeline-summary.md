# Context Pruning Pipeline Summary

## Purpose

Summarize the OA8-relevant implications of the external context-pruning note in
a portable repository-local reference.

## Source Note Summarized

- `Building a Context Pruning Pipeline for Long-Running Agents`

## Key Findings

### 1. Unbounded history is the real long-running pressure point

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

## OA8 Implications

The source suggests OA8 should remain broad enough for future policies beyond a
simple sliding window. In particular, future protocol growth may need to express:

- raw history vs summary continuity
- message-level vs turn-level retention semantics
- future pruning/selection strategy intent

However, the source does **not** justify adding live pruning execution to OA8’s
first pass.
