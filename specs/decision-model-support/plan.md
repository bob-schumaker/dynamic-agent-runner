# Decision Model Support Plan

## Status

- Feature spec: `spec.md`
- Mode: guided
- Plan status: ready to execute under the gates in `tasks.md`
- Implementation procedure: spec-driven development, followed by
  `execute-ready-item` for this feature

## Approach

Use one package-owned request/result contract with explicit `choice` and
`scores` modes. Workflow `decision_step` nodes use one `choice` question; the
internal compaction scorer batches `scores` questions. A caller-supplied adapter
implements nonstandard runtimes such as Laya; its model loading remains
client-owned. Qwen profiles use DAR's reviewed local model material and
execution binding. Both paths return the same validated contract.

Keep safety decisions outside the learned model. Node validation, allowed-edge
selection, message pinning, recent-turn retention, tool-pair preservation,
resource limits, redaction, and fallback remain DAR responsibilities. The
decision model supplies only an option or option scores. Context-policy code
always performs truncation and message deletion.

## Components and Target Areas

| Concern | Current target area | Expected work |
| --- | --- | --- |
| Public decision request, result, profile, and adapter protocol | `src/dynamic_agent_runner/decision_models.py` (new), `src/dynamic_agent_runner/__init__.py` | Define and export typed contracts; validate adapter identity and outputs |
| Workflow node shape and validation | `src/dynamic_agent_runner/models.py`, `src/dynamic_agent_runner/validation.py` | Add one-question decision-model subtype and profile/output-mode checks |
| Workflow node execution | `src/dynamic_agent_runner/executor.py` | Resolve exact runtime binding, invoke adapter, validate result, follow only the mapped edge |
| Qwen material and runner binding | `src/dynamic_agent_runner/workflow_host/model_execution_binding.py`, `src/dynamic_agent_runner/workflow_host/local_model_runners.py`, `src/dynamic_agent_runner/workflow_host/capabilities.py` | Bind only the evaluated Qwen profile and locked materials; reuse host limits and lifecycle |
| Compaction scoring | `src/dynamic_agent_runner/context_compaction.py`, `src/dynamic_agent_runner/executor.py` | Score eligible old messages in bounded batches, then apply deterministic compaction policy |
| Contract tests | `tests/test_decision_models.py` (new) | Test adapter request/result validation and output semantics |
| Workflow tests | `tests/test_validation.py`, `tests/test_executor.py` | Test schema rejection, exact routing, failure behavior, and no implicit fallback |
| Host binding tests | `tests/test_workflow_model_execution_binding.py`, `tests/test_local_model_runners.py` | Test exact profile/material admission and rejected candidates |
| Compaction tests | `tests/test_executor.py` | Test deterministic protection, fallback, redaction, and score application |

If discovery shows a named module no longer owns one of these responsibilities,
update this plan before changing implementation scope. Do not duplicate the
decision protocol inside provider adapters or add a second primitive workflow
node kind.

## Candidate Evaluation Gate

DMS-01 records exact candidate repositories/model identifiers, immutable
revisions, licenses, supported inference formats, runtime requirements, maximum
input sizes, and host resource measurements. Comparative model runs use a
pre-registered labeled evaluation set and criteria agreed before candidate
outputs are inspected. The report compares decision quality, calibration when
claimed, latency, and peak memory. For compaction it also compares retention
quality at a matched token budget against the current deterministic baseline.

An exact Qwen profile is implemented only after at least one Qwen candidate
passes those criteria and its runtime/material closure can be bound to a
reviewed DAR runner. If none passes, stop DMS-04 and request a user decision on
the candidate or acceptance criteria. Model downloads and real local inference
are manual gates; unit tests stay fake-only.

## Failure and Rollout

- Invalid or missing decision output fails the workflow node with a
  package-owned error through existing workflow failure handling; it never
  selects a default edge.
- Compaction scoring uses only an explicitly configured model profile. Missing,
  failed, timed-out, or invalid scoring uses the configured deterministic
  fallback or fails closed. The feature is not enabled by default.
- A changed model revision, runner, score semantic, or material closure is a
  different profile and requires admission and evaluation again.
- Traces include only bounded status, profile identity, counts, score semantic,
  and fallback classification. They omit user content and raw model output.

## Validation

For source changes, write/update focused tests first, observe the expected
failure, implement, then rerun the focused tests. Run the full suite and Ruff
after the focused matrix is green. Exact commands are listed in `tasks.md`.

Real-model competency evidence is separate from unit-test evidence and is
recorded in `model-evaluation.md`. No live provider, model download, or model
inference belongs in unit tests.
