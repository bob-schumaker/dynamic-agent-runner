# Loop Engineering

Use this refinement when an agent gathers evidence or repeats work until a
condition is satisfied. Keep the general agent-design, evaluation, and runtime
package contracts with their existing owners.

## Minimum loop contract

Record:

- **Objective** — what the loop is trying to make true.
- **Verifier** — the independent check that can observe progress or success.
- **Success condition** — the evidence that permits termination.
- **Preservation boundary** — the behaviors, artifacts, authority, or quality
  signals the loop must not weaken or alter to satisfy the success condition;
  the verifier checks this boundary alongside success.
- **Hard cap or budget guard** — the maximum iterations, steps, time, or cost.
- **No-progress signal** — what counts as repeated, contradictory, or unchanged
  output.
- **Context policy** — when to compact, prune, externalize state, or isolate a
  worker so the loop does not silently lose its contract.
- **Escalation and termination** — what happens on success, exhaustion,
  no-progress, verifier failure, cancellation, or human intervention.

Prefer the verifier before self-reported completion. A loop that says “done”
without checking the success condition has not established an exit.
Success is valid only when the preservation boundary also holds; otherwise a
loop can manufacture a pass by changing the measurement instead of the work.

## Patterns and guards

- `plan-execute-verify`: produce a bounded plan, perform one step, verify it,
  then continue or stop from the verifier result.
- `loop-until-dry`: repeat while the verifier identifies a concrete remaining
  item; stop when the set is empty or the guard is exhausted.
- `orchestrator-workers`: delegate isolated bounded tasks, collect their
  evidence, and let the orchestrator verify the aggregate result.
- `human-in-the-loop`: escalate a defined ambiguity or risk to a person rather
  than allowing the loop to guess indefinitely.

Add no-progress detection explicitly. Repeated identical outputs, unchanged
state after an action, cycling plans, or verifier disagreement should trigger
diagnosis, escalation, or termination—not another unbounded retry. Hard caps
and budgets protect against silent infinite loops and cost blowup; they do not
replace a meaningful verifier.

## Context management inside the loop

Intervene before context loss becomes a false success: compact a long trace
into verified state, prune irrelevant observations, externalize durable
artifacts with provenance, or isolate a worker with only the inputs it needs.
After compaction or delegation, re-establish the objective, verifier, current
progress, and remaining budget before continuing.

Do not use this reference to define evaluation rubrics, debugging ownership,
retrieval budgets, or runtime-manifest conventions; route those questions to
their existing owners.
