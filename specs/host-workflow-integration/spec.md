# Host Workflow Integration Specification

## Metadata

- Feature slug: `host-workflow-integration`
- Mode: `light`
- Artifact type: implemented feature specification
- Status: implemented v1 baseline; Slice H2 prepared for implementation
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Related existing specs:
  - `specs/capability-status-report/spec.md`
  - `specs/model-adapter-coverage/spec.md`
  - `specs/persistent-agent-sessions/spec.md`
  - `specs/model-event-streaming/spec.md`
  - `specs/power-marimo-host-automation/spec.md`
  - `specs/workspace-data-tool-pack/spec.md`
- Downstream evidence:
  - `/Users/roschuma/Repos/roschuma/power-marimo/src/power_marimo/tools/runtime_registry.py`
  - `/Users/roschuma/Repos/roschuma/power-marimo/src/power_marimo/notebook/chat_workspace.py`
  - `/Users/roschuma/Repos/roschuma/power-marimo/src/power_marimo/llm/model_selection.py`
  - `/Users/roschuma/Repos/roschuma/power-marimo/specs/dynamic-agent-runner-integration-refresh/tasks.md`

## Objective

Define the generic host-facing integration surfaces that downstream applications
need when they embed DAR as a workflow runtime while keeping host-specific
behavior outside this package.

This spec consolidates the reusable lessons from `../power-marimo`: host-owned
tool catalogs, model-facing aliases, inline manifest preflight, redacted
diagnostic summaries, resolved model selection, and session/context reuse
ergonomics.

## Recommendation Mapping

| Recommendation from review | Owning spec | Action |
| --- | --- | --- |
| Host tool service to `ToolRegistry` adapter | `host-workflow-integration` | New feature surface |
| Model-facing tool aliases separate from canonical host ids | `host-workflow-integration` | New feature surface |
| Capability preflight for inline/generated manifests | `host-workflow-integration`, extends `capability-status-report` | New host API over existing report contract |
| Reusable execution context/session ergonomics | `persistent-agent-sessions`, surfaced through `host-workflow-integration` | Existing session spec owns state; this spec owns host composition guidance |
| Trace diagnostics as a public summarization surface | `host-workflow-integration`, related to `model-event-streaming` | New diagnostic adapter surface |
| Model selection handoff and strict local coverage | `model-adapter-coverage`, surfaced through `host-workflow-integration` | Existing coverage policy owns execution semantics; this spec owns resolved-selection shape |
| Project/workspace data tools as a standard pattern | `workspace-data-tool-pack` | New separate tool-pack spec |

No Power-Marimo-specific Marimo, Qt, SDK, project-file, or room-power behavior is
in scope for this spec.

## Implementation Status

The v1 baseline is implemented in `src/dynamic_agent_runner/host_integration.py`
with exports from `dynamic_agent_runner`.

Completed:

- `HostToolBinding` adapts host-owned handlers into `ToolRegistry` entries.
- Canonical host ids, model-facing ids, aliases, and collision checks are
  supported.
- `ResolvedModelSelection` provides a provider-neutral execution handoff and
  redacted diagnostic payload.
- `summarize_capability_report(...)` and `summarize_trace_events(...)` provide
  bounded redacted diagnostics.
- Focused fake tests cover the helper surface.

Deferred:

- inline/generated manifest capability preflight without temporary package dirs
  is prepared as Slice H2
- capability-report extensions that expose canonical/model-facing ids in host
  tool report paths are prepared as Slice H2
- fuller public lifecycle examples for direct execution, reusable contexts, and
  `AgentSession` are prepared as Slice H2

## Prepared Implementation Slice H2

Slice H2 is the next implementation candidate for this spec while
`litellm-provider-adapter` remains paused on Python-version support. The slice
keeps the existing v1 helper surface and adds only the deferred host-facing
preflight and documentation pieces that are fake-testable today.

Prepared scope:

1. Add a public preflight helper for inline runtime manifests and already loaded
   `LoadedAgentWorkflow` objects.
2. Reuse the existing `CapabilityStatusReport` contract and package-directory
   invalid/strict behavior.
3. Surface host canonical ids, model-facing ids, and aliases in relevant tool
   capability details when the supplied registry was built from
   `HostToolBinding`.
4. Update public lifecycle guidance for direct execution, reusable
   `WorkflowExecutionContext`, and `AgentSession`.

Out of scope for H2:

- new executor or session semantics
- host-specific behavior from Power-Marimo or any other downstream application
- live model, network, GUI, or external host calls in tests
- a second capability report type
- runner-owned durable host state

Implementation artifacts:

- [`plan.md`](plan.md)
- [`tasks.md`](tasks.md)
- [`validation.md`](validation.md)

## Problem Statement

Host applications that embed DAR currently have to stitch together several
low-level surfaces:

- parse a manifest only to discover the tool definitions the host must expose
- convert a host-owned tool catalog into `RegisteredTool` instances
- map canonical host tool ids to model-safe tool names
- materialize temporary package directories to run capability preflight
- adapt trace events into bounded redacted diagnostics for application logs or UI
- pass a model adapter tuple, selected model name, and coverage mode around as
  separate fields
- decide when to use `WorkflowExecutionContext` directly versus `AgentSession`

Each piece exists in some form today, but there is no small, documented
host-integration layer. That pushes downstreams toward duplicated bridges and
ad hoc diagnostics.

## Scope

This feature covers:

1. host tool catalog adapter interfaces
2. model-facing aliases for canonical host tools
3. inline/generated manifest capability preflight
4. bounded redacted capability and trace diagnostic payloads
5. resolved model selection handoff shape
6. host guidance for choosing direct execution, reusable context, or
   `AgentSession`
7. fake-only tests that use simple host catalog and model-selection doubles

## Non-Goals

This feature must not introduce:

- host-specific tool packs
- Marimo, Qt, browser, SDK, project-file, AppleScript, or desktop behavior
- durable host storage
- live model, network, filesystem, or GUI calls in unit tests
- new executor semantics for model coverage or sessions
- replacement of `ToolRegistry`, `WorkflowExecutionContext`, `AgentSession`, or
  capability/status report contracts

## Functional Requirements

### FR-1: Adapt host-owned tools into DAR registries

Given a host owns a tool catalog, when it supplies a host-tool adapter, then DAR
should be able to create or validate a `ToolRegistry` from manifest-facing tool
definitions without inspecting host internals.

Acceptance criteria:

- Host tools remain host-owned and callable through host-provided handlers.
- DAR registers only tools referenced by the manifest or explicit allowlist.
- Missing host tools fail before execution with package-owned errors or
  capability/status diagnostics.
- Both sync and async tool invocation paths remain available through the
  existing registry protocol.

### FR-2: Separate canonical ids from model-facing ids

Given a host tool has a canonical id that is not suitable for model-facing
function names, when the host exposes it to DAR, then the host can provide a
model-facing id and aliases without changing the canonical host id.

Acceptance criteria:

- Capability/status reports both model-facing and canonical host ids when
  available.
- `to_openai_tools(...)` uses model-facing ids that satisfy provider naming
  constraints.
- Tool invocation through a model-facing id resolves to the intended host tool.
- Alias resolution is deterministic and rejects collisions.

### FR-3: Inspect inline or generated manifests without fake package dirs

Given a host generates a runtime manifest in memory, when it asks for capability
preflight, then DAR should inspect that manifest directly without requiring a
temporary `agent-runtime.yaml` package directory.

Acceptance criteria:

- A new API or overload accepts an inline manifest string or already loaded
  workflow object.
- The resulting report uses the existing `CapabilityStatusReport` contract.
- Package-directory inspection remains supported and unchanged.
- Invalid inline manifests produce the same invalid/strict behavior as package
  manifests.

### FR-4: Provide bounded diagnostic payload helpers

Given a host wants to show or log runner diagnostics, when it asks DAR to
summarize capability reports or trace events, then DAR should return bounded,
redacted, JSON-compatible payloads.

Acceptance criteria:

- Trace summaries include sequence, event type, run id, node id, and bounded
  payload summaries.
- Sensitive prompt, message, token, credential, and configured sensitive fields
  are redacted.
- Large mappings and sequences are summarized by type, keys, and lengths rather
  than dumped.
- Capability summaries include status, validity, count-by-state, and item
  summaries without raw collaborator objects.

### FR-5: Define a resolved model selection handoff shape

Given a host owns model/provider settings, when it passes model selection to DAR,
then it should have a small provider-neutral shape containing selected model
name, adapter sequence, coverage mode, and unavailable diagnostics.

Acceptance criteria:

- The shape composes with existing `model_adapter` and
  `model_adapter_coverage` arguments.
- Strict and augmented semantics remain owned by `model-adapter-coverage`.
- The shape can represent unavailable model configuration without constructing
  an adapter.
- It does not store API keys, local cache paths, adapter objects, or provider
  secrets in durable host settings.

### FR-6: Clarify host execution lifecycle choices

Given a host repeatedly executes a workflow, when it needs continuity, then DAR
docs/API guidance should distinguish:

- direct `execute_workflow_async(...)` for one bounded run
- reusable `WorkflowExecutionContext` for stable collaborators
- `AgentSession` for cross-prompt state, current-state retrieval, and restart

Acceptance criteria:

- Hosts do not need to build ad hoc context caches for ordinary session reuse.
- `AgentSession` remains the recommended surface when prompt history or
  restartable session state is required.
- Direct execution remains available for stateless generated workflows.

## Implementation Planning Notes

- Start with small helper functions or adapters rather than a new runtime layer.
- Keep source types protocol-based and fakeable.
- Extend capability/status inspection rather than adding a second report type.
- Keep diagnostic summaries read-only and lossy by design.
- Do not move model-selection policy into DAR; accept a resolved selection from
  hosts that own provider settings.

## TDD Implementation Tasks

Completed v1 slices:

1. RED/GREEN: host catalog adapter tests and registry creation from host
   bindings.
2. RED/GREEN: alias/collision tests and canonical id plus model-facing id
   mapping.
3. RED/GREEN: diagnostic summary tests and redacted bounded trace/capability
   payload helpers.
4. RED/GREEN: resolved model selection tests and execution-entrypoint kwargs.

Deferred slices:

1. Slice H2: inline capability preflight tests; inspect manifest string or
   loaded workflow without temporary package dirs.
2. Slice H2: capability report host id details for host-bound tools.
3. Slice H2: docs/API examples for direct execution, reusable context, and
   `AgentSession`.

## Validation Checklist

Implemented v1 validation:

```bash
poetry run pytest tests/test_host_integration.py -q
poetry run pytest tests/test_import.py -q
```

Future deferred tests must use fake host catalogs, fake model adapters, fake
trace events, and no live host application.
