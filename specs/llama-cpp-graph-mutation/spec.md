# llama.cpp local-model support and graph mutation specification

## Metadata

- Feature slug: `llama-cpp-graph-mutation`
- Mode: `light`
- Status: proposed only; implementation intentionally reverted after spec capture
- Related artifacts:
  - `specs/dynamic-agent-runner/references/graph-mutation-interface-design.md`
  - `src/dynamic_agent_runner/openai_client.py`
  - `src/dynamic_agent_runner/executor.py`
  - `src/dynamic_agent_runner/behavior.py`

## Goal

Specify two related runtime capabilities for `dynamic-agent-runner`:

1. local llama.cpp-backed model adapters that fit the runtime's existing
   `model_adapter` / additional-model selection contract
2. an internal-only graph mutation layer that can attach a local context-pruning
   pipeline to existing workflow graphs before execution

## Why these belong together

The graph-mutation design is motivated by an internal context-pruning pipeline,
and that pruning pipeline is expected to use local embedding-capable models for
cost-sensitive and privacy-preserving context management. llama.cpp local model
support is therefore one enabling runtime capability for the first planned graph
mutation use case.

## Existing Runtime Context

- The runtime already supports multiple model adapters through the
  `model_adapter` argument and adapter advertisement via `models` and `is_local`.
- The runtime already has a compile/preparation phase centered on
  `prepare_execution_plan(...)`.
- The runtime already supports caller-owned derived behavior overlays in
  `behavior.py` without mutating the immutable base workflow artifacts.

These existing seams support both capabilities:

- llama.cpp should fit the existing adapter contract rather than inventing a new
  model interface family
- graph mutation should be modeled as another derived compile-time layer rather
  than in-place artifact mutation

## Capability A — llama.cpp local model adapter

### Objective

Allow callers to provide local llama.cpp-backed model adapters that participate
in runtime model selection the same way existing OpenAI adapters do.

### Functional requirements

- The runtime must support a sync llama.cpp adapter and an async-compatible
  wrapper.
- The adapter must advertise one or more model names via `models`.
- The adapter must report `is_local=True` by default so existing
  `local_only` model-selection logic can prefer or require it.
- The constructor must support:
  - primary chat model path
  - optional explicit model alias or aliases
  - optional separate embedding model path
  - optional explicit embedding model alias or aliases
  - arbitrary additional `llama_cpp.Llama(...)` keyword arguments
- The adapter must normalize llama.cpp OpenAI-compatible chat responses into the
  runtime's existing `ModelResponse` / `ModelToolCall` structure.
- Embedding-capable local models must be supported for internal context
  management and retrieval-like operations.

### Non-goals

- no new public workflow-definition fields for low-level llama.cpp constructor
  settings
- no commitment yet to a public embedding API at the top-level runtime package
- no promise that portable workflow packages carry local model filesystem paths

### Existing implementation work captured before revert

The now-reverted code implemented the following design slice:

- new file `src/dynamic_agent_runner/llama_cpp.py`
  - `LlamaCppClientAdapter`
  - `AsyncLlamaCppClientAdapter`
  - `create_default_llama_class()`
  - `normalize_llama_cpp_response()`
- adapter constructor support for:
  - `model_path`
  - `model` / `models`
  - `embedding_model`
  - `embedding_models`
  - `embedding_model_path`
  - pass-through llama.cpp constructor kwargs
- chat response normalization from llama.cpp OpenAI-style chat completions into
  internal `ModelResponse`
- embedding request support via a separate embedding-capable client instance
- runtime typing/exports wired into:
  - `src/dynamic_agent_runner/api.py`
  - `src/dynamic_agent_runner/executor.py`
  - `src/dynamic_agent_runner/__init__.py`
- targeted tests added in `tests/test_llama_cpp.py`
- dependency declaration added in `pyproject.toml` and lockfile updates in
  `poetry.lock`

### Acceptance criteria for future implementation

- Given a caller-provided llama.cpp adapter, when an `llm_step` requests a model
  that the adapter advertises, then the runtime may select that adapter through
  the existing model-selection flow.
- Given `local_only` operational requirements, when a local llama.cpp adapter is
  available, then the runtime may satisfy those requirements without routing to
  remote providers.
- Given a separate local embedding model configuration, when internal runtime
  logic needs embeddings, then the adapter can produce embeddings without
  requiring a remote API.
- Given llama.cpp chat responses that include OpenAI-style tool calls, when the
  runtime normalizes the response, then tool calls are preserved in the existing
  internal response shape.

## Capability B — internal graph mutation layer

### Objective

Add an internal-only graph mutation layer that can derive modified execution
graphs from immutable base workflow packages before plan preparation and
execution.

### Functional requirements

- Graph mutation must be modeled as a compile-time derivation layer.
- The immutable base workflow package must remain unchanged.
- The first mutation use case is internal context-pruning attachment for an
  existing `llm_step`.
- The first implementation may use an input-transform mutation rather than full
  node/edge graph surgery.
- The design must allow later expansion into richer structural mutations.

### Shape recommendation

- Do **not** use a second full agent workflow definition as the mutation format.
- Use an internal typed mutation spec or internal mutation protocol that applies
  to an already-loaded workflow.

### Additional workflow metadata likely needed

Base workflow definitions should likely add small, high-value metadata for clean
attachment:

- node-level `context_pipeline` or `input_preparation` enablement
- `context_sources` declarations
- `context_contract` read/write slots
- optional high-level strategy/profile identifiers such as
  `semantic_pruning` / `local_default`

### Detailed design reference

The detailed graph-mutation recommendation lives in:

- `specs/dynamic-agent-runner/references/graph-mutation-interface-design.md`

That note recommends:

- internal mutation protocol and typed mutation specs
- compile-time mutation application before `prepare_execution_plan(...)`
- initial input-transform mutation instead of immediate graph surgery
- keeping implementation-specific local-model and pruning details out of the
  portable workflow definition

## Integration recommendation

When this feature returns for implementation, the recommended order is:

1. finalize the feature-level spec and any needed workflow metadata additions
2. add an internal `graph_mutation.py` seam and derived-workflow application
   stage
3. reintroduce llama.cpp adapter support against the stabilized spec
4. implement the first context-pruning mutation using local embeddings
5. add validation and tracing for mutation application and derived context flows

## Validation status for this spec artifact

- This artifact documents design intent and captures a reverted prototype.
- The previous prototype passed targeted tests before revert, but those results
  do not count as current implementation validation because the code has been
  intentionally removed.
