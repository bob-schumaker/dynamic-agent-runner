# Power-Marimo Analysis

I examined `../power-marimo` read-only and inferred the agent support it will
need for its AI-assisted Marimo notebook POC.

## What `power-marimo` is trying to build

`power-marimo` is scaffold-stage, but its roadmap is concrete enough to infer
the likely agent shape:

- Primary user: power engineers working with data center SLDs.
- First goal: AI-assisted Marimo notebook POC using `power-tetris-sdk`.
- First experiment:
  - choose a room
  - load its SLD
  - retrieve real-time room data
  - analyze each power-data entry over time
  - produce `RoomPowerResultsTable`
  - plot total power over a default ten-minute period
- AI-assistance mechanism: copied `marimo-pair` skill at
  `skills/marimo-pair/`.
- Follow-on: PyQt/PySide app embedding Marimo through
  `roschumalib.pyside.marimo_widget`.

Observed repo state:

- Branch: `develop`
- Local changes already present in `power-marimo`:
  - `M poetry.lock`
  - `M pyproject.toml`
  - `?? memory-bank/notes/`
- `pyproject.toml` already depends on `dynamic-agent-runner = "^0.1.1"`.

## Inferred agent support needed

### 1. Notebook-pairing agent support

`power-marimo` needs an agent that can operate against a running Marimo session,
using `marimo-pair` semantics:

- discover running Marimo servers
- execute scratchpad code in the active kernel
- inspect existing cells and variables
- create, edit, and run cells through `marimo._code_mode`
- avoid direct file edits to running notebook `.py` files
- preserve notebook dataflow semantics and avoid duplicate public definitions
- ask before destructive cell deletion or package installation when intent is
  unclear

This is best modeled as a **tool-based function-calling agent** with strong
notebook-specific tool policy.

### 2. Domain experiment orchestration support

The agent will need to guide or generate a sequence like:

1. select room
2. load associated SLD JSON through `power-tetris-sdk`
3. retrieve real-time room data
4. run per-entry analysis through TETRIS/power-analysis APIs
5. produce `RoomPowerResultsTable`
6. plot total power over time
7. summarize results for a power engineer

This is partly deterministic workflow orchestration and partly assistive
interpretation. It does **not** need high autonomy initially.

Recommended pattern: **workflow orchestration agent** compiled down to primitive
`llm_step`, `tool_use_step`, and `decision_step` nodes.

### 3. Marimo safety and mutation guardrails

The `marimo-pair` skill has several important guardrails that should become
runtime policy or tool policy:

- discover before starting a server
- prefer running Marimo with browser visible unless user asks headless
- do not expose tokens in process listings; prefer `MARIMO_TOKEN`
- use `ctx.packages.add()` instead of `pip` or `uv` from cells
- use `code_mode` for notebook mutations
- never `Edit` or `Write` the `.py` notebook file while a session is running
- treat deletions as destructive
- confirm package installs when not obvious from context

This maps well to the new grouped manifest shape:

- `runtime.execution_policy` for approval requirements and forbidden actions
- `metadata` for notebook phases and pattern labels
- `extensions` later for Marimo-session integration if we formalize it

### 4. Tool provenance and source separation

`power-marimo` will likely need tools from several origins:

- built-in or local workspace tools
- Marimo session tools/scripts from `skills/marimo-pair/scripts/`
- domain tools/adapters for `power-tetris-sdk`, SLD loading, and TETRIS analysis
- future PyQt/Marimo widget tools

So `ToolOrigin` or `ToolSource` becomes important before this grows past a POC.

### 5. Prepare-model-input/context support

The agent will need to build prompts from:

- user goal
- current notebook state or cell graph
- SLD metadata or summary
- room/time-series data summaries
- tool results
- Marimo gotchas and notebook-improvement rules

This strongly supports the planned `PreparedModelInput` /
`prepare_model_input(...)` seam before adding richer context-management or
notebook-state injection.

## How well `dynamic-agent-runner` can implement this today

### Can implement now: partial POC support

Current `dynamic-agent-runner` can likely support a narrow prototype if the
runtime package uses the existing flat manifest shape currently implemented in
code, or if we first do the grouped-manifest simplification slice.

Current implemented strengths:

- Loads runtime artifacts and Mermaid graph.
- Executes primitive `llm_step`, `tool_use_step`, and `decision_step` workflows.
- Supports async-first execution and sync wrappers.
- Supports callable registry and opt-in built-in read-only local workspace tools.
- Supports prompt/skill behavior overrides.
- Supports output contracts, route validation, tracing, retries, token
  budgeting, hooks, and prompt-cache observation.
- Can call user-registered Python tools, so wrapper tools around Marimo scripts
  or domain APIs are feasible.

A minimal viable `power-marimo` agent today could:

- use LLM steps to plan notebook cells and summarize results
- use registered tools to call Marimo discovery/execution scripts
- use registered domain tools to call `power-tetris-sdk` adapters
- route through decisions for missing input, execution failure, or result summary

### Not ready without next simplification slice

The current `dynamic-agent-runner` implementation still appears to parse older
flat manifest fields in `RuntimeManifest`:

- `patterns_present`
- `execution_policy`
- `state`
- `participant_groups`
- `modes`
- `phases`
- `roles`
- `output_contracts` as a mapping

That does **not yet match** the newly aligned upstream grouped schema, which
uses:

- `runtime.execution_policy`
- `runtime.state`
- `metadata.patterns_present`
- `metadata.participant_groups`
- `metadata.modes`
- `metadata.phases`
- `metadata.roles`
- `extensions`
- `output_contracts` as an array

So before generating new `agent-runtime.yaml` packages for `power-marimo`, I
would implement the newly added simplification follow-up S1 first.

## Feasibility by capability

- Basic notebook workflow graph: high after grouped-manifest update. Primitive
  nodes fit well.
- Marimo server discovery and execute-code tools: medium-high. Scripts can be
  wrapped as registered tools, but approval/safety policy is needed.
- Live notebook cell mutation: medium. It is technically possible via tools, but
  high-risk without Marimo-specific guardrails.
- Domain SDK experiment orchestration: medium. It needs domain adapters and safe
  fixtures; the repo has no first-party code/tests yet.
- Rich result interpretation and summarization: high. LLM plus output contracts
  can support this.
- Interactive iterative notebook agent: medium-low today. ReAct/loop semantics
  are only future-ish; current finite workflow can do bounded steps.
- Marimo state/session memory: low-medium. It needs an explicit session/context
  model; OA8 is deferred.
- Approval pauses/resumable notebook mutations: low today. OA7 is deferred;
  hooks can abort but not durable pause/resume.
- MCP-style tool discovery for Marimo: low today. E9 is not implemented.
- PyQt embedded Marimo follow-on: low for now. It needs widget API investigation
  and GUI integration outside current runner scope.

## Recommended implementation order

1. **Finish dynamic-runner schema alignment first**
   - S1: grouped `runtime` / `metadata` / `extensions`
   - `output_contracts` as array
   - reject/report legacy flat optional root fields

2. **Add internal preparation seams**
   - S2: `ExecutionPlan` / `PreparedNode`
   - S3: `PreparedModelInput` / `prepare_model_input(...)`
   - S4: `ToolOrigin` / `ToolSource`

3. **Define a narrow `power-marimo` runtime package**
   - Assistive/supervised agent, not autonomous.
   - Fixed finite graph for the first room-power experiment.
   - Tools:
     - `discover_marimo_servers`
     - `execute_marimo_code`
     - `inspect_notebook_state`
     - `create_or_edit_cell`
     - domain adapters for room/SLD/power analysis
   - Guardrails copied from `marimo-pair` as runtime policy/tool policy.

4. **Implement `power-marimo` domain adapters/test fixtures**
   - `src/power_marimo/` does not exist yet.
   - Add deterministic wrappers and fake fixtures before asking the agent to
     drive live notebook behavior.

5. **Only then consider iterative/ReAct behavior**
   - The first POC should be a bounded finite workflow.
   - ReAct-style looping can come later if notebook exploration needs repeated
     observe-act cycles.

## Bottom line

`power-marimo` is a good fit for `dynamic-agent-runner`, but not as a free-form
autonomous notebook agent yet.

The best near-term target is a **supervised, tool-based workflow-orchestration
agent** that uses Marimo tools and domain SDK adapters in a bounded graph. We
can support much of that after the grouped-manifest simplification slice, but
durable sessions, approval pauses, MCP discovery, and rich iterative notebook
autonomy remain future work.
