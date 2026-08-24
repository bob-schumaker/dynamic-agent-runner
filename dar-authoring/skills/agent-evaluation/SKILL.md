---
name: agent-evaluation
description: Create package-level evaluation plans, offline regression cases, and acceptance gates for a Dynamic Agent Runner workflow.
---

# DAR workflow evaluation

Use this optional companion after a workflow package exists or when the user
asks for a formal quality, safety, or release decision. DAR preserves evaluation
metadata but does not run an evaluation platform.

## Input boundary

Use the package contract and approved `AuthoringMaterialSet` projections only.
Do not include live-service credentials, raw prompt history, unselected
material, or external tool output in an evaluation artifact.

When this skill is routed from `agent-development`, use the supplied
`material_set_id` and `authoring_output_id`. Resolve the shared
`../../scripts/dar-workflow` wrapper relative to this `SKILL.md` file and use
`write-authored-package-file` for each evaluation artifact. Do not write
through a physical package path. Do not finalize the package; the entry skill
finalizes the complete package.

## Output

Create:

- `eval-plan.md`
- `evaluation-fixtures.json`
- `regression-gate.yaml`

Cover deterministic package loading and output-contract checks, expected tool
selection or refusal, bounded tool-call budgets, model/tool failure recovery,
prompt-injection resistance, action-ledger outcomes, `--dry-run`, and local
`--ask` behavior where applicable. State the decision owner, pass/fail rules,
fixture/provider digests, and which cases require external or human review.

Keep normal unit tests offline. A separate external harness may run an authoring
model or a configured provider and records only redacted evidence. The gate must
not claim that DAR supplies a judge, credentials, or evaluation infrastructure.
