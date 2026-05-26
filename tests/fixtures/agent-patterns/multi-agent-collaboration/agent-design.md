# Hello World Multi Agent Collaboration

## Purpose

This is a small test-resource agent design for the `multi-agent-collaboration`
pattern. It exists so `dynamic-agent-runner` can eventually exercise every
documented agent pattern with a portable generated runtime package.

## Runtime Package

- Runtime manifest: `agent-runtime.yaml`
- Mermaid graph: `agent-graph.mmd`
- Packaging mode: `hybrid_bundle`

## Agent Necessity

- Decision: `agent warranted` for fixture coverage.
- Simpler alternative: a deterministic hello-world function would be simpler in
production, but would not cover the `multi-agent-collaboration` runtime package
shape.

## Design Summary

- Primary agent pattern: `multi-agent-collaboration`
- LLM workflow: `parallel role fanout and synthesis`
- Coordination pattern: `scatter-gather`
- Autonomy level: `assistive`
- Runtime target: `in-process test fixture`

## Safety and Evaluation

- No live external mutations.
- No credentials or personal data.
- Unit tests should load the manifest and graph without live OpenAI calls.
