
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

.. header2:: Concurrency and async execution

The implementation is async-first. Synchronous public functions wrap the async
path and reject calls from an already-running event loop. Each run has isolated
execution state and ``run_id`` correlation in traces and lifecycle hook contexts.
Package-owned shared helper surfaces are synchronized where they are shared.
Caller-provided mutable tool handlers and lifecycle hooks remain caller-managed
for synchronization.
