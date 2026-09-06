# Conceptual ReAct Tool-Agent Runtime Example

This is a conceptual external-runtime example. It is not tied to any specific
Python package or runtime API. Replace `ExternalAgentRuntime`, `ToolRegistry`,
and `ModelAdapter` with the APIs from the actual consumer runtime.

## Control Flow

A ReAct tool loop must not force a tool call after every model step. The model
first chooses whether it needs a tool:

```text
reason -> route_action
route_action -> search_knowledge_step   when route == tool
route_action -> final_response          when route == final
search_knowledge_step -> reason
```

The loop exits when the route gate receives `{"route": "final"}`.

## Runtime Contracts

```text
reason model node returns:      {"route": "tool"} or {"route": "final"}
route decision node branches:   tool -> tool_use_step, final -> final_response
tool registry provides:         search_knowledge(arguments) -> observation
runtime enforces:               max_steps / max_iterations / timeout
final node returns:             answer object
```

## Conceptual Manifest Shape

```yaml
reason:
  emits:
    route: tool | final

route_action:
  reads: reason.route
  branches:
    tool: search_knowledge_step
    final: final_response

search_knowledge_step:
  invokes: search_knowledge
  writes: observation_log

final_response:
  reads:
    - prompt
    - observation_log
  emits:
    answer: string
```

## Conceptual Host Runner

```python
#!/usr/bin/env python3
"""Conceptual host runner for a ReAct tool-agent runtime package.

This is intentionally runtime-agnostic pseudocode. Replace
ExternalAgentRuntime, ToolRegistry, and ModelAdapter with the APIs from the
actual consumer runtime.
"""

from pathlib import Path


PACKAGE_DIRECTORY = Path(__file__).resolve().parent


def search_knowledge(arguments):
    query = arguments["query"]
    return {
        "summary": f"Example knowledge result for: {query}",
        "citations": ["local-example://react-tool-agent"],
    }


def main():
    tools = ToolRegistry()

    tools.register(
        id="search_knowledge",
        description="Read-only example knowledge search.",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        handler=search_knowledge,
    )

    model = ModelAdapter(
        scripted_routes=[
            {"node": "reason", "response": {"route": "tool"}},
            {"node": "reason", "response": {"route": "final"}},
        ],
        scripted_final={
            "answer": "The ReAct loop used one tool call, then exited.",
            "evidence": ["local-example://react-tool-agent"],
            "caveats": ["Conceptual model; replace with a real provider."],
        },
    )

    runtime = ExternalAgentRuntime(
        package_directory=PACKAGE_DIRECTORY,
        model=model,
        tools=tools,
        limits={
            "max_steps": 8,
            "max_iterations": 5,
        },
    )

    result = runtime.run(
        prompt="How should a ReAct loop exit when no tool is needed?"
    )

    print(result.final_answer)


if __name__ == "__main__":
    main()
```

## Notes

- The model route is structured: `{"route": "tool"}` or `{"route": "final"}`.
- The decision node owns branching.
- The tool node only runs on the `tool` branch.
- The final node runs on the `final` branch.
- The runtime, not the model, enforces `max_steps`, `max_iterations`, and
  timeout.
- The host runtime owns real tool registration; manifest metadata alone does not
  make a tool executable.
- The original user request is exposed to prompts as `{prompt}`, not as an
  uninitialized custom state key.
