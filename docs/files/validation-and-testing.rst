
.. header1:: Validation and Testing

The repository is designed so runtime behavior can be tested without live OpenAI
API calls or live external tools.

.. header2:: Targeted validation commands

Run Power-Marimo and fixture package coverage with:

.. code-block:: bash

   poetry run pytest tests/test_power_marimo_fixture.py tests/test_agent_pattern_fixtures.py -q

Run the full test suite with:

.. code-block:: bash

   poetry run pytest -q

Run pre-commit for changed files before committing:

.. code-block:: bash

   pre-commit run --files <changed files>

.. header2:: What tests cover

Current tests cover:

- artifact loading from paths, raw strings, and parsed mappings
- runtime manifest validation
- grouped runtime, metadata, and extension parsing
- external tool-index metadata validation
- callable registry lookup, schema conversion, and invocation
- runtime tool overrides and behavior overrides
- OpenAI request construction and fake-client adapter execution
- async model, tool, and hook dispatch
- workflow execution, retries, output contracts, route validation, token budgets,
  prompt-cache observations, and traces
- CLI execution and error reporting
- all 11 hello-world agent-pattern fixture packages
- the placeholder-safe Power-Marimo first-customer fixture

.. header2:: No live model calls in unit tests

Unit tests should use fake model adapters and fake tool registries. The default
OpenAI client boundary exists for production use, but tests should not require
network access or credentials.

.. header2:: Docs validation

The docs authoring source lives in ``docs/files/``. Generated Sphinx source lives
in ``docs/source/``. Use the docs Makefile as the build source of truth:

.. code-block:: bash

   make -C docs html

The ``clean`` target removes generated pages under ``docs/source/*.rst`` and the
build output. Treat it as destructive for generated docs output.
