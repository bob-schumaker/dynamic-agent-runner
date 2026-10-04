# Decision Model Support Tasks

Source of truth: `spec.md`. Implementation approach: `plan.md`.

The 2026-10-02 client-support decision separates adapter availability from
context-management quality. DMS-01/DMS-06/DMS-08/DMS-12/DMS-14 results remain
historical context-management evidence; revisit criteria when that work
resumes. DMS-16 plans optional client workflow support for exact Von,
Julia 1, Laya-MLX, and Qwen-based profiles without using those quality results
as adapter prerequisites. DMS-17 plans an opt-in Jev-Style v3 selector across
the exact MLX/Metal, PyTorch, and GGUF profiles evaluated in DMS-01.

## Readiness Review

- [x] Review DMS-17 against `spec.md` and `plan.md` with the Council
  architecture triad and Ponytail. The task is ready to begin profile freeze
  under its stated runtime/material, host resource-budget, and authorization
  gates. The review excluded CUDA until a separate exact profile exists and
  completed mapping coverage for `choice`, ordered `scores`, and constrained
  native `noul` output without adding a public mode.
  Council and Ponytail findings, dispositions, and verification are recorded
  in `validation.md`.
- [x] Re-review DMS-16 against `spec.md` and `plan.md` with the Council
  architecture triad and Ponytail after adding the Julia 1 candidate. The
  profile-freeze/admit-or-defer discovery step is ready to begin; Julia
  RED/GREEN and exposure remain gated on the exact row, pinned local
  runtime-code identity, no-remote-code proof, Julia-specific mapping tests,
  and exact dependency lock and implementation targets. Council challenge,
  repairs, Ponytail findings, and verification are recorded in `validation.md`.
- [x] Re-review DMS-16 against `spec.md` and `plan.md` with the Council
  architecture triad and Ponytail after the client-support scope decision.
  Council found it ready under staged technical gates: freeze exact profile
  rows and decide technical admission independently; reject context-retention
  use before inference; cover Laya `noul` mapping; and require exact approved
  compatibility evidence. Quality results do not gate client workflow support.
  Ponytail removed a duplicate DMS-16 plan-table row while retaining the task's
  necessary profile, use-boundary, and compatibility checks. Findings and
  dispositions are in `validation.md`.
- [x] Re-review the current task list against `spec.md` and `plan.md` with the
  Council architecture triad and Ponytail after making DMS-13 restartable.
  Council found the task graph ready with conditions; at that review DMS-13
  inference was blocked pending a preflight and approval binding the current
  harness, manifest, retry policy, and maximum call budget. Ponytail removed
  duplicated checkpoint mechanics from the open run task. Findings,
  challenge-round conclusions, dispositions, and verification are recorded in
  `validation.md`.
- [x] Re-review this task list against `spec.md` and `plan.md` with Council
  and Ponytail after adding the separate direct in-process Laya-MLX track.
  Clarify that server-backed Laya stays external-client-owned; authorize only
  one reviewed local MLX profile; define source-output translation; and add
  dependency, admission, and final-validation gates. See `validation.md` for
  findings, dispositions, and verification.
  - Verdict: implementation-ready; this plan is ready to execute under its
    stated gates. DMS-08 starts with identity verification and fake-backed
    runner work; model download and inference still require candidate-specific
    approval and a matching preflight.
  - The existing Qwen candidate results remain unchanged: no Qwen profile
    passed the frozen quality gates, so DMS-04 remains stopped. Laya-MLX is a
    separate candidate path and does not reopen DMS-04.
- [x] Review the current task list against `spec.md` and `plan.md` with the
  Council architecture triad and Ponytail after the completed DMS-14 matrix and
  addition of DMS-15. Reconcile stale DMS-14 state, make DMS-15 dependencies
  and evidence targets explicit, and keep helper implementation conditional
  on demonstrated cross-backend reuse. See `validation.md` for the review,
  dispositions, and validation.
  - **Council:** Ada, Aristotle, and Feynman completed independent first
    passes and a challenge round. They found stale DMS-14 status in the spec
    and plan, an unnecessary DMS-12 dependency on DMS-15, and missing
    DMS-15 traceability and exact validation targets. They agreed that the
    DMS-15 audit is ready while any implementation requires those repairs.
  - **Ponytail:** Keep DMS-15 as one audit-first task; reuse existing contract
    validation; add no helper unless at least two reviewed backends share the
    same runtime-neutral translation; record a no-change result otherwise.
  - **Repairs:** Updated the spec and plan to record DMS-14's completed matrix
    and comparative-only outcome; labeled its earlier pre-execution review as
    historical; removed DMS-12 as a DMS-15 prerequisite; linked DMS-15 to
    contract scope, plan ownership, audit evidence, tests, and conditional API
    documentation.
  - **Disposition:** The task list was ready under its stated gates. DMS-15's
    audit completed with no helper; helper implementation depends on
    demonstrated reuse.
    DMS-04 was stopped and DMS-10 deferred for context-management use at that
    review date. DMS-16 now owns optional client-workflow adapter support.
    DMS-12 is complete; DMS-13 now uses a pinned local MLX Llama judge and, at
    that review date, awaited approval for the revised exact run.

Tasks are ordered by dependency. Every code task follows TDD: add or update the
focused test first, observe the expected failure, implement, and rerun until it
passes. Do not use real model weights in unit tests.

## DMS-01 Candidate Evidence Gate

- [x] Review primary repositories and cards, and record immutable revisions,
  license, task/output contract, inference format, runtime, input length, and
  available memory evidence for Kev 0.5B, 0.6B, 4B, and 8B, and Bespoke Nimble
  9B in `model-evaluation.md`. Laya is
  excluded from the initial internal-model cohort because its current
  integration requires a server; external clients may support it later through
  the client adapter contract.
- [x] Use the pinned Kev-0.6B revision recorded in `model-evaluation.md` as the
  provisional small local design and evaluation target. Any manual inference
  is evaluation-only and remains behind the user-approved fixture/criteria and
  preflight gates below; this does not select a production profile. Unit tests
  remain fake-backed.
- [x] Freeze a labeled decision/retention evaluation set and its acceptance
  criteria before inspecting candidate results. Use non-sensitive fixtures;
  do not ingest user transcripts without separate authorization. Get user
  approval of the evaluation set and criteria before any real-model run.
- [x] **RED:** Add `tests/test_decision_model_evaluation.py` with fake outputs
  covering fixture-hash verification, label/input separation, matched-token
  baseline behavior, pre-recorded metrics, and redacted receipts. Confirm these
  cases fail before implementation.
- [x] **GREEN:** Implement the narrow harness at
  `scripts/evaluate_decision_models.py`. It verifies the fixture hashes, keeps
  labels out of candidate inputs, applies the matched-token deterministic
  recency baseline, calculates the pre-recorded quality/calibration metrics
  and intervals, and writes a redacted run receipt. Do not add a general
  model-runner framework.
- [x] Before download or inference, record a dated preflight receipt with the
  approved evaluation harness/runtime and exact artifact revisions, current
  host/storage availability, and whether execution uses an external research
  harness or an already admitted DAR runner. Stop before download/inference if
  the host or runtime does not permit the run.
- [x] **RED/GREEN:** Add fake-only tests for a pinned Kev-0.6B manual runner
  that refuses a missing/blocked preflight, builds decision and retention
  requests from input rows only, verifies the exact adapter/base/tokenizer
  revisions, and emits no raw input in its prediction/measurement files.
  Implement the candidate-specific runner at
  `tests/manual/run_kev_dms01.py`; it must use the pinned external harness
  in-process and must not add a DAR-owned server or model runner.
- [x] Run local competency measurements only for exact artifacts and runtimes
  allowed by the host. Record accuracy/retention quality, calibration metrics
  when claimed, latency, and peak memory. Compare compaction retention at a
  matched token budget with the deterministic baseline.
- [x] Recommend an exact local Qwen candidate for DMS-04 only if it passes the
  recorded criteria and a design-level compatibility review finds a feasible
  DAR runner/material closure. Record reject/defer reasons for other
  candidates. This recommendation is not production admission; DMS-04 must
  bind and fake-verify the exact runner/material lock, then complete its
  separately authorized competency check before the production decision.
  Kev-0.6B, Kev-0.8B, Von, Julia 1, PoorJev, and LitJev failed one or more
  required quality gates. NanoJev remains deferred for host and licensing constraints.
  No candidate is recommended. Stop before DMS-04 until a future candidate or
  criteria change is approved.
- [x] Add the technically admitted Julia 1 profile to the DMS-01 comparison
  without changing fixtures or thresholds. Add a fake-backed, candidate-bound
  CPU runner, record the exact preflight and outputs, and compare decision,
  retention, calibration, and operation metrics against the existing Von
  result. Julia 1 completed all 240 frozen cases; its result is recorded in
  `model-evaluation.md` and `evaluation/julia1-dms01-receipt.json`.
- [x] Run the approved Kev-0.8B candidate-specific evaluation on the frozen
  DMS-01 fixtures and record its exact preflight, predictions, token counts,
  measurements, and aggregate threshold results. It completed 240 cases and
  passed operations only; it does not qualify for DMS-04.
- [x] Expand and run the DMS-01 comparison for MacJev-322M-4K-Laya / PyTorch
  CPU, Lev LFM2.5-350M / CPU, and Jev-Style 0.8B v3 / PyTorch CPU and GGUF F16
  CPU. Freeze exact revisions, runtime/build materials, licenses, and
  preflight receipts; reuse the 240 frozen fixtures and thresholds unchanged.
  All four rows completed without inference errors or OOM and passed the
  operations gate, but all failed one or more DMS-01 quality gates. Results,
  failed first-attempt evidence, and exact artifacts are in
  `model-evaluation.md` and `evaluation/`.

## DMS-02 Decision Contract (FR-1, FR-3, FR-6)

- [x] **RED:** Add `tests/test_decision_models.py` for valid choice/score
  requests and invalid mode, duplicate decision/question IDs, missing
  questions, empty/duplicate options, unknown options, missing/duplicate
  question results/scores, result order, NaN/infinity, probability range/sum,
  ranking-versus-probability semantics, invalid/input/result limits, absent
  calibration evidence, explicit abstention, and exact adapter identity.
  Confirm the missing contract causes the tests to fail.
- [x] **GREEN:** Implement the typed adapter, request, result, and profile
  contracts in `src/dynamic_agent_runner/decision_models.py`; export only the
  intended public types from `src/dynamic_agent_runner/__init__.py`. Keep model
  runtimes outside DAR core.
- [x] Rerun the focused contract tests and Ruff on changed source/tests.
  Completion evidence: passing contract test output and public API review.

## DMS-03 Workflow Decision Node (FR-2)

- Depends on: DMS-02.
- [x] **RED:** Add validation and executor tests for a one-question decision
  model `decision_step`, including rejection of zero/multiple questions,
  incomplete or duplicate option-to-edge mappings, missing/unsupported
  profiles and a scores-only profile, and unsafe or unbounded context
  references. Reject workflow-authored adapter code, local paths, runtime
  imports, and implicit provider fallback. Prove exact choice-to-edge routing,
  caller-supplied adapter dispatch through its exact runtime binding, invalid
  result, unmapped option, and adapter failure.
  Confirm host-stricter input/output limits, cancellation, and deadline expiry
  prevent inference or routing as applicable, and package-owned errors and
  default traces omit context and raw adapter payloads. Confirm each new
  behavior fails before implementation; client runtimes remain outside DAR
  core and executable adapter content remains outside workflow packages.
- [x] **GREEN:** Use the existing `RuntimeNode.raw` preservation and update
  `src/dynamic_agent_runner/validation.py` and
  `src/dynamic_agent_runner/executor.py` to validate the subtype, resolve the
  exact runtime binding, and route only to the mapped edge.
- [x] Rerun `tests/test_validation.py` and `tests/test_executor.py` plus the
  focused new cases. Completion evidence: tests prove existing `llm_route`
  behavior remains valid and decision-model failures never choose a default
  edge.

## DMS-04 Qwen Local Profile (FR-4)

- Depends on: DMS-01 and DMS-02.
- Archived context-management disposition: the DMS-01 quality gate stopped
  Qwen use for context management. DMS-16 supersedes this task for client
  workflow support and uses technical/material/host-safety gates.
- [x] Apply the candidate gate: the completed DMS-01 cohort has no passing
  Qwen profile, so DMS-04 implementation is stopped as required by `spec.md`.
  No adapter tests, production binding, competency run, or admission decision
  are claimed. Revisit the context-management decision only when that work and
  its quality criteria are reopened.

## DMS-05 Internal Compaction Scoring (FR-5, FR-6)

- Depends on: DMS-02 and DMS-03.
- [x] **RED:** Add executor/compaction tests showing that low scores cannot
  remove pinned instructions, recent turns, unresolved state, or tool-call /
  result pairs, and that invalid, missing, abstaining, and timed-out results
  never authorize deletion. Also prove bounded batches preserve stable message
  IDs and that only an explicitly configured threshold or bounded ranking rule
  applies keep/drop scores; absent policy leaves scores diagnostic. Confirm
  failure before implementation.
- [x] **GREEN:** Add opt-in keep/drop scoring to
  `src/dynamic_agent_runner/context_compaction.py` and its call path in
  `src/dynamic_agent_runner/executor.py`. Keep candidate scoring separate from
  deterministic retention protections, configured fallback, and truncation.
  Use fake-backed profiles; any Qwen-backed scoring remains gated on DMS-04.
- [x] Rerun focused compaction and executor tests. Completion evidence includes
  retained-boundary tests and redacted trace assertions.

## DMS-06 Other Candidate Evaluation

- Depends on: DMS-01 evaluation method and DMS-02 contract.
- [x] Add a fake-backed, candidate-specific evaluation runner for Von at
  `tests/manual/run_von_dms06.py`. It verifies the pinned source and model
  revisions, refuses to download weights without separate Von-run approval
  and a matching preflight, loads the approved snapshot in-process with network
  access disabled during inference, and writes only predictions, tokenizer
  counts, and aggregate measurements. No DAR production support or model
  weights are added.
- [x] Run Von 1.2.0 on the approved frozen fixtures and record the exact
  preflight, prediction/token-count outputs, aggregate metrics, and threshold
  decision in `model-evaluation.md` and `evaluation/`. Von failed the decision
  and retention gates and is rejected for support.
- [x] Add the fake-only-tested PoorJev runner at
  `tests/manual/run_poorjev_dms06.py`. It pins the source, model, and shared
  research runtime; requires candidate-specific approval and a matching
  preflight; disables network access after the pinned model snapshot is fetched;
  and emits redacted predictions, tokenizer counts, and measurements.
- [x] Record the PoorJev preflight before any model download or inference.
  Host capacity, runtime, source revision, artifact revision, fixture hash, and
  harness hashes passed after candidate-specific approval. The approved run
  completed all frozen fixtures; its receipt and reject decision are recorded.
- [x] Add a fake-only-tested LitJev runner at
  `tests/manual/run_litjev_dms06.py`, using the source-locked `Qwen/Qwen3-0.6B-Base`
  pairing. It calls LitJev in-process on CPU, binds the source/model/runtime
  revisions, refuses unapproved or mismatched preflights, and emits redacted
  predictions, tokenizer counts, and measurements.
- [x] Run PoorJev on the approved frozen fixtures and record its evaluator
  receipt. It failed decision accuracy (0.54), retention F1 (0.35), keep recall
  (0.31), and utility improvement (+0.032 versus the required +0.05); scores
  remain uncalibrated. Operations passed.
- [x] Install LitJev's exact locked runtime under `/private/tmp`, rerun its
  preflight, run on the approved frozen fixtures, and record its evaluator
  receipt. It failed decision accuracy (0.29), retention F1 (0.56), and keep
  recall (0.50); utility improved by +0.167. Scores remain uncalibrated.
  Operations passed.
- [x] Complete comparative evaluation of PoorJev, NanoJev, and LitJev against
  the same request/result contract and task metrics. Exact identities, match
  rationale, source URLs, calibration claims, runtime/license constraints, and
  accept/defer decisions are recorded in `model-evaluation.md`. PoorJev and
  LitJev failed the frozen quality criteria; NanoJev remains deferred because
  its pinned inference source requires unavailable CUDA and its checkpoint
  license is undeclared.
- [x] Record no alternative context-management profile under the then-current
  quality thresholds: Von, PoorJev, and LitJev failed, while NanoJev is
  deferred. This historical disposition does not block the separate
  client-facing adapter work in DMS-16.

Frozen-fixture evaluation is complete for Von 1.2.0, PoorJev, LitJev, and
Jev-Style 0.8B v3. All failed one or more frozen quality gates. NanoJev is
deferred for host and licensing reasons. No alternative production support is
added.

## DMS-07 Initial Implementation Validation

- Depends on: DMS-03 through DMS-06.
- [x] Run focused validation. The DMS, workflow-binding, local-runner, and
  capability matrix including the Von, PoorJev, and LitJev fake runners
  completed with 427 passed and 1 skipped (the unavailable Darwin MPS hardware
  case); no tests failed.

  ```bash
  poetry run pytest tests/test_decision_models.py \
    tests/test_decision_model_evaluation.py tests/test_validation.py \
    tests/test_executor.py tests/test_workflow_model_execution_binding.py \
    tests/test_local_model_runners.py tests/test_capabilities.py \
    tests/test_von_dms06_runner.py tests/test_poorjev_dms06_runner.py \
    tests/test_litjev_dms06_runner.py -q
  ```

- [x] Run full validation against the worktree. With the isolated pinned Von
  runtime on the import path, the full run completed with 2,884 passed, 4
  skipped, 0 failed, and 7 deselected. The skips cover unavailable MPS and the
  host-rejected macOS `sandbox-exec` fixture; the three stale-wheel-path
  failures were corrected and now pass. Plain `poetry run pytest` imports stale
  installed `site-packages` code and is not authoritative for this worktree.

  ```bash
  PYTHONPATH=src:/private/tmp/dms06-von-source/.venv/lib/python3.14/site-packages \
    poetry run pytest -q
  ```
  `poetry run ruff check src tests` and `git diff --check` passed.
- [x] Update `model-evaluation.md` with candidate decisions and exact manual
  evidence. This records validation for the initial DMS-01 through DMS-06
  implementation slice only; it does not complete or promote the whole feature.
  Record any rejected/deferred model as such, not as supported.

## DMS-08 Laya-MLX Candidate Evaluation

- Depends on: the DMS-01 frozen fixtures, acceptance criteria, and evaluation
  harness; DMS-02 decision contract.
- [x] Resolve and record one exact candidate: source
  `mizorewww/laya-mlx@0a859518634112655cb97c745dbf04f5191aaf13`, MLX weights
  `aac6fef/laya-typed-decisions-mlx@28416e78cb26a239a4eabaa2e084904ec5e6cacb`,
  and provenance base
  `convaiinnovations/laya-typed-decisions@f9ab0b228f0fc0f14d873dbc99038f135c2da1b2`.
  Verify exact artifact availability, license, tokenizer, runtime and MLX
  requirements, model input limit, material digests, and the meaning/output
  shape of each supported Laya mode. Record evidence in `model-evaluation.md`;
  defer if identity, license, or output semantics cannot be established.
- [x] Add fake-backed tests in `tests/test_laya_mlx_dms08_runner.py` for
  preflight matching, exact source/model/runtime identity, input-only requests,
  representable output mapping, refusal on oversized inputs, offline inference
  after pinned materialization, and redacted outputs. Implement the manual
  runner at `tests/manual/run_laya_mlx_dms08.py` using a separately pinned
  isolated research runtime; it must not change DAR's `pyproject.toml` or
  `poetry.lock`, add a server, or create a production model binding.
- [x] Record the dated approved preflight before downloading weights or running
  inference. It passed for the exact source/runtime/artifacts, approved fixture,
  host capacity, and Metal availability. Run the isolated Poetry runtime on the
  approved frozen fixtures; record redacted predictions, tokenizer counts,
  aggregate metrics, latency, and peak memory in `evaluation/` and
  `model-evaluation.md`. The final run completed 240 cases with no invalid
  outputs or OOM but failed decision accuracy (0.685), retention F1 (0.625),
  and keep recall (0.50); the approved utility gain was +0.287. Apply the
  existing DMS-01 thresholds without modification. No production profile is
  admitted.

## DMS-09 MLX Runtime Compatibility Decision

- Depends on: DMS-08's pinned Laya-MLX source/runtime requirements.
- [x] Resolve whether Laya-MLX's required MLX range can coexist with DAR's
  current `mlx` extra (`mlx-lm>=0.31.3,<0.32.0`) and `mlx-embedding` extra
  (`mlx==0.32.2` on Darwin). Prefer an isolated Laya-specific optional extra or
  runtime when that preserves existing consumers; change a shared MLX range
  only if compatibility is demonstrated for the existing generation and
  embedding paths.
- [x] Record the chosen dependency boundary, supported Python/macOS/Apple
  Silicon matrix, and lockfile ownership in `model-evaluation.md`. The isolated
  evaluation runtime uses its own Poetry lock; this task made no changes to
  DAR's root `pyproject.toml` or `poetry.lock`. The exact tested combination is
  Python 3.14.7, arm64, macOS 26.6.2, and MLX 0.32.2.
  `poetry check --lock` and existing MLX generation/embedding contract tests
  pass. No upstream `uv.lock` is used.

## DMS-10 First-Party Laya-MLX Decision Adapter

- Archived context-management decision: DMS-08 failed the frozen DMS-01 quality
  gates, so this task does not admit Laya-MLX for context-management use.
  DMS-16 supersedes this task for optional client-facing workflow support and
  does not inherit its quality gate.
- [x] Record the context-management disposition: Laya-MLX failed decision
  accuracy and retention thresholds. Do not use it for context management
  unless those criteria are revisited. DMS-16 owns the separate client-workflow
  adapter decision.

## DMS-11 Laya-MLX Validation and Handoff

- Depends on: DMS-08 and DMS-09. Include DMS-10 adapter checks only if DMS-08
  passes the quality gates; otherwise validate the runner, unchanged binding
  surface, and the recorded deferred disposition.
- [x] Run the focused Laya-MLX runner, decision-contract, workflow binding,
  local-runner, capability, and existing MLX generation/embedding compatibility
  tests; then run the full test suite and Ruff. The adapter checks were
  correctly skipped because DMS-08 failed and DMS-10 remains deferred. Focused
  checks completed with 180 passed and 1 skipped; full validation completed
  with 2,901 passed, 4 skipped, 0 failed, and 7 deselected. Ruff, Poetry lock
  validation, and `git diff --check` passed. See `validation.md`.

  ```bash
  poetry run pytest tests/test_laya_mlx_dms08_runner.py \
    tests/test_decision_models.py \
    tests/test_workflow_model_execution_binding.py \
    tests/test_local_model_runners.py tests/test_capabilities.py \
    tests/test_mlx_models.py tests/test_mlx_embedding_dependency_contract.py -q
  poetry run pytest -q
  poetry run ruff check src tests
  ```
- [x] Reconcile `spec.md`, `plan.md`, `tasks.md`, and `model-evaluation.md` with
  the final Laya-MLX disposition. Keep the profile rejected/deferred because
  its frozen quality gates failed; do not promote the feature.

## DMS-12 Jev-Style 0.8B v3 Candidate Evaluation

- Depends on: DMS-01 frozen fixtures and criteria, DMS-02 contract, and the
  DMS-06 local-candidate review.
- [x] Review Jev-Style 0.8B v3 as a small direct-local candidate from the
  approved research references. Pin its MLX checkpoint, Qwen base, embedded
  scoring runtime, file digests, license, inference contract, and runtime
  requirements in `model-evaluation.md`. Treat upstream metrics as discovery
  evidence only; they do not establish DMS quality or production admission.
- [x] Add the fake-only-tested, candidate-specific runner at
  `tests/manual/run_jevstyle_dms12.py`. Pin and verify the 8-bit MLX model and
  scoring runtime, keep labels out of inputs, reject oversized inputs without
  truncation, use the candidate tokenizer for matched-budget retention, and
  emit only redacted predictions, token counts, and measurements. Use the
  in-process runtime directly; do not start or add a model server.
- [x] Add an isolated Poetry runtime at
  `specs/decision-model-support/evaluation/jevstyle-mlx-runtime/`. Record its
  exact package lock and dated preflight. After approval, regenerate a passing
  preflight that confirms the frozen fixture, pinned model/runtime files,
  available storage, and Metal availability.
- [x] Obtain approval for the exact Jev-Style source/model/runtime pairing,
  run all frozen DMS-01 cases, and record aggregate metrics and the
  accept/reject/defer decision. Jev-Style completed 240 cases with no run
  failures but did not pass the frozen quality thresholds; see the receipt and
  result in `model-evaluation.md`. The runner now downloads and verifies the
  checkpoint's required `NOTICE` file as well as the pinned model artifacts.

## DMS-13 End-to-End Context Compression Evaluation

- Depends on: DMS-05 compaction behavior and the DMS-01 evaluation harness
  conventions. This track evaluates downstream preservation and does not
  change DMS-01's frozen synthetic fixtures or thresholds.
- [x] Review the official [LongMemEval paper](https://arxiv.org/abs/2410.10813)
  and [repository](https://github.com/xiaowu0162/LongMemEval); pin the cleaned
  LongMemEval-S data revision and digest, verify dataset license/usage terms,
  inspect its evidence-turn annotations and
  official answer-scoring procedure, and record any scoring limitations.
  LongMemEval-S is the initial benchmark because it contains long timestamped
  assistant/user histories and covers information extraction, multi-session
  reasoning, temporal reasoning, knowledge updates, and abstention. Do not
  silently substitute a different benchmark revision. The pinned dataset,
  digest, terms, annotations, and scorer limitations are recorded in
  `evaluation/dms13-corpus-manifest.json`.
- [x] Define the end-to-end comparison before any candidate output is
  inspected: replay each history using full history where it fits, deterministic
  recency at matched budgets, and the actual DAR model-guided message-selection
  compaction at those same budgets. Use one exact downstream answer model and
  answer-generation configuration for every condition. Define feasible token
  budgets using that answer model's tokenizer, reserve fixed prompt and question
  tokens from its context window, and report full-history cases that exceed its
  context window separately. Exact tokenizer measurements and proposed matched
  budgets are recorded in the manifest. The combined direct-local runtime is
  pinned and installed in `/private/tmp/dms13-poetry-envs`; exact host preflight
  passed and is recorded in `evaluation/preflight-dms13-run-2026-09-28.json`. No
  local model server is part of the profile.
- [x] Define answer metrics, evidence-turn recall from the benchmark's released
  `has_answer` annotations, retained-token ratio, per-question-category
  reporting, and runtime/memory measurements. The official scorer options and
  their external-egress/server limitations are recorded. Keep questions, gold
  answers, and evidence annotations out of compactor inputs.
- [x] Select a reproducible answer-scoring method. Use the pinned
  `mlx-community/Llama-3.1-8B-Instruct-4bit@90215b22ec18e72f623dde2ea7af4097025160e2`
  in-process through MLX-LM, with the pinned LongMemEval prompt and ten-token
  verdict limit. The model snapshot's eight files are SHA-256 pinned in the
  manifest. This is not the official Llama 3.1 70B or GPT-4o scorer and is not
  directly comparable to their published results. The user requested the
  switch to this local model; the exact run remains separately gated below.
- [x] Propose context-preservation acceptance thresholds based on the selected
  downstream workflow risk and record the exact proposal in
  `evaluation/dms13-corpus-manifest.json`. These thresholds are separate from
  the already-approved DMS-01 criteria.
- [x] Obtain run-level approval for the then-current exact benchmark, answer
  model, compactor, runtime, local Llama scorer/artifacts, budgets, thresholds,
  and greedy-sampler harness before benchmark inference. That approved run
  lasted over 17 hours, then exited with `ManualRunError` after a 9,380-token /
  8,192-token warning. The harness did not preserve the exception message, so
  the cause is unknown. It produced no result directory or usable predictions;
  the approval does not cover the revised resumable harness. See
  `model-evaluation.md` and retain the historical receipt in
  `evaluation/dms13-run-approval-2026-09-28.json`.
- [x] Add fake-only tests for benchmark loading/identity, history-only
  compactor inputs, gold/evidence isolation, matched answer-tokenizer budgets,
  baseline parity, scoring aggregation, and redacted receipts. Implement the
  narrow evaluation harness without adding a general benchmark framework or
  invoking real models in unit tests. The executable candidate path is
  `tests/manual/run_context_compression_dms13.py`; fake tests cover its
  question-blind Von scoring, exact packed-input limit, approval binding, and
  refusal before model-cache creation; tests perform no real model inference.
- [x] Make the manual harness restartable: process fixed ten-item progress
  chunks, atomically persist each complete item's nine redacted prediction
  rows, record resumable in-progress state and periodic Von-score progress,
  skip verified successes on restart, retry unfinished items once, and require
  a complete verified checkpoint set before inference-free `--merge`. Bind
  these choices into the approval expectation and run identity. Focused fake-
  only tests cover checkpoint recovery, corrupt-output rejection, progress,
  and refusal to merge partial results.
- [x] Shelve the proposed 60-item pilot and full-corpus DMS-13 evaluation per
  the user's 2026-09-30 decision. Use published LongMemEval results as external
  context only; make no DAR-specific compression-quality claim. The approved
  checkpointed run remains stopped after 12 complete items; preserve its
  approval and partial checkpoints as historical artifacts. Reopen this task
  only after an explicit new decision and obtain an exact approval before any
  further inference.

## DMS-14 Published General Decision Transfer and Mac Runtime Comparison

- Depends on: DMS-01, DMS-02, DMS-06, and DMS-08. This track compares general
  typed-decision transfer separately from the synthetic DMS-01 fixtures and
  end-to-end DMS-13 context compression.
- [x] Review the [Kev `transfer-v4` suite](https://github.com/jaredpalmer/kev)
  and freeze its development split as the primary corpus. Apply the user's
  explicit 2026-09-27 direction to exclude all 80 `tweet_offensive` items
  before normalization for every candidate; record the exclusion reason, count,
  and excluded-ID digest while retaining the upstream full-split hash. Verify and record the
  exact upstream revision, suite/item hashes, license and usage terms, task
  schemas, and task-to-DMS-contract mapping in
  `evaluation/dms14-corpus-manifest.json`. Determine one common set of task
  categories all candidates can represent before inspecting candidate outputs;
  exclude unsupported categories for every candidate and record them. Stop if
  split, license, or mapping cannot be established; do not substitute a
  different corpus in this task. The selected corpus has 684 items in seven
  categories; source terms, task mappings, the full split identity, selected
  input/gold hashes, and the excluded-ID digest are recorded in the manifest.
- [x] Freeze the complete candidate cohort and protocol in `model-evaluation.md`
  before inference. Include only exact completed local evaluations already
  recorded there: Kev-0.6B, Kev-0.8B, Von 1.2.0, PoorJev, LitJev, and Laya-MLX.
  Exclude server-backed Laya, candidates not run, and Jev-Style because it had
  not completed DMS-12 when this matrix cohort was frozen. Pin every
  source/model/tokenizer/runtime
  revision and list unsupported pairs before approval; do not add or remove
  candidates after approval.
- [x] Define a versioned scoring protocol in `model-evaluation.md`: per-task
  accuracy and an equally weighted macro average across common categories;
  count invalid, missing, and abstaining answers as incorrect; report exact
  denominators and exclusions. Measure option-order sensitivity by comparing
  canonical and reversed option order for each choice item. Estimate paired
  95% confidence intervals by 10,000 stratified bootstrap resamples of item IDs
  within task, using the same sampled IDs for every candidate and a fixed seed
  recorded in the protocol. Report probability calibration only on common items
  with semantically comparable probability outputs; do not fit calibration on
  the evaluation items. Set general-transfer thresholds to macro accuracy >=
  0.75 and per-category accuracy >= 0.40; do not reuse DMS-01 retention
  thresholds. The cohort and protocol were approved once for the complete
  matrix; see the dated approval
  receipt under `evaluation/`.
- [x] Add `tests/manual/run_dms14_transfer.py` and fake-only
  `tests/test_dms14_transfer_runner.py` for the proposed in-process matrix. Add
  `scripts/evaluate_decision_transfer.py` and fake-only
  `tests/test_decision_transfer_evaluation.py` for corpus hashes, label/input
  isolation, task mapping, scoring, aggregation, and redacted receipts. Keep
  this benchmark-specific; do not generalize or alter the DMS-01 harness.
  Implementation is present and fake-tested. All 80 TweetEval items are
  excluded before normalization for every candidate.
- [x] Validate the fake-only runner and evaluator, run Ruff, and preflight every
  candidate/runtime row in the proposed matrix. Record the exact harness/source
  revisions, artifacts, runtimes, resource requirements, and any rows that
  cannot run in `model-evaluation.md`. A failed row must be excluded or resolved
  before the matrix is frozen; do not substitute a different artifact/runtime.
  Run CPU only where a candidate supports it and MLX only where supported on
  the target Mac; do not require a CPU path for an MLX-only candidate. Focused
  tests and Ruff pass. All six pinned source/runtime/artifact rows, offline
  artifact resolution, exact tokenizer feasibility for the 684 selected items,
  and M3 Pro Metal availability pass; see
  `evaluation/preflight-dms14-matrix-2026-09-27.json`.
- [x] Obtain one approval for the exact corpus manifest, complete runnable
  candidate/runtime matrix, scoring protocol, thresholds, harness revisions,
  and run. This single matrix approval covers every listed row; do not request
  per-model approvals. No model-runtime installation, candidate-weight
  download, or inference before this approval; do not retrain or tune on the
  evaluation items. The recorded receipt binds the exact matrix and corpus
  manifest hashes to the one full-matrix approval.
- [x] On the Apple M3 Pro host, run every approved candidate/runtime row
  in-process against the same corpus items and protocol: CPU where the
  candidate supports it and MLX where supported. Record macOS, runtime,
  precision/quantization, cold/warm latency, peak memory, and failures. Report
  a changed precision/quantization as a separate candidate configuration with
  its own quality result. Run all rows whose frozen preflights passed; record
  post-approval runtime failures without substitution and limit rankings to
  candidates with complete results. All six rows completed; each produced
  1,368 predictions with zero failed outputs. Matrix receipt, measurements,
  predictions, and output digests are in
  `evaluation/dms14-run-2026-09-27/`.
- [x] Run the focused fake tests with
  `poetry run pytest tests/test_dms14_transfer_runner.py tests/test_decision_transfer_evaluation.py -q`,
  run `poetry run ruff check scripts tests`, and run the full
  worktree-authoritative validation command recorded under DMS-07 after
  implementation. Record commands/results, matrix
  receipt, and separate general-use and Mac-use recommendations in
  `validation.md` and `model-evaluation.md`. DMS-14 results are comparative
  evidence only: they cannot reverse DMS-01 or DMS-08 decisions, establish
  DMS-13 context-preservation quality, or admit a DAR production profile. The
  full suite completed with 2,932 passed, 4 skipped, and 7 deselected; Ruff
  and diff checks passed. No candidate met both DMS-14 thresholds.

## DMS-15 Reusable Decision-Model Adapter Helpers

- Depends on: DMS-02 and the completed candidate-runner reviews in DMS-06,
  DMS-08, and DMS-14. DMS-12 may add later evidence but does not block this
  audit.
- [x] Review the candidate inference paths and separate repeated contract
  translation from evaluation-only pinning, preflight, and artifact checks.
  Record the actual backends and duplicated logic in `validation.md`. Consider
  mapping option-ID keyed scores into request-ordered result items, but select
  a helper only if the same translation is repeated across at least two
  reviewed backends and is not already handled by contract validation. Record
  a no-change disposition when no such helper is demonstrated. The completed
  audit found only backend-specific evaluation translations; the shared
  contract already enforces runtime-neutral result invariants. No helper was
  selected. See the DMS-15 audit in `validation.md`.
- [x] **RED:** No helper was selected, so no helper tests apply. If a future
  audit selects one, add focused tests to `tests/test_decision_models.py` for
  declared option ordering, missing and unknown option IDs, invalid scores,
  explicit score semantics, and calibration evidence where applicable; confirm
  failure before implementation.
- [x] **GREEN:** No helper was selected, so no source/API change applies. If a
  future audit selects one, implement only the runtime-neutral translation
  proven by that audit in `src/dynamic_agent_runner/decision_models.py`. Keep
  model loading, vendor-specific request encoding/tokenization, calibration
  fitting, and score interpretation inside each adapter. Reuse existing
  contract validation and preserve the adapter protocol and result semantics.
  Record whether it is internal or caller-facing; public API requires updating
  `src/dynamic_agent_runner/__init__.py` and `docs/files/python-api.rst`.
- [x] Add a short fake-adapter example and record the selected helper or
  no-change evidence in `validation.md`. If implemented, exercise the helper
  with fakes representing at least two of the audited scoring styles. The
  no-change example uses the existing contract and result validator.
- [x] If source changes, run
  `poetry run pytest tests/test_decision_models.py -q`, the worktree-authoritative
  full test command recorded under DMS-07, and `poetry run ruff check src tests`.
  For this no-code outcome, the audit is recorded and `git diff --check` passed;
  tests and Ruff were not applicable.

## DMS-16 Optional Client-Facing Local Decision Backends (FR-4, FR-7, FR-10, FR-11)

- Depends on: the implemented DMS-02 contract and DMS-03 workflow node. DMS-01,
  DMS-06, DMS-08, DMS-12, and DMS-14 quality outcomes do not gate client
  workflow support; they continue to govern context-management suitability.
- Progress (2026-10-02, refreshed): adapter and fake-test slices now exist for exact Von,
  Julia 1, Laya-MLX, and Kev-0.6B/Qwen3 identities. Focused contract, host,
  compaction, runtime-import, adapter, preflight, and one-shot smoke-runner
  suites pass (334 tests), including binding-time rejection of identity
  mismatches and `context_retention` for workflow-only
  backends. Root extras `von`, `julia1`,
  and `laya-mlx` each installed independently from the shared Poetry lock
  `6b723941863f3c9fd72db50dc359d3e4ffa78092e1402e6e48328374766b924a`; Julia
  and Von package imports pass, and Laya's load-only import initialized Metal
  when run outside the sandbox. The Julia extra pins Tokenizers <=0.23.0 to
  satisfy Transformers 5.0.0. Kev has no root extra because its pinned Torch
  `<2.9` requirement conflicts with DAR's current `>=2.9` optional dependency.
  The focused fake suite, including material-manifest and smoke-runner tests,
  passed with 334 tests; Ruff, `poetry check --lock`, and `git diff --check`
  passed. The post-download preflight verifies all 29 pinned model/runtime
  files. SHA-256 digests are pinned for Julia's default Torch runtime source,
  and source review confirms local checkpoint paths with
  `trust_remote_code=False`. Julia 1 and Laya-MLX passed their approved
  compatibility smokes. Von's first smoke exposed that the shared Poetry lock
  selects incompatible Transformers 5.0.0; its successful retry used the
  exact upstream Von lock with Transformers 5.17.0. The runner now records
  exception type, message, traceback, and stage, and uses separate numbered
  attempt receipts. The three
  installable extras were also installed independently on Python 3.13.16;
  package imports passed, including Laya-MLX's load-only Metal import outside
  the sandbox. Kev-0.6B is deferred because its upstream Torch cap conflicts
  with DAR's declared Torch range. The DMS-07 full suite also passes with
  3,029 passed, 4 skipped, and 7 deselected.
- Adapter/runtime targets: `von_decision_adapter.py` / extra `von` /
  `test_von_decision_adapter.py`; runtime import isolation in
  `test_decision_adapter_imports.py`; `julia1_decision_adapter.py` / extra
  `julia1` / `test_julia1_decision_adapter.py`;
  `laya_mlx_decision_adapter.py` / extra `laya-mlx` /
  `test_laya_mlx_decision_adapter.py`; and `kev_decision_adapter.py` /
  `test_kev_decision_adapter.py` (no root extra while its Torch conflict is
  unresolved). Each available extra was resolved with `poetry lock` and
  installed separately using
  `POETRY_VIRTUALENVS_IN_PROJECT=false POETRY_VIRTUALENVS_PATH=/private/tmp/dms16-poetry-<row> poetry install --only main --no-root --extras <extra>`;
  the Julia install additionally requires
  `tokenizers>=0.22.0,<=0.23.0`. Focused tests run with
  `POETRY_VIRTUALENVS_IN_PROJECT=false poetry run env PYTHONPATH=src pytest <test-file> -q`.
  The combined fake-test command is recorded in `validation.md`. The
  adapter-facing runner is `tests/manual/smoke_dms16.py`; obtain its exact
  per-profile approval digest with `--print-scope`, then invoke it only after
  matching approval. Its fake tests are in `tests/test_dms16_smoke_runner.py`.
  The runner stages only the frozen file allowlist and verifies it before
  loading offline. Approved materials and smoke outcomes are recorded below.
- [x] Resolve and freeze a closed profile/material/runtime row list before
  RED/GREEN work. Start from the evaluated Von 1.2.0 and Laya-MLX candidates,
  the Julia 1 candidate (`SupersonicLabs/Julia-1`), and selected Kev/Qwen
  checkpoints; do not describe Julia 1 as already evaluated or admitted. Each
  row records candidate/admitted/deferred state, source and model revisions,
  licenses, platform/runtime support, input limits, output semantics,
  declared dependency closure, and material digests. Do not broaden support to
  arbitrary Von, Julia, Laya, or Qwen models.
  For Julia 1 specifically, identify and pin every model-specific executable
  runtime/code source and digest, confirm license and local controlled loading,
  and prove the run needs neither remote-code loading nor dynamic code fetch;
  defer Julia if that boundary cannot be established. Confirm bounded choice,
  ordered-score, and yes/no-probability output semantics before admitting a
  row.
- [x] Define isolated optional extras for the supported runtimes in
  `pyproject.toml`; keep model stacks out of DAR's default/core dependencies.
  Verify each extra resolves in the Poetry lock and installs independently
  within the supported Python range. Record conflicts rather than widening
  shared dependency constraints without compatibility evidence. A conflict
  defers only its own profile row.
  Before RED/GREEN, complete each row's technical admit/defer decision and
  record its exact Python/platform and Poetry-lock dependency resolution. For
  Julia, resolve the exact Transformers version under `<5.1` without widening
  the shared default/core range. Name the adapter module, optional-extra name,
  focused test file, and exact Poetry resolve/install and focused-test commands;
  use `src/dynamic_agent_runner/workflow_host/julia1_decision_adapter.py` and
  `tests/test_julia1_decision_adapter.py` unless row review records a justified
  alternative. A deferred row has no RED/GREEN work and does not block others.
- [x] **RED:** Add fake-backed adapter and binding tests for each exact profile:
  request/result mapping, identity mismatch, unsupported mode, input/output
  limits, cancellation/deadline behavior, offline material loading, adapter
  errors, and redacted traces. Require an explicit `workflow_decision` use
  declaration and test that host admission rejects DMS-16 profiles for
  `context_retention` before inference. Include Laya `noul` cases for exact
  `yes`/`no` score mapping, request-order complement, malformed probabilities,
  rejection of `calibrated_probability` without pinned calibration evidence,
  and every unsupported request shape. For Julia, cover declared-option-only
  choice results; option-ID score mapping in request order with explicit
  ranking/probability semantics; and `noul` only for the exact two option IDs
  `yes` and `no`, including complement, option order, finite `[0, 1]` checks,
  malformed/unknown/unsupported shapes, and rejection of calibrated semantics
  without pinned calibration evidence. Verify model-specific runtime code is
  loaded only from the row's pinned local materials, no remote-code path is
  enabled, and each optional runtime is not imported unless selected.
  Observe failures before implementation.
- [x] **GREEN:** Implement each technically admitted row as a separately
  completable adapter slice in the row's recorded module/test targets, through
  the existing `DecisionModelAdapter` contract and host execution boundary.
  Preserve in-process execution, explicit profile selection, exact material
  binding, host-owned resource/lifecycle controls, and no fallback. Bind each
  profile as `workflow_decision`; host admission must reject
  `context_retention` use before inference. A deferred row has no GREEN work
  and does not block other admitted rows.
  Do not put model loading, tokenization, or score interpretation in the
  generic contract.
- [x] Run the named focused fake tests and Poetry dependency-resolution/install
  checks for each optional extra independently. The DMS-16 focused suite passes
  (334 tests); each installable extra resolved and installed independently on
  Python 3.13 and 3.14. The DMS-07 full suite passes (3,029 passed, 4 skipped,
  7 deselected), and Ruff, `poetry check --lock`, and `git diff --check` pass.
- [x] Download only the approved, immutable model/runtime allowlists and pass
  the exact-material preflight. The post-download receipt verifies all 29 files,
  Julia runtime-source hashes, runtime package versions, and the shared lock.
- [x] Run one approved synthetic, offline-after-staging compatibility smoke
  each for Julia 1 and Laya-MLX. Both returned contract-valid results and are
  admitted for optional `workflow_decision` use only. See their redacted
  receipts in `evaluation/` and the per-profile approval scopes in
  `validation.md`.
- [x] Diagnose and resolve the Von compatibility smoke. The shared Poetry
  extra selected Transformers 5.0.0, which failed in ModernBERT attention-mask
  expansion. The smoke runner now records actionable exception details and
  supports separately scoped attempts. Re-running once with the pinned Von
  source `uv.lock` (Transformers 5.17.0) returned a contract-valid result in
  1,062.933 ms. Von is admitted for `workflow_decision` with that profile
  runtime; the shared-lock `von` extra is not compatible for inference.
  Receipts and runtime evidence are linked in `validation.md`.
- [x] Record technical support status independently from context-management
  quality status in `model-evaluation.md` and `validation.md`. Record a separate
  support/defer disposition for each frozen profile row. Do not enable any
  workflow-decision-only adapter for compaction or context management until the
  relevant quality criteria are revisited and passed. Current dispositions are
  explicit: Von, Julia 1, and Laya-MLX are admitted for `workflow_decision`
  with their recorded profile runtimes; the shared-lock `von` extra remains
  incompatible for inference. Kev-0.6B/Qwen3 is deferred for the dependency
  conflict. No profile is admitted for `context_retention`.

## DMS-17 Optional Jev-Style v3 Machine-Selected Adapter

- Depends on: the DMS-02 decision contract, DMS-16 optional-backend admission
  boundary, and the exact DMS-01 Jev-Style v3 MLX, PyTorch BF16, and GGUF F16
  evidence. DMS-01 quality results do not gate client workflow use; none of
  these profiles is admitted for `context_retention`.
- [x] Pin the three model identities and artifact revisions from the DMS-01
  additions matrix: `chaoliangUNSW/Jev-Style-0.8B-Decision-v3-MLX` revision
  `1235ccd1c95d5228a07616cd7e323c9e0532c1dc` for Apple Silicon/Metal,
  `chaoliangUNSW/Jev-Style-0.8B-Decision-v3` revision
  `b023d1f9c7858fbf01504577a3bfc349ea5c7385` for PyTorch BF16, and
  `chaoliangUNSW/Jev-Style-0.8B-Decision-v3-GGUF` revision
  `edf37c26a1098f83cf4264b8adbe0dca2d2ebb0c` for GGUF F16 CPU.
- [x] Record each profile's runtime, license, local material manifest,
  supported input limit, adapter identity, and host resource-budget admission
  policy in `evaluation/jevstyle-v3-dms17-profile-admission.json`. Keep
  optional backend dependencies isolated. Current file availability is tracked
  separately in the DMS-17 preflight.
- [x] Define and fake-test the opt-in selector over the exact DMS-01 profiles.
  “Best” is the fixed pre-load preference MLX/Metal on Apple Silicon, then
  GGUF F16 CPU, then PyTorch BF16 CPU, filtered by host capabilities, exact
  local materials, and host resource-budget admission. This reflects DMS-01's
  measured warm-inference advantage of GGUF over PyTorch on the tested Mac; it
  is not a startup benchmark. The frozen PyTorch row is CPU-only; CUDA is
  deferred until a separate exact CUDA profile is reviewed and admitted. Skip
  only profiles unavailable before loading; bind the selected profile to its
  sealed `ModelExecutionBinding`; never switch after load or inference failure.
  Selection does not scan arbitrary paths or download weights.
- [x] **RED/GREEN:** Add
  `tests/test_jevstyle_decision_adapter.py` before implementing
  `src/dynamic_agent_runner/workflow_host/jevstyle_decision_adapter.py`.
  Cover deterministic selection, unavailable/no-eligible candidates, selected
  identity and sealed material binding, `choice` and ordered `scores` mapping,
  constrained `noul` mapping, lazy unselected loaders, and no fallback after
  load or inference failure. The adapter invokes only the selected host loader
  and does not import an optional runtime itself.
- [x] Extend the host-boundary tests for Jev-Style runtime/material admission,
  declared-option validation, error/redaction behavior, resource limits,
  cancellation/deadline, and `workflow_decision`-only use. Fake tests confirm
  unadmitted/missing materials never invoke a loader; the selector itself has
  no download path.
- [x] Resolve and install the three backend runtimes independently in isolated
  Poetry environments that also install DAR's core package. Record exact lock
  hashes in the admission ledger and run:

  ```sh
  poetry run pytest tests/test_jevstyle_decision_adapter.py tests/test_workflow_model_execution_binding.py -q
  poetry run ruff check src/dynamic_agent_runner/workflow_host/jevstyle_decision_adapter.py tests/test_jevstyle_decision_adapter.py tests/test_workflow_model_execution_binding.py
  ```

  Adapter and runtime imports pass in the exact isolated environments.
- [x] Revalidate exact materials and run one offline model load plus one
  synthetic choice through the adapter for each compatible profile, after its
  exact material preflight and separate run authorization. The bounded smoke
  harness is `tests/manual/smoke_jevstyle_dms17.py`, guarded by the approved
  scope-bound receipt. GGUF F16 CPU and PyTorch BF16 CPU each completed one
  inference; their receipts are in the evaluation folder. MLX material hashes
  matched, but its loader requires upstream `manifest.json`, which was absent
  from the approved material list, so no MLX inference occurred. Record that
  profile as deferred and obtain approval on an updated material/scope before
  retrying it. DMS-01 receipts remain quality evidence, separate from runtime
  compatibility evidence.
- [x] Record per-backend technical admit/defer outcomes separately from the
  DMS-01 quality result in `evaluation/jevstyle-v3-dms17-profile-admission.json`.
  GGUF, PyTorch, and MLX are admitted for `workflow_decision` only. None is
  enabled for context retention.
