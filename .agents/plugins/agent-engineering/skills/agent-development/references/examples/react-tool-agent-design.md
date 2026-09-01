---
title: ReAct Tool Agent Design Example
reference_type: example
applies_to: agent-development
runtime_manifest: react-tool-agent-runtime.yaml
runtime_graph: react-tool-agent-graph.mmd
---

## ReAct Tool Agent Design Example

### Decision

Agent warranted: yes, when the task needs iterative read-only evidence gathering
and the model must decide whether another tool call is useful before answering.

Simpler alternative: use a fixed retrieval-then-answer workflow when every run
should always call the same retrieval tool exactly once.

### Runtime

- Runtime target: conceptual external runtime
- Runtime surface: stateful session runtime
- Workspace boundary: no workspace mutation; read-only tool access
- Autonomy level: `supervised agent`
- Execution limits: bounded by `max_iterations`, `max_steps`, and timeout
- Completion: model routes to `final`, then a final response node answers from
  model-safe workflow state

### Pattern

- Primary agent pattern: tool-based function-calling agent
- LLM workflow: ReAct-style observe-think-act loop
- Coordination pattern: none

The executable route shape is:

```text
reason -> route_action
route_action -> search_knowledge_step when route == tool
route_action -> final_response        when route == final
search_knowledge_step -> reason
```

The package also keeps a `loopback` edge from `search_knowledge_step` to
`reason` as compatibility metadata while the downstream validator requires that
edge kind.

### Tool Contract

- Tool: `search_knowledge`
- Side effect: read
- Approval: normally not required; host may require approval for restricted read
  surfaces
- Model-visible output: model-safe observation summary
- Runtime-only output: raw backend response, if retained by the host runtime

### Prompt And State Policy

- Prompt variables use Python `.format(...)` single-brace syntax.
- Use the runtime-provided `{prompt}` key for the original user request; do not
  require a custom `user_goal` state key before the first node renders.
- First-turn reasoning prompts use `{node_outputs}` for workflow state so they do
  not require a tool-written state key before the first tool call.
- Hidden chain-of-thought is forbidden; carry only route tokens, final answers,
  and model-safe observation summaries between nodes.

### Safety And Evaluation

- Do not expose unapproved tools.
- Do not perform writes or mutations.
- Enforce iteration, step, and timeout limits in the host runtime.
- Regression tests should reject unconditional `llm_step -> tool_use_step`
  execution edges for ReAct loops.
- A working-package harness must register manifest tools with the host
  `ToolRegistry`; manifest tool metadata alone is descriptive.
- See `react-tool-agent-host-pseudocode.md` for the host-side registry and
  runner responsibilities without binding to a changing runtime API.
