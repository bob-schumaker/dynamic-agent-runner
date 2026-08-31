"""Non-executing workflow readiness for a configured generic MCP connection."""

from __future__ import annotations

from dataclasses import dataclass

from dynamic_agent_runner.workflow_host.connections import (
    MCPConnectionControlPlane,
    MCPConnectionError,
)
from dynamic_agent_runner.workflow_host.policy import WorkflowPolicy


class MCPWorkflowReadinessError(ValueError):
    """Raised when MCP readiness cannot be determined without execution."""


@dataclass(frozen=True)
class MCPWorkflowReadiness:
    """A closed, non-secret workflow connection readiness result."""

    connection_id: str
    status: str


class MCPWorkflowReadinessService:
    """Report whether a tool-bearing policy can proceed to human surface review."""

    def __init__(self, *, connections: MCPConnectionControlPlane) -> None:
        self._connections = connections

    def preflight(
        self,
        *,
        policy: WorkflowPolicy,
        connection_id: str,
        authentication_id: str | None = None,
    ) -> MCPWorkflowReadiness:
        """Report authentication or review readiness without a live MCP session."""

        if (
            not policy.declared_tools
            or "mcp_read_only" not in policy.required_capabilities
        ):
            raise MCPWorkflowReadinessError("policy does not require read-only MCP")
        try:
            connection = self._connections.preflight(
                connection_id, authentication_id=authentication_id
            )
        except MCPConnectionError as error:
            raise MCPWorkflowReadinessError("MCP connection is unavailable") from error
        if connection.status == "authentication_required":
            return MCPWorkflowReadiness(
                connection_id=connection.connection_id,
                status="authentication_required",
            )
        if connection.status != "authenticated":
            raise MCPWorkflowReadinessError("MCP connection readiness is invalid")
        return MCPWorkflowReadiness(
            connection_id=connection.connection_id,
            status="surface_review_required",
        )
