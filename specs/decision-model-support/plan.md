# Decision Model Support Plan

## Status

The evaluation corpus is governed by the merged
`evaluation/dms01-dms12-merged-matrix.json` manifest. DMS-12 is a result row in
that matrix, not a separate candidate cohort; new candidates append rows there.

- Feature spec: `spec.md`
- Mode: guided
- Plan status: partial implementation. DMS-01, DMS-06, DMS-08, DMS-12, and
  DMS-14 evaluations and quality gates remain recorded, but they do not gate
  optional client-facing backend support. Revisit quality criteria when
  context compression/management work resumes. DMS-13 adds a separate
  end-to-end LongMemEval-S context-preservation track with a pinned local
  in-process MLX Llama judge. DMS-13 is shelved; published LongMemEval results
  are used as external context, with no claim about DAR-specific performance.
  DMS-14 completed its approved published general-transfer and Mac-runtime
  matrix. No candidate met both thresholds; results remain comparative only.
  DMS-15 adds an audit-first review for runtime-neutral adapter helpers, with
  implementation conditional on proven reuse across backends. DMS-16 now has
  fake-backed adapter slices for Von, Julia 1, Laya-MLX, and Kev/Qwen, with
  the `workflow_decision` use guard in the shared host path. DMS-17 specifies
  an opt-in Jev-Style v3 selector across exact MLX/Metal, PyTorch, and GGUF
  profiles; its host-supplied loader adapter and fake-backed contract mapping
  are implemented, while backend admission remains pending.
  DMS-18 adds general score/noul workflow routing. DMS-19 defines the
  caller-owned llama.cpp capability surface without adding server lifecycle or
  a SystemOne endpoint.
  See `tasks.md` and `validation.md`.
- Readiness: the generic contract and workflow path are implemented. Optional
  adapter and fake-test slices exist for Von, Julia 1, Laya-MLX, and Kev/Qwen.
  Their profiles are not admitted or exposed until exact material, runtime,
  contract, and host-boundary validation plus approved compatibility smokes
  pass. Kev packaging remains deferred over its Torch constraint conflict.
  Jev-Style v3 has a first-party selector/decision adapter, but no runtime
  profile is admitted or exposed until each exact runtime/material smoke and
  host-boundary check passes. Context-management use still requires its own
  quality review.
- Implementation procedure: spec-driven development, followed by
  `execute-ready-item` for this feature

## Approach

Use one package-owned request/result contract with explicit `choice` and
`scores` modes plus constrained yes/no (`noul`) semantics. Workflow
`decision_step` nodes may use choice, scores, or noul routing under an explicit
deterministic route policy; the internal compaction scorer batches `scores`
questions. The first DAR-owned
implementation supports local models only. Plan optional, separately
installable in-process backends for Von, Julia 1, Laya-MLX, and reviewed
Qwen-based decision profiles, all behind the shared contract and exact
profile/material binding. Keep backend dependencies out of the core install,
require explicit profile selection, and preserve host-owned limits, lifecycle,
tracing, and redaction. Jev-Style adds an explicit `jevstyle-v3-auto` profile
whose host-side selector resolves once to one exact admitted backend profile
before material loading. “Best” means the deterministic pre-load preference
MLX/Metal on Apple Silicon, then GGUF F16 on CPU, then PyTorch BF16 on CPU.
This reflects DMS-01's faster measured warm inference for GGUF than PyTorch on
the tested Mac; it does not benchmark models at startup. CUDA is out of scope
until a separate exact profile is reviewed and admitted. Select only among profiles
admitted for host capability and the host-provided resource budget; if none is
eligible, fail before loading. A selector may pass over a backend unavailable
before loading, but a selected backend's load/inference failure never triggers
another backend. The selector uses only host capability data and sealed
profile/material availability; it does not scan model
directories or download weights. A caller-supplied adapter can still implement server-backed runtimes
such as Laya; the external client owns any server and its lifecycle.

These optional backends do not imply a default model. Their purpose is to let
clients explicitly select supported decision runtimes; they are not DAR's
recommendation for context compression or management. The existing DMS-01,
DMS-06, DMS-08, DMS-12, and DMS-14 measurements remain recorded and do not
block client-facing adapter work. Revisit those quality criteria and evaluate
context-management suitability separately when that work resumes. Backend
support still requires exact source/model/runtime identity, compatible
materials and licenses, bounded contract translation, offline loading after
material admission, and tests for host limits, lifecycle, errors, and
redaction. The Laya evaluation used an isolated Poetry research runtime and
did not alter DAR dependencies or use HTTP; DMS-09's MLX compatibility result
is useful technical evidence, separate from its quality result.

Keep safety decisions outside the learned model. Node validation, allowed-edge
selection, message pinning, recent-turn retention, tool-pair preservation,
resource limits, redaction, and fallback remain DAR responsibilities. The
decision model supplies only an option or option scores. Context-policy code
always performs truncation and message deletion.

## Components and Target Areas

| Concern | Current target area | Expected work |
| --- | --- | --- |
| Public decision request, result, profile, and adapter protocol | `src/dynamic_agent_runner/decision_models.py`, `src/dynamic_agent_runner/__init__.py` | Implemented; reuse the typed contract and validation |
| Workflow node shape and validation | `src/dynamic_agent_runner/validation.py` (`RuntimeNode.raw` preserves subtype data) | Implemented; preserve exact-profile dispatch and mapped-edge routing |
| Workflow node execution | `src/dynamic_agent_runner/context.py`, `src/dynamic_agent_runner/executor.py` | Implemented; resolve exact caller-supplied runtime binding, invoke adapter, validate result, follow only the mapped edge |
| Optional client backends (DMS-16) | Backend-specific adapters under `src/dynamic_agent_runner/workflow_host/`, optional extras in `pyproject.toml`, exact profile/material bindings, and the one-shot local smoke at `tests/manual/smoke_dms16.py` with fake tests in `tests/test_dms16_smoke_runner.py` | Freeze exact rows and technical admit/defer outcomes independently; add separately installable Von, Julia 1, Laya-MLX, and Qwen/Kev backends over the shared contract; enforce `workflow_decision` use before dispatch; require technical/material/host checks and approved exact-runtime compatibility evidence; no context-management quality gate for client support |
| Qwen/Kev material and runner binding (DMS-16) | `src/dynamic_agent_runner/workflow_host/model_execution_binding.py`, `src/dynamic_agent_runner/workflow_host/local_model_runners.py`, `src/dynamic_agent_runner/workflow_host/capabilities.py` | Bind selected exact Qwen/Kev profiles and locked materials after technical/runtime and host-boundary review; reuse host limits and lifecycle; assess context-management quality separately |
| Compaction scoring | `src/dynamic_agent_runner/context_compaction.py`, `src/dynamic_agent_runner/executor.py` | Implemented with fake profiles; model-backed use remains subject to context-management quality review |
| Candidate evaluation | `scripts/evaluate_decision_models.py`, `tests/test_decision_model_evaluation.py`, `specs/decision-model-support/evaluation/` | Implemented for the frozen fixtures; keep quality findings separate from client-backend compatibility |
| End-to-end compaction evaluation | DMS-13 task and `specs/decision-model-support/evaluation/` | Shelved. Use published LongMemEval findings as external context only; do not infer DAR-specific context-compression performance. Reopen only by explicit decision. |
| Published decision-transfer comparison | `tests/manual/run_dms14_transfer.py`, `tests/test_dms14_transfer_runner.py`, `scripts/evaluate_decision_transfer.py`, `tests/test_decision_transfer_evaluation.py`, `specs/decision-model-support/evaluation/`, and `model-evaluation.md` | Score the fixed completed-candidate cohort in process on pinned `transfer-v4` development items; freeze corpus/task mapping and scoring before output inspection; report paired quality and option-order measures on the same corpus in the Mac runtime profile |
| Pinned Kev competency run | `tests/manual/run_kev_dms01.py`, `tests/test_kev_dms01_runner.py` | Historical evaluation-only runner for the exact approved Kev-0.6B artifact; its quality outcome does not gate DMS-16 client support |
| Von alternative evaluation | `tests/manual/run_von_dms06.py`, `tests/test_von_dms06_runner.py` | Completed evaluation-only runner for pinned Von 1.2.0; its quality outcome does not gate DMS-16 client support |
| Jev-Style 0.8B v3 evaluation | `tests/manual/run_jevstyle_dms12.py`, `tests/test_jevstyle_dms12_runner.py`, `specs/decision-model-support/evaluation/jevstyle-mlx-runtime/` | Completed evaluation-only runner for the pinned 8-bit MLX checkpoint; it does not authorize client backend support or context-management use |
| Jev-Style v3 backend selector (DMS-17) | `src/dynamic_agent_runner/workflow_host/jevstyle_decision_adapter.py`, `tests/test_jevstyle_decision_adapter.py`, `tests/test_jevstyle_dms17_smoke_runner.py`, `tests/manual/smoke_jevstyle_dms17.py`, `tests/test_decision_adapter_imports.py`, and `tests/test_workflow_model_execution_binding.py` | Implemented opt-in selection from host-reported machine facts and pre-admitted candidates; invokes exactly the selected candidate's loader with its sealed execution binding. Translates Jev choice/score/noul outputs to the shared contract. Isolated locks include DAR core and backend dependencies; package imports pass. Profiles remain unadmitted pending current material verification and separately authorized exact model smokes. CUDA is outside DMS-17 pending a separate exact profile review. |
| Jev-Style v3 profile evidence (DMS-17) | `specs/decision-model-support/evaluation/dms01-additions-matrix.json` and `model-evaluation.md` | Reuse the exact MLX, PyTorch BF16, and GGUF F16 identities and comparative evidence. Client-runtime admission remains separate from DMS-01 context-management quality. |
| Laya-MLX candidate evaluation | `tests/manual/run_laya_mlx_dms08.py`, `tests/test_laya_mlx_dms08_runner.py`, `specs/decision-model-support/evaluation/` | Completed evaluation-only runner for the exact source/checkpoint/tokenizer/runtime; its quality outcome does not gate DMS-16 client support |
| DAR MLX dependency compatibility | `pyproject.toml`, `poetry.lock`, MLX generation and embedding checks | Choose a compatible optional-extra/runtime boundary without importing upstream `uv.lock`; change shared ranges only after existing MLX consumers pass compatibility checks |
| Laya-MLX decision adapter and binding (DMS-16) | `src/dynamic_agent_runner/workflow_host/laya_mlx_decision_adapter.py`, `src/dynamic_agent_runner/workflow_host/model_execution_binding.py`, `src/dynamic_agent_runner/workflow_host/capabilities.py`; `tests/test_laya_mlx_decision_adapter.py`, `tests/test_workflow_model_execution_binding.py`, `tests/test_capabilities.py` | Implement optional client-facing in-process support after exact runtime/material, output-mapping, and host-boundary checks; keep its DMS-08 quality result as a context-management finding, not an adapter-support gate. |
| Contract tests | `tests/test_decision_models.py` | Test adapter request/result validation and output semantics |
| Reusable adapter helpers (DMS-15) | `src/dynamic_agent_runner/decision_models.py`, `tests/test_decision_models.py`, and `validation.md`; `docs/files/python-api.rst` only if a helper is approved as public API | Audit completed candidate inference paths for duplicated contract translation; implement only runtime-neutral helpers proven useful across at least two backends; otherwise record a no-change disposition |
| Workflow tests | `tests/test_validation.py`, `tests/test_executor.py` | Test schema rejection, exact routing, failure behavior, and no implicit fallback |
| Host binding tests | `tests/test_workflow_model_execution_binding.py`, `tests/test_local_model_runners.py` | Test exact profile/material admission and rejected candidates |
| Compaction tests | `tests/test_executor.py` | Test deterministic protection, fallback, redaction, and score application |
| Workflow score/noul routing (DMS-18) | `src/dynamic_agent_runner/validation.py`, `src/dynamic_agent_runner/executor.py`, `src/dynamic_agent_runner/decision_models.py`, `tests/test_validation.py`, `tests/test_executor.py`, `tests/test_decision_models.py` | Add explicit node output modes and deterministic score/noul route policies; preserve option order, probability semantics, complement checks, abstention, limits, redaction, and fail-closed behavior. |
| Caller-owned llama.cpp surface (DMS-19) | `src/dynamic_agent_runner/local_models.py`, `src/dynamic_agent_runner/openai_client.py`, `src/dynamic_agent_runner/decision_models.py`, `tests/test_local_models.py`, `tests/test_openai_client.py`, `tests/test_decision_models.py` | Define and fake-test caller-owned bindings for chat, structured output, tools, embeddings, multimodal input, and decision inference. Keep model loading, native bindings, optional server lifecycle, and transport outside DAR core; do not expose `/v1/systemone`. |

If discovery shows a named module no longer owns one of these responsibilities,
update this plan before changing implementation scope. Do not duplicate the
decision protocol inside provider adapters or add a second primitive workflow
node kind.

## Context-Management Evaluation Gate

DMS-01 records exact candidate repositories/model identifiers, immutable
revisions, licenses, supported inference formats, runtime requirements, maximum
input sizes, and host resource measurements. Comparative model runs use a
pre-registered labeled evaluation set and criteria agreed before candidate
outputs are inspected. This gate decides context-management suitability; its
thresholds do not gate client-facing `decision_step` adapter support. The report
compares decision quality, calibration when claimed, latency, and peak memory.
For compaction it also compares retention quality at a matched token budget
against the current deterministic baseline.
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
inference. DMS-13 is shelved, and no pilot or full-corpus inference is planned.
Published LongMemEval results may be used as external context but do not
establish DAR-specific quality. Reopen only through a new explicit decision.
If a run is later authorized, an interrupted or failed run must resume from
verified per-item checkpoints and expose progress; after the main pass and
bounded retries, merge only a complete checkpoint set without further
inference. The preflight and approval must bind the exact checkpointed harness
and maximum retry cost before inference resumes. Its results supplement the
frozen synthetic DMS-01 evidence and do not alter prior DMS-01 results or
thresholds.

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
DMS-14 result changes existing quality decisions or DMS-13 status.
The approved matrix has completed: all six rows produced 1,368 predictions
with zero failed outputs, and no candidate met both thresholds. This remains
comparative general-decision-transfer evidence and does not block optional
client adapter support.

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

The initial Qwen candidate cohort contains local candidates only; the reviewed
server-backed Laya integration remains external-client-owned. The separate
DMS-08 Laya-MLX candidate is direct in-process local inference, not that server
integration. Keep all planned backends tied to exact source, model, runtime,
and material identities. Model downloads and real local inference remain
separately authorized manual actions; unit tests stay fake-only.

Adapter and fake-test slices now exist for Von, Julia 1, Laya-MLX, and
Kev-0.6B/Qwen3. Before exposing any profile, bind its exact runtime and
material closure to DAR's existing host boundary; verify bounded input/output
translation, capability limits, cancellation and deadlines, offline loading
after material admission, and redacted failures.
No default backend or implicit fallback is introduced. DMS-01 quality results
do not block client workflow support; before using a profile for compaction or
context management, reopen that work with its own criteria and explicit
profile admission. DMS-13 remains shelved until an explicit decision reopens
that work.

DMS-14 uses fake-only tests for corpus identity, task mapping, label isolation,
aggregation, and redacted receipts. Run its focused tests and Ruff before any
matrix inference. All eligible candidates use the same pinned `transfer-v4`
development items and scoring protocol. Record different precision or
quantization profiles as separate candidate configurations with separate
quality results.

## DMS-16 Optional Client Backend Support

Implement separately selectable, first-party in-process adapters for exact Von
1.2.0, the Julia 1 candidate after technical admission, Laya-MLX, and selected
Kev/Qwen-based profiles through the existing decision contract and host
execution binding. The completed DMS quality
evaluations do not gate client-authored workflow support. Keep their results
as context-management evidence; compaction use is out of scope until that work
is reopened with separate criteria and an explicit profile admission.

First freeze a closed profile/material/runtime row list, recording the exact
artifact/source revision, license, platform, input/output mapping, and optional
dependency closure. Resolve and admit or defer each row independently. Keep
backend stacks outside the default install and import them only when the
matching profile is selected. Mark each binding `workflow_decision`; host
admission rejects `context_retention` before inference. Test translations,
profile/material/use binding, limits, cancellation, deadlines, errors, and
redaction with fakes first. Before exposing any supported row, require an
approved exact-material preflight plus a post-install load and one bounded
compatibility inference. Reuse existing smoke evidence only when its material,
runtime lock, platform, and adapter path match exactly; obtain approval before
any new download or inference. Preserve offline loading, host-owned
resource/lifecycle controls, and fail-closed behavior. Add no server, implicit
fallback, generic model loader, or quality claim. Record client support
separately from context-management decisions.

## Failure and Rollout

- Invalid or missing decision output fails the workflow node with a
  package-owned error through existing workflow failure handling; it never
  selects a default edge.
- Compaction scoring uses only an explicitly configured model profile. Missing,
  failed, timed-out, or invalid scoring uses the configured deterministic
  fallback or fails closed. The feature is not enabled by default.
- A changed model revision, runner, score semantic, or material closure is a
  different profile and requires technical review and material admission
  again. Context-management use also requires renewed quality evaluation.
- Traces include only bounded status, profile identity, counts, score semantic,
  and fallback classification. They omit user content and raw model output.

## Validation

For source changes, write/update focused tests first, observe the expected
failure, implement, then rerun the focused tests. Run the full suite and Ruff
after the focused matrix is green. Exact commands are listed in `tasks.md`.

Real-model competency evidence is separate from unit-test evidence and is
recorded in `model-evaluation.md`. No live provider, model download, or model
inference belongs in unit tests.
