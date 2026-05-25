# Hello World Tool Server Or MCP Style Agent

## Purpose

This is a small test-resource agent design for the `tool-server-or-mcp-style-
agent` pattern. It exists so `dynamic-agent-runner` can eventually exercise
every documented agent pattern with a portable generated runtime package.

## Runtime Package

- Runtime manifest: `agent-runtime.yaml`
- Mermaid graph: `agent-graph.mmd`
- Packaging mode: `hybrid_bundle`

## Agent Necessity

- Decision: `agent warranted` for fixture coverage.
- Simpler alternative: a deterministic hello-world function would be simpler in
production, but would not cover the `tool-server-or-mcp-style-agent` runtime
package shape.

## Design Summary

- Primary agent pattern: `tool-server-or-mcp-style-agent`
- LLM workflow: `tool-server capability routing`
- Coordination pattern: `source-tool mediation`
- Autonomy level: `assistive`
- Runtime target: `in-process test fixture`

## Safety and Evaluation

- No live external mutations.
- No credentials or personal data.
- Unit tests should load the manifest and graph without live OpenAI calls.
