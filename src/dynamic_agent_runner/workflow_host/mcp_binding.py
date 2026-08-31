"""Host-owned bindings from declared MCP capability to reviewed client surface."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Mapping

from dynamic_agent_runner.workflow_host.mcp_surfaces import (
    CurrentMCPSurfaceClient,
    MCPSurfaceSnapshotControlPlane,
    MCPSurfaceSnapshotError,
)
from dynamic_agent_runner.workflow_host.policy import WorkflowPolicy
from dynamic_agent_runner.workflow_host.profiles import InstallationIdentityProvider
from dynamic_agent_runner.workflow_host.state import (
    OpaqueRecordError,
    PrivateStateStore,
)


class MCPWorkflowCapabilityBindingError(ValueError):
    """Raised when a workflow cannot bind to a reviewed MCP surface."""


@dataclass(frozen=True)
class MCPWorkflowCapabilityBinding:
    """An opaque, immutable binding with no executable remote tool handler."""

    binding_id: str
    policy_digest: str
    snapshot_id: str
    connection_id: str
    authentication_id: str
    connection_generation: int
    tool_id_to_remote_name: Mapping[str, str]


class MCPWorkflowCapabilityBindingControlPlane:
    """Bind one policy only to its reviewed authenticated MCP client generation."""

    def __init__(
        self, *, store: PrivateStateStore, surfaces: MCPSurfaceSnapshotControlPlane
    ) -> None:
        self._store = store
        self._surfaces = surfaces
        self._identity = InstallationIdentityProvider()

    def bind(
        self,
        *,
        policy: WorkflowPolicy,
        snapshot_id: str,
        client: CurrentMCPSurfaceClient,
    ) -> MCPWorkflowCapabilityBinding:
        """Persist one human-reviewed binding for a compiled policy."""

        mapping = _declared_tool_mapping(policy)
        try:
            snapshot = self._surfaces.verify_current_client(snapshot_id, client)
            for tool in policy.declared_tools:
                self._surfaces.require_approved_tool(
                    snapshot_id, tool.remote_tool_name, tool.side_effect
                )
            binding_id = self._store.issue(
                kind="mcp_workflow_capability_binding",
                owner=self._identity.principal,
                payload={
                    "policy_digest": policy.policy_digest,
                    "snapshot_id": snapshot.snapshot_id,
                    "connection_id": snapshot.connection_id,
                    "authentication_id": snapshot.authentication_id,
                    "connection_generation": snapshot.connection_generation,
                    "tool_id_to_remote_name": mapping,
                },
                expires_at=datetime.max.replace(tzinfo=UTC),
                now=datetime.now(UTC),
            )
        except MCPSurfaceSnapshotError as error:
            raise MCPWorkflowCapabilityBindingError(str(error)) from error
        except OpaqueRecordError as error:
            raise MCPWorkflowCapabilityBindingError(
                "MCP capability binding is unavailable"
            ) from error
        return MCPWorkflowCapabilityBinding(
            binding_id=binding_id,
            policy_digest=policy.policy_digest,
            snapshot_id=snapshot.snapshot_id,
            connection_id=snapshot.connection_id,
            authentication_id=snapshot.authentication_id,
            connection_generation=snapshot.connection_generation,
            tool_id_to_remote_name=MappingProxyType(mapping),
        )

    def load(self, binding_id: str) -> MCPWorkflowCapabilityBinding:
        """Load one immutable capability binding owned by this installation."""

        try:
            payload = self._store.load(
                binding_id,
                expected_kind="mcp_workflow_capability_binding",
                owner=self._identity.principal,
                now=datetime.now(UTC),
            ).payload
            binding = MCPWorkflowCapabilityBinding(
                binding_id=binding_id,
                policy_digest=_digest(payload["policy_digest"]),
                snapshot_id=_opaque_id(payload["snapshot_id"], "snapshot_id"),
                connection_id=_opaque_id(payload["connection_id"], "connection_id"),
                authentication_id=_opaque_id(
                    payload["authentication_id"], "authentication_id"
                ),
                connection_generation=_positive_generation(
                    payload["connection_generation"]
                ),
                tool_id_to_remote_name=MappingProxyType(
                    _tool_mapping(payload["tool_id_to_remote_name"])
                ),
            )
        except (OpaqueRecordError, KeyError, TypeError, ValueError) as error:
            raise MCPWorkflowCapabilityBindingError(
                "MCP capability binding is unavailable"
            ) from error
        return binding


def _declared_tool_mapping(policy: WorkflowPolicy) -> dict[str, str]:
    if not policy.declared_tools:
        raise MCPWorkflowCapabilityBindingError(
            "policy does not declare an MCP capability"
        )
    required_capability = (
        "mcp_side_effects"
        if any(tool.side_effect != "read" for tool in policy.declared_tools)
        else "mcp_read_only"
    )
    if required_capability not in policy.required_capabilities:
        raise MCPWorkflowCapabilityBindingError("policy MCP capability is invalid")
    tool_ids = tuple(tool.tool_id for tool in policy.declared_tools)
    if tool_ids != policy.task_invocation.allowed_tool_ids:
        raise MCPWorkflowCapabilityBindingError("policy tool declaration is invalid")
    return _tool_mapping(
        {tool.tool_id: tool.remote_tool_name for tool in policy.declared_tools}
    )


def _tool_mapping(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping) or not value:
        raise MCPWorkflowCapabilityBindingError("policy tool declaration is invalid")
    result: dict[str, str] = {}
    for tool_id, remote_name in value.items():
        if (
            not isinstance(tool_id, str)
            or not tool_id
            or not isinstance(remote_name, str)
            or not remote_name
        ):
            raise MCPWorkflowCapabilityBindingError(
                "policy tool declaration is invalid"
            )
        result[tool_id] = remote_name
    return result


def _opaque_id(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.startswith("v1."):
        raise MCPWorkflowCapabilityBindingError(f"{name} must be an opaque identifier")
    return value


def _positive_generation(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise MCPWorkflowCapabilityBindingError("connection generation is invalid")
    return value


def _digest(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise MCPWorkflowCapabilityBindingError("policy digest is invalid")
    return value
