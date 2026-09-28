# Decision Model Support Readiness Validation

Status: readiness review passed when authored; current execution status is
partial. See the implementation audit at the end of this file and the current
state in `spec.md` and `tasks.md`.

## Review scope

Reviewed `tasks.md` against `spec.md` and `plan.md` for scope, dependencies,
requirement coverage, test-first sequencing, task minimality, next action, and
validation. No implementation or model evaluation was performed.

## Council deliberation

- **Problem:** Determine whether the task list completely and minimally maps
  the decision-model spec and plan to executable work under their explicit
  gates.
- **Composition:** Aristotle, Ada, and Feynman (architecture triad).
- **Execution mode:** Parallel independent Council passes with a challenge
  round.
- **Unresolved questions:** None material to task readiness. Candidate
  evaluation outcomes and evaluation-set approval remain explicit DMS-01
  gates.
- **Recommended next step:** Begin DMS-01 candidate evaluation. Obtain approval
  of the labeled evaluation set and criteria before any real-model run.
- **Consensus or split:** Consensus that the original task list was not ready
  until contract, node, runtime-control, and compaction-policy coverage was
  explicit. The panel agreed DMS-05 must no longer depend on Qwen admission
  (DMS-04). On its remaining dependency, Ada and Feynman favored DMS-02 alone;
  Aristotle favored DMS-02 and DMS-03 because DMS-03 owns the shared executor
  binding path. The task list retains DMS-03 as a dependency so DMS-05 can reuse
  that binding instead of introducing a second dispatch path.
- **Key insights by member:**
  - Aristotle: The candidate-evaluation, contract, workflow, Qwen, and
    compaction tasks are distinct work classes with an explicit dependency
    order. Candidate selection must remain evidence-gated and must not be
    conflated with implementation readiness. Keep DMS-05 after DMS-03 to reuse
    its generic executor binding, but remove its DMS-04 dependency.
  - Ada: The contract's identity, option, and score invariants, safe node
    references, caller-adapter boundary, and cancellation/redaction behavior
    need named observable checks. Do not duplicate every detail already
    specified in `spec.md` without improving task-level traceability.
  - Feynman: The gaps can be stated as concrete counterexamples: a package
    must not smuggle adapter code, batch boundaries must not change message
    identity, and missing policy must not turn a score into deletion authority.
    Cancellation, deadline expiry, and redacted errors/traces require their
    own integration checks.
- **Points of disagreement:** Ada and Feynman judged generic compaction
  dependent only on DMS-02; Aristotle noted DMS-05 changes the executor call
  path and should reuse the exact dispatch binding established in DMS-03. The
  retained DMS-03 dependency is a bounded sequencing choice that avoids a
  second binding path; no Council member required Qwen admission before the
  generic compaction safeguards.
- **Confidence and caveats:** High for artifact-level scope and task coverage;
  model capability remains unverified by design until DMS-01. The review does
  not claim implementation correctness or empirical model performance.
- **Follow-up:** Reassess DMS-04 only after the recorded candidate decision;
  stop and request user direction if no exact Qwen profile passes.

## Ponytail review

Ponytail: **Lean already. Ship.** No task should be removed: each maps to a
stated contract, isolation boundary, evaluation gate, safety invariant, or
named validation command. The added checks fit the existing task groups.

## Task-list readiness verification

- DMS-01 defines candidate evidence, pre-registered evaluation criteria,
  non-sensitive fixtures, a user approval gate before real-model runs, and a
  stop condition if no Qwen candidate passes.
- DMS-02 through DMS-06 map to FR-1 through FR-6 and preserve the spec's
  client-adapter, exact-profile, fail-closed, compaction-retention, and
  evaluation boundaries. DMS-03 names node shape, exact adapter binding,
  host-stricter limits, cancellation/deadline, and redacted error/trace checks.
- DMS-04 retains Qwen profile/material admission and now explicitly rejects
  fetch, remote code, substitute profiles, and violations of host lifecycle
  limits. DMS-05 uses fake profiles and does not wait for DMS-04.
- Every implementation task has a RED step before GREEN implementation, in
  line with repository TDD instructions.
- DMS-07 names focused and full test/lint commands and limits promotion to
  implemented status to passing acceptance criteria.
- The next action is discovery/evaluation (DMS-01), not source mutation. Real
  model runs remain gated on the specified evaluation-set approval and host
  allowance.
- `git diff --check`: passed.

This plan is ready to execute under its stated gates.

## DMS-14 Implementation Progress — 2026-09-27

Implemented the corpus-specific normalizer/scorer and fake-tested in-process
matrix runner. Corpus preparation verifies the pinned Kev split and upstream
manifest, keeps gold labels in a separate file, and hashes normalized inputs
and labels. The runner evaluates canonical and reversed option orders, writes
redacted result rows, and checks a single matrix-level approval against the
exact corpus manifest and pinned harness files. Matrix orchestration requires
successful preflight for every row before starting, then invokes all rows
sequentially under that one approval; it does not ask for per-model approval.
Before loading each candidate, the runner rechecks every approved artifact's
size and SHA-256 and forces Hugging Face access offline.

The upstream split has 764 items. By explicit user direction, all 80
`tweet_offensive` items are excluded before normalization for every candidate;
the selected corpus has 684 items across seven categories. The raw split hash,
selected input and label hashes, and excluded-ID digest are recorded. Included
sources are reviewed for local noncommercial research use, including Emotion's
research-only terms and QNLI/SQuAD CC BY-SA 4.0 attribution/share-alike terms.
The legacy/composition holdouts are generated by code at the pinned Kev
revision, whose repository license is Apache-2.0. The manifest records these
terms and scope.

The revised six-row matrix was approved once and executed on the Apple M3 Pro.
Approved thresholds were macro accuracy >= 0.75 and per-category accuracy >=
0.40. All six rows completed offline using pinned runtimes and digest-verified
cached artifacts. Each emitted 1,368 predictions for 684 items in two option
orders, with zero invalid, missing, abstaining, or failed outputs. The 80
`tweet_offensive` items were excluded before normalization from every row.

- Focused fake tests: 22 passed, including category exclusion before
  normalization, offline model access, and live artifact digest checks.
- Ruff on the new evaluator, runner, and tests: passed.
- Full matrix preflight:
  [`preflight-dms14-matrix-2026-09-27.json`](evaluation/preflight-dms14-matrix-2026-09-27.json)
  records source revisions/imports, runtime locks and packages, cached weight
  and calibration digests, offline artifact resolution, tokenizer maxima,
  host resource counters, and Metal device availability. Every row passes.
- DMS-07 worktree-authoritative full validation:
  `PYTHONPATH=src:/private/tmp/dms06-von-source/.venv/lib/python3.14/site-packages poetry run pytest -q`
  completed with 2,932 passed, 4 skipped, 0 failed, and 7 deselected.
- `poetry run ruff check src tests scripts` and `git diff --check`: passed.
- The single matrix approval and its artifact bindings are recorded in
  [`dms14-matrix-approval-2026-09-27.json`](evaluation/dms14-matrix-approval-2026-09-27.json).
- Run results, output hashes, and measurements are in
  [`dms14-run-2026-09-27/`](evaluation/dms14-run-2026-09-27/); its `run-receipt.json`
  binds all outputs to the approved matrix and corpus. All six rows completed.
- No candidate met both thresholds. Von CPU led on macro accuracy (0.693),
  while Kev-0.8B passed every category floor; their paired difference is not
  decisive (0.037, 95% CI -0.004 to 0.078). Laya-MLX was the fastest Mac path
  but scored 0.250 on MMLU. See `model-evaluation.md` for full results and
  separate general-use and Mac recommendations.
- Full validation completed with 2,932 passed, 4 skipped, 0 failed, and 7
  deselected; Ruff and `git diff --check` passed.

## DMS-14 Published General Decision Transfer Readiness Review (Historical) — 2026-09-27

Reviewed the DMS-14 tasks against `spec.md`, `plan.md`, and
`model-evaluation.md`. This review assessed task readiness; it did not create
the corpus manifest or execute candidate inference. The subsequent DMS-14
implementation progress recorded above supersedes its pre-execution status.

- **Council:** Aristotle, Ada, and Feynman (architecture triad); parallel
  independent first passes, a challenge round, and a post-repair audit. The
  panel found and resolved missing spec/plan traceability, incomplete
  dependencies and cohort definition, underspecified scoring and option-order
  checks, missing implementation and validation targets, and an unclear
  approval boundary. Final review found no remaining material readiness
  blockers. The corpus identity, protocol, runnable matrix, and approval are
  execution-time prerequisites and remain outstanding.
- **Ponytail:** Removed optional secondary-corpus comparisons to keep one
  primary corpus and a bounded comparison. Kept a corpus-specific runner and
  evaluator rather than adding a general benchmark framework. Kept DMS-01's
  harness unchanged because it is bound to its existing fixtures.
- **Repairs:** DMS-14 now traces to the spec and plan as evidence-only work,
  depends on DMS-01, DMS-02, DMS-06, and DMS-08, and names a fixed cohort of
  already evaluated local candidates. It requires the exact corpus revision,
  split, hashes, license, task mapping, scoring protocol, paired bootstrap,
  option-order comparison, implementation/test files, and result receipt to
  be recorded. CPU and MLX rows are limited to runtimes each candidate
  supports; the MLX-only candidate does not require CPU support. DMS-07's
  worktree-authoritative full validation command is explicitly reused.
- **Approval boundary:** One user approval covers the exact frozen corpus,
  complete runnable candidate/runtime matrix, scoring protocol, thresholds,
  harness revisions, and run. There are no per-model approval prompts. Row
  preflights establish which rows are runnable before that matrix approval;
  failures after approval are recorded without substitution. No model-runtime
  installation, weight download, or inference is authorized before the single
  matrix approval.
- **Disposition:** DMS-14 is ready to execute under these gates. Its results
  are comparative evidence only and cannot change DMS-01/DMS-08 outcomes,
  establish DMS-13 context-preservation quality, or admit a production model.
- **Validation:** `git diff --check` passed. No tests, runtime installation,
  candidate-weight downloads, or model inference were performed for this
  readiness review.

This plan is ready to execute under its stated gates.

## Current Task List Readiness Review — 2026-09-27

Reviewed the full `tasks.md` against `spec.md`, `plan.md`, and the recorded
DMS-14 results. Council used the Aristotle/Ada/Feynman architecture triad for
independent passes, a challenge round, and post-repair verification. All three
verified that the DMS-14 matrix is complete and comparative-only, DMS-15 no
longer depends on unfinished DMS-12, and DMS-15 has explicit scope, plan
ownership, evidence, tests, conditional API documentation, and validation.
Their final verdicts were ready under the stated gates.

Ponytail kept DMS-15 as one audit-first task. The audit reuses the existing
contract validation and records a no-change outcome unless at least two
reviewed backends demonstrate the same runtime-neutral translation. Any
resulting helper must stay in the existing decision-model boundary; no general
framework or model-loading, tokenization, calibration, or score-interpretation
helper is presumed.

The task list is ready under its stated gates. DMS-15's audit may proceed;
helper implementation is conditional on demonstrated reuse. DMS-04 remains
stopped, DMS-10 remains deferred, and DMS-12/DMS-13 retain their separate
approval and benchmark gates. `git diff --check` passed. No tests were run
because this review changed planning artifacts only.

## DMS-15 Reusable Adapter Helper Audit — 2026-09-27

Reviewed the completed candidate inference paths in `tests/manual/` and
`run_dms14_transfer.py`. Kev emits its own choice/probability shape; Von exposes
rounded probabilities and has candidate-specific rounding repair; PoorJev
returns probabilities keyed by generated hypothesis text that must be mapped
back to option IDs; LitJev and Jev-Style expose different answer objects and
probability tolerances; Laya-MLX returns a different mapping and needs its own
normalization tolerance. Those translations are evaluation-harness code, not
DAR runtime adapters, and their differences carry backend-specific meaning.

The production boundary is currently the fake-adapter contract. It already
requires request-ordered question results, exact declared option IDs, finite
scores, explicit `DecisionScoreSemantics`, and valid probability semantics
where claimed. The reviewed candidate profiles were rejected or deferred by
their separate gates, so the repository has no admitted backend adapter whose
contract translation can establish cross-backend production reuse. A generic
score-mapping helper would either duplicate `validate_decision_result` or
incorrectly absorb model-specific extraction, normalization, or calibration.
**Disposition: no new helper is justified.**

The existing fake-adapter contract can be exercised without any backend helper:

```python
class FakeAdapter:
    def __init__(self, identity):
        self.identity = identity

    def decide(self, request):
        question = request.questions[0]
        return DecisionModelResult(
            self.identity,
            (DecisionModelResultItem(question.id, choice=question.options[0].id),),
        )
```

This example returns the declared option ID; the caller then applies the
existing `validate_decision_result` contract. No RED/GREEN helper tests or
public API/documentation changes apply because the audit selected no helper.
`git diff --check` passed; no code tests were run because the audit changed
planning and validation notes only.

## DMS-13 LongMemEval-S Setup and Fake Harness — 2026-09-27

Pinned the cleaned LongMemEval-S dataset and source repository revisions in
`evaluation/dms13-corpus-manifest.json`. The downloaded dataset outside the
repository matched the recorded SHA-256 and loaded as 500 unique items, six
question types, 30 abstention cases, and 246,750 history messages. The exact
Qwen3-4B reader tokenizer and chat template were loaded from pinned local files
without loading model weights. Correct measurements using `input_ids` for all
500 items found history token counts min/p50/p95/max of 112,712/120,653/
123,090/125,751 and complete reader-prompt counts of
112,767/120,714/123,142/125,810. Every history exceeds each proposed 8,192,
16,384, 32,768, and 65,536 budget; no complete prompt exceeds the 262,144
context after reserving 512 generation tokens.

The pinned official LongMemEval evaluator registers GPT-4o
(`gpt-4o-2024-08-06`), GPT-4o mini (`gpt-4o-mini-2024-07-18`), and local Llama
3.1 70B behind an OpenAI-compatible endpoint. GPT-4o is unavailable through
the current ChatGPT auth. The user selected `gpt-6-luna` from the live DAR
catalog; the pinned question-type-specific LongMemEval prompt will be retained,
but `gpt-6-luna` is not an official LongMemEval scorer. Its 4,500 calls would
send each question, gold answer, and candidate answer externally. The pinned
prompt source SHA-256 is recorded in the manifest. This remains pending
endpoint-specific approval; no benchmark inference or judging has run. A
combined direct-local Poetry runtime is pinned in `evaluation/dms13-runtime/`; `poetry lock` and
`poetry check --lock` passed. It was installed under `/private/tmp` and
preflighted with the pinned Von source imports. The exact locked package
versions match, Metal is available, host RAM is 36 GiB, and `/private/tmp` had
49.3 GiB free. The initial runtime preflight
`evaluation/preflight-dms13-2026-09-27.json` records `preflight_passed: true`.
The refreshed run-specific receipt
`evaluation/preflight-dms13-run-2026-09-28.json` binds the exact manifest,
candidate runner, evaluator, runtime lock, source revisions, current host
capacity, and Metal check; it has `run_allowed: false` pending user approval.
The Qwen reader weights are not cached in the designated DMS-13 model cache;
no DMS13 weights were loaded and no inference was performed. The answerer,
exploratory Von compactor, scorer, budgets, metrics, and thresholds are bound in
the corpus manifest and `model-evaluation.md`.

Added a benchmark-specific, callback-driven harness that removes questions,
gold answers, and evidence annotations from compactor inputs; enforces matched
token budgets and selection ordering; skips answer/scorer calls on context
overflow; computes category/answerability metrics and paired stratified
bootstrap intervals; and writes fixed-schema redacted prediction records.
Added `RankedTurnCompactor` to apply the DMS bounded-ranking rule to complete
conversation turns while caching each fake or candidate score across budget
conditions. It accepts a score callback and remains benchmark-specific; it
does not introduce a reusable model adapter or production binding.
Added a candidate-specific `VonTurnScorer` callback. It receives one turn only,
checks the exact packed Von input against the 8,192-token limit before
inference, validates the pinned keep/drop probability output, and returns the
keep-minus-drop ranking margin. The manual runner loads Qwen3-4B locally with
MLX, uses the exact LongMemEval answer prompt and the `gpt-6-luna` judge, and
writes only redacted predictions and aggregate receipts. Before creating the
model cache, it requires approval bound to the manifest, preflight, runner and
evaluator digests, runtime lock, model revisions, budgets, thresholds, and
4,500 external requests containing questions, gold answers, and candidate
answers. The official LongMemEval prompt is loaded from its exact source file
only after the recorded SHA-256 matches. Fake tests cover input isolation,
packed-size rejection, prompt-builder arguments, exact approval binding, and
refusal before model-cache creation.
The first full-corpus fake sweep exposed repeated session IDs within one
question; message IDs now include session position so selection identity and
evidence-turn recall remain unique. The cached Von scoring callback will score
each of the corpus's 122,462 conversation turns once across the four budgets.
A second sweep completed 500 items across
full history, recency, and model-guided conditions at all four budgets: 4,500
rows, using fake compactor/answer/judge callbacks and no model inference.
Validation:

- `poetry run pytest tests/test_context_compression_evaluation.py tests/test_context_compression_dms13_runner.py -q`: 19 passed with fake backends and no model inference.
- `poetry run ruff check src tests scripts`: passed.
- `PYTHONPATH=src:/private/tmp/dms06-von-source/.venv/lib/python3.14/site-packages poetry run pytest -q`: 2,951 passed, 4 skipped, 0 failed, 7 deselected.
- Pinned isolated-runtime check of DMS-13 preflight, runtime packages, and
  official scorer source digest passed; no model imports, weight downloads,
  inference, or API calls occurred.
- `poetry run ruff check scripts/evaluate_context_compression.py tests/test_context_compression_evaluation.py`: passed.
- `python -m json.tool specs/decision-model-support/evaluation/dms13-corpus-manifest.json`: passed.
- `python -m json.tool specs/decision-model-support/evaluation/preflight-dms13-run-2026-09-28.json`: passed.
- `git diff --check`: passed.

No model weights were downloaded and no model inference or external judge call
was performed. DMS-13 remains comparative evaluation only; it cannot admit a
production profile or change DMS-01 decisions.

### DMS-13 DAR auth-path update — 2026-09-28

Replaced the runner's direct `OPENAI_API_KEY` check and hard-coded public API
client with DAR's default provider and OpenAI adapter. The locked runtime
resolves this host to `chatgpt.com`; preflight and run receipts bind that
endpoint and the 4,500-call scope. The locked runtime was installed under
`/private/tmp/dms13-poetry-envs`; the public API route was not called. The
focused runner tests pass (8 passed), Ruff passes for the runner and its tests,
and `git diff --check` passes. Auto-review rejected sending benchmark-derived
questions, gold answers, and candidate answers to `chatgpt.com` under the
earlier approval for `api.openai.com`. The user selected `gpt-6-luna` from the
DAR catalog (`gpt-6-sol`, `gpt-6-astra`, `gpt-6-luna`, `gpt-5.6-sol`,
`gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-5.5`). The DMS-13 runner now uses the DAR
Responses adapter, verifies the live model catalog before model-cache
creation, and requests 64 output tokens at temperature 0. The pending run
receipt binds the selected model and endpoint. No model weights were downloaded
and no benchmark inference or judge request was made.

## DMS-12 Jev-Style 0.8B v3 Candidate Preparation — 2026-09-27

Screened the 8-bit MLX build from the referenced local-options review and
pinned the checkpoint, base, scorer script, tokenizer, readout files, and
SHA-256 digests in `model-evaluation.md`. The isolated Poetry runtime resolves
Python 3.14.6, MLX 0.32.2, mlx-lm 0.31.3, NumPy 2.5.3, Tokenizers 0.23.2, and
Hugging Face Hub 1.33.0; its lock SHA-256 is
`5bcfab3b03b00500fb9fa2c4ba94a36de52d6453fe0b5312ea10f1cf81ed977d`. This
version pairing matches the checkpoint's documented MLX conversion/runtime.
The run path imports the checkpoint's scorer only after its pinned SHA-256
matches, then loads local weights in process. It does not start a model server.

The fake-only runner suite passed (9 passed), Ruff passed for the new runner and
tests, and `poetry check --lock` plus `git diff --check` passed. The dated
preflight confirms the approved fixture hash, pinned runtime and artifact
identities, isolated Poetry virtualenv and lock, 36 GiB RAM, 70.2 GiB free
storage, and Metal availability. It sets `run_allowed=false` only because
separate candidate-specific approval is absent. The model cache is empty; no
weights were downloaded and no inference ran. DMS-12 requires that approval, a
regenerated passing preflight, and a one-time frozen evaluation before it can
report a candidate decision.

## DMS-08 through DMS-11 Laya-MLX Result — 2026-09-27

DMS-08 resolved the exact Laya-MLX source, model, tokenizer, provenance base,
Apache-2.0 licenses, 1,024-token limit, supported mode outputs, and material
digests in `model-evaluation.md`. The isolated runtime is captured by
`evaluation/laya-mlx-runtime/pyproject.toml` and `poetry.lock`; the root DAR
Poetry files were not changed for this evaluation. The pinned runtime resolved
and installed successfully. A sandboxed preflight initially could not see Metal; the final
preflight passed outside that headless sandbox with the approved fixture hash,
exact source/model/runtime identities, 36 GiB RAM, 76.9 GB free storage, and
Metal available. No weights were downloaded until that preflight passed.

The final run used pinned source revision
`0a859518634112655cb97c745dbf04f5191aaf13`, model revision
`28416e78cb26a239a4eabaa2e084904ec5e6cacb`, and provenance base
`f9ab0b228f0fc0f14d873dbc99038f135c2da1b2`. It ran in-process, offline after
materialization, with no server, remote code, PyTorch, or Transformers. The
fake-only runner tests first exposed no loader. After implementation they
verified exact identities, fixture-only requests, option-ID mapping,
four-decimal probability normalization, context-limit rejection, offline load,
preflight refusal, and redaction.

The final frozen evaluation completed all 240 cases with no invalid, missing,
timeout, oversize, abstention, error, or OOM results. Decision accuracy was
0.685/200 (95% Wilson interval 0.618–0.745), below the required 0.80. Retention
F1/keep recall were 0.625/0.50, below 0.80/0.90. Utility was 0.593 versus
0.306 recency (+0.287), above the +0.05 gate. Decision/retention ECE were
0.1001/0.153, so combined calibration failed. Operations passed with
984,383,488-byte peak RSS, 582 ms post-materialization load, and warm p50/p95
of 25.9/68.1 ms. Predictions, token counts, measurements, preflight, and
aggregate report are in `evaluation/laya-typed-decisions-*` and
`evaluation/preflight-laya-mlx-dms08-approved-2026-09-27.json`. DMS-08 therefore
rejects this candidate for DMS support; DMS-10 adapter and admission work is
deferred by its quality gate.

DMS-09 confirmed that MLX 0.32.2 satisfies Laya-MLX's >=0.32.2,<0.33 range,
coexists with the current `mlx-lm` and `mlx-embedding` lock constraints, and
was lockable in the isolated Poetry runtime. The existing MLX generation and
embedding contract checks remain valid. No DAR dependency changes were needed
or made.

DMS-11 validation used these commands:

```bash
poetry run pytest tests/test_laya_mlx_dms08_runner.py \
  tests/test_unit_test_network_policy.py -q
PYTHONPATH=src:/private/tmp/dms06-von-source/.venv/lib/python3.14/site-packages \
  poetry run pytest tests/test_laya_mlx_dms08_runner.py \
  tests/test_decision_models.py tests/test_workflow_model_execution_binding.py \
  tests/test_local_model_runners.py tests/test_capabilities.py \
  tests/test_mlx_models.py tests/test_mlx_embedding_dependency_contract.py -q
PYTHONPATH=src:/private/tmp/dms06-von-source/.venv/lib/python3.14/site-packages \
  poetry run pytest -q
poetry run ruff check src tests
poetry check --lock
git diff --check
```

Results: the network-policy and runner checks passed (16 passed); the focused
decision/binding/MLX suite passed with 180 passed and 1 hardware skip; the full
suite passed with 2,901 passed, 4 skipped, 0 failed, and 7 deselected. Ruff,
Poetry lock validation, and whitespace validation passed. A plain Poetry full
run resolves stale installed package code; the worktree `PYTHONPATH` and
isolated Von runtime above are required for authoritative full-suite results.

The final handoff leaves DMS-04 stopped and DMS-10 deferred. No first-party
Laya-MLX adapter or production profile is added, and the overall feature stays
partial because no evaluated model meets the frozen quality criteria.

## Implementation and Validation Audit — 2026-09-27

DMS-01 through DMS-03 and DMS-05 implementation work is present. Kev-0.6B
failed the frozen quality criteria, so no Qwen profile was recommended and
DMS-04 remains stopped before admission. DMS-06 records exact source revisions
for Von, PoorJev, NanoJev, and LitJev. The approved Von 1.2.0 run failed its
decision and retention thresholds and is rejected for support; the later
PoorJev and LitJev evaluations also failed quality gates, while NanoJev remains
deferred for host and licensing reasons.

Verification of the current worktree:

- DMS/workflow-binding/local-runner/capability focused suite, including the
  Von/PoorJev/LitJev fake-runner tests: 427 passed, 1 skipped because MPS
  hardware is unavailable.
- Full worktree suite: 2,884 passed, 4 skipped, 0 failed, 7 deselected.
- `ruff check src tests` and `git diff --check`: passed.

The full-suite skips cover unavailable platform or hardware integrations. The
three clean-Codex harness tests previously used stale wheel-version paths; they
now resolve the current wheel version from `pyproject.toml` and pass.
One full-suite attempt under load timed out the M4.4 isolated-actor scenario;
that case passed on isolated rerun and the next full run passed without failures.

Von's approved preflight, predictions, token counts, measurements, and
aggregate evaluation receipt are recorded under `evaluation/`. The runner
passed its exact-revision checks and completed all 240 cases in-process on CPU
with no OOM. DMS-04 remains stopped; the feature remains partial.

## DMS-06 Identity Refresh — 2026-09-27

Rechecked the pinned PoorJev source and Hub metadata after the earlier review
recorded an unresolved model endpoint. At that review point, its source pins
`MoritzLaurer/deberta-v3-base-zeroshot-v2.0` at Hub revision
`8e7e5af5983a0ddb1a5b45a38b129ab69e2258e8`; the model card declares MIT, and
the source implements an in-process CPU-capable local NLI backend. The exact
source/model revisions, weight digest, license, runtime options, and DMS
contract-fit rationale are recorded in `model-evaluation.md`. Added
`tests/manual/run_poorjev_dms06.py` with fake coverage for input-only request
construction, probability validation, output redaction, and exact approval/pin
checks. The focused tests pass (3 passed), and Ruff plus `git diff --check`
pass. The dated preflight confirms 36 GiB host memory, 79.5 GiB free storage,
Python 3.14.7, and the exact locked research runtime. It has
the initial preflight was blocked because candidate-specific approval was
absent. The later approved run and metrics are recorded below.

LitJev is paired with the immutable Qwen3-0.6B-Base checkpoint already used in
the Kev comparison. Its fake-only runner tests pass (3 passed). The initial
initial preflight confirms the same host/storage capacity and exact source/base
identities, but was blocked by the absent candidate-specific approval and the
source-locked runtime not yet being installed. The later approved run and
metrics are recorded below.

The pinned NanoJev predictor requires CUDA and rejects other device types; the
host is macOS ARM without CUDA. Its model card also leaves weights licensing
undeclared, so the candidate remains deferred without a source patch or weight
download.

## Readiness Review Refresh (Pre-Execution) — 2026-09-26

Re-reviewed the current `tasks.md` against `spec.md`, `plan.md`, and
`model-evaluation.md` after clarifying that DAR's first implementation is
local-only, Laya's server remains external-client-owned, and Kev-0.6B is only a
provisional design/evaluation target.

- **Council panel:** Aristotle, Ada, and Feynman (architecture triad).
- **Execution:** Parallel independent first passes, a cross-examination round,
  and final artifact-consistency checks; no external backend was used.
- **Initial findings:** DMS-01 appeared to require the DAR runner/material
  admission that DMS-04 builds; the evaluation harness and preflight were not
  assigned to a task; DMS-06 needed a fail-closed identity-resolution outcome;
  the implementation-readiness paragraph still assigned production admission
  to DMS-01.
- **Resolution:** DMS-01 now builds/tests a narrow fake-backed metric harness,
  records preflight evidence, and recommends a candidate only. DMS-04 proves
  the exact DAR binding and makes the production admit/reject decision after
  its separately authorized competency check. DMS-06 records exact primary
  identities or evidence-backed `defer: unresolved identity` outcomes. The
  stale spec sentence was corrected, and DMS-07's focused command includes
  the new evaluation-harness test.
- **Disagreement resolved:** Aristotle initially considered DMS-06 unready
  because the names lacked pinned artifacts. Ada and Feynman observed that
  exact source resolution is itself an explicit task output and that unresolved
  identities may be deferred. Aristotle updated his position after review of
  that wording; DMS-06 remains in the DMS-07 dependency chain.
- **Ponytail review:** Lean enough. No task removal is warranted: the
  evaluation harness is the minimum reproducible method for the registered
  metrics, and the detailed boundaries guard real model and runtime authority.
  No general model-runner framework or Laya server task was added.
- **Final verdict:** Ready under the user-approval, host-preflight, DMS-01
  candidate-evidence, and DMS-04 production-admission gates. No model run or
  implementation validation is claimed. The evaluation fixtures' hashes were
  verified; `git diff --check` passed.

## Approved Von Evaluation — 2026-09-26

The user approved a Von 1.2.0 run on the frozen DMS-01 fixtures. Its exact
preflight passed with the immutable source/model revisions, approved fixture
hash, Python 3.14.7 runtime and package lock, 36 GiB host memory, and sufficient
storage. The in-process CPU runner downloaded the pinned snapshot, verified
both large weight digests, disabled Hub/Transformers fallback during inference,
and completed 240 cases. No raw case text appears in the prediction, token
count, or aggregate receipt files.

The evaluator found decision accuracy 0.775, below 0.80, with a 0.55
fact-selection category below the 0.70 floor. Retention F1 was 0.387 and keep
recall 0.363, below 0.80 and 0.90. Approved utility was 0.3355 versus recency
0.3062, a +0.0293 gain below +0.05. Both decision and retention scores are
uncalibrated. Operations passed with no OOM and peak RSS about 3.94 GiB. Von is
rejected for DMS support; its full breakdown is in `model-evaluation.md` and
`evaluation/von-1.2.0-receipt.json`.

Final worktree verification after the approved runs and harness-test corrections:

- DMS/workflow-binding/local-runner/capability focused suite: 427 passed, 1
  skipped for unavailable MPS hardware.
- Full suite: 2,884 passed, 4 skipped, 0 failed, 7 deselected.
- `ruff check src tests` and `git diff --check`: passed.

The full suite imports the current worktree with `PYTHONPATH=src` and the
isolated research runtime's site-packages directory so optional PyTorch-backed
tests have their pinned dependency. Plain `poetry run pytest` imports stale
installed DAR code and is not authoritative for the worktree.

DMS-04 remains stopped because no Qwen candidate passed DMS-01. The following
approved alternative runs and decisions supersede the earlier pending status.
The overall feature remains partial.

## Approved Alternative Runs — 2026-09-27

PoorJev's approved run completed all 240 cases with no inference failures.
Decision accuracy was 0.54; retention F1 was 0.350, keep recall 0.313, and
utility gain +0.032, below the required +0.05. Probability scores remained
uncalibrated. Operations passed with no OOM and 1,116,389,376-byte peak RSS.
See `evaluation/poorjev-receipt.json`.

LitJev's exact locked runtime was installed under `/private/tmp`; its approved
final preflight passed before download and inference. The run completed all
240 cases with no inference failures. Decision accuracy was 0.29; retention F1
was 0.559, keep recall 0.50, and utility gain +0.167. The latter passed its
utility threshold, but decision accuracy, retention F1, and keep recall failed.
Scores remained uncalibrated. Operations passed with no OOM and
5,605,228,544-byte peak RSS. See `evaluation/litjev-receipt.json`.

PoorJev and LitJev are rejected against the frozen thresholds. NanoJev remains
deferred because the pinned predictor requires unavailable CUDA and its model
license is undeclared. No alternative is admitted to DMS support.

The user approved a follow-on Kev-0.8B evaluation. Its final preflight passed
with the exact fixture and harness hashes, 36 GiB host memory, 79.7 GB free
storage, Python 3.13.15, and the pinned source lock. The CPU in-process run
downloaded the exact adapter/base revisions and completed all 240 cases without
inference failures or OOM. Decision accuracy was 0.82, but explicit-rule
category accuracy was 0.425. Retention F1/keep recall were 0.390/0.388; utility
gain over recency was +0.001. Decision/retention ECE were 0.152/0.264. Only
operations passed: peak RSS was about 5.58 GiB, cold latency 3,696 ms, warm p50
3,654 ms and p95 5,627 ms. Kev-0.8B is rejected for DMS-04. See the approved
preflight and receipt in `model-evaluation.md`; DMS-04 remains stopped because
no candidate passes the frozen criteria.

## Laya-MLX Readiness Review — 2026-09-28

Reviewed `tasks.md` against `spec.md`, `plan.md`, and `model-evaluation.md`
after the user clarified that the intended Laya path is direct, in-process MLX
inference, with no Laya server implementation.

- **Council:** Aristotle, Ada, and Feynman (architecture triad); parallel
  independent first passes, a challenge round, then final positions. No
  user-local roster addendum or external Codex backend was used. The panel
  initially found scope/plan drift, incomplete task ordering, an assumed rather
  than recorded candidate identity, and undefined `noul` translation. After
  the user's scope clarification and artifact repairs, all three concluded
  that no readiness blockers remain. The panel agreed `noul` maps to the
  existing two-option `scores` result only for a `scores` request/profile with
  exact `yes`/`no` option IDs; it does not add a public mode or map to
  abstention.
- **Ponytail:** Keep the separate evaluation, MLX compatibility decision,
  adapter/admission, and terminal validation tasks. Each is a distinct gate;
  collapsing them would obscure candidate approval, dependency isolation, or
  production admission. No task removal recommended.
- **Repairs:** Updated `spec.md` and `plan.md` to authorize one pinned,
  first-party, in-process Laya-MLX profile while retaining external-client
  ownership of server-backed Laya. DMS-08 now records exact proposed source and
  checkpoint revisions, requires isolated research runtime and identity/license
  verification, and prohibits changes to DAR's Poetry configuration during
  evaluation. DMS-09 decides MLX dependency compatibility. DMS-10 defines
  fail-closed result translation and a separately authorized competency and
  admission decision. Renamed DMS-07 as initial-slice validation and added
  DMS-11 for final Laya-branch validation and handoff.
- **Disposition:** `tasks.md` is implementation-ready under its stated gates.
  DMS-08 begins with candidate verification and fake-backed runner work. Real
  model download and inference remain blocked until candidate-specific approval
  and a matching preflight exist. DMS-04 remains stopped; this does not admit a
  Qwen or Laya profile.
- **Validation:** `git diff --check` passed. No unit tests, model downloads, or
  inference runs were performed as part of this readiness review.

This plan is ready to execute under its stated gates.

## DMS-12 Jev-Style Run and DMS-13 Approved Attempt — 2026-09-28

DMS-12's post-approval preflight passed with the pinned Python 3.14.6 runtime,
installed MLX 0.32.2 packages, and Metal available. The first model load
stopped at the upstream manifest check because the runner's download allowlist
omitted the manifest-required `NOTICE`. Added that exact pinned file to the
download allowlist and artifact digest map, regenerated preflight, and reran.
The approved Jev-Style checkpoint then completed all 240 frozen cases; its
aggregate metrics fail the DMS-01 decision and retention quality gates. The
aggregate receipt, redacted predictions, tokenizer counts, and measurements
are recorded under `evaluation/jevstyle-dms12-*` and summarized in
`model-evaluation.md`.

DMS-13's exact user approval receipt matched the passing run-specific
preflight, manifest, harness, runtime lock, source revisions, model artifacts,
thresholds, and 4,500 external scorer requests. The runner stopped before
model-cache creation because the environment had no `OPENAI_API_KEY`. Von and
LongMemEval checkouts matched their approved revisions. No model weights were
downloaded, no inference ran, and no benchmark data was sent externally.
Resume the same approved run when the credential is available. The absence of
that credential is the only known execution blocker; DMS-13 remains
incomplete.

The status audit reconciled the implementation gates in `tasks.md`, `spec.md`,
`plan.md`, and the candidate table: DMS-04 and DMS-10 are explicit
quality-gated deferrals, DMS-12 is complete, and the approved DMS-13 run is the
only remaining open evaluation task. The DMS-14 cohort remains frozen as
approved; Jev-Style was not added retroactively.
`git diff --check` passed. The configured `rumdl` pre-commit environment could
not install because the package mirror does not provide `rumdl==0.1.62`; the
remaining hooks were invoked with `SKIP=rumdl,rumdl-fmt` and had no applicable
files. No code tests were run for this documentation-only status correction.
