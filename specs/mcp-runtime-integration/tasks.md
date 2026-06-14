# MCP Runtime Integration V1 Tasks

Status: planned next implementation slice

## Slice 0 — Planning Checkpoint

- [x] T0.1 Resolve v1 transport, process launch, source configuration,
      namespacing, cache, and default policy decisions in `spec.md`.
- [x] T0.2 Add `plan.md`, `tasks.md`, and `validation.md` before
      implementation.
- [x] T0.3 Commit the planning checkpoint before code changes.
  - Completed in commit `12b9862`
    (`docs(specs): plan mcp registry injection`)

## Slice 1 — Public MCP Registry Injection Contract

- [x] T1.1 [tests] Add RED import/shape tests for MCP tool binding and registry
      construction helpers.
  - Spec: FR-1, FR-3, FR-4
  - Files/components: `tests/test_mcp.py`,
    `src/dynamic_agent_runner/mcp.py`,
    `src/dynamic_agent_runner/__init__.py`
  - Validation: `poetry run pytest tests/test_mcp.py tests/test_import.py -q`
  - RED:
    - `poetry run pytest tests/test_mcp.py tests/test_import.py -q` —
      failed because `MCPToolBinding` and helper exports were missing

- [x] T1.2 [implementation] Add `MCPToolBinding`,
      `registered_tool_from_mcp_binding(...)`, and `create_mcp_registry(...)`.
  - Spec: FR-1, FR-3, FR-4, FR-5
  - Files/components: `src/dynamic_agent_runner/mcp.py`,
    `src/dynamic_agent_runner/__init__.py`
  - Validation: `poetry run pytest tests/test_mcp.py tests/test_import.py -q`
  - GREEN:
    - `poetry run pytest tests/test_mcp.py tests/test_import.py -q` —
      `4 passed in 0.15s`

## Slice 2 — Policy Defaults and Registry Behavior

- [x] T2.1 [tests] Add coverage for MCP provenance, hidden exposure,
      approval-required defaults, duplicate id failure, and registry invocation.
  - Spec: FR-3, FR-4, FR-5
  - Files/components: `tests/test_mcp.py`, `tests/test_registry.py`
  - Validation: `poetry run pytest tests/test_mcp.py tests/test_registry.py -q`
  - Result:
    - `poetry run pytest tests/test_mcp.py tests/test_registry.py -q` —
      `38 passed in 0.17s`
  - Note: these checks were already satisfied by the Slice 1 implementation, so
    no RED failure was produced.

- [x] T2.2 [implementation] Normalize MCP binding metadata into existing
      `ToolDefinition`, `ToolSource`, and `InMemoryToolRegistry` behavior.
  - Spec: FR-3, FR-4, FR-5
  - Files/components: `src/dynamic_agent_runner/mcp.py`,
    `src/dynamic_agent_runner/registry.py`
  - Validation: `poetry run pytest tests/test_mcp.py tests/test_registry.py -q`
  - Result:
    - No additional code change was required after explicit tests; behavior was
      implemented in `dae1b8a`.

## Slice 3 — Capability Status

- [x] T3.1 [tests] Add RED tests that capability status reports MCP metadata as
      metadata-only and caller-supplied MCP-origin registry entries as live.
  - Spec: FR-1, FR-3, FR-6
  - Files/components: `tests/test_capabilities.py`
  - Validation:
    `poetry run pytest tests/test_capabilities.py tests/test_mcp.py -q`
  - RED:
    - `poetry run pytest tests/test_capabilities.py tests/test_mcp.py -q` —
      failed because `mcp.tool.mcp.echo` was not reported

- [x] T3.2 [implementation] Add live MCP registry-entry status reporting without
      launching or invoking MCP infrastructure.
  - Spec: FR-1, FR-3, FR-6
  - Files/components: `src/dynamic_agent_runner/capabilities.py`
  - Validation:
    `poetry run pytest tests/test_capabilities.py tests/test_mcp.py -q`
  - GREEN:
    - `poetry run pytest tests/test_capabilities.py tests/test_mcp.py -q` —
      `13 passed in 0.12s`

## Slice 4 — Completion Evidence

- [x] T4.1 [validation] Run focused affected tests.
  - Command:
    `poetry run pytest tests/test_mcp.py tests/test_registry.py`
    `tests/test_capabilities.py tests/test_import.py -q`
  - Result: `46 passed in 0.17s`

- [x] T4.2 [validation] Run focused pre-commit.
  - Command:
    `pre-commit run --files src/dynamic_agent_runner/mcp.py`
    `src/dynamic_agent_runner/registry.py`
    `src/dynamic_agent_runner/capabilities.py`
    `src/dynamic_agent_runner/__init__.py tests/test_mcp.py`
    `tests/test_registry.py tests/test_capabilities.py tests/test_import.py`
    `specs/mcp-runtime-integration/spec.md`
    `specs/mcp-runtime-integration/plan.md`
    `specs/mcp-runtime-integration/tasks.md`
    `specs/mcp-runtime-integration/validation.md specs/README.md`
  - Result: passed

- [x] T4.3 [docs] Record completion evidence and update spec status before the
      next focus area.
