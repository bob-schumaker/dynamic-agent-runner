# Power-Marimo Host Automation Specification

## Metadata

- Feature slug: `power-marimo-host-automation`
- Mode: `light`
- Artifact type: future downstream integration feature specification
- Status: proposed future feature; placeholder-safe fixture baseline exists, live
  Marimo/PyQt automation is not implemented
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Related artifacts:
  - `specs/dynamic-agent-runner/references/power-marimo-agent-support-analysis.md`
  - `tests/fixtures/power-marimo/agent-runtime.yaml`
  - `tests/test_power_marimo_fixture.py`
  - `specs/async-session-memory-pipeline/spec.md`
  - `specs/approval-interruption-resume/spec.md`
  - `specs/sandbox-workspace-runtime/spec.md`
  - `specs/skill-source-resolution/spec.md`

## Objective

Define the future runtime integration contract for a supervised Power-Marimo
workflow that can use Marimo-session tools, power-domain adapters, and optional
PyQt-widget automation without turning `dynamic-agent-runner` into an
unbounded notebook or desktop automation agent.

## Existing Baseline

The runtime-package simplification sequence produced a placeholder-safe
Power-Marimo fixture with fake-tool execution coverage. The current runtime can
load and execute bounded workflow packages, preserve tool provenance, prepare
model input, and run fake tools. It does not implement live Marimo server
discovery, notebook session control, PyQt widget automation, domain SDK adapters,
or direct manipulation of running notebooks.

Council roadmap note: keep the first Power-Marimo story host-managed. The
current runner can be useful for bounded workflow execution if Power-Marimo
supplies live tools, continuity state, and approval policy. Do not make
Power-Marimo the reason to add runner-owned durable memory, unrestricted desktop
automation, or broad sandbox behavior before the approval/sandbox/status slices
are proven.

## Scope

This feature covers:

1. Marimo-session tool contracts for server discovery, notebook inspection,
   scratchpad execution, and cell creation/editing
2. power-domain adapter contracts for room selection, SLD loading, live room data,
   TETRIS/power analysis, results-table production, and plotting
3. safety policy for notebook file edits, cell deletion, package installation,
   token handling, and approval-sensitive operations
4. prepared model input assembled from notebook state, SLD summaries, user goals,
   domain tool results, and Marimo-specific gotchas
5. optional PyQt-widget automation boundaries
6. tool provenance and downstream agent-as-tool metadata for `marimo-pair`

## Functional Requirements

### FR-1: Treat Power-Marimo as a bounded host integration

The runtime must execute a generated workflow that calls host-provided tools; it
must not own the Power-Marimo application lifecycle.

Acceptance criteria:

- The host supplies Marimo-session and domain tools through the registry.
- The workflow package references tool ids and metadata but does not embed live
  server credentials, process ids, GUI handles, or absolute notebook paths.
- If required host tools are missing, preparation or execution fails clearly
  before pretending the workflow can operate live.
- Unit validation uses fake tools and fixtures without launching Marimo or PyQt.

### FR-2: Define Marimo-session tool contracts

Marimo-session tools must expose narrow, approval-aware operations.

Acceptance criteria:

- Server discovery reports candidate sessions without leaking tokens in process
  listings, traces, or model-visible output.
- Notebook inspection returns bounded notebook state, cell metadata, and
  execution status summaries.
- Scratchpad execution runs isolated exploratory code without editing the running
  notebook file.
- Cell creation/editing uses Marimo-approved APIs such as `_code_mode` when
  available and does not write directly to the running notebook `.py` file.
- Cell deletion and package installation are approval-sensitive.

### FR-3: Define power-domain adapter contracts

Domain tools must return structured, bounded results suitable for model context.

Acceptance criteria:

- Room selection returns selected room identifiers, confidence, and reason.
- SLD loading returns a bounded summary and provenance rather than dumping large
  raw files.
- Real-time room data retrieval returns timestamped data with source metadata.
- TETRIS/power analysis returns structured intermediate and final calculations.
- `RoomPowerResultsTable` production returns a stable structured table payload.
- Total-power plotting returns plot artifact metadata or a bounded preview rather
  than large binary data in model-visible output.

### FR-4: Enforce notebook and desktop safety policy

Live automation must be supervised and approval-aware.

Acceptance criteria:

- Direct writes to a running notebook `.py` file are forbidden.
- Cell deletion, package installation, shell execution, and PyQt widget mutation
  require approval policy.
- PyQt automation, if enabled, is limited to explicitly granted widgets/actions
  and cannot perform arbitrary desktop control.
- Tool arguments and trace events redact tokens, file paths, and data fields
  according to host policy.

### FR-5: Prepare model input from bounded host state

The workflow must provide enough context without flooding prompt history.

Acceptance criteria:

- Prepared input can include user goal, notebook state summary, SLD summary,
  domain tool summaries, current result table state, plot artifact references,
  and Marimo gotchas.
- Large notebooks, SLDs, and domain data are summarized or referenced through
  bounded file/context metadata.
- Prepared input records source provenance and truncation metadata.
- Host-managed continuity may be used across repeated runner calls without
  claiming runner-owned durable memory.

### FR-6: Preserve tool provenance and agent-as-tool boundaries

The integration must keep host tools distinguishable.

Acceptance criteria:

- Tool provenance distinguishes built-in tools, Marimo-session tools, domain SDK
  adapters, runtime overrides, MCP tools, and downstream agent-as-tool sources.
- The downstream `marimo-pair` capability is represented through metadata or a
  registered tool/agent adapter without adding a new primitive node kind.
- `SKILL.md` content for `marimo-pair` is not loaded from external paths unless
  the skill-source-resolution feature authorizes that behavior.

## Non-Goals

- No free-form autonomous notebook agent.
- No runtime ownership of Marimo server startup, shutdown, authentication, or
  browser/UI lifecycle in the first version.
- No arbitrary PyQt or desktop automation.
- No direct edits to running notebook source files.
- No live Power-Marimo validation in core unit tests.
- No durable session memory beyond host-managed continuity unless a session
  feature explicitly implements it.

## Design Constraints

- Keep the dynamic-agent-runner library host-agnostic.
- Keep live app/session details in caller-owned tool adapters.
- Fail closed for missing host tools, missing approval policy, or ambiguous
  notebook/session targets.
- Keep token and credential handling out of process listings and model-visible
  output.
- Preserve fake-tool validation as the core repository test path.

## NEEDS CLARIFICATION

- Which Marimo APIs are stable enough for cell creation/editing in v1?
- Should server discovery be implemented by Power-Marimo, by caller tools, or by
  a runner-provided optional tool pack?
- What exact token-redaction policy is required for Marimo session URLs and
  process metadata?
- What operations should PyQt-widget automation support, if any?
- What approval policy applies to cell creation, cell editing, cell deletion,
  package installation, scratchpad execution, and widget mutation?
- What structured schema should `RoomPowerResultsTable` use?
- How should plot artifacts be represented: file paths, opaque host ids, images,
  or model-facing summaries?
- What host-managed continuity state should Power-Marimo pass between runner
  calls?
- How should downstream `marimo-pair` behavior be supplied: tool, agent-as-tool,
  skill source, or separate workflow package?
- What live integration tests, if any, belong outside core unit tests?

## Validation Checklist

- [ ] Missing required Marimo-session tools fail clearly.
- [ ] Fake Marimo-session tools can execute the bounded fixture workflow.
- [ ] Direct notebook file edit attempts are forbidden.
- [ ] Cell deletion and package installation require approval.
- [ ] Token-like values are redacted from traces and model-visible output.
- [ ] Domain tools return bounded structured outputs.
- [ ] Prepared input includes provenance and truncation metadata.
- [ ] PyQt automation is unavailable unless explicitly granted.
