<!-- rumdl-disable MD013 -->

# Scratchpad Context Store Specification

Feature slug: `scratchpad-context-manager`

Status: Draft, revised after second council review

Source inspiration: [sickn33/antigravity-awesome-skills](https://github.com/sickn33/antigravity-awesome-skills). The source repository's skills and memory-bank patterns show a useful convention: keep large or durable working context outside the immediate model prompt, keep a compact reference or summary in active context, and make scratch work inspectable across workflow steps. This specification adapts that idea for Dynamic Agent Runner without copying Antigravity's repository layout or requiring a bundled storage backend.

## Objective

Add an optional scratchpad context store to Dynamic Agent Runner so workflows can offload large intermediate artifacts without putting full content into the active model context.

The storage implementation must be caller-owned. DAR should depend on a small `Protocol` that models artifacts and metadata, not on local files, a database, or a specific persistence pattern.

The v1 goal is intentionally narrow: when a tool result is too large for model-visible context, DAR stores the full value in the caller's scratchpad store and replaces the prompt/state/trace projection with a compact artifact reference.

## V1 Scope

V1 MUST include:

- public scratchpad protocol types and package-owned scratchpad errors;
- `scratchpad_store: ScratchpadStore | None` as a caller-supplied execution-context collaborator;
- a canonical JSON-serializable `ScratchpadArtifactRef` shape for state, trace, and model-visible projections;
- one automatic offload path for large tool results after tool invocation and before state/trace/model-facing serialization;
- bounded summaries/previews in artifact references;
- fake in-memory store tests proving existing behavior is unchanged when scratchpad is disabled or unavailable.

V1 MUST NOT include model-exposed scratchpad tools, delegated scratchpad tool providers, read/describe/list/search/delete/select/open APIs, prepared-context offload, session-history offload, or full resume semantics.

## Problem

Current workflow context is optimized for short-lived message and tool state. That makes it awkward to support workflows that need to:

- retain bulky tool results without sending them back to the model every turn;
- carry concise artifact references across nodes;
- preserve bounded trace diagnostics without leaking full content;
- attach metadata such as content type, origin, size, expiration, or summary;
- leave storage, tenancy, retention, search, and indexing policy to the caller.

A file-object-like interface handles bytes and text, but it over-specifies storage mechanics and under-specifies artifact identity, metadata, and persistence. A store interface keeps DAR's code simpler: DAR writes artifacts, records returned metadata, and projects compact references into workflow state, traces, and prompts.

## Design Summary

Introduce a caller-supplied `ScratchpadStore` protocol with one required v1 operation:

1. `put(...) -> ScratchpadArtifact`

`ScratchpadArtifact` is store-returned metadata. `ScratchpadArtifactRef` is the JSON-serializable reference DAR stores in workflow state, trace payloads, and model-visible context.

The simple v1 explanation is:

> When a tool returns a large value, DAR puts the large value in the caller's store and gives the workflow/model a label, summary, preview, and metadata.

## Proposed Public Types

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Mapping, Protocol, runtime_checkable

ScratchpadData = str | bytes
ScratchpadScope = Literal["run", "session", "durable"]


class ScratchpadError(Exception):
    """Base error for scratchpad policy, validation, and storage failures."""


class ScratchpadPolicyError(ScratchpadError):
    """Scratchpad policy rejected an operation before storage was called."""


class ScratchpadStoreError(ScratchpadError):
    """The caller-provided store failed a scratchpad operation."""


class ScratchpadInvalidArtifactError(ScratchpadError):
    """The store returned invalid artifact metadata."""


@dataclass(frozen=True)
class ScratchpadArtifact:
    artifact_id: str
    scope: ScratchpadScope
    content_type: str | None = None
    size_bytes: int | None = None
    created_at: datetime | None = None
    expires_at: datetime | None = None
    summary: str | None = None
    preview: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScratchpadArtifactRef:
    artifact_id: str
    scope: ScratchpadScope
    type: Literal["scratchpad_artifact_ref"] = "scratchpad_artifact_ref"
    content_type: str | None = None
    size_bytes: int | None = None
    created_at: str | None = None
    expires_at: str | None = None
    summary: str | None = None
    preview: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_mapping(self) -> dict[str, Any]:
        """Return a compact JSON-serializable reference payload.

        V1 omits keys whose value is ``None`` and omits ``metadata`` when empty.
        """
        ...


@runtime_checkable
class ScratchpadStore(Protocol):
    def put(
        self,
        data: ScratchpadData,
        *,
        artifact_id: str | None = None,
        scope: ScratchpadScope = "run",
        content_type: str | None = None,
        summary: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        expires_at: datetime | None = None,
    ) -> ScratchpadArtifact:
        """Store an immutable artifact and return canonical metadata."""
        ...
```

## Store Contract

DAR treats the caller's store as the source of truth for stored artifact metadata.

Store invariants:

- `artifact_id` returned from `put` MUST be a non-empty string.
- `scope` MUST be one of `run`, `session`, or `durable`.
- Artifact IDs are opaque. DAR MUST NOT parse them as paths, URLs, UUIDs, or content hashes.
- `artifact_id` MUST identify one artifact within the caller's store boundary without DAR passing separate scope, run, session, or tenant parameters. Stores that need scoped identity must encode that scope inside the opaque ID or store-managed state.
- DAR MUST NOT join artifact IDs into filesystem paths or normalize path separators.
- Store-returned metadata is authoritative input to DAR's artifact projection, but DAR still applies v1 projection bounds, protected metadata rules, and redaction rules before creating `ScratchpadArtifactRef`.
- Automatic v1 offload SHOULD call `put` with `artifact_id=None`; store allocation is preferred.
- Artifacts are immutable from DAR's perspective in v1. If a caller-supplied `artifact_id` collides with an existing artifact, the store SHOULD raise `ScratchpadStoreError` rather than silently overwrite.
- `created_at` and `expires_at` in `ScratchpadArtifactRef` MUST be UTC ISO-8601 strings when present.
- `metadata` in `ScratchpadArtifactRef` MUST be JSON-serializable.

Metadata merge and projection rules:

- DAR-owned origin keys are protected: `workflow_id`, `run_id`, `node_id`, `tool_id`, `origin`, `producer_type`, and `producer_id`.
- If store metadata contains a protected key, DAR's value wins in the final `ScratchpadArtifactRef.metadata`.
- Store metadata that conflicts with protected keys MAY be preserved under `store_metadata` when useful, but MUST NOT overwrite DAR-owned origin.
- `summary` and `preview` returned by the store MUST be re-bounded by DAR before projection.
- Final `summary` MUST be at most `max_summary_chars`.
- Final `preview` MUST be at most `max_preview_chars`.
- `content_type` returned by the store is authoritative unless it is missing or invalid. If missing or invalid, DAR uses its inferred content type or omits the field.
- `token_estimate` and `content_hash` are not v1 typed fields. Stores MAY include them in metadata, but DAR MUST NOT compute or depend on them in v1.
- `ScratchpadArtifactRef.to_mapping()` omits `None` values and empty metadata for compact, deterministic prompt/state payloads.

Error translation:

- Invalid policy, size, scope, or missing-store conditions become `ScratchpadPolicyError`.
- Store operation failures become `ScratchpadStoreError`.
- Empty IDs, invalid scopes, non-serializable ref metadata, or invalid store-returned metadata become `ScratchpadInvalidArtifactError`.
- Public executor/tool boundaries MUST translate scratchpad failures into existing package-owned workflow or tool errors without leaking full artifact content.

## Runtime Integration

Add an optional store collaborator to the workflow execution context:

```python
@dataclass
class WorkflowExecutionContext:
    ...
    scratchpad_store: ScratchpadStore | None = None
```

This matches DAR's current collaborator pattern for caller-owned registries, adapters, hooks, stores, and context selectors.

When no store is supplied:

- scratchpad-disabled workflows behave exactly as they do today;
- scratchpad-enabled workflows behave exactly as they do today when `require_store=false`;
- scratchpad-enabled workflows fail during validation/startup when `require_store=true`.

## Canonical Artifact Reference

The reference shape used in state, trace, and model-visible context MUST be a compact `ScratchpadArtifactRef`, not the full `ScratchpadArtifact` object and not raw store content.

Example:

```python
{
    "type": "scratchpad_artifact_ref",
    "artifact_id": "store-owned-id",
    "scope": "run",
    "content_type": "application/json",
    "size_bytes": 18432,
    "summary": "Tool result from node collect_docs.",
    "preview": "{\"nodes\": 417, \"edges\": 1292, ...}",
    "metadata": {
        "workflow_id": "...",
        "run_id": "...",
        "node_id": "collect_docs",
        "origin": "tool_result",
        "producer_type": "tool",
        "producer_id": "collect_docs",
        "schema_name": "dependency_graph",
        "schema_version": "1",
        "top_level_keys": ["nodes", "edges", "communities"],
    },
}
```

The same canonical ref may have different projections:

- workflow state stores the full serializable ref;
- trace payloads store the ref and bounded diagnostics according to redaction policy;
- model-visible prompts receive the ref plus summary/preview, never full content by default.

## V1 Offload Placement

V1 offload happens at one choke point: after a tool invocation returns a `ToolResult` or raw tool value, and before DAR serializes that result into node output, workflow state, trace payloads, or model-facing prompt content.

The implementation SHOULD make this boundary explicit with a helper shaped like:

```python
def _offload_tool_result_if_needed(...) -> ToolResult:
    ...
```

This helper is the only v1 place where full tool content may cross into scratchpad storage. It must return the same public `ToolResult` shape DAR already uses, but with offloaded content replaced by a compact artifact reference.

For an eligible large tool result:

1. DAR materializes the tool value into canonical `str` or `bytes`.
2. DAR computes bounded preliminary metadata such as content type, byte size, summary, preview, origin, workflow ID, run ID, node ID, and tool ID when available.
3. DAR calls `scratchpad_store.put(...)` with the full string/bytes payload.
4. DAR validates the returned `ScratchpadArtifact`.
5. DAR creates `ScratchpadArtifactRef` from store-returned metadata plus DAR origin metadata.
6. DAR projects the ref into model-facing output and workflow state.
7. DAR emits trace payloads containing the ref and bounded diagnostics, not the full artifact content.

V1 MUST NOT store the full artifact content in trace payloads, persisted session messages, or model-visible prompts when diagnostics are `redacted` or `metadata_only`.

Implementation notes for current DAR surfaces:

- The model-facing value should become the artifact ref envelope.
- Raw full content may exist only as transient in-process data needed to call the store.
- `raw_output` or equivalent diagnostic fields MUST NOT contain full offloaded content unless a future explicit `diagnostics: full` policy is implemented and tested.
- Lifecycle hooks that observe post-tool state should see the post-offload projection unless an implementation plan explicitly documents a pre-offload hook point.

## Tool Result Materialization

DAR MUST normalize a tool result before applying size checks, content type inference, preview generation, and storage.

Supported v1 materialization:

- `bytes` are stored unchanged with `content_type="application/octet-stream"` unless a safer caller/tool content type is available.
- `str` is stored unchanged and measured as UTF-8 bytes.
- JSON-compatible mappings, lists, strings, numbers, booleans, and `None` are serialized with deterministic JSON settings: UTF-8, sorted keys, compact separators, and no ASCII escaping.
- `ToolResult` values are normalized from their model-facing value unless the implementation explicitly routes direct raw tool output before constructing `ToolResult`.
- Unsupported custom Python objects fail with `ScratchpadPolicyError` rather than falling back to `repr(...)`.

Size checks:

- `max_inline_bytes` and `max_artifact_bytes` are measured on the exact bytes that would be stored.
- Content at or below `max_inline_bytes` remains inline.
- Content above `max_inline_bytes` and at or below `max_artifact_bytes` is eligible for offload.
- Content above `max_artifact_bytes` fails before `scratchpad_store.put(...)`.

Preview rules:

- Text previews are produced from decoded text and truncated to `max_preview_chars`.
- Binary previews are omitted unless a future binary-preview policy is added.
- JSON previews are generated from the deterministic serialized JSON string.

Unsupported or failed materialization is not a storage failure; it is a scratchpad policy failure.

## Offloaded ToolResult Contract

After `_offload_tool_result_if_needed(...)` returns an offloaded result, no full artifact content may remain in any DAR-visible `ToolResult` field.

Required post-offload `ToolResult` shape:

- `output` MUST be the `ScratchpadArtifactRef.to_mapping()` payload.
- `model_output` MUST be `None` or the same ref payload as `output`; it MUST NOT contain full artifact content.
- `raw_output` MUST be `None` in v1 for offloaded results.
- `event_payload` MUST contain only bounded metadata and MUST NOT contain full artifact content.
- `log_preview` MAY contain a bounded summary or preview, capped by policy.
- `sensitive_fields` MUST mark any field that could contain scratchpad diagnostics if future policies add richer diagnostics.

Required call placement:

- direct `tool_use_step` execution MUST call the helper before updating `state.tool_results`, node outputs, traces, or lifecycle hooks;
- model-tool loop execution MUST call the helper before constructing tool-result messages for the model;
- any `_unwrap_output` or equivalent node-output logic MUST see the post-offload ref, not the full artifact content;
- post-tool lifecycle hooks see the post-offload `ToolResult` in v1.

Once offload is attempted, V1 offload is atomic: either storage succeeds and all DAR-visible projections receive a valid `ScratchpadArtifactRef`, or the workflow fails with a package-owned error. V1 MUST NOT fall back to inline content after a failed store call, and V1 MUST NOT emit degraded artifact refs.

## Policy Configuration

V1 policy lives at `runtime.execution_policy.scratchpad_context` in the workflow manifest. If the key is absent, scratchpad offload is disabled. Runtime context may provide the `scratchpad_store` collaborator, but v1 does not define a separate execution-context policy override.

V1 policy should stay small:

```yaml
scratchpad_context:
  enabled: true
  require_store: false
  default_scope: run
  max_inline_bytes: 4096
  max_artifact_bytes: 1048576
  max_summary_chars: 240
  max_preview_chars: 800
  diagnostics: redacted
  offload:
    tool_outputs: true
    tool_errors: false
```

Policy meanings:

- `enabled`: enables scratchpad offload behavior when a store is available.
- `require_store`: fail workflow startup if enabled and no store is supplied.
- `default_scope`: scope used when automatic offload stores an artifact; v1 default is `run`.
- `max_inline_bytes`: model-facing content larger than this is eligible for offload.
- `max_artifact_bytes`: maximum artifact size DAR will submit to the store in one `put`.
- `max_summary_chars`: maximum summary stored in prompt-visible metadata.
- `max_preview_chars`: maximum preview stored in prompt-visible metadata.
- `diagnostics`: `redacted` or `metadata_only` in v1.
- `offload.tool_outputs`: enables large tool-result offload.
- `offload.tool_errors`: deferred by default; error content may contain sensitive data and needs separate tests.

V1 MUST NOT include `session_reference_policy`, model-visible scratchpad tool policy, delegated tool allowlists, line-range selectors, search/list/delete policy, prepared-context offload, or session-history offload.

Node-level scratchpad policy overrides are deferred. V1 uses the same policy for direct `tool_use_step` results and model-tool-loop results.

## Worked Example

Configuration:

```yaml
scratchpad_context:
  enabled: true
  require_store: true
  default_scope: run
  max_inline_bytes: 4096
  max_artifact_bytes: 1048576
  max_summary_chars: 240
  max_preview_chars: 120
  diagnostics: redacted
  offload:
    tool_outputs: true
    tool_errors: false
```

A tool returns a 10 KB JSON object:

```json
{
  "nodes": [{"id": "a"}, {"id": "b"}],
  "edges": [{"source": "a", "target": "b"}],
  "sentinel": "FULL_BLOB_SENTINEL repeated many times..."
}
```

Expected store call:

```python
scratchpad_store.put(
    data=<full JSON string>,
    scope="run",
    content_type="application/json",
    summary="Large JSON tool result from node collect_docs.",
    metadata={
        "origin": "tool_result",
        "producer_type": "tool",
        "producer_id": "collect_docs",
        "node_id": "collect_docs",
        "top_level_keys": ["nodes", "edges", "sentinel"],
    },
)
```

Expected model-visible replacement:

```json
{
  "type": "scratchpad_artifact_ref",
  "artifact_id": "artifact-123",
  "scope": "run",
  "content_type": "application/json",
  "size_bytes": 10240,
  "summary": "Large JSON tool result from node collect_docs.",
  "preview": "{\"nodes\": [{\"id\": \"a\"}, {\"id\": \"b\"}], \"edges\": ...",
  "metadata": {
    "origin": "tool_result",
    "producer_type": "tool",
    "producer_id": "collect_docs",
    "node_id": "collect_docs",
    "top_level_keys": ["nodes", "edges", "sentinel"]
  }
}
```

The full sentinel string MUST be absent from model-visible prompt content and redacted trace payloads. The fake store in tests MUST contain the full JSON exactly once.

## Persistence Scope

Scopes are metadata in v1, not a durable resume guarantee.

- `run`: valid only for the current workflow run.
- `session`: valid for a caller-defined session boundary when the caller's store supports that boundary.
- `durable`: valid across sessions until deleted or expired by the caller's store.

V1 automatic offload SHOULD default to `run`. V1 MUST NOT claim that `session` or `durable` refs are restart-safe unless a later resume feature defines session identity, missing-artifact behavior, and snapshot policy.

Future resume work should define:

- whether `session` references are tied to `AgentSessionState.session_id`;
- whether `run` references are omitted from snapshots;
- whether missing `session` or `durable` refs fail the run or produce a future degraded-ref shape;
- how store metadata is revalidated on resume.

## Subagents and LLM-as-Tool Outputs

Subagents and LLM-as-tool adapters should not require a special v1 path. If their large structured output enters DAR through the same tool-result choke point, it is handled by v1 offload and identified through metadata:

```python
{
    "origin": "tool_result",
    "producer_type": "subagent",
    "producer_id": "graph-reviewer",
    "schema_name": "dependency_graph",
    "schema_version": "1",
}
```

Special handling for raw subagent outputs, custom subagent contracts, or model-exposed retrieval tools is deferred until the basic tool-result offload path is proven.

## Future DAR Tool Layer

The scratchpad surface is sufficient for a future DAR-provided tool layer, but that is not part of v1.

Future built-in scratchpad tools should be expressed as an opt-in registry/tool-pack integration, matching existing DAR patterns such as `create_workspace_data_registry(...)`, rather than as a new parallel `ScratchpadToolProvider` abstraction.

Future extension protocols may include:

```python
@runtime_checkable
class ScratchpadMetadataStore(ScratchpadStore, Protocol):
    def describe(self, artifact_id: str) -> ScratchpadArtifact:
        """Return artifact metadata without loading content."""
        ...


@runtime_checkable
class ScratchpadReadableStore(ScratchpadMetadataStore, Protocol):
    def get(
        self,
        artifact_id: str,
        *,
        offset: int = 0,
        limit: int | None = None,
        encoding: str | None = "utf-8",
    ) -> ScratchpadData:
        """Return full or bounded artifact content."""
        ...
```

Retrieval range semantics, read authorization, missing-artifact behavior, and degraded references belong to that future read surface, not v1 automatic offload.

Potential future tools:

- `scratchpad_put`: store bounded text, bytes, or JSON-serializable content and return a compact artifact ref;
- `scratchpad_describe`: return metadata for an artifact ID already authorized by workflow state or caller policy;
- `scratchpad_read`: return bounded content for an artifact ID already authorized by workflow state or caller policy.

Future authorization rule:

- DAR-provided scratchpad read/describe tools may operate only on artifact refs already present in workflow state, or on IDs explicitly authorized by trusted caller policy.
- Search, list, delete, retention, legal hold, indexing, summarization, schema-aware projections, and cross-artifact relationships remain caller-owned.

## Functional Requirements

### FR1: Caller-Owned Store

DAR MUST accept a caller-supplied `ScratchpadStore | None` through the workflow execution context or equivalent public construction API.

Acceptance criteria:

- Existing callers work unchanged when no store is provided.
- A fake in-memory store can satisfy the protocol in tests.
- DAR does not import or depend on a concrete storage backend.

### FR2: Canonical Artifact Reference

DAR MUST represent offloaded content with `ScratchpadArtifactRef` in state, traces, and model-visible projections.

Acceptance criteria:

- Refs are JSON-serializable.
- Refs use `type == "scratchpad_artifact_ref"`.
- Refs contain no full artifact content.
- Store-returned metadata is re-bounded and merged without overriding protected DAR origin keys.
- Invalid store-returned metadata fails closed.

### FR3: Tool Result Offload

When configured, DAR MUST offload eligible large tool results into the store and replace model-facing content with a compact artifact ref.

Acceptance criteria:

- Tool results at or below `max_inline_bytes` remain inline by default.
- Tool results above `max_inline_bytes` are stored when a store is available.
- Tool results above `max_artifact_bytes` fail with `ScratchpadPolicyError`.
- Model-visible context includes ref metadata, not full artifact content.
- The full artifact is stored exactly once for one eligible tool result.
- Arbitrary custom Python objects fail with `ScratchpadPolicyError` instead of being stored via `repr(...)`.

### FR4: Exact Context Boundary

Scratchpad offload MUST happen after tool invocation and before node output, workflow state, trace payload, and model-facing serialization.

Acceptance criteria:

- Workflow state receives a serializable artifact ref.
- Model prompts receive a ref with bounded summary/preview.
- Trace output records refs without full content when diagnostics are redacted.
- Any hook or trace point that observes pre-offload raw content is explicitly documented before implementation.

### FR5: Store Contract and Error Mapping

DAR MUST define store invariants and package-owned error mapping before implementation.

Acceptance criteria:

- Empty artifact IDs are rejected.
- Artifact IDs remain opaque even when they look like paths.
- Storage failures are translated to package-owned errors at public boundaries.

### FR6: Offloaded ToolResult Contract

DAR MUST ensure offloaded tool results cannot leak full artifact content through existing `ToolResult` surfaces.

Acceptance criteria:

- Offloaded `ToolResult.output` is the artifact ref payload.
- Offloaded `ToolResult.model_output` is `None` or the same artifact ref payload.
- Offloaded `ToolResult.raw_output` is `None`.
- Offloaded `ToolResult.event_payload` contains only bounded metadata.
- Direct tool-use and model-tool-loop paths both call the offload helper before state, trace, hook, and model-result serialization.

### FR7: Bounded Metadata and Redaction

Prompt-visible and trace-visible scratchpad metadata MUST be bounded and deterministic.

Acceptance criteria:

- `summary` is truncated to `max_summary_chars`.
- `preview` is truncated to `max_preview_chars`.
- Diagnostics in v1 are `redacted` or `metadata_only`.
- Full offloaded content is absent from model-visible prompt content.
- Full offloaded content is absent from redacted trace payloads.

### FR8: Persistence Scope Is Honest

Every stored artifact MUST carry a `scope`, but v1 MUST NOT promise restart-safe dereference.

Acceptance criteria:

- V1 automatic offload defaults to `run`.
- `session` and `durable` are documented as caller/store claims, not DAR resume guarantees.
- Resume behavior remains deferred unless a later feature defines session identity, missing-artifact behavior, and any degraded-ref shape.

### FR9: Existing Behavior Compatibility

Scratchpad integration MUST preserve existing behavior unless explicitly enabled and configured.

Acceptance criteria:

- With scratchpad disabled, existing workflows produce identical model-facing results.
- With scratchpad enabled, `require_store=false`, and no store, existing workflows produce identical model-facing results.
- With scratchpad enabled, `require_store=true`, and no store, workflow startup fails with a package-owned configuration error.

## Non-Functional Requirements

- The protocol must remain dependency-free and standard-library-only.
- Unit tests must not depend on live OpenAI, Hugging Face, Marimo, local model servers, or external storage.
- Error messages must identify the scratchpad operation and artifact ID when safe, without leaking artifact content.
- Prompt-visible scratchpad metadata must be bounded and deterministic for tests.
- The implementation should align with DAR's existing `WorkflowExecutionContext`, `ToolResult`, trace, and registry/tool-pack patterns.

## Non-Goals

- Build a bundled durable store in v1.
- Define a global scratchpad directory layout.
- Require a file-like object for all stores.
- Add model-exposed `scratchpad.*` tools in v1.
- Add delegated scratchpad tool providers in v1.
- Add read/describe/list/search/delete/select/open APIs in v1.
- Offload prepared context or session history in v1.
- Guarantee persistence beyond a run in v1.
- Replicate the full Antigravity skills or memory-bank system.

## Suggested Implementation Slices

### Slice 1: Protocol, Policy, and Reference Contract

- Add public `ScratchpadArtifact`, `ScratchpadArtifactRef`, `ScratchpadScope`, `ScratchpadData`, `ScratchpadStore`, and scratchpad error types.
- Add minimal scratchpad policy parsing/defaults.
- Add `scratchpad_store` to workflow execution context.
- Add fake in-memory store tests for protocol validation and invalid metadata.

### Slice 2: Tool Result Materialization and Projection

- Add deterministic materialization for strings, bytes, and JSON-compatible values.
- Add artifact-ref projection with metadata merge, protected DAR keys, and bounded summary/preview.
- Add pure helper tests for boundaries, unsupported objects, metadata conflicts, and `to_mapping()` shape.

### Slice 3: Direct Tool Result Offload

- Identify the single point where tool outputs become node output/state/trace/model-facing content.
- Store eligible large outputs through `ScratchpadStore.put`.
- Replace inline model-facing content with `ScratchpadArtifactRef` through `_offload_tool_result_if_needed(...)`.
- Add tests for inline, offloaded, missing-store, require-store, oversize, invalid-artifact, and store-error paths.

### Slice 4: Model Tool Loop Offload

- Route model-tool loop results through the same offload helper.
- Prove model-tool result messages receive refs instead of full content.

### Slice 5: Projection and Redaction

- Ensure prompts, state, and redacted traces receive bounded artifact refs.
- Add a worked-example fixture with a large JSON sentinel.
- Prove the sentinel is present in the fake store and absent from state, model-visible prompt content, redacted trace payloads, and post-tool hook observations.

## Deferred Work

- Model-exposed scratchpad registry/tool pack.
- Caller-delegated scratchpad tools.
- Metadata/read protocol extensions such as `ScratchpadMetadataStore` and `ScratchpadReadableStore`.
- File-like streaming via a future `open` extension.
- Structured fragment retrieval via JSON Pointer, JSONPath, or caller-owned selector tools.
- Search, list, delete, retention, expiration sweeps, and legal hold behavior.
- Content-addressed artifact IDs.
- DAR-computed token estimates and content hashes.
- Degraded artifact refs.
- Full resume semantics for `session` and `durable` refs.
- Subagent-specific raw-output contracts beyond the shared tool-result offload path.
- Prepared-context and session-history offload.
- Encryption, tenant isolation, and policy enforcement beyond metadata passthrough.
- Rich artifact relationships such as parent/child, derived-from, or citation graphs.

## Testing Strategy

Unit tests should use a fake in-memory store that records calls and can simulate missing artifacts or storage failures.

Required v1 test coverage:

- no-store behavior remains unchanged when scratchpad context is disabled;
- enabled plus `require_store=false` and no store remains unchanged;
- enabled plus `require_store=true` fails fast without a store;
- large JSON tool result is stored and replaced by `ScratchpadArtifactRef`;
- large dict/list tool result is deterministically serialized before storage;
- small tool result remains inline;
- store-returned metadata is re-bounded and merged without overriding protected DAR origin keys;
- empty artifact ID returned by a store fails closed;
- path-like artifact IDs are treated as opaque strings;
- artifact above `max_artifact_bytes` fails before store call;
- unsupported custom objects fail before store call;
- full JSON sentinel is present in the fake store exactly once;
- full JSON sentinel is absent from `ToolResult.output`, `model_output`, `raw_output`, and `event_payload` after offload;
- full JSON sentinel is absent from workflow state stringification;
- full JSON sentinel is absent from model-visible prompt content;
- full JSON sentinel is absent from redacted trace payloads;
- full JSON sentinel is absent from post-tool hook observations;
- summary is bounded by `max_summary_chars`;
- preview is bounded by `max_preview_chars`;
- store errors are translated to package-owned workflow/tool errors.

## Open Questions

- Should `tool_errors` remain deferred until there is a separate sensitivity policy for exception text?
- Should a future model-visible scratchpad tool pack use names such as `scratchpad_read` to match current tool ID conventions, or `scratchpad.read` if provider/tooling support permits dots?
- Should `describe` be required by the first future read surface, or stay optional until a model-visible scratchpad tool pack needs it?
