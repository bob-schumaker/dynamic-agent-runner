# Model Interface Tool-Parity Test Specification

## Metadata

- Feature slug: `model-interface-parity`
- Mode: `light`
- Artifact type: test and acceptance specification
- Status: deterministic matrix and T2.1 approval harness delivered; T2.2 is
  next and local competency remains separate
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Related feature specs:
  - `specs/model-adapter-coverage/spec.md`
  - `specs/llama-cpp-local-model/spec.md`
  - `specs/mlx-local-model-adapter/spec.md`
  - `specs/mlx-local-model-tool-use/spec.md`
  - `specs/apple-foundation-model-adapter/spec.md`
  - `specs/tool-invocation-coordinator/spec.md`
  - `specs/approval-interruption-resume/spec.md`

## Objective

Define a deterministic, offline test matrix that assesses whether DAR-supported
model interfaces preserve the same model-facing tool contract and workflow
outcomes. Parity concerns request shaping, tool-call normalization, schema
validation, invocation order, result continuation, and error handling. It does
not require identical model prose or token sequences.

## Problem Statement

DAR exposes multiple model integration paths with different transports and
provider-native tool representations. Existing focused adapter tests prove
individual boundaries, but they do not establish that the same controlled
workflow behaves consistently across those boundaries. Using Fastmail for that
comparison would introduce network, authentication, changing upstream tool
metadata, and human approval into what should be a repeatable local test.

The matrix needs a small, controlled tool surface and narrowly scoped prompts
so it can distinguish an adapter-contract regression from ordinary variation in
model generation.

## Scope

This specification covers:

1. deterministic controlled tools and prompts usable without network,
   credentials, or external services;
2. a common observable result record for tool-path comparison;
3. contract coverage for every supported sync or async model interface using
   fakes, injected backends, or local recording transports;
4. optional, manually run local-model competency measurements using pinned
   artifacts; and
5. a separately scoped approval-interaction pass using the same controlled
   tools.

## Non-Goals

- No Fastmail, MCP server, account, OAuth flow, or external network call.
- No live model, Hugging Face download, Metal, or local model-server dependency
  in the pytest suite.
- No claim that different providers or quantizations produce identical text,
  token ids, latency, or tool-call identifiers.
- No expansion of the current in-process MLX tool capability. That capability
  is owned by the `mlx-local-model-tool-use` follow-up to
  `mlx-local-model-adapter`.
- No inclusion of human approval in the tool-path parity suite.
- No automated live mutation of any external system.

## Interface Matrix

The deterministic contract suite must cover each currently supported interface
through its injectable boundary. A row is not eligible for the local-model
competency suite until it advertises tool-calling support and can execute the
controlled fixture.

| Interface | Contract fixture | Local-model competency status |
| --- | --- | --- |
| OpenAI sync and async adapters | scripted SDK client | not required |
| LiteLLM sync and async adapters | scripted completion client | not required |
| OpenAI-compatible local endpoint sync and async adapters | recording local transport | eligible when a caller supplies a compatible server |
| Direct llama.cpp sync and async adapters | injected llama.cpp backend | eligible with a pinned GGUF artifact |
| In-process MLX sync and async adapters | injected compatible MLX codec/backend seam | contract-eligible through the injected pair; the stock backend remains unsupported |
| Apple Foundation Models async adapter | injected SDK/bridge seam | eligible on an eligible Mac as a separate provider-family run |

The model-agnostic executor-level fixture must also run with sync and async
fake adapters. That protects shared tool-loop behavior even where a concrete
provider has no local live-model run.

## Controlled Tool Contract

The fixture tool registry must contain only deterministic, process-local
handlers. None has `approval_required`, external side effects, credentials, or
network access.

| Tool | Input schema | Deterministic result |
| --- | --- | --- |
| `lookup_record` | `{key: string}` | a fixed record for known keys, otherwise a fixed not-found result |
| `create_record` | `{title: string, body: string}` | a stable fixture-local identifier and echoed fields |
| `transform_record` | `{record_id: string, operation: "uppercase"}` | a stable transformed record for a fixture-local identifier |
| `fail_controlled` | `{code: string}` | a typed, deliberate tool failure with no mutation |

The registry must record every attempted handler invocation, its normalized
arguments, and its result or failure. Fixture-local state resets for each test
case and cannot escape the process.

## Required Scenarios

### S1: Exact tool selection

The prompt requests creation of a named record while `lookup_record` and
`transform_record` are also available.

Acceptance criteria:

- Given the S1 prompt and controlled tool set, when an interface produces a
  normalized tool call, then it selects `create_record` exactly once before any
  handler runs.
- The title and body match the prompt's declared values after normal schema
  normalization.
- No decoy handler is invoked.

### S2: Schema-valid structured arguments

The prompt requires values that exercise strings, an enum, and a dependent
record identifier.

Acceptance criteria:

- Given a tool call contains valid arguments, when DAR validates it, then the
  recording handler receives only the schema-valid normalized arguments.
- Given the model emits unknown, missing, incorrectly typed, or malformed
  arguments, when DAR processes the call, then no handler is invoked and the
  outcome is a package-owned validation or model-tool error.

### S3: Two-step result continuation

The prompt requires a lookup followed by an uppercase transformation of the
returned record.

Acceptance criteria:

- Given the first result is returned to the model, when the workflow continues,
  then `transform_record` receives the identifier returned by `lookup_record`.
- Invocation order is `lookup_record`, then `transform_record`, with no
  additional invocation.
- The final workflow result incorporates the deterministic transformation.

### S4: Controlled tool failure

The prompt explicitly calls `fail_controlled`.

Acceptance criteria:

- Given the handler returns its deliberate failure, when the interface resumes
  the model loop or completes its provider-native callback, then the failure is
  represented through the normal DAR tool-result/error path.
- No other controlled tool is invoked as a side effect of the failure.
- The trace and result record preserve the normalized tool name and typed
  failure classification without provider-native exception leakage.

### S5: No-tool completion

The prompt requests a direct textual answer and does not require any tool.

Acceptance criteria:

- Given the controlled tools are available, when the no-tool prompt runs, then
  the recording registry observes no invocation.
- A valid final model response completes the workflow without a synthetic tool
  result.

### S6: Malformed provider output

Each adapter-specific seam must be driven with malformed or incomplete
provider-native tool-call data.

Acceptance criteria:

- Given malformed tool-call data, when normalization fails, then DAR raises or
  reports a package-owned model/tool error with the handler invocation count at
  zero.
- A provider-native payload must not bypass schema validation, tool policy, or
  the shared invocation coordinator.

## Parity Observables

Every scenario must produce a comparison record containing:

- interface identifier and sync/async mode;
- scenario identifier;
- exposed tool names and schemas, in deterministic order;
- normalized model tool calls and arguments;
- handler invocation sequence and normalized results or failures;
- final workflow completion class; and
- relevant package-owned error class or trace event type.

Parity is assessed by comparing this record's contract fields. Response prose,
provider request IDs, timestamps, token usage, and provider-native callback IDs
are diagnostic metadata and must not be equality requirements.

For deterministic matrix closure, a test-only semantic projection additionally
compares every seam record with its scenario baseline. It excludes interface
and sync/async mode, canonicalizes provider JSON arguments and mapping order,
and omits provider-specific trace mechanics. Its mandatory fields are scenario
or variant, exposed schemas, normalized calls, invocations/results, completion
outcome, and an approved package-error category. Structured S2 invalids are
`validation_error`; malformed S2/S6 are `normalization_error` and may be an
MLX `ModelExecutionError` or a `WorkflowExecutionError` at another seam; S4
is `tool_failure`. Native tests retain exact error-class assertions. Apple S4
is callback-native: its semantic outcome is one failed `fail_controlled`
invocation, package-owned executor error, and no response continuation; it does
not require a model-loop `tool_failure` stop trace.

The exposed-schema field is captured from the actual first adapter-facing
request (or its provider-bound equivalent), then normalized to tool name and
parameters. It must not be reconstructed from the shared fixture.

## Test Levels and Gates

### Deterministic contract gate

This is required for every interface row. It runs in ordinary pytest using
fakes, injected backends, or a recording local transport.

- It must not import optional provider SDKs unless the existing test seam does
  so safely.
- It must make no network request, external tool invocation, or model download.
- It is hard pass/fail: the specified normalized calls, invocations, results,
  and failure behavior must match the scenario.

### Local-model competency measurement

This is optional, manually initiated, and outside CI. It uses Qwen3 Instruct
with fixed generation settings to compare direct llama.cpp, a compatible local
endpoint, and an explicitly compatible MLX codec/backend pair. The stock MLX
backend remains outside this measurement because it rejects tool-bearing
requests. The MLX artifact revision is owned by
[`mlx-local-model-tool-use/implementation-decision.md`](../mlx-local-model-tool-use/implementation-decision.md).
Apple Foundation Models is measured separately because it cannot use the same
model weights.

For each scenario, record attempts, valid tool selections, schema-valid
arguments, completion outcomes, artifact revision, backend version, and
generation settings. Report rates and failures; do not treat a language-model
variation as a deterministic contract mismatch.

### Approval-interaction gate

This is a separate coordinator/executor pass. It reuses `create_record` with
`approval_required: true` and tests deny, approve once, and approve for the
current run. It must not be a prerequisite for no-approval interface parity and
does not require a live model or external tool.

The gate exercises the generated-workflow wrapper's existing approval broker,
not DAR's pause-only public interruption boundary. DAR's durable resume and
approval-decision APIs remain out of scope.

## Cross-Cutting Requirements

### FR-1: Common DAR path

All provider-native callbacks and normalized model responses under test must
enter DAR's normal tool validation, coordinator, lifecycle, trace, state, and
result-shaping path before a controlled handler runs.

### FR-2: Fixture isolation

Each scenario must create new fixture-local registry state. Tool handlers must
not read environment credentials, files outside the test fixture, wall-clock
state, or network resources.

### FR-3: Capability truthfulness

Tests must not mark an adapter as tool-parity capable merely because a fake
backend can return a tool call. Capability metadata and public behavior must
agree. The MLX injected compatible codec/backend pair is tool-capable, while
the stock MLX backend remains an expected unsupported case.

### FR-4: Separation of concerns

Tool-path parity verifies automatic behavior with no approval boundary.
Approval tests verify coordinator behavior with deterministic controlled tools.
External-service acceptance, including Fastmail, remains an independent,
human-authorized test category.

## Validation Checklist

- [x] A controlled registry implements all four tools with no external I/O.
- [x] S1 through S6 run against sync and async executor-level fake adapters.
- [x] Every eligible provider/adapter row has focused deterministic contract
      coverage at its injected transport or backend seam.
- [x] The comparison record omits nondeterministic provider metadata from hard
      equality assertions.
- [x] MLX coverage proves the injected compatible codec/backend pair's normal
      tool path and the stock backend's unsupported rejection separately.
- [x] Approval interaction is explicitly a separate, not-run gate for this
      deterministic matrix closure; it must cover deny, approve once, and
      approve-for-run using only `create_record`.
- [x] No parity test performs a network request, authentication flow, model
      download, live model call, or external mutation.

## Open Questions

- The implementation task must choose the precise fixture and comparison-record
  module locations after reviewing the nearest executor and adapter test files.
- The implementation task must select the repeat count for optional local-model
  competency measurements; artifact provenance is already fixed by the MLX
  implementation decision and remains outside the CI contract.
