# Graph Mutation Interface Design

## Goal

Design an **internal-only** graph mutation interface for `dynamic-agent-runner`
so the runtime can inject or transform workflow structure before execution,
starting with an internal LLM context-pruning pipeline.

## Current Runtime Seams Relevant to Mutation

- The runtime already distinguishes between:
  - an **immutable base package** (`agent-runtime.yaml`, `agent-graph.mmd`,
    `agent-design.md`, `skill-bundle/`)
  - **caller-owned override layers** compiled into a derived execution-ready
    workflow
- `prepare_execution_plan(...)` is already the main compile/preparation phase for
  turning loaded artifact models into execution-ready node/edge structures.
- `behavior.py` already applies a derived overlay model for prompt and skill
  behavior without mutating source artifacts in place.

These are strong signals that graph mutation should be modeled as another
**compile-time derivation layer**, not as in-place mutation of the loaded base
workflow.

## Recommendation Summary

### 1. Use a separate internal mutation definition shape

Do **not** define graph mutation as another full agent workflow definition.

Instead, define a smaller internal mutation contract that operates **on** an
already-loaded workflow graph.

Why:

- a mutation is not an executable workflow on its own
- reusing the full workflow-definition shape would duplicate node/edge semantics
  unnecessarily
- the first use case is structural adaptation of an existing graph,
  not loading a second graph and merging two equal peers
- a compact mutation contract is easier to validate, reason about, and keep
  internal while the design evolves

### 2. Apply mutation during compilation/preparation

Recommended pipeline:

1. load immutable base workflow package
2. apply runtime behavior overrides
3. apply internal graph mutations
4. validate the derived graph
5. prepare the final execution plan

This keeps mutation in the same conceptual layer as existing override-driven
derived behavior.

### 3. Start with an internal Python interface first

The first implementation should be an internal API and internal datamodel,
without exposing it as a public artifact contract.

Suggested first internal protocol:

```python
class WorkflowGraphMutation(Protocol):
    def apply(self, workflow: LoadedAgentWorkflow) -> LoadedAgentWorkflow: ...
```

Recommended richer shape once multiple mutation types exist:

```python
@dataclass(frozen=True)
class MutationResult:
    workflow: LoadedAgentWorkflow
    notices: tuple[str, ...] = ()


class WorkflowGraphMutation(Protocol):
    mutation_id: str

    def apply(self, workflow: LoadedAgentWorkflow) -> MutationResult: ...
```

This keeps the contract simple while allowing later validation notices,
diagnostics, or trace emission.

## Proposed Internal Mutation Model

For the first implementation, prefer a **typed internal object model** rather
than YAML-first user-facing artifacts.

Suggested internal shape:

```python
@dataclass(frozen=True)
class GraphMutationTarget:
    node_id: str | None = None
    edge_from: str | None = None
    edge_to: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class GraphMutationSpec:
    mutation_id: str
    kind: str
    target: GraphMutationTarget
    config: Mapping[str, Any] = field(default_factory=dict)
```

And an orchestrator:

```python
@dataclass(frozen=True)
class WorkflowMutationBundle:
    mutations: tuple[GraphMutationSpec, ...] = ()
```

This gives the runtime a stable internal language for mutations without yet
committing to a public YAML schema.

## Why not make mutations full workflow definitions?

Using the full agent workflow definition shape for mutations would create these
problems:

- unclear authority between the base graph and the mutation graph
- unnecessary duplication of entrypoint, package, node-kind, and edge-kind rules
- harder merge semantics for node identity, edge identity, and validation order
- temptation to treat mutations like peer workflows rather than transformation
  layers

The runtime only needs a **patch/transform language**, not a second full
workflow package.

## First Target Use Case: Context Pruning Pipeline Injection

The first mutation use case is to add an internal context-pruning step before an
existing `llm_step` consumes prompt context.

That mutation should:

- locate a target `llm_step`
- insert a derived pre-processing node or equivalent derived input-transform
  stage
- route the target node's prompt/context inputs through the pruning logic
- preserve the original base graph untouched

### Recommended initial mutation style

Prefer **derived input transformation** over arbitrary graph surgery where
possible.

In practice, the first implementation can be one of two shapes:

#### Option A — Input-transform mutation at compile time

Rather than inserting a visibly new node into the graph model, attach a
pre-execution input transform to a target `llm_step`.

Advantages:

- less graph churn
- lower validation complexity
- easier to add for one narrow use case
- keeps Mermaid and node identity drift smaller in early iterations

#### Option B — True derived-node insertion

Insert an internal node such as `context_pruning_step` before a target
`llm_step`, rewiring incoming edges to the new node and wiring the new node to
the original target.

Advantages:

- clearer future generalization for multiple graph transforms
- easier tracing and debug visibility
- better long-term fit if more structural mutations are expected

### Recommendation

Use **Option A first**, but design the mutation interface so it can later evolve
into **Option B** without changing the conceptual mutation layer.

That means the first internal mutation may compile into enriched prepared-node
behavior rather than physically altering `RuntimeNode` / `RuntimeEdge` objects,
while still being represented conceptually as a graph mutation.

## Additional Workflow Definition Metadata Needed

To attach context pruning cleanly, the base workflow definition likely needs a
small amount of additional metadata.

### Required or strongly recommended additions

#### 1. Stable attachment metadata for target LLM nodes

Need a way to identify which nodes permit pre-LLM context mutation.

Recommended manifest addition on `llm_step` nodes:

```yaml
context_pipeline:
  enabled: true
  pipeline_id: default
```

Or, if the repository prefers more general language:

```yaml
input_preparation:
  allow_mutation_hooks: true
  preparation_profile: conversational_context
```

This avoids relying only on node kind plus heuristics.

#### 2. Structured context source metadata

The pruning pipeline needs to know what memory/context pool it is pruning.

Recommended metadata:

```yaml
context_sources:
  - kind: conversation_history
    source: state.chat_history
  - kind: latest_user_prompt
    source: prompt
```

Without this, the pruning system has to guess from prompt templates or generic
node outputs.

#### 3. Mutation-safe state/input boundaries

The pruning stage needs a clean contract for what it may read and what it may
emit.

Recommended metadata:

```yaml
context_contract:
  history_input: state.chat_history
  current_prompt_input: prompt
  output_slot: prepared_context
```

This makes the mutation deterministic and avoids hidden coupling to prompt
template internals.

#### 4. Optional semantic-retrieval configuration hook

For the llama.cpp local embedding use case, the workflow may eventually need to
declare that semantic pruning is allowed and what profile it should use.

Recommended shape:

```yaml
context_pipeline:
  enabled: true
  strategy: semantic_pruning
  profile: local_default
```

The runtime can then resolve `local_default` to an internal mutation and local
embedding adapter configuration.

## What should stay out of the base workflow definition for now

Do **not** require the base workflow definition to fully describe:

- exact mutation rewiring rules
- low-level llama.cpp constructor arguments
- embedding model paths
- top-k similarity internals
- implementation-specific pruning algorithms

Those belong in runtime-owned internal mutation configuration or deployment
configuration, not in the portable workflow package.

## Recommended Responsibility Split

### Base workflow definition should declare

- which nodes allow context-pipeline attachment
- what context sources exist
- what context/output contract the node expects
- optional high-level strategy/profile identifiers

### Internal runtime mutation layer should own

- how context pruning is implemented
- how local embedding models are selected
- how pruning rewrites or transforms prepared input
- how traces and diagnostics are emitted
- whether the implementation is input-transform only or true node insertion

## Suggested Near-Term Internal API

Suggested first module:

```text
src/dynamic_agent_runner/graph_mutation.py
```

Suggested first contents:

- `WorkflowGraphMutation` protocol
- `MutationResult`
- `GraphMutationSpec`
- `WorkflowMutationBundle`
- `apply_workflow_mutations(workflow, mutations)`
- `ContextPruningMutation` internal implementation

Suggested first runtime integration point:

- after artifact loading and runtime-behavior overlay
- before `prepare_execution_plan(...)`

## Validation Rules for a First Mutation Slice

The first mutation implementation should validate at least:

- target node exists
- target node is an `llm_step`
- target node explicitly allows the relevant context pipeline or mutation hook
- required context sources are declared
- output slot or prepared-input contract is unambiguous
- mutation does not orphan edges or remove the workflow entrypoint
- derived workflow remains valid under normal node/edge validation

## Final Recommendation

1. **Do not model graph mutation as another full workflow definition.**
2. **Use an internal mutation interface and internal typed mutation specs first.**
3. **Treat mutation as a compile-time derivation layer**, parallel to current
   runtime behavior overrides.
4. **Start with context-pruning as an input-transform mutation** on target
   `llm_step` nodes rather than full graph surgery.
5. **Add small, high-value workflow metadata** for clean attachment:
   - mutation/context-pipeline enablement
   - structured context sources
   - input/output context contract
   - optional high-level strategy/profile id

This gives the runtime a clean path to inject an internal local context-pruning
pipeline now, while leaving room to evolve toward broader graph-transform
support later.
