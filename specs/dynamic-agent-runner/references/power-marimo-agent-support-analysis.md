# Power Marimo Agent Support Analysis

## Purpose

This reference records a read-only evaluation of `../power-marimo` as a first
candidate downstream consumer for `dynamic-agent-runner` after the upstream
agent-development skill adopted the grouped runtime-package manifest contract.
Use it as supporting evidence for prioritizing the next `dynamic-agent-runner`
runtime slices.

## Repository reviewed

- Repository: `../power-marimo`
- Branch observed: `develop`
- Working tree at latest check:
  - `M poetry.lock`
  - `M pyproject.toml`
  - `?? memory-bank/notes/`
- Important files reviewed:
  - `README.md`
  - `pyproject.toml`
  - downstream `power-marimo/specs/project-roadmap/spec.md` (reviewed in the
    separate downstream repository; not part of this corpus)
  - `skills/marimo-pair/SKILL.md`
  - `skills/marimo-pair/reference/gotchas.md`
  - `skills/marimo-pair/reference/notebook-improvements.md`
  - `skills/marimo-pair/reference/rich-representations.md`
  - `skills/marimo-pair/scripts/discover-servers.sh`
  - `skills/marimo-pair/scripts/execute-code.sh`
  - `memory-bank/activeContext.md`
  - `memory-bank/progress.md`

## Project intent inferred

`power-marimo` is an early-stage Python scaffold for AI-assisted power
engineering workflows with Marimo.

The first product goal is an AI-assisted Marimo notebook proof of concept using
`power-tetris-sdk`. The follow-on goal is a PyQt/PySide application that embeds
Marimo through the experimental `roschumalib.pyside.marimo_widget`.

The first proof-of-concept experiment is defined at roadmap level:

1. choose a room
2. load its associated SLD
3. retrieve real-time room data
4. analyze each power-data entry over time
5. produce a `RoomPowerResultsTable` from `tetris-analysis`
6. plot total power over the default ten-minute period

The project has selected the copied `marimo-pair` skill at `skills/marimo-pair/`
as the AI-assistance mechanism for interacting with the notebook.

## Inferred agent-support needs

### Notebook-pairing tools

A useful `power-marimo` agent needs to operate against a running Marimo session.
The `marimo-pair` skill defines the key tool contract:

- discover running Marimo servers
- execute scratchpad code in the active kernel
- inspect cells and variables
- create, edit, and run cells through `marimo._code_mode`
- use `async with cm.get_context() as ctx`
- avoid direct file writes to a running notebook `.py` file
- preserve Marimo dataflow and single-definition semantics

This is a good fit for a supervised tool-based agent with model-visible Marimo
session tools backed by registered Python or script adapters.

### Domain experiment orchestration

The first notebook agent should orchestrate a fixed, bounded experiment rather
than behave as an open-ended autonomous notebook assistant.

Likely domain tools or adapters:

- select or validate a room target
- load SLD JSON through `power-tetris-sdk`
- retrieve real-time room data
- run per-entry TETRIS/power analysis
- return or validate a `RoomPowerResultsTable`
- generate plot-ready power-over-time data

The LLM should help plan notebook cells, explain results, and choose safe next
steps, but deterministic domain adapters should own data retrieval and analysis.

### Runtime policy and guardrails

The notebook workflow has important mutation and safety constraints:

- discover before starting a Marimo server
- prefer visible browser operation unless the user asks for headless mode
- avoid exposing tokens in process listings; prefer `MARIMO_TOKEN`
- use `ctx.packages.add()` rather than `pip` or `uv` from notebook cells
- mutate notebook structure only through `code_mode`
- never use direct file edits for a running notebook `.py` file
- treat cell deletion as destructive
- confirm package installation when the dependency need is not obvious
- keep temporary file dependencies out of notebook cells

These should be represented as `runtime.execution_policy` and tool policy, not
as informal prompt-only guidance.

### Context and model-input preparation

The agent will need prompts built from multiple context sources:

- user goal and selected room
- current notebook cell graph
- Marimo server/session identity
- SLD metadata and summaries
- room power data summaries
- tool results and validation outputs
- Marimo gotchas and rich-representation guidance

This reinforces the need for a `PreparedModelInput` / `prepare_model_input(...)`
seam before adding richer context-management, session pruning, or hierarchical
prompt injection.

### Tool provenance

`power-marimo` will mix tools from multiple origins:

- built-in local workspace tools
- `marimo-pair` scripts and Marimo-session adapters
- `power-tetris-sdk` / SLD / TETRIS domain adapters
- future PyQt or Marimo-widget integration tools
- possible runtime overrides during experimentation

This makes `ToolOrigin` / `ToolSource` important before implementing MCP or
agent-as-tool sources.

## Fit with current `dynamic-agent-runner`

### What can be supported now

The existing runner can support a narrow finite workflow if the package uses the
currently implemented manifest shape or if grouped-manifest alignment is done
first.

Implemented capabilities already useful for `power-marimo` include:

- primitive `llm_step`, `tool_use_step`, and `decision_step` execution
- callable registry and registered tool invocation
- async-first execution with sync wrappers
- prompt and skill behavior overrides
- output contracts and route validation
- tracing, retries, token budgeting, lifecycle hooks, and prompt-cache
  observation
- opt-in read-only local workspace tools

A bounded prototype can therefore be implemented as a supervised graph that
plans notebook cells, calls Marimo/domain tools, validates results, and
summarizes outputs.

### What should be implemented first

The current local code still appears oriented around older flat optional
manifest fields and `output_contracts` as a mapping. The upstream skill reference
now defines grouped `runtime`, `metadata`, and `extensions` maps and
`output_contracts` as an array.

Before generating new `power-marimo` runtime packages, `dynamic-agent-runner`
should implement the grouped manifest contract and build normalized preparation
seams.

### What is not ready yet

The following are not ready as core `dynamic-agent-runner` capabilities today:

- durable approval pauses and resumable notebook mutation state
- full Marimo session memory or multi-turn session protocol
- MCP-style dynamic tool discovery for Marimo tools
- free-form ReAct notebook autonomy beyond bounded loop conventions
- PyQt/PySide embedded Marimo widget runtime support

These should remain deferred until the first bounded notebook POC validates the
workflow.

## Feasibility by capability

| Need | Current feasibility | Notes |
| --- | --- | --- |
| Basic notebook workflow graph | High after grouped-manifest update | Primitive nodes fit well. |
| Marimo server discovery and execute-code tools | Medium-high | Can wrap scripts as registered tools; needs approval and safety policy. |
| Live notebook cell mutation | Medium | Technically possible through tools, but high-risk without Marimo-specific guardrails. |
| Domain SDK experiment orchestration | Medium | Needs domain adapters and safe fixtures; `power-marimo` has no first-party code/tests yet. |
| Rich result interpretation and summarization | High | LLM steps plus output contracts fit. |
| Interactive iterative notebook agent | Medium-low | Prefer bounded finite graph first; defer broader ReAct behavior. |
| Marimo state/session memory | Low-medium | Needs explicit session/context model. |
| Approval pauses/resumable notebook mutations | Low | Deferred until approval/resume requirements exist. |
| MCP-style tool discovery for Marimo | Low | Depends on future registry-source work. |
| PyQt embedded Marimo follow-on | Low | Requires widget API investigation and GUI integration outside current runner scope. |

## Recommended next sequence for `dynamic-agent-runner`

1. Implement grouped manifest contract support:
   - parse `runtime`, `metadata`, and `extensions`
   - parse `output_contracts` as an array
   - reject or clearly report legacy flat optional root fields
2. Add internal `ExecutionPlan` / `PreparedNode` normalization.
3. Add pass-through `PreparedModelInput` / `prepare_model_input(...)` before
   expanding context-management or notebook-state prompt construction.
4. Add `ToolOrigin` / `ToolSource` provenance before MCP, Marimo-session, or
   agent-as-tool registry sources.
5. Define a narrow `power-marimo` runtime package as a supervised, bounded
   workflow-orchestration agent.
6. Implement `power-marimo` domain adapters and fixtures before live notebook
   automation.
7. Consider ReAct-style iterative notebook behavior only after the finite POC
   proves the interaction model.

## Bottom line

`power-marimo` is a good candidate first consumer for `dynamic-agent-runner`, but
it should start as a supervised, bounded workflow-orchestration agent rather than
a free-form autonomous notebook agent.

The next `dynamic-agent-runner` work should prioritize grouped-manifest
alignment and preparation seams because those capabilities directly unblock a
safe `power-marimo` runtime package.
