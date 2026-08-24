"""Tests for immutable reviewed MCP tool-surface snapshots."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


PLUGIN_SERVER_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "server"
sys.path.insert(0, str(PLUGIN_SERVER_ROOT))

from dar_workflow_server.connections import MCPConnectionControlPlane  # noqa: E402
from dar_workflow_server.mcp_surfaces import (  # noqa: E402
    MCPDiscoveredTool,
    MCPSurfaceSnapshotControlPlane,
    MCPSurfaceSnapshotError,
)
from dar_workflow_server.profiles import LocalModelProfileControlPlane  # noqa: E402
from dar_workflow_server.state import PrivateStateStore  # noqa: E402


class MemorySecretStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def store(self, secret: str) -> str:
        reference = f"mcp-secret-v1-{len(self.values) + 1}"
        self.values[reference] = secret
        return reference

    def load(self, reference: str) -> str:
        return self.values[reference]

    def delete(self, reference: str) -> None:
        self.values.pop(reference, None)


def _control(
    tmp_path: Path,
) -> tuple[MCPSurfaceSnapshotControlPlane, str, str]:
    store = PrivateStateStore(tmp_path / "state")
    profiles = LocalModelProfileControlPlane(store=store)
    profile = profiles.create(
        model_id="local-model-v1",
        adapter_id="strict-local-adapter-v1",
        base_url="http://127.0.0.1:11434/v1",
        capabilities={"text_generation"},
    )
    connections = MCPConnectionControlPlane(
        store=store,
        profiles=profiles,
        secret_store=MemorySecretStore(),
    )
    connection = connections.create(
        profile_id=profile.profile_id,
        endpoint="https://mcp.example.test/v1",
        scopes={"mail.read"},
        authentication_method="api_token",
    )
    authentication = connections.configure_api_token(connection.connection_id, "token")
    return (
        MCPSurfaceSnapshotControlPlane(store=store, connections=connections),
        connection.connection_id,
        authentication.authentication_id,
    )


def _tools() -> list[MCPDiscoveredTool]:
    return [
        MCPDiscoveredTool(
            name="list_unread",
            input_schema={"type": "object", "properties": {}},
        ),
        MCPDiscoveredTool(
            name="send_email",
            input_schema={"type": "object", "properties": {"to": {"type": "string"}}},
        ),
    ]


def test_snapshot_allows_only_human_reviewed_read_only_tools(tmp_path: Path) -> None:
    control, connection_id, authentication_id = _control(tmp_path)

    snapshot = control.create(
        connection_id=connection_id,
        authentication_id=authentication_id,
        connection_generation=1,
        tools=_tools(),
        approved_read_only_tool_names={"list_unread"},
    )

    assert snapshot.connection_id == connection_id
    assert snapshot.connection_generation == 1
    assert snapshot.read_only_tool_names == frozenset({"list_unread"})
    assert (
        control.require_read_only_tool(snapshot.snapshot_id, "list_unread") == snapshot
    )
    with pytest.raises(MCPSurfaceSnapshotError, match="not approved for read-only"):
        control.require_read_only_tool(snapshot.snapshot_id, "send_email")


def test_snapshot_detects_tool_or_input_schema_drift(tmp_path: Path) -> None:
    control, connection_id, authentication_id = _control(tmp_path)
    snapshot = control.create(
        connection_id=connection_id,
        authentication_id=authentication_id,
        connection_generation=1,
        tools=_tools(),
        approved_read_only_tool_names={"list_unread"},
    )

    control.verify_current(snapshot.snapshot_id, _tools())
    changed = _tools()
    changed[0] = MCPDiscoveredTool(
        name="list_unread",
        input_schema={"type": "object", "properties": {"limit": {"type": "integer"}}},
    )

    with pytest.raises(MCPSurfaceSnapshotError, match="surface_changed"):
        control.verify_current(snapshot.snapshot_id, changed)


def test_snapshot_rejects_unknown_or_duplicate_reviewed_tools(tmp_path: Path) -> None:
    control, connection_id, authentication_id = _control(tmp_path)

    with pytest.raises(MCPSurfaceSnapshotError, match="unknown"):
        control.create(
            connection_id=connection_id,
            authentication_id=authentication_id,
            connection_generation=1,
            tools=_tools(),
            approved_read_only_tool_names={"missing"},
        )
    with pytest.raises(MCPSurfaceSnapshotError, match="unique"):
        control.create(
            connection_id=connection_id,
            authentication_id=authentication_id,
            connection_generation=1,
            tools=[_tools()[0], _tools()[0]],
            approved_read_only_tool_names={"list_unread"},
        )
