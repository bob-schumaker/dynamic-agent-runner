# Workspace Data Tool Pack Specification

## Metadata

- Feature slug: `workspace-data-tool-pack`
- Mode: `light`
- Artifact type: implemented feature specification
- Status: implemented v1 baseline from downstream Power-Marimo evidence
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Related existing specs:
  - `specs/sandbox-workspace-runtime/spec.md`
  - `specs/persistent-agent-sessions/spec.md`
  - `specs/context-management-prepare-stage/spec.md`
  - `specs/host-workflow-integration/spec.md`
  - `specs/web-tool-pack/spec.md`
  - `specs/rag-orchestration-contract/spec.md`

## Objective

Define an opt-in standard workspace data tool pack for JSON-compatible
read/write/search/list/delete operations over caller-provided workspace or
session data stores.

This generalizes the useful pattern from downstream hosts that let workflows
save structured intermediate results without making DAR own the host's project
file, database, notebook, UI, or durable memory system.

## Problem Statement

Agent workflows often need a place to put structured intermediate artifacts:
analysis notes, extracted facts, temporary summaries, evidence handles,
generated plans, or compact tool outputs. Without a standard tool shape, every
host invents different ids, schemas, metadata fields, search defaults, deletion
semantics, and context-size safeguards.

Power-Marimo shows the reusable pattern:

- model-facing tools expose JSON-compatible data, not host objects
- write/read/search/list/delete are enough for a first pass
- search/list default to metadata-only to avoid flooding context
- unavailable stores return structured `status`, `warnings`, `caveats`, and
  `next_steps`
- host persistence and dirty-state behavior remain downstream-owned

DAR should own the portable tool pack contract, not the host storage backend.

## Implementation Status

The v1 baseline is implemented by `create_workspace_data_registry(...)`,
`WorkspaceDataToolPolicy`, and related registry helpers in
`src/dynamic_agent_runner/registry.py`, with exports from
`dynamic_agent_runner`.

Completed:

- opt-in `workspace_data_write`, `workspace_data_read`,
  `workspace_data_search`, `workspace_data_list`, and
  `workspace_data_delete` tools
- required injected store
- JSON-compatible write validation and maximum item size policy
- metadata-first search/list defaults
- stable `not_found` read/delete results
- delete approval flag in tool metadata
- fake-store tests and import coverage

Deferred:

- runner-owned durable storage, indexing, vector search, and host dirty-state
- richer approval/resume integration beyond delete metadata
- trace redaction beyond ordinary registry/tool behavior
- capability/status states for disabled, missing-store, live, write-disabled,
  delete-approval-required, and policy-rejected configurations

## Scope

This feature covers:

1. an opt-in built-in `workspace_data` tool pack
2. standard tool ids and model-facing schemas
3. injected workspace/session data store interface
4. JSON-compatible item metadata and payload boundaries
5. metadata-only search/list defaults
6. redacted traces and capability/status reporting
7. approval/sandbox policy hooks for write and delete operations
8. fake-store unit tests only

## Non-Goals

This feature must not introduce:

- runner-owned durable database or project file format
- automatic persistence of every tool result
- binary blob storage
- secret storage
- cross-project/global memory
- vector indexing, embeddings, or RAG ingestion
- UI for managing stored data
- host dirty-state, save, sync, or backup behavior

Durable semantic memory remains out of scope. Hosts may bind this pack to their
own project, workspace, or session store.

## Proposed Tool Pack Shape

The first built-in pack should be named `workspace_data` and remain disabled by
default.

Candidate v1 tool ids:

- `workspace_data_write`
- `workspace_data_read`
- `workspace_data_search`
- `workspace_data_list`
- `workspace_data_delete`

The implementation should allow host aliases when a downstream needs names such
as `project_data_write`, but the package-owned standard ids should remain
provider-safe and avoid punctuation that breaks function-name constraints.

Conceptual API shape:

```python
registry = create_workspace_data_registry(
    store=my_store,
    policy=WorkspaceDataToolPolicy(
        max_item_bytes=128_000,
        default_search_limit=20,
        require_delete_approval=True,
    ),
)
```

Names are draft.

## Functional Requirements

### FR-1: Keep workspace data explicitly opt-in

Given no workspace data pack is enabled and no caller registers equivalent
tools, when a workflow references workspace data tool ids, then execution must
fail through the existing unavailable-tool path.

Given the caller enables the pack, when registry preparation runs, then tools
are registered only in the effective registry and are still exposed only to
nodes that reference them.

### FR-2: Require an injected store

Given the workspace data pack is enabled, when executable behavior is needed,
then the caller must provide an explicit store/collaborator.

Missing stores must report `missing_collaborator` in capability/status and fail
clearly at invocation time.

### FR-3: Use JSON-compatible item shape

Given data is written or read, when it crosses the model/tool boundary, then it
must be JSON-compatible and must not expose SDK, GUI, file-handle, model
adapter, Python object, or host-internal instances.

Candidate item fields:

- `id`
- `kind`
- `title`
- `description`
- `tags`
- `labels`
- `data`
- `created_at`
- `updated_at`
- `actor`
- `content_type`

### FR-4: Support write/upsert

Given the model calls `workspace_data_write`, when the payload is valid and
policy allows writes, then the store creates or updates one item and returns
status, operation, item metadata, warnings, caveats, and next steps.

Oversized, non-JSON-compatible, or policy-rejected writes must fail clearly
without partial visible success.

### FR-5: Support read

Given the model calls `workspace_data_read`, when the id exists, then the result
returns the requested item and may include data by default.

Given the id is missing, then the result returns a stable `not_found` status and
actionable next steps.

### FR-6: Support metadata-first search and list

Given the model calls `workspace_data_search` or `workspace_data_list`, when
`include_data` is omitted, then the result must omit item data blobs by default.

Search/list should support query, kind, tags, labels, include-data, and limit
parameters. Search may be simple host/store search; vector or full-text indexes
are not required.

### FR-7: Support delete with policy hooks

Given the model calls `workspace_data_delete`, when deletion is enabled and the
id exists, then one item is deleted and the result names the deleted id.

Delete should be approval-required by default unless host policy marks it safe.

### FR-8: Report capability and trace status

Given workflows reference workspace data tools, when capability status runs,
then the report must distinguish disabled pack, missing store, live store,
write-disabled, delete-approval-required, and policy-rejected states.

Given tools run, when traces are emitted, then traces must include bounded item
ids, operation, status, count, truncation, and error category without dumping
large data blobs or secrets.

## Acceptance Criteria

- `workspace_data` is disabled unless explicitly enabled.
- Missing injected store is reported and fails clearly.
- Tool ids are provider/function-name safe.
- Write/read/search/list/delete use JSON-compatible structured results.
- Search/list default to metadata-only.
- Write rejects oversized or non-JSON-compatible payloads.
- Delete is approval-required or disabled by default unless explicitly trusted.
- Capability/status distinguishes disabled, missing-store, live, and
  policy-rejected states.
- Traces are bounded and redacted.
- Unit tests use fake stores and no live filesystem, database, network, or host
  application.

## Implementation Planning Notes

- Keep the store interface minimal: write, read, search, list, delete.
- Do not define a durable storage backend in the first slice.
- Reuse `ToolResult.model_output` to keep model-visible output compact when raw
  host/store diagnostics are larger.
- Coordinate write/delete approval behavior with `approval-interruption-resume`
  and `sandbox-workspace-runtime`.
- Coordinate future retrieved evidence use with `rag-orchestration-contract`;
  this pack can store evidence handles but must not become RAG infrastructure.

## TDD Implementation Tasks

Completed v1 slices:

1. RED: disabled/missing-store tests; GREEN: opt-in registry and capability
   missing-store failure.
2. RED: write/read tests; GREEN: fake-store write/upsert/read with JSON
   compatibility checks.
3. RED: search/list tests; GREEN: metadata-only defaults, filters, and limits.
4. RED: delete policy tests; GREEN: approval-required delete metadata and
   delete/not-found results.
5. RED: executor integration tests; GREEN: model tool calls use workspace data
   tools through ordinary registry dispatch.

Deferred slices:

1. RED: capability/status tests; GREEN: disabled, missing-store, live,
   write-disabled, delete-approval-required, and policy-rejected states.
2. RED: trace redaction tests; GREEN: bounded operation summaries without large
   blobs.

## Validation Checklist

Relevant commands:

```bash
poetry run pytest tests/test_registry.py tests/test_import.py -q
poetry run pytest tests/test_executor.py -q
```

Future tests must not perform live filesystem, database, network, model, or host
application calls.
