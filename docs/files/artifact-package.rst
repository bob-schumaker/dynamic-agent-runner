
.. header1:: Runtime Artifact Packages

``dynamic-agent-runner`` consumes generated dynamic-agent design packages. The
runtime package is source data, not Python code.

.. header2:: Package shape

A typical package contains:

.. code-block:: text

   <agent-package>/
     agent-design.md
     agent-runtime.yaml
     agent-graph.mmd
     skill-bundle/

``agent-runtime.yaml`` is the executable manifest. ``agent-design.md`` explains
intent and safety. ``agent-graph.mmd`` visualizes control flow. ``skill-bundle/``
is reserved for referenced skill support files when a package uses that mode.

.. header2:: Required manifest fields

The current supported manifest version uses ``format_version: 1`` and
``package_type: dynamic_agent_design``. Required top-level fields include:

- ``format_version``
- ``package_type``
- ``package_id``
- ``entrypoint``
- ``packaging``
- ``nodes``
- ``edges``

The runtime also preserves top-level ``tools``, ``skills``,
``output_contracts``, and ``validation`` sections when present.

.. header2:: Grouped optional sections

Optional complexity belongs in grouped maps:

- ``runtime`` — execution policy and runtime state metadata
- ``metadata`` — pattern, mode, phase, role, and participant metadata
- ``extensions`` — optional capability envelopes

Legacy flat root fields such as ``execution_policy``, ``state``,
``patterns_present``, ``participant_groups``, ``modes``, ``phases``, ``roles``,
``runtime_surface``, ``workspace_boundary``, and ``completion_contract`` are not
treated as compatibility paths. They should be moved into the grouped sections.

.. header2:: Nodes and edges

Supported primitive node kinds are:

- ``llm_step`` — render prompt messages and call the configured model adapter
- ``tool_use_step`` — invoke a callable registry tool by ``tool_id``
- ``decision_step`` — currently supports ``decision_subtype: llm_route``

Supported control-flow edges include ``sequential`` and branch traversal from
``decision_step`` nodes. Artifact metadata may preserve other edge kinds for
future work, but unsupported runtime edge configurations fail clearly during
execution.

``llm_step`` nodes may also carry provider-neutral ``model_requirements``
metadata. This describes selection requirements such as structured output,
tool-calling, long context, citation generation, and ``embeddings`` support.
These fields are manifest guidance for runtime/model selection and validation;
they are not passed through to the provider request as API parameters.

.. code-block:: yaml

   - id: synthesize_answer
     kind: llm_step
     prompt:
       user_template: "Answer from retrieved context: {retrieved_context}"
       output_schema_ref: answer
     model_requirements:
       required_capabilities:
       - structured_output
       - embeddings
       context_requirements:
         needs_retrieved_context: true
       output_requirements:
         format: schema_ref
         schema_ref: answer
         evidence_citations: preferred

.. header2:: RAG and embedding-backed retrieval metadata

RAG workflows use the existing primitive node kinds rather than adding a new
node type. Use ``tool_use_step`` nodes for retrieval, index lookup, graph lookup,
reranking, or context assembly; use ``llm_step`` nodes for query planning and
answer synthesis; and use ``decision_step`` nodes for sufficiency, freshness, and
fallback routing.

Declare RAG intent in ``metadata.patterns_present`` and describe retrieval policy
under ``metadata.rag_pipeline``:

.. code-block:: yaml

   metadata:
     patterns_present:
     - rag
     - embedding_retrieval
     rag_pipeline:
       retrieval_mode: embedding_semantic
       embedding_capability: required
       graph_capability: not_applicable
       index_owner: runtime
       graph_store_owner: unknown
       corpus_boundary: runtime fixture documents
       chunking_policy: runtime default
       metadata_filters:
       - tenant
       reranking: vector_score
       freshness_policy: manual
       provenance_required: true

The loader preserves ``metadata.rag_pipeline`` as manifest metadata. Validation
checks the supported enum values and the basic consistency of RAG pattern flags:
``embedding_retrieval`` requires ``retrieval_mode: embedding_semantic`` or
``hybrid`` plus ``embedding_capability: required``; graph retrieval patterns
require ``graph_capability: required``.

.. header2:: Output contracts

``output_contracts`` is an array of contract objects. ``llm_step`` nodes can
reference a contract by setting ``output_schema_ref`` on the node or inside its
``prompt`` metadata.

Required fields are validated against JSON object model output or adapter-provided
structured output. Plain text is accepted only for the common single-field
``message`` contract used by hello-world fixtures.

.. header2:: Extensions

Extension entries are fail-closed when required but unsupported:

.. code-block:: yaml

   extensions:
     marimo_session:
       required: false
       config:
         live_execution: false

Unsupported extensions with ``required: false`` are preserved for diagnostics and
future preparation reports. Malformed extension envelopes fail validation.
