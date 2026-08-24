"""Tests for host-owned read-only MCP tool handlers."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


PLUGIN_SERVER_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "server"
sys.path.insert(0, str(PLUGIN_SERVER_ROOT))

from dynamic_agent_runner import create_host_tool_registry  # noqa: E402

from dar_workflow_server.connections import MCPConnectionControlPlane  # noqa: E402
from dar_workflow_server.descriptor import (  # noqa: E402
    DeclaredTool,
    InputContract,
    TaskInvocation,
    WorkflowLimits,
)
from dar_workflow_server.mcp_binding import (  # noqa: E402
    MCPWorkflowCapabilityBindingControlPlane,
)
from dar_workflow_server.mcp_surfaces import (  # noqa: E402
    MCPDiscoveredTool,
    MCPSurfaceSnapshotControlPlane,
)
from dar_workflow_server.mcp_tools import create_read_only_mcp_tool_bindings  # noqa: E402
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
        self.calls: list[tuple[str, dict[str, object]]] = []

    def list_tools(self) -> tuple[MCPDiscoveredTool, ...]:
        return self._tools

    def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        self.calls.append((name, arguments))
        return {"content": [{"type": "text", "text": "three unread messages"}]}


def _policy() -> WorkflowPolicy:
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
            allowed_tool_ids=("mail_lookup",),
        ),
        limits=WorkflowLimits(8),
        required_capabilities=frozenset({"local_model", "mcp_read_only"}),
        declared_tools=(DeclaredTool("mail_lookup", "list_unread"),),
    )


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
            name="list_unread",
            input_schema={
                "type": "object",
                "properties": {"folder": {"type": "string"}},
                "required": ["folder"],
                "additionalProperties": False,
            },
        ),
        MCPDiscoveredTool(
            name="send_email",
            input_schema={"type": "object", "properties": {}},
        ),
    )
    client = CurrentClient(
        connection.connection_id, authentication.authentication_id, tools
    )
    surfaces = MCPSurfaceSnapshotControlPlane(store=store, connections=connections)
    snapshot = surfaces.create(
        connection_id=connection.connection_id,
        authentication_id=authentication.authentication_id,
        connection_generation=1,
        tools=tools,
        approved_read_only_tool_names={"list_unread"},
    )
    binding_control = MCPWorkflowCapabilityBindingControlPlane(
        store=store, surfaces=surfaces
    )
    binding = binding_control.bind(
        policy=_policy(), snapshot_id=snapshot.snapshot_id, client=client
    )
    return surfaces, binding_control, binding, client


def test_host_binding_dispatches_only_the_current_reviewed_read_only_tool(
    tmp_path: Path,
) -> None:
    surfaces, binding_control, binding, client = _setup(tmp_path)

    bindings = create_read_only_mcp_tool_bindings(
        policy=_policy(),
        binding_id=binding.binding_id,
        binding_control=binding_control,
        client=client,
        surfaces=surfaces,
    )
    registry = create_host_tool_registry(bindings)
    result = registry.invoke_tool("mail_lookup", {"folder": "inbox"})

    assert len(bindings) == 1
    assert bindings[0].model_id == "mail_lookup"
    assert bindings[0].side_effect == "read"
    assert result.success is True
    assert result.output == {
        "content": [{"type": "text", "text": "three unread messages"}]
    }
    assert client.calls == [("list_unread", {"folder": "inbox"})]


def test_host_binding_rejects_drift_before_remote_tool_dispatch(tmp_path: Path) -> None:
    surfaces, binding_control, binding, client = _setup(tmp_path)
    registry = create_host_tool_registry(
        create_read_only_mcp_tool_bindings(
            policy=_policy(),
            binding_id=binding.binding_id,
            binding_control=binding_control,
            client=client,
            surfaces=surfaces,
        )
    )
    client.current_generation = 2

    result = registry.invoke_tool("mail_lookup", {"folder": "inbox"})

    assert result.success is False
    assert "surface_changed" in (result.error or "")
    assert client.calls == []


def test_host_binding_never_constructs_an_unapproved_send_like_handler(
    tmp_path: Path,
) -> None:
    surfaces, binding_control, binding, client = _setup(tmp_path)
    policy = _policy()
    forged_policy = WorkflowPolicy(
        **{
            **policy.__dict__,
            "declared_tools": (DeclaredTool("mail_lookup", "send_email"),),
        }
    )

    with pytest.raises(ValueError, match="does not match"):
        create_read_only_mcp_tool_bindings(
            policy=forged_policy,
            binding_id=binding.binding_id,
            binding_control=binding_control,
            client=client,
            surfaces=surfaces,
        )

    assert client.calls == []
