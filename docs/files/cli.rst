
.. header1:: CLI Usage

The console script is ``dynamic-agent-runner``.

.. header2:: Basic command

Run a workflow package from local artifact paths:

.. code-block:: bash

   dynamic-agent-runner \
     --runtime-manifest path/to/agent-runtime.yaml \
     --agent-design path/to/agent-design.md \
     --mermaid-graph path/to/agent-graph.mmd \
     --tool-index path/to/tool-index.yaml \
     --prompt "Run the workflow for this user request."

Required option:

- ``--runtime-manifest`` — path to ``agent-runtime.yaml``

Optional artifact options:

- ``--agent-design`` — path to ``agent-design.md``
- ``--mermaid-graph`` or ``--mermaid-diagram`` — path to ``agent-graph.mmd``
- ``--tool-index`` — path to reusable ``tool-index.yaml`` metadata
- ``--runtime-overrides`` — path to runtime prompt and skill override YAML

If ``--mermaid-graph`` is omitted, the loader resolves ``mermaid_diagram`` from
the runtime manifest relative to the manifest path.

.. header2:: Prompt input

The prompt can come from an argument, a file, or standard input:

.. code-block:: bash

   dynamic-agent-runner --runtime-manifest agent-runtime.yaml --prompt "Say hello."

.. code-block:: bash

   dynamic-agent-runner --runtime-manifest agent-runtime.yaml --prompt-file prompt.txt

.. code-block:: bash

   printf 'Say hello.\n' | dynamic-agent-runner --runtime-manifest agent-runtime.yaml

``--prompt`` and ``--prompt-file`` are mutually exclusive. If neither is supplied,
the CLI reads standard input. Empty prompt input fails clearly.

.. header2:: Maximum steps

Use ``--max-steps`` to cap node execution count:

.. code-block:: bash

   dynamic-agent-runner \
     --runtime-manifest agent-runtime.yaml \
     --prompt "Run with a step cap." \
     --max-steps 20

This guards against workflows that cannot reach a terminal state within the
expected number of node executions.

.. header2:: Read-only local workspace tools

The only CLI-supported registry pack today is the opt-in read-only
``local_workspace`` pack. Enable it with one or more ``--workspace-root`` values:

.. code-block:: bash

   dynamic-agent-runner \
     --runtime-manifest agent-runtime.yaml \
     --prompt "Inspect this workspace." \
     --workspace-root .

The pack is read-only and constrained to approved roots. Write and shell-command
tools are not part of the default enabled set.

.. header2:: Output and errors

On success, the CLI prints the final workflow result to standard output. Non-text
results are serialized as JSON with sorted keys.

Loading, validation, registry, model, and execution failures are printed to
standard error with a non-zero exit code.
