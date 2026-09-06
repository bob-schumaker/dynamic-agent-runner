# Agent Runtime Package Artifacts

## Purpose

Use this reference when `agent-development` emits implementation-oriented
artifacts for a conceptual external runtime. A runtime package is a portable
design bundle for another library to build or configure an agent; it does not
replace this repository's rules or skills.

For concrete examples beyond the minimal smoke-test package, see:

- `corpus/capabilities/agent-development/references/examples/evidence-loop-research-agent-runtime.yaml`
- `corpus/capabilities/agent-development/references/examples/evidence-loop-research-agent-graph.mmd`
- `corpus/capabilities/agent-development/references/examples/multi-agent-coordination-agent-runtime.yaml`
- `corpus/capabilities/agent-development/references/examples/multi-agent-coordination-agent-graph.mmd`
- `corpus/capabilities/agent-development/references/examples/persistent-goal-workflow-runtime.yaml`
- `corpus/capabilities/agent-development/references/examples/persistent-goal-workflow-graph.mmd`
- `corpus/capabilities/agent-development/references/examples/event-driven-triage-agent-runtime.yaml`
- `corpus/capabilities/agent-development/references/examples/event-driven-triage-agent-graph.mmd`

## Artifact set and packaging

Recommended layout:

```text
<design-dir>/
  agent-design.md
  agent-runtime.yaml
  agent-graph.mmd
  skill-bundle/
```

- `agent-runtime.yaml` — structured source of truth for runtime construction
- `agent-graph.mmd` — Mermaid view derived from the YAML
- `skill-bundle/` — copied or distilled skill support files needed by nodes

Packaging modes:

- `hybrid_bundle` — prompts and manifest metadata inline in YAML; larger skills
  and support files bundled beside it. Recommended default.
- `inline_only` — all prompts, tool descriptions, and skill text embedded in
  YAML. Use only for small packages.
- `bundled_only` — YAML references external package files for most prompt and
  skill content.

## Runtime manifest sections

For `format_version: 1`, the manifest contract uses a small executable root plus
three grouped maps for optional complexity:

```yaml
format_version: 1
package_type: dynamic_agent_design
package_id: <id>
name: <optional>
description: <optional>
entrypoint: <node id>
mermaid_diagram: agent-graph.mmd
packaging: {}
nodes: []
edges: []
tools: []
skills: []
output_contracts: []
validation: {}
runtime: {}
metadata: {}
extensions: {}
```

Required top-level fields are:

- `format_version`
- `package_type`
- `package_id`
- `entrypoint`
- `packaging`
- `nodes`
- `edges`

Optional root execution collections are:

- `tools`
- `skills`
- `output_contracts`
- `validation`

Optional grouped maps are:

- `runtime` — executable policy and runtime-owned state a consumer may validate
  or enforce
- `metadata` — design and planning metadata a consumer should preserve and expose
  but not enforce by default
- `extensions` — optional capability declarations using a common extension
  envelope

Do not add new optional fields at the manifest root for runtime policy, design
metadata, or future capability declarations. Place those fields under the
appropriate grouped map.

### Core vs extension manifest contract

Use the smallest manifest surface that keeps execution, metadata, and optional
capabilities distinct.

| Class | Location | Examples | Runtime behavior |
| --- | --- | --- | --- |
| Core executable | root | `nodes`, `edges`, `entrypoint` | validate and enforce |
| Runtime policy | `runtime` | `execution_policy.max_iterations`, `execution_policy.prompt_cache`, `state.artifacts` | validate and enforce where implemented |
| Capability declaration | `extensions` | `mcp`, `sessions`, `sandbox`, `guardrails`, `approvals` | fail, warn, or preserve based on extension support and `required` |
| Design metadata | `metadata` | `patterns_present`, `phases`, `roles`, `modes`, `participant_groups`, `runtime_surface` | preserve and expose, not enforce by default |

### Runtime policy

`runtime` contains policy or state that a runtime may use while preparing or
executing the graph.

Every generated runtime package must include
`runtime.execution_policy.exit_strategy`. This is the portable no-infinite-loop
contract for the package. Record at least:

- terminal conditions that end the run
- what the runtime should do when iteration, step, evidence, or time budgets are
  exhausted
- how ambiguous completion is handled

When a manifest includes any `loopback` edge or repeatable tool/model cycle,
also include positive `runtime.execution_policy.max_iterations` and
`runtime.execution_policy.max_steps` values. Do not leave loop bounds as
`unknown` in generated looping workflows.

Recommended lightweight shape:

```yaml
runtime:
  execution_policy:
    autonomy_level: <assistive | supervised_agent | bounded_autonomous | high_autonomy>
    allowed_execution_modes:
      - sequential_fallback
    external_backend_allowed: <yes | no | conditional>
    max_iterations: <number or unknown>
    max_steps: <number or unknown>
    timeout: <duration or unknown>
    exit_strategy:
      terminal_conditions:
        - <final output produced>
        - <escalation emitted>
      on_exhaustion: <finalize_with_caveats | escalate | fail_closed | return_partial>
      ambiguous_completion: <retry_with_limit | clarify | escalate | fail_closed>
    approval_required_for:
      - <side-effecting action>
    forbidden_actions:
      - <forbidden action>
    prompt_cache:
      enabled: <true | false>
      strategy: stable_prefix
      min_prefix_tokens: <positive integer; omit when unknown>
      prefix_parts: []
      variable_parts: []
      cache_key_hint: <package_id | package_id_and_version | none | runtime_default>
      provider_hints: {}
  state:
    artifacts: []
    mutable_fields: []
```

### Design metadata

`metadata` carries implementation-ready design decisions into a runtime package
without making them primitive execution fields. Prefer concise metadata and links
to `agent-design.md` over duplicated prose.

Recommended lightweight shape:

```yaml
metadata:
  patterns_present: []
  participant_groups: []
  modes: []
  phases: []
  roles: []
  runtime_surface:
    type: stateful_session_runtime
    owner: <runtime, host, provider, or unknown>
  workspace_boundary:
    type: resumable_workspace
    snapshot_strategy: <none | on_approval | scheduled | runtime_default>
  completion_contract:
    mechanism: terminal_completion_tool
    ambiguous_completion: escalate
  result_surfaces:
    final_output: true
    continuation_state: true
    audit_records: true
  permission_profile:
    filesystem: restricted_roots
    network: allowlist
  approval_channels:
    - workspace_mutation
  action_policy:
    source: <policy file, inline id, or unknown>
  sandbox_enforcement:
    filesystem_backend: <runtime_default | provider | host | none>
  network_policy:
    mode: <forbidden | direct | proxied | allowlist_first>
  mutation_safety:
    changed_state_provenance: <patch_diff | vcs_diff | runtime_diff | unknown>
  tool_exposure:
    strategy: <direct | deferred | namespace_grouped | connector_filtered>
  context_pipeline:
    model_visible_inputs: <summary or reference>
  instruction_authority:
    precedence: <summary or reference>
  trace_bundle:
    payload_capture: <none | redacted | full | conditional>
  evidence_model:
    model_visible: <summary or reference>
    runtime_only: <summary or reference>
  rag_pipeline:
    retrieval_mode:
      <keyword | structured | embedding_semantic | graph | hybrid | unknown>
    embedding_capability: <required | optional | not_applicable | unknown>
    graph_capability: <required | optional | not_applicable | unknown>
    index_owner: <runtime | host | external_service | unknown>
    graph_store_owner: <runtime | host | external_service | unknown>
    corpus_boundary: <summary or reference>
    chunking_policy: <summary or reference>
    graph_schema: <ontology/schema reference or unknown>
    entity_extraction_policy: <summary or reference>
    relationship_extraction_policy: <summary or reference>
    traversal_policy: <summary or reference>
    metadata_filters: []
    reranking: <none | model | vector_score | graph_score | hybrid | unknown>
    freshness_policy: <on_write | scheduled | manual | unknown>
    provenance_required: <true | false | conditional>
  event_contracts:
    - id: <event id>
      producer: <component>
      consumer: <component>
  goals:
    - id: <goal id>
      terminal_statuses: [succeeded, failed, canceled]
```

Guidance:

- Keep values provider-neutral unless provider-specific hints are nested under a
  provider-specific object.
- Use `unknown` or omit a field when the design has not made that decision.
- Treat approval channels as user or policy interaction points, not enforcement
  guarantees.
- Use sandbox, network, and mutation metadata to describe runtime enforcement or
  known enforcement gaps.
- Distinguish model-visible evidence from runtime-only evidence so downstream
  runtimes do not accidentally expose raw traces, terminal payloads, or tool
  payloads to the model.

#### Handoff vs agent-as-tool metadata

Represent multi-agent ownership changes and delegated specialist calls as
portable `metadata`, not as new primitive node kinds.

- **handoff** transfers active ownership of the workflow or session from one
  agent profile, role, or runtime context to another. The downstream consumer
  should preserve enough continuation state for the new owner to resume as the
  active executor.
- **agent-as-tool** delegates a bounded subtask to another agent-like capability
  while the current workflow remains the active owner. The delegated call returns
  a result into the current flow the same way another tool would.

Recommended grouped shape:

```yaml
metadata:
  handoffs:
    - id: planner_to_executor
      kind: ownership_transfer
      from_role: planner
      to_role: executor
      trigger: approval_granted
      carries:
        - task_brief
        - acceptance_criteria
        - unresolved_risks
  delegated_agents:
    - id: research_specialist
      tool_id: research-agent
      delegation_mode: bounded_subtask
      returns_to: coordinator
      result_contract:
        type: structured_report
```

Guidance:

- Use `metadata.handoffs` for ownership-transfer semantics, active profile
  changes, resumable continuation boundaries, or explicit execution takeover.
- Use `metadata.delegated_agents` when another agent is exposed through the tool
  surface and returns into the current execution path.
- Keep these shapes descriptive and portable. Runtime-specific execution,
  sandboxing, session plumbing, or adapter details belong in `runtime` or in a
  consumer-owned implementation layer.
- Preserve compatibility with the existing graph model: handoff and
  agent-as-tool semantics may coexist with `phases`, `participant_groups`,
  `roles`, and `modes`, but they should not replace ordinary control-flow edges.

#### Approval and interruption metadata

Represent approval-sensitive and interruption-aware behavior as a split between
portable descriptive `metadata`, enforceable `runtime` policy, and optional
consumer-specific `extensions.approvals` capabilities.

Recommended grouped shape:

```yaml
metadata:
  approval_interactions:
    - target:
        tool_id: deploy-production
      approval_sensitivity: high_risk_write
      approval_message: Confirm production deployment and maintenance window.
      interruptible: true
      resumability: expected
  approval_channels:
    - workspace_mutation

runtime:
  execution_policy:
    approval_required_for:
      - production_deploy
      - destructive_write

extensions:
  approvals:
    required: false
    config: {}
```

Guidance:

- Use `metadata.approval_interactions` for portable, human-facing semantics such
  as approval sensitivity/category, rationale or approval message,
  interruptibility, and resumability expectations.
- `approval_message` should explain why approval may be needed in a way a human
  reviewer or host UI can expose directly, without assuming one runtime-specific
  approval engine.
- `interruptible` describes whether the operation may pause safely before or
  during execution. `resumability` describes whether the package expects the
  consumer runtime to support resuming afterward.
- Use `runtime.execution_policy` only for behavior a consumer runtime may
  validate or enforce, such as approval gates for action classes.
- Use `extensions.approvals` only when a downstream runtime needs richer,
  consumer-specific approval capabilities beyond the portable metadata and base
  runtime policy.
- Keep interruption and resume metadata descriptive. Concrete pause tokens,
  checkpoint storage, UI flows, session restoration, or durable resume engines
  remain consumer-owned implementation details.

For evidence-heavy designs, a short metadata pattern such as `evidence_loop`
fits well as a workflow overlay when the runtime intentionally:

- starts with the least expensive adequate evidence path
- applies an explicit sufficiency gate before expanding retrieval
- uses structured evaluator output such as `missing_information` to drive the
  next retrieval queries
- enforces retrieval-depth budgets, retry limits, or escalation thresholds
- distinguishes normalized model-visible evidence from raw runtime-only payloads

When that pattern is present, prefer metadata and node contracts that make the
gate visible: evaluator or callable-specialist roles, `decision_step` sufficiency
checks, explicit retrieval budgets in `runtime.execution_policy`, and layered
observability in `metadata.trace_bundle`.

### Capability extensions

`extensions` declares optional capability modules. Each extension uses a uniform
envelope:

```yaml
extensions:
  <extension-id>:
    required: <true | false>
    config: {}
```

Generic extension validation behavior:

- Unsupported extension with `required: true` fails closed.
- Unsupported extension with `required: false` is preserved and reported when the
  consumer has a warning or report channel.
- Supported extension with invalid `config` shape fails closed.
- Malformed extension envelopes fail validation.

This repository currently defines the generic envelope and fail-closed behavior.
Concrete per-extension schemas for capabilities such as `mcp`, `sessions`,
`sandbox`, `guardrails`, and `approvals` should be added only when a downstream
runtime needs them.

## Versioning and compatibility

`format_version: 1` is a runtime package contract.

This first coordination round intentionally resets the draft optional-field
contract to the grouped `runtime`, `metadata`, and `extensions` shape. Backward
compatibility with the older flat optional-field draft shape is not required or
desired.

Runtime consumers should:

- reject or report legacy flat optional fields such as `execution_policy`,
  `state`, `patterns_present`, `participant_groups`, `modes`, `phases`, `roles`,
  `runtime_surface`, `workspace_boundary`, and `completion_contract` at the
  manifest root
- fail closed when required fields are missing or when a known field has an
  unsupported enum value
- fail closed when an unsupported extension is marked `required: true`
- preserve and report unsupported extensions marked `required: false` when a
  warning or report channel exists
- record whether a runtime consumed the package exactly, with warnings, or after
  explicit migration

Removing required fields, renaming node kinds, changing decision subtype names,
or changing edge semantics requires a new format version.

## Node kinds and decisions

Use these primary execution node kinds:

- `llm_step` — model call for planning, generation, critique, synthesis,
  extraction, classification, or role response.
- `tool_use_step` — actual tool invocation or adapter call in the workflow.
- `decision_step` — branch or gate.

Allowed decision subtypes:

- `tool_response_compare` — compare a tool result against criteria, thresholds,
  or expected shape.
- `simple_check` — deterministic check such as boolean, count, presence, schema,
  mode, permission, or status.
- `llm_route` — LLM selects one route from allowed paths.

Preserve the small primitive node taxonomy. Represent multi-agent, Council-like,
debate-like, or handoff structure as metadata, phases, participant groups, modes,
and edges rather than new primitive node kinds.

### Provider-neutral model requirements for `llm_step`

Use `model_requirements` on `llm_step` nodes when the implementor needs guidance
for model selection without naming a provider or model. These fields describe the
capabilities, reasoning depth, context needs, and operational tradeoffs required
by the node.

Recommended shape:

```yaml
- id: <llm-node-id>
  kind: llm_step
  model_requirements:
    required_capabilities:
      - <supports_structured | supports_functions | embeddings>
      - <supports_vision | input_modalities | supports_json_mode>
      - <code_reasoning | math_reasoning>
    reasoning_profile:
      level: <minimal | low | medium | high | extended>
      task_type: <classification | extraction | generation | planning>
      task_subtype: <critique | synthesis | tool_selection | route_selection>
      uncertainty_handling: <answer_with_caveats | ask_clarification | escalate>
    context_requirements:
      expected_input_size: <small | medium | large | very_large | unknown>
      context_window: <tokens or unknown>
      needs_retrieved_context: <true | false | conditional>
    output_requirements:
      format: <free_text | structured_json | schema_ref | tool_call>
      schema_ref: <output-contract-id or null>
      evidence_citations: <required | preferred | not_needed>
    operational_preferences:
      latency_sensitivity: <low | medium | high>
      cost_sensitivity: <low | medium | high>
      determinism: <preferred | balanced | creative>
      data_boundary: <local_only | private_runtime | provider_allowed | unknown>
    fallback_policy:
      if_unavailable: <use_lower_capability | use_higher_capability | escalate>
      minimum_acceptable_level: <minimal | low | medium | high | extended>
```

Guidance:

- Treat `model_requirements` as model-selection guidance, not as a provider API
  contract.
- Use `required_capabilities` for features a selected model or runtime adapter
  must support before the node can execute safely.
- Prefer registry-native capability names such as `supports_structured`,
  `supports_functions`, `supports_json_mode`, `supports_vision`, and
  `input_modalities` for model-fact capability requirements.
- Use `embeddings` when the node or its runtime adapter must create, compare, or
  consume vector representations for semantic search, clustering, deduplication,
  reranking, memory retrieval, or similar embedding-backed behavior.
- Keep context size as an explicit fact such as
  `context_requirements.context_window` rather than a derived label such as
  a workflow-defined long-context threshold. Treat that threshold as local
  selection policy layered on top of the numeric window.
- Use `reasoning_profile.level` to express task complexity, not hidden chain-of-
  thought visibility. Do not require raw reasoning traces as output.
- Use `reasoning_profile.task_type` and `task_subtype` to help implementors route
  simple classification, extraction, or formatting nodes to cheaper models while
  reserving stronger models for planning, synthesis, critique, tool selection,
  code reasoning, math reasoning, or high-stakes decisions.
- Use `context_requirements` to capture context-window pressure independently of
  reasoning difficulty.
- Use `operational_preferences` to expose cost, latency, determinism, and data
  boundary tradeoffs without forcing a specific vendor.
- Use `fallback_policy` to say whether a runtime may use a lower-capability model,
  should escalate to a stronger model, or must stop for human direction.
- When both `prompt.output_schema_ref` and
  `model_requirements.output_requirements.schema_ref` are present, they should
  name the same output contract unless the package explains the difference.

Runtime mapping guidance:

- Treat `model_requirements` as runtime-consumer selection input, not as request
  fields to pass through to a provider unchanged.
- Map `required_capabilities` to explicit model-registry or adapter facts before
  execution. If a required capability is unavailable, follow `fallback_policy`
  or stop with a clear unmet-capability report.
- Use `reasoning_profile`, `context_requirements`, `output_requirements`, and
  `operational_preferences` to rank compatible candidates according to local
  runtime policy. Cost, latency, determinism, data-boundary, and provider
  availability decisions belong to the runtime, not to the upstream package.
- Apply provider-specific parameters only through an adapter that explicitly
  supports the selected behavior. Unsupported provider hints should be ignored,
  preserved, or reported as metadata-only according to the runtime's capability
  reporting contract.

## ReAct-style loop manifests

A ReAct-style agent can be represented in `format_version: 1` without adding a
new primitive node kind. Use the existing node taxonomy:

- `llm_step` for the reasoning or thought step that chooses the next safe action
- `tool_use_step` for the action step that invokes a declared tool
- `decision_step` for observation evaluation, termination checks, and route
  selection
- `loopback` edges to return from observation evaluation to the next reasoning
  step

Recommended manifest conventions:

- include `react_loop` in `metadata.patterns_present`
- declare `runtime.execution_policy.max_iterations` and
  `runtime.execution_policy.max_steps`
- declare `runtime.execution_policy.exit_strategy` with terminal conditions for
  final answer, exhausted limits, and escalation
- model loop state under `runtime.state.artifacts`, including the user goal,
  reasoning trace summary, selected action, model-safe tool observation, and
  final answer
- expose only approved tools through `available_tools`
- use `tool_use_step.tool_id` for actual tool execution
- route through an executable `llm_route` `decision_step` before tool use so the
  model can choose `tool` or `final`
- preserve raw tool outputs as runtime-only state when needed, but pass only a
  model-safe observation summary back into the next `llm_step`

For implementation-oriented ReAct packages, prefer this executable route-gated
shape:

```text
reason -> route_action
route_action -> act          when route == tool
route_action -> final_answer when route == final
act -> reason
```

Do not emit an unconditional `llm_step -> tool_use_step` edge for ReAct. That
shape forces another tool call even when the model has enough evidence to answer.
Use `decision_subtype: llm_route`, `route_from: <reason-node-id>`, and branch
edge `condition` values matching the allowed route ids. Reserve `simple_check`
for deterministic runtime checks that the consumer runtime actually executes.

Current validator and traversal behavior may require both an executable return
edge and a metadata loopback edge from the tool node back to the reasoning node:

```yaml
- from: search_knowledge_step
  to: reason
  edge_kind: sequential
  condition: observation available

- from: search_knowledge_step
  to: reason
  edge_kind: loopback
  condition: observation available
```

Keep both edges in generated packages until the downstream runtime can execute
`loopback` edges directly or the validator stops requiring loopback metadata.
Use the sequential edge as the executable control-flow return and the loopback
edge as compatibility metadata.

When prompt rendering uses Python `.format(...)` syntax, use single-brace
variables such as `{prompt}`. For conceptual external runtime examples, prefer a
runtime-provided `{prompt}` key for the original user request instead of an
uninitialized custom state key such as `{user_goal}`. Avoid first-turn references
to state keys that may not exist yet; prefer a runtime-provided aggregate such as
`{node_outputs}` or named state keys only after the graph has guaranteed they
have been written.
When a user asks for a working package, include a small host runner or test
harness that constructs the tool registry entries required by the consumer
runtime; manifest tool metadata alone is not enough to execute a tool call. In
generic examples, prefer pseudocode for host runner shape rather than naming
unstable runtime APIs.

`runtime.execution_policy.react_loop` may describe observation, termination, and
escalation policy for runtimes that consume those fields. The repository-local
validator does not require that optional policy object today; it enforces the
structural ReAct contract triggered by `metadata.patterns_present: react_loop`.

A ReAct loop must have explicit termination criteria. Do not rely on the model to
decide indefinitely. Runtime consumers must enforce iteration, step, timeout, and
exit-strategy limits from `runtime.execution_policy`.

Minimal ReAct graph shape:

```text
reason -> route_action
route_action -> search_knowledge_step  when route == tool
search_knowledge_step -> reason
route_action -> final_response         when route == final
```

## RAG, GraphRAG, and embedding-backed retrieval manifests

A RAG workflow can be represented in `format_version: 1` without adding a new
primitive node kind. Use existing graph pieces:

- `tool_use_step` for retrieval, index lookup, graph lookup, subgraph traversal,
  reranking, or context assembly
- `llm_step` for query planning, answer synthesis, critique, or citation-aware
  response generation
- `decision_step` for retrieval sufficiency, empty result handling, freshness
  checks, and fallback routing

Recommended manifest conventions:

- include `rag` and, when applicable, `embedding_retrieval`, `graph_retrieval`,
  or `graphrag` in `metadata.patterns_present`
- describe retrieval policy under `metadata.rag_pipeline`
- add `embeddings` to `llm_step.model_requirements.required_capabilities` when a
  model or runtime adapter must generate or consume embedding vectors for that
  step
- use `metadata.rag_pipeline.graph_capability: required` when the workflow
  depends on entity/relation graph construction, graph queries, traversal, or
  subgraph evidence assembly
- keep citation expectations under
  `model_requirements.output_requirements.evidence_citations` or other workflow
  output contracts rather than treating citation behavior as a base capability
  term
- model retrieved chunks, citations, source metadata, and retrieval scores as
  runtime state artifacts when they affect synthesis or auditability
- for GraphRAG, also model entities, relationships, graph paths, selected
  subgraphs, ontology or schema versions, and graph-derived claim provenance when
  those affect synthesis or auditability
- keep raw source documents and raw vector-store payloads runtime-only unless the
  design explicitly makes them model-visible
- keep raw graph-store payloads runtime-only unless the selected subgraph or
  graph evidence is intentionally model-visible
- route weak, stale, empty, or low-confidence retrieval through a `decision_step`
  that can deepen retrieval, ask for clarification, answer with caveats, or
  escalate

Minimal embedding-backed RAG graph shape:

```text
plan_query -> retrieve_context -> evaluate_retrieval -> synthesize_answer
                      |                    |
                      v                    v
                 rerank_context       clarify / escalate
```

Minimal GraphRAG graph shape:

```text
plan_query -> retrieve_seed_context -> expand_subgraph -> evaluate_graph_evidence
                                                  |                    |
                                                  v                    v
                                           rank_graph_context     synthesize_answer
```

## Prompt fields

`llm_step` nodes and `llm_route` decision nodes may include:

```yaml
prompt:
  system: |
    <role and durable behavior>
  developer: |
    <runtime/tool/policy instructions>
  user_template: |
    <template using declared input variables>
  input_vars:
    - evidence_bundle
  output_schema_ref: <optional schema or output contract id>
```

Prompts should not embed secrets, credentials, or high-risk personal data.

## Prompt cache intent

Runtime manifests may declare provider-neutral prompt-cache intent under
`runtime.execution_policy.prompt_cache`. This describes how stable prompt
material should be ordered for runtimes that support token-level prompt caching.
Runtime consumers must still validate actual eligibility after rendering the
effective request.

Recommended fields:

```yaml
runtime:
  execution_policy:
    prompt_cache:
      enabled: true
      strategy: stable_prefix
      min_prefix_tokens: 1024
      prefix_parts:
        - system
        - developer
        - skill_instructions
        - tool_schemas
        - x-<runtime-extension-part>
      variable_parts:
        - user_prompt
        - run_state
        - x-<runtime-extension-part>
      cache_key_hint: package_id
      provider_hints:
        openai:
          cache_key_strategy: package_id_and_version
          retention: auto
```

Field guidance:

- `enabled` — whether the package author intends to target prompt caching.
- `strategy` — for `format_version: 1`, use `stable_prefix` for repeated stable
  prompt material at the beginning of the rendered request.
- `min_prefix_tokens` — provider-neutral positive integer token target; omit when
  unknown. Runtimes may override or reinterpret per provider/model.
- `prefix_parts` — stable prompt components rendered before variable run content
  when doing so preserves semantics.
- `variable_parts` — run-specific components excluded from the cacheable prefix.
- `cache_key_hint` — provider-neutral hint such as `package_id`,
  `package_id_and_version`, or `none`.
- `provider_hints` — optional provider-specific hints. Runtime adapters interpret
  only providers and fields they explicitly support; hints are not mandatory API
  fields.

Canonical stable-prefix candidates: `system`, `developer`, `skill_instructions`,
`tool_schemas`, `role_definitions`, `output_contracts`, and
`workflow_structure`.

Canonical variable-part candidates: `user_prompt`, `run_state`,
`retrieved_context`, and `tool_results`.

Custom part names are allowed only with an `x-` prefix, for example
`x-domain-policy-context`, so runtimes can distinguish deliberate extensions from
misspelled canonical names.

Runtimes should not blindly trust cache intent. They should preserve stable-
prefix ordering when safe, estimate rendered prefix tokens when tooling is
available, emit observability such as cache eligibility and prefix hashes, allow
caller overrides or disablement, and report observed cached-token usage when the
provider returns it.

Do not make provider-specific request parameters mandatory in upstream packages.
For example, OpenAI-oriented fields such as cache-key strategy or retention stay
under `provider_hints.openai` until a runtime adapter confirms support.

## Tools registry

Use top-level `tools:` to describe tool capabilities made available to LLM nodes
or invoked by `tool_use_step` nodes.

Portable tool semantics belong in the manifest even when the runtime owns the
concrete implementation. Use tool fields to separate:

- portable semantic capability metadata, such as `tool_type`
- implementation/backend selection, such as `adapter`
- operational risk and policy hints, such as `side_effect` and
  `approval_required`

`tool_type` describes **what kind of capability** a tool represents, not how a
consumer runtime injects, hosts, or transports it. A runtime may implement the
same `tool_type` through local code, a runtime-owned adapter, MCP wiring,
host-provided connectors, scripts, or another backend.

Recommended tool fields:

```yaml
- id: <tool-id>
  label: <human label>
  description_for_llm: |
    <tool description shown to model nodes>
  tool_type:
    <file_read | file_write | web_search | web_fetch | shell_command |
    code_execution | structured_data_query | external_api | agent_tool |
    human_approval>
  adapter: <runtime adapter id or unknown>
  input_schema: {}
  output_schema: {}
  side_effect: <none | read | write | mutate | destructive>
  approval_required: <yes | no | conditional>
  timeout: <duration or unknown>
  retry_policy: <none | bounded | runtime_default>
  failure_behavior: <fail | fallback | escalate | retry>
  skill_bindings: []
```

Initial portable `tool_type` vocabulary:

- `file_read` — read or enumerate repository, workspace, or filesystem content
- `file_write` — create, update, move, or delete filesystem-backed content
- `web_search` — discover candidate remote resources through search
- `web_fetch` — retrieve known remote content without emphasizing broad search
- `shell_command` — invoke a shell or command runner
- `code_execution` — execute code or snippets in a language/runtime environment
- `structured_data_query` — query a database, index, graph, or structured store
- `external_api` — call an external service or application API
- `agent_tool` — delegate a bounded subtask to another agent-like capability
- `human_approval` — request, capture, or route human approval as a workflow step

Field-boundary guidance:

- `tool_type` is portable semantic metadata. It should stay stable across
  consumer runtimes even when the implementation backend changes.
- `adapter` identifies the runtime-specific implementation path or integration
  handle. It is consumer-owned and may differ across runtimes for the same
  `tool_type`.
- `side_effect` describes the operational mutation risk of invoking the tool,
  not the capability class.
- `approval_required` communicates whether the tool normally needs an approval
  gate. It does not replace richer approval policy under `runtime` or optional
  approval-related extensions.

Short example:

```yaml
- id: repo-file-reader
  label: Repository file reader
  description_for_llm: |
    Read source files from the checked-out repository.
  tool_type: file_read
  adapter: runtime_file_reader
  input_schema:
    type: object
  output_schema:
    type: object
  side_effect: read
  approval_required: no
  timeout: 30s
  retry_policy: runtime_default
  failure_behavior: fail
  skill_bindings: []
```

LLM nodes use `available_tools` to declare local tool context. `tool_use_step`
nodes use `tool_id` to invoke a specific tool.

## Skills manifest and bindings

Use top-level `skills:` for package inventory and per-node or per-tool
`skill_bindings` for consumption.

Recommended skill fields:

```yaml
- id: <skill-id>
  source_type: <repo_skill | generated_skill | external_skill | distilled_reference>
  source_path: <repo-relative source path or external identifier>
  packaging_mode: <bundled_copy | distilled | referenced_only | inline_excerpt>
  bundled_path: <path under skill-bundle or null>
  support_files:
    - source_path: <path>
      bundled_path: <path>
```

Recommended binding usages:

- `instruction_context`
- `tool_adapter`
- `policy_context`
- `output_formatter`
- `shared_reference`

## Pattern, phase, and mode metadata

Use `metadata.patterns_present` for coarse design classification. Use
`metadata.phases`, `metadata.modes`, and `metadata.participant_groups` when a
graph needs multi-agent, debate, Council, parallel, or repeatable workflow
structure.

Useful phase kinds:

- `selection`
- `preparation`
- `parallel_fanout`
- `batched_fanout`
- `challenge_round`
- `aggregation`
- `decision_gate`
- `verification`
- `persistence`

Use `peer_visibility` to preserve independence boundaries:

- `none`
- `prior_round_outputs`
- `full_panel`

## Derived execution views for consumers

Runtime consumers should build a normalized internal view before adding optional
features to the execution loop. Recommended framework-neutral seams are:

- `ExecutionPlan` — normalized manifest view consumed by the runner. It resolves
  defaults, indexes node/edge/tool/skill identifiers, separates executable
  control flow from capability overlays, and records unsupported extension
  reports.
- `PreparedNode` — per-node normalized execution metadata. It should include the
  node kind, prompt source, allowed tools, skill bindings, state inputs and
  outputs, policy context, and any extension-derived capabilities that apply to
  that node.
- `PreparedModelInput` / `prepare_model_input(...)` — model-input preparation
  seam for prompt rendering, token budgeting, prompt-cache observation, session
  pruning, compaction, retrieved-context insertion, and hierarchical instruction
  ordering.
- `ToolOrigin` / `ToolSource` — provenance object for tools from the built-in
  registry, manifest declarations, companion tool indexes, runtime overrides,
  MCP discovery, or agent-as-tool sources.

These names are recommended design seams, not mandatory implementation classes.
A downstream runtime may choose different names if it preserves the same
responsibilities and reports unsupported or ignored manifest features honestly.

## Edge kinds

Recommended `edge_kind` values:

- `sequential`
- `branch`
- `loopback`
- `parallel_fanout`
- `parallel_join`
- `event`
- `capability` for derived tool-availability overlays

Execution uses control-flow edges. Tool availability uses overlay edges so a
capability is not confused with a tool call.

Edge semantics for `format_version: 1`:

- `sequential` — normal control transfer after source node completion.
- `branch` — conditional transfer from a decision or other branch-capable step;
  include a `condition` label.
- `loopback` — return to an earlier node or phase; consumers must enforce an
  iteration or timeout limit from `runtime.execution_policy`.
- `parallel_fanout` — start independent downstream branches that may run in
  parallel when supported.
- `parallel_join` — converge fanned-out branches; consumers should define whether
  all branches or a quorum is required.
- `event` — asynchronous or external event handoff; include enough state in
  `carries` for later continuation.
- `capability` — derived graph overlay showing that a node can access a tool; it
  is not an execution edge and must not be treated as a tool invocation.

## Validation, examples, and schema

Use the lightweight helper when available:

```bash
corpus/capabilities/agent-development/scripts/validate_agent_runtime.py \
  <design-dir>/agent-runtime.yaml \
  --mermaid <design-dir>/agent-graph.mmd
```

The helper checks required fields, supported enum values, node and edge
references, tool-use references, skill bindings, prompt presence for LLM nodes,
`llm_route` decision contracts, grouped metadata references, prompt-cache
metadata, ReAct loop contract requirements, extension envelopes, legacy
flat-field rejection, and optional Mermaid node-id consistency. It prefers PyYAML
and otherwise falls back to Ruby's standard YAML parser when `ruby` is available.

When `metadata.patterns_present` contains `react_loop`, the helper additionally
requires a positive `runtime.execution_policy.max_iterations`, a positive
`runtime.execution_policy.max_steps`, at least one `loopback` edge, at least one
`llm_step` with `available_tools`, at least one `tool_use_step`, an `llm_route`
decision gate with `tool` and `final` branches, no unconditional
`llm_step -> tool_use_step` execution edge, and a model-safe observation state
artifact. For all manifests, the helper also requires
`runtime.execution_policy.exit_strategy`; for any loopback graph it rejects
unknown loop bounds.

Packaged examples and supporting files:

- `corpus/capabilities/agent-development/references/examples/simple-tool-agent-runtime.yaml`
- `corpus/capabilities/agent-development/references/examples/simple-tool-agent-graph.mmd`
- `corpus/capabilities/agent-development/references/examples/react-tool-agent-design.md`
- `corpus/capabilities/agent-development/references/examples/react-tool-agent-runtime.yaml`
- `corpus/capabilities/agent-development/references/examples/react-tool-agent-graph.mmd`
- `corpus/capabilities/agent-development/references/examples/react-tool-agent-host-pseudocode.md`
- `corpus/capabilities/agent-development/references/examples/evidence-loop-research-agent-runtime.yaml`
- `corpus/capabilities/agent-development/references/examples/evidence-loop-research-agent-graph.mmd`
- `corpus/capabilities/agent-development/references/examples/multi-agent-coordination-agent-runtime.yaml`
- `corpus/capabilities/agent-development/references/examples/multi-agent-coordination-agent-graph.mmd`
- `corpus/capabilities/agent-development/references/examples/persistent-goal-workflow-runtime.yaml`
- `corpus/capabilities/agent-development/references/examples/persistent-goal-workflow-graph.mmd`
- `corpus/capabilities/agent-development/references/examples/event-driven-triage-agent-runtime.yaml`
- `corpus/capabilities/agent-development/references/examples/event-driven-triage-agent-graph.mmd`
- `corpus/capabilities/agent-development/references/examples/tool-index.yaml`
- `corpus/capabilities/agent-development/schemas/agent-runtime.schema.json`
- `tests/test_agent_runtime_validator.py`

Use the simple runtime and graph as smoke-test shapes: one LLM request-analysis
node, one `tool_use_step`, one `llm_route` decision, and two possible LLM
follow-up nodes. Use the multi-agent, persistent-goal, event-driven, and
evidence-loop examples when the runtime package needs coordination,
long-running state, event ingress, or evaluator-gated retrieval shapes. Use
`tool-index.yaml` when multiple manifests should share a portable tool catalog.
A concrete `agent-runtime.yaml` should reference only the
tools it exposes to a given LLM node or invokes from a `tool_use_step`.

Use the ReAct runtime and graph as a smoke-test shape for a bounded
observe-think-act loop: one reasoning `llm_step` with approved available tools,
one `llm_route` gate, one `tool_use_step`, `tool` and `final` branch paths, an
executable return edge plus loopback metadata, explicit iteration and timeout
policy, explicit exit strategy, model-safe observation state, runtime-native
`{prompt}` access for the original request, and host-side pseudocode showing
ToolRegistry setup responsibilities.

The schema is intentionally partial; use the validator for cross-reference and
Mermaid consistency checks. Validator regression coverage protects both the
semantic validator API and packaged smoke-test example.

When changing validator or `format_version: 1` semantics, update tests so they
remain a contract for the repository-local validator.

## Mermaid mapping

Recommended rendering conventions:

- `llm_step` as a process node labeled `LLM: <label>`
- `tool_use_step` as a process node labeled `Tool Use: <label>`
- `decision_step` as a diamond
- tool capability registry entries as sidecar database/cylinder-style nodes
- `available_tools` as dashed `can call` edges when a tool overlay is requested
- phases as Mermaid `subgraph` blocks when useful

## Authority and portability

Generated packages may include skills copied from this repository, but the
runtime package does not automatically inherit repository policy authority. When
a packaged skill references governing rules, preserve those references in
metadata and disclose whether they are bundled, summarized, or external.

Do not package unrelated local paths, credentials, personal data, or
machine-specific assumptions. Prefer repository-relative source paths and
portable bundle paths.
