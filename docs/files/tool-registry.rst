
.. header1:: Tool Registry Usage

The runtime uses a repository-owned tool registry. Manifest and tool-index tool
entries provide metadata, but callable tool execution requires a registry entry.

.. header2:: Registering a tool

Create a ``ToolDefinition`` and ``RegisteredTool`` and add it to an
``InMemoryToolRegistry``:

.. code-block:: python

   from dynamic_agent_runner import InMemoryToolRegistry, RegisteredTool
   from dynamic_agent_runner.models import ToolDefinition

   def search_repo(arguments):
       query = arguments["query"]
       return {"message": f"searched for {query}"}

   registry = InMemoryToolRegistry(
       [
           RegisteredTool(
               ToolDefinition.from_mapping(
                   {
                       "id": "search_repo",
                       "description_for_llm": "Search repository text.",
                       "input_schema": {
                           "type": "object",
                           "properties": {"query": {"type": "string"}},
                           "required": ["query"],
                       },
                       "side_effect": "read",
                       "approval_required": False,
                   }
               ),
               search_repo,
           )
       ]
   )

The registry validates object-shaped input schemas before invocation and before
OpenAI-compatible tool schema exposure.

.. header2:: Direct tool invocation

``tool_use_step`` nodes call tools by ``tool_id``. Callable registry entries are
authoritative for execution. Metadata-only tools in a manifest or tool index do
not make a tool executable.

Tool handlers receive a mapping of resolved arguments and may return either a raw
value or a ``ToolResult``. Raw values are wrapped as successful ``ToolResult``
objects.

.. header2:: MCP tool bindings

MCP integration is explicit and caller-owned. The package does not discover or
start MCP servers, but callers can bind known MCP tools into the normal registry
contract:

.. code-block:: python

   from dynamic_agent_runner import MCPToolBinding, create_mcp_registry

   registry = create_mcp_registry(
       [
           MCPToolBinding(
               tool_id="mcp.echo",
               source_id="repo-tools",
               server_id="repo-mcp",
               mcp_tool_name="echo",
               handler=lambda args: {"echo": args["text"]},
               input_schema={
                   "type": "object",
                   "properties": {"text": {"type": "string"}},
                   "required": ["text"],
               },
           )
       ]
   )

MCP-bound tools default to hidden exposure and approval required. Trusted callers
may override policy metadata in the binding ``metadata`` mapping.

.. header2:: Host-owned tool bindings

Host applications can adapt their own callable tools into the registry without
renaming their internal catalog:

.. code-block:: python

   from dynamic_agent_runner import HostToolBinding, create_host_tool_registry

   registry = create_host_tool_registry(
       [
           HostToolBinding(
               canonical_id="power_marimo.analyze_notebook",
               model_id="analyze_notebook",
               handler=analyze_notebook,
               description="Analyze the active notebook.",
               input_schema={"type": "object", "properties": {}},
           )
       ]
   )

``canonical_id`` remains the host-facing id. ``model_id`` and aliases are the
provider-safe ids exposed to workflow models. ``summarize_trace_events(...)``,
``summarize_capability_report(...)``, and ``ResolvedModelSelection`` provide
bounded handoff helpers for hosts that need redacted status or model-selection
payloads.

.. header2:: Opt-in built-in tool packs

Built-in packs are disabled unless the caller explicitly creates and supplies
their registries. They require injected clients or stores so unit tests do not
make live external calls:

.. code-block:: python

   from dynamic_agent_runner import (
       SubagentPreset,
       WebToolPolicy,
       WorkspaceDataToolPolicy,
       create_subagent_registry,
       create_web_registry,
       create_workspace_data_registry,
   )

   web_registry = create_web_registry(
       search_client=my_search_client,
       fetch_client=my_fetch_client,
       policy=WebToolPolicy(allowed_domains=("example.com",)),
   )

   workspace_data_registry = create_workspace_data_registry(
       store=my_json_store,
       policy=WorkspaceDataToolPolicy(default_search_limit=5),
   )

   subagent_registry = create_subagent_registry(
       runner=my_subagent_runner,
       presets={"reviewer": SubagentPreset(id="reviewer")},
   )

``create_web_registry(...)`` exposes ``web_search`` and ``web_fetch``.
``create_workspace_data_registry(...)`` exposes ``workspace_data_write``,
``workspace_data_read``, ``workspace_data_search``, ``workspace_data_list``, and
``workspace_data_delete``. ``create_subagent_registry(...)`` exposes
``run_subagent`` and ``run_subagents``. These helpers normalize model-facing
results, but network access, durable storage, child lifecycle, and host dirty
state remain caller-owned.

.. header2:: Async tool handlers

Registered tools record whether their handler is synchronous or asynchronous.
The async executor awaits async handlers directly and dispatches synchronous
handlers without blocking the event loop. The synchronous registry path can run
async handlers only when no event loop is already running.

.. header2:: Tool exposure

Tool definitions may declare an ``exposure`` state:

- ``direct`` — callable by direct tool steps and exposable to models
- ``direct_model_only`` — exposable to models but not directly callable by a
  ``tool_use_step``
- ``hidden`` — directly callable but not model-exposed
- ``deferred`` — reserved for future discovery/activation patterns and not
  directly callable today

Unknown exposure values fail validation.

.. header2:: Tool policy metadata

``ToolPolicy`` preserves side-effect, approval, sandbox, timeout, retry, and
failure-behavior metadata separately from callable registration. Current policy
fields are diagnostic and validation inputs; high-risk enforcement requires a
future scoped policy implementation.

.. header2:: Runtime overrides

Runtime tool overrides can add, replace, disable, or restrict tools globally or
per ``llm_step`` without modifying generated artifacts. Override-added and
replacement tools receive runtime-override provenance.

.. header2:: Tool provenance

Tool definitions carry ``ToolSource`` metadata for diagnostics. Current source
kinds distinguish manifest declarations, external tool-index entries, built-in
tools, runtime overrides, and caller-registered tools.
