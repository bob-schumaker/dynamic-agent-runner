<!-- markdownlint-disable MD013 -->
# DAR External Adapter Protocol Implementation Plan

Status: approved; implementation not started

## Authority and scope

This plan implements the approved
[`spec.md`](spec.md). The first release is one optional, receiver-approved
Chrome Built-in AI/Gemini Nano adapter using the exported
`DARExternalAdapterProtocol`.

In scope:

- exported protocol, descriptor, health, request-context, and error types
- receiver-controlled local adapter install/remove/list lifecycle
- exact adapter resolution and fail-closed admission
- integration with the existing `ModelAdapter` and executor seams
- fake Chrome bridge conformance tests
- top-level exports and focused documentation

Out of scope:

- Chrome automation or direct model-file access
- multimodal output, streaming, persistent sessions, or native callbacks
- a second public provider framework or per-node binding map
- rewrites of OpenAI, LiteLLM, AFM, MLX, llama.cpp, or existing local runners
- live Chrome or network-backed unit tests

## Success criteria

The first slice is complete when:

1. A valid receiver-approved adapter can be imported, described, health-checked,
   selected by the receiver through an exact model identity tuple, projected
   into the existing `model_adapter` path, and invoked.
2. Sync adapters execute through DAR's bounded worker executor when called from
   an async workflow; async adapters are awaited; an invalid return shape fails
   closed.
3. Unsupported capability, model, content, timeout, cancellation, malformed
   response, removal, and replay cases produce package-owned errors before or
   during dispatch as specified.
4. Model-returned tool calls re-enter the existing tool coordinator and the
   external adapter never receives a handler or approval object.
5. Existing OpenAI/LiteLLM tests and behavior remain unchanged when no external
   adapter is supplied.
6. The optional Chrome bridge passes deterministic fake-backed conformance
   tests and fails closed when readiness or its authenticated bridge session is
   unavailable.
7. A selected external adapter prevents default-provider construction or
   dispatch for every mismatched workflow model alias.

## Technical approach

### 1. Establish the public contract with RED tests

Add `tests/test_external_adapter_protocol.py` first. Tests should initially
fail and cover:

- protocol and top-level import shape
- descriptor validation, text-only v1 capabilities, and digest mismatch
- health states and exact model identity resolution
- request-context redaction and cancellation
- sync/async dispatch behavior and invalid awaitable returns
- response normalization, JSON Schema validation, and `raw=None`
- tool-call re-entry without handler access
- package-owned error translation

Use only in-memory fake adapters, fake health states, and fake bridge objects.
Do not add a live browser, sidecar, or external network dependency.

### 2. Add package-owned protocol types, validation, and the executor façade

Create `src/dynamic_agent_runner/external_adapter.py` with:

- `DARExternalAdapterProtocol`
- `ExternalModelAdapterDescriptor`
- `ExternalModelAdapterHealth`
- `DARExternalRequestContext` and `CancellationHandle`
- descriptor/digest validation helpers
- package-owned adapter and model-execution errors
- a DAR-owned `ModelAdapter` façade whose `models` contains exactly the
  descriptor's `model_alias` and whose calls go through descriptor, health,
  context, response, and error validation
- a shared DAR-owned bounded external-adapter dispatcher used by both registry
  façades and direct BYOM façades

Keep this module transport-neutral and independent of Chrome. Reuse existing
`OpenAIModelRequest`, `ModelResponse`, and `ModelToolCall` types rather than
creating parallel request/response classes. Validate public boundaries before
calling adapter code; do not leak vendor exceptions, prompts, credentials, or
raw transport objects.

The existing executor selects adapters through `.models` and
`create_response`; it must not receive a raw protocol object and silently
treat it as a wildcard. The façade is the only object passed to the existing
`model_adapter` path. It derives local/capability metadata from the descriptor
and never supplies OpenAI fallback for its selected alias.

At the start of `_normalize_model_adapters`, normalize every supplied adapter
element—including elements inside sequences—by detecting an object implementing
the approved external protocol, validating its protocol/version, and wrapping
it in the façade before legacy adapter normalization. This is the public BYOM
path: a caller can pass the exported protocol object, alone or in a sequence,
through the existing `model_adapter` argument without importing a private
façade class. Malformed or duplicate external entries fail deterministically;
mixed external/legacy sequences retain the external alias and no-fallback
rules.

### 3. Implement the receiver-owned adapter registry

Add the minimal registry/install boundary in
`src/dynamic_agent_runner/workflow_host/external_adapter_registry.py`.
Keep `workflow_host/host.py` as a composition caller rather than adding a
second large control plane. The registry must:

- accept only an explicitly approved local package or installed plugin ID
- validate static metadata before importing the factory
- validate the live descriptor and contract digest after import
- reject duplicate IDs, protocol mismatches, and unsupported capabilities
- resolve the exact tuple
  `(adapter_id, contract_digest, model_alias, canonical_model_id)`
- check health immediately before dispatch
- reject pending calls after removal while allowing already-dispatched work to
  finish until its deadline
- retain no secrets and never delete Chrome profiles, model assets, or caches

Persist only a receiver-owned manifest/receipt containing adapter ID, protocol
version, descriptor digest, artifact digest or trusted signer/origin, and
factory reference. It must also contain an immutable `artifact_locator` and
distribution name/version identifying the exact bytes to revalidate. Store it
under the receiver's DAR state root with owner-only permissions and atomic
replace. On a new process, validate the receipt, locator, exact artifact bytes,
and trust metadata before importing the factory, then validate the live
descriptor; disable any changed, missing, or tampered registration. Installation
failure rolls back the receipt. Removal unregisters future calls and removes
only the registration record.

Do not add a generic marketplace, arbitrary URL installer, or second execution
protocol. The registry wraps the one exported adapter protocol.

The receiver must not auto-scan installed adapters. A receiver-owned host
selects one installed adapter explicitly by ID, derives the descriptor digest,
model alias, and canonical model ID to form the exact tuple, creates the
façade, and passes that façade through the existing `model_adapter` surface.
The adapter ID is not a new public workflow/API argument. A duplicate alias
without an explicit receiver selection fails closed.

### 4. Integrate with the existing executor seam

Integrate with the existing `ModelAdapter` compatibility path in:

- `src/dynamic_agent_runner/executor.py`
- `src/dynamic_agent_runner/workflow_host/external_adapter_registry.py`

The integration should preserve the current `model_adapter` argument and model
coverage behavior. External adapters are adapted to the existing request build,
tracing, cancellation, normalization, and tool-coordination flow; do not add a
Chrome-specific executor branch.

The public API and `WorkflowExecutionContext` remain unchanged. The
receiver-owned host selects an adapter ID internally, creates the façade, and
supplies it as the existing `model_adapter` value. The façade binds only to its
one descriptor alias. Once an external adapter is selected, every workflow
model node must request that alias; a different alias fails before any default
OpenAI adapter is constructed or dispatched, regardless of augmented coverage.
If a node omits its model alias, the receiver resolves it to the selected
external descriptor's sole alias; ambiguous or multiple external selections
fail closed.

Before fallback selection, derive required features from the external
descriptor and the node request. Reject unsupported structured output,
tool-calling, model semantics, or limits before dispatch; do not let the
ordinary selector choose OpenAI merely because the façade lacks legacy
capability fields.

Add a DAR-owned bounded external-adapter dispatcher shared by registry-created
and direct-injection façades. Admission uses a bounded semaphore and the
request deadline; cancellation releases queued work without exposing executor
state to the adapter. Async adapters remain on the event loop. Do not claim
that the current loop-default `asyncio.to_thread` executor is bounded.

The façade rejects a sync invocation of an async-only descriptor before calling
the adapter. Internal dispatch tokens are single-use and reject forged,
expired, revoked, mismatched, or replayed calls; they are not exported as a
public lease protocol.

Inject only `DARExternalRequestContext`; keep prior internal tool and executor
context in DAR-private state.

Add focused RED/GREEN tests in `tests/test_executor.py` and the nearest
existing import/CLI test modules for:

- direct `model_adapter` injection
- exact model selection and strict/augmented coverage compatibility
- sync adapter execution from async workflow
- cancellation, timeout, removal, and replay behavior
- forged, expired, revoked, adapter/digest/model/mode-mismatched, and consumed
  internal dispatch-token rejection before external dispatch
- canonical digest vectors, duplicate/unknown descriptor fields, finite-domain
  rejection, immutable descriptor copies, and deterministic capability/local
  projection
- receiver-private adapter selection, alias collision rejection, and no
  fallback for the selected external alias
- raw BYOM protocol injection is wrapped before `_normalize_model_adapters`
- singleton, sequence-contained, and mixed external/legacy raw protocol
  normalization cases
- omitted-model resolution to the sole external alias and ambiguous omission
  rejection
- descriptor-driven structured-output/tool capability admission under both
  strict and augmented policies, with no OpenAI fallback
- a multi-node workflow with a mismatched model alias fails before external
  OpenAI construction or dispatch under either coverage policy
- bounded-worker saturation, deadline, and cancellation behavior
- private-context isolation: the adapter cannot reach the tool registry or
  approval state
- unchanged OpenAI/LiteLLM adapter paths

### 5. Add receiver CLI lifecycle commands

Extend `src/dynamic_agent_runner/cli.py` with the approved lifecycle commands:

```text
dynamic-agent-runner adapter install <approved-local-plugin>
dynamic-agent-runner adapter remove <adapter-id>
dynamic-agent-runner adapter list
```

Adapter commands accept a receiver-owned `--state-root`. Workflow execution
does not gain a new public adapter-ID flag; receiver-owned composition passes a
validated façade through the existing `model_adapter` argument.

Keep normal workflow execution behavior unchanged. CLI tests must cover parser
dispatch, successful install/list/remove, duplicate or invalid package failure,
and redacted error output. Registry state must be reloadable by a new process
without importing an unvalidated factory; tests must cover deleted, moved,
replaced, and factory-reference-mismatch artifacts.

### 6. Export and document the public seam

Update `src/dynamic_agent_runner/__init__.py` with the approved public types and
errors. Update `README.md` with only the minimum usage documentation needed to
explain:

- receiver-approved installation
- direct BYOM injection through `model_adapter`
- text-only v1 capability limits
- fail-closed behavior and the tool boundary

Do not document future transport or migration behavior as implemented.

### 7. Implement the optional Chrome bridge separately

The Chrome-specific package/entrypoint depends only on the exported protocol
and its browser bridge. It must:

- call supported Chrome Built-in AI JavaScript APIs
- report readiness/download state through `health()`
- translate text and supported structured results
- advertise no streaming, native callbacks, or handler callbacks
- authenticate the extension/origin session and bind requests to the DAR call
  context
- reject unavailable, disconnected, oversized, expired, or replayed requests

The DAR package must not scan for Chrome or import Chrome-specific code during
ordinary execution.

## Dependency order and checkpoints

1. Contract RED tests and protocol types.
2. Registry validation and exact resolution.
3. Executor/API integration and fake adapter execution.
4. CLI lifecycle and process reload checks.
5. Top-level exports and documentation.
6. Optional Chrome bridge and fake bridge conformance.
7. Full validation and artifact consistency review.

Each checkpoint must leave a working slice and record the focused test command
and result before the next slice begins.

## Alternatives rejected

- A new provider/executor framework: duplicates the existing `ModelAdapter` seam.
- A per-workflow-node binding map: unnecessary until multiple external models
  can run in one workflow.
- A generic plugin marketplace or URL installer: expands trust and lifecycle
  scope without helping the Chrome first slice.
- Routing ordinary OpenAI/LiteLLM calls through the external protocol: adds a
  hop without a caller need.
- A Chrome-specific executor branch: leaks browser lifecycle into generic DAR.

## Risk controls

- **Untrusted plugin code:** receiver approval and metadata validation occur
  before import; invalid packages fail closed.
- **Tool authority escape:** adapters receive model-visible tool descriptors and
  a redacted request context, never a registry or approval object.
- **Async blocking:** sync calls use the new bounded external-adapter worker
  pool; saturation and deadline behavior are tested.
- **Runtime drift:** descriptor changes require reinstall and digest validation.
- **Bridge failure:** health, deadline, cancellation, disconnect, and replay
  failures become package-owned errors.
- **Regression:** all existing OpenAI/LiteLLM and adapter coverage tests remain
  required gates.

## Verification commands

During implementation:

```text
poetry run pytest tests/test_external_adapter_protocol.py -q
poetry run pytest tests/test_executor.py tests/test_cli.py -q
poetry run ruff check src tests
```

Completion gate:

```text
poetry run pytest -q
poetry run ruff check src tests
poetry check
poetry build
git diff --check
```

No live Chrome, Ollama, Apple, or remote-provider call is part of the unit
test gate. Any live browser check is a separately authorized integration gate.

## Traceability

| Approved spec area | Plan section | Primary verification |
| --- | --- | --- |
| Public contract and text-only v1 | 1–2 | `test_external_adapter_protocol.py` |
| Exact admission and fail-closed behavior | 3–4 | registry/executor fake tests |
| Receiver install/remove/list | 3, 5 | CLI and reload tests |
| BYOM export and existing adapter compatibility | 4, 6 | import and OpenAI/LiteLLM tests |
| Chrome bridge boundary | 7 | fake bridge conformance tests |
| Tool-handler isolation | 2, 4, 7 | tool-boundary tests |

## Readiness

The approved spec is the source of truth for behavior. This plan is ready to
execute under its stated gates. Implementation must use TDD, update this plan
only for technical sequencing changes, and request new approval for any v1
scope or contract change.
