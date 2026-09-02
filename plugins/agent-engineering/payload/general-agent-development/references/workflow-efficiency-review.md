# Workflow Efficiency Review

Use this reference when an `agent-development` task explicitly asks to review
or reduce an agent workflow's token use, latency, cost risk, or avoidable model
work. It is an advisory review mechanic, not a model selector, dispatch policy,
runtime optimizer, billing system, or Dynamic Agent Runner (DAR) implementation
contract.

Preserve the governing agent-design, evaluation, safety, and runtime-package
contracts. Do not trade output quality, safety, or required validation for a
smaller prompt or fewer model calls.

## Review modes

### Static design review

Consume only the agent design, runtime manifest, workflow graph, tool and
output contracts, plus representative input shape. Label every conclusion
`static-only`; it is a hypothesis, not a measured saving.

### Run-evidence review

Use this mode only with an explicit, redacted, versioned report from a
host-owned producer. Reject the report for empirical review unless it includes:

- report-schema and generator version; report, baseline, and candidate run IDs;
- workflow/package and manifest revision identifiers with correlated node IDs;
- model/provider/configuration identity, metric units, source, availability,
  and aggregation window;
- evaluation suite and cohort/case identity, pass criteria, and output, safety,
  and quality outcomes;
- comparison pairing or sampling method, retry/failure treatment, and stated
  runtime comparability limits; and
- forbidden-field rules, redaction owner, validation result, and fail-closed
  behavior for missing identity, provenance, correlation, or redaction data.

Do not consume raw prompts, complete tool payloads, credentials, private paths,
hidden reasoning, or unredacted traces. A runtime's in-memory trace capability
does not establish that a durable, safe report exists.

## Claim labels

- `static-only` — a design hypothesis with no run measurement.
- `observed` — a report-scoped measurement; do not claim improvement or cause.
- `confirmed improvement` — a comparable baseline/candidate evaluation meets
  stated pass criteria without output, safety, or quality regression.

When billed usage or pricing is unavailable, present token estimates, cache
eligibility, prefix hashes, and provider-reported cached tokens only as
non-billing proxies. Never infer cost from them.

## Review sequence

1. State the workflow objective and the quality, safety, latency, and cost
   constraints that an optimization must preserve.
2. Map every step as deterministic processing, retrieval or lookup, model
   reasoning, or deterministic rendering. Keep model reasoning only where
   ambiguity, synthesis, judgment, or open-ended reasoning materially needs it.
3. Inspect model-visible inputs for duplicated context, unbounded raw payloads,
   missed normalization, avoidable model calls, weak stable-prefix ordering, and
   missing batching or caching opportunities.
4. Recommend one smallest quality-preserving change. Prefer structured
   normalization, targeted retrieval, bounded previews, batching, cacheable
   stable prefixes, and deterministic output rendering before adding another
   model call or a new agent role.
5. State the claim label and the evidence needed to test the recommendation.
   For a claimed improvement, compare representative baseline and candidate
   cases under the report's stated comparability limits.

## Output

```text
Objective and preservation boundary:
Review mode and claim label:
Workflow map:
Evidence available and unavailable:
Smallest recommended change:
Validation: <representative evaluation, non-regression gate, and metrics>
```

Reject a proposed reduction when it weakens a required output contract, safety
control, evaluation case, or evidence boundary. Route model/profile selection
to the applicable dispatch owner, formal evaluation design to `agent-evaluation`,
and any DAR report producer or validator to a separately authorized DAR change.
