# Decision Model Candidate Evaluation

Status: **DMS-01 evaluated; no candidate recommended.** Kev-0.6B completed the
approved synthetic evaluation and failed the decision and retention quality
thresholds. Kev-0.8B, Jev-Style 0.8B v3, and the approved DMS-06 runs for Von,
PoorJev, and LitJev also failed one or more quality gates; NanoJev remains
deferred. No production model is admitted.
The original Qwen candidate cohort is local-only. Server-backed Laya
integration remains external-client-owned. Laya-MLX is a separate direct,
in-process local candidate under DMS-08. Its approved frozen-fixture run failed
the decision and retention quality thresholds; no Laya-MLX profile is admitted
or recommended.

Jev-Style 0.8B v3 completed its approved DMS-01 frozen-fixture evaluation. It
failed the decision and retention gates, so it is rejected for the current
criteria and is not recommended for production. The run used the pinned 8-bit
MLX checkpoint and isolated runtime; detailed metrics and receipts are below.

A separate DMS-13 track measures end-to-end context preservation on the
official LongMemEval-S benchmark. It compares full history, deterministic
recency, and model-guided message retention with a shared downstream answer
model and matched answer-model-tokenizer history budgets. Its exact proposal
and token measurements are in
[`evaluation/dms13-corpus-manifest.json`](evaluation/dms13-corpus-manifest.json).
The user requested a local judge after the selected `gpt-6-luna` route would
have sent benchmark-derived data to `chatgpt.com`. DMS-13 now pins
`mlx-community/Llama-3.1-8B-Instruct-4bit@90215b22ec18e72f623dde2ea7af4097025160e2`
as an in-process MLX-LM judge. Its complete snapshot was downloaded and
SHA-256 verified; a load-only smoke check passed with Metal enabled and 4.52 GB
peak memory. No benchmark inference has started. The exact local-only run
approval remains pending; no benchmark-derived data will be sent to a model
endpoint. DMS-13 does not change the frozen synthetic DMS-01 criteria or any
recorded candidate result.

The user approved the fixture hashes, acceptance thresholds, and retention
utility definition below on 2026-09-26, before candidate output was inspected.

Related research reference: [Jev-style local options](references/jev-style-local-options.md)
covers additional local model projects and training approaches. It informed
candidate discovery; each candidate-specific comparison still requires an
exact artifact, scoped approval, and preflight. The approved DMS-06 alternative
results are recorded below.

## DMS-13 LongMemEval-S context-preservation proposal

The corpus is pinned to cleaned LongMemEval-S revision
`98d7416c24c778c2fee6e6f3006e7a073259d48f`; its 277,383,467-byte JSON file
matches SHA-256
`d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`.
The source repository is pinned at
`9e0b455f4ef0e2ab8f2e582289761153549043fc`; both publish MIT terms. The
corpus contains 500 questions, 30 abstention cases, six question types, and
246,750 history messages. Questions, answers, and `has_answer` evidence labels
are removed before any compactor call.

The proposed reader is
`mlx-community/Qwen3-4B-Instruct-2507-4bit@50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b`,
with its pinned tokenizer/chat template, temperature 0, no thinking, and a
512-token answer reserve. Exact tokenizer measurement across all items found
history lengths min/p50/p95/max of 112,712/120,653/123,090/125,751 tokens and
complete prompt lengths of 112,767/120,714/123,142/125,810. All prompts fit
the declared 262,144-token context with the reserve. Proposed retained-history
budgets are 8,192, 16,384, 32,768, and 65,536 tokens; all source histories
exceed these budgets, so recency and model-guided conditions can be compared
at each matched budget.

The proposed compactor is the already evaluated local Von 1.2.0 profile, with
source, model, runtime lock, and runtime package versions pinned in the
manifest. Von failed DMS-01 and DMS-14 criteria; using it in this exploratory
context-preservation comparison would not reverse those findings or admit a
production profile.

The combined Python 3.14.7 runtime pins Von's Torch/Transformers path, the Qwen
MLX reader, and the Llama MLX judge in
[`evaluation/dms13-runtime/`](evaluation/dms13-runtime/); its updated lock
SHA-256 is
`6c2acc5c4ab2d93503348e70301e467ccae4e147e59fb770e25204e1624fe201`. It also
pins Von's required `pydantic==2.13.5`, resolved from the pinned Von source
lock. The isolated runtime is installed under `/private/tmp/dms13-poetry-envs`;
all pinned packages and all three model loads were verified, and Metal is
available. The initial runtime
[preflight receipt](evaluation/preflight-dms13-2026-09-27.json) verifies the
runtime setup. The run-specific
[preflight receipt](evaluation/preflight-dms13-run-2026-09-28.json) binds the
complete evaluation harness, current host/storage check, and pinned artifacts.
The local Llama scorer is pinned to
`mlx-community/Llama-3.1-8B-Instruct-4bit@90215b22ec18e72f623dde2ea7af4097025160e2`;
all eight files and digests are recorded in the manifest and preflight. Its
model weights are 4,517,489,037 bytes under the Llama 3.1 Community License.
The DMS-13 runtime lock does not include the OpenAI package. After adding
Von's Pydantic dependency, two approved attempts reached the first Qwen answer
generation and stopped because MLX-LM 0.31.3 does not accept `temp=0`. Each
attempt completed Von scoring for the first item's 273 turns, generated no
answer tokens, and made zero judge calls. No benchmark data left the machine.
The runner now passes MLX-LM's pinned greedy sampler to both Qwen and Llama.
One-token synthetic generations passed for both models using the corrected
sampler; no benchmark data was used in that smoke. The corrected harness and
refreshed preflight are bound in a new pending receipt; approval is needed
again because the harness digest changed.

The [pinned official evaluator](https://github.com/xiaowu0162/LongMemEval/blob/9e0b455f4ef0e2ab8f2e582289761153549043fc/src/evaluation/evaluate_qa.py)
supports GPT-4o, GPT-4o mini, and local Llama 3.1 70B behind an
OpenAI-compatible HTTP endpoint. It uses question-type-specific prompts,
temperature 0, and a ten-token verdict; its label rule accepts any response
containing `yes`. DMS-13 retains those prompts and label semantics while using
the separate local 8B MLX checkpoint above in-process without a server. This is
not the official 70B/GPT-4o scorer and results are not directly comparable to
published scorer results. All 4,500 question/gold-answer/candidate-answer
judgments remain local; only pinned public artifacts are downloaded. The
evaluation persists boolean labels and aggregate metrics, never raw prompts or
scorer responses.

Proposed primary budget is 32,768 history tokens. Proposed acceptance compares
paired model-guided and recency outcomes over 10,000 question-type-stratified
bootstrap samples (seed 13): answer-accuracy noninferiority requires the
95-percent interval's lower bound to exceed -0.03; evidence-turn recall may
not be more than 0.05 below recency; and at least one of answer accuracy or
evidence-turn recall must improve by 0.05 at the primary budget. The user
approved the thresholds and original public-API run configuration on
2026-09-28, then requested the switch to a pinned local MLX Llama judge. That
changes the exact scorer binding, so the refreshed local-only run receipt still
requires approval. No benchmark inference or judge call has occurred.

## Host and DAR fit

- Host: Apple M3 Pro (Mac15,6), 36 GB unified memory, arm64 macOS 26.6.2.
- Free space at reconnaissance: 32 GiB. Approximate base weight files for the
  five local candidates total about 45 GiB, before cache copies or runtime
  overhead. No cache was inspected. Recheck available storage before any run.
- The optional `transformers-peft` extra currently caps PEFT at
  `>=0.19.1,<0.20.0` and Transformers at `>=5.0.0,<6.0.0`. Kev-4B asks for
  PEFT `>=0.21` and Transformers `>=5.17`; see the compatibility smoke below.
  DAR's Torch range is `>=2.9,<3`, while the pinned Kev source runtime declares
  `>=2.6,<2.9`, so packaged-runner compatibility still has a Torch-range
  conflict.
- DAR's reviewed native local runner profile is
  `transformers-peft-single-image-v1`; it does not implement the decision
  scoring/head interfaces listed below. DMS-01 uses an approved research
  harness to recommend a candidate, not to admit a production profile. DMS-04
  must bind and verify the exact DAR runner/material lock before production
  selection.
- Existing deterministic session pruning is recent whole-turn retention at
  `src/dynamic_agent_runner/executor.py::_pruned_session_messages`. A matched
  token-budget baseline will be implemented in the evaluation harness without
  changing that runtime behavior.

## Candidate artifact evidence

Revisions are immutable Hugging Face commit IDs checked on 2026-09-26. Weight
sizes are repository file sizes, not peak inference memory. Unknown values are
not inferred from parameter counts.

| Candidate artifact (revision) | Base and license | Task/output and inference | Input limit and memory evidence |
|---|---|---|---|
| `jaredpalmer/kev-0.5b` (`9ce2fd39db3a397c89733f94af948e3d1fdfffcd`); base `Qwen/Qwen2.5-0.5B` (`060db6499f32faf8b98477b0a26969ef7d8b9987`) | Apache-2.0. Card labels it a superseded prototype. | LoRA plus pointer head; choice, score, and no-ul outputs. Card describes fp32 Apple MPS. | State path: <=384 training tokens per branch; serving path: 8192 tokens per branch. Base file 988,097,824 B; adapter/head 37 MB per card. Peak inference memory not reported. |
| `jaredpalmer/kev-0.6b` (`dece6dba8d43f0f7ded45e9f5b9df12474d90843`); base `Qwen/Qwen3-0.6B-Base` (`da87bfb608c14b7cf20ba1ce41287e8de496c0cd`) | Apache-2.0. This is Qwen3, not Qwen2.5. | LoRA plus pointer head; reference is Apple Silicon. | Candidate input limit and peak memory not published. Base file 1,192,135,096 B; rough BF16 base weights ~1.2 GB, adapter/head ~42 MB by card. |
| `jaredpalmer/kev-4b` (`139fdd94f1b6a6ad80cc15e08fcb99cac885a101`); base `Qwen/Qwen3.5-4B-Base` (`1001bb4d826a52d1f399e183466143f4da7b741b`) | Apache-2.0. This is Qwen3.5. | LoRA plus pointer head; choices, scores, and no-ul. Current card requires Transformers >=5.17 and PEFT >=0.21. | 8192 serving context; card reports ~9 GiB GPU memory for BF16. Base files 9,319,828,056 B. Card reports MPS is slow without DeltaNet kernels. |
| `jaredpalmer/kev-8b` (`c80773da7f383f93c4dbff0c0b008e0463f9145a`); base `Qwen/Qwen3-8B` (`49e3418fbbbca6ecbdf9608b4d22e5a407081db4`) | Apache-2.0. This is Qwen3. | LoRA plus pointer head; card supports Apple MPS/BF16. | Candidate input limit not clearly published. Card reports ~17 GB BF16 / ~33 GB fp32. Base files 16,381,516,776 B; adapter/head ~183 MB per card. |
| `bespokelabs/Bespoke-Nimble-9B` (`bd792f44ec8e265be861bfcdf4e05967ffe0e858`); card base `Qwen/Qwen3.5-9B` (`c202236235762e1c871ad0ccb60c8ee5ba337b9a`) | Apache-2.0. | Fine-tuned decision scoring: choice, boolean, rubric probabilities; scores answer tokens, up to 255 choices. PyTorch/CUDA BF16 reference; source also points to a Mac/MLX loader. | 8192 tokens. Adapter ~173 MB; base files 19,306,310,880 B. No M3 Pro peak-memory measurement. CUDA reference is unavailable on this Mac. |
| `convaiinnovations/laya` (`55cf4c4ebb4ebe31b2550e8bdf3bd21b99753851`), English root checkpoint | Apache-2.0; ModernBERT-large, 421M. | One-pass typed choice/score/no-ul outputs and probabilities; Transformers `laya` runtime, MPS/CPU/CUDA. | 512 token English root context; weight file 842,609,210 B. Peak memory not published. |
| Alternative server-backed Laya artifact: `convaiinnovations/laya-typed-decisions` (`1a793eb568e6718f15941d08f85432581df534e3`) | Apache-2.0; 421M typed-decision checkpoint. | Typed decision outputs. | 1024 token context; exact candidate runtime requirements and peak memory require verification before any run. |

### Kev-4B dependency compatibility smoke — 2026-09-27

The pinned Kev-4B adapter (`jaredpalmer/kev-4b@139fdd94f1b6a6ad80cc15e08fcb99cac885a101`)
and base (`Qwen/Qwen3.5-4B-Base@1001bb4d826a52d1f399e183466143f4da7b741b`)
loaded and completed one synthetic choice request on CPU. The isolated runtime
used Python 3.13.15, PEFT 0.21.0, Transformers 5.17.0, and Torch 2.8.0. The
returned probabilities were finite and normalized; peak RSS was 15.3 GiB and
load plus inference took 88.5 seconds. No project dependency or lockfile was
changed. This confirms the upstream PEFT/Transformers pairing can execute the
pinned Kev-4B checkpoint. It is a compatibility smoke only, not a DMS-14
corpus score or evidence that DAR's Torch `>=2.9` range works with Kev's
declared Torch `<2.9` range.

The table's Laya checkpoints are the server-backed Transformer artifacts and
remain external-client references; they are not the Laya-MLX candidate. DMS-08
evaluated this distinct direct-local pairing:

| Candidate | Current evidence and disposition |
|---|---|
| Laya-MLX: source [`mizorewww/laya-mlx`](https://github.com/mizorewww/laya-mlx/tree/0a859518634112655cb97c745dbf04f5191aaf13) at `0a859518634112655cb97c745dbf04f5191aaf13`; MLX checkpoint [`aac6fef/laya-typed-decisions-mlx`](https://huggingface.co/aac6fef/laya-typed-decisions-mlx/tree/28416e78cb26a239a4eabaa2e084904ec5e6cacb) at `28416e78cb26a239a4eabaa2e084904ec5e6cacb`; provenance base `convaiinnovations/laya-typed-decisions` at `f9ab0b228f0fc0f14d873dbc99038f135c2da1b2`. | Approved local MLX evaluation completed; rejected for DMS support because frozen decision and retention quality gates failed. No DAR production profile was implemented or admitted. |

## Laya-MLX exact artifact and runtime

The source is Apache-2.0 [`mizorewww/laya-mlx`](https://github.com/mizorewww/laya-mlx/tree/0a859518634112655cb97c745dbf04f5191aaf13), revision
`0a859518634112655cb97c745dbf04f5191aaf13`, package version 0.2.0. Its
[`pyproject.toml`](https://github.com/mizorewww/laya-mlx/blob/0a859518634112655cb97c745dbf04f5191aaf13/pyproject.toml)
requires Python >=3.11, Apple Silicon/macOS MLX >=0.32.2,<0.33, NumPy >=1.26,
Hugging Face Hub >=0.34,<2, and Tokenizers >=0.21,<1. The direct API is
`laya_mlx.load(...).predict(state, questions)`; it runs in process without a
server, PyTorch, or Transformers. The selected typed-decisions checkpoint is
English-only; its model card documents Apple Silicon macOS 26+ for the local
runtime. The upstream source dependency itself uses MLX's broader platform
support, but only macOS 26.6.2 was exercised here.

The model is Apache-2.0 [`aac6fef/laya-typed-decisions-mlx`](https://huggingface.co/aac6fef/laya-typed-decisions-mlx/tree/28416e78cb26a239a4eabaa2e084904ec5e6cacb),
revision `28416e78cb26a239a4eabaa2e084904ec5e6cacb`: 421,293,830 FP16
parameters, a 842,609,225-byte weight file, and a 1,024-token total input
limit. Provenance is Apache-2.0
[`convaiinnovations/laya-typed-decisions`](https://huggingface.co/convaiinnovations/laya-typed-decisions/tree/f9ab0b228f0fc0f14d873dbc99038f135c2da1b2),
revision `f9ab0b228f0fc0f14d873dbc99038f135c2da1b2`. The checkpoint tokenizer
is the exact pinned `tokenizer/tokenizer.json` and `tokenizer_config.json`.
The downloaded model files were SHA-256 checked against the checkpoint's
`manifest.json`; the inference materials are:

| File | Bytes | SHA-256 |
|---|---:|---|
| `model.safetensors` | 842,609,225 | `804ef8802b4cac7a67913b0cfb8448659e934a50284aaa867b98d7d9a6e7d1e0` |
| `encoder/config.json` | 2,084 | `5268d24ad3b77c8151de5dcb0762ba4391619aad9ab0bda33e36fb083cfeae6d` |
| `rl_agent_config.json` | 848 | `d99c800b818cb1a60734adba961c27abeaff2d142bb9fc473edb34b7de32fde9` |
| `tokenizer/tokenizer.json` | 3,583,228 | `6c8aaa9a542084f2457eab775d4eeb51f92a70c0fd9de28d5edb0ddec3c08d30` |
| `tokenizer/tokenizer_config.json` | 337 | `08d4cf3ac4dca381759441b85b91a6d40e688471dcd33d15d6649eb0a9a854d1` |
| `mlx_config.json` | 322 | `fe0d126c46e70e28e47767801b15e3219280484ce298cab6aadcd339ca242cae` |

The source API maps `choice` to a selected named option and probabilities,
`score` to an expected ordinal score plus probabilities over rubric levels,
and `noul` to P(true). The result also carries confidence/action fields and
four-decimal probabilities. This run used only `choice` for decisions and
binary `keep`/`drop` retention questions. The DMS runner records those outputs
as ordinary `probability`, not calibrated-probability evidence. The checkpoint
ships fitted temperatures, but its `choice:11+` temperature 0.1006 is clamped
by the upstream loader to 0.5 and explicitly treated as uncalibrated; the DMS
retention results also fail the frozen calibration criteria.

The checkpoint card reports MLX 0.32.2 validation on M3 Max and 63/63 selected
answer parity with its upstream PyTorch implementation. That is port-fidelity
evidence, not DMS task accuracy. The DMS evaluation used an isolated Poetry
runtime on Python 3.14.7, arm64 macOS 26.6.2, and MLX 0.32.2. Its independent
lock is [`evaluation/laya-mlx-runtime/poetry.lock`](evaluation/laya-mlx-runtime/poetry.lock)
(SHA-256 `8e985781ad08f589f20780b0ee971f26ce6f3a526ec4111e2031765894e75884`);
the runtime project and lock are separate from DAR's root Poetry dependency
set. No DAR root Poetry files were changed for this evaluation, and no upstream
`uv.lock` was imported.

The approved preflight is
[`evaluation/preflight-laya-mlx-dms08-approved-2026-09-27.json`](evaluation/preflight-laya-mlx-dms08-approved-2026-09-27.json).
It verified the exact source, model, provenance base, fixture and harness
hashes, 36 GiB host memory, 76.9 GB free storage, installed pinned runtime, and
Metal availability. Inference ran in process with network access disabled
after the exact checkpoint snapshot was materialized. The redacted outputs and
evaluation receipt are
[`evaluation/laya-typed-decisions-receipt.json`](evaluation/laya-typed-decisions-receipt.json),
[`evaluation/laya-typed-decisions-predictions.jsonl`](evaluation/laya-typed-decisions-predictions.jsonl),
[`evaluation/laya-typed-decisions-token-counts.jsonl`](evaluation/laya-typed-decisions-token-counts.jsonl),
and [`evaluation/laya-typed-decisions-measurements.json`](evaluation/laya-typed-decisions-measurements.json).

Decision accuracy was 0.685/200 (95% Wilson interval 0.618–0.745), with no
invalid decision outputs after normalizing only the source API's four-decimal
rounding drift. Retention at the matched 50% token budget achieved
F1 0.625, keep recall 0.50, and category-macro token-weighted utility 0.593
versus recency's 0.306, a +0.287 gain. Thus the utility gate passed, while
decision accuracy, retention F1, keep recall, and combined calibration failed.
Decision ECE was 0.1001 and decision Brier 0.404 versus the 0.771 prevalence
baseline; retention ECE was 0.153 and retention Brier 0.186 versus the 0.250
prevalence baseline. Combined score calibration is unqualified. Operations
passed: no OOM, peak RSS 984,383,488 bytes, warm p50 25.9 ms and p95 68.1 ms.
The first checkpoint materialization and model load took 14.65 s; the recorded
cold load after local materialization was 582 ms. The model is rejected for DMS
support; DMS-10 first-party adapter work is deferred by its explicit quality
gate.

## DMS-09 MLX dependency decision

The existing DAR `mlx` extra resolves `mlx-lm==0.31.3`, whose dependency
requires MLX >=0.31.2. The separate `mlx-embedding` extra pins MLX 0.32.2.
Both are compatible with Laya-MLX's MLX >=0.32.2,<0.33 requirement at the
resolved version 0.32.2. `poetry check --lock` and the existing MLX generation
and embedding contract checks pass with the current lock. DMS keeps its Poetry
configuration unchanged because the DMS-08 candidate failed quality gates;
the temporary candidate runtime is the isolated Poetry project above. The
tested evaluation combination was Python 3.14.7, arm64, macOS 26.6.2; this does
not claim broader DAR first-party support for Laya-MLX.

## Kev-0.8B evaluation result

The latest small Kev checkpoint is a possible candidate for a separately
approved follow-on DMS-01 run: `jaredpalmer/kev-0.8b` at Hub revision
`9a45d25eb2ab761841196625383fa1dff0e56c1e`, based on
`Qwen/Qwen3.5-0.8B-Base` at `dc7cdfe2ee4154fa7e30f5b51ca41bfa40174e68`.
The adapter and head are 43,338,624 and 2,103,999 bytes; the base weight file
is 1,746,942,600 bytes. The exact adapter LFS SHA-256 is
`9b908623acb162118575f4e7a94524f9c139c335be4bfb74d6cfceca01e1885a`; the
base weight SHA-256 is
`c2b1e5a17d9c1e27685d92ed9b382911ebb99955ecd89052d1721241adfbab6c`.
Both are Apache-2.0. The upstream code is pinned here to
`jaredpalmer/kev@5920c5fe4ca8e0970ed4209ac2c9b8e18bea5109` and exposes the
in-process `Checkpoint.load` scoring path; its optional HTTP server is not
required for local inference.

The model card reports a 65,536-token state limit; each question branch may
extend the state by up to 8,192 tokens. The Qwen base config allows 262,144
positions. Its reported accuracy was
0.827 on its in-distribution decision-v7 development set and 0.697 on its
transfer-v4 locked test; the card reports its fitted temperature as 2.35 and
out-of-domain Brier/ECE of 0.430/0.049. These are publisher results, not DMS
measurements.
The project requires Python `>=3.12,<3.14`, Transformers `>=5.17,<6`, Torch
`>=2.6,<2.9`, and PEFT `>=0.21`. Python 3.13 fits DAR's supported interpreter
range, but DAR's current Transformers/PEFT extra caps PEFT below 0.20, so an
exact DAR runtime/material closure is not established. The approved DMS-01 run
used an isolated Python 3.13.15 CPU runtime from the pinned `uv.lock` and
completed all 240 cases without inference failures. Decision accuracy was
0.82, but the explicit-rule category was 0.425 (below 0.70). Retention F1 was
0.390, keep recall was 0.388, and category-macro token-weighted keep-recall
utility was 0.309 versus 0.309 for recency, a +0.001 gain (below +0.05).
Decision and retention ECE were 0.152 and 0.264 (both above 0.10). Operations
passed with no OOM and 5,995,266,048-byte peak RSS (~5.58 GiB); cold inference
was 3,696 ms, warm p50 3,654 ms and p95 5,627 ms. Kev-0.8B is rejected for
DMS-04, not a recommendation or admission.

The approved preflight and redacted result artifacts are
[`preflight-kev08-dms01-approved-2026-09-26.json`](evaluation/preflight-kev08-dms01-approved-2026-09-26.json),
[`kev-0.8b-receipt.json`](evaluation/kev-0.8b-receipt.json),
[`kev-0.8b-measurements.json`](evaluation/kev-0.8b-measurements.json),
[`kev-0.8b-predictions.jsonl`](evaluation/kev-0.8b-predictions.jsonl), and
[`kev-0.8b-token-counts.jsonl`](evaluation/kev-0.8b-token-counts.jsonl).

Primary references: [Kev-0.8B model card](https://github.com/jaredpalmer/kev/blob/5920c5fe4ca8e0970ed4209ac2c9b8e18bea5109/docs/model-cards/kev-0.8b.md),
[Kev source revision](https://github.com/jaredpalmer/kev/tree/5920c5fe4ca8e0970ed4209ac2c9b8e18bea5109),
[Kev-0.8B adapter revision](https://huggingface.co/jaredpalmer/kev-0.8b/tree/9a45d25eb2ab761841196625383fa1dff0e56c1e), and
[Qwen3.5-0.8B base revision](https://huggingface.co/Qwen/Qwen3.5-0.8B-Base/tree/dc7cdfe2ee4154fa7e30f5b51ca41bfa40174e68).

## Provisional local design and manual-test target

Use Kev-0.6B at adapter revision
`dece6dba8d43f0f7ded45e9f5b9df12474d90843` and base revision
`da87bfb608c14b7cf20ba1ce41287e8de496c0cd` to make the initial small local
profile design and manual test concrete. It is the smallest reviewed Kev
candidate other than the card's superseded 0.5B prototype, and its card gives an
Apple Silicon reference path. This is a provisional engineering target, not a
production selection or a claim that its scores pass the acceptance criteria.
Unit tests continue to use fake adapters. Production admission still requires
the approved DMS-01 evaluation and exact reviewed runner/material lock.

Primary sources: [Kev source](https://github.com/jaredpalmer/kev), [Kev
0.5B](https://huggingface.co/jaredpalmer/kev-0.5b/tree/9ce2fd39db3a397c89733f94af948e3d1fdfffcd),
[Kev 0.6B](https://huggingface.co/jaredpalmer/kev-0.6b/tree/dece6dba8d43f0f7ded45e9f5b9df12474d90843),
[Kev 4B](https://huggingface.co/jaredpalmer/kev-4b/tree/139fdd94f1b6a6ad80cc15e08fcb99cac885a101),
[Kev 8B](https://huggingface.co/jaredpalmer/kev-8b/tree/c80773da7f383f93c4dbff0c0b008e0463f9145a),
[Bespoke Nimble](https://huggingface.co/bespokelabs/Bespoke-Nimble-9B/tree/bd792f44ec8e265be861bfcdf4e05967ffe0e858),
[Nimble source](https://github.com/bespokelabsai/nimble), [Laya English
checkpoint](https://huggingface.co/convaiinnovations/laya/tree/55cf4c4ebb4ebe31b2550e8bdf3bd21b99753851),
[Laya typed checkpoint](https://huggingface.co/convaiinnovations/laya-typed-decisions/tree/1a793eb568e6718f15941d08f85432581df534e3),
and [Laya loader source](https://github.com/xosi/laya). Card-reported performance
figures are not used as acceptance evidence.

## Approved frozen evaluation set

Synthetic-only fixtures are prepared; inputs and answer key are separate so
the key can remain sealed from candidate runners:

- Inputs: `evaluation/dms01-inputs.jsonl` (240 rows: 200 decisions and 40
  retention scenarios, each containing four candidate messages).
- Labels: `evaluation/dms01-labels.jsonl` (240 rows; no user transcripts or
  other sensitive data).
- SHA-256 inputs: `6d0230190f455d3f488881ef0f709881fba783f33bab4d5a6a93db576cf5c73f`.
- SHA-256 labels: `a87f79b376b7e0c790df78cdd6a623d06450364d6d7c708974c8a953d7b7c7a5`.
- Decision cases are balanced across numeric boundary, exception precedence,
  fact selection, explicit rule, and missing evidence (40 each).
- Retention cases cover renewal, release, booking, invoice, and migration (8
  per scenario category, four candidate messages each). Each candidate's
  tokenizer defines the same 50% input-token budget policy.

The fixtures and thresholds below are frozen. Retention utility is the macro
average across retention categories of token-weighted gold-keep recall: tokens
in labeled `keep` messages retained by the candidate divided by tokens in all
labeled `keep` messages, using the candidate tokenizer. The recency baseline
uses the same per-message token counts and the same 50% token budget. DMS-01
uses `scripts/evaluate_decision_models.py`, tested with fake outputs before
real inference. Its dated preflight records fixture hashes, exact artifacts,
the approved harness/runtime, host and storage availability, and whether the
run uses an external research harness or an admitted DAR runner. If any gate
fails, stop before download or inference. An external research harness may
provide DMS-01 measurements; only the DMS-04 binding can establish DAR
production admission.

## Approved acceptance criteria

1. Decision accuracy: at least 0.80 overall and 0.70 in each of the five
   categories. Report exact-match accuracy and 95% Wilson intervals. Invalid,
   missing, timeout, oversize, and abstaining outputs count as incorrect, with
   their rates reported separately.
2. Retention: compare against a deterministic recency baseline at an identical
   per-model-tokenizer 50% budget. Require keep/drop F1 >=0.80, keep recall
   >=0.90, and at least a 5 percentage-point utility improvement over that
   baseline. Report results overall and by scenario category. The runtime's
   pinned/recent/unresolved/tool-pair protections remain deterministic and
   outside the scorer.
3. Calibration: if probability semantics are claimed, report Brier score and
   10-bin expected calibration error. Call probabilities calibrated only if
   ECE <=0.10 and Brier score beats a prevalence-only baseline. Otherwise
   report ranking scores as uncalibrated and do not use them as probabilities.
4. Operations: measure cold/warm latency p50 and p95 and peak resident memory;
   require no OOM and peak <=24 GiB. Report runtime and precision. Do not
   extrapolate unmeasured memory from parameter count.
5. Recommendation and admission are separate. DMS-01 recommends a candidate
   only after approved evaluation and design-level feasibility review. DMS-04
   makes the production admit/reject decision only after fake-verifying an
   exact DAR runner/material lock for the base, adapter/head, tokenizer, and
   runtime and completing its separately authorized competency check, with no
   remote code or artifact substitution.

The deterministic baseline must use the same candidate-message inputs,
tokenizer, and budget; labels are applied only after its retained set is fixed.
Metric code and baseline behavior must be reviewed before candidate inference.

## Kev-0.6B measured result

The approved preflight is recorded at
[`evaluation/preflight-dms01-2026-09-26.json`](evaluation/preflight-dms01-2026-09-26.json).
The aggregate-only run receipt is
[`evaluation/kev-0.6b-receipt.json`](evaluation/kev-0.6b-receipt.json). The
runner used the pinned Kev source commit and immutable adapter/base revisions
above, Python 3.13.15, torch 2.8.0, Transformers 5.17.0, PEFT 0.21.0, CPU
fp32, and no model server or remote code. All 240 synthetic cases completed;
there were no invalid, missing, timeout, oversize, abstention, or error rows.

- Decision accuracy was 0.685 overall (95% Wilson interval 0.618–0.745), below
  the 0.80 requirement. Category accuracy ranged from 0.175 to 1.00; explicit
  rule (0.175), numeric boundary (0.40), and fact selection (0.975) are shown
  in the receipt, with fact selection above the 0.70 floor.
- Retention F1 was 0.378 and keep recall was 0.388, below 0.80 and 0.90. The
  approved utility was 0.260 versus recency's 0.309, a -0.049 gain rather than
  the required +0.05.
- Decision and retention outputs did not meet the ECE calibration threshold;
  do not treat their scores as calibrated probabilities.
- Operations passed: no OOM, peak RSS 4,197,040,128 bytes (~3.91 GiB), cold
  inference 139 ms, warm p50 125 ms and p95 359 ms.

Kev-0.6B is **rejected for DMS-04** because it fails both decision and
retention quality gates. Other candidates are deferred from this run: Kev-0.5B
is labeled a superseded prototype by its card; Kev-4B requires PEFT >=0.21,
while DAR's current optional extra pins PEFT <0.20, so it has no reviewed DAR
runtime closure; Kev-8B's card estimates ~17 GB BF16 / ~33 GB fp32 weights and
there is no approved, measured runtime profile for it in DAR; Nimble-9B is a
separate candidate outside the Qwen cohort and its reference is CUDA-oriented,
so it is not a DMS-04 Qwen recommendation. These deferrals are not claims that
those models fail the frozen quality criteria.

No local Qwen candidate is recommended for DMS-04. The approved follow-on
PoorJev and LitJev evaluations also failed the frozen thresholds; Von failed
them as well. A future candidate or changed acceptance criteria requires a
new scoped decision, exact-artifact preflight, and evaluation. The original
Qwen cohort did not select a Laya checkpoint. DMS-08 now tracks the separate
direct in-process Laya-MLX candidate above; server-backed Laya integration
remains external-client-owned.

## DMS-06 alternative review (2026-09-26)

This review records primary-source identity and integration fit. Kev's
evaluation approval covers only Kev-0.6B. Von 1.2.0 has since received a
candidate-specific approval and frozen-fixture evaluation; its measured result
is reported below. No author-reported benchmark or calibration claim is treated
as a DAR result. PoorJev and LitJev have since received candidate-specific
approval and completed frozen-fixture runs. Both failed one or more required
quality gates. NanoJev remains deferred for its host and licensing constraints.

| Name | Exact source artifact and match | Calibration, runtime, and license evidence | DMS decision |
|---|---|---|---|
| von | Source [wfzyx/von](https://github.com/wfzyx/von) at commit `fb6e7a937e4fc6b6e72b2ce5035edd56bc370e54`; model `wfzyx/von` at Hub revision `5df8185a4f2327ad0a7cd117cc4f701ac557b9ae` (395M parameters); API model name `von-1.2.0`. It provides `choice`, `noul`, `score`, and batched `system_one`, with in-process and HTTP options. | Hub metadata declares Apache-2.0. The project describes temperature fitting and calibration, but its published JevBench calibration axis is in-sample; author-reported held-out Noul prior is a distinct result. The repository documents CPU and Apple MPS support. Model config and runner set an 8,192-token maximum. DAR-host result: Python 3.14.7, CPU fp32, in-process, no server; see receipt below. | **Reject for the frozen quality thresholds.** The run missed decision and retention gates; it is not admitted for DAR support. |
| poorjev | Source [rupeshpoojary9/poorjev](https://github.com/rupeshpoojary9/poorjev) at commit `7e684e95db13b90238c63e6ab39e1a016263a168`; local NLI backend pins `MoritzLaurer/deberta-v3-base-zeroshot-v2.0` at Hub revision `8e7e5af5983a0ddb1a5b45a38b129ab69e2258e8`. Its `model.safetensors` is 368,871,908 bytes with LFS SHA-256 `6e8f2af78c828dcbd5243aac40fb87430376f0b8a9c288f4993df3ea3558d557`. This local inference backend maps typed questions to NLI hypotheses and returns option distributions; it fits the DMS decision shape, but its default temperature is 1.0 (no fitted calibration). | Code is MIT; the pinned Hub card declares MIT. Source supports CPU, MPS, and CUDA and documents offline inference after the initial download. The pinned runner truncates premise/hypothesis pairs at 512 tokens; the model config's maximum positions is also 512. README results use a small English support-oriented dataset and do not establish DMS performance. | **Reject for frozen quality thresholds.** Decision accuracy 0.54; retention F1 0.350, keep recall 0.313, and utility gain +0.032 (required +0.05). Scores are uncalibrated. |
| NanoJev | Source [TianyuCodings/NanoJev](https://github.com/TianyuCodings/NanoJev) at commit `76fdfc9ecdca45a9bcef17991a07d3041a87685a`; checkpoint `C-Tianyu/NanoJev` release `unified-games-v1` peeled to revision `047b927b30882a1138fc504821b82ac145a4b81a`. This is the step-400 `hard_lr1e5` run. Its option-set API is structurally mappable to choice decisions, but its published task focus is Maze, Snake, ViZDoom Basic, and Predict Position. | Repository source includes an MIT license; Hub metadata has no weights license. At the pinned source revision, `DecisionPredictor` rejects any device other than CUDA and calls CUDA APIs; the current host is macOS ARM with no CUDA. No general workflow decision metrics were established. | **Defer: host and license.** The pinned runner cannot execute on this host and weight licensing is undeclared. Do not patch candidate source or download weights for this comparison. |
| LitJev | Source [zhengxuyu/litjev](https://github.com/zhengxuyu/litjev) at commit `e7fb109a7466da9709028eb9c4e9f16eaeb4e2a3`; exact evaluation base selected as `Qwen/Qwen3-0.6B-Base` at revision `da87bfb608c14b7cf20ba1ce41287e8de496c0cd` (same immutable base used for the Kev-0.6B comparison). The 1,192,135,096-byte weight file has LFS SHA-256 `cd2a512003e2f9f3cd3c32a9c3573f820bb28c940f73c57b1ddaa983d9223eba`. LitJev's in-process `TransformersScorer` exposes the Jev choice/score/noul shape and supports Qwen3; the project default is 27B, so this is an explicit small-checkpoint pairing, not an upstream-tested default. | Code and Qwen base are Apache-2.0. LitJev says probabilities are not calibrated by default. The source provides in-process scoring, so no HTTP server is required for the evaluation. Its exact source lock has SHA-256 `bf0e1ff4aeda5ffe276e58f64edd7324bbaa8cec941fa174312b23e6bab0f1d8` and pins PyTorch 2.11.0. Qwen's config maximum is 32,768 positions; the candidate runner caps input at 16,384 tokens. | **Reject for frozen quality thresholds.** Decision accuracy 0.29; retention F1 0.559 and keep recall 0.50, despite utility gain +0.167. Scores are uncalibrated. |
| Jev-Style 0.8B v3 (completed DMS-12 evaluation) | Checkpoint and embedded MLX scorer [`chaoliangUNSW/Jev-Style-0.8B-Decision-v3-MLX`](https://huggingface.co/chaoliangUNSW/Jev-Style-0.8B-Decision-v3-MLX/tree/1235ccd1c95d5228a07616cd7e323c9e0532c1dc) at revision `1235ccd1c95d5228a07616cd7e323c9e0532c1dc`; provenance base [`Qwen/Qwen3.5-0.8B-Base`](https://huggingface.co/Qwen/Qwen3.5-0.8B-Base/tree/dc7cdfe2ee4154fa7e30f5b51ca41bfa40174e68) at `dc7cdfe2ee4154fa7e30f5b51ca41bfa40174e68`. The selected 8-bit `model.safetensors` is 799,973,748 bytes (SHA-256 `36890afff7a9da5b7228d81cd79434088267bd250c9eafab14539e6a5161a5fe`); runtime script `jev_style_decision_mlx.py` is 34,497 bytes (SHA-256 `e3ba700043d764f0fe50931cc3524d8329552bf4f4187f411671fd323e363acf`). The checkpoint manifest also pins tokenizer, readout, and config files. | Model card declares Apache-2.0 weights; it notes some training data has restrictive or unclear terms, which must be considered before redistributing derived artifacts. The embedded runtime exposes direct `JevStyleDecisionMLX.decide_many` for in-process typed choice, score, and yes/no decisions; no server is needed. The reviewed runtime set is Python 3.14.6, `mlx==0.32.2`, `mlx-lm==0.31.3`, `numpy==2.5.3`, `tokenizers==0.23.2`, and `huggingface-hub==1.33.0`; isolated lock SHA-256 is `5bcfab3b03b00500fb9fa2c4ba94a36de52d6453fe0b5312ea10f1cf81ed977d`. It applies a shipped global temperature by default and rejects over-budget input rather than truncating; DMS calibration remains unverified. The model card reports 0.80 GB for 8-bit weights and a 25,600-token limit, but peak inference memory is not reported. | **Reject for the frozen DMS-01 gates.** Decision accuracy 0.84; retention utility 0.477 (+0.168 vs. recency), but decision and retention thresholds failed. Full result and receipt follow below. |

Pinned primary-source links: [von source revision](https://github.com/wfzyx/von/tree/fb6e7a937e4fc6b6e72b2ce5035edd56bc370e54),
[von model revision](https://huggingface.co/wfzyx/von/tree/5df8185a4f2327ad0a7cd117cc4f701ac557b9ae),
[poorjev source revision](https://github.com/rupeshpoojary9/poorjev/tree/7e684e95db13b90238c63e6ab39e1a016263a168),
[poorjev local NLI backend](https://github.com/rupeshpoojary9/poorjev/blob/7e684e95db13b90238c63e6ab39e1a016263a168/src/poorjev/backends/local_nli.py),
[poorjev model revision](https://huggingface.co/MoritzLaurer/deberta-v3-base-zeroshot-v2.0/tree/8e7e5af5983a0ddb1a5b45a38b129ab69e2258e8),
[poorjev PRD](https://github.com/rupeshpoojary9/poorjev/blob/main/PRD.md),
[NanoJev source revision](https://github.com/TianyuCodings/NanoJev/tree/76fdfc9ecdca45a9bcef17991a07d3041a87685a),
[NanoJev model revision](https://huggingface.co/C-Tianyu/NanoJev/tree/047b927b30882a1138fc504821b82ac145a4b81a),
[NanoJev model card/license metadata](https://huggingface.co/C-Tianyu/NanoJev/blob/047b927b30882a1138fc504821b82ac145a4b81a/README.md), and
[NanoJev pinned predictor](https://github.com/TianyuCodings/NanoJev/blob/76fdfc9ecdca45a9bcef17991a07d3041a87685a/scripts/predict_toy_decisions.py),
[LitJev source revision](https://github.com/zhengxuyu/litjev/tree/e7fb109a7466da9709028eb9c4e9f16eaeb4e2a3), and
[Qwen3-0.6B-Base revision](https://huggingface.co/Qwen/Qwen3-0.6B-Base/tree/da87bfb608c14b7cf20ba1ce41287e8de496c0cd). Repository refs and the public Hugging Face model metadata were rechecked on 2026-09-27. Earlier lookup of the incomplete identifier `MoritzLaurer/deberta-v3-base` returned HTTP 401; the source's actual `...-zeroshot-v2.0` identifier is public and its immutable metadata is now recorded. The model snapshots were downloaded only to the approved external cache paths and their runner-verified file digests are recorded above.

PoorJev's fake-backed runner is [run_poorjev_dms06.py](../../tests/manual/run_poorjev_dms06.py),
with tests in [test_poorjev_dms06_runner.py](../../tests/test_poorjev_dms06_runner.py).
Its approved dated preflight is
[`evaluation/preflight-poorjev-dms06-approved-2026-09-27.json`](evaluation/preflight-poorjev-dms06-approved-2026-09-27.json).
The pinned source checkout, shared runtime lock, host capacity, storage,
fixtures, artifact, and harness hashes match. The approved run completed 240
cases with no invalid, missing, timeout, oversize, abstention, or error rows.
Its aggregate receipt is
[`evaluation/poorjev-receipt.json`](evaluation/poorjev-receipt.json); redacted
predictions, tokenizer counts, and measurements are in `evaluation/poorjev-*`.
Decision accuracy was 0.54 (95% Wilson interval 0.471–0.608). Retention F1 was
0.350, keep recall 0.313, and category-macro utility 0.341 versus recency's
0.309, a +0.032 gain below the +0.05 requirement. Decision/retention ECE were
0.450/0.493; both score sets remain uncalibrated. Operations passed: no OOM,
peak RSS 1,116,389,376 bytes, cold latency 23.62 s, warm p50 224 ms, p95 971 ms.
PoorJev is rejected for these frozen thresholds.

LitJev's fake-backed runner is [run_litjev_dms06.py](../../tests/manual/run_litjev_dms06.py),
with tests in [test_litjev_dms06_runner.py](../../tests/test_litjev_dms06_runner.py).
Its initial preflight is
[`evaluation/preflight-litjev-dms06-2026-09-27.json`](evaluation/preflight-litjev-dms06-2026-09-27.json);
the approved final preflight is
[`evaluation/preflight-litjev-dms06-approved-2026-09-27.json`](evaluation/preflight-litjev-dms06-approved-2026-09-27.json).
The exact source-locked runtime, including PyTorch 2.11.0, was installed under
`/private/tmp`; final preflight passed all host, storage, revision, fixture, and
harness checks. LitJev completed 240 cases with no invalid, missing, timeout,
oversize, abstention, or error rows. Its aggregate receipt is
[`evaluation/litjev-receipt.json`](evaluation/litjev-receipt.json); redacted
predictions, tokenizer counts, and measurements are in `evaluation/litjev-*`.
Decision accuracy was 0.29 (95% Wilson interval 0.232–0.356). Retention F1 was
0.559, keep recall 0.50, and category-macro utility 0.475 versus recency's
0.309, a +0.167 gain. Decision/retention ECE were 0.307/0.183, so scores remain
uncalibrated. Operations passed: no OOM, peak RSS 5,605,228,544 bytes, cold
latency 33.98 s, warm p50 317 ms, p95 438 ms. LitJev is rejected because
decision accuracy, retention F1, and keep recall miss their thresholds.

The Von model snapshot's two largest files are each 1,579,143,688 bytes
(`model.safetensors`) and 1,581,316,459 bytes (`option_marker.pt`), with pinned
SHA-256 digests enforced by the candidate-specific fake-tested manual runner.
Its runtime is pinned to the Von source `uv.lock` at SHA-256
`acaaa8abfcd3bc18eff1557fe2c73be73c00899eed5b1145de1b30518acf1f41`; inference
is CPU fp32 and in-process. The upstream loader otherwise falls back to a
mutable Hub default when a local checkpoint is incomplete, so the runner
requires the complete pinned snapshot, verifies both weight digests, and sets
Hub/Transformers offline mode before loading. The initially blocked preflight
is retained at
[`evaluation/preflight-von-dms06-2026-09-26.json`](evaluation/preflight-von-dms06-2026-09-26.json);
the approved preflight is
[`evaluation/preflight-von-dms06-approved-2026-09-26.json`](evaluation/preflight-von-dms06-approved-2026-09-26.json).
The isolated Python 3.14.7 runtime matched the pinned packages and lock digest.

### Von 1.2.0 frozen-fixture result

The approved run completed all 240 frozen cases (200 decisions and 40
retention tasks) on CPU fp32 with no server or remote code. The evaluator's
aggregate-only receipt is
[`evaluation/von-1.2.0-receipt.json`](evaluation/von-1.2.0-receipt.json); the
runner's redacted outputs are
[`predictions`](evaluation/von-1.2.0-predictions.jsonl),
[`tokenizer counts`](evaluation/von-1.2.0-token-counts.jsonl), and
[`measurements`](evaluation/von-1.2.0-measurements.json). The evaluator applied
the approved category-macro, token-weighted gold-keep recall utility at the
matched 50% budget.

| Decision category | Accuracy |
|---|---:|
| Exception precedence | 0.875 |
| Explicit rule | 0.875 |
| Fact selection | 0.550 |
| Missing evidence | 1.000 |
| Numeric boundary | 0.575 |

Overall decision accuracy was **0.775** (95% Wilson interval 0.712–0.827),
below the 0.80 threshold; fact selection also missed its 0.70 category floor.
Six of 200 decision results (3%) were invalid.

| Retention category | Model utility | Recency utility |
|---|---:|---:|
| Booking | 0.5193 | 0.3104 |
| Invoice | 0.2600 | 0.2600 |
| Migration | 0.3730 | 0.3333 |
| Release | 0.3794 | 0.2039 |
| Renewal | 0.1458 | 0.4236 |

Overall retention F1 was **0.387** and keep recall **0.363**, below 0.80 and
0.90. Utility was **0.3355** versus recency's **0.3062**, a gain of **0.0293**,
below the required +0.05.

Scores were **uncalibrated**. Decision ECE was 0.219 (threshold 0.10); retention
ECE was 0.083, but its Brier score 0.260 did not beat the prevalence baseline
0.250. Operational thresholds passed: no OOM, peak RSS 4,228,907,008 bytes
(about 3.94 GiB), cold latency 57.27 seconds, warm p50 178 ms, and warm p95
953 ms.

Von 1.2.0 is rejected for DMS support because its decision accuracy, fact
selection category, retention F1/recall, and retention utility gain miss the
pre-registered thresholds. Its operational performance does not offset these
quality failures. PoorJev and LitJev have also failed their frozen-fixture
quality gates; NanoJev remains deferred for the host and licensing reasons
above. No alternative is admitted.

The earlier Jev-style literature review remains available at
[references/jev-style-local-options.md](references/jev-style-local-options.md).
It informed discovery only and does not substitute for the pinned artifact or
the DMS-01 frozen evaluation. Jev-Style 0.8B v3 has since completed its
separate DMS-12 evaluation and failed the frozen quality gates; see the result
below.

## DMS-14 Published Decision Transfer Matrix

The approved comparison cohort is pinned in
[`evaluation/dms14-matrix.json`](evaluation/dms14-matrix.json): Kev-0.6B,
Kev-0.8B, Von, PoorJev, LitJev, and Laya-MLX, using CPU where supported and
MLX/Metal for Laya-MLX. The primary corpus is Kev `transfer-v4` development
split at the exact revision and hashes in
[`evaluation/dms14-corpus-manifest.json`](evaluation/dms14-corpus-manifest.json).
The upstream split has 764 items. All 80 `tweet_offensive` items are excluded
by explicit user direction before normalization for every candidate; the
selected corpus contains 684 items in seven categories. The original upstream
split hash and excluded-ID digest are recorded separately. Normalized model
inputs and gold labels have separate recorded digests; the raw corpus is not
copied into this repository.

The approved comparison uses canonical and reversed option order, equally
weighted category-macro accuracy, and 10,000 paired bootstrap resamples
stratified by category with seed 14. Invalid, missing, and abstaining outputs
count as incorrect. The approved proposed thresholds were macro accuracy >=
0.75 and per-category accuracy >= 0.40. Raw probability metrics are reported
on the 684 common items; no calibration was fitted on this evaluation set.

The corpus manifest records scoped local, noncommercial research terms for the
included sources and the pinned Kev repository's Apache-2.0 terms for its
generated policy/rule rows. The 80 full-text TweetEval offensive items are
excluded because their intended use required unresolved X policy permission;
no excluded item enters candidate inputs or metrics. Emotion is permitted for
research only; QNLI's source is identified as SQuAD CC BY-SA 4.0, with
attribution/share-alike obligations. The complete evidence is in the corpus
manifest.

The user approved the complete matrix once; no per-model approvals were
requested. The approval receipt binds matrix SHA-256
`6dd0764bdcd122227ace407820fcb8d5a8cdf3aa73f19562b97e72e7046b24b9` and
corpus-manifest SHA-256
`de2a00505e956a053a7e893e473410b8686a5da0335fc11e980e862e63c6042e`. All
six rows completed in process offline using their pinned runtimes and cached,
digest-verified artifacts. Each produced 1,368 predictions (684 items in two
option orders) with zero invalid, missing, abstaining, or failed outputs.

### Results

| Rank | Candidate / device | Category-macro accuracy (95% bootstrap CI) | Overall accuracy | Lowest category | Option-order flips | Warm p50 / p95 | Peak RSS |
|---:|---|---:|---:|---|---:|---:|---:|
| 1 | Von / CPU | 0.693 (0.661–0.724) | 469/684 (0.686) | MMLU 0.379 | 0/684 (0.0%) | 110 / 177 ms | 3.35 GiB |
| 2 | Kev-0.8B / CPU | 0.655 (0.620–0.689) | 446/684 (0.652) | MMLU 0.491 | 82/684 (12.0%) | 3,972 / 4,462 ms | 4.99 GiB |
| 3 | Kev-0.6B / CPU | 0.600 (0.566–0.636) | 412/684 (0.602) | Legacy holdout 0.450 | 134/684 (19.6%) | 161 / 272 ms | 3.86 GiB |
| 4 | Laya-MLX / Metal | 0.594 (0.561–0.628) | 399/684 (0.583) | MMLU 0.250 | 66/684 (9.6%) | 27 / 45 ms | 0.93 GiB |
| 5 | PoorJev / CPU | 0.490 (0.453–0.527) | 327/684 (0.478) | MMLU 0.276 | 1/684 (0.1%) | 430 / 1,104 ms | 1.05 GiB |
| 6 | LitJev / CPU | 0.429 (0.392–0.464) | 284/684 (0.415) | Emotion 0.198 | 487/684 (71.2%) | 418 / 553 ms | 4.21 GiB |

Warm latency is measured per item in each option order; the table reports the
median and 95th percentile over the 1,368 calls. Peak RSS is process maximum.
Cold model-load time was 4,977 ms for Kev-0.6B, 4,308 ms for Kev-0.8B, 6,177
ms for Von, 2,773 ms for PoorJev, 4,528 ms for LitJev, and 758 ms for
Laya-MLX.

| Category | Kev-0.6B | Kev-0.8B | Von | PoorJev | LitJev | Laya-MLX |
|---|---:|---:|---:|---:|---:|---:|
| Composition holdout | 0.490 | 0.573 | 0.396 | 0.479 | 0.521 | 0.469 |
| Emotion | 0.474 | 0.569 | 0.836 | 0.457 | 0.198 | 0.595 |
| Legacy holdout | 0.450 | 0.713 | 0.750 | 0.450 | 0.388 | 0.450 |
| MMLU | 0.483 | 0.491 | 0.379 | 0.276 | 0.293 | 0.250 |
| PAWS | 0.513 | 0.575 | 0.888 | 0.675 | 0.625 | 0.800 |
| QNLI | 0.863 | 0.788 | 0.738 | 0.588 | 0.475 | 0.813 |
| SciQ | 0.931 | 0.879 | 0.862 | 0.509 | 0.500 | 0.784 |

None meets both approved thresholds. Von is the point-estimate leader, but
its macro accuracy is 0.057 below threshold and it misses the category floor
on composition holdout (0.396) and MMLU (0.379). Kev-0.8B meets the category
floor in every category but misses the macro threshold by 0.095. Von's paired
macro-accuracy difference versus Kev-0.8B is 0.037 (95% bootstrap interval
−0.004 to 0.078), so this benchmark does not establish a clear quality winner
between those two.

Raw probability metrics are available for all 684 common items. Macro
multiclass Brier / 10-bin top-label ECE were 0.426 / 0.111 for Von,
0.421 / 0.033 for Kev-0.8B, 0.540 / 0.169 for Kev-0.6B, 0.525 / 0.086 for
Laya-MLX, 0.621 / 0.085 for PoorJev, and 0.634 / 0.072 for LitJev. These are
descriptive raw-output metrics, not calibrated acceptance results.

**Recommendation:** Von CPU is the best measured general-use and Mac quality
candidate in this cohort, with Kev-0.8B second by point estimate. Laya-MLX is
the fastest Mac path (27 ms median) and uses the least memory, but its lower
macro accuracy and 0.250 MMLU result make it the latency-first option only.
Since no candidate meets both thresholds, this is a comparative ranking, not
a production recommendation or DAR profile admission. DMS-14 does not measure
context-preservation quality and does not reverse DMS-01 or DMS-08 decisions.

## DMS-12 Jev-Style 0.8B v3 result

The approved run used `chaoliangUNSW/Jev-Style-0.8B-Decision-v3-MLX` at
`1235ccd1c95d5228a07616cd7e323c9e0532c1dc`, its Qwen3.5-0.8B base at
`dc7cdfe2ee4154fa7e30f5b51ca41bfa40174e68`, the isolated Python 3.14.6 / MLX
0.32.2 runtime, and Metal. It completed all 240 frozen cases with zero failed
rows and no OOM. Decision accuracy was **0.84** (95% Wilson interval
0.783–0.884), below the frozen decision threshold. At the matched 50% token
budget, retention utility was **0.477**, a **+0.168** improvement over
recency; model token-weighted keep recall was 0.485. Retention F1 was 0.548
and keep recall was 0.500. The decision and retention quality gates both
failed; calibration remains unverified for DMS despite the checkpoint's
shipped global temperature. Peak RSS was 1.16 GB, cold load 2.96 s, and warm
latency p50/p95 was 43/189 ms. The candidate is rejected under current DMS-01
criteria, with no production admission.

The aggregate-only receipt is
[`evaluation/jevstyle-dms12-receipt.json`](evaluation/jevstyle-dms12-receipt.json);
redacted predictions, tokenizer counts, and measurements are stored alongside
it. The run-specific preflight is
[`evaluation/preflight-jevstyle-dms12-2026-09-28.json`](evaluation/preflight-jevstyle-dms12-2026-09-28.json).
The runner downloads the checkpoint's `NOTICE` because its own manifest
integrity check requires it; that pinned file was added to the artifact digest
checks.

## DMS-13 original public-API run attempt

The user approved the exact pinned LongMemEval-S, Von compactor, Qwen reader,
GPT-4o scorer, runtime, thresholds, and 4,500 external requests. The approval
receipt is
[`evaluation/dms13-run-approval-2026-09-28.json`](evaluation/dms13-run-approval-2026-09-28.json),
and its host/runtime preflight passed. The runner stopped before cache download
or model inference because `OPENAI_API_KEY` was not available. No benchmark
content was sent to `api.openai.com`. That approval did not authorize the
revised ChatGPT endpoint and `gpt-6-luna` scorer. This historical attempt is
superseded by the local MLX Llama scorer documented above. DMS-13 remains
incomplete pending approval and execution of the revised local-only run.

The complete receipt, evaluation, matrix receipt, per-candidate redacted
predictions, and measurements are in
[`evaluation/dms14-run-2026-09-27/`](evaluation/dms14-run-2026-09-27/).
`run-receipt.json` binds every output digest to the approved matrix, corpus,
and run. Full scores and option-order comparisons are in `evaluation.json`.
