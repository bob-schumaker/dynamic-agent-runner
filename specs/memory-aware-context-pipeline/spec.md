# Memory-Aware Context Pipeline Specification

## Metadata

- Feature slug: `memory-aware-context-pipeline`
- Mode: `light`
- Artifact type: proposed feature specification
- Status: proposed; roadmap refinement needed before implementation
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Related specs:
  - `specs/rag-orchestration-contract/spec.md`
  - `specs/context-management-prepare-stage/spec.md`
  - `specs/async-session-memory-pipeline/spec.md`
  - `specs/persistent-agent-sessions/spec.md`
  - `specs/semantic-context-profiles/spec.md`
- Evaluated reference:
  - `/Users/roschuma/Repos/github/memlayer`
  - `https://github.com/MARKTECHPOST-AI-MEDIA-INC/AI-Agents-Projects-Tutorials`
    provides supporting short-term, long-term, and episodic memory-policy
    examples; DAR adopts contract vocabulary only, not tutorial storage engines

## Objective

Add passive memory-aware context support to `dynamic-agent-runner` by adopting
useful ideas from `memlayer` without importing `memlayer` as a runtime
dependency.

The runner should support declarative memory identity, ownership, provenance,
retention/selection policy, passive context handoff, and explicit
memory-ingestion hooks through caller-owned tools, stores, and adapters. Active
retrieval remains a caller-owned operation, normally represented by
`metadata.rag_pipeline` or an explicitly invoked caller tool. DAR must not
become a memory database, vector store, provider wrapper, background scheduler,
embedding framework, or durable memory service.

## Problem Statement

DAR already has package-owned workflow execution, model adapters, tool
registries, context preparation, RAG metadata, and in-memory agent sessions. It
does not yet provide a clear contract for workflows that want persistent memory
beyond the current session.

`memlayer` demonstrates useful patterns:

- salience filtering before saving memories
- direct text ingestion into memory
- hybrid vector plus graph retrieval
- fast, balanced, and deep retrieval tiers
- graph-only lightweight mode
- caller-owned memory retrieval as explicit model-visible context
- traceable retrieval behavior

However, `memlayer` owns more than DAR should own: provider wrappers, storage
lifecycle, Chroma/NetworkX persistence, background services, direct tool
injection, and live-model extraction. DAR should translate the ideas into
orchestration contracts.

## Scope

This feature covers:

1. declarative memory pipeline metadata in workflow manifests
2. validation of memory retriever, salience, and ingestion declarations
3. caller-owned memory tools for search, ingest, and optional graph traversal
4. context-management handoff for retrieved memories
5. trace metadata for memory search, salience decisions, ingestion, and
   degraded states
6. capability/status reporting for missing or metadata-only memory collaborators
7. lightweight graph-only and hybrid retrieval modes as manifest concepts
8. retrieval tiers: `fast`, `balanced`, and `deep`
9. provenance fields for memory snippets injected into prompts

## Council-Driven Refinement

The June 2026 council review found the spec useful only if it stays a small,
fake-testable orchestration contract. The review raised three required
clarifications:

- distinguish passive memory context from active ordinary RAG retrieval
  contractually, not only semantically
- define a minimal v1 with executable or fake-testable behavior for each named
  concept
- make ingestion, active retrieval, and salience explicit caller-owned actions,
  never implicit runner behavior

This revision addresses those findings by defining the `metadata.rag_pipeline`
relationship, v1 schema, collaborator contracts, invocation points, capability
states, evidence shape, trace payload expectations, and no-implicit-save
invariants.

## Debate-Driven Refinement

A follow-up three-round debate found the spec useful as a separate proposed
feature only if its first implementation proves distinct value beyond
`metadata.rag_pipeline`.

The debate decision is:

- keep `memory-aware-context-pipeline` as proposed roadmap material
- make the first implementation slice passive-context handoff-only and
  fake-testable; it must not invoke a retriever
- do not implement salience or ingestion behavior in v1
- reassess after the first slice; if the distinct memory semantics do not
  matter in practice, fold remaining ideas back into `metadata.rag_pipeline`

This means the spec may describe salience, active retrieval, and ingestion
collaborator contracts, but implementation authorization for v1 covers only
validation, capability/status, memory evidence shape, passive context handoff,
and trace metadata for caller-provided memory evidence.

## Non-Goals

This feature must not introduce:

- a dependency on `memlayer`
- runner-owned vector storage, graph storage, Chroma, NetworkX, or embeddings
- runner-owned durable memory persistence
- background consolidation, curation, or reminder threads
- provider-specific wrapper clients
- live model calls from unit tests
- automatic saving of every user prompt
- implicit memory retrieval outside declared workflow/context policy
- a new primitive node type in v1

## Direct Support Boundary

Memory support should be directly supported as an orchestration contract, not
as infrastructure.

Eventual runner-owned responsibilities:

- parse and validate memory declarations
- expose memory capability/status diagnostics
- enforce required collaborators before execution
- carry provenance and memory metadata through traces
- pass retrieved memories into `context-management-prepare-stage`
- provide hooks where caller-owned salience, ingestion, retrieval, and graph
  traversal tools can participate in workflow execution

Caller-owned responsibilities:

- decide what content is eligible to become durable memory
- classify salience, importance, expiration, and memory kind
- calculate optional novelty, access/usage, and outcome signals used by the
  caller's retrieval, consolidation, retention, or ingestion policy
- generate embeddings or graph representations
- store vector, graph, lexical, episodic, semantic, or procedural memories
- execute retrieval, graph traversal, fusion, reranking, and compression
- manage retention, deletion, redaction, permissions, and tenant policy
- operate background jobs, schedulers, curation, and memory compaction

## Active RAG and Passive Memory Context

`memory_pipeline` must not become a parallel, fuzzier copy of `rag_pipeline`.
The two surfaces have different purposes and different runtime roles:

- `metadata.rag_pipeline` describes retrieval over knowledge sources such as
  documents, indexes, graph stores, and external corpora. RAG is active
  turn-time evidence retrieval.
- `metadata.memory_pipeline` describes workflow access to caller-owned durable
  agent/user memory, including persistence eligibility, salience policy,
  temporal provenance, memory identity, passive context selection, and explicit
  ingestion collaborators. It is a passive context policy, not a retriever.

An explicitly invoked caller-owned memory tool may actively retrieve memory
evidence, including from infrastructure shared with RAG. That operation occurs
outside the passive memory pipeline; the pipeline only validates, annotates,
and hands off the resulting memory evidence. DAR should not care whether the
caller uses a vector store, graph store, database, file store, or service. The
distinction is the contract presented to workflow authors: memory has identity,
ownership, retention, salience, and ingestion semantics that ordinary RAG
metadata does not carry.

When a workflow only needs document or corpus retrieval, use
`metadata.rag_pipeline`. Use `metadata.memory_pipeline` only when the workflow
declares passive long-term user/agent memory context or explicit memory
ingestion. Any active memory retrieval must be an explicit caller-owned tool
invocation, not an implicit memory-pipeline action.

If both are present, validation should treat them as separate declarations that
may share caller-owned tool ids only when the manifest says so explicitly.

When `metadata.rag_pipeline` and `metadata.memory_pipeline` are both present,
they must remain separate data flows. Content retrieved through RAG must not be
persisted into caller-owned context memory by DAR, by memory-pipeline default
behavior, or by a generic "retrieved context" handoff. Persisting RAG evidence
as memory requires an explicit workflow step that calls a caller-owned memory
ingestion tool with deliberate input selected by the workflow author. The
presence of both pipelines is never implicit consent to convert RAG results into
long-term memory.

## Manifest Shape

Memory behavior is declared under metadata and consumed by existing workflow
nodes, tool registry entries, and context preparation.

```yaml
metadata:
  patterns_present:
    - rag
    - memory_retrieval
  memory_pipeline:
    mode: hybrid
    retrieval_tiers:
      fast:
        retriever_tool_id: memory_search_fast
        max_results: 2
        graph_traversal: false
      balanced:
        retriever_tool_id: memory_search_balanced
        max_results: 5
        graph_traversal: false
      deep:
        retriever_tool_id: memory_search_deep
        max_results: 10
        graph_traversal: true
    salience:
      classifier: caller_tool
      tool_id: memory_salience_check
      save_policy: salient_only
    ingestion:
      tool_id: memory_ingest
      trigger: explicit_workflow_step
    provenance_required: true
    context_assembly:
      target: prepare_model_input
      lane: retrieved_context
      max_context_tokens: 4096
      required_evidence_fields:
        - memory_id
        - source
        - created_at
        - relevance_score
```

## Minimal V1 Contract

V1 is intentionally narrow:

1. Validate `metadata.memory_pipeline`.
2. Report capability/status for declared memory collaborators.
3. Define trace event names and redacted payload fields.
4. Accept fake memory retriever output that maps into the existing
   `prepare_model_input(...)` retrieved-context lane.
5. Prove that passive memory-specific identity, ownership, and provenance add
   value beyond plain RAG evidence.

Salience, graph traversal, and ingestion remain declared future collaborator
contracts in v1. They may be validated as metadata, but no v1 implementation
should execute or orchestrate them beyond existing generic workflow/tool
mechanics.

V1 must not:

- invoke active retrieval automatically from `prepare_model_input(...)` or
  from passive memory context assembly
- save content automatically at the end of a prompt, node, run, or session
- run background consolidation, curation, reminders, compaction, or deletion
- interpret memory relevance or salience itself
- execute salience or ingestion behavior as part of memory-pipeline v1
- introduce a new primitive node kind

## First Slice Exit Gate

After the first implementation slice, decide whether this spec remains separate
or folds back into RAG.

Keep the separate spec only if fake-test evidence shows at least one
memory-specific contract that `metadata.rag_pipeline` does not already express
cleanly, such as:

- stable `memory_id` identity distinct from document chunk identity
- subject/user/agent memory ownership metadata
- temporal memory provenance such as `created_at` and retention hints
- explicit no-implicit-save policy checked by validation or capability status
- trace payloads that distinguish memory retrieval from ordinary corpus
  retrieval without exposing raw memory content

Fold future work into `metadata.rag_pipeline` if the first slice only proves
generic retrieval, provenance, and context packing.

## V1 Schema

`metadata.memory_pipeline` is a mapping. It is required when
`metadata.patterns_present` contains `memory_retrieval`, `long_term_memory`, or
`memory_ingestion`.

Allowed top-level fields:

- `mode`: optional enum. Allowed: `lightweight`, `hybrid`, `graph`.
- `retrieval_tiers`: optional mapping keyed by tier name. Allowed keys:
  `fast`, `balanced`, `deep`.
- `salience`: optional mapping.
- `ingestion`: optional mapping.
- `provenance_required`: optional boolean.
- `context_assembly`: optional mapping.
- `degraded_states`: optional list of strings.

`retrieval_tiers.<tier>` fields:

- `retriever_tool_id`: required nonblank string.
- `max_results`: optional positive integer.
- `graph_traversal`: optional boolean.
- `required`: optional boolean, default `true`.
- `output_slot`: optional nonblank string, default `retrieved_context`.

`salience` fields:

- `classifier`: optional enum. Allowed: `caller_tool`, `none`.
- `tool_id`: required nonblank string when `classifier` is `caller_tool`.
- `save_policy`: optional enum. Allowed: `salient_only`, `explicit_only`,
  `disabled`. Default: `explicit_only`.

`ingestion` fields:

- `tool_id`: required nonblank string unless ingestion is absent.
- `trigger`: required enum when ingestion is present. Allowed:
  `explicit_workflow_step`.
- `requires_salience`: optional boolean, default `false`.

`context_assembly` fields:

- `target`: required enum when present. Allowed: `prepare_model_input`.
- `lane`: optional enum. Allowed: `retrieved_context`.
- `source_slot`: optional nonblank string, default `retrieved_context`.
- `max_context_tokens`: optional positive integer.
- `required_evidence_fields`: optional list of strings.

Validation must reject unknown retrieval tier keys, malformed fields, missing
required tool ids, unsupported enum values, and `provenance_required: true`
without either nonempty `context_assembly.required_evidence_fields` or a
declared retriever/evidence contract that provides provenance.

## Collaborator Contracts

V1 collaborators are existing caller-owned tools. These contracts describe
expected payloads for validation, trace metadata, and fake tests; they do not
require new runtime infrastructure.

### Caller-Owned Memory Evidence Tool

This is an active caller-owned collaborator, not behavior performed by the
passive memory pipeline. Its output becomes eligible for passive context
handoff only after the explicit workflow invocation.

Input should include:

- `query`: string
- `tier`: `fast`, `balanced`, or `deep`
- `max_results`: optional integer
- `user_id` or caller-owned subject identifier when the workflow provides one
- `filters`: optional mapping

Output should be either:

```yaml
evidence:
  - memory_id: mem_123
    content: "User prefers concise engineering summaries."
    source: "caller_memory_store"
    created_at: "2026-06-21T12:00:00Z"
    memory_kind: episodic
    relevance_score: 0.91
    salience_score: 0.84
    novelty_score: 0.63
    usage_score: 0.40
    outcome_score: 0.75
    source_id: "memory:mem_123"
    chunk_id: "mem_123"
    citation_handle: "memory:mem_123"
    token_estimate: 18
    required: false
```

or a direct list of equivalent evidence mappings.

When present, `salience_score`, `novelty_score`, `usage_score`, and
`outcome_score` are caller-supplied normalized numbers from `0.0` through
`1.0`. They are evidence metadata, not runner-computed ranking authority.

### Salience Tool

Salience is future contract material in v1. The first implementation slice may
validate the declaration shape, but it must not add memory-pipeline runtime
behavior that calls this collaborator automatically.

Input should include:

- `candidate_content`: string
- `memory_kind`: optional string
- `subject_id`: optional caller-owned identifier
- `context`: optional mapping

Output should include:

- `decision`: `save`, `skip`, or `defer`
- `reason`: optional string
- `importance_score`: optional number
- `expiration`: optional timestamp string or null

### Ingestion Tool

Ingestion is future contract material in v1. The first implementation slice may
validate the declaration shape, but it must not add memory-pipeline runtime
behavior that calls this collaborator automatically.

Input should include:

- `content`: string
- `subject_id`: optional caller-owned identifier
- `memory_kind`: optional string
- `salience`: optional salience output mapping
- `provenance`: optional mapping

Output should include:

- `memory_id`: string
- `status`: `stored`, `skipped`, or `deferred`
- `reason`: optional string

## Memory Evidence Handoff

Memory evidence must map onto the existing retrieved-context lane instead of a
new prompt-injection path.

The handoff mapping is:

- `memory_id` becomes a memory-specific provenance identifier.
- `content` becomes the model-visible retrieved-context content.
- `source_id`, `chunk_id`, and `citation_handle` map directly to the existing
  retrieved-context metadata fields when supplied.
- `relevance_score` should map to the existing `score` field.
- `created_at`, `memory_kind`, `owner`, and retention metadata may appear under
  `freshness` or `packing_hint` until a richer retrieved-context metadata
  contract exists.
- Caller-supplied salience, novelty, usage, and outcome scores may appear under
  `packing_hint` with provenance; a scheduled slice must define whether any
  selector consumes them before they affect ordering or omission.
- `required` follows the existing required-context behavior.

If evidence lacks `source_id`, `chunk_id`, or `citation_handle`, the caller
should provide deterministic values derived from `memory_id` when provenance is
required. Missing required provenance is a validation or tool-output error only
when the scheduled implementation slice defines enforcement for live outputs.

## Invocation Points

Active memory evidence retrieval is invoked only by explicit workflow behavior:

- a `tool_use_step` that calls a declared memory retriever, or
- an existing model-tool loop where the memory retriever is exposed as a
  caller-owned tool by policy.

Future salience and ingestion behavior may be invoked only by explicit workflow
behavior:

- a `tool_use_step` that calls `memory_salience_check`
- a `tool_use_step` that calls `memory_ingest`
- an existing loop that exposes those tools by policy

Those salience and ingestion invocations are not part of the first
memory-pipeline implementation slice.

`prepare_model_input(...)` may pack retrieved memory evidence that already
exists in the configured state slot. It must not call memory retrieval,
salience, or ingestion tools itself.

## Capability and Status States

Capability/status reporting should classify memory declarations without
executing tools:

- `metadata_only`: memory metadata is declared, but no registry coverage was
  supplied for live collaborator checks.
- `live_covered`: every required declared memory tool id is present in the
  caller-supplied registry.
- `missing_collaborator`: a required memory retriever, salience tool, or
  ingestion tool is absent from the supplied registry.
- `disabled`: memory declarations or save policy explicitly disable a behavior.
- `degraded`: metadata declares an allowed degraded state such as
  `partial_results`, `stale_but_allowed`, or `graph_unavailable`.
- `invalid`: validation found malformed metadata.

Required missing collaborators should fail preflight when capability/status is
used as an execution gate. Optional missing collaborators should report degraded
or metadata-only status without invoking them.

## Invariants

- DAR must not persist memory unless an explicit caller-owned ingestion tool is
  invoked by workflow execution.
- DAR must not persist RAG-retrieved content into context memory merely because
  `metadata.rag_pipeline` and `metadata.memory_pipeline` are both declared.
- DAR must not retrieve memory outside declared workflow behavior.
- DAR must not mutate model adapter input except through
  `prepare_model_input(...)`.
- DAR must not treat chat/session history as durable memory.
- DAR must not infer salience or memory kind internally.
- DAR must not infer novelty, usage value, or outcome value internally; it may
  carry caller-supplied values and provenance through evidence and diagnostics.
- DAR must not start background memory work.
- DAR must not include raw memory content in trace payloads when existing
  redaction patterns would omit retrieved-context content.

## Functional Requirements

### FR-1: Validate Memory Metadata

The runtime must validate `metadata.memory_pipeline` when
`metadata.patterns_present` includes `memory_retrieval`, `long_term_memory`, or
`memory_ingestion`.

Validation must fail when:

- required retriever tool ids are missing
- retrieval tier names are unknown
- `context_assembly.target` is not `prepare_model_input`
- provenance is required but required evidence fields are absent
- ingestion is declared without a caller-owned ingestion tool
- ingestion declares any trigger other than `explicit_workflow_step`
- salience declares `classifier: caller_tool` without a tool id

### FR-2: Keep Retrieval Caller-Owned

All retrieval, graph traversal, embedding search, salience classification, and
ingestion execution must happen through existing caller-owned tools or adapters.

DAR may validate, route, trace, and pack results. DAR must not implement the
memory backend.

### FR-3: Support Retrieval Tiers

The manifest must support `fast`, `balanced`, and `deep` retrieval tiers.

Tier semantics:

- `fast`: low-latency lookup, few results, no graph traversal
- `balanced`: default memory recall, moderate result count, no required graph
  traversal
- `deep`: richer recall, graph-capable, suitable for "everything about X"
  queries

The tier is metadata and tool-selection input. DAR does not prescribe the
retrieval algorithm.

Undeclared tier keys must be rejected. A workflow may omit a tier entirely; it
must not rely on runner-provided default retrieval behavior for omitted tiers.

### FR-4: Salience Is Explicit

Memory saving must be explicit. A workflow may call a salience tool and then an
ingestion tool, but DAR must not silently persist user prompts or model outputs.

Supported save policies:

- `salient_only`
- `explicit_only`
- `disabled`

`salient_only` means the workflow must call a caller-owned salience collaborator
before a caller-owned ingestion collaborator. It does not authorize DAR to
classify or persist content.

Salience and ingestion orchestration are deferred beyond v1. V1 may validate
their declarations and report collaborator status only.

### FR-5: Context Preparation Owns Prompt Injection

Retrieved memories must enter model input through `prepare_model_input(...)` as
retrieved context, with token budgeting, omission diagnostics, and provenance
metadata.

Model adapters must receive prepared input; they must not perform memory search
or prompt mutation.

### FR-6: Trace Memory Operations

Trace events should distinguish:

- `memory_salience_checked`
- `memory_retrieval_started`
- `memory_retrieval_completed`
- `memory_context_prepared`
- `memory_ingestion_started`
- `memory_ingestion_completed`
- `memory_degraded`

Trace payloads must avoid raw secret leakage and should include counts, tier,
tool id, result ids, omitted count, and degraded reason.

When supplied by a caller-owned collaborator, evidence and trace metadata may
also carry a declared memory kind (`short_term`, `long_term`, `episodic`,
`semantic`, or `procedural`) plus bounded salience, novelty, usage, and outcome
signals. These fields are descriptive policy inputs with provenance; their
presence does not authorize DAR to consolidate, retain, or persist memory.

Trace payloads should use this shape where practical:

```yaml
event_type: memory_retrieval_completed
payload:
  tier: balanced
  tool_id: memory_search_balanced
  result_count: 3
  included_count: 2
  omitted_count: 1
  result_ids:
    - mem_123
    - mem_456
  degraded_reason: null
```

Payloads must not include raw memory content unless a future trace policy
explicitly allows unredacted retrieved-context content.

## Acceptance Criteria

- Workflow validation accepts a manifest with declared memory tiers and covered
  tool ids.
- Workflow validation fails clearly when a required memory tool is missing.
- Workflow validation fails for unknown tier keys, unsupported enum values,
  missing required provenance fields, salience policy mismatch, and ingestion
  without `explicit_workflow_step`.
- A fake memory search tool can return memory evidence that is packed into
  prepared model input.
- V1 does not add salience or ingestion execution paths; their declarations are
  metadata-only or future collaborator contracts.
- Metadata-only memory declarations do not invoke retrieval, salience, or
  ingestion tools during validation or capability inspection.
- Attempted implicit save behavior is rejected by validation or remains
  impossible because no runtime hook exists for it.
- First-slice evidence records whether the distinct memory contract should stay
  separate or be folded back into `metadata.rag_pipeline`.
- Unit tests use fake registries and fake model adapters only.
- DAR gains no required dependency on `memlayer`, `chromadb`,
  `sentence-transformers`, `networkx`, `anthropic`, or `google-genai`.

## Initial Implementation Slices

This spec is not implementation authorization. If scheduled, the first slice
should stay declarative and fake-testable:

1. add validation for `metadata.memory_pipeline`
2. add capability/status reporting for declared memory collaborators
3. add trace event constants or documented event names for memory operations
4. prove retrieved memory evidence can use the existing retrieved-context lane
5. record the first-slice exit-gate decision on whether the separate memory
   contract remains justified
6. defer salience execution, ingestion execution, live retrieval services,
   durable stores, and background services to caller-owned integrations or
   future approved slices
