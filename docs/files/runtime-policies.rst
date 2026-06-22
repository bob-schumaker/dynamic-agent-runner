
.. header1:: Runtime Policies and Safety Boundaries

Runtime policy fields live under ``runtime.execution_policy`` in
``agent-runtime.yaml``. The runtime preserves and enforces only the policy fields
implemented by current package-owned interfaces.

.. header2:: Execution policy metadata

Common policy fields include:

.. code-block:: yaml

   runtime:
     execution_policy:
       autonomy_level: supervised agent
       allowed_execution_modes:
       - sequential_fallback
       external_backend_allowed: false
       max_steps: 10
       timeout: runtime_default
       approval_required_for:
       - live write or mutation
       forbidden_actions:
       - store secrets in prompts or logs
       model: gpt-test

The runtime currently uses the configured model name and maximum step values.
Model selection reads a node-level ``model`` first, then
``execution_policy.model``, then ``execution_policy.default_model``. Other fields
are preserved as policy metadata and should be documented honestly until a scoped
implementation enforces them.

The current runtime also preserves ``execution_policy.model_capabilities`` as
provider-neutral capability metadata on the loaded manifest. This metadata is
available for inspection and documentation, but it is not forwarded as provider
request parameters.

When callers do not provide explicit model adapters and a node does not require
capability-based routing, the executor constructs the default async OpenAI
adapter for the requested model name. Capability-aware routing is only applied
when the manifest supplies ``llm_step.model_requirements`` and/or
``execution_policy.model_map`` metadata. Local-only selection is therefore part
of the explicit manifest-driven routing contract, not an implicit background
fallback.

.. code-block:: yaml

   runtime:
     execution_policy:
       default_model: gpt-4o-mini
       model_capabilities:
         context_window: 128000
         structured_output: true
         reasoning: true
       model_map:
         remote-basic:
         - tool_calling
         local-structured:
         - tool_calling
         - structured_output

Caller-owned local OpenAI-compatible endpoints can be represented with
``LocalOpenAIEndpointConfig`` and the local adapter helpers. Those helpers wrap an
existing endpoint and classify connectivity, protocol, and identity failures; the
runner does not start, stop, or supervise model-server processes.

.. header2:: Retry policy

By default, model and tool calls are attempted once. Workflows can opt into
bounded retry behavior:

.. code-block:: yaml

   runtime:
     execution_policy:
       model_retry_policy:
         max_attempts: 3
         retry_on:
         - model_error

Node-level retry policy can also be attached to a model or tool node:

.. code-block:: yaml

   - id: lookup
     kind: tool_use_step
     tool_id: search_repo
     retry_policy:
       max_attempts: 2
       retry_on:
       - tool_failure

Retry outcomes are recorded in ``WorkflowExecutionState.retry_records``.

.. header2:: Tool-call completion loop

Model-exposed tools can run inside an ``llm_step`` when
``runtime.execution_policy.tool_use_completion.run_again`` is ``required``. The
executor sends model tool calls to the caller-provided registry, appends tool
results to the transcript, and asks the model again until the model stops
requesting tools, ``stop_on_tool`` is enabled, or the iteration limit is reached.

.. code-block:: yaml

   runtime:
     execution_policy:
       tool_use_completion:
         run_again: required
         stop_on_tool: disabled
         final_output: default

The loop is bounded by ``max_steps`` when configured, otherwise by the runtime's
internal default. Approval-required tool calls can return an interruption result
from the lower-level executor APIs.

.. header2:: Tool choice policy

``tool_choice_policy`` is disabled unless configured. It separates first-turn
tool forcing from follow-up model requests after a tool result has been added to
the iterative loop transcript.

.. code-block:: yaml

   runtime:
     execution_policy:
       tool_choice_policy:
         initial: required
         after_tool_result: auto

Supported values are ``required`` and ``auto``. ``required`` sends forced tool
choice for that phase; ``auto`` omits forced ``tool_choice`` and lets the model
answer without another tool call. Node-local policy can override the runtime
default:

.. code-block:: yaml

   nodes:
   - id: reason
     kind: llm_step
     tool_choice_policy:
       initial: required
       after_tool_result: auto

Legacy node-level ``tool_choice`` remains supported when no explicit
``tool_choice_policy`` is configured. A node that sets both fields fails
validation.

.. header2:: Token budgeting

Token budgeting is disabled unless configured. A policy can fail before a model
call when rendered input is too large:

.. code-block:: yaml

   runtime:
     execution_policy:
       token_budget:
         model: gpt-4o-mini
         max_prompt_tokens: 4000
         on_exceed: error

The runtime uses ``tiktoken`` for estimates. Unknown models fall back to a base
encoding and record the fallback flag. Automatic truncation is not currently
implemented.

.. header2:: Tool descriptor budgeting

Tool descriptor budgeting is disabled unless configured. When enabled, the
executor starts from the normal registry-exposed tools for an ``llm_step`` and
packs only OpenAI-compatible descriptors that fit configured descriptor limits.

.. code-block:: yaml

   runtime:
     execution_policy:
       tool_descriptor_budget:
         enabled: true
         model: gpt-4o-mini
         max_tokens: 1200
         max_tools: 8
         strategy: deterministic_metadata
         low_confidence_behavior: include_all_within_budget
         required_tools:
         - read_file
         diagnostics: redacted

Node-local overrides can tighten scalar limits or add required tools:

.. code-block:: yaml

   nodes:
   - id: answer
     kind: llm_step
     available_tools:
     - search_repo
     - read_file
     tool_descriptor_budget:
       max_tokens: 800
       required_tools:
       - search_repo

The selector never exposes tools filtered out by
``registry.list_tools_for_node(...)``. Required tools are packed first and fail
before model dispatch if they are unavailable or cannot fit. Optional tools can
be omitted for explicit reasons such as ``max_tools`` or ``over_budget``.

Diagnostics are redacted on ``model_request`` traces. They include selected and
omitted tool ids, reasons, counts, token estimates, strategy, and tokenizer
fallback metadata; they do not include raw prompt content, arguments, or full
tool schemas. The first implementation uses deterministic metadata scoring only;
NLTK, embeddings, vector stores, and model-backed selection are not runtime
dependencies.

.. header2:: Prompt-cache intent

Prompt-cache metadata is provider-neutral intent. It records stable prefix and
variable prompt-part expectations and emits trace evidence. Provider-specific
request controls remain deferred; adapter responses that expose cached-token
usage are recorded as telemetry.

.. code-block:: yaml

   runtime:
     execution_policy:
       prompt_cache:
         enabled: true
         strategy: stable_prefix
         prefix_parts:
         - system
         variable_parts:
         - user_template

Callers can pass ``prompt_cache=False`` at execution time to disable prompt-cache
observation for a run.

.. header2:: Prepare-model-input policy

``runtime.execution_policy.prepare_model_input`` controls implemented prompt
preparation behavior before a model request. The current runtime can add
hierarchy messages, include bounded package-local file context, include retrieved
context supplied in execution state, prune or compact session messages, apply
lane budgets, select older turns, run caller-injected semantic older-turn
selection, and emit preparation metadata.

.. code-block:: yaml

   runtime:
     execution_policy:
       prepare_model_input:
         prompt_hierarchy:
           system:
           - "Follow the package safety policy."
           developer:
           - "Prefer concise answers."
         context_compaction:
           auto:
             enabled: true
             threshold_ratio: 0.8
             reserve_tokens: 1024
             scope: current_run
             implementation: metadata_only
             strategy: basic
             mode: auto
             manual_mode: allowed
             trigger: token_threshold
             reset_behavior: new_window
             lifecycle_stages:
             - validate
             - segment
             - report
             metrics:
             - lane_utilization
         context_compression:
           profile: balanced
           lanes:
             recent_turn_tokens: 4000
             retrieved_context_tokens: 8000
           selection:
             strategy: deterministic_overlap
             max_selected_turns: 6
             chronological_reassembly: true

Validation rejects unsupported compaction, compression, lane, and selection
values. File context remains package-root bounded; paths that escape the package
root fail closed.

``context_compression.selection.strategy: injected_semantic`` is live only when
the caller supplies a context selector through direct execution or
``WorkflowExecutionContext``. The selector receives bounded older-turn
candidates and returns turn ids plus scores; retrieved RAG evidence stays in the
retrieved-context lane and is not passed to the selector. Missing selectors fall
back to deterministic overlap with visible preparation metadata. The runner does
not create embeddings, vector stores, memory stores, or retrievers for semantic
selection.

Provider-backed remote compaction, richer model-backed summary behavior, and
remaining semantic/profile behavior are prepared as future specs. See
``specs/provider-backed-context-compaction/``,
``specs/model-backed-context-summaries/``, and
``specs/semantic-context-profiles/`` for those planned follow-up surfaces.

.. header2:: Runtime behavior overrides

Runtime behavior overrides can patch ``llm_step`` prompts and skill references
without mutating generated artifacts. Inline skill instructions still render in
the ``skill_instructions`` prompt lane with each skill's ``prompt_role``.

.. header2:: Skill source resolution

Package-local ``SKILL.md`` loading is disabled by default. Package-directory
workflows can opt in with ``runtime.execution_policy.skill_source_resolution``:

.. code-block:: yaml

   runtime:
     execution_policy:
       skill_source_resolution:
         enabled: true
         allowed_sources:
         - package_bundle
         max_skill_bytes: 65536
         max_node_skill_bytes: 262144
         load_support_files: false
         prompt_role: developer

When enabled, skill declarations without inline ``instructions`` must use a
package-local ``bundled_path`` that resolves under ``packaging.skill_bundle_dir``
and points to a ``SKILL.md`` file. The executor loads those bodies into the
existing ``skill_instructions`` prompt lane after runtime behavior overrides are
applied, preserving effective ``skill_refs`` order. Loaded, omitted, and
rejected sources are reported as redacted preparation and trace metadata with
content hashes and byte counts, never raw skill bodies.

The loader fails closed for missing files, absolute or escaping paths, symlink
escapes, binary-looking content, non-UTF-8 content, and per-skill or per-node byte
limit violations. ``source_path`` remains provenance-only and is never read.
``support_files`` remain package validation artifacts; ``load_support_files`` is
reserved and must be ``false``.

.. header2:: Guardrails

Guardrail declarations live under ``extensions.guardrails``:

.. code-block:: yaml

   extensions:
     guardrails:
       declarations:
       - id: no_secrets
         phase: input
         behavior_on_tripwire: abort

Declared ``input`` guardrails are live when the caller supplies an
``InMemoryGuardrailRegistry`` through ``execute_workflow(...)``,
``execute_workflow_async(...)``, or ``WorkflowExecutionContext``. Missing input
guardrail handlers fail closed before the first node runs. A handler returning
``GuardrailDecision.ABORT`` raises ``GuardrailExecutionError`` and emits
guardrail trace events. Other phases are validated and preserved, but not yet
executed.

.. header2:: Approval interruption metadata

Approval-required tool flows can preserve interruption and resumable-state intent
under ``runtime.execution_policy.approval_interruption``.

.. code-block:: yaml

   runtime:
     execution_policy:
       approval_interruption:
         mode: pause_on_approval
         persist: external_checkpoint
         resume_from: approval_decision
         pending_tool_calls_state_key: pending_tool_calls
         pending_approvals_state_key: pending_approvals
         interruption_state_key: interruption_state
         resume_token_state_key: resume_token

The metadata is preserved and validated. The lower-level executor can also
return ``WorkflowInterruptedResult`` when a model tool call reaches a registered
tool that requires approval. The package still does not provide durable
checkpoint storage, resume-token persistence, or an external approval service.

.. header2:: Async-session metadata

Multi-turn or resumable workflow intent can be preserved under
``runtime.execution_policy.async_session`` and used by ``AgentSession`` for
in-memory v1 session continuity.

.. code-block:: yaml

   runtime:
     execution_policy:
       async_session:
         mode: conversational
         persist: external_checkpoint
         history: full
         session_id_state_key: session.id
         session_messages_state_key: session.messages

``AgentSession`` with ``InMemorySessionStore`` provides runner-owned
process-local session storage, current-state retrieval, snapshot restart, and
cross-prompt transcript replay. ``history`` controls what is replayed into the
next bounded run: ``none`` replays no prior messages, ``last_turn`` replays only
the previous user/assistant pair, ``full`` replays all retained user/assistant
messages, and v1 ``summary`` preserves caller-supplied summary metadata without
generating summaries.

Persisted policies must still satisfy fail-closed validation rules, including a
required ``session_id_state_key`` when ``persist`` is not ``none`` and omission
of ``session_messages_state_key`` when ``history`` is ``none``. Durable
filesystem, database, Redis, cloud, OCI, or external-checkpoint stores remain
out of scope for v1.

.. header2:: Sandbox runtime metadata

Sandbox/workspace runtime intent for future write-command tools can be preserved
under ``runtime.execution_policy.sandbox_runtime``.

.. code-block:: yaml

   runtime:
     execution_policy:
       sandbox_runtime:
         mode: per_run_workspace
         filesystem: workspace_write
         persist_workspace: named_session
         command_policy: allow_list
         writable_root_state_key: writable_root
         working_directory_state_key: working_directory

The current runtime preserves and validates this metadata only. It does not yet
implement a writable workspace runtime, command execution engine, allow-list
enforcement, or sandbox boundary manager. The existing opt-in ``local_workspace``
built-in pack remains a separate read-only tool pack.

.. header2:: Concurrency and async execution

The implementation is async-first. Synchronous public functions wrap the async
path and reject calls from an already-running event loop. Each run has isolated
execution state and ``run_id`` correlation in traces and lifecycle hook contexts.
Package-owned shared helper surfaces are synchronized where they are shared.
Caller-provided mutable tool handlers and lifecycle hooks remain caller-managed
for synchronization.
