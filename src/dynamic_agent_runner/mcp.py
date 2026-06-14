"""Explicit MCP tool registration helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from dynamic_agent_runner.models import (
    ToolDefinition,
    ToolExposure,
    ToolOriginKind,
    ToolSource,
    ToolSourceKind,
)
from dynamic_agent_runner.registry import (
    InMemoryToolRegistry,
    RegisteredTool,
    ToolHandler,
)


@dataclass(frozen=True)
class MCPToolBinding:
    """Caller-supplied MCP tool descriptor and handler."""

    tool_id: str
    source_id: str
    server_id: str
    mcp_tool_name: str
    handler: ToolHandler
    description_for_llm: str | None = None
    input_schema: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


def registered_tool_from_mcp_binding(binding: MCPToolBinding) -> RegisteredTool:
    """Build a registry tool from an explicit MCP binding."""

    raw_metadata = {
        "id": binding.tool_id,
        "description_for_llm": (
            binding.description_for_llm or f"Use MCP tool {binding.mcp_tool_name}"
        ),
        "input_schema": dict(binding.input_schema or {"type": "object"}),
        "exposure": ToolExposure.HIDDEN.value,
        "approval_required": "yes",
    }
    raw_metadata.update(dict(binding.metadata))
    definition = ToolDefinition.from_mapping(raw_metadata)
    definition = _definition_with_mcp_source(definition, binding)
    return RegisteredTool(definition, binding.handler)


def create_mcp_registry(bindings: list[MCPToolBinding]) -> InMemoryToolRegistry:
    """Create an in-memory registry from explicit MCP tool bindings."""

    return InMemoryToolRegistry(
        registered_tool_from_mcp_binding(binding) for binding in bindings
    )


def _definition_with_mcp_source(
    definition: ToolDefinition,
    binding: MCPToolBinding,
) -> ToolDefinition:
    return ToolDefinition(
        id=definition.id,
        raw=definition.raw,
        label=definition.label,
        tool_type=definition.tool_type,
        adapter=definition.adapter,
        side_effect=definition.side_effect,
        approval_required=definition.approval_required,
        exposure=definition.exposure,
        policy=definition.policy,
        source=ToolSource(
            kind=ToolSourceKind.CALLER_REGISTERED,
            origin=ToolOriginKind.MCP,
            source_id=binding.source_id,
            detail=f"{binding.server_id}:{binding.mcp_tool_name}",
        ),
    )
