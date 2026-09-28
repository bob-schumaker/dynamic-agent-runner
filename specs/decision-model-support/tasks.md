# Decision Model Support Tasks

Source of truth: `spec.md`. Implementation approach: `plan.md`.

## Readiness Review

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
  - **Disposition:** The task list is ready under its stated gates. DMS-15's
    audit can proceed; helper implementation depends on demonstrated reuse.
    DMS-04 remains stopped, DMS-10 remains deferred, and DMS-12/DMS-13 retain
    their separate approval and benchmark gates.

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
  Kev-0.6B, Kev-0.8B, Von, PoorJev, and LitJev failed one or more required
  quality gates. NanoJev remains deferred for host and licensing constraints.
  No candidate is recommended. Stop before DMS-04 until a future candidate or
  criteria change is approved.
- [x] Run the approved Kev-0.8B candidate-specific evaluation on the frozen
  DMS-01 fixtures and record its exact preflight, predictions, token counts,
  measurements, and aggregate threshold results. It completed 240 cases and
  passed operations only; it does not qualify for DMS-04.

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
- [ ] **RED:** Add fake-backed binding tests for the selected Qwen profile,
  immutable base/adapter materials, unsupported revisions/runtimes, and
  profile mismatch. Prove no network fetch, remote-code execution, or
  substitute profile is used, and that host resource/deadline/cancellation
  limits are enforced. Confirm rejected profiles fail before materialization
  or model loading.
- [ ] **GREEN:** Bind the selected Qwen decision adapter through
  `src/dynamic_agent_runner/workflow_host/model_execution_binding.py`,
  `src/dynamic_agent_runner/workflow_host/local_model_runners.py`, and
  `src/dynamic_agent_runner/workflow_host/capabilities.py`, reusing the exact
  host resource and lifecycle boundaries. Do not add fallback profiles.
- [ ] Rerun `tests/test_workflow_model_execution_binding.py` and
  `tests/test_local_model_runners.py`. Complete the separately authorized
  local competency check for the exact profile; record its artifact and runtime
  receipt in `model-evaluation.md`. Make the production admit/reject decision
  only after both the DMS-01 candidate evidence and this exact DAR binding pass.

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
- [x] Add no alternative production support: Von, PoorJev, and LitJev failed
  the frozen quality thresholds, while NanoJev is deferred. Do not expand the
  initial Qwen profile task.

Frozen-fixture evaluation is complete for Von 1.2.0, PoorJev, and LitJev.
NanoJev is deferred for host and licensing reasons. Jev-Style 0.8B v3 is
tracked as a separate DMS-12 follow-on evaluation. No alternative production
support is added.

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

- Depends on: DMS-08 passing the frozen DMS-01 quality gates and DMS-09's
  runtime compatibility decision. If evaluation fails, record the disposition
  and leave implementation deferred.
- Disposition: deferred because DMS-08 failed decision accuracy and retention
  quality gates. Do not add a first-party profile, DAR dependency, or production
  admission for this candidate.
- [ ] **RED:** Add fake-backed tests in
  `tests/test_laya_mlx_decision_adapter.py` for exact profile/material/runtime
  binding, typed request translation, and context-limit rejection without
  truncation. Map Laya `choice` to one declared option and a complete Laya score
  vector to DMS `scores` only under the existing score-semantics rules. Cover
  `noul` probability endpoints and an interior value, malformed probabilities,
  reordered yes/no options, and missing calibration evidence. Map
  Laya `noul` only when the request and profile support `scores` and the
  question has exactly two options with stable `yes` and `no` IDs. Reject
  non-finite or out-of-range `p_yes` before computing its complement; map
  `p_yes` and `1-p_yes` by option ID and emit in request order. Use `probability`
  semantics when valid but uncalibrated; use `calibrated_probability` only when
  pinned calibration evidence satisfies the contract. Reject other `noul`
  shapes and prove it cannot satisfy a `choice` request. Test offline loading
  and host resource/deadline/cancellation enforcement. Prove no substitution,
  remote code, server lifecycle, or new public result mode is introduced.
- [ ] **GREEN:** Implement a focused in-process MLX decision adapter using
  DAR's `DecisionModelAdapter` boundary at
  `src/dynamic_agent_runner/workflow_host/laya_mlx_decision_adapter.py`, bound
  through the existing host model-execution and capability boundaries. Reuse
  the exact reviewed material and host lifecycle; do not route through the
  text-generation or embedding adapters.
- [ ] After fake binding and compatibility checks pass, record a candidate-
  specific preflight and obtain separate approval for the exact local
  competency run. Make and record an explicit production admit/reject decision
  against DMS-01 quality criteria and DMS-02/FR-7 binding requirements; do not
  infer admission from evaluation or adapter tests.

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
  exact package lock and dated preflight. The preflight confirms the frozen
  fixture, pinned model/runtime files, 36 GiB RAM, 70 GiB free storage, and
  Metal availability; it blocks only because candidate-specific run approval
  is absent. No model weights have been downloaded.
- [ ] Obtain separate approval for the exact Jev-Style source/model/runtime
  pairing, regenerate a passing preflight, then run and record the frozen
  DMS-01 metrics and accept/reject/defer decision.

## DMS-13 End-to-End Context Compression Evaluation

- Depends on: DMS-05 compaction behavior and the DMS-01 evaluation harness
  conventions. This track evaluates downstream preservation and does not
  change DMS-01's frozen synthetic fixtures or thresholds.
- [ ] Review the official [LongMemEval paper](https://arxiv.org/abs/2410.10813)
  and [repository](https://github.com/xiaowu0162/LongMemEval); pin the cleaned
  LongMemEval-S data revision and digest, verify dataset license/usage terms,
  inspect its evidence-turn annotations and
  official answer-scoring procedure, and record any scoring limitations.
  LongMemEval-S is the initial benchmark because it contains long timestamped
  assistant/user histories and covers information extraction, multi-session
  reasoning, temporal reasoning, knowledge updates, and abstention. Do not
  silently substitute a different benchmark revision.
- [ ] Define the end-to-end comparison before any candidate output is
  inspected: replay each history using full history where it fits, deterministic
  recency at matched budgets, and the actual DAR model-guided message-selection
  compaction at those same budgets. Use one exact downstream answer model and
  answer-generation configuration for every condition. Define feasible token
  budgets using that answer model's tokenizer, reserve fixed prompt and question
  tokens from its context window, and report full-history cases that exceed its
  context window separately.
- [ ] Define answer scoring, evidence-turn recall from the benchmark's released
  `has_answer` annotations, retained-token ratio, per-question-category
  reporting, and runtime/memory measurements. Use the official scorer where
  suitable; if it requires an external judge or incompatible runtime, resolve
  and approve a reproducible alternative before inference. Keep questions,
  gold answers, and evidence annotations out of compactor inputs.
- [ ] Propose context-preservation acceptance thresholds based on the selected
  downstream workflow risk, and obtain approval for the exact benchmark,
  answer model, scoring method, and thresholds before model inference. These
  thresholds are separate from the already-approved DMS-01 criteria; no
  numeric DMS-13 pass bar is assumed by this task.
- [ ] Add fake-only tests for benchmark loading/identity, history-only
  compactor inputs, gold/evidence isolation, matched answer-tokenizer budgets,
  baseline parity, scoring aggregation, and redacted receipts. Implement the
  narrow evaluation harness without adding a general benchmark framework or
  invoking real models in unit tests.
- [ ] After exact candidate-specific approval and passing preflight, run the
  approved model-guided compaction condition and baselines. Record exact
  dataset, answer model, compactor, runtime, scorer, budget, and harness
  revisions; publish aggregate metrics and disposition in `model-evaluation.md`.
  Do not infer DMS-01 passage or production admission from this track.

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
  Exclude server-backed Laya, candidates not run, and Jev-Style until DMS-12 is
  completed and separately scheduled. Pin every source/model/tokenizer/runtime
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
- [ ] Review the candidate inference paths and separate repeated contract
  translation from evaluation-only pinning, preflight, and artifact checks.
  Record the actual backends and duplicated logic in `validation.md`. Consider
  mapping option-ID keyed scores into request-ordered result items, but select
  a helper only if the same translation is repeated across at least two
  reviewed backends and is not already handled by contract validation. Record
  a no-change disposition when no such helper is demonstrated.
- [ ] **RED:** For each selected helper, add focused tests to
  `tests/test_decision_models.py` for declared option ordering, missing and
  unknown option IDs, invalid scores, explicit score semantics, and calibration
  evidence where applicable. Confirm the tests fail before implementation.
- [ ] **GREEN:** Implement only the runtime-neutral translation proven by the
  audit in `src/dynamic_agent_runner/decision_models.py`. Keep model loading,
  vendor-specific request encoding/tokenization, calibration fitting, and score
  interpretation inside each adapter. Reuse existing contract validation;
  preserve the current adapter protocol and result semantics. Decide and record
  whether the helper is internal or caller-facing; a public export requires
  updating `src/dynamic_agent_runner/__init__.py` and
  `docs/files/python-api.rst`.
- [ ] Add a short fake-adapter example and record the selected helper or
  no-change evidence in `validation.md`. If implemented, exercise the helper
  with fakes representing at least two of the audited scoring styles.
- [ ] If source changes, run
  `poetry run pytest tests/test_decision_models.py -q`, the worktree-authoritative
  full test command recorded under DMS-07, and `poetry run ruff check src tests`.
  For a no-code outcome, record the audit and run `git diff --check` only.
