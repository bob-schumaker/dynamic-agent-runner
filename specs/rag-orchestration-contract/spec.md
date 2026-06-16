# RAG Orchestration Contract Specification

## Metadata

- Feature slug: `rag-orchestration-contract`
- Mode: `light`
- Artifact type: future feature specification
- Status: proposed future feature; current runtime validates limited
  `metadata.rag_pipeline` fields but does not execute a RAG pipeline directly
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Related specs:
  - `specs/context-management-prepare-stage/spec.md`
  - `specs/capability-status-report/spec.md`
  - `specs/live-guardrail-execution/spec.md`
  - `specs/iterative-agent-loop-runtime/spec.md`
  - `specs/mcp-runtime-integration/spec.md`
  - `specs/internal-graph-mutation/spec.md`
- Evaluated reference:
  - Jia Huang's `RAG from First Principles` (Packt Publishing, ISBN
    `9781835888667`, 2026 metadata date)
  - repository-local RAG research notes covering production RAG pitfalls,
    agentic search, GraphRAG, reranking, context pruning, Markdown chunking,
    multi-hop QA, and specialized retrieval agents

## Objective

Define how `dynamic-agent-runner` should support retrieval-augmented generation
(RAG) as a first-class orchestration contract without becoming a RAG
infrastructure framework.

The runner should be able to load, validate, report, trace, and execute
RAG-shaped workflows where retrieval is performed by explicit caller-owned
tools, MCP bindings, or injected adapters. It should not own document ingestion,
chunking, embedding generation, vector storage, sparse indexes, graph stores, or
reranker implementations.

## Problem Statement

The runtime already preserves and validates provider-neutral RAG metadata through
`metadata.patterns_present` and `metadata.rag_pipeline`. It also supports
primitive workflow nodes, caller-owned tool registries, MCP-origin tool
provenance, context preparation, guardrails, capability/status reporting, and
bounded iterative model-tool loops.

Those pieces are enough to execute RAG-shaped workflows, but they do not yet
define a coherent orchestration contract. Without that contract, future RAG work
can drift in two bad directions:

- too little structure, where RAG is only a loose pattern label and callers
  cannot preflight missing retrievers, stale indexes, absent provenance, or
  unsupported post-processing expectations
- too much ownership, where the runner starts bundling retrieval infrastructure
  such as loaders, embedding models, vector databases, sparse indexes, graph
  stores, or rerankers that should remain caller-owned

This spec defines the middle path: direct support for RAG metadata,
orchestration, validation, observability, provenance, and evaluation hooks while
leaving retrieval infrastructure outside the package.

## Current Baseline

The implemented runtime already has these relevant surfaces:

- primitive node taxonomy: `llm_step`, `tool_use_step`, and `decision_step`
- `metadata.patterns_present` support for `rag`, `embedding_retrieval`,
  `graph_retrieval`, and `graphrag`
- `metadata.rag_pipeline` validation for retrieval mode, embedding capability,
  graph capability, index owner, graph store owner, reranking, freshness,
  provenance, and metadata filters
- explicit caller-owned `ToolRegistry` execution for retrieval tools
- MCP-origin registry entry support and provenance metadata
- context-management prepare stage for prompt-context assembly and compression
- capability/status reporting for live, metadata-only, missing, and disabled
  collaborators
- live input guardrails and deferred future output/tool guardrail phases
- opt-in bounded iterative model-tool loops for ReAct-style and retrieval loops

This spec does not replace those surfaces. It organizes future RAG behavior
around them.

## Scope

This feature covers:

1. manifest metadata for RAG stage declarations
2. validation of RAG pattern, stage, and collaborator consistency
3. capability/status reporting for RAG collaborators and degraded conditions
4. trace metadata for retrieval, fusion, reranking, context assembly, and
   generation boundaries
5. provenance contracts for retrieved chunks and generated answers
6. context-management integration for bounded prompt injection of retrieved
   context
7. guardrail and evaluation hooks for retrieval quality, faithfulness, and
   groundedness
8. workflow patterns for ordinary RAG, lexical RAG, structural RAG, hybrid RAG,
   graph retrieval, GraphRAG, agentic RAG, and iterative/adaptive retrieval
9. optional graph-mutation attachment or insertion points for context
   preparation and retrieval orchestration
10. typed query, evidence, answer-state, and failure-state contracts
11. multi-stage retrieval funnels with cost, latency, and candidate-count
    metadata

## Non-Goals

This feature must not introduce:

- built-in document ingestion or parsing
- built-in chunking pipelines
- built-in embedding generation
- built-in vector databases, sparse indexes, graph stores, or index maintenance
- built-in reranker, compressor, evaluator, or RAG framework dependencies
- live network retrieval without explicit caller-provided tools or MCP bindings
- runner-owned durable knowledge-base storage
- automatic indexing background jobs
- mutation of generated package artifacts
- a new primitive `rag_step` node kind in the first design

## Direct Support Boundary

RAG should be directly supported as an orchestration contract, not as
infrastructure.

Direct runner-owned responsibilities:

- parse and validate RAG declarations
- expose RAG capability/status diagnostics
- enforce required collaborators before execution
- carry provenance and retrieval metadata through traces
- make retrieved context visible to `prepare_model_input(...)` through bounded,
  policy-controlled inputs
- provide hooks where caller-owned evaluators and guardrails can inspect
  retrieval and generation outputs
- preserve primitive workflow execution and registry-authoritative tool use

Caller-owned responsibilities:

- load, parse, and chunk documents
- generate sparse, dense, graph, or multimodal representations
- maintain indexes and freshness policy
- execute retrieval, query rewriting, metadata filtering, routing, fusion,
  reranking, compression, correction, and evaluation logic
- choose RAG frameworks or services such as LangChain, LlamaIndex, Milvus,
  Elasticsearch, graph databases, RAGAS, TruLens, DeepEval, or Phoenix
- manage data governance, retention, and access policy for knowledge sources

## Proposed Manifest Shape

The current `metadata.rag_pipeline` surface should grow carefully before any
runtime execution behavior changes.

Illustrative future metadata:

```yaml
metadata:
  patterns_present:
    - rag
    - embedding_retrieval
  rag_pipeline:
    orchestration_mode: hybrid_retrieval
    retrieval_mode: hybrid
    stages:
      pre_retrieval:
        query_contract: parsed_question
        query_rewriting: optional
        query_decomposition: optional
        metadata_filtering: required
        ambiguity_handling: ask_or_abstain
      retrieval:
        retrievers:
          - id: keyword_search
            tool_id: search_bm25
            mode: lexical_keyword
          - id: semantic_search
            tool_id: search_embeddings
            mode: embedding_semantic
        candidate_budget:
          stage1_k: 50
          stage2_k: 20
          final_k: 5
      post_retrieval:
        fusion: rrf
        reranking: caller_adapter
        compression: caller_adapter
        correction: optional
      context_assembly:
        target: prepare_model_input
        provenance_required: true
        max_context_tokens: 8192
        required_evidence_fields:
          - source_id
          - chunk_id
          - citation_handle
      evaluation:
        retrieval_metrics:
          - precision
          - recall
          - mrr
        response_metrics:
          - faithfulness
          - groundedness
          - answer_relevance
    embedding_capability: required
    graph_capability: unavailable
    index_owner: external_service
    reranking: caller_adapter
    freshness_policy: scheduled
    provenance_required: true
    metadata_filters:
      - source_id
      - updated_at
    answer_states:
      - answer_found
      - insufficient_context
      - conflicting_sources
      - absence_verified
```

The example is not an implementation contract. It records the target vocabulary
for future validation and capability/status work.

## Retrieval Orchestration Modes

RAG declarations should describe the retrieval control strategy separately from
the storage or ranking technology. Future metadata should allow these modes:

- `preindexed_retrieval` — use caller-owned indexes prepared before query time,
  such as vector, sparse, full-text, graph, or database indexes
- `just_in_time_retrieval` — use live tools such as filesystem search,
  document readers, SQL, Cypher, MCP resources, or API queries at runtime
- `hybrid_retrieval` — combine multiple retrieval modes, such as lexical plus
  semantic, graph plus text, or live tools over an indexed candidate slice
- `structural_retrieval` — use caller-owned parsers or tools that retrieve
  structure-aware units such as sections, tables, AST nodes, functions,
  entities, or document spans
- `agentic_retrieval` — let a bounded agent loop choose retrieval tools,
  inspect observations, refine queries, prune working context, and decide when
  enough evidence has been collected

Vector search must not be assumed as the default. Stable FAQ-style corpora may
use vector retrieval with reranking; evolving code, logs, tickets, and private
workspace data may prefer just-in-time tool retrieval; relationship-heavy
questions may require graph traversal; exact identifiers often require lexical
or structural search.

## Query And Answer Contracts

Production RAG needs typed intermediate state. The runner should eventually
support contracts that let caller-owned parsers and evaluators expose query and
answer shape without forcing free-form strings through every stage.

Future parsed-query metadata may include:

- `intent`
- `answer_shape`
- `scope_filters`
- `format_constraints`
- `operators`, including negation, comparison, time range, and aggregation
- `ambiguities`
- `decomposition_plan`
- `retrieval_brief`
- `generation_brief`

Future answer-state metadata may include:

- `answer_found`
- `insufficient_context`
- `ambiguous_query`
- `conflicting_sources`
- `stale_sources`
- `reference_unresolved`
- `absence_verified`
- `retrieval_failed`
- `guardrail_blocked`

These states should be machine-readable so orchestration can ask for
clarification, follow references, run a second retrieval pass, abstain, or route
to a guardrail/evaluator instead of letting the model improvise.

## Evidence Object Guidance

Retrieved context should be modeled as structured evidence, not only text. A
future package-owned retrieved-context item may expose:

- source identifiers: `source_id`, source label/title, owner, version, and trust
  classification
- chunk identifiers: `chunk_id`, `parent_id`, child ids, adjacent ids, and
  citation handle
- structural location: heading path, section path, page, line, character span,
  bounding box, table cell coordinates, AST path, or transcript timestamp
- content shape: block type such as prose, table, code, list, figure, image,
  audio, video, or mixed
- retrieval metadata: retrieval path, rank, score, score type, fusion score,
  reranker score, and selected mode
- freshness metadata: timestamp, source version, index version, stale flag, and
  freshness policy
- context-management metadata: required/optional lane, token estimate,
  oversized flag, partial flag, pruned flag, and compression provenance

The runner should carry these fields when provided, but it should not create or
maintain the underlying evidence store.

## Multi-Stage Funnel Guidance

RAG orchestration should support high-recall, low-cost candidate generation
followed by more expensive precision stages. Future stage metadata may include:

- candidate counts such as `stage1_k`, `stage2_k`, and `final_k`
- latency and cost budgets per stage
- cache policy for repeated or semantically duplicate queries
- score thresholds and minimum-evidence requirements
- fallback behavior when no candidate meets threshold
- hard-negative or distractor evaluation labels for regression tests
- tail-latency expectations for rerankers and specialized retrieval agents

Examples include lexical or vector retrieval over many documents, cross-encoder
or ColBERT-style reranking over tens of candidates, and LLM listwise ranking
only over the final small set. The runner should report the declared funnel and
collaborator readiness; caller-owned tools or adapters perform the work.

## Reference Resolution And Absence Proof

Some retrieved evidence points to other evidence, such as "see Section 4.2" or a
table note that requires another page. Future RAG orchestration should support a
reference-resolution state that can trigger a deterministic or agentic follow-up
retrieval pass before generation.

Absence claims also need structure. A model saying "not found" over top-k chunks
is not proof that the corpus lacks the answer. Future answer contracts should
distinguish:

- not found in retrieved context
- retrieval failed or timed out
- relevant references remain unresolved
- literal/structured absence proof was attempted
- absence was verified by caller-owned deterministic search or another
  configured proof mechanism

The runner should make these states visible in traces and capability/status
reports without owning the underlying corpus scan.

## GraphRAG Layer Guidance

GraphRAG declarations should identify which graph layer is involved:

- document layer: sources, versions, authors, permissions, and provenance
- lexical layer: chunks, sections, tables, figures, embeddings, spans, and
  parent/child or neighboring relationships
- domain layer: entities, concepts, events, products, contracts, incidents, and
  relationships
- operational layer: extraction confidence, lineage, sensitivity, quality,
  freshness, schema version, and policy metadata
- tool/workflow layer: retrievers, tools, schemas, auth requirements,
  preconditions, plans, tool calls, retries, and evaluation results

This keeps GraphRAG from collapsing into a single `graph_capability` flag and
helps capability/status reporting explain what kind of graph support is live.

## Functional Requirements

### FR-1: Preserve primitive workflow nodes

RAG workflows must continue to use `llm_step`, `tool_use_step`, and
`decision_step` nodes.

Acceptance criteria:

- A workflow can declare `rag` metadata without introducing a new primitive node
  kind.
- Retrieval execution occurs through explicit tool use, MCP tool bindings, or
  injected adapters.
- Agentic or iterative RAG uses existing loop and decision semantics rather than
  bypassing the executor.
- Graph mutation may attach or insert context/retrieval behavior only through
  approved mutation specs.

### FR-2: Validate RAG stage declarations

The runner must validate RAG declarations enough to catch inconsistent package
shape before execution.

Acceptance criteria:

- `metadata.rag_pipeline` remains required when RAG patterns are present.
- RAG-specific patterns require matching capabilities, such as required
  embedding capability for `embedding_retrieval` and required graph capability
  for `graph_retrieval` or `graphrag`.
- Declared retrieval stages reference known tool ids, MCP bindings, or adapter
  ids when the workflow expects live execution.
- Hybrid retrieval distinguishes retrieval mode, fusion method, reranking
  method, and compression method.
- Provenance-required RAG declarations fail closed when no provenance-producing
  retriever or context contract is available.
- Declared orchestration modes use supported values and do not imply runner-owned
  retrieval infrastructure.
- Stage-level candidate budgets, latency budgets, or cost budgets are validated
  as metadata when present.

### FR-3: Report RAG capability status

Capability/status reporting must make RAG readiness inspectable.

Acceptance criteria:

- Reports distinguish metadata-only RAG declarations from live retriever,
  reranker, compressor, evaluator, and context-assembly collaborators.
- Reports identify missing required collaborators before execution.
- Reports can describe degraded conditions such as stale index, absent
  provenance, unsupported fusion, unavailable graph store, unavailable embedding
  retriever, or disabled post-processing.
- Reports can distinguish preindexed, just-in-time, hybrid, structural, and
  agentic retrieval declarations.
- Reports can identify missing query parsers, answer verifiers, reference
  resolvers, absence-proof mechanisms, and evaluation adapters when declared
  required.
- Reports remain descriptive and must not start retrieval services or mutate
  indexes.

### FR-4: Carry retrieval provenance

Retrieved context must carry enough provenance for tracing, prompt assembly,
guardrails, and answer citation.

Acceptance criteria:

- Retrieved items can expose source id, source title or label, chunk id, parent
  id, position metadata, timestamp or freshness metadata, retrieval score,
  retrieval path, and source trust classification when available.
- Retrieved items can expose structural metadata such as heading path, section
  path, block type, source coordinates, adjacent ids, oversized flag, partial
  flag, and citation handle when available.
- Prompt assembly can include bounded provenance metadata without dumping
  sensitive raw source content into traces.
- Generated answers can be checked against retrieved provenance by future output
  guardrails or evaluators.
- Missing provenance is visible in capability/status and trace metadata.

### FR-5: Integrate with context preparation

RAG context must enter model prompts through `prepare_model_input(...)` or a
compatible future context-management seam.

Acceptance criteria:

- Retrieved context is treated as a bounded context lane, not as unstructured
  transcript history.
- Context assembly respects prompt hierarchy, output headroom, required vs
  optional lanes, compression profiles, and deterministic fallback trimming.
- Caller-owned retrieval results can provide selection hints such as score,
  source type, recency, parent/child relationship, and chunk role.
- Context injection emits redacted diagnostics for included, omitted, trimmed,
  and compressed retrieved items.
- Agentic retrieval context can expose soft and hard token thresholds so a
  retrieval agent may continue, prune, or stop according to policy.

### FR-6: Support hybrid and post-retrieval metadata

The manifest must distinguish retrieval, fusion, reranking, compression, and
correction because they have different safety, cost, and privacy properties.

Acceptance criteria:

- Hybrid retrieval can declare multiple retrieval paths.
- Fusion methods such as `rrf` are distinct from reranking methods such as
  `cross_encoder`, `colbert`, `llm`, `caller_adapter`, or `external_service`.
- Lexical, regex, full-text, SQL, Cypher, graph traversal, structural AST, and
  multimodal retrieval modes can be declared without requiring vector search.
- Compression methods such as contextual compression, RECOMP-style summaries, or
  prompt compression are distinct from context-management fallback trimming.
- Correction or self-checking is declared separately from retrieval and
  generation.
- The runner can preflight required collaborators for each declared operation.

### FR-7: Support typed query and answer-state contracts

RAG orchestration must be able to route based on typed intermediate state when a
caller supplies it.

Acceptance criteria:

- Parsed-query outputs can be declared as caller-owned collaborators.
- Answer states can drive orchestration decisions such as clarify, retrieve
  again, resolve reference, abstain, or finalize.
- Absence claims distinguish "not in retrieved context" from "not in corpus"
  when a caller-owned absence-proof mechanism is declared.
- Structured answer contracts remain compatible with existing output-contract
  validation and future output guardrails.

### FR-8: Support reference-resolution loops

RAG orchestration must be able to represent unresolved references without
fabricating around them.

Acceptance criteria:

- Retrieved evidence may declare unresolved references to sections, pages,
  entities, rows, documents, URLs, or graph nodes.
- A workflow can route unresolved references to caller-owned resolver tools or a
  bounded agentic retrieval loop.
- Reference resolution traces identify the triggering evidence id and resulting
  evidence ids without dumping raw sensitive content.
- Generation can be delayed or abstained when required references remain
  unresolved.

### FR-9: Expose evaluation hooks without owning evaluators

RAG evaluation must be supported through hooks and metadata while evaluator
implementations remain caller-owned.

Acceptance criteria:

- Retrieval evaluation can record precision, recall, F1, MRR, MAP, P@K,
  document precision, page precision, positional precision, or caller-defined
  metrics.
- Response evaluation can record faithfulness, groundedness, context relevance,
  answer relevance, hallucination flags, or caller-defined metrics.
- Evaluation traces identify metric names, scores, evaluator provenance, and
  redacted inspected artifact ids.
- Evaluation can record golden-query expectations such as must-retrieve,
  must-not-retrieve, answer-must-contain, answer-must-not-contain, hard
  distractors, and abstention expectations.
- Unit tests for this feature use fake evaluator adapters only.

### FR-10: Compose with guardrails and approval policy

RAG orchestration must not bypass existing safety boundaries.

Acceptance criteria:

- Retrieval tools remain registry-authoritative and approval/sandbox-aware.
- MCP-origin retrievers preserve MCP provenance and conservative defaults.
- Future tool-input, tool-output, and output guardrails can inspect query,
  retrieved context, and generated answers.
- Sensitive retrieved content is redacted from traces by default.
- Live external retrieval, reranking, or evaluation services require explicit
  caller/deployment configuration.

## Pattern Guidance

Ordinary RAG:

- use one or more retrieval tools before an `llm_step`
- pass retrieved context through state into prompt preparation
- require provenance when answers need citations or auditability

Lexical or just-in-time RAG:

- use exact, regex, full-text, file, SQL, Cypher, or API tools when the question
  depends on identifiers, current source state, exact phrases, or live data
- prefer small, clear retrieval tools over overlapping search surfaces
- expose cost, latency, and max-tool-call limits when retrieval is agentic

Hybrid RAG:

- declare multiple retrieval paths
- declare fusion separately from reranking
- use deterministic fusion such as RRF when score scales are incompatible

Structural RAG:

- use structure-aware caller tools for sections, tables, Markdown heading paths,
  code ASTs, transcripts, or multimodal segments
- preserve structural metadata on retrieved evidence
- avoid cross-section overlap pollution when source structure is available

GraphRAG:

- use `graph_retrieval` or `graphrag` pattern metadata
- require graph capability and graph-store ownership metadata
- keep graph queries caller-owned through tools, MCP, or injected adapters
- declare which GraphRAG layer is being used when future metadata supports it

Agentic or adaptive RAG:

- use iterative-loop runtime only when bounded and opt-in
- keep query rewriting, clarification, decomposition, routing, and corrective
  retrieval as explicit steps or tool calls
- report loop and retrieval diagnostics separately
- support prune-or-finish behavior near hard context limits when retrieval
  agents manage their own working evidence set

Multimodal RAG:

- treat multimodal retrieval as caller-owned
- preserve modality metadata and provenance when context is injected
- do not add built-in image, audio, or video embedding backends under this spec

Decision guidance:

- Use vector retrieval with reranking for stable factual knowledge bases,
  product docs, FAQs, and glossary-like corpora.
- Use lexical or structural retrieval for exact identifiers, code, logs, legal
  clauses, tables, line-level citation, and rapidly changing private workspaces.
- Use hybrid retrieval when both exact matching and semantic synonym handling
  matter.
- Use GraphRAG when relationships, multi-hop traversal, entity resolution,
  provenance, or explainability are central.
- Use agentic retrieval only when the task needs dynamic search, clarification,
  decomposition, reference resolution, or iterative verification and can afford
  the additional latency/cost.

## Relationship to Existing Specs

- `dynamic-agent-runner` owns package loading, primitive workflow execution, and
  public API boundaries.
- `context-management-prepare-stage` owns prompt assembly, context lanes,
  trimming, compression profiles, and retrieved-context injection.
- `capability-status-report` owns user-visible readiness diagnostics for RAG
  collaborators.
- `live-guardrail-execution` owns future input, tool, and output guardrail
  execution around queries, retrieved context, and answers.
- `mcp-runtime-integration` owns MCP-origin retrieval tools, resources, prompts,
  and live MCP source boundaries.
- `iterative-agent-loop-runtime` owns bounded agentic/adaptive RAG loops.
- `internal-graph-mutation` owns future compile-time graph attachment or
  insertion of context/retrieval preparation behavior.
- `async-session-memory-pipeline` does not own live RAG retrieval or prompt
  shaping.

## NEEDS CLARIFICATION

- Should the expanded RAG metadata remain entirely under
  `metadata.rag_pipeline`, or should stage-level execution policy live under
  `runtime.execution_policy`?
- What exact enum values should be supported for fusion, reranking,
  compression, correction, and evaluator types?
- What exact enum values should be supported for orchestration mode and
  retrieval mode, including lexical, structural, SQL, Cypher, graph, and
  multimodal variants?
- Should retrieval results use a package-owned public dataclass, a protocol, or
  plain mappings supplied by tools?
- Should parsed-query and answer-state contracts be modeled as output contracts,
  lifecycle hooks, guardrail inputs, or a dedicated RAG contract type?
- How should provenance metadata map into generated answer citation formats?
- Which RAG degraded states belong in capability/status v1 versus later
  deployment reporting?
- Should RAG evaluation hooks be modeled as guardrails, lifecycle hooks, or a
  separate evaluator registry?
- How much of the illustrative stage vocabulary should be validated before
  there is live orchestration behavior?
- How should token/cost budgets be represented for agentic retrieval loops and
  specialized retrieval agents?

## Future Work

Future approved slices may add:

- expanded `metadata.rag_pipeline` validation for stage-level declarations
- RAG capability/status sections for retrievers, indexes, graph stores,
  rerankers, compressors, evaluators, freshness, and provenance
- a package-owned retrieved-context item contract
- parsed-query and answer-state contracts for routing, abstention, reference
  resolution, and absence proof
- redacted trace events for retrieval, fusion, reranking, compression, context
  assembly, evaluation, and generation
- context-management support for retrieved-context lanes and provenance-aware
  trimming
- just-in-time retrieval examples using file, SQL, Cypher, MCP, and structural
  search tools
- agentic retrieval examples with soft/hard context thresholds and
  prune-or-finish behavior near hard limits
- fake-adapter tests for RAG evaluation metrics and guardrail composition
- examples showing ordinary RAG, hybrid RAG, GraphRAG, and bounded agentic RAG
  using primitive nodes

## Validation Checklist

- [ ] RAG declarations stay metadata/orchestration-only until an approved
      implementation slice exists.
- [ ] No built-in loader, chunker, embedding, vector DB, graph store, reranker,
      or evaluator dependency is introduced.
- [ ] RAG pattern metadata composes with primitive nodes.
- [ ] Required retriever/collaborator gaps are reportable before execution.
- [ ] Retrieved context enters prompts through context-management boundaries.
- [ ] Provenance absence is visible when `provenance_required` is true.
- [ ] Hybrid retrieval distinguishes retrieval, fusion, reranking, compression,
      and correction.
- [ ] RAG modes include just-in-time, lexical, structural, graph, and agentic
      retrieval without making vector search the default.
- [ ] Typed query and answer states can drive clarification, abstention,
      reference resolution, or second-pass retrieval in future slices.
- [ ] Stage budgets and candidate-count metadata are distinct from live
      retrieval execution.
- [ ] Evaluation hooks use fake adapters in unit tests.
