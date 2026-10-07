# Decision Model Support

## Canonical evaluation matrix

The DMS corpus uses one merged DMS-01/DMS-12 matrix. The canonical manifest is
[`evaluation/dms01-dms12-merged-matrix.json`](evaluation/dms01-dms12-merged-matrix.json).
It names all twelve historical DMS-01 rows, marks the Jev-Style MLX row as the
completed DMS-12 result, and is the only place to append new candidate rows.
The dated full-matrix JSON and DMS-12 receipt remain immutable source snapshots.

## Metadata

- Feature slug: `decision-model-support`
- Mode: guided
- Artifact type: feature specification
- Status: partial implementation; DMS-01, DMS-02, DMS-03, DMS-05, and DMS-07
  work is present. DMS-01, DMS-06, DMS-08, DMS-12, and DMS-14 results and
  quality gates remain recorded, but by user direction they do not gate
  optional client workflow support for Von, Julia 1, Laya-MLX, or Qwen-based
  decision profiles. Revisit quality criteria when context compression and
  management work resumes. DMS-04 and DMS-10's earlier quality-gated adapter
  deferrals are superseded by the client-support work in DMS-16. No current context-management
  profile is admitted; revisit its criteria when that work resumes. NanoJev
  remains deferred for host and licensing constraints. DMS-13 is shelved:
  published LongMemEval results are sufficient as
  external context for current purposes. No internal pilot or full-corpus run
  is planned, and published results do not establish DAR-specific performance.
  DMS-14 completed its approved published
  general-transfer matrix; no candidate met both thresholds, and the results
  remain comparative evidence only. DMS-15 is an
  audit-first task for reusable adapter helpers; no helper is presumed. DMS-18
  extends workflow decision nodes beyond choice-only routing to general scores
  and explicit yes/no (`noul`) handling. DMS-19 defines the caller-owned
  llama.cpp adapter surface across chat, structured output, tools, embeddings,
  multimodal input, and decision inference; DAR does not own a llama.cpp
  server or its lifecycle.
- Owner: workflow runtime and local model execution boundaries
- Related:
  - `specs/dynamic-agent-runner/spec.md`
  - `specs/local-model-runner-interface/spec.md`
  - `specs/workflow-model-materials/spec.md`
  - `specs/workflow-capability-requirements/spec.md`
  - `specs/context-management-prepare-stage/spec.md`
  - `specs/model-backed-context-summaries/spec.md`
  - `specs/provider-backed-context-compaction/spec.md`
- Plan: `plan.md`
- Tasks: `tasks.md`

## Objective

Support local decision models as an explicit, opt-in client capability that
workflows can use through a decision node. Separately, DAR may use decision
models to score context messages for compaction only after that work is
reopened with separately defined criteria and an explicit profile admission.
Keep model inference behind a package-owned
typed contract so external clients can adapt server-backed runtimes such as
Laya, and DAR can add separately installed in-process adapters for Von,
Julia 1, Laya-MLX, and reviewed Qwen-based profiles.
Workflow nodes must be able to consume the full decision contract, including
choice, ordered scores, and bounded yes/no (`noul`) outcomes, without exposing
model-specific protocols.

## Scope

1. A typed decision request and result contract for a finite set of named
   options, bounded input context, and model-produced option scores.
2. A `decision_step` workflow node that invokes an admitted decision-model
   capability and routes execution using its validated result.
3. A client-supplied adapter seam for nonstandard decision models and runtimes,
   including server-backed Laya integrations. The external client owns any
   server, its lifecycle, and that integration's model loading; DAR has no
   server requirement.
4. Optional DAR support for exact Qwen-based decision-model profiles through
   reviewed local model material and execution bindings. Kev-0.6B remains the
   provisional small local design/manual-test target. DMS-01 quality results
   do not gate client-authored decision workflows; revisit context-management
   criteria when that work resumes.
5. Optional first-party support for one direct, in-process Laya-MLX decision
   profile after exact artifact, license, runtime, material, and contract
   compatibility review. Its DMS-01 quality result informs context-management
   suitability only. This profile does not launch a server or add HTTP
   transport.
6. An internal compaction-scoring use of the same contract. The model may rank
   eligible older messages for retention; deterministic context policy retains
   pinned instructions, recent turns, active tool-call/result pairs, and other
   required state, and applies the actual deletion/truncation.
7. Fake-backed tests and model evaluation tasks. Unit tests must not download or
   invoke real model weights.
8. An end-to-end context-preservation evaluation of DAR's message-selection
   compaction against the public LongMemEval-S benchmark (DMS-13, shelved).
   Published LongMemEval results provide external context only; they do not
   establish DAR-specific performance or replace the frozen synthetic DMS-01
   candidate criteria.
9. A published general-decision-transfer comparison and Mac runtime profile
   for already evaluated local candidates. DMS-14 provides comparative
   selection evidence only and cannot change DMS-01 quality decisions, DMS-13
   context-preservation findings, or production-admission gates.
10. Runtime-neutral adapter helpers only where completed candidate reviews
    demonstrate repeated contract translation across at least two model
    backends. Helpers preserve the existing contract and do not add model
    loading, tokenization, or score interpretation to DAR's generic layer.
11. Optional first-party support for the exact reviewed Von 1.2.0 local
    profile through a backend-specific adapter and dependency group. Its
    quality results do not gate client workflow support; context-management
    use remains subject to separately reviewed criteria.
12. Optional first-party support for an exact Julia 1 local profile after its
    independent DMS-16 technical admission, through a backend-specific adapter
    and isolated optional extra. Its quality results do not gate client
    workflow support; context-management use remains subject to separately
    reviewed criteria.
13. An opt-in Jev-Style 0.8B v3 selector that resolves to one exact
    MLX/Metal, PyTorch, or GGUF backend using host capabilities and locally
    admitted runtime/material availability. Selection finishes before loading
    and produces an exact profile binding; it does not download models or
    switch backends after a load or inference failure.
14. General workflow use of `scores` results and constrained `noul` results.
    Score-based routing is deterministic and declared by the workflow; a model
    never chooses an edge policy or threshold. A `noul` result is a bounded
    yes/no probability with explicit complement semantics and may route only
    through declared yes/no edges.
15. A caller-owned llama.cpp support surface that lets clients bind the
    existing DAR model and decision contracts to direct in-process or
    caller-managed llama.cpp runtimes. The surface may cover text generation,
    structured output, tool calls, embeddings, multimodal input, and native
    decision-model inference; each capability remains opt-in and exact.

## Non-goals

- Replacing `llm_step`, model-backed summaries, provider-backed compaction, or
  existing deterministic compaction.
- Letting a model alone decide to delete messages, alter instruction hierarchy,
  discard unresolved work, or break tool-call/result pairs.
- Claiming that schema-valid output, a high score, or a confidence value means a
  decision is correct or calibrated.
- DAR-owned support for arbitrary model families, checkpoints, or runtimes.
  Each supported Von, Julia 1, Laya-MLX, Qwen-based, or Jev-Style profile is
  exact and reviewed for technical compatibility, material provenance,
  licensing, and host-boundary safety. Jev-Style automatic selection is
  limited to the three enumerated v3 backend profiles.
- DAR-owned server-backed Laya support or server lifecycle. External clients
  own those integrations. The narrowly scoped in-process Laya-MLX profile in
  scope does not generalize to other Laya runtimes, loaders, or checkpoints.
- Workflow-authored Python, native runtime code, model downloads, arbitrary
  filesystem access, or remote-code loading.
- General-purpose classifier training or a DAR-owned training pipeline.

## Decision Contract

The package-owned contract accepts one bounded decision request containing:

- a stable decision ID and a bounded context payload;
- one or more questions, each with a stable question ID and a finite ordered
  set of stable option IDs;
- an optional caller-declared task/profile ID, such as `context_retention_v1`;
- host-supplied execution limits and cancellation/deadline context.

The context payload is a finite JSON-compatible value resolved from workflow
state through existing safe references. Each registered profile declares
maximum input bytes, input tokens, question count, options per question, result
bytes, and supported output modes. DAR enforces byte and item-count limits;
the adapter enforces the profile's tokenizer-specific token limit. The host may
set stricter limits. Profile `permitted_uses` are host-controlled admission
data, not caller-declared request data. DMS-16 client profiles permit only
`workflow_decision`; resolving one for `context_retention` fails before adapter
dispatch. A caller-declared task/profile ID cannot grant a use that the host
profile does not permit.

The request declares an output mode supported by the selected profile:
`choice` or `scores`. A choice result contains one declared option ID. A score
result contains one finite score per declared option and a score semantic of
`ranking_score`, `probability`, or `calibrated_probability`. Probability scores
are finite values in `[0, 1]` that sum to one within an absolute tolerance of
`1e-6`; calibrated probabilities also identify the calibration evidence they
rely on. Ranking scores are finite and are not probabilities. Adapters must not
relabel raw logits or uncalibrated scores as probabilities.

The result identifies the exact adapter/model binding and returns exactly one
result for every requested question in request order. DAR validates identity,
cardinality, option membership, score semantics, and the profile's declared
input and output limits before using the result. A missing or duplicate result,
unknown option, non-finite score, unsupported output mode, or out-of-limit
request fails closed.

An adapter may explicitly mark a question `abstained`; that result contains no
choice or scores. A missing result is malformed, not an abstention. A workflow
node abstention raises a package-owned workflow error. A compaction abstention
uses its configured deterministic fallback or fails closed.

The public protocol does not require a particular model API, tensor shape,
transport, or serving framework. Adapters own translation between this contract
and model-specific input/output. Each registered profile declares supported
output modes, input limits, and model identity. Client-supplied adapters are
provided by the caller through a typed runtime binding, selected by exact
profile identity, and cannot be supplied as executable workflow-package
content. The adapter receives only the bounded decision request and host
execution limits. The client owns its adapter runtime and model loading; DAR
does not pass client adapters local paths or DAR-managed model materials.
DAR-owned Qwen profiles resolve locked materials through the host runner.

## Workflow Node

The existing `decision_step` is extended with the `decision_model` subtype
rather than adding a new primitive node kind. Each node declares exactly one decision
question, its finite options and option-to-edge mapping, references bounded
context from workflow state through the existing safe state-reference rules,
and names a required decision-model profile supporting the node's declared
output mode. A choice node routes by its selected option. A scores node must
declare a deterministic score-routing policy. `argmax` accepts finite ranking,
probability, or calibrated-probability scores and resolves ties by the first
declared option. `threshold` targets one declared option, accepts only
probability or calibrated-probability semantics, routes when the value is
greater than or equal to the declared threshold, and otherwise uses an
explicit abstain edge or fails closed. A noul node must declare yes/no edges
and a threshold over the normalized true probability. A caller adapter that
starts with a native boolean must translate it to the exact ordered yes/no
score result before DAR validation; DAR does not add a boolean result shape.
A workflow can express multiple decisions as multiple nodes. The contract may
batch questions for internal use such as compaction scoring. A profile declares
the maximum input and output sizes; the host enforces its own stricter limits.
The node does not declare adapter code, local paths, runtime imports, or an
implicit provider fallback.

Before inference, DAR validates the node and resolves the exact admitted model
capability. At execution, DAR validates the adapter result and follows only the
edge mapped from the returned option. Missing capability, failed inference,
invalid output, or an unmapped option raises a package-owned workflow error
through existing workflow failure handling; it never silently routes to a
default edge.

## Local Model Profiles and Client Adapters

DAR will provide reviewed optional local execution profiles for Von 1.2.0,
the Julia 1 candidate after technical admission, Laya-MLX, selected Qwen/Kev
decision models, and Jev-Style 0.8B v3 using immutable model-material
declarations and existing host admission, resource-budget, lifecycle, and
tracing boundaries.
Profiles are limited to exact artifacts evaluated or otherwise technically
reviewed in `tasks.md`; a model-family name alone is never sufficient for
admission. Kev-0.6B remains the provisional smallest
non-prototype design target. DMS-01 and related quality results inform
context-management use only and do not gate client-authored decision workflow
support. Adapter support still requires reviewed source/model/runtime identity,
license and material closure, bounded contract translation, and host-boundary
tests. Unit tests use fake adapters and never load real weights. Any manual
inference on real weights requires its own exact preflight and approval.

Jev-Style automatic selection is an explicit opt-in profile, not a generic
default. The host selector considers only compatible backends whose exact
runtime and local materials have already passed admission and fit the
host-provided resource budget. Its preference is
MLX/Metal on Apple Silicon when the MLX runtime and Metal device are available;
otherwise GGUF F16 on CPU, then PyTorch BF16 on CPU if GGUF is unavailable.
DMS-01 measured faster warm inference for GGUF than PyTorch on the tested Mac.
The frozen PyTorch profile is CPU-only; CUDA selection is outside this scope
until an exact CUDA profile is separately reviewed and admitted. Selection
among eligible profiles may continue past a backend that is unavailable
before loading, but once one exact profile is selected, load or inference
failure is returned without trying another backend. The selector never scans
arbitrary model folders or downloads materials. Every binding records the
selected backend and exact checkpoint/runtime identity.

The admitted Julia 1 profile was also evaluated on the frozen DMS-01 fixtures
under the existing criteria. It failed the decision and retention quality
gates; this comparative result does not change its separate client-workflow
admission.

DAR's local model execution has no server requirement. Server-backed Laya
integrations remain external-client-owned, including their server, lifecycle,
Python runtime, custom heads, loader, and model loading. The separately scoped
Laya-MLX profile is direct in-process local inference and does not use that
server integration. DAR defines and validates the shared contract but does not
embed or launch a Laya server. DAR passes client adapters only the bounded
request and host execution context; it does not pass workflow tools,
credentials, sealed artifact paths, or authority to download DAR-managed
assets. Model-backed context compaction remains separately quality-gated.

## Compaction Scoring

The initial internal task is to score eligible older messages for `keep` or
`drop`. Scoring may be batched, but batches must respect the selected profile's
input limit and preserve stable message identifiers. Truncation remains
deterministic context-management behavior and is never a model action. DAR
retains safety-pinned and recent messages independently of model scores. If the
scorer is unavailable, times out, abstains, or returns invalid output,
compaction follows the configured deterministic fallback or fails closed; it
must never interpret missing output as permission to drop content.

Each candidate question includes the active task context and that candidate's
stable message ID and content. The compaction policy must explicitly configure
how `keep` scores affect retention (a threshold or a bounded ranking rule); DAR
does not infer a deletion threshold from model output. Without that policy, the
scores are diagnostic only and do not delete messages.

DMS-13 was designed to measure end-to-end compression quality separately from
per-message retention metrics. Its proposed method replays LongMemEval-S
histories through the compaction path and compares full-history, recency, and
model-guided answers under matched token budgets. That internal evaluation is
now shelved. Published [LongMemEval results](https://arxiv.org/abs/2410.10813)
are external context only and cannot establish DAR-specific compression
quality. Do not treat per-message retention scores or synthetic-fixture results
as proof that compressed histories preserve downstream answer quality.

Scoring and application are separate: traces may record bounded counts,
decision IDs, score semantics, adapter identity, and fallback status, but must
not expose message contents or raw model payloads by default. Any learned
threshold or score interpretation must be supported by evaluation on labeled
transcripts and recorded separately from workflow decision correctness.

## Functional Requirements

### FR-1: Validate the typed decision contract

DAR rejects requests with duplicate IDs, empty or duplicate options, invalid
limits, or an unsupported profile before adapter dispatch. It rejects results
that omit or duplicate questions/options, select an undeclared option, contain
non-finite values, or misstate score semantics.

### FR-2: Execute a decision-model workflow node

An admitted decision-model `decision_step` sends its bounded request through
the exact resolved adapter, validates the result, and follows the matching
declared edge. Failure behavior is explicit, deterministic, and observable.

### FR-3: Permit caller-supplied adapters

A caller-supplied adapter can implement the public contract for a nonstandard
runtime such as Laya. The run-time binding identifies the supported profile
exactly; workflow packages cannot install or replace adapters.

### FR-13: Execute score and noul workflow decisions

An admitted `decision_model` node may request `choice`, `scores`, or constrained
`noul` output. Scores remain ordered by the declared option IDs and retain their
explicit `ranking_score`, `probability`, or `calibrated_probability` semantics.
The workflow declares how a score result becomes a route; DAR evaluates that
policy deterministically after validating the result. Threshold routing is
limited to probability semantics; ranking scores are not bounded to `[0, 1]`.
An explicit abstention is routable only through a declared abstain edge;
otherwise it fails closed. Calibrated probabilities require pinned profile
evidence that establishes calibration; an unadmitted calibration claim is
unsupported; the result's calibration evidence must equal the exact
host-pinned evidence ID bound by profile admission, and a profile without that
binding cannot advertise calibrated semantics. A `noul` result is valid only
for exactly two declared options
with IDs `yes` and `no`, and is normalized by the caller adapter to a complete
ordered probability pair before DAR validation. The adapter derives the
complement from the native true probability or boolean; DAR verifies the pair
sums to one and preserves the declared option order as the mapping authority.
For a `noul` threshold policy, DAR routes `yes` when `p_yes >= threshold` and
`no` otherwise. An explicit abstained result uses a declared abstain edge or
fails closed. No result can silently
become a choice or a deletion authorization. Missing, malformed, ambiguous,
or below-threshold results fail closed.

### FR-14: Provide a caller-owned llama.cpp adapter surface

DMS-19 owns a capability matrix for caller-owned llama.cpp bindings and may
define transport- and runtime-neutral helpers where an identified client need
exists. The matrix records the existing DAR contract, caller-owned work, exact
upstream API/profile, modalities, bounds, identity, observable request
lifecycle state limited to deadline and cancellation, errors, and unsupported
cases. Existing
DAR-owned direct llama.cpp chat/embedding loaders remain separate from this
caller-owned surface. New decision or multimodal bindings keep model loading,
native bindings, optional server processes, endpoint transport, lifecycle,
credentials, and artifact paths with the caller. DAR owns request
construction, typed-result validation, limits, identity binding, cancellation,
redaction, and contract validation. Helpers must not require a llama.cpp
server, expose a SystemOne endpoint, or add llama.cpp dependencies to the core
install. Unsupported upstream surfaces fail explicitly rather than falling
back to text generation or a different model.

### FR-4: Support selected Qwen decision profiles

DAR may expose exact, pinned Qwen-based decision profiles to client-authored
workflows when their materials, license, output mapping, and runner/runtime
compatibility are reviewed and admitted. DMS-01's context-management quality
thresholds do not gate this client workflow support. No network fetch, remote
code, or fallback to a different model occurs during execution.

### FR-5: Use decisions for safe compaction scoring

The shared contract can score eligible transcript messages for retention, while
DAR's deterministic policy protects required context and applies bounded
compaction. Invalid or missing scores never authorize deletion.

### FR-6: Bound, redact, and account for execution

Decision inference observes the host's context, output, deadline, cancellation,
and resource limits. Traces and errors are package-owned and redacted.

### FR-7: Support one reviewed in-process Laya-MLX profile

DAR may support the single Laya-MLX source/checkpoint/runtime combination
identified by DMS-08 and technically admitted by DMS-16 for client-authored
decision workflows after its pinned MLX runtime and material closure, license,
output mapping, and host-boundary behavior are reviewed. DMS-01 quality
thresholds apply to context-management suitability, not client workflow
support. The adapter runs
directly in process: it does not start a server, use HTTP, execute remote code,
or accept workflow-supplied model paths or loader code. It translates only
outcomes that the existing decision contract can represent; unsupported
outputs fail closed.
The Laya `noul` outcome is supported only for a `scores` request whose selected
profile supports scores and whose question declares exactly two options with
IDs `yes` and `no`. Validate its finite yes probability in `[0, 1]`, map it
and its complement to the matching IDs, and emit the scores in request order.
Use `probability` semantics unless pinned calibration evidence satisfies the
existing contract; only then use `calibrated_probability`. Reject malformed
values and all other `noul` request shapes. Do not add a public `noul` mode.

### FR-8: Measure end-to-end context preservation

DMS-13's end-to-end compaction evaluation is shelved. Published LongMemEval-S
results may inform external context only; they are not evidence about DAR's
message-selection compaction. No internal pilot or full-corpus analysis will
run under the current decision. Reopening this requirement needs a new explicit
decision and run approval. DMS-13 cannot retroactively satisfy or modify DMS-01
candidate gates.

### FR-9: Compare published general-decision transfer

DMS-14 compares the fixed cohort of already evaluated local candidates on one
reviewed, pinned general-decision-transfer corpus with a pre-registered task
mapping, scoring protocol, and acceptance/ranking rules. It reports comparable
task-level and macro accuracy, invalid/abstaining outputs, option-order
sensitivity, uncertainty, and probability calibration only where outputs are
semantically comparable. Its Mac profile uses the same corpus and protocol and
records exact runtime, precision, latency, memory, and failures; runtime or
quantization variants with different numerical behavior receive separate
quality results. One approval covers the complete candidate/runtime matrix
before any model download or inference. This is comparative evidence only: it
cannot reverse prior DMS-01/DMS-08 reject/defer decisions, establish DMS-13
compression quality, or establish context-management suitability. Client-
backend support follows the separate technical and host-safety gates.

### FR-10: Support an optional local Von profile

DAR may expose the exact reviewed Von 1.2.0 profile through an optional
dependency group and backend-specific adapter for client-authored decision
workflows. Support requires pinned source/model/runtime identity, license and
material review, bounded translation to the existing choice/scores contract,
and host-boundary validation. DMS-06/DMS-14 quality results do not gate client
workflow support; context-management use requires a separate quality decision.

### FR-11: Support an optional local Julia 1 profile

DAR may expose an exact SupersonicLabs Julia 1 candidate profile after DMS-16
technical admission, through an optional extra and backend-specific
adapter for client-authored decision workflows. Support requires pinned
source/model/runtime identity, license and material review, dependency
isolation, bounded translation of choice, ordered-score, and
yes/no-probability outputs to the existing choice/scores contract, and
host-boundary validation. Runtime code must be locally controlled and pinned;
dynamic remote-code loading is not permitted. No Julia runtime or
model-loading behavior is added to the generic contract. Quality results do
not gate client workflow support; context-management use requires a separate
quality decision.

### FR-12: Select an admitted Jev-Style v3 backend for the local machine

DAR may offer an explicit Jev-Style v3 automatic profile that resolves once,
before model loading, from host-reported machine facts and locally admitted
candidates, to one of three exact local profiles: Jev-Style v3 MLX
8-bit on Apple Silicon/Metal, Jev-Style v3 PyTorch BF16 on CPU, and
Jev-Style v3 GGUF F16 on CPU. “Best” means the first profile in this
deterministic preference order that is compatible with the host and admitted
for its runtime, exact local materials, and resource budget:

1. MLX 8-bit with Metal on Apple Silicon.
2. GGUF F16 on CPU.
3. PyTorch BF16 on CPU.

This order reflects DMS-01's results: MLX/Metal is preferred for Apple
hardware, and GGUF had faster warm inference than PyTorch on the tested Mac.
The selector does not benchmark models at startup. The frozen PyTorch profile
does not support CUDA selection; that requires a separately reviewed exact
profile. A profile may be skipped only when its platform, runtime, device, or
pre-admitted local materials are unavailable before selection, or host
admission says its resource budget cannot run it. If no profile is eligible,
selection fails before loading. It binds the chosen exact model, runtime,
material manifest, and adapter identity before loading. It must not download,
scan arbitrary paths, or switch profiles after loading or inference starts.
Each backend's
translation to existing `choice` and ordered `scores` requests is tested
independently. A native `noul` result may map only to a `scores` request with
exactly the `yes` and `no` option IDs; it does not add a public `noul` mode.
Calibrated score semantics require pinned calibration evidence. All three
profiles are `workflow_decision` only; DMS-01 quality results do not gate that
client use, and none is admitted for context retention.

The host supplies normalized machine facts, exact pre-admitted candidates, and
their local loaders. Each candidate binds a sealed `ModelExecutionBinding`;
the selector invokes only the chosen candidate's loader. DAR does not install
or import these optional runtimes as part of its core package. Host loaders
remain responsible for using the bound material/runtime and enforcing the
existing resource, deadline, cancellation, and lifecycle controls.

## Acceptance Criteria

- Contract tests cover valid choice and score requests and malformed
  requests/results, including duplicate/missing outputs, unknown options,
  NaN/infinity, byte/token/item limits, unsupported output modes,
  score-semantics mismatch, absent calibration evidence, and explicit
  abstention.
- A fake adapter proves workflow-node routing, exact capability selection,
  explicit failure behavior, and no implicit fallback.
- A client adapter can be supplied by the caller and invoked without adding its
  runtime dependency to DAR core or workflow package contents.
- Von, Julia 1, Laya-MLX, and Qwen/Kev support is limited to exact reviewed
  material/profile combinations and is covered by deterministic fake tests
  plus runtime/material compatibility checks. These profiles declare
  `workflow_decision` use and cannot be bound for `context_retention`; enforce
  this in host admission with a fake rejection test before inference.
  DMS-01's context-management recommendation is separate from client workflow
  support; runtime binding, limits, lifecycle, and material admission remain
  required.
- Jev-Style automatic selection is opt-in and chooses only among its exact
  admitted MLX/Metal, PyTorch, and GGUF profiles. Fake tests cover platform and
  runtime eligibility, selection priority, unavailable profiles, exact
  identity binding, no arbitrary model scanning/download, and no post-selection
  fallback. Real compatibility smokes remain separate from unit tests.
- The Laya-MLX profile is separately limited to its exact reviewed source,
  checkpoint, tokenizer, runtime, and material combination. Its direct local
  adapter passes fake binding tests and technical/runtime compatibility
  checks before client use; it never launches a server or uses HTTP. Its
  context-management quality result does not gate client workflow support.
- Compaction tests prove pinned instructions, recent context, unresolved state,
  and tool-call/result pairs survive low retention scores; invalid, missing,
  timed-out, or abstaining scores cannot cause deletion.
- Evaluation records include task-specific quality, calibration/abstention
  where available, latency, peak memory, supported input size, runtime/license
  constraints, and a clear accept/reject/defer decision for each context-
  management candidate. These quality decisions do not gate optional client
  backend support; exact technical, material, contract, and host-safety checks
  remain mandatory for every supported profile.
- DMS-13 is shelved. Published LongMemEval-S results may be cited as external
  context only and do not establish DAR-specific end-to-end answer quality.
  DMS-01 thresholds and results remain unchanged.
- DMS-14 records the exact corpus/split and hashes, fixed candidate cohort,
  task mapping and scoring protocol before inference; it reports the approved
  complete local/Mac runtime matrix and a redacted aggregate receipt. One
  matrix-level approval covers all listed candidate/runtime combinations.
  Results remain separate from DMS-01 retention, DMS-13 compression, and
  client-backend compatibility decisions.
- DMS-15 adds runtime-neutral adapter helpers only when the audited candidate
  paths demonstrate repeated contract translation across at least two
  backends. Helpers preserve declared option order and explicit score
  semantics, reuse existing contract validation, and leave model loading,
  tokenization, calibration, and model-specific score interpretation in the
  adapters. If no repeated translation is demonstrated, record the audit and
  add no helper.
- DMS-18 covers workflow score/noul routing with fake adapters for argmax,
  threshold, complement, malformed, abstention, and fail-closed behavior.
- DMS-19 covers caller-owned llama.cpp capability bindings with fake backends
  for chat, structured output, tools, embeddings, multimodal input, and
  decision inference. It does not add server lifecycle or a SystemOne endpoint.
- No unit test downloads or invokes real weights, and no default trace contains
  transcript content or raw model payloads.

## Implementation Readiness

The implementation procedure is the repository's spec-driven development
workflow. The concrete source and test targets, task dependencies, test-first
requirements, and delivery gates are in `plan.md` and `tasks.md`. Optional
client workflow support for Von, Julia 1, Laya-MLX, reviewed Qwen-based
profiles, and the opt-in Jev-Style selector is independent of context-management
quality gates. It still requires
exact profile and material binding, technical runtime compatibility,
output-contract validation, and host-safety checks. Each DMS-16 profile is
explicitly workflow-decision-only, and host admission must reject it for context retention
without invoking inference. Use for context compaction or management remains
disabled until the relevant quality criteria are revisited and passed.
Server-backed Laya integrations remain external-client-owned. DMS-15 tracks an
audit-first assessment of reusable adapter helpers; it does not presume that
new helper code is warranted.

The typed contract, workflow decision node, and fake-backed compaction scoring
are implemented. Adapter and fake-test slices now exist for Von, Julia 1,
Laya-MLX, Kev/Qwen, and Jev-Style v3; optional runtime installs passed for Von,
Julia 1, and Laya-MLX. Jev-Style's selector is implemented, but none of its
backends is first-party-admitted. No profile is admitted or exposed until
exact local material closure and approved adapter-facing compatibility smokes
are complete, and Kev's
root optional packaging is deferred over its Torch constraint conflict.
Existing context-management quality results do not gate client support and
remain separate from compaction admission. NanoJev remains deferred for host
and licensing constraints. See `tasks.md` and `validation.md` for current
validation. This feature is partial and is not complete.

## Validation Strategy

Use fake adapters for unit and integration tests. Run authorized local model
competency checks only against exact pinned artifacts and record them outside
the unit-test suite. For compaction, use labeled representative transcripts and
compare retention decisions against reviewed labels; report false-drop rates on
critical/pinned content, overall retention quality, calibration/abstention if
available, latency, and memory. Do not promote a model based only on vendor
benchmarks or schema validity.

Exact implementation checks are listed in `tasks.md` and may be refined after
candidate-profile discovery without changing the acceptance criteria.
