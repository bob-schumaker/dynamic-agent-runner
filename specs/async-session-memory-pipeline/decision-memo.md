# Power-Marimo First-Customer Readiness Decision Memo

## Decision

Proceed with a first-customer `power-marimo` integration using
**client-managed multi-call continuity**.

Do **not** block first-customer delivery on runner-owned async-session memory
behavior.

## Why this is acceptable now

- The runner already supports reusable `WorkflowExecutionContext` envelopes.
- The runner already supports repeated async calls via
  `run_agent_workflow_async(...)`.
- The runner already supports caller-owned `run_id` correlation.
- The likely first customer needs a bounded, supervised notebook + power
  analysis workflow more than a native runner-owned session platform.

## What the host/client must own in v1

- notebook/session identity
- prior-turn continuity
- prompt assembly for subsequent turns
- retained notebook/domain summaries
- mapping between notebook sessions and runner calls

## What the runner can honestly promise now

- bounded workflow execution per call
- reusable execution context
- tool-based orchestration
- host-managed continuity across repeated calls

## What the runner must not promise yet

- native multi-turn session persistence
- automatic transcript replay
- built-in context pruning or summary memory
- durable pause/resume semantics for risky notebook actions

## Priority implication

For first-customer value, these likely matter before OA8 implementation:

1. safe Marimo/domain adapters
2. bounded workflow quality
3. clear host-managed continuity pattern
4. OA7 if notebook mutation approvals require resumable interruption

OA8 remains useful as a future protocol seam, but not a gating dependency.
