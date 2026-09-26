# Decision Model Support Tasks

Source of truth: `spec.md`. Implementation approach: `plan.md`.

Tasks are ordered by dependency. Every code task follows TDD: add or update the
focused test first, observe the expected failure, implement, and rerun until it
passes. Do not use real model weights in unit tests.

## DMS-01 Candidate Evidence Gate

- [ ] Evaluate the named Qwen candidates (Kev Qwen2.5 0.5B, 0.6B, 4B, and 8B;
  Bespoke Nimble Qwen3.5 9B) and Laya's 421M model. Verify primary repositories
  and model cards; record exact model IDs/revisions, license, task/output
  contract, inference format, runtime, supported input length, and required
  memory in `model-evaluation.md`.
- [ ] Freeze a labeled decision/retention evaluation set and its acceptance
  criteria before inspecting candidate results. Use non-sensitive fixtures;
  do not ingest user transcripts without separate authorization. Get user
  approval of the evaluation set and criteria before any real-model run.
- [ ] Run local competency measurements only for exact artifacts and runtimes
  allowed by the host. Record accuracy/retention quality, calibration metrics
  when claimed, latency, and peak memory. Compare compaction retention at a
  matched token budget with the deterministic baseline.
- [ ] Select an exact Qwen profile only if it passes the recorded criteria and
  can be admitted through the reviewed DAR local runner and material lock.
  Otherwise stop DMS-04 and ask for user direction. Completion evidence is the
  model evaluation report and an explicit candidate decision.

## DMS-02 Decision Contract (FR-1, FR-3, FR-6)

- [ ] **RED:** Add `tests/test_decision_models.py` for valid choice/score
  requests and invalid mode, duplicate/missing question, unknown option,
  missing/duplicate score, NaN/infinity, unsupported score semantics, input
  and result limits, absent calibration evidence, explicit abstention, and
  adapter identity cases. Confirm the missing contract causes the tests to fail.
- [ ] **GREEN:** Implement the typed adapter, request, result, and profile
  contracts in `src/dynamic_agent_runner/decision_models.py`; export only the
  intended public types from `src/dynamic_agent_runner/__init__.py`. Keep model
  runtimes outside DAR core.
- [ ] Rerun the focused contract tests and Ruff on changed source/tests.
  Completion evidence: passing contract test output and public API review.

## DMS-03 Workflow Decision Node (FR-2)

- Depends on: DMS-02.
- [ ] **RED:** Add validation and executor tests for a one-question decision
  model `decision_step`, exact choice-to-edge routing, missing/unsupported
  profile, invalid result, unmapped option, and adapter failure. Confirm each
  new behavior fails before implementation.
- [ ] **GREEN:** Update `src/dynamic_agent_runner/models.py`,
  `src/dynamic_agent_runner/validation.py`, and
  `src/dynamic_agent_runner/executor.py` to validate the subtype, resolve the
  exact runtime binding, and route only to the mapped edge.
- [ ] Rerun `tests/test_validation.py` and `tests/test_executor.py` plus the
  focused new cases. Completion evidence: tests prove existing `llm_route`
  behavior remains valid and decision-model failures never choose a default
  edge.

## DMS-04 Qwen Local Profile (FR-4)

- Depends on: DMS-01 and DMS-02.
- [ ] **RED:** Add fake-backed binding tests for the selected Qwen profile,
  immutable base/adapter materials, unsupported revisions/runtimes, and
  profile mismatch. Confirm rejected profiles fail before materialization or
  model loading.
- [ ] **GREEN:** Bind the selected Qwen decision adapter through
  `src/dynamic_agent_runner/workflow_host/model_execution_binding.py`,
  `src/dynamic_agent_runner/workflow_host/local_model_runners.py`, and
  `src/dynamic_agent_runner/workflow_host/capabilities.py`, reusing the exact
  host resource and lifecycle boundaries. Do not add fallback profiles.
- [ ] Rerun `tests/test_workflow_model_execution_binding.py` and
  `tests/test_local_model_runners.py`. Complete the separately authorized
  local competency check for the exact profile; record its artifact and runtime
  receipt in `model-evaluation.md`.

## DMS-05 Internal Compaction Scoring (FR-5, FR-6)

- Depends on: DMS-02 and DMS-04.
- [ ] **RED:** Add executor/compaction tests showing that low scores cannot
  remove pinned instructions, recent turns, unresolved state, or tool-call /
  result pairs, and that invalid, missing, abstaining, and timed-out results
  never authorize deletion. Confirm failure before implementation.
- [ ] **GREEN:** Add opt-in keep/drop scoring to
  `src/dynamic_agent_runner/context_compaction.py` and its call path in
  `src/dynamic_agent_runner/executor.py`. Keep candidate scoring separate from
  deterministic retention protections, configured fallback, and truncation.
- [ ] Rerun focused compaction and executor tests. Completion evidence includes
  retained-boundary tests and redacted trace assertions.

## DMS-06 Other Candidate Evaluation

- Depends on: DMS-01 evaluation method and DMS-02 contract.
- [ ] Evaluate von, poorjev, NanoJev, and LitJev against the same request/result
  contract and task metrics. Record primary-source identity, exact revision,
  calibration claims/evidence, runtime and license constraints, measured
  resource use where a permitted local run is practical, and accept/reject/
  defer rationale in `model-evaluation.md`.
- [ ] Add support only for a candidate that passes the recorded criteria and
  receives a scoped follow-up; do not expand the initial Qwen profile task.

## DMS-07 Final Validation and Handoff

- Depends on: DMS-03 through DMS-06.
- [ ] Run focused validation:

  ```bash
  poetry run pytest tests/test_decision_models.py tests/test_validation.py \
    tests/test_executor.py tests/test_workflow_model_execution_binding.py \
    tests/test_local_model_runners.py tests/test_capabilities.py -q
  ```

- [ ] Run full validation: `poetry run pytest -q` and
  `poetry run ruff check src tests`.
- [ ] Update `model-evaluation.md` with candidate decisions and exact manual
  evidence; update `spec.md` and `specs/README.md` from proposed to implemented
  only when all acceptance criteria pass. Record any rejected/deferred model
  as such, not as supported.
