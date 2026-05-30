# Power-Marimo Runtime Package Fixture

## Purpose

This is a placeholder-safe first-customer fixture for a supervised Power-Marimo
notebook experiment agent. It proves that `dynamic-agent-runner` can represent
the intended downstream runtime package shape without connecting to a live
Marimo server, reading real SLD data, or invoking live `power-tetris-sdk`
operations.

## Runtime Package

- Runtime manifest: `agent-runtime.yaml`
- Mermaid graph: `agent-graph.mmd`
- Packaging mode: `hybrid_bundle`
- Fixture mode: placeholder-only, fake-tool execution

## Agent Necessity

- Decision: `agent warranted` for workflow-orchestration fixture coverage.
- Simpler alternative: a deterministic script could run this placeholder flow,
  but it would not demonstrate the grouped runtime manifest, primitive node
  sequence, skill reference, and tool-policy shape needed by the downstream
  Power-Marimo notebook runtime package.

## Design Summary

- Primary agent pattern: `workflow-orchestration-agent`
- LLM workflow: supervised prompt chaining around fake tool execution
- Coordination pattern: single-orchestrator sequential workflow
- Autonomy level: `supervised agent`
- Runtime target: in-process test fixture
- Workspace boundary: placeholder fixture only; no live notebook mutation

## Agent-as-Tool Boundary

The downstream `marimo-pair` capability is represented as an agent-as-tool
operation. The `invoke_marimo_pair` node remains a primitive `tool_use_step`, but
its raw metadata records that the callable operation is backed by
`../power-marimo/skills/marimo-pair/SKILL.md` and is limited to one bounded
Marimo notebook task.

This is intentionally not a new primitive runtime node kind and not durable
handoff-style multi-agent metadata.

## Placeholder Tool Surface

The fixture defines placeholder tools for:

- `discover_marimo_servers`
- `marimo_pair_agent`
- `inspect_notebook_state`
- `run_room_power_analysis`

The fake registry used by tests returns synthetic outputs for these tools. Live
Marimo, SLD, and SDK behavior is intentionally unsupported by this fixture.

## Safety and Evaluation

- No live Marimo server access.
- No real SLD data access.
- No live `power-tetris-sdk` calls.
- No credentials or personal data.
- Unit tests load `agent-runtime.yaml`, verify `agent-graph.mmd`, and exercise
  the bounded happy path with fake tools and fake model responses.
