# Hello World Tool Based Function Calling Agent

## Purpose

This is a small test-resource agent design for the `tool-based-function-calling-
agent` pattern. It exists so `dynamic-agent-runner` can eventually exercise
every documented agent pattern with a portable generated runtime package.

## Runtime Package

- Runtime manifest: `agent-runtime.yaml`
- Mermaid graph: `agent-graph.mmd`
- Packaging mode: `hybrid_bundle`

## Agent Necessity

- Decision: `agent warranted` for fixture coverage.
- Simpler alternative: a deterministic hello-world function would be simpler in
production, but would not cover the `tool-based-function-calling-agent` runtime
package shape.

## Design Summary

- Primary agent pattern: `tool-based-function-calling-agent`
- LLM workflow: `ReAct-style tool use`
- Coordination pattern: `none`
- Autonomy level: `supervised agent`
- Runtime target: `in-process test fixture`

## Safety and Evaluation

- No live external mutations.
- No credentials or personal data.
- Unit tests should load the manifest and graph without live OpenAI calls.
