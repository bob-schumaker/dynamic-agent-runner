
.. header1:: CLI Usage

The console script is ``dynamic-agent-runner``.

.. header2:: Basic command

Run a workflow package from its directory:

.. code-block:: bash

   dynamic-agent-runner \
      --package path/to/agent-package \
      --prompt "Run the workflow for this user request."

Required option:

- ``--package`` — path to a canonical package directory containing
  ``agent-runtime.yaml``, ``agent-design.md``, and ``agent-graph.mmd``

Optional artifact options:

- ``--runtime-overrides`` — path to runtime prompt and skill override YAML

.. header2:: Prompt input

The prompt can come from an argument, a file, or standard input:

.. code-block:: bash

   dynamic-agent-runner --package path/to/agent-package --prompt "Say hello."

.. code-block:: bash

   dynamic-agent-runner --package path/to/agent-package --prompt-file prompt.txt

.. code-block:: bash

   printf 'Say hello.\n' | dynamic-agent-runner --package path/to/agent-package

``--prompt`` and ``--prompt-file`` are mutually exclusive. If neither is supplied,
the CLI reads standard input. Empty prompt input fails clearly.

.. header2:: Maximum steps

Use ``--max-steps`` to cap node execution count:

.. code-block:: bash

   dynamic-agent-runner \
      --package path/to/agent-package \
      --prompt "Run with a step cap." \
      --max-steps 20

This guards against workflows that cannot reach a terminal state within the
expected number of node executions.

.. header2:: Read-only local workspace tools

The only CLI-supported registry pack today is the opt-in read-only
``local_workspace`` pack. Enable it with one or more ``--workspace-root`` values:

.. code-block:: bash

   dynamic-agent-runner \
      --package path/to/agent-package \
      --prompt "Inspect this workspace." \
      --workspace-root .

The pack is read-only and constrained to approved roots. Write and shell-command
tools are not part of the default enabled set.

.. header2:: Output and errors

On success, the CLI prints the final workflow result to standard output. Non-text
results are serialized as JSON with sorted keys.

Loading, validation, registry, model, and execution failures are printed to
standard error with a non-zero exit code.
