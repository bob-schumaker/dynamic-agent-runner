# Action Packet Checklist

Use this reference when `corpus/capabilities/agent-action-review/SKILL.md`
needs the exact input packet for a review.

## Required packet fields

Collect only the fields needed to review the proposed action:

1. original user request, governing policy, or system instruction
2. exact proposed action:
   - operation or tool name
   - target resource
   - complete parameters
   - filesystem scope
   - network scope
   - maximum execution count
   - not-before time
   - expiry time
3. assessment that claims the action is justified
4. evidence and policy used by that assessment
5. approval record:
   - approver identity
   - issuer
   - role
   - audience
   - action digest when present
   - nonce
   - issue time
   - not-before time
   - expiry time
   - use count or maximum uses
6. current monitoring or heartbeat state when lifecycle monitoring matters
7. trusted current time and prior nonce-use record when replay matters

List missing fields before analysis. Do not silently invent defaults.
If trusted packet evidence for replay, reviewer independence, monitoring
continuity, or current time is unavailable, expect the review to stay
`INCONCLUSIVE` unless a concrete mismatch already blocks the action.

## Normalized action identity

Build one normalized action object without dropping fields:

```json
{
  "operation": "git.push",
  "target": "owner/repository",
  "parameters": {
    "branch": "fix/example",
    "commit": "40-character-sha",
    "remote": "origin"
  },
  "filesystem_scope": [],
  "network_scope": ["github.com:443"],
  "execution_count": 1,
  "not_before": "RFC3339 timestamp",
  "expires_at": "RFC3339 timestamp"
}
```

When a project-defined canonicalization or digest algorithm exists, use it.
Otherwise compare every field structurally and report that the digest could not
be independently verified.

## Never normalize away

Treat these as material distinctions:

- repository, branch, commit, environment, recipient, amount, currency, host,
  port, path root, or CIDR
- recursive, force, overwrite, privileged, destructive, or dry-run flags
- execution count, approval window, or expiry

If evidence only justifies a narrower target or scope than the proposed action,
that is a mismatch.
