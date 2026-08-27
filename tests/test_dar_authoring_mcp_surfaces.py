"""Tests for immutable reviewed MCP tool-surface snapshots."""

from __future__ import annotations

from pathlib import Path

import pytest


from dynamic_agent_runner.workflow_host.connections import MCPConnectionControlPlane  # noqa: E402
from dynamic_agent_runner.workflow_host.mcp_surfaces import (  # noqa: E402
    MCPDiscoveredTool,
    MCPSurfaceSnapshotControlPlane,
    MCPSurfaceSnapshotError,
)
from dynamic_agent_runner.workflow_host.profiles import LocalModelProfileControlPlane  # noqa: E402
from dynamic_agent_runner.workflow_host.state import PrivateStateStore  # noqa: E402


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


class ReconnectedClient:
    def __init__(
        self,
        connection_id: str,
        authentication_id: str,
        tools: list[MCPDiscoveredTool],
        *,
        generation: int = 2,
    ) -> None:
        self.connection_id = connection_id
        self.authentication_id = authentication_id
        self.current_generation = generation
        self._tools = tuple(tools)
        self.list_tools_calls = 0

    def list_tools(self) -> tuple[MCPDiscoveredTool, ...]:
        self.list_tools_calls += 1
        return self._tools


class FakeAppleSchemaSDK:
    @staticmethod
    def generable(_description: str):
        return lambda generated_type: generated_type


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


def test_snapshot_records_a_reviewed_write_tool_without_dispatch(
    tmp_path: Path,
) -> None:
    control, connection_id, authentication_id = _control(tmp_path)

    snapshot = control.create(
        connection_id=connection_id,
        authentication_id=authentication_id,
        connection_generation=1,
        tools=_tools(),
        approved_read_only_tool_names=set(),
        approved_tool_side_effects={"send_email": "write"},
    )

    assert snapshot.tool_side_effects == {"send_email": "write"}
    assert (
        control.require_approved_tool(snapshot.snapshot_id, "send_email", "write")
        == snapshot
    )
    with pytest.raises(MCPSurfaceSnapshotError, match="not approved"):
        control.require_read_only_tool(snapshot.snapshot_id, "send_email")
    with pytest.raises(MCPSurfaceSnapshotError, match="not approved"):
        control.require_approved_tool(snapshot.snapshot_id, "send_email", "delete")


def test_snapshot_rejects_unknown_or_invalid_side_effect_class(
    tmp_path: Path,
) -> None:
    control, connection_id, authentication_id = _control(tmp_path)

    for side_effects in (
        {"missing": "write"},
        {"send_email": "anything"},
    ):
        with pytest.raises(MCPSurfaceSnapshotError, match="approved"):
            control.create(
                connection_id=connection_id,
                authentication_id=authentication_id,
                connection_generation=1,
                tools=_tools(),
                approved_read_only_tool_names=set(),
                approved_tool_side_effects=side_effects,
            )


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


@pytest.mark.parametrize(
    ("input_schema", "expected_status"),
    [
        (
            {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
            "admissible",
        ),
        (
            {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": True,
            },
            "blocked",
        ),
    ],
)
def test_snapshot_preflights_one_current_reviewed_apple_tool_without_retaining_schema(
    tmp_path: Path, input_schema: dict[str, object], expected_status: str
) -> None:
    control, connection_id, authentication_id = _control(tmp_path)
    tools = [
        MCPDiscoveredTool(
            name="search_email",
            input_schema=input_schema,
        )
    ]
    snapshot = control.create(
        connection_id=connection_id,
        authentication_id=authentication_id,
        connection_generation=1,
        tools=tools,
        approved_read_only_tool_names={"search_email"},
    )
    client = ReconnectedClient(
        connection_id,
        authentication_id,
        tools,
        generation=2,
    )

    receipt = control.preflight_apple_reviewed_tool_schema(
        snapshot.snapshot_id,
        client,
        tool_name="search_email",
        sdk=FakeAppleSchemaSDK(),
    )

    assert receipt.tool_set_digest == snapshot.tool_set_digest
    assert receipt.status == expected_status
    assert "query" not in repr(receipt)
    assert client.list_tools_calls == 1


def test_snapshot_revalidates_same_identity_reconnect_but_rejects_schema_drift(
    tmp_path: Path,
) -> None:
    control, connection_id, authentication_id = _control(tmp_path)
    snapshot = control.create(
        connection_id=connection_id,
        authentication_id=authentication_id,
        connection_generation=1,
        tools=_tools(),
        approved_read_only_tool_names={"list_unread"},
    )

    verified, tools = control.verify_reconnected_client_tools(
        snapshot.snapshot_id,
        ReconnectedClient(connection_id, authentication_id, _tools()),
    )

    assert verified == snapshot
    assert tools == tuple(_tools())
    changed = _tools()
    changed[0] = MCPDiscoveredTool("list_unread", {"type": "string"})
    with pytest.raises(MCPSurfaceSnapshotError, match="surface_changed"):
        control.verify_reconnected_client_tools(
            snapshot.snapshot_id,
            ReconnectedClient(connection_id, authentication_id, changed),
        )


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
