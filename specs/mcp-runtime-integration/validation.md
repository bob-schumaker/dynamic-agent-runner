# MCP Runtime Integration V1 Validation Log

Status: Slice 2 MCP policy defaults and registry behavior covered

## Scope

- Feature: `specs/mcp-runtime-integration/spec.md`
- Plan: `specs/mcp-runtime-integration/plan.md`
- Tasks: `specs/mcp-runtime-integration/tasks.md`

## Planned Checks

- `poetry run pytest tests/test_mcp.py tests/test_import.py -q`
- `poetry run pytest tests/test_mcp.py tests/test_registry.py -q`
- `poetry run pytest tests/test_capabilities.py tests/test_mcp.py -q`
- `poetry run pytest tests/test_mcp.py tests/test_registry.py`
  `tests/test_capabilities.py tests/test_import.py -q`
- `pre-commit run --files src/dynamic_agent_runner/mcp.py`
  `src/dynamic_agent_runner/registry.py`
  `src/dynamic_agent_runner/capabilities.py`
  `src/dynamic_agent_runner/__init__.py tests/test_mcp.py`
  `tests/test_registry.py tests/test_capabilities.py tests/test_import.py`
  `specs/mcp-runtime-integration/spec.md`
  `specs/mcp-runtime-integration/plan.md`
  `specs/mcp-runtime-integration/tasks.md`
  `specs/mcp-runtime-integration/validation.md specs/README.md`

## Evidence

- Planning checkpoint resolves v1 as explicit caller-supplied MCP registry
  injection only: no transports, process launch, implicit discovery, schema
  cache, or live MCP infrastructure in tests.
- Planning checkpoint committed in `12b9862`
  (`docs(specs): plan mcp registry injection`).

### T1.1 RED — public MCP registry injection contract

- Command: `poetry run pytest tests/test_mcp.py tests/test_import.py -q`
- Expected result: fail before MCP registry injection exports exist
- Observed result: `4 failed in 0.16s`
- Failure boundary:
  - missing `MCPToolBinding`
  - missing `registered_tool_from_mcp_binding(...)`
  - missing `create_mcp_registry(...)`

### T1.2 GREEN — public MCP registry injection contract

- Command: `poetry run pytest tests/test_mcp.py tests/test_import.py -q`
- Observed result: `4 passed in 0.15s`
- Interpretation: callers can construct explicit MCP tool bindings, convert
  them into registered tools, and build an in-memory registry without live MCP
  infrastructure.

### T2.1/T2.2 Policy Defaults and Registry Behavior

- Command: `poetry run pytest tests/test_mcp.py tests/test_registry.py -q`
- Observed result: `38 passed in 0.17s`
- Interpretation: explicit MCP bindings now preserve MCP provenance, default to
  hidden exposure and approval required, allow trusted caller policy overrides,
  reject duplicate tool ids through existing registry behavior, and invoke
  through `InMemoryToolRegistry`.
- Note: these checks passed without code changes after Slice 1 because the
  initial helper implementation already normalized this metadata.
