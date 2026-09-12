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
| `max_runtime_milliseconds` | Wall-clock deadline covering model load residency for the invocation and every generation fragment. |
| `max_memory_bytes` | Maximum resident model-execution memory reservation for the invocation. |

The effective value for each field is the minimum of the workflow declaration,
the selected model material/profile limit, the receiving-runner capability
where it declares a bound, the receiving-host ceiling, and the enclosing
sealed-artifact limit where it applies. A workflow may request less than a host
ceiling but never more. Limits and effective values are host-private operational
policy; the sealed workflow's declared value remains package material.
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

The receiving runner exposes a reviewed capability record containing its
supported effective-context bound and one memory-reservation implementation.
The host supplies its private ceilings. These inputs and the sealed declared
budget resolve one effective budget before model loading.

A `MemoryReservationProvider` is receiver-installed and accepts only the
selected material-lock identity, runner identity, selected execution device,
packed-context token count, requested new-token bound, effective memory
ceiling, and deadline. It returns an opaque reservation that must be released
exactly once. The provider's estimation inputs, device counters, and
implementation details never enter the workflow package, trace, or model
prompt.

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
material/profile, host policy, and, when present, enclosing sealed-artifact
descriptor. Runner-specific request fields cannot increase it. Unknown,
missing, non-integer, Boolean, or over-ceiling values fail closed with a
redacted `generation_budget_invalid` or `generation_budget_unavailable`
classification. Zero is valid only for `max_continuations`.

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
4. count exact generated tokens and assembled UTF-8 bytes after every fragment;
   discard the candidate when either aggregate limit is exceeded before any
   downstream processing;
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
generation bounds. The reservation must be enforceable by one of:

1. a process/container hard memory limit;
2. a platform runtime allocation limit; or
3. a reviewed host estimator plus exclusive reservation whose upper bound is
   no greater than the effective budget.

If the selected runner/platform cannot make such a reservation, the invocation
fails before model loading with `generation_memory_budget_unavailable`. DAR
must not rely on operating-system memory-pressure termination as enforcement.
The reservation is released on every terminal path.

### FR-4: Deadline and cancellation

The host starts the generation deadline before invocation-scoped model loading
or generation can allocate execution memory. A runner must support cancellation
through load and generation, or execute in an isolatable worker that can be
terminated at the deadline. Otherwise it is unavailable for a deadline-bounded
request with `generation_deadline_unavailable`; reporting a timeout after a
noninterruptible call returns is insufficient. It does not require eviction of
a separately managed shared resident model. A timeout produces
`generation_deadline_exceeded`; late backend output is discarded. The host
records request-scoped cleanup completion before it releases the invocation.

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
- A fake reservation provider proves a missing, excessive, and released memory
  reservation are classified correctly.
- A cancellation/deadline test proves late output is destroyed and all private
  state is cleared.
- Existing converter and local-runner tests migrate to canonical budgets with
  no model download or live device dependency.
- One manually authorized run on a supported host demonstrates a bounded
  terminal result or a redacted pre-dispatch budget rejection; an OS memory
  kill is never acceptance evidence.
