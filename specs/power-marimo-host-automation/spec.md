# Power-Marimo Dynamic Workflow Client Specification

## Metadata

- Feature slug: `power-marimo-host-automation`
- Mode: `light`
- Artifact type: downstream-client alignment specification
- Status: downstream client evaluated; no DAR implementation is authorized
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Related DAR artifacts:
  - `tests/fixtures/power-marimo/agent-runtime.yaml`
  - `tests/test_power_marimo_fixture.py`
  - `specs/dynamic-agent-runner/references/power-marimo-agent-support-analysis.md`
  - `specs/async-session-memory-pipeline/power-marimo-host-integration.md`
  - `specs/dynamic-agent-runner/spec.md`
- Downstream evidence from `../power-marimo`:
  - `src/power_marimo/tools/service.py`
  - `src/power_marimo/tools/runtime_registry.py`
  - `src/power_marimo/notebook/chat_workspace.py`
  - `src/power_marimo/runtime/llm_power_experiment.py`
  - `src/power_marimo/notebook/marimo_server.py`
  - `tests/test_marimo_dynamic_agent_e2e.py`
  - `tests/test_qext_marimo_chat_workspace.py`
  - `tests/test_t27_app_llm_workflow.py`
  - `specs/README.md`

## Objective

Record the correct boundary between `dynamic-agent-runner` and the downstream
`power-marimo` application after evaluating the current sibling repository.

`dynamic-agent-runner` only owns generic dynamic-agent workflow loading,
validation, execution, model/tool adapter boundaries, tracing, runtime policy,
and fake-testable package behavior. It does not own Marimo, Qt, hosted UI
lifecycle, desktop automation, Power-Marimo domain semantics, SDK-session state,
or application safety policy.

## Boundary Decision

Power-Marimo is a downstream client of DAR, not a DAR feature surface. The
downstream application may build Marimo, Qt, SDK, project-data, AppleScript, or
other host-specific capabilities, but those capabilities must enter DAR only as:

1. generated or inline runtime manifests
2. caller-provided tool registries
3. caller-provided model adapters
4. caller-provided execution contexts, trace sinks, and lifecycle hooks
5. ordinary prompts, runtime overrides, and session/history inputs

DAR must not add Power-Marimo-specific modules, dependencies, tool packs,
notebook helpers, Qt helpers, server discovery, process lifecycle management,
desktop automation, SDK adapters, or live app validation.

## Current Downstream State

The earlier DAR-side spec described Power-Marimo host automation as mostly
future work. That is no longer an accurate description of the sibling repo.
`../power-marimo` now owns a concrete host-side integration:

- `ToolService` registers namespaced application tools, including notebook,
  domain, project-data, and surface-update tools.
- `runtime_registry.py` adapts that service into a DAR-compatible tool registry
  from manifest-facing tool IDs and aliases.
- hosted notebook chat builds a runtime manifest, selects a model adapter,
  performs capability preflight, captures redacted traces, and calls
  `execute_workflow_async(...)`.
- desktop LLM workflow code builds a bounded runtime manifest and calls
  `execute_workflow(...)` with the app-owned tool service.
- live or app-specific Marimo/QExt/AppleScript validation lives in
  `../power-marimo`, gated by that repository's environment variables and test
  policy.

This proves the intended architecture: downstream clients own host behavior and
DAR remains a generic execution engine.

## DAR-Owned Scope

This feature records only the DAR-facing contract required by downstream clients
such as Power-Marimo:

1. load and validate runtime packages or inline workflow definitions
2. execute bounded dynamic-agent workflows
3. call tools supplied by a caller-owned registry
4. preserve tool provenance and manifest-facing tool IDs
5. expose runtime policy controls such as retries, token budgeting,
   tool-call completion, model adapter coverage, and prepared model input
6. emit redacted trace events and capability/status reports
7. support fake-tool validation in this repository without live downstream
   applications

## Downstream-Owned Scope

Power-Marimo, or any other client, owns all host-specific concerns:

- Marimo server discovery, startup, shutdown, session attachment,
  authentication, and notebook mutation
- Qt, PySide, QExt, WebEngine, widget lifecycle, and desktop UI automation
- app-specific AppleScript commands and packaged app smoke paths
- Power-Tetris SDK session construction, persistence, restore, analysis
  execution, and result normalization
- project file state, project-data tools, dirty-state integration, and UI
  rendering
- application approval policy, safety policy, redaction policy, and live
  integration tests
- packaged prompt/skill assets used by the app

These may be exposed to DAR only through host-provided tool registries, manifests,
model adapters, and execution context collaborators.

## Functional Requirements

### FR-1: Keep DAR host-agnostic

DAR must not import, depend on, or special-case Power-Marimo, Marimo, Qt, PySide,
QExt, AppleScript, Power-Tetris SDK, or related desktop/runtime packages.

Acceptance criteria:

- DAR unit tests do not import or launch downstream applications.
- DAR package metadata does not add downstream host dependencies.
- Runtime behavior remains expressed through generic workflow, model, tool,
  trace, capability, and policy interfaces.

### FR-2: Accept host-provided tool registries

Downstream clients must be able to adapt their local tool services into DAR's
generic `ToolRegistry` contract.

Acceptance criteria:

- DAR validates missing manifest tool references against the supplied registry.
- Manifest-facing tool IDs can remain aliases resolved by the downstream host.
- DAR does not inspect host tool internals beyond the generic registered-tool
  contract.
- Tool results are treated as caller-owned payloads and surfaced through normal
  workflow state, trace redaction, and final-result handling.

### FR-3: Run bounded dynamic-agent workflows only

DAR's role is to execute a bounded workflow, not to become a persistent host
automation agent.

Acceptance criteria:

- Workflow bounds come from existing runtime policy fields such as `max_steps`,
  `max_iterations`, retry policy, token budget, and tool-call completion.
- Long-running host lifecycle, UI readiness, live server state, and durable app
  session state remain outside DAR.
- Reusable `WorkflowExecutionContext`, `AgentSession`, or host-managed continuity
  may be used only as generic runner surfaces.

### FR-4: Keep client safety policy outside DAR

DAR may enforce its generic approval, guardrail, sandbox, and tracing boundaries,
but it must not define Power-Marimo-specific safety policy.

Acceptance criteria:

- Notebook edits, package installation, UI mutation, shell execution, project
  persistence, and SDK operations are downstream tool semantics.
- If a downstream operation requires approval, the host models that through its
  tool registry, manifest, or DAR's generic approval surfaces.
- DAR docs and specs do not claim ownership over host permission policy.

### FR-5: Preserve fake-only core validation

DAR's own validation for Power-Marimo-shaped packages must stay fixture-based.

Acceptance criteria:

- `tests/fixtures/power-marimo/agent-runtime.yaml` remains a placeholder-safe
  package fixture.
- `tests/test_power_marimo_fixture.py` validates generic package loading and fake
  tool execution only.
- Live Marimo, Qt, SDK, AppleScript, or packaged-app tests live in
  `../power-marimo`, not in DAR.

### FR-6: Document downstream evidence without copying ownership

DAR specs may cite downstream files as evidence for integration shape, but must
not duplicate downstream specs or make their implementation state a DAR
maintenance obligation.

Acceptance criteria:

- This spec records the boundary and observed downstream integration shape.
- Future changes to Power-Marimo live behavior are routed to Power-Marimo specs.
- DAR changes are made only when a generic runner contract is missing or
  incorrect.

## Non-Goals

- No Marimo support layer in DAR.
- No Qt, PySide, QExt, WebEngine, or desktop automation support in DAR.
- No Power-Marimo, Power-Tetris SDK, project-data, AppleScript, or app-specific
  tool pack in DAR.
- No runner-owned live server discovery, startup, shutdown, auth, browser, or UI
  lifecycle.
- No live downstream application tests in DAR unit or integration suites.
- No durable downstream app memory beyond generic runner/session surfaces.
- No special runtime behavior keyed to Power-Marimo package IDs, tool names, or
  manifests.

## Validation Checklist

- [x] DAR has a placeholder-safe Power-Marimo fixture and fake-tool test path.
- [x] `../power-marimo` has a caller-owned tool-service adapter into DAR.
- [x] `../power-marimo` owns live Marimo/QExt/app validation surfaces.
- [x] DAR remains dependency-free with respect to Marimo, Qt, and Power-Marimo.
- [x] The intended boundary is host-provided tools plus bounded workflow
      execution.
- [ ] Future DAR work changes this area only for generic runner contracts, not
      client-specific automation.
