# Internal Graph Mutation Implementation Plan

Status: In progress

- Current checkpoint: T1.4 execution-plan mutation integration is committed in
  `src/dynamic_agent_runner/models.py` and
  `src/dynamic_agent_runner/graph_mutation.py` with focused GREEN evidence in
  `tests/test_graph_mutation.py` and `tests/test_executor.py`, while T1.1 RED
  validation evidence remains active in `tests/test_validation.py`.
- Current evidence:
  - `poetry run pytest tests/test_graph_mutation.py -q` passes with the focused
    internal mutation datamodel and protocol checks.
  - `poetry run pytest tests/test_executor.py -q` passes with the expected
    mutation-bundle and per-node mutation-preparation seam assertions.
  - `poetry run pytest tests/test_validation.py -q` fails with the expected
    missing-contract and ineligible-node attachment cases.
- Next overall task gate: T1.5 fail-closed attachment-metadata validation.
- Next implementation steps that can satisfy the current RED evidence:
  - T1.5 fail-closed attachment-metadata validation
  - T2.1 prepared-input RED coverage after validation closes

## Goal

Plan the first implementation path for an internal compile-time graph-mutation
layer that attaches context-pruning preparation to selected `llm_step` nodes
without mutating base workflow artifacts, introducing a public mutation schema,
or coupling the design to a single local-model transport.

## Spec Trace

- Spec: `specs/internal-graph-mutation/spec.md`
- Related repo guardrails:
  - `specs/dynamic-agent-runner/spec.md`
  - `specs/dynamic-agent-runner/references/graph-mutation-interface-design.md`
  - `specs/async-session-memory-pipeline/spec.md`
  - `specs/llama-cpp-local-model/spec.md`
- Constitution: none; repository rules plus the approved feature spec are the
  active guardrails for this feature

## Technical Summary

- The first slice should add a repository-owned internal mutation layer that is
  applied during workflow preparation, parallel to current runtime behavior
  overrides.
- The first implementation should prefer **input-transform mutation** over true
  derived-node insertion.
- Portable workflow manifests should opt into mutation through small explicit
  node metadata such as `context_pipeline`, `context_sources`, and
  `context_contract`.
- The runtime should keep base workflow packages immutable and resolve any
  mutation effect into derived prepared-node or prepared-input behavior.
- The first slice should reuse existing planning and execution seams — especially
  `prepare_execution_plan(...)` and `prepare_model_input(...)` — rather than
  adding a separate executor family.
- Semantic retrieval, embedding-model choice, Hugging Face configuration, and
  top-K ranking internals should remain runtime-owned details behind strategy or
  profile identifiers rather than becoming required portable manifest fields.

## Source Artifacts

- `specs/internal-graph-mutation/spec.md` — authoritative feature intent and
  boundaries
- `specs/dynamic-agent-runner/references/graph-mutation-interface-design.md` —
  detailed design reference for the first mutation target and metadata shape
- `src/dynamic_agent_runner/models.py` — current runtime manifest, prepared-node,
  and execution-plan datamodels
- `src/dynamic_agent_runner/validation.py` — fail-closed validation engine for
  runtime manifests and execution metadata
- `src/dynamic_agent_runner/behavior.py` — existing derived overlay model that
  demonstrates the repository's compile-time derivation style
- `src/dynamic_agent_runner/executor.py` — current execution-plan preparation,
  prepared-input construction, and `llm_step` execution path
- `tests/test_validation.py` — primary manifest-validation test surface
- `tests/test_executor.py` — primary prepared-input and runtime-behavior test
  surface

## Current Repository State

- `RuntimeNode.raw` and `PreparedNode.raw` already preserve arbitrary manifest
  metadata, so the first slice can validate and consume explicit context-pipeline
  metadata without immediately committing to a large typed public manifest model
  expansion.
- `prepare_execution_plan(...)` already constructs the derived execution view
  used by the executor, which makes it the natural place to resolve or attach
  mutation behavior.
- `behavior.py` already demonstrates the repository's preferred pattern of
  derived behavior layered over immutable loaded artifacts.
- `prepare_model_input(...)` already performs model-input preparation, session
  pruning, hierarchy-based compaction, and file-context enrichment; that makes it
  the narrowest existing seam for an input-transform-style context-pruning
  mutation.
- `tests/test_validation.py` and `tests/test_executor.py` already contain focused
  coverage for fail-closed metadata validation and prepared-input behavior, so
  the graph-mutation feature can extend current test surfaces without needing a
  new end-to-end harness.

## Delivery Strategy

### Slice 1 — Mutation metadata contract and internal seam

Deliver the smallest architecture-first slice first:

- define the repository-owned internal mutation protocol and datamodels
- validate explicit node metadata for safe context-pipeline attachment
- apply mutation as a compile-time derivation layer without mutating the base
  loaded workflow
- keep the first mutation target limited to selected `llm_step` nodes

This slice establishes the architectural seam and fail-closed boundaries before
any richer pruning behavior is introduced.

### Slice 2 — Prepared-input mutation integration

Once the mutation seam exists, wire the first target into model-input
preparation:

- allow eligible `llm_step` nodes to route declared context inputs through an
  internal context-pruning mutation before the model call
- keep the implementation as a derived input transform rather than visible graph
  surgery
- emit clear preparation metadata and diagnostics so mutation activity is visible
  in tests and traces

This slice satisfies the spec's first real behavior target while keeping the
scope narrow.

### Slice 3 — Strategy/profile growth and future semantic pruning hooks

Only after Slices 1 and 2 are stable should later work consider:

- richer strategy or profile identifiers
- semantic ranking or embedding-backed pruning profiles
- tighter integration with local embedding follow-up work
- eventual evolution from input-transform behavior to true derived-node
  insertion if future use cases require it

This later slice must remain separate from llama.cpp transport ownership and any
public mutation-schema stabilization.

## Architectural Decision

### Chosen approach

Use an **internal compile-time input-transform mutation layer** that enriches
derived workflow or prepared-input behavior rather than editing base runtime
artifacts in place.

### Why this approach is preferred

- It matches the existing repository pattern of compile-time derivation and
  runtime-owned overlays.
- It keeps validation and execution changes narrow by building on
  `prepare_execution_plan(...)` and `prepare_model_input(...)`.
- It avoids early Mermaid/node-identity churn.
- It preserves room for a future move to true derived-node insertion if later
  features require it.

### Why true node insertion is not the first slice

- It would widen graph-validation and edge-rewiring complexity too early.
- It would increase drift risk between portable workflow artifacts and early
  runtime-only experimentation.

### Why a public YAML mutation schema is rejected for now

- The approved spec keeps mutation internals runtime-owned until the repository
  has enough experience to justify a stable artifact contract.
- The portable manifest only needs small explicit attachment metadata for the
  first slice.

### Why semantic embedding policy is deferred behind strategy/profile ids

- The first slice needs a safe mutation seam more than it needs a finalized
  semantic-retrieval backend.
- Embedding-model selection, cache policy, and retrieval internals belong to
  runtime-owned configuration and later follow-up work.

## Affected Areas

- `src/dynamic_agent_runner/graph_mutation.py` — new internal mutation protocol,
  datamodels, validation helpers, and first `ContextPruningMutation`
  implementation
- `src/dynamic_agent_runner/models.py` — any minimal prepared-node or
  execution-plan metadata needed to carry derived mutation behavior forward
- `src/dynamic_agent_runner/validation.py` — fail-closed validation for explicit
  `context_pipeline`, `context_sources`, and `context_contract` attachment
  metadata
- `src/dynamic_agent_runner/executor.py` — prepared-input integration point for
  applying mutation-derived context transformation before model execution
- `tests/test_validation.py` — attachment-metadata validation coverage
- `tests/test_executor.py` — prepared-input and mutation-integration coverage
- `tests/test_graph_mutation.py` — optional focused internal mutation-unit tests
  if a separate test surface improves clarity

## Architecture and Data Flow

### First-slice compile-time mutation flow

1. The runtime loads the immutable workflow package into `LoadedAgentWorkflow`.
2. Validation confirms whether any node opting into context-pipeline mutation has
   the required attachment metadata.
3. During `prepare_execution_plan(...)`, the runtime resolves internal mutation
   specs for eligible `llm_step` nodes.
4. The mutation layer enriches derived prepared-node behavior or companion plan
   metadata without mutating the base `RuntimeManifest`, `RuntimeNode`, or
   `RuntimeEdge` objects.
5. `prepare_model_input(...)` applies the resolved mutation-owned transform to
   declared context inputs before request construction.
6. The adapter path, request shaping, response handling, and executor node
   traversal remain repository-owned and otherwise unchanged.

### Proposed portable attachment metadata

Recommended first-shape metadata on eligible `llm_step` nodes:

```yaml
nodes:
  - id: answer
    kind: llm_step
    prompt:
      user_template: "Use {prepared_context} to answer {prompt}"
    context_pipeline:
      enabled: true
      strategy: semantic_pruning
      profile: default
    context_sources:
      - kind: conversation_history
        source: state.chat_history
      - kind: latest_user_prompt
        source: prompt
    context_contract:
      history_input: state.chat_history
      current_prompt_input: prompt
      output_slot: prepared_context
```

The first implementation may validate a narrower subset of this shape, but it
should preserve the same responsibility split:

- the manifest declares attachment intent and context boundaries
- the runtime owns how the mutation is actually executed

## Domain and Integration Boundaries

- Bounded context or owner: workflow preparation and prepared-input derivation
  inside `dynamic-agent-runner`
- Context relationship:
  - customer-supplier with the existing loader/validation/executor seams owned by
    this repository
  - separate-ways boundary for local embedding selection and deployment/runtime
    model provisioning
- Model translation:
  - portable manifest metadata -> internal mutation spec
  - internal mutation spec -> prepared input transformation and diagnostics
- Tactical pattern fit: typed internal datamodel plus narrow executor hook,
  rather than public schema or large runtime-family expansion
- Domain assumptions:
  - eligible workflow nodes can declare explicit context boundaries in manifest
    metadata
  - the first slice should remain input-transform only
  - semantic ranking details can remain deferred behind runtime-owned strategy
    or profile resolution

## Contracts

### Internal mutation contract

Suggested first internal module and contents:

```text
src/dynamic_agent_runner/graph_mutation.py
```

Suggested first contents:

- Implemented in T1.3:
  - `WorkflowGraphMutation` protocol
  - `MutationResult`
  - `GraphMutationSpec`
  - `WorkflowMutationBundle`
- Still pending in later slices:
  - `apply_workflow_mutations(...)`
  - `ContextPruningMutation`

### Executor integration contract

- Input:
  - `PreparedNode`
  - `ExecutionPlan`
  - declared context sources and contract metadata
  - current execution state prompt/session/context values
- Output:
  - prepared input parts that include the mutation-owned context result before
    model request construction
  - preparation diagnostics that show mutation application status

## Validation Strategy

Primary targeted checks for the first implementation slice:

```bash
poetry run pytest tests/test_graph_mutation.py -q
```

Current recorded checkpoint:

- T1.3 GREEN evidence was captured with:

  ```bash
  poetry run pytest tests/test_graph_mutation.py -q
  ```

- Observed result: `3 passed`
- Passing tests:
  - `test_workflow_mutation_bundle_can_describe_context_pruning_target`
  - `test_mutation_result_preserves_workflow_and_notices`
  - `test_workflow_graph_mutation_protocol_supports_apply_contract`
- T1.4 GREEN evidence was captured with:

  ```bash
  poetry run pytest tests/test_executor.py -q
  ```

- Observed result: `52 passed`
- Passing tests include:
  - `test_prepare_execution_plan_keeps_base_workflow_unchanged_for_context_pipeline_nodes`
  - `test_prepare_execution_plan_derives_mutation_preparation_for_eligible_llm_step`
- T1.1 RED evidence was captured with:

  ```bash
  poetry run pytest tests/test_validation.py -q
  ```

- Observed result: `2 failed, 53 passed`
- Failing tests:
  - `test_context_pipeline_attachment_requires_explicit_sources_and_contract`
  - `test_context_pipeline_attachment_rejects_non_llm_step_nodes`
For the current mixed checkpoint, widen to:

```bash
poetry run pytest \
  tests/test_graph_mutation.py \
  tests/test_validation.py \
  tests/test_executor.py -q
```

Formatting and repository-policy validation:

```bash
poetry run pre-commit run --files \
  specs/internal-graph-mutation/spec.md \
  specs/internal-graph-mutation/plan.md \
  specs/internal-graph-mutation/tasks.md \
  src/dynamic_agent_runner/graph_mutation.py \
  src/dynamic_agent_runner/models.py \
  src/dynamic_agent_runner/validation.py \
  src/dynamic_agent_runner/executor.py \
  tests/test_graph_mutation.py \
  tests/test_validation.py \
  tests/test_executor.py
```

## Risks and Tradeoffs

- If the first slice tries to finalize semantic retrieval details too early, it
  may couple the mutation contract to unresolved embedding/runtime decisions.
- If validation is too permissive, mutation attachment could drift into implicit
  prompt guessing and hidden coupling.
- If prepared-input integration becomes too special-case, the mutation seam may
  duplicate existing compaction or file-context behavior instead of composing with
  it.
- If node insertion is attempted too early, graph complexity may overshadow the
  higher-ROI input-transform path.

## Expected Deliverable

After the first implementation pass, the repository should have an authoritative
internal graph-mutation seam, explicit fail-closed attachment metadata for
eligible `llm_step` nodes, and a narrow context-pruning-oriented input transform
that integrates with existing preparation and execution boundaries without
changing the immutable portable workflow package contract.

At the current checkpoint, the repository has GREEN evidence for both the
internal mutation datamodel layer and the execution-plan mutation seam, while
fail-closed attachment validation and prepared-input mutation behavior remain
ahead.
