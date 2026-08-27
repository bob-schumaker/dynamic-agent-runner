<!-- markdownlint-disable MD013 -->
# Apple Foundation Models Adapter Specification

## Metadata

- Feature slug: `apple-foundation-model-adapter`
- Mode: `guided`
- Artifact type: authoritative SDD feature specification
- Status: A1 and A2 implementation complete; A3 DAR-authoring host integration planned; standalone direct release gate established; pytest-native SDK checks remain diagnostic
- Version: `0.5`
- Date: 2026-07-01
- Owner: dynamic-agent-runner model-provider boundary
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Related feature specs:
  - `specs/openai-compatible-provider-wrapper/spec.md`
  - `specs/model-adapter-coverage/spec.md`
  - `specs/openai-responses-tool-loop-compat/spec.md`
  - `specs/iterative-agent-loop-runtime/spec.md`
  - `specs/approval-interruption-resume/spec.md`
  - `specs/tool-invocation-coordinator/spec.md`
  - `specs/model-event-streaming/spec.md`
  - `specs/mlx-local-model-adapter/spec.md`
- Related implementation surfaces:
  - `src/dynamic_agent_runner/openai_client.py`
  - `src/dynamic_agent_runner/executor.py`
  - `src/dynamic_agent_runner/errors.py`
  - `src/dynamic_agent_runner/workflow_host/host.py`
  - `src/dynamic_agent_runner/workflow_host/profiles.py`
  - `src/dynamic_agent_runner/workflow_host/runner.py`
  - `src/dynamic_agent_runner/__init__.py`
  - `tests/test_openai_client.py`
  - `tests/test_executor.py`
  - `tests/test_import.py`
- Local reference implementation inspected:
  - `/Users/roschuma/Repos/github/fmx/`
  - commit `b553183759732eeff8524d9cfa970e48dd83584a`
- Upstream dependency evaluated:
  - Apple `apple-fm-sdk` `0.2.0`

## Objective

Add a macOS-only, package-owned adapter that lets dynamic-agent-runner execute
text and JSON-schema-constrained requests through Apple's on-device Foundation
Models framework while preserving DAR's existing model-selection, request,
response, error, tracing, and strict-coverage boundaries.

The adapter must present an in-process OpenAI Responses-compatible client
surface to DAR. It must not require the `fmx` package, the official OpenAI SDK,
an HTTP server, or a caller-managed model asset. The Apple SDK remains an
optional, lazily imported provider dependency.

## Problem Statement

Apple's Foundation Models SDK for Python exposes the system-managed on-device
model available through Apple Intelligence on eligible Macs. The locally
inspected `fmx` project demonstrates useful behavior for availability checks,
session construction, text generation, structured output, generation options,
streaming, image prompts, and transcript handling, but `fmx` is a CLI-oriented
application rather than a reusable DAR model adapter:

- it imports `apple_fm_sdk` eagerly
- its one-shot response path prints to standard output
- its session factory is a thin SDK constructor
- its command surface does not implement DAR's request and response contracts
- its current chat flow does not expose tool calling

DAR already has a repository-owned OpenAI-compatible client facade. An internal
Apple client can implement that facade and be wrapped by
`AsyncOpenAIClientAdapter`, allowing the existing executor path to normalize the
response without adding an Apple-specific executor branch.

The system Apple model is not an MLX model. It has no caller-owned model path,
GGUF file, converted checkpoint, Hugging Face identity, or server lifecycle.
This feature therefore requires a separate provider specification rather than
an extension of `mlx_models.py`.

## Discovery Evidence

The following behavior was observed during feature discovery on macOS 26.5.1
on arm64 hardware with Apple Intelligence enabled:

- `apple-fm-sdk==0.2.0` installed and imported under Python 3.12, 3.13, and
  DAR's selected Python 3.14.6 runtime.
- The Apple system model reported available and produced text under the tested
  Python versions.
- The local `fmx` suite passed 19 tests under Python 3.13 and Python 3.14,
  including live text and structured-output smoke tests.
- Some direct probes returned an opaque `GenerationError` with status `255`
  while the availability check still reported success; later complete live
  suites passed. Availability is therefore a preflight signal, not a guarantee
  that generation will succeed.

These observations justify the first-release dependency and runtime direction,
but they do not replace repeatable unit coverage or release validation.

## Users

- macOS callers who want DAR workflows to use Apple's on-device system model
  without an API key or caller-managed model files
- downstream hosts that require an explicit local-only adapter boundary through
  `model_adapter_coverage="strict"`
- runtime maintainers who need provider integration behind DAR-owned protocols
- test authors who need deterministic provider-boundary tests plus opt-in or
  environment-gated live Apple model verification

## Domain Vocabulary

- **Apple Foundation Models provider**: the package-owned integration with
  Apple's `apple-fm-sdk` and system-managed on-device language model.
- **System model**: the model selected and managed by macOS and Apple
  Intelligence; it is not a portable model artifact owned by DAR or the caller.
- **Responses-compatible facade**: an in-process Python object implementing the
  subset of DAR's OpenAI Responses client protocol required by this feature. It
  is not a claim of full OpenAI wire-protocol compatibility.
- **Live Apple test**: an integration or end-to-end test that invokes the real
  on-device system model. Live Apple tests are not unit tests.
- **Structured output**: generation constrained by an explicit JSON Schema and
  returned to DAR as JSON text in the normalized `ModelResponse.content`.
- **Local execution**: DAR makes no provider network request; model execution is
  delegated in process to the macOS Foundation Models framework.
- **Tool invocation coordinator**: a DAR-owned execution boundary whose first
  slice supports direct and model-loop tool requests and applies DAR exposure, approval,
  lifecycle-hook, tracing, registry, state, and result-shaping behavior before
  any registered tool handler can run.

## Existing Runtime Context

- `OpenAIModelRequest` is DAR's normalized model-request type.
- `ModelResponse` is DAR's normalized model-response type.
- `AsyncOpenAIClientProtocol` and its responses-resource protocol define the
  minimum async provider-facing client surface.
- `AsyncOpenAIClientAdapter` already owns async dispatch, package-owned error
  translation hooks, model aliases, local metadata, and response normalization.
- `normalize_openai_response(...)` already accepts Responses-style mappings and
  extracts message text and model tool calls.
- Model selection already accepts caller-provided adapters and supports strict
  coverage through `model_adapter_coverage="strict"`.
- Capability-constrained selection uses the workflow's existing model-map and
  model-capability metadata paths. The Apple adapter must not introduce a
  parallel selection engine.
- Provider-native token streaming is not yet part of the public model adapter
  result contract; the final `ModelResponse` remains authoritative.
- DAR's iterative tool loop expects model-requested calls to return as
  `ModelToolCall` values so DAR retains tool approval, tracing, execution, and
  result-policy ownership.
- Apple's `Tool.call(...)` callback is a provider ingress point, not permission
  to invoke a registered handler directly. Future Apple tool support must route
  callbacks through a DAR-owned tool invocation coordinator.

## Release Boundaries

### First release: A1 — Local Text and Structured Responses

The first release includes:

1. an optional, lazy `apple-fm-sdk` dependency path
2. a package-owned Apple backend boundary with injected test seams
3. an async in-process Responses-compatible client facade
4. a public factory returning a configured `AsyncOpenAIClientAdapter`
5. fixed caller-visible model aliases for the Apple system model
6. macOS, SDK, and system-model availability preflight behavior
7. ordered text-message and instruction translation
8. final text response normalization
9. explicit JSON Schema structured output
10. supported temperature and maximum-output-token translation
11. package-owned error translation and retry-safe failure behavior
12. conservative provider capability metadata and strict-coverage examples
13. deterministic fake-backed unit and executor tests
14. live Apple integration and workflow smoke tests on eligible Macs
15. public documentation for installation, eligibility, usage, limitations, and
    failure diagnosis

### Second release: A2 — DAR-Managed Apple Tool Bridge

The second release adds Apple model tool use without moving tool policy or tool
execution ownership into the provider adapter:

1. only tools exposed to the active DAR node are registered with the Apple
   session
2. Apple `Tool.call(...)` callbacks translate provider arguments into a
   package-owned invocation request
3. every callback delegates to a DAR-owned tool invocation coordinator
4. the coordinator applies tool exposure, argument validation, approval policy,
   lifecycle hooks, tracing, registry invocation, workflow-state updates, and
   `ToolResult.model_facing_output` selection
5. approval-required calls cannot reach the registered handler before DAR
   records and resolves the approval decision
6. a synchronous, trusted decision collaborator may return an exact approved,
   denied, cancelled, or expired result before dispatch; unresolved approval
   must become a provider-aware DAR interruption before the tool handler runs
7. Apple receives only the coordinator's serialized model-facing result or a
   provider-safe representation of a DAR-controlled failure
8. live tests prove that an Apple callback enters DAR behavior before the test
   tool handler and that denied approval prevents handler invocation

The technical plan must choose between a generated Apple wrapper per exposed
DAR tool and a single schema-constrained gateway tool. Per-tool wrappers are
preferred when DAR schemas can be translated without loss; a gateway remains an
allowed fallback only if it preserves the same coordinator and allowlist.

A2 is authorized by its separately approved plan. Its implementation depends on
the completed direct/model-loop coordinator slice, then extracts a provider-safe
ingress seam and an explicit synchronous approval-decision contract that preserve
DAR state and correlation. The current coordinator does not itself enable Apple
callbacks.

### Deferred releases

Later releases require separate approval and plan slices for:

- provider-native text-delta streaming through DAR's public event stream
- image or other multimodal input
- persistent or resumed Apple SDK sessions and transcript translation
- durable cross-process approval pause/resume of an in-flight Apple session when
  A2's in-process approval resolution is insufficient
- a sync Apple client facade when a concrete caller requires one
- a loopback or externally addressable HTTP OpenAI-compatible server
- Private Cloud Compute or any remote Apple model
- model switching, custom Apple system-model use cases, or guardrail variants
- automatic use of a future native macOS `fm` command

## Proposed Public Usage

The exact helper names may be refined during planning, but the first release
must preserve this small caller-facing shape:

```python
from dynamic_agent_runner import (
    AppleFoundationModelConfig,
    create_apple_foundation_model_async_adapter,
    run_agent_workflow,
)

adapter = create_apple_foundation_model_async_adapter(
    AppleFoundationModelConfig(
        model_aliases=("apple-system-language-model",),
    )
)

result = run_agent_workflow(
    prompt="Answer using the on-device Apple model.",
    package_directory="path/to/agent-package",
    model_adapter=[adapter],
    model_adapter_coverage="strict",
)
```

An async adapter is the canonical first-release surface. It must be accepted by
both DAR's sync and async high-level workflow entry points through the existing
executor path.

## Functional Requirements

### FR-1: Provide a package-owned Apple provider boundary

DAR must own the boundary between runtime requests and `apple-fm-sdk`.

Acceptance criteria:

- Given the Apple feature is installed, when the factory constructs an adapter,
  then DAR returns an existing `AsyncOpenAIClientAdapter` backed by a
  package-owned Apple client rather than a new executor-specific adapter family.
- Given the package-owned Apple client receives a request, when it invokes the
  SDK, then SDK-specific types remain inside the Apple provider module.
- Given tests need deterministic behavior, when the provider is constructed
  with injected availability, session, or generation collaborators, then no
  Apple SDK import or live model invocation is required.
- Given a caller imports `dynamic_agent_runner`, when Apple support is not
  installed, then package import still succeeds.

### FR-2: Expose an in-process OpenAI Responses-compatible facade

The provider must implement the subset of DAR's async OpenAI client protocol
needed for request dispatch and response normalization.

Acceptance criteria:

- Given `AsyncOpenAIClientAdapter` calls `client.responses.create(...)`, when
  the Apple client handles the call, then it accepts the model, input,
  `response_format`, and supported generation-option fields produced by DAR.
- Given Apple returns final text, when the facade returns to the adapter, then it
  returns a Responses-style mapping that `normalize_openai_response(...)`
  converts into `ModelResponse(content=<text>)`.
- Given the provider creates a response identifier, then the identifier is
  unique enough for run diagnostics and does not claim to be an Apple SDK model
  or transcript identifier.
- Given the in-process facade is used, then no loopback port, HTTP transport,
  OpenAI API key, or official OpenAI SDK client is required.
- Given an unsupported OpenAI-compatible field is supplied, then the provider
  rejects it clearly rather than silently claiming full protocol support.

### FR-3: Treat the Apple model as a fixed system-managed local model

The adapter must expose stable caller-facing aliases without pretending that
the caller controls the underlying model identity.

Acceptance criteria:

- Given the default configuration, when adapter selection runs, then the adapter
  advertises `apple-system-language-model` or the approved equivalent alias.
- Given callers configure additional aliases, when the provider receives a
  selected alias, then it validates that the alias belongs to the adapter before
  invoking the single system model.
- Given the adapter is inspected, then it reports local in-process execution and
  system-managed model identity.
- Given a caller requests a model path, Hugging Face reference, GGUF file, MLX
  directory, or arbitrary remote model id, then the Apple configuration rejects
  that input because those concepts do not apply to the system model.

### FR-4: Fail clearly when the platform or model is unavailable

Apple provider construction must remain portable, while first use must fail
with actionable package-owned errors.

Acceptance criteria:

- Given Linux, Windows, an older macOS release, or a non-eligible environment,
  when `dynamic_agent_runner` is imported, then import succeeds without loading
  `apple_fm_sdk`.
- Given a non-Darwin platform, when generation is requested, then execution
  raises a package-owned `ModelExecutionError` before attempting an SDK import.
- Given `apple-fm-sdk` is absent on an otherwise eligible platform, when
  generation is requested, then the error names the missing optional Apple
  dependency without leaking a raw `ImportError`.
- Given Apple Intelligence is disabled, the device is ineligible, or the model
  is not ready, when preflight runs, then the error preserves the SDK reason and
  provides an actionable diagnostic.
- Given preflight reports available but session creation or generation fails,
  when the SDK raises, then the failure is translated and preserved as the
  cause; preflight success must not suppress or misclassify the generation
  failure.

### FR-5: Translate instructions and ordered text messages

The provider must convert DAR's normalized text conversation into Apple session
input deterministically.

Acceptance criteria:

- Given system or developer messages, when a fresh Apple session is created,
  then their text is combined in original order into session instructions.
- Given user and assistant text messages, when the request prompt is prepared,
  then all messages are retained in original order with their roles preserved by
  the approved transcript or deterministic prompt-rendering strategy.
- Given the current request contains conversation history, when generation
  begins, then no prior message is silently dropped.
- Given content contains a non-text part, tool transcript item, image, audio, or
  unsupported provider object, then the first release rejects the request with a
  package-owned error instead of coercing it through `str(...)`.
- Given the SDK session maintains its own transcript, when the request finishes,
  then that provider transcript does not replace DAR's authoritative workflow or
  session history.

### FR-6: Use a fresh Apple session per model request

The first release must avoid hidden state, cross-run leakage, and SDK session
concurrency hazards.

Acceptance criteria:

- Given two DAR model requests, when the provider handles them, then each
  request creates its own Apple `LanguageModelSession`.
- Given the request already contains history, when a fresh Apple session is
  created, then the provider does not also replay hidden state from a previous
  request.
- Given concurrent DAR requests, when they execute, then they do not share one
  mutable Apple session.
- Given future persistent-session work is requested, then it requires an
  explicit follow-up contract for transcript ownership and resumption.

### FR-7: Support final plain-text generation

The first release must support final, non-streaming text generation.

Acceptance criteria:

- Given a valid text request, when Apple generation succeeds, then the caller
  receives a normalized `ModelResponse` with non-empty content when the provider
  produced non-empty text.
- Given the SDK returns an empty string, when normalization completes, then the
  provider preserves the empty result rather than inventing content.
- Given the SDK exposes progressive snapshots internally, when the first release
  completes the request, then it still returns only the final authoritative
  response through DAR's current adapter contract.
- Given a request asks for provider-native streaming, then the first release
  fails clearly or disables the option according to the approved request
  contract; it must not expose partial snapshots as a completed response.

### FR-8: Support explicit JSON Schema structured output

The first release must translate supported structured-output requests into
Apple guided generation.

Acceptance criteria:

- Given `response_format` contains an explicit supported JSON Schema, when the
  provider handles the request, then it passes the schema through the Apple
  SDK's JSON-schema generation path.
- Given Apple returns structured generated content, when the facade returns a
  Responses-style mapping, then `ModelResponse.content` contains valid JSON text
  representing the generated value.
- Given the schema is malformed, missing, unsupported by Apple, or rejected by
  the SDK, then the provider raises a package-owned error with the SDK failure
  preserved as the cause.
- Given `response_format={"type": "json_object"}` contains no schema, then the
  first release rejects it rather than inventing an unconstrained schema.
- Given structured output is required by a workflow node, when the Apple alias
  is declared with `structured_output` in the existing model-map or capability
  metadata path, then strict adapter selection can choose the Apple adapter.

### FR-9: Map only supported generation options

The provider must translate a conservative, documented subset of generation
options.

Acceptance criteria:

- Given a request supplies `temperature`, when the value is valid for the Apple
  SDK, then the provider maps it to Apple `GenerationOptions.temperature`.
- Given a request supplies DAR's existing local-adapter option `max_tokens` or
  the Responses-compatible alias `max_output_tokens`, then the provider maps it
  to
  `GenerationOptions.maximum_response_tokens`.
- Given both token-limit aliases are supplied, then request validation rejects
  the ambiguous request before generation.
- Given no supported generation options are supplied, then the provider uses
  Apple defaults rather than constructing speculative values.
- Given an unsupported sampling, penalty, seed, stop, log-probability, or
  provider-specific option is supplied, then the provider rejects or explicitly
  documents ignoring it; silent acceptance is not allowed.
- Given a value is outside the SDK-supported type or range, then validation
  fails before generation when DAR can validate it locally.

### FR-10: Preserve DAR error and retry ownership

All public failures must use DAR-owned error types and remain safe for the
existing workflow retry policy.

Acceptance criteria:

- Given any SDK availability, session, schema, context-window, guardrail,
  generation, or tool-related exception, when it crosses the provider boundary,
  then callers receive a package-owned error with the original exception as its
  cause.
- Given an SDK error can be classified as context overflow, transient
  availability, rate limiting, cancellation, invalid input, or permanent model
  unavailability, then the translation retains that classification in the
  package-owned message or subtype needed by runtime policy.
- Given an opaque error such as status `255`, then the provider does not claim a
  permanent or retryable classification without evidence.
- Given retry policy is configured by DAR, then the provider performs no hidden
  unbounded retry loop and does not duplicate a completed response.
- Given cancellation reaches an async SDK request, then cancellation propagates
  without being converted into a successful or retryable result.

### FR-11: Advertise conservative capabilities

The first release must report only behavior it implements through DAR.

Acceptance criteria:

- Given adapter diagnostics are inspected, then the provider reports:
  - provider: `apple_foundation_models`
  - execution: `in_process`
  - local: `true`
  - model_identity: `system_managed`
  - structured_output: `true`
  - streaming: `false`
  - tool_calling: `false`
  - multimodal: `false`
  - embeddings: `false`
- Given the Apple SDK supports a capability that DAR has not bridged, then the
  adapter continues to report that capability as unsupported.
- Given a workflow requires unsupported capabilities, then selection or request
  validation fails before the provider silently degrades the request.

### FR-12: Preserve DAR-owned tool execution across release boundaries

The first release must not allow Apple SDK tool callbacks to bypass DAR's tool
runtime.

Acceptance criteria:

- Given a request includes tools, tool choice, tool-call transcript items, or
  tool-result transcript items, when the first-release provider validates the
  request, then it raises a clear package-owned unsupported-capability error
  before Apple generation.
- Given Apple SDK documentation exposes `Tool` callbacks, then the first release
  does not register DAR tools as Apple callbacks.
- Given A2 Apple tool support is enabled, then every Apple callback delegates to
  the DAR-owned tool invocation coordinator and never invokes a handler or
  `ToolRegistry.invoke_tool_async(...)` directly.
- Given the coordinator receives an Apple-originated request, then it preserves
  DAR exposure checks, approval behavior, lifecycle hooks, tracing, registry
  validation and invocation, workflow-state storage, model-facing output, and
  completion-policy enforcement to the extent supported by the approved A2
  contract.
- Given an approval-required tool has not been approved, then the registered
  handler is not invoked even though Apple is awaiting the callback.

### FR-13: Fit strict and augmented adapter coverage

The Apple adapter must participate in existing model-adapter coverage without a
new selection branch.

Acceptance criteria:

- Given a caller supplies only the Apple adapter with
  `model_adapter_coverage="strict"`, when a node requests an advertised Apple
  alias, then the executor selects it through the existing path.
- Given strict coverage and no supplied adapter advertises the Apple alias, then
  execution fails before creating a default OpenAI adapter.
- Given augmented coverage and an unrelated eligible OpenAI model is requested,
  then current default OpenAI fallback behavior remains unchanged.
- Given a node requires structured output, then the existing model-map or
  capability metadata must declare the Apple alias accordingly; the feature
  must not add hidden model-selection semantics.

### FR-14: Provide deterministic unit and live integration coverage

The feature must distinguish fast deterministic unit coverage from real-model
verification.

Acceptance criteria:

- Given unit tests run on any supported development platform, then they use fake
  availability, session, generated-content, and error collaborators and never
  import or call the live Apple model.
- Given `apple-fm-sdk` is absent, when the unit and import suites run, then all
  non-live Apple adapter tests still pass.
- Given an eligible Mac with the optional dependency and Apple Intelligence
  available, when explicitly enabled standalone live checks run, then they exercise real text and JSON-schema generation.
- Given an eligible Mac, when the standalone live end-to-end check runs, then a DAR workflow selects the Apple adapter with strict coverage and returns a model-produced final result.
- Given the model is unavailable, when live tests are collected, then they skip
  with the SDK's availability reason rather than fail during module import.
- Given live output is nondeterministic, then tests assert structural and
  semantic invariants rather than exact prose except for deliberately bounded
  smoke prompts.
- Given pytest-native Apple checks run, then their result is recorded separately because the SDK can return opaque status 255 despite a successful availability preflight; standalone live evidence is authoritative.
- Given CI or another machine lacks Apple prerequisites, then live tests are
  skipped and deterministic unit coverage remains authoritative for code
  correctness.

### FR-15: Document installation, usage, and limitations

The feature must be usable without reading provider implementation code.

Acceptance criteria:

- Documentation names macOS 26+, compatible Apple silicon, Apple Intelligence,
  the supported Python range, the optional `apple-fm-sdk` install path, and any
  Xcode or agreement prerequisite imposed by the upstream SDK.
- Documentation shows sync and async DAR workflow entry-point usage with the
  canonical async Apple adapter and strict coverage.
- Documentation shows explicit structured-output capability metadata where
  required by model selection.
- Documentation states that the model is system-managed and that no API key,
  model path, Hugging Face reference, or local HTTP server is used.
- Documentation states the first-release exclusions for tools, public
  streaming, images, persistent Apple sessions, PCC, and external HTTP clients.
- Documentation includes diagnostics for disabled Apple Intelligence,
  ineligible devices, model-not-ready state, missing SDK, and generation failure
  after successful preflight.

### FR-16: Route A2 Apple tool callbacks through DAR behavior

The A2 provider bridge must treat Apple tool callbacks as requests to DAR, not
as direct tool invocations.

Acceptance criteria:

- Given an Apple session exposes tools for a DAR node, when the session is
  constructed, then it receives only wrappers for tools returned by the active
  node's DAR exposure rules.
- Given Apple invokes a wrapper, when the wrapper receives generated arguments,
  then it converts them to a DAR-owned invocation request containing the active
  run, node, tool, call, and argument context.
- Given the invocation request reaches the coordinator, then the coordinator
  performs the same argument validation and policy checks required for a
  provider-originated DAR model tool call before invoking the registry.
- Given an invocation requires approval, then exposure and argument validation
  run first, approval is resolved before pre-invocation lifecycle hooks, and the
  handler or registry is not invoked until approval succeeds.
- Given the tool requires approval, when no approval decision exists, then the
  coordinator enters DAR's approval behavior and does not invoke the handler.
- Given a synchronous trusted decision collaborator approves the exact normalized
  invocation, then the coordinator invokes the handler once with the approved
  arguments and records the approval and tool lifecycle events.
- Given approval is rejected, cancelled, expires, or cannot be resolved through
  the active host contract, then the handler is not invoked; unresolved approval
  is represented through a provider-aware DAR interruption rather than an
  unclassified direct callback error.
- Given the registry returns a `ToolResult`, when the callback completes, then
  Apple receives only a serialized form of `ToolResult.model_facing_output` and
  DAR retains the full result in workflow state.
- Given tool output declares sensitive fields, when trace events are emitted,
  then the coordinator preserves the current DAR redaction contract.
- Given Apple invokes more tools or iterations than DAR policy permits, then the
  coordinator stops further handler invocation and returns a DAR-controlled
  failure or interruption.
- Given an A2 tool schema cannot be represented safely as an Apple
  `GenerationSchema`, then adapter preparation rejects that tool before session
  generation instead of weakening its validation silently.

### FR-17: Support Apple Foundation Models in the sealed DAR-authoring host

The human-configured local host must be able to select the Apple adapter for a
saved workflow without turning it into an HTTP or LiteLLM profile.

Acceptance criteria:

- Given a human configures an Apple host profile on an eligible Mac, then it
  records an Apple provider selection and model alias without a base URL, API
  key, model-path, or downloaded-model reference.
- Given an unsupported platform, missing optional SDK, or unavailable system
  model, then profile setup and host opening fail with a package-owned,
  redacted eligibility error before any workflow, MCP, or tool dispatch.
- Given a saved workflow is registered to the Apple profile, then the host
  constructs the canonical Apple async adapter rather than the HTTP local-model
  adapter, while preserving strict-local registration checks and binding the
  run to that exact profile. A workflow model alias outside the selected
  adapter's strict coverage must fail before input consumption, provider work,
  MCP initialization, or handler dispatch.
- Given a saved workflow exposes a reviewed MCP tool, then an Apple callback
  reaches the existing DAR coordinator and preserves reviewed-surface binding,
  approval, lifecycle hooks, state, trace redaction, result shaping, and tool
  budgets.
- Given the configured host remains HTTP-backed, then its profile, adapter
  selection, registration, and invocation behavior remain unchanged.
- Given the eligible-Mac Fastmail read-only acceptance is run after A3, then it
  first verifies from a redacted current-surface digest that the reviewed
  `search_email` schema is admissible for an Apple wrapper, then uses the saved
  Apple-backed workflow and calls only that tool. It records only
  package/transcript digests, terminal status, and dispatch counts; no email
  content, OAuth value, raw tool result, or raw schema enters checked-in
  evidence. An inadmissible schema blocks the acceptance rather than weakening
  the schema or starting the live run.

## Non-Functional Requirements

### NFR-1: Portability

Importing DAR and constructing configuration values must remain safe without
Apple dependencies and on non-macOS platforms.

### NFR-2: Privacy boundary

The adapter must not create an HTTP client, resolve a remote model, download
model assets, or send prompts through a DAR-owned network path. Documentation
must describe the on-device integration without making guarantees beyond the
behavior of Apple's framework and the host's operating-system configuration.

### NFR-3: Concurrency safety

Requests must not share mutable Apple SDK sessions. The provider must respect
async cancellation and DAR's existing request concurrency behavior.

### NFR-4: Testability

Every first-release behavior except the Apple framework's own model quality must
be testable through injected fakes. Live tests validate integration rather than
replace deterministic unit coverage.

### NFR-5: Compatibility honesty

The facade must describe itself as a supported OpenAI Responses-compatible
subset. Unsupported fields and capabilities must fail closed; the feature must
not claim drop-in compatibility for arbitrary OpenAI clients.

### NFR-6: Dependency isolation

DAR must depend directly on an approved `apple-fm-sdk` version range as an
optional dependency. It must not depend on `fmx`, vendor `fmx` source, invoke the
`fmx` CLI, or copy CLI presentation and persistence concerns into the provider.

### NFR-7: Provider callback containment

No Apple callback may receive a raw handler or unrestricted registry reference.
It must receive only an invocation coordinator scoped to the current run, node,
and exposed tool set.

## Edge and Error Cases

- The platform is Darwin but the macOS version is below the SDK requirement.
- The SDK imports successfully but its native library fails to load.
- Apple Intelligence is disabled after adapter construction.
- Availability reports true but session creation or generation fails.
- The model becomes unavailable between preflight and generation.
- The system model rejects the prompt through its guardrails.
- Instructions exist without a user message.
- Multiple system and developer messages must preserve order.
- The request contains only assistant history or contains an empty prompt.
- The request contains tool, image, audio, or unknown content parts.
- The requested alias is not advertised by the adapter.
- The structured-output schema is invalid JSON Schema or unsupported by Apple.
- Generated structured content cannot be serialized as JSON.
- `temperature` or token limits have invalid types or ranges.
- Async generation is cancelled.
- The SDK raises a context-window or opaque generation error.
- Two workflows invoke the adapter concurrently.
- Live tests encounter a model-not-ready or temporarily unavailable state.

## Security and Privacy Considerations

- No API key or provider credential is required by the adapter.
- Prompts and generated content remain sensitive and must follow existing DAR
  tracing redaction behavior.
- Availability and error diagnostics must not include prompt content.
- Structured-output validation errors may identify schema locations but must not
  dump unrelated sensitive request content.
- On-device execution does not authorize ambient filesystem, network, contacts,
  calendar, or application access.
- Apple tools must remain behind DAR's explicit exposure, approval, lifecycle,
  tracing, registry, state, and result-shaping boundaries.

## Non-Goals

The A1 release does not include:

- any dependency on or runtime invocation of `fmx`
- an Apple-specific executor branch or workflow node kind
- a new general model-adapter framework
- an HTTP `/v1/responses`, `/v1/chat/completions`, or `/v1/models` server
- use of the official OpenAI SDK for Apple model calls
- sync Apple SDK client emulation as a separate public provider surface
- Apple SDK tool registration or DAR tool calling (added by A2)
- provider-native token or snapshot streaming
- image, audio, or other multimodal prompts
- persistent Apple sessions, transcript save/load, or durable memory
- Private Cloud Compute or any other remote Apple inference path
- model selection beyond the one system-managed on-device model
- MLX model loading, GGUF handling, model conversion, Hugging Face downloads, or
  local model inventory
- automatic retry of unclassified SDK failures
- benchmarks, model-quality evaluation, or parity claims against hosted models

The A3 release does not add a generic provider-profile framework, an Apple HTTP
server, a non-Apple host behavior change, workflow-selected provider routing,
or a bypass around the existing sealed registration, MCP, approval, and trace
boundaries.

The A2 release additionally does not include direct callback-to-handler or
direct callback-to-registry invocation, ambient access to all registered tools,
or silent fallback around approval and schema constraints.

## Validation Checklist

The first-release implementation is not complete until all applicable checks
pass:

- [x] Package import succeeds without `apple-fm-sdk`.
- [x] Adapter configuration and construction succeed on non-macOS platforms
      without importing `apple-fm-sdk`.
- [x] First generation on an unsupported platform fails before SDK import.
- [x] Missing SDK, unavailable model, and SDK generation errors translate to
      package-owned errors with preserved causes.
- [x] Fake-backed text generation returns a normalized `ModelResponse`.
- [x] Instructions and ordered text history translate without silent loss.
- [x] Unsupported content, streaming, and unrecognized request fields
      fail closed.
- [x] Explicit JSON Schema generation returns valid JSON text.
- [x] Schema-less `json_object` mode fails clearly.
- [x] Temperature, `max_tokens`, and `max_output_tokens` map correctly, and
      conflicting token-limit aliases fail before generation.
- [x] A fresh SDK session is created per request.
- [x] Concurrent requests do not share mutable sessions.
- [x] Strict coverage selects the Apple alias and prevents default OpenAI
      fallback for missing coverage.
- [x] Structured capability selection works through existing model metadata.
- [x] Unit tests make no live Apple model calls.
- [x] Standalone live text, structured-output, and full DAR workflow checks pass on the designated eligible Mac; the separate pytest-native SDK result is recorded.
- [x] Live tests skip cleanly with an actionable reason when Apple prerequisites
      are unavailable.
- [x] Focused tests, full tests, lint, package build, and import checks pass.
- [x] Documentation covers installation, prerequisites, strict local usage,
      capabilities, limitations, and diagnostics.

### A2 validation checklist

- [x] Apple sessions receive only wrappers for tools exposed to the active node.
- [x] Callback arguments enter the DAR-owned tool invocation coordinator.
- [x] No callback can invoke a handler or registry directly.
- [x] DAR argument validation runs before the test handler.
- [x] Approval-required tools cannot run before approval resolution.
- [x] Approved calls run once with the approved arguments.
- [x] Rejected, cancelled, expired, and unresolved approvals never invoke the
      handler.
- [x] DAR lifecycle hooks, trace events, state storage, sensitive-field
      redaction, and model-facing output behavior are preserved.
- [x] Tool iteration and completion limits are enforced before further handler
      invocation.
- [x] Unsupported Apple argument-schema translations fail before generation.
- [x] Fake-backed unit tests and live Apple callback tests cover the complete
      coordinator path.

### A3 validation checklist

- [ ] Apple profile configuration does not accept or persist HTTP transport,
      credential, model-path, or downloaded-model fields.
- [ ] Unsupported host/platform/SDK/model states fail before MCP initialization
      or any handler dispatch.
- [ ] A saved Apple-backed workflow constructs the canonical async adapter and
      retains exact profile-registration binding and strict adapter coverage;
      an unmatched package model fails before input consumption or dispatch.
- [ ] Existing HTTP-backed host profiles retain their current adapter and
      behavior.
- [ ] Apple-backed saved workflows preserve reviewed MCP binding, coordinator
      ingress, approval, lifecycle, state, trace redaction, result shaping, and
      callback budgets.
- [ ] Fake tests cover all host profile and runner paths; eligible-Mac live
      tests prove direct Apple-backed saved-workflow execution.
- [ ] The Fastmail read-only acceptance records only redacted evidence and
      preflights the redacted `search_email` surface digest for Apple-schema
      admissibility, then succeeds through the Apple-backed saved workflow.

## Resolved Decisions

1. DAR will implement the Apple flow internally and depend directly on the
   optional Apple SDK; `fmx` is reference evidence only.
2. The compatibility surface is an in-process async Responses-compatible client,
   not an HTTP server.
3. The existing `AsyncOpenAIClientAdapter` remains the executor-facing adapter.
4. The system Apple model is a distinct provider and does not extend the MLX
   model-asset adapter.
5. The first release supports final text and explicit JSON Schema output only.
6. Apple tool use is an explicit A2 release; public provider streaming,
   multimodal input, persistent Apple sessions, PCC, and HTTP serving remain
   deferred.
7. The first release creates one Apple SDK session per model request.
8. Unit tests remain fake-backed and live-model-free. Separate live integration and end-to-end checks exercise the real on-device
   model only when explicitly enabled; standalone Python execution is the
   authoritative live evidence because pytest-native Apple SDK execution can
   fail with opaque status 255 despite a successful availability preflight.
9. Unknown or opaque SDK failures are translated but not automatically classified
   as retryable.
10. The provider advertises only capabilities implemented through DAR, even when
    the Apple SDK itself exposes more.
11. Apple tool callbacks are provider ingress points and must pass through a
    DAR-owned tool invocation coordinator before any handler can run.
12. A2 approval-required callbacks may dispatch once only when a synchronous
    trusted decision approves the exact normalized invocation. Denied,
    cancelled, and expired decisions do not dispatch; unresolved approval
    returns a provider-aware DAR interruption before any handler runs. A2 does
    not wait for durable approval resume inside the Apple callback, bypass
    approval, or disguise an interruption as an ordinary direct tool invocation.

## Open Questions

No implementation-blocking product questions remain for the A1 specification
boundary. Exact class names, optional dependency version constraints, request
renderer structure, error subtype reuse, and test-file placement belong to the
technical plan and must not widen the approved first-release scope.

The approved A2 plan selects provider-aware interruption before handler
invocation. Durable cross-process approval resume remains a later feature; direct
callback invocation of the handler or registry is not an allowed alternative.
