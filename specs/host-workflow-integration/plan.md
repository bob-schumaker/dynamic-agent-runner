# Host Workflow Integration Slice H2 Plan

## Metadata

- Feature slug: `host-workflow-integration`
- Slice: H2 inline preflight and host lifecycle polish
- Status: implemented
- Date: 2026-06-22
- Owning spec: [`spec.md`](spec.md)

## Objective

Finish the useful deferred host-integration pieces without expanding DAR into a
host runtime. The slice adds in-memory capability preflight for generated
workflows, preserves the existing capability/status report contract, exposes
host id metadata through relevant report summaries, and documents the host
lifecycle choices that downstream applications already need.

## Current Fit

The package already has the right lower-level pieces:

- `load_agent_workflow_artifacts(...)` accepts inline manifest mappings and raw
  YAML strings.
- `LoadedAgentWorkflow` is the in-memory workflow object used by execution and
  validation.
- `inspect_agent_package_capabilities(...)` owns the public preflight report
  contract for package directories.
- `HostToolBinding` stores canonical host ids, model-facing ids, and aliases in
  registry tool definitions.
- README and `docs/files/python-api.rst` already describe direct execution,
  reusable contexts, capability preflight, and `AgentSession`.

H2 connected these pieces without adding a new runtime layer.

## Proposed API Shape

The implemented public helper in the capability/host integration boundary is:

```python
inspect_agent_workflow_capabilities(
    *,
    workflow: LoadedAgentWorkflow | None = None,
    runtime_manifest: ArtifactInput | None = None,
    mermaid_graph: TextInput | None = None,
    agent_design: TextInput | None = None,
    tool_index: ArtifactInput | None = None,
    runtime_overrides: ArtifactInput | None = None,
    tool_registry: object | None = None,
    guardrail_registry: object | None = None,
    model_adapter: object | None = None,
    model_adapter_coverage: str | None = None,
    built_in_tool_packs: Iterable[str] | None = None,
    session_store: object | None = None,
    strict: bool = False,
) -> CapabilityStatusReport
```

The public contract is:

- accept either `workflow` or inline artifact inputs, not both
- return `CapabilityStatusReport`
- avoid creating temporary package directories
- preserve package-directory inspection through
  `inspect_agent_package_capabilities(...)`
- preserve strict/non-strict invalid behavior

## Design Notes

- Refactor capability inspection internally around an already loaded workflow so
  package and inline preflight share one implementation path.
- Keep invalid-report handling package-owned and deterministic. Inline invalid
  manifests should report `package.validation` and include any package id that
  can be safely recovered.
- Host id metadata belongs in `CapabilityStatusItem.details`; existing item ids,
  states, and categories should remain stable.
- Only expose scalar/list metadata from registry definitions:
  `host_canonical_id`, `host_model_id`, and `host_aliases`.
- Documentation should show when to use direct execution, reusable
  `WorkflowExecutionContext`, or `AgentSession`; it should not introduce a new
  host lifecycle abstraction.

## Non-Goals

- No Power-Marimo-specific integration.
- No temporary package generation helper.
- No model-provider selection policy changes.
- No durable host storage, live host callbacks, GUI calls, or external services.
- No changes to generated `docs/source/*.rst`; update `docs/files/*.rst` only.

## Implementation Boundaries

Implemented code touch points:

- `src/dynamic_agent_runner/capabilities.py`
- `src/dynamic_agent_runner/host_integration.py`
- `src/dynamic_agent_runner/__init__.py`
- `tests/test_capabilities.py`
- `tests/test_host_integration.py`
- `README.md`
- `docs/files/python-api.rst`

Do not touch generated docs under `docs/source/`.
