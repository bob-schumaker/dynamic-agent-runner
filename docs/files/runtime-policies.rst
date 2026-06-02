
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
Other fields are preserved as policy metadata and should be documented honestly
until a scoped implementation enforces them.

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

.. header2:: Prompt-cache intent

Prompt-cache metadata is provider-neutral intent. It records stable prefix and
variable prompt-part expectations and emits trace evidence, but provider-specific
request pass-through remains deferred until SDK/API support is verified.

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

.. header2:: Runtime behavior overrides

Runtime behavior overrides can patch ``llm_step`` prompts and skill references
without mutating generated artifacts. Initial support is limited to inline skill
instructions and prompt-role placement. Arbitrary ``SKILL.md`` source-path
resolution remains deferred until trust, packaging, precedence, and loading rules
are specified.

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

The current runtime preserves and validates this metadata only. It does not yet
implement a live approval engine, execution pause, resumable checkpoint store,
or resume-token protocol.

.. header2:: Async-session metadata

Future multi-turn or resumable workflow intent can be preserved under
``runtime.execution_policy.async_session``.

.. code-block:: yaml

   runtime:
     execution_policy:
       async_session:
         mode: conversational
         persist: external_checkpoint
         history: full
         session_id_state_key: session.id
         session_messages_state_key: session.messages

The current runtime preserves and validates this metadata only. It does not yet
implement runner-owned session storage, transcript replay, summary generation,
or automatic cross-run message reuse. Persisted policies must still satisfy the
implemented fail-closed validation rules, including a required
``session_id_state_key`` when ``persist`` is not ``none`` and omission of
``session_messages_state_key`` when ``history`` is ``none``.

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
