# Decision Model Support Plan

## Status

- Feature spec: `spec.md`
- Mode: guided
- Plan status: partial implementation; DMS-04 remains stopped because no Qwen
  candidate passed DMS-01. DMS-08 evaluated and rejected Laya-MLX against the
  frozen quality gates, so DMS-10 first-party adapter work is deferred and
  DMS-11 closes with validation and handoff. DMS-12 evaluated Jev-Style 0.8B
  v3 and rejected it under the frozen quality gates. DMS-13 adds a separate
  end-to-end LongMemEval-S context-preservation track; its exact run is approved
  but cannot execute until the required API credential is available.
  DMS-14 completed its approved published general-transfer and Mac-runtime
  matrix. No candidate met both thresholds; results are comparative only and
  do not admit a production profile. DMS-15 adds an audit-first review for
  runtime-neutral adapter helpers, with implementation conditional on proven
  reuse across backends.
  See `tasks.md` and `validation.md`.
- Readiness: DMS-08 through DMS-11 were implementation-ready under their stated
  gates. The DMS-08 result now stops the DMS-10 production-adapter branch.
- Implementation procedure: spec-driven development, followed by
  `execute-ready-item` for this feature

## Approach

Use one package-owned request/result contract with explicit `choice` and
`scores` modes. Workflow `decision_step` nodes use one `choice` question; the
internal compaction scorer batches `scores` questions. The first DAR-owned
implementation supports local models only. Kev-0.6B is the provisional small
local design/manual-test target; fake adapters remain the unit-test mechanism,
and local model results are separately gated by DMS-01. A caller-supplied
adapter can implement server-backed runtimes such as Laya; the external client
owns any server and its lifecycle. Separately, DMS-08 through DMS-10 evaluate
and may add one first-party, direct in-process Laya-MLX profile. Its evaluation
uses an isolated Poetry research runtime and does not alter DAR dependencies.
DMS-09 confirmed that MLX 0.32.2 satisfies the upstream Laya requirement and
coexists with DAR's current MLX extras. This candidate failed DMS-01 quality
gates, so no Laya production adapter or DAR dependency was added. The direct
evaluation did not use HTTP or start a server. DAR's Qwen profiles continue to
use reviewed local model material and execution binding, and the Laya
evaluation did not reopen the stopped Qwen admission task. DMS-12 separately
screens Jev-Style 0.8B v3 on the same local host and frozen fixtures; it does
not authorize model inference or production support until its candidate gates
pass.

Keep safety decisions outside the learned model. Node validation, allowed-edge
selection, message pinning, recent-turn retention, tool-pair preservation,
resource limits, redaction, and fallback remain DAR responsibilities. The
decision model supplies only an option or option scores. Context-policy code
always performs truncation and message deletion.

## Components and Target Areas

| Concern | Current target area | Expected work |
| --- | --- | --- |
| Public decision request, result, profile, and adapter protocol | `src/dynamic_agent_runner/decision_models.py` (new), `src/dynamic_agent_runner/__init__.py` | Define and export typed contracts; validate adapter identity and outputs |
| Workflow node shape and validation | `src/dynamic_agent_runner/validation.py` (`RuntimeNode.raw` already preserves subtype data) | Add one-question decision-model subtype and profile/output-mode checks |
| Workflow node execution | `src/dynamic_agent_runner/context.py`, `src/dynamic_agent_runner/executor.py` | Resolve exact caller-supplied runtime binding, invoke adapter, validate result, follow only the mapped edge |
| Qwen material and runner binding | `src/dynamic_agent_runner/workflow_host/model_execution_binding.py`, `src/dynamic_agent_runner/workflow_host/local_model_runners.py`, `src/dynamic_agent_runner/workflow_host/capabilities.py` | Bind only the evaluated Qwen profile and locked materials; reuse host limits and lifecycle |
| Compaction scoring | `src/dynamic_agent_runner/context_compaction.py`, `src/dynamic_agent_runner/executor.py` | Score eligible old messages in bounded batches, then apply deterministic compaction policy |
| Candidate evaluation | `scripts/evaluate_decision_models.py` (new), `tests/test_decision_model_evaluation.py` (new), `specs/decision-model-support/evaluation/` | Verify frozen fixture hashes and label separation, compare matched-token recency baseline, compute pre-recorded metrics, and emit a redacted evaluation receipt |
| End-to-end compaction evaluation | DMS-13 task and `specs/decision-model-support/evaluation/` | Replay the pinned LongMemEval-S histories through DAR compaction; compare full history, recency, and model-guided retention with one fixed downstream answer model and matched budgets; report answer quality and annotated evidence-turn recall separately from DMS-01 message-retention metrics |
| Published decision-transfer comparison | `tests/manual/run_dms14_transfer.py`, `tests/test_dms14_transfer_runner.py`, `scripts/evaluate_decision_transfer.py`, `tests/test_decision_transfer_evaluation.py`, `specs/decision-model-support/evaluation/`, and `model-evaluation.md` | Score the fixed completed-candidate cohort in process on pinned `transfer-v4` development items; freeze corpus/task mapping and scoring before output inspection; report paired quality and option-order measures on the same corpus in the Mac runtime profile |
| Pinned Kev competency run | `tests/manual/run_kev_dms01.py` (new), `tests/test_kev_dms01_runner.py` (new) | Run the exact approved Kev-0.6B artifact in-process through its pinned external research harness; export only predictions, tokenizer counts, and aggregate measurements |
| Von alternative evaluation | `tests/manual/run_von_dms06.py` (new), `tests/test_von_dms06_runner.py` (new) | Evaluate the pinned Von 1.2 snapshot in-process on the shared frozen inputs, with a separate candidate approval gate, pinned source/runtime, no Von server, and redacted outputs |
| Jev-Style 0.8B v3 evaluation | `tests/manual/run_jevstyle_dms12.py` (new), `tests/test_jevstyle_dms12_runner.py` (new), `specs/decision-model-support/evaluation/jevstyle-mlx-runtime/` | Evaluate the pinned 8-bit MLX checkpoint in process on the shared frozen inputs; the candidate runner verifies exact materials, lock, and preflight, and refuses model download/inference until exact candidate approval |
| Laya-MLX candidate evaluation | `tests/manual/run_laya_mlx_dms08.py` (new), `tests/test_laya_mlx_dms08_runner.py` (new), `specs/decision-model-support/evaluation/` | Resolve and pin one source/checkpoint/tokenizer/runtime; evaluate in an isolated research environment with candidate approval, preflight, offline inference, input-limit rejection, and redacted outputs |
| DAR MLX dependency compatibility | `pyproject.toml`, `poetry.lock`, MLX generation and embedding checks | Choose a compatible optional-extra/runtime boundary without importing upstream `uv.lock`; change shared ranges only after existing MLX consumers pass compatibility checks |
| Laya-MLX decision adapter and binding (deferred) | `src/dynamic_agent_runner/workflow_host/laya_mlx_decision_adapter.py`, `src/dynamic_agent_runner/workflow_host/model_execution_binding.py`, `src/dynamic_agent_runner/workflow_host/capabilities.py`; `tests/test_laya_mlx_decision_adapter.py`, `tests/test_workflow_model_execution_binding.py`, `tests/test_capabilities.py` | Do not implement: DMS-08 failed decision and retention quality gates. Reconsider only after a newly approved candidate passes the frozen criteria. |
| Contract tests | `tests/test_decision_models.py` (new) | Test adapter request/result validation and output semantics |
| Reusable adapter helpers (DMS-15) | `src/dynamic_agent_runner/decision_models.py`, `tests/test_decision_models.py`, and `validation.md`; `docs/files/python-api.rst` only if a helper is approved as public API | Audit completed candidate inference paths for duplicated contract translation; implement only runtime-neutral helpers proven useful across at least two backends; otherwise record a no-change disposition |
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
The one-purpose harness and its fake-output tests verify fixture hashes, label
separation, baseline construction, metrics, and redacted receipts. A dated
preflight records the allowed evaluation runtime and host capacity before any
download or inference.

DMS-13 adds a separate end-to-end benchmark because a message-level keep/drop
metric does not establish that a later user question remains answerable after
compaction. It uses the official LongMemEval-S task histories and questions,
with full-history, deterministic recency, and model-guided conditions sharing
the same fixed downstream answer model and answer-model-tokenizer history
budgets, with prompt/question tokens reserved from the context window.
Dataset revision/license, answer model, scorer, budget points, runtime, and
acceptance thresholds must be resolved and approved before real candidate
inference. Its results supplement the frozen synthetic DMS-01 evidence and do
not alter prior DMS-01 results or thresholds.

DMS-14 adds published general-decision-transfer evidence for the already
evaluated local cohort. It uses one fixed `transfer-v4` development split and
records its immutable source revision, item hashes, license, and task-to-
contract mapping in `evaluation/dms14-corpus-manifest.json`. The complete
candidate/runtime cohort and a versioned, pre-registered protocol are recorded
in `model-evaluation.md` before output inspection. The transfer evaluator and
runner are separate from the DMS-01 fixture-bound evaluator and runner. One
matrix-level approval authorizes all listed candidate/runtime pairs;
candidate-specific identity checks and host preflight still run for every pair.
If an exact corpus mapping or runtime is unusable, record the exclusion before
approval; do not substitute an artifact or add a candidate after approval. No
DMS-14 result changes existing admission, DMS-01, or DMS-13 decisions.
The approved matrix has completed: all six rows produced 1,368 predictions
with zero failed outputs, and no candidate met both thresholds. This remains
comparative evidence and admits no production profile.

DMS-15 audits completed candidate paths for repeated, runtime-neutral
contract-translation logic. It depends on the completed DMS-06, DMS-08, and
DMS-14 reviews; the separate DMS-12 result does not change its audit boundary
or the already frozen DMS-14 matrix.
The audit records either a no-change finding or the specific helper justified
by reuse across at least two backends. Any helper stays within the existing
request/result contract and preserves current validation authority. Tests and
the adapter example live with the contract tests and `validation.md`; public
exports and API documentation are updated only if the review selects a
publicly supported helper.

The initial Qwen candidate cohort contains local candidates only; the then-
reviewed Laya integration required a server and remains external-client-owned.
The separate DMS-08 Laya-MLX candidate is a direct local implementation, not
that server integration. It must be identified and reviewed independently and
may not change DAR dependencies during its isolated evaluation.
Kev-0.6B is a provisional design/evaluation target; any manual inference is
behind DMS-01's approval and preflight gates. DMS-01 recommends a candidate for
DMS-04 but does not admit it for production. DMS-04 binds and fake-verifies the
exact DAR runner/material closure, then performs its separately authorized
competency check. Production admission requires both candidate evidence and
the exact DAR binding to pass. DMS-06 must resolve each named alternative to a
primary-source artifact or record an evidence-backed unresolved-identity defer
before applying the shared evaluation method.

An exact Qwen profile is implemented only after at least one Qwen candidate
passes those criteria and DMS-04 confirms its runtime/material closure can be
bound to a reviewed DAR runner. If none passes or can be bound, stop DMS-04 and
request a user decision on the candidate or acceptance criteria. Model
downloads and real local inference are manual gates; unit tests stay fake-only.

The Laya-MLX branch is ordered DMS-08 candidate identity/evaluation, DMS-09
DAR MLX dependency compatibility, then DMS-10 in-process adapter and admission.
If DMS-08 misses a frozen quality gate or DMS-09 cannot establish a compatible
runtime/material closure, stop the branch without implementing or admitting
the profile. A successful adapter build still requires its separately
authorized competency run and explicit admit/reject record.

DMS-14 uses fake-only tests for corpus identity, task mapping, label isolation,
aggregation, and redacted receipts. Run its focused tests and Ruff before any
matrix inference. All eligible candidates use the same pinned `transfer-v4`
development items and scoring protocol. Record different precision or
quantization profiles as separate candidate configurations with separate
quality results.

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
