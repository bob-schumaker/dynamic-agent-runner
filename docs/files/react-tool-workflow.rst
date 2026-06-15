
.. header1:: ReAct Tool Workflow Guide

A simple ReAct workflow should be explicit graph control, not one opaque agent
node. Model the loop as reasoning, routing, tool action, and synthesis. The key
rule is that a missing tool call exits the tool loop: when the model decides no
tool is needed, route to a final-answer node instead of entering a
``tool_use_step``.

.. header2:: Control-flow shape

Use this shape for a small ReAct agent:

.. code-block:: text

   reason -> route_action -> act -> reason
                 |
                 +-> final_answer

``reason`` emits a route token such as ``tool`` or ``final``. ``route_action``
is a ``decision_step`` with ``decision_subtype: llm_route``. The ``tool`` branch
executes the tool and loops back with the observation. The ``final`` branch skips
the tool and exits to the final answer step.

In the current runtime, the executable return edge from the tool node back to
the reasoning node is a ``sequential`` edge. A matching ``loopback`` edge is
included as ReAct pattern metadata so validation can recognize the loop.

Do not make ``reason -> act`` unconditional. An unconditional edge means the
runtime will try to execute the tool even when the model has no tool request.

.. header2:: Files for a runnable example

The example below is a complete local package plus a small host script. The host
script supplies a fake model adapter and an in-process tool registry, so it does
not need live OpenAI credentials or an external tool server.

.. code-block:: text

   simple-react-agent/
     agent-design.md
     agent-graph.mmd
     agent-runtime.yaml
   run_simple_react.py

.. header3:: ``simple-react-agent/agent-design.md``

.. code-block:: markdown

   # Simple ReAct Agent

   This package demonstrates a bounded ReAct loop:

   1. `reason` decides whether to use a tool.
   2. `route_action` branches on the model route.
   3. `search_notes` runs only when the route is `tool`.
   4. `reason` sees the observation and may route to `final`.
   5. `final_answer` produces the user-facing answer.

   The workflow exits the tool loop when `reason` emits `final`; it does not run
   a tool step with an empty tool request.

.. header3:: ``simple-react-agent/agent-graph.mmd``

.. code-block:: text

   flowchart TD
       reason[Reason]
       route_action{Route action}
       search_notes[Search notes]
       final_answer[Final answer]

       reason -->|sequential| route_action
       route_action -->|tool| search_notes
       search_notes -->|sequential| reason
       search_notes -.->|loopback metadata| reason
       route_action -->|final| final_answer

.. header3:: ``simple-react-agent/agent-runtime.yaml``

.. code-block:: yaml

   format_version: 1
   package_type: dynamic_agent_design
   package_id: simple-react-agent
   name: Simple ReAct Agent
   description: Minimal ReAct loop that exits when no tool call is requested.
   entrypoint: reason
   mermaid_diagram: agent-graph.mmd
   packaging:
     mode: hybrid_bundle

   runtime:
     execution_policy:
       model: gpt-test
       max_iterations: 3
       max_steps: 8
     state:
       artifacts:
       - id: observation_log
         description: Model-safe observations from prior tool calls.
         source: runtime
       mutable_fields:
       - observation_log

   metadata:
     patterns_present:
     - react_loop

   tools:
   - id: search_notes
     label: Search notes
     description_for_llm: Search local notes for relevant facts.
     adapter: local.search_notes
     input_schema:
       type: object
       properties:
         query:
           type: string
       required:
       - query
     output_schema:
       type: object
       properties:
         observation:
           type: string
     side_effect: read
     approval_required: false

   nodes:
   - id: reason
     kind: llm_step
     label: Decide whether to use a tool
     model: gpt-test
     prompt:
       system: |
         You are a bounded ReAct agent.
         Reply with exactly one route token:
         - tool: use the search_notes tool
         - final: enough information is available
       user_template: |
         User request: {prompt}

         Current workflow state:
         {node_outputs}

         Choose the next route: tool or final.
       input_vars:
       - prompt

   - id: route_action
     kind: decision_step
     label: Route tool or final
     decision_subtype: llm_route
     route_from: reason
     decision_contract:
       allowed_paths:
       - tool
       - final

   - id: search_notes
     kind: tool_use_step
     label: Search notes
     tool_id: search_notes
     inputs_from:
       query: prompt
     outputs:
       state_key: observation_log

   - id: final_answer
     kind: llm_step
     label: Write final answer
     model: gpt-test
     prompt:
       system: |
         Answer the user using the available observation. Be concise.
       user_template: |
         User request: {prompt}

         Workflow state:
         {node_outputs}

         Final answer:
       input_vars:
       - prompt

   edges:
   - source: reason
     target: route_action
     edge_kind: sequential
   - source: route_action
     target: search_notes
     edge_kind: branch
     condition: tool
   - source: search_notes
     target: reason
     edge_kind: sequential
   - source: search_notes
     target: reason
     edge_kind: loopback
   - source: route_action
     target: final_answer
     edge_kind: branch
     condition: final

   validation:
     package_checks:
     - Every node id is unique.
     - Every edge endpoint references an existing node.
     - The ReAct loop has a positive max_iterations value.

.. header3:: ``run_simple_react.py``

.. code-block:: python

   from dynamic_agent_runner import (
       InMemoryToolRegistry,
       OpenAIClientAdapter,
       RegisteredTool,
       run_agent_workflow,
   )
   from dynamic_agent_runner.models import ToolDefinition


   class FakeResponses:
       def __init__(self, responses):
           self.responses = list(responses)

       def create(self, **kwargs):
           return self.responses.pop(0)


   class FakeClient:
       def __init__(self, responses):
           self.responses = FakeResponses(responses)


   def search_notes(arguments):
       query = arguments["query"]
       return {
           "observation": (
               f"Search result for {query!r}: dynamic-agent-runner executes "
               "llm_step, decision_step, and tool_use_step nodes as graph "
               "primitives."
           )
       }


   tool_definition = ToolDefinition.from_mapping(
       {
           "id": "search_notes",
           "description_for_llm": "Search local notes for relevant facts.",
           "input_schema": {
               "type": "object",
               "properties": {"query": {"type": "string"}},
               "required": ["query"],
           },
           "side_effect": "read",
           "approval_required": False,
       }
   )

   registry = InMemoryToolRegistry(
       [
           RegisteredTool(
               tool_definition,
               search_notes,
           )
       ]
   )

   adapter = OpenAIClientAdapter(
       FakeClient(
           [
               {"id": "route_1", "output_text": "tool"},
               {"id": "route_2", "output_text": "final"},
               {
                   "id": "final",
                   "output_text": (
                       "Use a decision node after reasoning. If the route is "
                       "'tool', run the tool and loop back; if the route is "
                       "'final', skip the tool and answer."
                   ),
               },
           ]
       ),
       models=["gpt-test"],
   )

   result = run_agent_workflow(
       package_directory="simple-react-agent",
       prompt="How should a ReAct loop exit when no tool is needed?",
       tool_registry=registry,
       model_adapter=adapter,
       max_steps=8,
   )

   print(result)

Running the script prints the final fake model answer. The first model response
routes to ``tool``, so ``search_notes`` runs. The second model response routes
to ``final``, so the graph exits the loop and skips another tool call.

.. header2:: Design notes

- ``decision_step`` is the loop gate. It prevents empty or unnecessary tool
  calls. The executable return edge is ``sequential``; the ``loopback`` edge
  records the ReAct loop pattern for validation.
- ``tool_use_step`` invokes the caller-registered tool handler. The manifest's
  ``tools`` section describes the tool, but the runtime still requires a
  callable registry entry.
- ``runtime.execution_policy.max_iterations`` bounds the ReAct loop.
- ``runtime.execution_policy.max_steps`` should leave room for route, tool, and
  final-answer nodes.
- Store model-safe observations in runtime state, such as ``observation_log``.
  Prompts can reference ``{node_outputs}`` at any point, and can reference a
  named state key after a tool node writes it.
- For a one-shot tool workflow that does not need ReAct looping, use
  ``llm_step -> tool_use_step -> llm_step`` instead.
