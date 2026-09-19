---
name: agent-evaluation
description: Create package-level evaluation plans, offline regression cases, and acceptance gates for a Dynamic Agent Runner workflow.
---

# DAR workflow evaluation

Use this optional companion after a workflow package exists or when the user
asks for a formal quality, safety, or release decision. DAR preserves evaluation
metadata but does not run an evaluation platform.

## DAR control plane

This plugin contains no MCP server or launcher. Run DAR's package CLI directly:

<!-- rumdl-disable MD013 -->

```sh
uv run --no-project --python 3.14 --index-url https://artifactory.oci.oraclecorp.com/api/pypi/global-release-pypi/simple --with dynamic-agent-runner==0.1.19 dar-package version --json
```

<!-- rumdl-enable MD013 -->

For local development, use an absolute wheel path as the `--with` value. If a
required package-writing command is unavailable, return
`authoring_runtime_unavailable` rather than emitting an unvalidated package or
using a legacy wrapper.

## Output

Create an evaluation plan, fixtures, and a regression gate that cover
deterministic package loading and output-contract checks, expected tool
selection or refusal, bounded tool-call budgets, model/tool failure recovery,
prompt-injection resistance, action-ledger outcomes, `--dry-run`, and `--ask`
behavior where applicable. State the decision owner, pass/fail rules, fixture
and provider digests, and which cases require external or human review.

Keep normal unit tests offline. A separate external harness may run an authoring
model or a configured provider and records only redacted evidence. The gate must
not claim that DAR supplies a judge, credentials, or evaluation infrastructure.
