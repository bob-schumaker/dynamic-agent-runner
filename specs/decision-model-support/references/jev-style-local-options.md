# Jev-Style Local Decision Options

**Role:** Research reference for later decision-model candidate review. This is
not a DAR support decision or model evaluation result.

**Reviewed:** 2026-09-26

## What “Jev-style” means

TypeSafe describes Jev as a hosted decision API that takes shared state and
typed questions and returns bounded answers instead of generated prose:

- `choice`: select from supplied options and return per-option probabilities.
- `score`: rate on an ordered scale and return a score and distribution.
- `noul`: return a calibrated yes/no probability.

TypeSafe says it has not published Jev's weights, parameter count, or low-level
internals. The architecture page is an observable API description, not a
reproduction of the model. See [TypeSafe's Jev architecture
overview](https://www.jevtypesafeai.com/jev/architecture).

## Local options

### Kev: trainable Qwen-based decision models

[Kev](https://github.com/jaredpalmer/kev) is an open-source family of
Jev-like decision models. Its current README lists 0.8B, 4B, 9B, and 27B
variants based on Qwen3.5 and Qwen3.8. The 0.8B model is listed for Apple
Silicon laptops; 4B and 9B for 32 GB Macs and larger GPUs; 27B for 80 GB
datacenter GPUs. The local API follows TypeSafe's System One request shape.

The repository describes LoRA fine-tuning on labeled examples, held-out
temperature calibration, and frozen benchmark suites. Its reports include
accuracy, Brier score, calibration error, option-order sensitivity, and
question-isolation checks. These are project-reported results; they are not
DAR evaluation results or a controlled comparison with Jev. Kev's code and
models are described as Apache-2.0, while the base-model and dataset licenses
must be checked separately for the exact artifacts. See the [Kev
README](https://github.com/jaredpalmer/kev#readme) and its linked
[model cards](https://github.com/jaredpalmer/kev/tree/main/docs/model-cards).

The current project exposes a local API server, while its package also supports
in-process model loading. A server-backed deployment is optional and does not
imply a DAR-owned server requirement.

### Train Your First Jev: small-model training course

[train-your-first-jev](https://github.com/cexll/train-your-first-jev) is a
bilingual interactive course for training a Qwen2.5-0.5B LoRA adapter plus a
scoring head. It documents disjoint train, validation, calibration, and test
splits; selecting an epoch by validation loss; a one-time held-out test; and
separate temperature fitting.

The repository reports an example training stage of about 45–50 minutes on an
M1 Pro. Its own caveat is material: the example's 47.66% held-out accuracy and
calibration results show a training signal on that public task, not production
reliability, general capability, or parity with Jev. See the project's
[training and evaluation notes](https://github.com/cexll/train-your-first-jev#interactive-open-model-training).

### JevStyle: packaged local checkpoints

[JevStyle](https://jevstyle.com/) currently lists Decision 0.8B v3, MacJev
322M, and Decision 2B versions, with PyTorch, MLX, and GGUF downloads linked
from its model page. The specific [Jev-Style 0.8B project
README](https://github.com/lawrence3699/jev-style#readme) describes a local
System One-compatible service and in-process Python use, with MLX on Apple
Silicon, PyTorch on CPU/CUDA, and an optional GGUF backend. It reports up to
25,600 input tokens and multilingual evaluations; treat those as project claims
until independently evaluated on DAR's task.

[MacJev-322M-4K-Laya](https://huggingface.co/chaoliangUNSW/MacJev-322M-4K-Laya)
is a separate small checkpoint based on Laya multilingual weights. Its card
describes a 4,096-token decision model with PyTorch and MLX formats for local
in-process inference; a GGUF format uses `llama-server`. It is a third-party
derived model/runtime, not DAR-owned Laya support. Its reported metrics are
author claims, not DAR results.

### AnyJev: decision readout and calibration for an existing model

[AnyJev](https://jevai.dev/anyjev/) is a Python toolkit, not a new base model or
an open release of TypeSafe's Jev. It reads typed decisions from a causal model
you choose and adds option-order and label-prior corrections. Its documented
levels are:

- Raw: answer-token logits, with no correction.
- L0: option rotations and label-prior correction; no task calibration.
- L1: temperature calibration, with the project guide suggesting 100–500
  labels.
- L2: a question-specific closed-form head using hidden states, with the guide
  suggesting 100–300 labels.

The label counts are guidance from the project, not a guarantee of calibration
or accuracy. AnyJev identifies itself as pre-alpha and says it does not
reproduce Jev's private weights, training data, or RLCD method. See the
[AnyJev guide](https://jevai.dev/anyjev/) and its linked
[source repository](https://github.com/nokia-applied-research/AnyJev).

### Lev: compact alternate backbone prototype

[Lev](https://github.com/franckverrot/lev) adapts the Kev-style typed-decision
interface to Liquid AI's LFM2.5-350M. The maintainer calls it a prototype. Its
published comparison reports 361M parameters, 25 ms for a three-question
request, and 0.546 out-of-domain accuracy versus Kev-0.6B's 0.598, measured on
an M2 Max with 96 GB. These are maintainer-reported results on that benchmark
and hardware; use Lev as a lightweight experiment, not as an established
replacement. The Lev repository is Apache-2.0; the LFM2.5-350M base has the
separate LFM Open License v1.0. See [Lev's README and results](https://github.com/franckverrot/lev#results).

## Practical investigation order

For a local system, the source review suggests:

1. Try AnyJev when a suitable local base model already exists and labeled
   examples are available for calibration or a small question-specific head.
2. Compare Kev-0.8B and JevStyle-0.8B when a dedicated compact model is wanted;
   include MacJev when a particularly small local checkpoint or longer inputs
   matter.
3. Consider Kev-4B/9B when transfer accuracy is more important than laptop
   resource use. Kev-27B is positioned for datacenter hardware.
4. Keep Lev as a prototype comparison and use the training course as an
   educational recipe, not as a production benchmark.

For any candidate, use disjoint source-level train/validation/calibration/test
sets, option-permutation and shuffled-context controls, and a low-confidence
fallback defined from held-out data. Probability output, project-reported
calibration, and a Jev-compatible API do not establish accuracy on DAR's task.

## Relationship to DMS

These options are reference material only. They do not add models to the
approved DMS-01 cohort, change its frozen fixtures or criteria, replace the
provisional Kev-0.6B design target, or authorize model downloads or inference.
Before candidate evaluation, reconcile the current source revisions and any
proposed cohort changes through the existing DMS-01 approval gate. DAR's first
implementation remains local-model focused; any server lifecycle belongs to an
external client or to the separately reviewed model package, not to an
implicit DAR server requirement.
