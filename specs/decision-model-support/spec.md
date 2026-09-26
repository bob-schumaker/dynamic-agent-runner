# Decision Model Support

## Metadata

- Feature slug: `decision-model-support`
- Mode: guided
- Artifact type: feature specification
- Status: implementation-ready under the evaluation and approval gates below;
  implementation has not started
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

Support local decision models as an explicit capability that workflows can use
through a decision node and DAR can use internally to score context messages
for compaction. Keep model inference behind a package-owned typed contract so
clients can adapt nonstandard runtimes such as Laya, while DAR provides a
reviewed path for Qwen-based decision models.

## Scope

1. A typed decision request and result contract for a finite set of named
   options, bounded input context, and model-produced option scores.
2. A `decision_step` workflow node that invokes an admitted decision-model
   capability and routes execution using its validated result.
3. A client-supplied adapter seam for nonstandard decision models and runtimes,
   including Laya implementations that expose their own inference interface.
4. DAR support for Qwen-based decision models through reviewed local model
   material and execution profiles, initially targeting the Qwen variants
   listed in DMS-01.
5. An internal compaction-scoring use of the same contract. The model may rank
   eligible older messages for retention; deterministic context policy retains
   pinned instructions, recent turns, active tool-call/result pairs, and other
   required state, and applies the actual deletion/truncation.
6. Fake-backed tests and model evaluation tasks. Unit tests must not download or
   invoke real model weights.

## Non-goals

- Replacing `llm_step`, model-backed summaries, provider-backed compaction, or
  existing deterministic compaction.
- Letting a model alone decide to delete messages, alter instruction hierarchy,
  discard unresolved work, or break tool-call/result pairs.
- Claiming that schema-valid output, a high score, or a confidence value means a
  decision is correct or calibrated.
- DAR-owned support for every evaluated model/runtime listed in `tasks.md`. Other
  candidates are evaluation tasks; each needs an explicit compatibility and
  support decision.
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
set stricter limits.

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
and names a required decision-model profile supporting `choice` output. A
workflow can express multiple decisions as multiple nodes. The contract may
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

## Qwen Support and Client Adapters

DAR will provide a reviewed local execution path for Qwen-based decision models
using immutable workflow model-material declarations and existing host
admission, resource-budget, lifecycle, and tracing boundaries. Candidate
profiles are limited to the exact Qwen variants evaluated in `tasks.md`. The
selected profile, supported quantizations/runtimes, and model revisions are
recorded from that evaluation; model-family name alone is never sufficient for
admission.

Laya and other nonstandard decision runtimes use the client-supplied adapter
interface. DAR defines and validates the contract, but does not embed Laya's
Rust server, Python runtime, custom heads, or model-specific loader. DAR passes
client adapters only the bounded request and host execution context; it does
not pass workflow tools, credentials, sealed artifact paths, or authority to
download DAR-managed assets.

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

### FR-4: Support selected Qwen decision profiles

DAR supports only evaluated, pinned Qwen decision profiles with verified
materials and declared runner/runtime compatibility. No network fetch, remote
code, or fallback to a different model occurs during execution.

### FR-5: Use decisions for safe compaction scoring

The shared contract can score eligible transcript messages for retention, while
DAR's deterministic policy protects required context and applies bounded
compaction. Invalid or missing scores never authorize deletion.

### FR-6: Bound, redact, and account for execution

Decision inference observes the host's context, output, deadline, cancellation,
and resource limits. Traces and errors are package-owned and redacted.

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
- Qwen support is limited to exact evaluated material/profile combinations and
  is covered by deterministic fake tests plus separately authorized local
  competency evidence.
- Compaction tests prove pinned instructions, recent context, unresolved state,
  and tool-call/result pairs survive low retention scores; invalid, missing,
  timed-out, or abstaining scores cannot cause deletion.
- Evaluation records include task-specific quality, calibration/abstention
  where available, latency, peak memory, supported input size, runtime/license
  constraints, and a clear accept/reject/defer decision for each candidate.
  Evaluation criteria are recorded before comparative runs; Qwen profile
  implementation stops for user direction if no candidate meets them.
- No unit test downloads or invokes real weights, and no default trace contains
  transcript content or raw model payloads.

## Implementation Readiness

The implementation procedure is the repository's spec-driven development
workflow. The concrete source and test targets, task dependencies, test-first
requirements, and delivery gates are in `plan.md` and `tasks.md`. The next
action is DMS-01, candidate evaluation; no model profile is assumed before its
evidence is recorded.

This plan is ready to execute under its stated gates. Local model competency
runs remain an explicit manual gate, and the Qwen implementation task stops for
user direction if the pre-recorded evaluation criteria are not met.

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
