# RAG Orchestration Contract V1 Plan

## Objective

Prepare a narrow v1 implementation for RAG as a declarative orchestration
contract. V1 should expand `metadata.rag_pipeline` validation and
capability/status reporting so packages can describe RAG stages, collaborators,
provenance, source readiness, permission requirements, cache state, and degraded
conditions without making the runner own retrieval infrastructure.

## Current Baseline

Implemented runtime surfaces already include:

- primitive workflow nodes: `llm_step`, `tool_use_step`, and `decision_step`
- `metadata.patterns_present` preservation
- limited `metadata.rag_pipeline` validation for retrieval mode, embedding and
  graph capabilities, owner fields, reranking, freshness, provenance, and
  metadata filters
- caller-owned `ToolRegistry` execution
- MCP-origin tool provenance
- capability/status reporting for runtime, model, tool, MCP, guardrail, and
  package validation states
- context-management prepare-stage baseline for prompt context lanes
- bounded iterative model-tool loops for agentic retrieval patterns

The runtime does not yet validate stage-level RAG declarations, report required
retriever readiness, carry retrieved-context contracts, or execute a RAG
pipeline directly.

## V1 Scope

Implement only:

- expanded declarative `metadata.rag_pipeline` validation
- supported enum/value sets for orchestration mode, retrieval profiles,
  retrieval modes, fusion, reranking, compression, correction, cache,
  permission, source lifecycle, GraphRAG layers, and degraded states
- validation for stage mappings, candidate/budget metadata, and referenced tool
  ids when present
- capability/status reporting for metadata-only RAG declarations, live
  caller-supplied retrieval tools, missing required collaborators, provenance
  requirements, context-management handoff requirements, stale/degraded
  declarative state, and permission requirements
- documentation and examples showing primitive-node RAG package shape

Do not implement:

- document ingestion, chunking, embeddings, vector stores, graph stores, sparse
  indexes, rerankers, compressors, evaluators, or caches
- live retrieval orchestration beyond existing `tool_use_step` execution
- a new `rag_step` node kind
- a public retrieved-context dataclass or protocol
- answer citation rendering
- evaluator registries or output guardrails
- background indexing or cache invalidation jobs

## V1 Manifest Shape

V1 keeps all new declarative metadata under `metadata.rag_pipeline`.

Supported high-level shape:

```yaml
metadata:
  patterns_present:
    - rag
    - embedding_retrieval
  rag_pipeline:
    orchestration_mode: hybrid_retrieval
    retrieval_mode: hybrid
    retrievers:
      - id: keyword
        tool_id: search_keyword
        mode: lexical_keyword
        required: true
      - id: semantic
        tool_id: search_semantic
        mode: embedding_semantic
        required: true
    fusion: rrf
    reranking: caller_adapter
    compression: none
    correction: optional
    candidate_budget:
      stage1_k: 50
      stage2_k: 20
      final_k: 5
    provenance_required: true
    context_assembly:
      target: prepare_model_input
      max_context_tokens: 8192
      required_evidence_fields:
        - source_id
        - chunk_id
        - citation_handle
    permissions:
      permission_filtering: required
      permission_failure_policy: fail_closed
      audit_required: true
    source_readiness:
      source_registry: external_service
      refresh_mode: scheduled
      index_version: caller_supplied
      stale_state: fresh
    cache:
      retrieval_results: optional
      semantic_query_cache: optional
    degraded_states:
      - stale_but_allowed
      - partial_results
```

The exact field names can be adjusted during Slice 1 if existing validation
helpers strongly favor flatter metadata. Any change should preserve the v1
boundary: declarative validation and status only.

## Implementation Slices

### Slice 0: Planning Checkpoint

Add `plan.md`, `tasks.md`, and `validation.md`; update `spec.md` and
`specs/README.md` so the feature is marked prepared rather than merely future
analysis.

Validation:

- Markdown/pre-commit over the new and changed spec artifacts.

### Slice 1: Declarative RAG Metadata Validation

Add validation for v1 RAG fields without changing execution behavior.

Likely files:

- `src/dynamic_agent_runner/validation.py`
- `tests/test_validation.py` or new `tests/test_rag_orchestration.py`
- `docs/files/artifact-package.rst`

Validation:

- valid staged RAG metadata passes
- unsupported enum values fail clearly
- malformed `retrievers`, `candidate_budget`, `context_assembly`,
  `permissions`, `source_readiness`, `cache`, and `degraded_states` fail clearly
- RAG patterns still require `metadata.rag_pipeline`
- embedding and graph pattern requirements continue to pass/fail as today

### Slice 2: Collaborator and Capability Status

Report declared RAG collaborators through capability/status without invoking
retrieval.

Likely files:

- `src/dynamic_agent_runner/capabilities.py`
- `tests/test_capabilities.py`
- possibly `src/dynamic_agent_runner/registry.py` only if existing registry
  inspection is insufficient

Validation:

- absent RAG metadata produces no RAG capability item
- metadata-only RAG declarations report metadata-only state
- required retriever tool ids covered by caller-supplied `ToolRegistry` report
  live
- missing required retriever tool ids report missing collaborator
- optional missing retrievers remain metadata-only or degraded, not invalid
- stale/degraded declarative state is visible without executing tools

### Slice 3: Provenance and Context-Management Handoff Metadata

Validate and report provenance and context-management handoff declarations. RAG
declares evidence requirements and target context assembly; context-management
owns prompt packing and injection.

Likely files:

- `src/dynamic_agent_runner/validation.py`
- `src/dynamic_agent_runner/capabilities.py`
- `docs/files/runtime-policies.rst` or `docs/files/artifact-package.rst`
- tests from Slices 1 and 2

Validation:

- `provenance_required: true` requires enough declared evidence fields or a
  required provenance-producing retriever declaration
- context assembly target is limited to `prepare_model_input` or `external`
- context token budgets are positive integers when provided
- source lifecycle, permission, cache, and degraded-state metadata are reflected
  in redaction-safe capability details

### Slice 4: Completion Evidence

Record final validation and update spec/memory state.

Validation:

- focused affected tests
- `poetry run pytest -q` unless a narrower scope is explicitly justified
- focused `pre-commit run --files ...`
- update `specs/README.md`, `tasks.md`, `validation.md`, and memory-bank files
  if requested by the active workflow

## Test Strategy

Use only manifest dictionaries, temporary package fixtures when package loading
is needed, fake registries, and fake tools. Do not add live retrievers, vector
stores, graph stores, RAG frameworks, embedding models, network calls, or
external services to unit tests.

Core tests:

- minimal valid RAG metadata remains accepted
- staged hybrid metadata validates
- malformed stage metadata fails with field-specific errors
- capability/status distinguishes metadata-only, live, missing collaborator,
  and degraded RAG states
- existing non-RAG manifests remain unchanged
- existing RAG validation tests continue to pass

## Risks

- Scope creep into infrastructure: reject any implementation that adds
  ingestion, embeddings, indexes, vector DBs, graph stores, rerankers,
  compressors, evaluators, or caches.
- New schema overreach: validate only values needed for preflight and status;
  preserve unknown caller-owned metadata only when it is not safety-relevant.
- Capability/status noise: keep report items high-signal and grouped by RAG
  role rather than emitting one low-value item for every optional field.
- Context-management drift: do not pack or inject retrieved context in this
  feature; only validate/report metadata that future context-management lanes
  can use.
- Backward compatibility: existing limited `metadata.rag_pipeline` manifests
  must continue to validate unless they violate newly documented safety rules.

## Readiness

This feature is ready for implementation when `tasks.md` is accepted as the
execution checklist. Implementation should start at Slice 1 and commit each
slice independently if the active workflow requests commits.
