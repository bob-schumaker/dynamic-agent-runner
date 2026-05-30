
.. header1:: Quickstart

``dynamic-agent-runner`` executes generated agent workflow packages. A package
normally contains an ``agent-runtime.yaml`` manifest, an ``agent-design.md``
design note, and an ``agent-graph.mmd`` Mermaid graph.

.. header2:: Install dependencies

Install the project dependencies with Poetry:

.. code-block:: bash

   poetry install --with dev

If you use mise, enter the repository so ``.mise.toml`` can configure the local
Python environment. The repository also provides ``env_setup`` for shell setup:

.. code-block:: bash

   source env_setup

.. header2:: Run from Python

Use ``run_agent_workflow(...)`` when you want to load, validate, execute, and
return the final result in one call:

.. code-block:: python

   from dynamic_agent_runner import run_agent_workflow

   result = run_agent_workflow(
       runtime_manifest="tests/fixtures/agent-patterns/basic-reasoning-agent/agent-runtime.yaml",
       agent_design="tests/fixtures/agent-patterns/basic-reasoning-agent/agent-design.md",
       prompt="Say hello from this workflow.",
       model_adapter=my_model_adapter,
       tool_registry=my_tool_registry,
   )

The default model path uses the official ``openai`` package. Unit tests and local
examples should inject fake model adapters instead of making live model calls.

.. header2:: Run from the CLI

After installation, use the console script:

.. code-block:: bash

   dynamic-agent-runner \
     --runtime-manifest tests/fixtures/agent-patterns/basic-reasoning-agent/agent-runtime.yaml \
     --agent-design tests/fixtures/agent-patterns/basic-reasoning-agent/agent-design.md \
     --prompt "Say hello from this workflow."

If ``--mermaid-graph`` is omitted, the loader resolves the manifest's
``mermaid_diagram`` reference relative to the runtime manifest path.

.. header2:: What happens during a run

A normal run follows this flow:

1. Load the runtime manifest, design note, Mermaid graph, optional tool index,
   and optional runtime behavior overrides.
2. Validate required fields, node IDs, edges, prompts, skill references, output
   contracts, extension envelopes, and callable tool availability.
3. Prepare an internal execution plan from primitive runtime nodes.
4. Render model input for each ``llm_step``.
5. Dispatch ``tool_use_step`` nodes through a caller-provided tool registry.
6. Traverse supported ``sequential`` and ``branch`` control-flow edges.
7. Return the final result and retain detailed execution state when using the
   lower-level executor API.

.. header2:: Current boundaries

The runtime supports a finite graph executor with primitive node kinds:

- ``llm_step``
- ``tool_use_step``
- ``decision_step``

Broader behavior such as live Marimo automation, MCP discovery, durable approval
resume, unrestricted notebook mutation, and full multi-agent execution remains
out of scope until future scoped follow-ups define it.
