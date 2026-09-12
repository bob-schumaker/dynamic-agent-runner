# Model Generation Resource Budgets Specification

## Metadata

- Feature slug: `model-generation-resource-budgets`
- Status: ready for implementation
- Owner: dynamic-agent-runner workflow-host and local-model boundaries
- Plan: `plan.md`
- Tasks: `tasks.md`
- Related specifications:
  - `specs/sealed-artifact-workflow-runner/spec.md`
  - `specs/workflow-locked-inference-callback/spec.md`
  - `specs/workflow-input-converter-plugin/spec.md`
  - `specs/local-model-runner-interface/spec.md`
  - `specs/model-execution-plugin-interface/spec.md`

## Objective

Define one canonical, host-enforced budget contract for a single model
generation invocation. It prevents a workflow-declared generation or raw-text
continuation policy from growing output, prompt context, execution time, or
resident memory until the host is killed by resource pressure.

## Scope

The contract applies to every DAR model-generation runner, including built-in
and receiver-installed runners. A workflow declares requested limits; the host
selects stricter effective limits and rejects an invocation that cannot be
bounded before model execution.

The canonical `GenerationResourceBudget` contains positive integers except
`max_continuations`, which is a nonnegative integer:

| Field | Meaning |
| --- | --- |
| `max_new_tokens_per_fragment` | Maximum tokens requested from one backend generation call. |
| `max_continuations` | Maximum additional fragments after the initial fragment. Zero disables raw-text continuation. |
| `max_total_generated_tokens` | Aggregate generated tokens across all fragments. |
| `max_total_output_bytes` | UTF-8 byte ceiling for the assembled model completion before downstream processing. |
| `max_effective_context_tokens` | Maximum of packed input tokens plus the requested generated-token bound for every backend call, including prompt, media tokens, and retained continuation context. |
| `max_runtime_milliseconds` | Wall-clock deadline covering worker launch, packing, admission, model load, every generation fragment, and reap. |
| `max_memory_bytes` | Maximum invocation-scoped packing and model-execution memory envelope. |

The effective value is resolved field by field. A source absent for a field is
non-applicable; a source required below but absent or malformed fails closed.

| Source | Form | Applicable fields |
| --- | --- | --- |
| Workflow execution descriptor | Required exact seven-field `generation_budget` object | All fields |
| Selected material/profile | Optional `generation_budget_cap` strict partial object using only canonical field names | Any declared field |
| Runner capability | Required typed capability record | `max_effective_context_tokens`; memory-admission and cancellation/worker support, not a second untyped budget |
| Receiving host | Required exact seven-field ceiling | All fields |
| Enclosing sealed-artifact descriptor | Existing descriptor values | `max_runtime_milliseconds` and `max_memory_bytes` only |

For a numeric field, the effective value is the minimum of the workflow value,
host ceiling, and every applicable declared source in that row. The outer
descriptor does not cap model-completion bytes, tokens, or continuations:
artifact output and callback limits govern distinct artifact bytes. A workflow
may request less than a host ceiling but never more. Limits and effective
values are host-private operational policy; the sealed workflow's declared
value remains package material.
Workflow-visible results contain only redacted outcome classifications and safe
aggregate counters.

### Immutable declaration carrier

The workflow declaration is the strict canonical `generation_budget` object in
the selected model's `execution-descriptor.json` `abi_fields`. It has exactly
the seven fields listed above. The selected execution-descriptor ABI validator
owns its schema and accepts no aliases or extra fields. The existing execution
descriptor is a sealed model-material asset whose digest is pinned by the
material lock; the budget is therefore immutable for the workflow revision and
cannot be selected by prompt text, payload bytes, a request field, or a host
path.

Every built-in or receiver-installed runner exposes a reviewed
`GenerationRunnerCapability` record containing its runner contract identity,
supported effective-context bound, one of the three FR-3 memory-admission
methods, and exactly one lifecycle form: cancellation coverage for both `load`
and `generate`, or `generation-worker-v1` plus enforceable bootstrap and
generation-stage hard-limit methods. Every form also declares an enforceable
pre-packing containment method for its selected platform/device. A missing,
duplicate, incompatible, or unenforceable field makes the runner unavailable
before load with `generation_budget_unavailable`; no runner may substitute an
invocation-time policy. The host supplies its private ceilings. These inputs
and the sealed declared budget resolve one effective budget before model
loading.

The generic converter-capable model-adapter boundary owns sealed-input binding,
budget resolution, worker lifecycle, reservation admission, receipt/result
validation, aggregate accounting, redacted telemetry, and terminal response
construction. Its worker-child factory is bound to exact converter/material
identities and constructs converter, packed-input, processor, and runner state
locally. No DAR budget contract is named for a modality, pixel/image decoder,
model family, or concrete adapter class; those remain workflow conformance
implementations of this boundary.

Platform memory containment is available only when the selected runner/device
pair supplies a reviewed, enforceable containment implementation for the
declared bootstrap and generation-stage envelopes. DAR does not claim one
portable CPU, RSS, accelerator, or unified-memory limiter. An unsupported or
unenforceable pair fails before sealed-input ingress with
`generation_memory_budget_unavailable`.

For a receiver-installed local runner, `LocalModelRunnerCatalog` registers the
runner identifier and exactly one `GenerationRunnerCapability` together. The
catalog rejects a missing capability, duplicate runner identifier, duplicate
capability binding, or capability whose runner identity differs from the
registered runner before `create_adapter` runs. DAR-owned runners use the same
validation rule at their registration boundary.

A worker-capable registration additionally contains exactly one parent-only
worker-child factory bound to the same runner identity and capability contract.
The registration rejects a missing, duplicate, mismatched, or worker-protocol-
incompatible factory before launch. Cancellation-capable registrations have no
factory. The factory produces only the launch descriptor defined below.

A `MemoryReservationProvider` is receiver-installed and accepts only the
selected material-lock identity, runner identity, selected execution device,
packed-context token count, requested new-token bound, effective memory
ceiling, and deadline. It returns an opaque reservation that must be released
exactly once. The provider's estimation inputs, device counters, and
implementation details never enter the workflow package, trace, or model
prompt.

### Isolated generation-worker transport

An in-process runner that cannot cooperatively cancel is not made
deadline-bounded by a thread, future, or post-hoc timeout. It must use one
terminable isolated generation worker per bounded invocation. This is a
host/runner implementation boundary, not a workflow capability and not a
generic tensor-serialization API.

The worker reuses the existing personal-use precedent of exact,
owner-authorized digest-bound workflow assets. It does not reuse an existing
execution mechanism: input converters are currently imported in process and
sealed artifacts currently execute in a bounded thread. This worker is new
resource/lifecycle containment, not an OS security boundary for malicious
code. The dedicated process exists to make model lifetime terminable for
deadline and memory enforcement. The parent starts one monotonic deadline
before worker launch; it covers launch, packing, admission, model load, every
fragment, and reap. The parent resolves the effective budget and supplies only:

- canonical sealed invocation data and canonical messages;
- verified immutable converter and model-material identities plus a
  host-private launch configuration for their read-only assets;
- the resolved generation budget and selected execution device; and
- a host-private worker invocation identifier.

The child loads creator-supplied converter code through the same DAR-owned
sealed-asset declaration, digest verification, and restricted converter-context
pattern used by the current in-process converter loader. Moving that loader
into a child does not widen its authority, make the converter an IPC protocol
participant, or create a distinct worker trust regime. The child receives the
verified asset identity and host-private asset-access configuration; it never
receives a workflow-selected import path, arbitrary loader callback, host model
object, or device handle during packing.

The receiver-registered worker-child factory executes only in the parent under
that established sealed-asset trust path. It returns a typed immutable
`GenerationWorkerLaunchDescriptor`; DAR validates it, serializes its exact
fields, and sends it to a fixed DAR worker entry point. The descriptor contains
only the worker protocol version, runner capability contract, converter and
material/descriptor identities, selected device, resolved budget, sealed
invocation/fragment identities, and host-private read-only asset locators or
handles. The worker revalidates it and reconstitutes only registered typed
components. It never deserializes a callable, imports a workflow-selected
module, or accepts arbitrary model-loading code. The immutable descriptor has
an exact versioned mapping encoding and a fixed host-private maximum byte size.
Its required fields are protocol version; invocation digest and fragment index;
runner ID and capability-contract digest; converter ID and asset digest;
material-lock and execution-descriptor digests; selected device; canonical
budget; and opaque controller-issued read-only asset handles. The parent
validates it before framing; the fixed entry point validates it before any asset
resolution. Handles are not paths, cannot be supplied by workflow input, and
are never emitted in workflow-visible frames.

Before worker launch, the host applies a reviewed bootstrap packing envelope:
a process/runtime hard memory limit and deadline remain active while converter
and processor state are constructed and input is packed. The bootstrap envelope
is sufficient for the selected sealed-input byte declaration and converter
declared input/output limits, permits no
model loading or accelerator allocation, and cannot exceed the effective memory
ceiling. The generation-stage hard limit may tighten that envelope after
admission but cannot replace it. Thus packing exhaustion terminates and reaps
the worker before model load instead of relying on host memory pressure.

The host-owned `GenerationWorkerLauncher` creates the worker with a two-phase
runtime contract. In the `pack` phase it supplies only verified asset access,
sealed invocation bytes, and a packing interface; it supplies no host-owned
model-loader, model object, or selected-device handle. After parent
authorization, the `generate` phase may resolve the compatible runner and
selected device. The exact-identity personal-use contract requires converter
code not to bypass those phases; it is not a defense against malicious Python.
If a platform cannot enforce the declared bootstrap envelope for both host and
selected-device allocations, that runner/device combination is unavailable.
The same pre-packing containment rule applies to a cancellation-capable
in-process runner before it decodes or packs input.

The selected runner/device registration supplies a reviewed platform-controller
implementation with bounded `launch`, `wait_ready`, `terminate`, `kill`, and
`reap` operations. On expiry the parent stops admitting frames, attempts
terminate, escalates to kill after the controller's declared bounded grace
interval, and then requires reap confirmation. Launch, readiness, IPC, or
controller-operation failure is `generation_execution_failed`; a deadline path
that reaches termination is `generation_deadline_exceeded`. A controller that
cannot provide bounded reap confirmation is unavailable before launch. The
parent releases a reservation only after cleanup and reap confirmation.

The worker constructs converter state, processor state, packed tensors,
generation/KV-cache state, and model state locally. Host-controlled launch
details may identify verified local assets, as they do for today's converter
loader, but are not part of the workflow-visible worker ABI. The invocation
protocol must not receive or return packed tensors, Python converter/model
objects, token IDs, host paths, or opaque converter state.

The `generation-worker-v1` protocol is a versioned, parent-driven state
machine. Every message contains the host-private invocation identifier and
fragment index. Its only result scalars are packed-context token count,
generated-token count, aggregate generated-token count, fragment output-byte
count, aggregate output-byte count, and one finite outcome classification;
these scalars are not token IDs. It has exactly these transitions:

1. `pack` returns either `packed(receipt, packed_context_tokens)` or a terminal
   classification. The receipt commits to the canonical invocation digest,
   converter and material identities, selected device, fragment index, and
   packed-context token count.
2. The parent validates that receipt and count, checks context/deadline, and
   atomically reserves memory in the `(material-lock, runner, device)` namespace.
   It then sends `authorize(receipt, remaining_generated_tokens)`.
3. The worker may generate only from the retained packing associated with that
   receipt. Repacking, a receipt mismatch, an out-of-order or duplicate message,
   or generation before authorization is a protocol failure. Each fragment
   returns its candidate bytes privately with the safe scalar counts, or a
   terminal classification. Before framing candidate bytes, the worker checks
   its exact aggregate output-byte count, discards an oversized candidate, and
   limits an admitted frame to the remaining output-byte budget. The parent
   recomputes every fragment
   and aggregate byte count from received bytes; reported byte scalars are
   consistency checks, not trusted accounting. A continuation repeats `pack`
   and admission for its next fragment. The generation-stage hard limit is
   installed before the first model load and remains in force for all later
   continuation admissions in that invocation.
4. Only a `completed` terminal result whose parent-verified aggregate counts
   are within every effective limit may reach terminal processing. Any malformed,
   stale, late, inconsistent, or oversized result is discarded.

`generated_token_count` is an exact compatible-runner attestation: the worker
counts its private generated token IDs or consumes equivalent backend generation
metadata, then binds the scalar to the receipt and fragment index. Under the
current exact-identity personal-use trust model, the parent validates receipt,
fragment, authorization, per-fragment maximum, remaining allowance, and
aggregate arithmetic; it does not reconstruct token IDs or retokenize output.
An attestation mismatch, an over-remaining count, or an aggregate inconsistency
is `generation_worker_protocol_invalid`.

The finite classifications are `generation_budget_invalid`,
`generation_budget_unavailable`, `generation_memory_budget_unavailable`,
`generation_deadline_unavailable`, `generation_deadline_exceeded`,
`generation_context_exceeded`, `generation_token_limit_exceeded`,
`generation_output_limit_exceeded`, `generation_worker_protocol_invalid`, and
`generation_execution_failed`.
On every normal or exceptional terminal path, the parent reaps the worker,
discards any candidate output on failure, records cleanup, and then releases
the reservation. Shared resident models are outside this feature: they are not
charged to invocation reservations and may not be used by a worker that claims
the per-invocation process hard limit. Worker reuse is out of scope until it
can preserve the same per-invocation memory, deadline, and cleanup semantics.

The approved untrusted-asset isolation backend remains deferred. When it is
available, DAR shall migrate input converters, sealed-artifact assets, and
generation workers together to that common backend; this specification does
not create a generation-worker-only security mechanism.

## Boundaries

This specification supersedes model-generation limit ownership in
`workflow-input-converter-plugin` and `local-model-runner-interface`. Their
current `max_tokens` and `max_continuations` behavior remains compatibility
behavior only until this contract is implemented and migrated.

`sealed-artifact-workflow-runner` remains the outer execution boundary. Its
descriptor limits govern an asset invocation, callbacks, I/O, and output
artifacts. This contract governs a model-generation capability invoked inside
that boundary. Runtime and memory ceilings effective for a generation are also
capped by the enclosing sealed-artifact limits; it does not duplicate artifact
output-slot or callback limits.

This specification does not define:

- workflow page schemas, cursors, deterministic merges, or domain validation;
- automatic prompt summarization, context compression, or semantic state
  extraction;
- a model-specific context-window value, memory estimator, scheduler, or
  device-selection policy; or
- a promise that a model can satisfy a requested output contract within its
  budget.

A workflow that needs more than one bounded response defines independently
valid pages and deterministic state outside DAR. DAR enforces each generation
budget and any workflow-level callback/page call limit without interpreting
the page contents.

## Requirements

### FR-1: One normalized budget at the runner boundary

Before model loading, every generation request shall resolve exactly one
`GenerationResourceBudget` from the immutable workflow declaration, selected
material/profile, typed runner capability, host policy, and, when present,
enclosing sealed-artifact descriptor. Runner-specific request fields cannot
increase it. An absent optional material/profile field is non-applicable; a
missing required workflow, runner, or host value is unavailable. Unknown,
non-integer, Boolean, malformed, or over-ceiling declared values fail closed
with `generation_budget_invalid`; a required missing or incompatible source
fails with `generation_budget_unavailable`. Zero is valid only for
`max_continuations`.

The legacy OpenAI-shaped `max_tokens` and `max_continuations` request fields
are accepted only as compatibility aliases during migration. They must resolve
to the canonical budget and may only reduce its per-fragment and continuation
limits. They cannot bypass aggregate token, output-byte, context, deadline, or
memory controls.

### FR-2: Pre-dispatch and per-fragment enforcement

The host shall enforce all of the following:

1. measure actual packed input tokens before every backend call and reject when
   that count plus the requested new-token bound exceeds either
   `max_effective_context_tokens` or the selected runner's supported context;
2. request at most the lesser of `max_new_tokens_per_fragment` and the remaining
   aggregate generated-token allowance from a backend;
3. stop before a continuation when the remaining context, continuation, token,
   or deadline budget cannot admit another fragment;
4. count parent-validated exact generated-token and assembled UTF-8-byte
   scalars after every fragment; discard the candidate when either aggregate
   limit is exceeded before any downstream processing;
5. discard private candidate output and clear sealed inputs, packed inputs, and
   request-scoped generation/KV-cache state on any budget failure,
   cancellation, or timeout; and
6. never pass partial output to a workflow terminal processor or artifact
   collector.

The output-byte ceiling is an admission ceiling, not a promise that a backend
can stop inside a variable-width decoded token. Per-fragment token and memory
bounds limit transient work; byte accounting rejects an oversized fragment
before it becomes an admitted model result.

For raw-text continuation, the runner must account for the actual packed input
on every fragment. It must not silently drop, summarize, or mutate prior text
to fit the context budget. A workflow that wants a compact cursor is responsible
for supplying one through a separate bounded invocation.

### FR-3: Enforceable memory admission

`max_memory_bytes` is an admission control, not aspirational descriptor
metadata. Before backend entry, the host must obtain a receiver-owned memory
reservation for the selected material, device, packed input, and requested
generation bounds. Admission and release are atomic in the
`(material-lock, runner, device)` namespace; a reservation covers only
invocation-scoped allocations and never silently charges separately managed
shared residency. The reservation must be enforceable by one of:

1. a process/container hard memory limit;
2. a platform runtime allocation limit; or
3. a reviewed host estimator plus exclusive reservation whose conservative
   upper bound, including stated overhead, is no greater than the effective
   budget.

Before that generation admission, every runner must be inside its declared
pre-packing containment method. For a worker, this is the bootstrap envelope;
for an in-process runner, it is a platform/runtime limit or prior reservation
that covers decode and packing. A selected platform/device that cannot contain
those allocations fails with `generation_memory_budget_unavailable` before it
receives sealed input.

If the selected runner/platform cannot make such a reservation, the invocation
fails before model loading with `generation_memory_budget_unavailable`. DAR
must not rely on operating-system memory-pressure termination as enforcement.
The reservation is released on every terminal path.

### FR-4: Deadline and cancellation

The host starts the monotonic generation deadline before invocation-scoped
worker launch, converter packing, model loading, or generation can allocate
execution memory. A runner must support cancellation through load and
generation, or execute in an isolatable worker that can be terminated at the
deadline. Otherwise it is unavailable for a deadline-bounded request with
`generation_deadline_unavailable`; reporting a timeout after a
noninterruptible call returns is insufficient. It does not require eviction of
a separately managed shared resident model. A timeout produces
`generation_deadline_exceeded`; late backend output is discarded. The host
records request-scoped cleanup completion before it releases the invocation.
If expiry occurs during reap, the host escalates termination through its
platform worker controller, admits no late frame, records the failed reap, and
does not release the reservation until the worker is confirmed reaped or the
host has classified the worker controller unavailable before launch.

### FR-4a: Isolated-worker protocol

For a terminable isolated worker, the host shall use `generation-worker-v1`.
It shall install the bootstrap packing envelope before launch, validate one
receipt before every fragment's memory admission, apply any tighter
generation-stage hard limit before model loading, prohibit generation until
parent authorization, and terminate and reap the worker on expiry. It shall
reject every malformed, duplicate, stale, inconsistent, or late message with
`generation_worker_protocol_invalid`; it shall not send an oversized candidate
into an IPC result frame. Tensor serialization, converter-state serialization,
and a thread-only timeout do not satisfy this requirement. The worker follows
the current personal-use exact-identity trust model and is not evidence of
untrusted-code isolation; a future common isolation backend must replace this
execution mode for all workflow-provided Python surfaces together.

### FR-5: Observability without content disclosure

For an authorized debug run only, DAR may retain redacted per-fragment facts:
fragment index, packed-context token count, generated-token count, output-byte
count, exhaustion outcome, elapsed time, and budget-stop classification. Normal
traces and results may expose only final aggregate counters and a redacted
classification. Neither path exposes prompts, completion fragments, token IDs,
sealed payload bytes, tensors, model paths, or reservation internals.

## Acceptance Criteria

- Fake runners prove every dimension rejects before or at the correct boundary,
  with no downstream processor receiving partial output.
- A continuation test proves a growing raw prompt is rejected at the effective
  context limit rather than allocating beyond it.
- A fake reservation provider proves a missing, excessive, concurrent, and
  released reservation is classified correctly, with atomic namespace admission
  and exactly one release.
- A cancellation/deadline test proves late output is destroyed and all private
  state is cleared.
- An isolated-worker transcript fake proves bootstrap memory/deadline limits
  precede packing; each fragment has a validated receipt and safe scalar counts;
  generation begins only after reservation and authorization; no tensors,
  token IDs, converter objects, or host paths cross the workflow-visible
  protocol; malformed/repacked/duplicate/late messages are rejected; and a
  deadline-expired worker is terminated and reaped exactly once.
- A deterministic fake child-process conformance test proves the launcher
  installs the bootstrap limit before pack, withholds loader/device access until
  authorization, retains the generation-stage limit across continuations, and
  reaps on deadline. Equivalent fake platform-adapter tests prove the selected
  device allocation path is unavailable when it cannot be contained.
- A controlled real-child integration test with no model/device dependency
  proves that a child blocked after its ready marker is terminated and reaped on
  deadline, emits no admitted late frame, and releases its reservation only
  after cleanup.
- Built-in, cancellation-capable in-process, and receiver-installed runner
  fakes each prove a declared pre-packing containment/admission method or a
  redacted pre-load rejection.
- Existing converter and local-runner tests migrate to canonical budgets with
  no model download or live device dependency.
- One manually authorized run on a supported host demonstrates a bounded
  terminal result or a redacted pre-dispatch budget rejection; an OS memory
  kill is never acceptance evidence.
