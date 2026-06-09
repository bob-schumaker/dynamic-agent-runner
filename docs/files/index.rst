
.. header1:: The dynamic-agent-runner Library Documentation

``dynamic-agent-runner`` loads generated agent runtime artifacts, validates their
relationships, executes supported workflow nodes through the official OpenAI
Python SDK boundary and a repository-owned tool registry, and returns the final
workflow result.

Start with :doc:`quickstart` if you want to run a workflow. Use the API, CLI,
manifest, registry, and operations pages for deeper integration details.

.. toctree::
   :maxdepth: 2
   :caption: Usage Documentation

   quickstart
   artifact-package
   react-tool-workflow
   python-api
   cli
   tool-registry
   runtime-policies
   tracing-and-observability
   power-marimo-fixture
   validation-and-testing

.. automodule:: dynamic_agent_runner
   :noindex:
