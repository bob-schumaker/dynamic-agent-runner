
.. header1:: Power-Marimo Fixture

The Power-Marimo fixture is the first downstream package-shape example. It proves
that the runtime can represent a supervised, bounded Marimo notebook power
experiment workflow without live external dependencies.

.. header2:: Files

The fixture lives under ``tests/fixtures/power-marimo/``:

.. code-block:: text

   tests/fixtures/power-marimo/
     agent-runtime.yaml
     agent-graph.mmd
     agent-design.md

The test coverage lives in ``tests/test_power_marimo_fixture.py``.

.. header2:: What it demonstrates

The fixture demonstrates:

- grouped ``runtime``, ``metadata``, and ``extensions`` maps
- a ``workflow-orchestration-agent`` pattern marker
- primitive node kinds only: ``llm_step`` and ``tool_use_step``
- ``marimo-pair`` represented as a SKILL-backed agent-as-tool operation
- placeholder Marimo and domain tool definitions
- fake-tool execution of the bounded happy path
- no live Marimo server, real SLD data, or live ``power-tetris-sdk`` access

.. header2:: Agent-as-tool boundary

The ``invoke_marimo_pair`` node remains a primitive ``tool_use_step``. Its raw
metadata records the downstream skill boundary:

.. code-block:: yaml

   agent_as_tool:
     skill_id: marimo-pair
     skill_path: ../power-marimo/skills/marimo-pair/SKILL.md
     task_boundary: perform a bounded Marimo notebook operation

This is intentionally not a new primitive runtime node kind and not durable
handoff-style multi-agent metadata.

.. header2:: Placeholder tools

The fixture defines placeholder tools for:

- ``discover_marimo_servers``
- ``marimo_pair_agent``
- ``inspect_notebook_state``
- ``run_room_power_analysis``

Tests provide fake callable registry entries for those tools. The fake outputs
are synthetic and safe for unit tests.

.. header2:: Validation command

Run the fixture coverage with:

.. code-block:: bash

   poetry run pytest tests/test_power_marimo_fixture.py tests/test_agent_pattern_fixtures.py -q

This command loads the fixture, verifies the agent-as-tool metadata, and executes
the bounded fake-tool happy path with fake model responses.
