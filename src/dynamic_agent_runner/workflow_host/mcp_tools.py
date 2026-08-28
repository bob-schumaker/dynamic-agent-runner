"""Host-owned read-only MCP handlers derived from reviewed capability bindings."""

from __future__ import annotations

from collections.abc import Mapping
from threading import Lock
from typing import Protocol

from dynamic_agent_runner import HostToolBinding

from dynamic_agent_runner.workflow_host.descriptor import DeclaredTool
from dynamic_agent_runner.workflow_host.mcp_binding import (
    MCPWorkflowCapabilityBindingControlPlane,
    MCPWorkflowCapabilityBindingError,
)
from dynamic_agent_runner.workflow_host.mcp_surfaces import (
    CurrentMCPSurfaceClient,
    MCPDiscoveredTool,
    MCPSurfaceSnapshotControlPlane,
    MCPSurfaceSnapshotError,
)
from dynamic_agent_runner.workflow_host.policy import WorkflowPolicy


class MCPReadOnlyToolClient(CurrentMCPSurfaceClient, Protocol):
    """A live MCP client that can call one host-approved remote tool."""

    def call_tool(
        self, name: str, arguments: Mapping[str, object]
    ) -> Mapping[str, object]:
        """Call one remote tool through its authenticated connection."""


class MCPToolBindingError(ValueError):
    """Raised when host-owned MCP tool construction or dispatch is unsafe."""


class MCPToolCallCounter:
    """One workflow-wide tool-call ceiling shared by all reviewed MCP handlers."""

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._count = 0
        self._lock = Lock()

    def claim(self) -> None:
        with self._lock:
            if self._count >= self._limit:
                raise MCPToolBindingError("workflow tool-call limit is exhausted")
            self._count += 1


def create_read_only_mcp_tool_bindings(
    *,
    policy: WorkflowPolicy,
    binding_id: str,
    binding_control: MCPWorkflowCapabilityBindingControlPlane,
    client: MCPReadOnlyToolClient,
    surfaces: MCPSurfaceSnapshotControlPlane,
    tools: tuple[DeclaredTool, ...] | None = None,
    counter: MCPToolCallCounter | None = None,
) -> tuple[HostToolBinding, ...]:
    """Create host handlers solely from a loaded current read-only binding."""

    try:
        binding = binding_control.load(binding_id)
        expected = _policy_tool_mapping(policy)
        selected = _selected_read_only_tool_mapping(policy, tools)
        if binding.policy_digest != policy.policy_digest or (
            dict(binding.tool_id_to_remote_name) != expected
        ):
            raise MCPToolBindingError("MCP capability binding does not match policy")
        snapshot, current_tools = surfaces.verify_reconnected_client_tools(
            binding.snapshot_id, client
        )
        discovered = _tools_by_name(current_tools)
        if set(selected.values()) - set(snapshot.read_only_tool_names):
            raise MCPToolBindingError("MCP tool is not approved for read-only use")
        return tuple(
            _host_binding(
                tool_id=tool_id,
                remote_name=remote_name,
                input_schema=discovered[remote_name].input_schema,
                binding_id=binding.binding_id,
                binding_control=binding_control,
                client=client,
                surfaces=surfaces,
                counter=counter,
            )
            for tool_id, remote_name in selected.items()
        )
    except (MCPWorkflowCapabilityBindingError, MCPSurfaceSnapshotError) as error:
        raise MCPToolBindingError(str(error)) from error


def _host_binding(
    *,
    tool_id: str,
    remote_name: str,
    input_schema: Mapping[str, object],
    binding_id: str,
    binding_control: MCPWorkflowCapabilityBindingControlPlane,
    client: MCPReadOnlyToolClient,
    surfaces: MCPSurfaceSnapshotControlPlane,
    counter: MCPToolCallCounter | None,
) -> HostToolBinding:
    def handler(arguments: Mapping[str, object]) -> Mapping[str, object]:
        try:
            binding = binding_control.load(binding_id)
            surfaces.verify_reconnected_client_tools(binding.snapshot_id, client)
            if binding.tool_id_to_remote_name.get(tool_id) != remote_name:
                raise MCPToolBindingError(
                    "MCP capability binding does not match policy"
                )
            surfaces.require_read_only_tool(binding.snapshot_id, remote_name)
            if counter is not None:
                counter.claim()
            return client.call_tool(remote_name, dict(arguments))
        except MCPSurfaceSnapshotError as error:
            raise MCPToolBindingError(str(error)) from error

    return HostToolBinding(
        canonical_id=f"mcp:{binding_id}:{tool_id}",
        model_id=tool_id,
        handler=handler,
        label=tool_id,
        description="Call the workflow's reviewed read-only MCP tool.",
        input_schema=input_schema,
        side_effect="read",
        approval_required="no",
    )


def _policy_tool_mapping(policy: WorkflowPolicy) -> dict[str, str]:
    if not policy.declared_tools:
        raise MCPToolBindingError("policy does not declare read-only MCP capability")
    tool_ids = tuple(tool.tool_id for tool in policy.declared_tools)
    if tool_ids != policy.task_invocation.allowed_tool_ids:
        raise MCPToolBindingError("policy tool declaration is invalid")
    mapping = {tool.tool_id: tool.remote_tool_name for tool in policy.declared_tools}
    if len(mapping) != len(policy.declared_tools) or any(
        not key or not value for key, value in mapping.items()
    ):
        raise MCPToolBindingError("policy tool declaration is invalid")
    return mapping


def _selected_read_only_tool_mapping(
    policy: WorkflowPolicy, tools: tuple[DeclaredTool, ...] | None
) -> dict[str, str]:
    selected = policy.declared_tools if tools is None else tools
    if (
        "mcp_read_only" not in policy.required_capabilities
        or not selected
        or any(tool.side_effect != "read" for tool in selected)
    ):
        raise MCPToolBindingError("policy does not declare read-only MCP capability")
    expected = _policy_tool_mapping(policy)
    mapping = {tool.tool_id: tool.remote_tool_name for tool in selected}
    if any(
        expected.get(tool_id) != remote_name for tool_id, remote_name in mapping.items()
    ):
        raise MCPToolBindingError("policy tool declaration is invalid")
    return mapping


def _tools_by_name(
    tools: tuple[MCPDiscoveredTool, ...],
) -> dict[str, MCPDiscoveredTool]:
    result = {tool.name: tool for tool in tools}
    if len(result) != len(tools):
        raise MCPToolBindingError("MCP tool surface is invalid")
    return result
