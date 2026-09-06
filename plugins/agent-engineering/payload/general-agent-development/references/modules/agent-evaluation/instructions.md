---
name: agent-evaluation
description: Use to design eval plans, rubrics, judges, gates, and human-review sampling for agents, prompts, tools, LLM workflows, and state-mutating systems.
---

# agent evaluation skill

Use this skill when the main task is to evaluate an agentic system, prompt,
tool-use workflow, memory behavior, or LLM-backed process in a repeatable way.

This is a specialized standalone skill. It owns evaluation design and review;
it does not replace ordinary unit tests, PR review, debugging, or agent
architecture design.

## Relationship to adjacent skills

- Use `corpus/capabilities/agent-development/SKILL.md` when evaluation is one
  dimension of a broader agent design or runtime package.
- Use this skill when evaluation design, rubrics, judge workflows, regression
  gates, or evaluation-set construction are the main work.
- Use `corpus/capabilities/test-driven-development/SKILL.md` for deterministic
  behavior changes where examples can be expressed as ordinary tests.
- Use `corpus/capabilities/systematic-debugging/SKILL.md` when a specific
  failure has already occurred and needs root-cause diagnosis.
- Use `corpus/procedures/code-review.md` and
  `corpus/capabilities/code-review-mechanics/SKILL.md` for ordinary diff review
  rather than ongoing model or agent quality evaluation.

## When to use

Use this skill when the user asks to:

- design an evaluation plan for an agent, prompt, workflow, or tool-using system
- create or review evaluation rubrics
- build golden tasks, regression cases, or edge-case test sets
- evaluate non-deterministic outputs where multiple paths can be valid
- design LLM-as-judge or human-review workflows
- compare prompts, models, memory settings, tool contracts, or agent
  configurations
- define release or regression gates for an agentic system
- evaluate a state-mutating agent by checking the final state and audit trail

Do not use this skill for routine unit tests, single PR review findings,
benchmark claims that need current source verification, or generic metrics
dashboards with no agent-quality question.

## Workflow

### 1. Define the evaluation decision

State what decision the evaluation must support:

- ship, block, or roll back a change
- compare two prompts, models, tools, memory settings, or workflows
- identify quality regressions
- calibrate an automated judge against human review
- measure whether an agent reaches an expected end state

If no decision will be made from the result, narrow the evaluation before
building rubrics.

### 2. Define the evaluated object

Identify the unit under evaluation:

- full agent run
- one LLM step
- prompt or system instruction
- tool-selection behavior
- retrieval or memory behavior
- generated artifact
- final state after a mutation-capable run
- multi-agent coordination outcome

Record the runtime, model, tools, context sources, memory state, permissions,
and budgets that must be held stable for fair comparison.

### 3. Build the evaluation set

Create cases from realistic usage and known risks:

- common happy paths
- edge cases
- ambiguous or underspecified requests
- adversarial or prompt-injection attempts when relevant
- long-context or multi-turn cases
- tool failures, empty results, and partial successes
- state mutation and rollback cases

Stratify by complexity instead of relying on one average score. A simple set can
use `simple`, `medium`, `complex`, and `extended` buckets.

### 4. Design the rubric

Use dimensions that match the task, such as:

- task completion
- factual accuracy or grounding
- source and citation quality
- instruction following
- safety and permission handling
- tool selection and recovery
- output format compliance
- user-facing clarity
- state correctness and changed-state provenance
- efficiency within stated cost, latency, token, or tool-call budgets

For each dimension, define observable pass/fail or score levels. Avoid criteria
that measure several things at once. State the threshold that changes the
release, rollback, or iteration decision.

### 5. Choose judge and review mechanics

Pick the lightest reliable evaluator:

- deterministic checks for schemas, exact state, command output, or invariants
- direct scoring against a rubric for objective dimensions
- pairwise comparison for preference judgments
- LLM-as-judge with structured output when scale matters
- human review for high-risk, low-confidence, or subjective cases

Mitigate judge bias when using model-based evaluation:

- require evidence-backed justification before the score or verdict
- randomize or swap positions in pairwise comparisons
- penalize unsupported confidence, irrelevant length, and authoritative tone
  without evidence
- use a different judge than the generator when practical
- sample disagreements and low-confidence cases for human review

Do not treat a judge score as ground truth without calibration or review.

### 6. Evaluate state, tools, and safety

For tool-using or mutation-capable agents, evaluate more than the final prose:

- final persisted state
- audit log and changed-state provenance
- whether required approvals were requested
- whether forbidden actions were avoided
- tool-call arguments and recovery from tool errors
- evidence trail for claims
- cleanup or rollback behavior after partial failure

Prefer end-state evaluation when multiple valid paths can reach the same
outcome.

### 7. Define reporting and regression gates

Record:

- baseline and candidate identifiers
- case count and complexity coverage
- rubric thresholds
- pass/fail, score, confidence, and missing-information fields
- allowed flakiness or rerun policy
- manual review sampling rule
- blocking regressions and acceptable tradeoffs

Keep trend data comparable across runs. If the test set, judge, rubric, model,
or tool contract changes, record that the baseline moved.

## Output expectations

Return:

```text
Evaluation decision:
Evaluated object:
Evaluation set:
Rubric:
Judge or review method:
State/tool/safety checks:
Regression gate:
Reporting format:
Risks and calibration gaps:
```

## Completion standard

This skill is complete when the evaluation has a decision owner, a defined
object under test, representative cases, observable rubric criteria, calibrated
judge or human-review mechanics, state/tool/safety checks where relevant, and a
regression gate that can honestly pass, fail, or request more evidence.
