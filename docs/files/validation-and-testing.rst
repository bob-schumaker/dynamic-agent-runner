
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
- context-pipeline validation and internal graph-mutation preparation
- callable registry lookup, schema conversion, and invocation
- runtime tool overrides and behavior overrides
- OpenAI request construction and fake-client adapter execution
- local model path resolution, offline policy, identity checks, direct
  in-process llama.cpp adapters, and local endpoint error classification
- llama.cpp memory-fit profiling through caller-supplied advisory profilers
- Hugging Face model discovery normalization and error wrapping
- async model, tool, and hook dispatch
- input guardrail registries and guardrail execution failures
- explicit MCP tool binding into the normal registry contract
- capability inspection reports for live, metadata-only, missing-collaborator,
  and invalid package states
- opt-in subagent tool packs with caller-injected runners and bounded child
  execution limits
- workflow execution, retries, output contracts, route validation, token budgets,
  prompt-cache observations, provider cache telemetry, prepare-model-input
  policy, and traces
- persistent in-memory agent sessions, snapshot restart, session event
  streaming, and collaborative parent/child session management
- CLI execution and error reporting
- all 11 hello-world agent-pattern fixture packages
- the placeholder-safe Power-Marimo first-customer fixture

.. header2:: No live model calls in unit tests

Unit tests should use fake model adapters and fake tool registries. The default
OpenAI client boundary exists for production use, but tests should not require
network access or credentials. A separate live interoperability test compares
the installed Codex CLI and DAR provider adapter against the same structured
output contract. Run it only when live credentials and network access are
intentional:

.. code-block:: bash

   DAR_RUN_LIVE_CODEX_PARITY=1 poetry run pytest \
     tests/test_live_codex_parity.py -q -s

The test is opt-in, uses an isolated temporary Codex home, and does not run as
part of the normal unit suite.

.. header2:: Manually gated live model-interface matrix

The deterministic and live matrices share one controlled S1--S6 tool catalog.
The live runner exposes only in-memory record tools, but it calls the selected
real model or local server. It requires an explicit environment gate and one
configured target:

.. code-block:: bash

   DAR_RUN_LIVE_MODEL_INTERFACE_MATRIX=1 poetry run python \
     scripts/run_live_model_interface_matrix.py \
     --target endpoint --model qwen3-local \
     --base-url http://127.0.0.1:8000/v1

Supported targets are ``codex``, ``openai``, ``litellm``, ``endpoint``,
``llama_cpp``, ``mlx_qwen3``, and ``apple``. Direct llama.cpp and MLX require
``--model-path``; the MLX target uses the pinned package-owned Qwen3 helper.
Use ``--scenario`` and ``--mode`` to narrow a manual run. Existing Codex and
Apple native checks are marked ``live_matrix`` supporting rows; they remain
separately opt-in because they require their own credentials or eligible host.

.. header2:: Docs validation

The docs authoring source lives in ``docs/files/``. Generated Sphinx source lives
in ``docs/source/``. Use the docs Makefile as the build source of truth:

.. code-block:: bash

   make -C docs html

The ``clean`` target removes generated pages under ``docs/source/*.rst`` and the
build output. Treat it as destructive for generated docs output.

.. header2:: Graphify navigation

Generated Graphify state lives under ignored ``graphify-out/``. Refresh the code
graph with ``graphify update .`` after structural changes, then use
``graphify query``, ``graphify path``, and ``graphify explain`` for codebase
navigation. The current graph is AST/code-only unless semantic extraction is run
with an LLM API key.
