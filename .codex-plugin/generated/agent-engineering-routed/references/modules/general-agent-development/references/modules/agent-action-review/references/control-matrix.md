# Control Matrix

Use this reference when `corpus/capabilities/agent-action-review/SKILL.md`
needs the detailed review controls and result mapping.

## Six controls

Evaluate every control as `PASS`, `FAIL`, `INCONCLUSIVE`, or
`NOT_APPLICABLE`.

### 1. Recomputed assessment

- Re-run the deterministic evaluator when its implementation and inputs are
  available.
- Compare the full canonical result, not selected fields.
- `FAIL` when recomputation disagrees materially.
- `INCONCLUSIVE` when only unverifiable claims, schema checks, or checksums are
  available.

### 2. Exact action binding

- Compare the proposed action with the action bound into the approval.
- Compare the full normalized object and digest when available.
- `FAIL` when any material field changed after approval.
- Treat broader target or scope as a mismatch when the evidence only justifies
  a narrower action.

### 3. Replay and identity

- Verify nonce uniqueness and unused status.
- Verify subject, issuer, audience, role, issue time, not-before time, expiry,
  and use count.
- `FAIL` for reused nonce, wrong audience, role mismatch, expired approval,
  future-dated approval, or excessive use count.
- `INCONCLUSIVE` when no trustworthy time source or replay store exists.

### 4. Reviewer independence

Check whether reviewers or evaluators are materially independent across:

| Dimension | Compare |
| --- | --- |
| Model | family, version, fine-tune |
| Provider | account and control plane |
| Prompt | shared template or ancestry |
| Retrieval | overlapping sources and indexes |
| Tools | shared evaluator code and runtime |
| Operator | common owner or approval authority |

Do not count correlated reviewers as independent quorum members.

### 5. Evidence completeness

- Inventory every cited evidence item.
- Confirm presence, relevance, authenticity clues, and validity window.
- Keep support and refutation separate.

| Support | Refutation | Epistemic state |
| --- | --- | --- |
| absent | absent | `UNDETERMINED` |
| present | absent | `SUPPORTED_ONLY` |
| absent | present | `REFUTED_ONLY` |
| present | present | `CONFLICTED` |

- `FAIL` when removed, altered, expired, or concealed evidence changes the
  justified result.
- Never average `CONFLICTED` evidence into a safe-looking score.

### 6. Monitoring freshness

- Confirm the action is still inside its validity window.
- Check monitoring-event integrity evidence when present.
- Check expected heartbeat cadence, sequence, and chain continuity.
- `FAIL` when required monitoring is missing, stale, reordered, or broken.
- Do not interpret silence as health.

## Mutation resistance checks

Before finalizing, ask whether the review would still pass after:

1. replacing a blocked assessment with an allowed result
2. changing one approved target, parameter, scope, or commit
3. reusing a valid nonce
4. replacing independent reviewers with correlated copies
5. removing one refuting evidence item
6. stopping a required monitoring heartbeat

If a mutation still passes, the affected control should be `FAIL`.

## Result mapping

Use exactly one result:

- `ELIGIBLE_FOR_HUMAN_DECISION` — all required controls pass
- `ELIGIBLE_WITH_CONTROLS` — no required control fails, but explicit external
  controls must still resolve listed conditions before execution; name those
  conditions explicitly in `Outstanding controls:`
- `BLOCKED` — at least one required control fails or the action exceeds the
  justified scope
- `INCONCLUSIVE` — no required control is proven false, but the evidence needed
  for a safe decision is missing or unverifiable

Every final report must still state `Execution authorized: false`.
