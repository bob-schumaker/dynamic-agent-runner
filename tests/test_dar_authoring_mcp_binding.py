"""Tests for profile-owned read-only MCP workflow capability bindings."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


PLUGIN_SERVER_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "server"
sys.path.insert(0, str(PLUGIN_SERVER_ROOT))

from dar_workflow_server.connections import MCPConnectionControlPlane  # noqa: E402
from dar_workflow_server.descriptor import (  # noqa: E402
    DeclaredTool,
    InputContract,
    TaskInvocation,
    WorkflowLimits,
)
from dar_workflow_server.mcp_binding import (  # noqa: E402
    MCPWorkflowCapabilityBindingControlPlane,
    MCPWorkflowCapabilityBindingError,
)
from dar_workflow_server.mcp_surfaces import (  # noqa: E402
    MCPDiscoveredTool,
    MCPSurfaceSnapshotControlPlane,
)
from dar_workflow_server.policy import WorkflowPolicy  # noqa: E402
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


class CurrentClient:
    def __init__(
        self,
        connection_id: str,
        authentication_id: str,
        tools: tuple[MCPDiscoveredTool, ...],
    ) -> None:
        self.connection_id = connection_id
        self.authentication_id = authentication_id
        self.current_generation = 1
        self._tools = tools

    def list_tools(self) -> tuple[MCPDiscoveredTool, ...]:
        return self._tools


def _setup(tmp_path: Path):
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
    tools = (
        MCPDiscoveredTool(
            name="list_unread", input_schema={"type": "object", "properties": {}}
        ),
        MCPDiscoveredTool(
            name="send_email", input_schema={"type": "object", "properties": {}}
        ),
    )
    surfaces = MCPSurfaceSnapshotControlPlane(store=store, connections=connections)
    snapshot = surfaces.create(
        connection_id=connection.connection_id,
        authentication_id=authentication.authentication_id,
        connection_generation=1,
        tools=tools,
        approved_read_only_tool_names={"list_unread"},
    )
    return (
        store,
        surfaces,
        snapshot,
        CurrentClient(
            connection.connection_id, authentication.authentication_id, tools
        ),
    )


def _policy(*, remote_tool_name: str = "list_unread") -> WorkflowPolicy:
    return WorkflowPolicy(
        package_id="mail-reader",
        revision_digest="a" * 64,
        descriptor_digest="b" * 64,
        policy_digest="c" * 64,
        model_profile_requirement="local-general-model",
        input_contract=InputContract("hybrid", 8192, "original_prompt"),
        task_invocation=TaskInvocation(
            entrypoint="read_mail",
            max_total_tool_calls=3,
            allowed_structured_input_fields=(),
            allowed_artifact_roles=(),
            terminal_output_schema_ref="mail-v1",
            allowed_tool_ids=("mail_tool",),
        ),
        limits=WorkflowLimits(8),
        required_capabilities=frozenset({"local_model", "mcp_read_only"}),
        declared_tools=(DeclaredTool("mail_tool", remote_tool_name),),
    )


def test_binding_requires_current_approved_read_only_surface(tmp_path: Path) -> None:
    store, surfaces, snapshot, client = _setup(tmp_path)
    binding = MCPWorkflowCapabilityBindingControlPlane(
        store=store, surfaces=surfaces
    ).bind(policy=_policy(), snapshot_id=snapshot.snapshot_id, client=client)

    assert binding.policy_digest == "c" * 64
    assert binding.snapshot_id == snapshot.snapshot_id
    assert binding.connection_generation == 1
    assert binding.tool_id_to_remote_name == {"mail_tool": "list_unread"}


def test_binding_rejects_send_like_or_drifted_surface(tmp_path: Path) -> None:
    store, surfaces, snapshot, client = _setup(tmp_path)
    control = MCPWorkflowCapabilityBindingControlPlane(store=store, surfaces=surfaces)

    with pytest.raises(MCPWorkflowCapabilityBindingError, match="not approved"):
        control.bind(
            policy=_policy(remote_tool_name="send_email"),
            snapshot_id=snapshot.snapshot_id,
            client=client,
        )
    client.current_generation = 2
    with pytest.raises(MCPWorkflowCapabilityBindingError, match="surface_changed"):
        control.bind(policy=_policy(), snapshot_id=snapshot.snapshot_id, client=client)
