# Decision Model Support Readiness Validation

## DMS-01 Local Candidate Additions — 2026-10-03

Ran the four frozen additions-matrix rows against all 240 approved DMS-01
fixtures on local CPU. MacJev, Lev, Jev-Style PyTorch BF16, and Jev-Style GGUF
F16 completed without inference failures or OOM and passed operations; all
failed one or more quality thresholds. Exact metrics, immutable pins,
preflights, evaluator receipts, and artifacts are in `model-evaluation.md`
and `evaluation/`.

The initial PyTorch Jev-Style attempt failed all rows due to a runner/upstream
API contract mismatch. Added a fake-backed regression test, corrected the
adapter, preserved the initial failed outputs, and reran the pinned row. Also
corrected GGUF RSS measurement to include scorer-child high-water RSS; its
preflight-bound rerun completed with the quality scores unchanged. Focused
verification passed: `poetry run pytest tests/test_dms01_additions_runner.py
-q` (6 passed) and Ruff reported no issues for the runner and its tests.

## DMS-17 Jev-Style v3 Selector Specification — 2026-10-03

Added FR-12 and DMS-17 for an opt-in `jevstyle-v3-auto` profile. “Best” means
the first profile in a fixed pre-load preference among profiles admitted for
the host: MLX/Metal on Apple Silicon, then GGUF F16 CPU, then PyTorch BF16 CPU.
The preference reflects DMS-01's measured warm-inference advantage for GGUF
over PyTorch on the tested Mac; it does not benchmark models at startup. The
DMS-01 PyTorch profile is CPU-only; CUDA is outside scope
until a separate exact profile is reviewed and admitted. The task now covers
the shared contract's `choice` and ordered `scores` modes, with native `noul`
output mapped only for exact yes/no options inside a `scores` request; it does
not add a public `noul` mode. Calibrated semantics require pinned evidence. A
backend unavailable before
loading may be skipped, but a load or inference failure after profile
selection cannot switch models. The selector uses sealed local
profile/material availability and does not download or scan arbitrary model
paths. All variants remain `workflow_decision` only; none is admitted yet.

The recorded DMS-01 model quality and latency results informed this preference.
DMS-17 still requires completed material/license/runtime admission, isolated
backend checks, host-boundary tests, and separate compatibility-smoke
authorization before any profile is exposed.

## DMS-17 Selector Adapter Implementation — 2026-10-03

Implemented `jevstyle_decision_adapter.py` as an opt-in selector over the
three exact DMS-01 v3 identities. The host supplies normalized machine facts,
pre-admitted candidates, and their local loaders. The selector applies the
fixed MLX/Metal, GGUF F16 CPU, then PyTorch BF16 CPU preference, passes the
chosen sealed `ModelExecutionBinding` to exactly one loader, and does not
fallback after loading or inference begins. The adapter maps Jev `choice` and
ordered `score` responses to the shared contract; native `noul` is used only
for a `scores` request with exactly the `yes` and `no` option IDs. Outputs are
probability scores, not calibrated probabilities. All bindings permit only
`workflow_decision`.

Optional backend packages are not imported by the adapter. A subprocess
import-isolation case covers MLX, PyTorch/Transformers, and llama.cpp. Focused
verification passed: `poetry run pytest
tests/test_jevstyle_decision_adapter.py
tests/test_workflow_model_execution_binding.py
tests/test_decision_adapter_imports.py -q` (**30 passed**) and Ruff lint
passed. Formatting was applied to the new adapter tests. This verifies the
selector and shared mapping only: no backend runtime was resolved/installed,
no model was loaded, and no profile is technically admitted or exposed.
Final verification also passed the complete suite (`poetry run pytest -q`:
**3063 passed, 1 skipped, 7 deselected**), repository Ruff checks, focused
format checks, and `git diff --check`.

## DMS-17 Isolated Runtime and Smoke Readiness — 2026-10-03

Added `dynamic-agent-runner` as a local path dependency in each isolated
Jev-Style Poetry runtime so the DAR adapter and pinned model backend can run in
one process. The three Python 3.14.7 locks now include DAR core dependencies;
their SHA-256 digests are recorded in the profile admission ledger. Resolved
and installed with:

```sh
export POETRY_VIRTUALENVS_IN_PROJECT=false
export POETRY_VIRTUALENVS_PATH=/private/tmp/dms17-jevstyle-venvs
for runtime_project in jevstyle-mlx-runtime jevstyle-torch-runtime jevstyle-gguf-runtime; do
  poetry -C "specs/decision-model-support/evaluation/$runtime_project" lock
  poetry -C "specs/decision-model-support/evaluation/$runtime_project" install --no-root --only main
done
```

The exact backend and DAR adapter imports pass for MLX 0.32.2 / mlx-lm 0.31.3,
Torch 2.14.0 / Transformers 5.17.0, and Tokenizers 0.23.2; the MLX import
confirmed Metal availability. No weights were loaded. Current DMS-17 preflight
reverified every PyTorch and GGUF material digest and their host resource
gates; the exact MLX files are pinned but not staged.

Added the one-request offline smoke runner
`tests/manual/smoke_jevstyle_dms17.py` and fake-only checks in
`tests/test_jevstyle_dms17_smoke_runner.py`. The smoke requires a scope-bound
approval receipt covering all three exact profiles, checks runtime/material
pins and current resource budget before loading, disables network access,
passes the selected engine through `load_jevstyle_v3_binding`, validates one
synthetic `choice`, and records one receipt per profile. Focused verification
passed across the Jev-Style adapter, smoke runner, executor, execution binding,
and import-isolation tests (**282 passed**); Ruff passed. The current preflight
scope digest is
`3c244212a6ce0317acc69a455db62b459ca46898d896705efc094862ce7d3712` and
`run_allowed` is false pending separate user authorization. No DMS-17 weights
were loaded and no compatibility smoke has run.

## DMS-17 Task Readiness Review — 2026-10-03

Reviewed the DMS-17 task against `spec.md`, `plan.md`, the DMS-01 model table,
and the exact additions matrix. The architecture triad was run as sequential
persona passes in this session (reduced independence; no delegated councillor
agents or external backend were used), followed by a challenge round.

### Council architecture triad

- **Aristotle:** The task has a coherent unit of work: freeze three exact
  runtime/material profiles, select one by host eligibility, implement the
  shared adapter, then admit each backend independently. The original CUDA
  branch was a category mismatch because the only frozen PyTorch row is CPU.
- **Ada:** Model selection is a deterministic mapping from host capability,
  admitted materials, and resource eligibility to one exact profile. The
  output must stay bound to that identity; quality thresholds and runtime
  calibration are separate concerns. The supported contract modes should be
  explicit rather than inferred from the model family's name.
- **Feynman:** The DMS-01 measurements establish that GGUF is faster than
  PyTorch for the tested CPU setup, but they do not establish a CUDA profile or
  a universally fastest model across all hosts. A small preference order with
  a fail-closed no-eligible case is testable; model load/inference failures
  must not trigger a second backend.

In the challenge round, the triad agreed to keep backend preference bounded
to observed host classes, separate technical admission from DMS-01 quality,
and require host resource-budget eligibility. The task now covers shared
contract modes (`choice` and `scores`), including constrained mapping of
native `noul` output without adding a public mode; it explicitly defers CUDA
pending its own exact profile and tests the no-eligible-profile
path. Remaining profile-specific runtime and package details are discovery
outputs of the first task, not readiness blockers.

### Ponytail

Lean already. Ship. The three-backend freeze, selector rules, fake test gate,
and per-profile admission steps each establish separate required evidence;
removing them would leave the adapter task unable to start or verify safely.

### Disposition and verification

DMS-17 is ready to begin with profile freeze. Backend implementation and
exposure remain gated on exact runtime/material closure, resource admission,
fake tests, isolated backend checks, and separately authorized compatibility
smokes. DMS-01 quality rejection remains independent of client workflow
support; no profile is admitted for context retention.

`git diff --check` passed. No code tests were run because this review changed
specification and task artifacts only; Markdown lint could not run because
`rumdl` is not installed in the Poetry environment.

## Julia 1 DMS-01 Comparison — 2026-10-03

Added `tests/manual/run_julia1_dms01.py` and fake-only coverage in
`tests/test_julia1_dms01_runner.py`. The runner uses the exact admitted Julia 1
CPU profile, does not provide labels to the model, scores the unchanged 240
frozen DMS-01 cases, and emits redacted predictions plus tokenizer and
operation measurements. The exact preflight at
`evaluation/preflight-julia1-dms01-2026-10-03.json` passed before the user's
requested run. The offline inference completed all 240 cases with no invalid,
missing, oversize, abstained, timeout, or error outputs.

Julia 1 scored 0.445 decision accuracy, 0.358 retention F1, 0.363 keep recall,
and −0.0158 category-macro utility improvement over recency. It failed both
quality gates and passed operation limits: 3.385 s cold load, 14 ms warm p50,
76 ms p95, 1,183,350,784 bytes peak RSS, no OOM. The full comparison with Von
is in `model-evaluation.md`; aggregate metrics and redacted run artifacts are
in `evaluation/julia1-dms01-*`. Focused verification:
`poetry run pytest tests/test_julia1_dms01_runner.py -q` (2 passed) and Ruff
on the runner and test (passed).

## DMS-16 Adapter and Optional Runtime Progress Before Approved Smokes — 2026-10-02

This is the pre-material, pre-inference snapshot. Current approved-run
outcomes and material verification are recorded below.

Implemented fake-backed adapter slices for the pinned Von, Julia 1, Laya-MLX,
and Kev-0.6B/Qwen3 candidates. The generic workflow executor now requires
`workflow_decision` permission before adapter dispatch, and the context
retention path requires its separate `context_retention` permission. Focused
contract, executor, compaction, import-isolation, adapter, preflight, and fake
smoke-runner suites passed: **334 passed** with `PYTHONPATH=src poetry run pytest
tests/test_decision_models.py tests/test_executor.py
tests/test_context_compaction.py tests/test_decision_adapter_imports.py
tests/test_julia1_decision_adapter.py
tests/test_von_decision_adapter.py tests/test_laya_mlx_decision_adapter.py
tests/test_kev_decision_adapter.py tests/test_preflight_dms16.py
tests/test_dms16_smoke_runner.py -q`.
Repository Ruff, `poetry check --lock`, and `git diff --check` passed. TDD
regressions first failed as expected for both an unsupported-use
binding and an adapter/profile identity mismatch. Each DMS adapter now declares
its exact identity and permits only `workflow_decision`; the binding rejects
wrong identities and `context_retention` before inference. Four subprocess
tests also confirm that importing adapter modules does not import their model
runtimes. Binding tests cover all four exact DMS-16 adapter identities; runtime
identity tests verify that the runnable Von, Julia 1, and Laya-MLX profiles
include the current shared Poetry-lock digest. This corrected Von and Laya-MLX
from their older evaluation-only lock identities and added the lock to Julia 1.
Julia's adapter also rejects answer IDs outside the requested question set; the
new fake case failed before the check was added and passes afterward.

Optional runtime checks used the current shared root lock
`6b723941863f3c9fd72db50dc359d3e4ffa78092e1402e6e48328374766b924a` in
separate Poetry environments:

- Julia 1 extra installed on Python 3.14.7 with Torch 2.14.0, Transformers
  5.0.0, Tokenizers 0.22.2, Safetensors 0.8.0, and NumPy 2.5.3; all imported.
  The first install revealed a Tokenizers 0.23.2 / Transformers 5.0.0
  incompatibility. Pinning the Julia extra to `tokenizers<=0.23.0` produced a
  clean install and import from a fresh environment.
- Von extra installed and imported on Python 3.14.7 with Torch 2.14.0,
  Transformers 5.0.0, and the exact Von source revision. The upstream source
  identifies the package as 1.2.3; DMS-16 pins the source commit and model
  artifact rather than relying on a mutable package version label.
- Laya-MLX extra installed. Its import could not initialize Metal inside the
  sandbox; an elevated load-only check initialized `Device(gpu, 0)` and
  imported Laya-MLX successfully. No model files were loaded.
- Kev has no root optional extra because the exact upstream source requires
  Torch `<2.9`, while DAR's existing optional Torch dependency declares
  `>=2.9`. Its earlier Python 3.13 / Torch 2.8 evaluation runtime does not
  verify the DMS-16 adapter path.

Each installable extra (`julia1`, `von`, and `laya-mlx`) was also resolved and
installed independently with Python 3.13.16 from the same Poetry lock. Julia's
Torch/Transformers/Tokenizers/Safetensors/NumPy imports passed; Von's Torch,
Transformers, and Von imports passed; Laya-MLX and MLX imports passed after a
load-only run outside the sandbox to make Metal available. These checks cover
both supported Python minor lines (3.13 and 3.14); no model weights were loaded.

Added the no-download preflight `tests/manual/preflight_dms16.py` and ran it.
The [receipt](evaluation/preflight-dms16-2026-10-02.json) confirms the root
Poetry lock and all three isolated runtime package sets, records current host
and storage state, and finds none of the expected model files at
`/private/tmp/dms16-materials/`. Julia's runtime-code file digests are also
verified against the pinned upstream snapshot and are included in the checker,
along with the model, encoder config, and tokenizer material digests. The local
preflight correctly fails because these files are not staged; it records that
download and inference were not performed and never authorizes a run.

The no-download preflight now verifies the complete runtime-required local file
sets: Git blob SHA-1 for Von and Laya-MLX config/tokenizer files, SHA-256 for
large weights and Julia runtime source, and SHA-256 for Julia config/tokenizer
files. The Git blob IDs came from the immutable [Von
snapshot](https://huggingface.co/wfzyx/von/tree/5df8185a4f2327ad0a7cd117cc4f701ac557b9ae)
and [Laya-MLX snapshot](https://huggingface.co/aac6fef/laya-typed-decisions-mlx/tree/28416e78cb26a239a4eabaa2e084904ec5e6cacb)
metadata; no model or tokenizer content was fetched. The receipt remains
blocked by 29 missing or mismatched model/runtime files and confirms no
download or inference. Repository Ruff, `poetry check --lock`, and
`git diff --check` passed.

`tests/test_preflight_dms16.py` adds four fake-file checks for Git object SHA-1,
SHA-256, absent/mismatched files, and the required snapshot paths. In the RED
check all four failed because the digest helper and the config/tokenizer
manifests were absent; after implementation all four passed as part of the
334-test focused suite.

`tests/manual/smoke_dms16.py` is now the exact one-shot manual path for the
three installable profiles. Its approval digest binds the immutable profile
manifest, current Poetry lock, runtime version, host platform, and smoke,
preflight, contract, adapter, and dependency source files. After approval it
stages only allowlisted files, verifies all digests, disables Hub and
Transformers network fallback before model loading, makes one synthetic typed
choice call, validates the result, and reserves a single-use redacted receipt.
Fake tests prove that missing approval and reused receipt paths stop before
staging, material verification precedes loading, loading occurs offline, and
inference is called exactly once. The live smoke remains unrun. For the current
DAR worktree, Python 3.14.7, macOS arm64 host, and Poetry lock, the exact
one-run approval scopes are:

- Von `wfzyx/von@5df8185a4f2327ad0a7cd117cc4f701ac557b9ae`, source
  `fb6e7a937e4fc6b6e72b2ce5035edd56bc370e54`:
  `2fac97a936ff3ce38189646ca170a635ba84910a109580c5e85cb3a9c998a999`.
- Julia 1 `SupersonicLabs/Julia-1@a85b127321d580d65176c89ced8273f305745d85`:
  `ef25605782eeb1e853c488dae56f782a172625c5163196a8f6c7d7045d9a37cc`.
- Laya-MLX `aac6fef/laya-typed-decisions-mlx@28416e78cb26a239a4eabaa2e084904ec5e6cacb`,
  source `0a859518634112655cb97c745dbf04f5191aaf13`:
  `8483067b516b9e4c1b1df3c67948e094a01987d34467b34a7165803b4e38234f`.

The DMS-07 full suite then passed: **3,029 passed, 4 skipped, 7 deselected**.
The first run exposed two fixture mismatches: a DMS-13 preflight test read an
absent shelved judge cache, and a DMS-12 fake omitted the pinned `NOTICE` file
from its expected download allowlist. The DMS-13 preflight test now supplies a
synthetic local snapshot (with digest validation still covered separately),
and the DMS-12 expectation matches the runner's pinned allowlist. Both targeted
tests and the full suite pass. No model inference was performed by these tests.

The frozen evaluation preflights contain expected Von, Laya, and Kev artifact
digests, but their recorded `/private/tmp` cache paths no longer exist. For
Julia, the Python runtime source files were fetched at the pinned revision into
`/private/tmp/dms16-julia-source` solely for static review; their SHA-256 values
are pinned in `tests/manual/preflight_dms16.py` and verified in the receipt.
The review confirms checkpoint loading uses local paths with
`trust_remote_code=False`; this does not replace an offline load/inference
smoke. The model weights, tokenizer assets, and complete snapshot are absent
from the candidate material root, so no row is admitted or exposed.
Existing evaluation approvals do not cover these new adapters, so no DMS-16
model weights or tokenizer assets were downloaded and no compatibility
inference was run. The
remaining gate is a fresh exact-material preflight and matching user approval
before each bounded adapter-facing smoke. Kev-0.6B/Qwen3 is deferred because
its upstream Torch cap conflicts with DAR's declared range.
Context-management quality is not part of this client-support gate.

Verification refreshed after the fake adapters and one-shot smoke runner were
completed: the focused DMS-16 suite passed **334 tests**; the DMS-07 full suite
passed **3,029 passed, 4 skipped, 7 deselected**; Ruff, `poetry check --lock`,
and `git diff --check` passed. These checks do not load candidate weights or
replace the outstanding exact-material smoke gate.

## DMS-16 Initial Approved Material and Compatibility Smoke Results — 2026-10-02

The user approved downloading the exact pinned model/runtime allowlists and
one synthetic choice smoke for each of Von, Julia 1, and Laya-MLX. The current
post-download [preflight receipt](evaluation/preflight-dms16-post-download-2026-10-02.json)
passes with all 29 required files verified, Julia's pinned runtime-source
hashes matching, the shared Poetry lock matching, and the Python 3.14.7
optional package versions matching. The machine is macOS 26.7 arm64 with 36
GiB RAM; about 59.8 GiB remained free after material staging. The checker
itself performed no download or inference.

| Profile | Approved scope | Result |
|---|---|---|
| Von `wfzyx/von@5df8185a4f2327ad0a7cd117cc4f701ac557b9ae`; source `fb6e7a937e4fc6b6e72b2ce5035edd56bc370e54` | `2ad8672a9abe45589ecc5c6746025b4ea7878a2d99529b6bc4f654a2fd9396b6` | All six pinned files verified and local CPU model loading succeeded. One adapter-facing inference was attempted and failed; the [redacted receipt](evaluation/dms16-smoke-von.json) records `inference_failed`. The one-run receipt prevents replay. Von remains unadmitted pending diagnosis and approval for a new attempt. |
| Julia 1 `SupersonicLabs/Julia-1@a85b127321d580d65176c89ced8273f305745d85` | `721237326dc8029411ada2bd6fc5659747efd4b7a03eb72da8103f901daae43b` | All 17 pinned model, tokenizer, and runtime-source files verified. One offline CPU inference returned a contract-valid choice in 27.841 ms; see the [redacted receipt](evaluation/dms16-smoke-julia1.json). Admitted for optional `workflow_decision` use only. |
| Laya-MLX `aac6fef/laya-typed-decisions-mlx@28416e78cb26a239a4eabaa2e084904ec5e6cacb`; source `0a859518634112655cb97c745dbf04f5191aaf13` | `f24b022fa00836a7836e8cdba2faa98d8a78cd88bfcb2c06ddd6935f20971c05` | All six pinned files verified. A sandboxed model load failed before inference; the single approved offline Metal smoke was then run outside the sandbox and returned a contract-valid choice in 1,277.511 ms. The model warned that one confidence bucket is uncalibrated; confidence was not consumed. See the [redacted receipt](evaluation/dms16-smoke-laya-mlx.json). Admitted for optional `workflow_decision` use only. |

All three runs used the synthetic request in `tests/manual/smoke_dms16.py`;
network fallback was disabled before model loading. No user or transcript data
was used. No profile is admitted for `context_retention`. At this checkpoint,
Von's failed inference had no diagnostic details in its receipt.

## DMS-16 Von Diagnostics and Compatible Runtime Retry — 2026-10-02

The smoke runner now records the failure stage, exception type, message, and
traceback in both its receipt and CLI response. It assigns separate approval
scopes and receipts to numbered attempts, preserving prior evidence.

The first DMS-16 Von attempt used the shared Poetry runtime with Transformers
5.0.0 and failed without useful diagnostics. Attempt 2 exposed the cause:
`AttributeError: 'dict' object has no attribute 'size'` in Transformers'
ModernBERT attention-mask expansion, called from Von's encoder. This was a
runtime incompatibility, before adapter result validation. The successful
DMS-06 run used the exact Von source `uv.lock`, SHA-256
`acaaa8abfcd3bc18eff1557fe2c73be73c00899eed5b1145de1b30518acf1f41`, which
pins Transformers 5.17.0. The [attempt 2 receipt](evaluation/dms16-smoke-von-attempt-2.json)
contains the exception details and traceback.

The DMS-16 preflight now binds Von to that profile-specific lock and verifies
the installed package set. The [compatible-runtime preflight](evaluation/preflight-dms16-von-compatible-2026-10-02.json)
passed with all 29 model/runtime files verified and no blockers. The [attempt 3
receipt](evaluation/dms16-smoke-von-attempt-3.json) records one offline CPU
inference with a contract-valid result in 1,062.933 ms. Its approval scope is
`c5e20834b40ae5ee47b8e82b1e856fb0aeddc77d576a14e2404a455b4a2571ca`.

The root Poetry `von` extra still resolves Transformers 5.0.0 because the
shared lock also satisfies Julia 1's `<5.1` range. Do not use that root-extra
runtime for Von inference; the admitted DMS-16 Von profile uses the pinned
upstream `uv.lock`. Von is admitted for optional `workflow_decision` use with
that profile runtime only. No profile is admitted for `context_retention`.

## DMS-16 Readiness Review After Adding Julia 1 — 2026-10-02

Reviewed the current `spec.md`, `plan.md`, and `tasks.md` after adding Julia 1
as a prospective optional client backend. No implementation, model download,
or inference was performed.

### Council architecture triad

Ada, Aristotle, and Feynman completed independent first passes, a challenge
round, and Ada's post-repair audit. The Council agreed that DMS-16 is ready to
start with profile freeze and technical admit/defer discovery; Julia RED/GREEN
and exposure must wait for the exact row and its implementation-time evidence.

The first passes and challenge round found these requirements:

- Describe Julia 1 as a candidate pending DMS-16 technical admission, not as
  already reviewed, evaluated, or admitted.
- Pin and license-review every model-specific executable runtime/code source.
  Require local controlled loading and defer the row if remote-code loading or
  dynamic code acquisition is needed.
- Add Julia-specific fake cases for declared-option choice, request-ordered
  option-ID scores with explicit score semantics, and exact `yes`/`no`
  probability mapping with complement, order, finite-range, malformed-output,
  and calibration-evidence checks.
- Resolve the exact Python/platform and Transformers `<5.1` dependency lock;
  name the optional extra, adapter/test targets, and focused resolution,
  install, and test commands before RED/GREEN. Reuse the existing DMS-07 full
  suite and Ruff gates instead of duplicating them.
- Complete RED/GREEN independently per technically admitted row; a deferred
  row has no implementation work and does not block other rows. None of these
  technical gates makes historical context-management quality a client-support
  requirement.

Aristotle emphasized the need for concrete implementation targets before
RED/GREEN. Feynman agreed that targets may be selected during row freeze, but
that the exact focused commands and runtime lock must be recorded before
implementation. Ada accepted that timing and the need for Julia-specific
mapping and custom-code controls. There was no substantive dissent after the
challenge round.

Ada's post-repair audit found the wording, custom-code boundary, mapping cases,
dependency/target requirements, per-row independence, and quality separation
consistent across all three artifacts. No readiness blocker remains for the
profile-freeze step. Julia implementation is still gated on completing that
step and passing its specific RED/GREEN and compatibility checks.

### Ponytail review

The smallest coherent change is to keep Julia inside DMS-16's existing
profile-freeze, optional-extra, RED/GREEN, and exposure gates. No separate
Julia specification, general model loader, reusable helper, quality gate, or
duplicate full-suite/Ruff task is warranted. Julia-specific checks remain only
where its custom runtime and three output shapes differ from the common adapter
checks. The row-level gates are deliberately separate so a deferred profile
does not block other admitted rows.

### Repairs and verification

- Changed FR-11 and the scope/status language to identify Julia as a candidate
  pending technical admission.
- Added exact local-code identity and no-remote-code requirements, Julia output
  mapping cases, and row-freeze outputs for its Poetry resolution, optional
  extra, module/test targets, and focused commands.
- Made GREEN work separately completable for each admitted profile and
  clarified that a deferred row does not block the others.
- `git diff --check` passed. No tests were run because this review changed
  planning and validation artifacts only.

**Disposition:** DMS-16 is ready to begin exact profile-row freeze and technical
admit/defer review. Julia is not yet admitted or implemented; its row can be
deferred on technical, dependency, provenance, or contract grounds without
changing client-support quality criteria.

## DMS-16 Initial Client Backend Support Readiness Review — 2026-10-02

Reviewed the client-support update to `spec.md`, `plan.md`, and `tasks.md`.
The user's direction is to make optional Von, direct in-process Laya-MLX, and
Qwen/Kev decision backends available to client workflows without applying the
existing context-quality criteria. Revisit those criteria when context
compression/management work resumes. No implementation, model download, or
inference was performed.

### Council architecture triad

Aristotle, Ada, and Feynman completed parallel independent first passes, a
challenge round, and a post-repair audit. They found and resolved these
readiness gaps:

- FR-7 now separates DMS-08's historical Laya candidate evidence from DMS-16's
  technical admission; DMS-10 remains an archived context-management decision.
- DMS-16 freezes a closed profile/material/runtime list and records an
  independent technical admit/defer outcome before RED/GREEN work for each
  profile. One row's dependency conflict does not block another.
- The spec makes `permitted_uses` host-controlled admission data. DMS-16
  profiles permit only `workflow_decision`, and `context_retention` resolution
  must fail before adapter dispatch. Caller-provided task/profile IDs cannot
  grant permission. A fake rejection test is required before inference.
- RED coverage includes FR-7's exact Laya `noul` mapping, malformed and
  unsupported shapes, and rejection of `calibrated_probability` without
  pinned calibration evidence.
- Before exposing a row, the task requires approved exact-material preflight
  and a bounded synthetic, contract-valid, offline-after-admission
  compatibility smoke. Existing evidence may be reused only when material
  digests, runtime/extra lock, platform, and adapter-facing path all match.

Council's final verdict was ready under these staged technical gates. It found
no quality threshold, corpus score, or retention metric in DMS-16 client
admission. Remaining proof is implementation-time: the host use guard must
pass its fake test before any profile is exposed.

### Ponytail

Ponytail found the new support work warranted by the explicit client-support
decision. It identified a duplicate broad DMS-16 row in the plan table; that
row was removed and its concise profile, use-boundary, and compatibility
summary retained in the remaining entry. The detailed DMS-16 section and task
remain because they carry the distinct execution and validation gates.

### Disposition and verification

DMS-16 is ready to begin with the exact profile-row freeze and independent
technical admission step. It does not authorize downloads or real inference by
itself; each new compatibility run still requires matching approval and
preflight. Client workflow support is separate from future context-management
use. `git diff --check` passed. No tests were run because this review changed
planning artifacts only.

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
rejects this candidate for context-management quality; DMS-10's context-use
adapter and admission work was deferred by that quality gate. DMS-16 later
selected this separate local backend for optional client support, subject to
its independent technical/material checks and approved compatibility smoke.

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
rejected for context-management quality; its separate DMS-16 client-support
disposition is pending technical/material checks and an approved compatibility
smoke. Its full breakdown is in `model-evaluation.md` and
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

PoorJev and LitJev are rejected against the frozen context-management quality
thresholds. NanoJev remains deferred because the pinned predictor requires
unavailable CUDA and its model license is undeclared. These outcomes do not
admit or reject the profiles selected for DMS-16 client support.

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

Historical record from the initial external-scorer attempt: DMS-13's exact
user approval receipt matched the passing run-specific
preflight, manifest, harness, runtime lock, source revisions, model artifacts,
thresholds, and 4,500 external scorer requests. The runner stopped before
model-cache creation because the environment had no `OPENAI_API_KEY`. Von and
LongMemEval checkouts matched their approved revisions. No model weights were
downloaded, no inference ran, and no benchmark data was sent externally.
At that point, resuming after approval of the corrected harness receipt was the
only remaining execution blocker. This external-scorer attempt was superseded
by the local MLX path below; DMS-13 remains incomplete.

The historical status audit reconciled the implementation gates in `tasks.md`,
`spec.md`, `plan.md`, and the candidate table: DMS-04 and DMS-10 are explicit
quality-gated deferrals, DMS-12 is complete, and the approved DMS-13 run is the
only remaining open evaluation task. The DMS-14 cohort remains frozen as
approved; Jev-Style was not added retroactively.
`git diff --check` passed. The configured `rumdl` pre-commit environment could
not install because the package mirror does not provide `rumdl==0.1.62`; the
remaining hooks were invoked with `SKIP=rumdl,rumdl-fmt` and had no applicable
files. No code tests were run for this documentation-only status correction.

## DMS-13 local MLX judge switch and initial attempts — 2026-09-28

Replaced the proposed `gpt-6-luna` remote judge with the user's requested
pinned local MLX scorer: `mlx-community/Llama-3.1-8B-Instruct-4bit` at
`90215b22ec18e72f623dde2ea7af4097025160e2`. Hugging Face reports the model's
Llama 3.1 Community License and a 4,517,489,037-byte weight file. Downloaded
the complete snapshot to `/private/tmp/dms13-local-llama-judge-90215b22`; the
runner and manifest pin SHA-256 for all eight repository files. The exact MLX
runtime loaded this snapshot with Metal available; load-only peak MLX memory was
4,517,406,216 bytes. The first approved attempt with the corrected Von runtime
reached the first Qwen generation and exposed an MLX-LM API mismatch before
answer tokens were generated; a second attempt confirmed the same failure. Each
attempt scored only the first item's 273 conversation turns with Von and made
zero judge calls. No benchmark data left the machine.

The manual runner now scores with the pinned LongMemEval prompt using
`mlx_lm.generate` in process, temperature 0, and a ten-token output cap. Snapshot
SHA-256 uses streaming reads to avoid loading full weight files into memory. It
makes 4,500 local judge calls, expects zero remote judge calls, and stores only
boolean labels and aggregate metrics. The DMS-13 Poetry runtime no longer
includes the OpenAI package; it now pins Von's required `pydantic==2.13.5`.
The revised Poetry lock SHA-256 is
`6c2acc5c4ab2d93503348e70301e467ccae4e147e59fb770e25204e1624fe201`.

Validation:

- RED: the local-generation fake first failed because `_score_with_local_model` did not exist; the bounded-hash fake then failed because `_sha256` required `read_bytes`.
- GREEN: `poetry run pytest tests/test_context_compression_dms13_runner.py tests/test_context_compression_evaluation.py -q` — 22 passed after the greedy-sampler API correction.
- `poetry run ruff check scripts/evaluate_context_compression.py tests/manual/run_context_compression_dms13.py tests/test_context_compression_dms13_runner.py` — passed.
- Isolated runtime `poetry check --lock` — passed with existing Poetry metadata deprecation warnings.
- Pinned-runtime package verification and load-only smoke for Qwen, Llama, and
  Von — passed; Metal is available and OpenAI is absent.
- After the MLX-LM sampler correction, Qwen and Llama each generated one token
  from a synthetic prompt in the pinned runtime; this smoke used no benchmark
  data and is separate from the pending full matrix.
- At this historical checkpoint, the corrected preflight and pending receipt
  identified the then-current greedy-sampler harness and a 4,500-call run.
  Two approved attempts stopped before answer generation because MLX-LM
  rejected `temp=0`; each scored the first item's 273 turns with Von and made
  zero judge calls. The runner was then corrected to pass `make_sampler(0)`.
  This receipt and preflight are superseded for execution: their 4,500-call
  limit and artifact digests do not bind the checkpointed retry harness or its
  9,000-call maximum. Do not use them to authorize further inference.

The local model is not the LongMemEval authors' official Llama 3.1 70B server
or GPT-4o scorer, so its results are exploratory and not directly comparable.

## DMS-13 Restartable Run Readiness Review — 2026-09-29

The approved local-judge attempt ran for more than 17 hours, exited with
`ManualRunError`, and produced no result directory or usable predictions. The
runner logged a 9,380-token sequence against an 8,192-token limit immediately
before exit but did not preserve the exception message; the warning is not
established as the cause. This is the current run outcome recorded in
`model-evaluation.md` and `tasks.md`.

The harness now checkpoints each completed item atomically, records progress,
skips verified successes on restart, retries unfinished items once, and merges
only a complete verified set without inference. Focused fake-only tests cover
resume, interrupted items, corrupt checkpoints, progress, and incomplete
merge. A fresh exact preflight and approval for the revised artifacts and
bounded retry envelope remain required. The existing receipt/preflight records
4,500 local judge calls and 122,462 Von turn scores; the retryable run permits
up to 9,000 and 244,924 respectively. Their hashes and limits are historical
and cannot authorize the revised run.

### Council architecture triad

Aristotle, Ada, and Feynman completed independent first passes and a challenge
round. They agreed the task graph and run sequence are ready with conditions;
the current real-model run is not authorized. Their challenge confirmed that
the mismatch is an execution-evidence defect, not a missing dependency or
task. Before inference, regenerate preflight and approval binding the exact
manifest, harness/runtime, retry policy, and maximum cost. The councillors
preserved the distinction between task readiness and run authorization.

### Ponytail

Ponytail found duplicated checkpoint details in the open DMS-13 run task,
already specified by its completed restartability task. The open item now
refers to that procedure and keeps only the preflight, approval, execution,
merge, and result-recording steps, reducing the item by one line.

### Disposition and verification

`tasks.md` is ready to continue under its stated gates; DMS-13 remains
incomplete and blocked from further inference pending a fresh matching
preflight and user approval. The old 2026-09-28 receipt remains historical.
`git diff --check` passed. No model inference was performed for this review.

## DMS-13 shelved — 2026-09-30

The user shelved DMS-13 and decided published LongMemEval results are
sufficient external context for current purposes. No DMS-13 pilot or full
internal evaluation is planned. Published results do not establish
DAR-specific context-compression performance.

The approved checkpointed run had been stopped after 12 complete items. It
saved 108 prediction rows, 3,760 Von turn scores, and 118 local judge calls;
item 13 remained partial at 225 Von scores and zero judge calls. These partial
outputs are not used as evaluation results. Preserve the run receipt and
checkpoints as historical artifacts; resume only after an explicit new
decision. The 60-item pilot proposal is shelved with the full run.

## DMS-17 Jev-Style v3 Backend Smokes — 2026-10-03

The user approved scope `3c244212a6ce0317acc69a455db62b459ca46898d896705efc094862ce7d3712` for the three pinned profiles. Exact MLX materials were staged from the pinned revision and all eight SHA-256 digests matched. The PyTorch BF16 CPU and GGUF F16 CPU profiles each completed one offline synthetic choice through the DAR adapter; both returned the valid supplied option `billing`. Receipts are `dms17-smoke-torch-bf16-cpu.json` and `dms17-smoke-gguf-f16-cpu.json`.

The MLX smoke did not reach inference. The sandbox attempt could not access Metal; outside the sandbox, MLX initialization reached the upstream repository integrity check, which requires `manifest.json`. That file was not in the pinned material allowlist, so it was not staged. The failure and zero-inference status are recorded in `dms17-smoke-mlx-metal-failure.json`. MLX remains deferred. Supporting it requires pinning the manifest digest, updating the scope, and obtaining approval for that revised scope. The two CPU profiles are technically admitted for `workflow_decision` use only; DMS-01 quality results remain separate, and none is admitted for context retention.

## DMS-17 MLX/Metal Follow-up Smoke — 2026-10-03

Executed the explicitly requested MLX-only retry under scope `decb9724f9850d226d874ccf19c0e79e7de0dc80b49fbc313eb5ca1df7867e40`. Added SHA-256 pins for `manifest.json`, `LICENSE`, the remaining manifest-listed 8-bit files, and `requirements.txt`. All 14 staged files required by the upstream verifier for the selected 8-bit profile matched their pinned digests. The pre-load selector chose the MLX/Metal profile; one offline synthetic choice returned the valid supplied option `billing` in 1,074 ms. Receipt: `evaluation/dms17-smoke-mlx-metal-attempt-3.json`.

Two earlier attempts failed before inference: attempt 1 lacked `manifest.json`; attempt 2 exposed the verifier-required `requirements.txt`. Both are retained in `evaluation/dms17-smoke-mlx-metal-failure.json`. GGUF, PyTorch, and MLX are now admitted for `workflow_decision` only. None is admitted for context retention. `git diff --check` and JSON parsing passed; no evaluation fixture, training, calibration, or inference-time network access was used.

## DMS-18/DMS-19 Readiness Review — 2026-10-06

The named target was the DMS-18/DMS-19 addition in `tasks.md`, reviewed
against `spec.md` and `plan.md`. Council and Ponytail found the additions ready
for contract freeze and matrix discovery, but not ready to claim that the new
capabilities are implemented. DMS-18 lacked exact score-policy edge behavior
and `noul` complement ownership. DMS-19 lacked auditable row dispositions and
precise caller identity/lifecycle evidence. Council also found that DMS-19's
decision-inference row must wait for the DMS-18 contract while other discovery
rows may proceed.

Repairs applied:

- `argmax` ties resolve by first declared option; threshold routing is
  probability-only, uses `>=`, and routes abstention only through an explicit
  abstain edge or fails closed. For `noul`, `yes` is selected at or above the
  threshold and `no` below it; an explicitly abstained result uses the abstain
  edge or fails closed.
- Calibrated probabilities require an exact host-pinned evidence ID bound by
  profile admission. Caller adapters derive the finite `noul` complement and
  provide the complete ordered `yes`/`no` probability pair; DAR verifies and
  routes that result. Native booleans must be translated at the caller
  boundary.
- DMS-18 conformance uses a generic caller-owned fake and does not presume a
  Kev adapter.
- DMS-19 enumerates the six requested capability families and requires each
  row to be selected, deferred, or unsupported with caller/use-case evidence,
  contract details, and rationale. Identity is a caller-supplied claim check;
  DAR validates only observable request lifecycle state (deadline/cancellation)
  and does not attest to private native-model lifecycle.
- The task list now records the staged execution dependency and the
  implementation-ready disposition for contract freeze/matrix discovery.

Validation: `git diff --check` passed. No model, endpoint, server, network, or
download was used. Later GREEN work must run the task-specified fake-focused
tests, full suite, and Ruff after the contracts and matrix are frozen.

## DMS-18 Implementation and DMS-19 Capability Matrix — 2026-10-06

DMS-18 is implemented through the existing `decision_step` primitive. The
manifest accepts `choice`, `scores`, and constrained `noul` modes; score results
are validated in declared option order; `argmax` is deterministic; threshold
routing is probability-only and inclusive; and calibrated results require the
profile's exact `calibration_evidence_id`. Noul remains a caller adapter
translation to an ordered `yes`/`no` probability pair. Focused decision,
validation, and executor tests pass (`378 passed` in the adjacent suite).
Current Von, Julia 1, Laya-MLX, and Jev-Style adapter tests cover their native
score/noul shapes where supported; the generic executor fake covers workflow
routing.

DMS-19's initial matrix is deliberately limited to the existing
`llama-cpp-python>=0.3.29,<0.4.0` direct in-process seam. DAR does not expose a
server endpoint or own model/runtime lifecycle.

| Capability | Disposition and identified caller | DAR contract and upstream surface | Acceptance / limits / unsupported cases |
| --- | --- | --- | --- |
| Text/chat generation | selected — `local_models` direct caller | `OpenAIModelRequest` → `Llama.create_chat_completion`; sync and async adapters; text in/text out | Existing fake-backend parity tests normalize content, identity, limits, errors, and deadlines; no server or download in tests. |
| Structured output | selected — workflow model caller using `response_format` | Same chat API with JSON-schema `response_format`; text/JSON out | Existing tests preserve schema request and bounded response normalization; malformed output and identity failures are rejected. |
| Tool calls | selected — workflow tool-calling caller | Same chat API with `tools`/`tool_choice`; ChatML function-calling profile when configured | Existing fake tests preserve explicit and ChatML function-call tool calls; unsupported profiles do not advertise tool capability. |
| Embeddings | selected — retrieval/index caller | `Llama.create_embedding`; sync and async embedding adapters; text in/vector out | Existing tests cover dimensions, batching, identity, result limits, and backend errors; multimodal embeddings are unsupported. |
| Multimodal input | unsupported — no DAR request modality or identified llama.cpp caller contract | No `OpenAIModelRequest` image/audio payload is admitted by this seam | Not advertised and no adapter normalization is added; a future row requires a named caller, payload bounds, and fake evidence. |
| Decision-model inference | deferred — no identified llama.cpp-native decision caller yet | Generic `DecisionModelBinding` is available; a caller must map native output to it and request `DecisionMode.SCORES` for DMS-18 scores/noul | No llama.cpp decision capability is advertised; Clef remains optional and in-process only if a caller supplies that binding. |

Across selected rows, callers own model loading, native bindings, transport,
credentials, lifecycle, and artifact paths. DAR validates caller-supplied
identity claims and only observable deadline/cancellation state; it does not
observe private native lifecycle state. The matrix intentionally contains no
`/v1/systemone` endpoint.

Validation: `poetry run pytest tests/test_decision_models.py
tests/test_validation.py tests/test_executor.py -q` → `378 passed`. The full
tests/test_validation.py tests/test_executor.py -q` → `379 passed`; with the
llama.cpp local-model and OpenAI client-seam suites included, `619 passed`.
Ruff and diff checks pass. After repairing the DMS-17 test fixture to bind
approval to the selected profile, a full `poetry run pytest -q` run reached
3,082 tests: 3,080 passed, one skipped, and two unrelated environment-bound
tests failed. The failures are macOS `sandbox-exec` startup exceeding the
one-second SVG fixture limit and the M4.4 clean-Codex author actor timing out;
neither exercises the changed decision-model or llama.cpp paths. The final
closeout checkbox remains open until those repository-level failures are
repaired or explicitly waived.
