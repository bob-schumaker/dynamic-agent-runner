"""Tests for host-owned read-only MCP tool handlers."""

from __future__ import annotations

import json
from pathlib import Path
from datetime import UTC, datetime, timedelta

import pytest


from dynamic_agent_runner import create_host_tool_registry  # noqa: E402

from dynamic_agent_runner.workflow_host.connections import MCPConnectionControlPlane  # noqa: E402
from dynamic_agent_runner.workflow_host.descriptor import (  # noqa: E402
    DeclaredTool,
    InputContract,
    TaskInvocation,
    WorkflowLimits,
)
from dynamic_agent_runner.workflow_host.mcp_binding import (  # noqa: E402
    MCPWorkflowCapabilityBindingControlPlane,
)
from dynamic_agent_runner.workflow_host.mcp_surfaces import (  # noqa: E402
    MCPDiscoveredTool,
    MCPSurfaceSnapshotControlPlane,
)
from dynamic_agent_runner.workflow_host.mcp_tools import (
    create_read_only_mcp_tool_bindings,
)  # noqa: E402
from dynamic_agent_runner.workflow_host.fastmail_triage import (  # noqa: E402
    FastmailTriageQuery,
    create_fastmail_triage_search_binding,
    default_fastmail_triage_query,
    project_fastmail_triage_result,
)
from dynamic_agent_runner.workflow_host.policy import WorkflowPolicy  # noqa: E402
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

    def reconnect(self) -> None:
        self.current_generation += 1


def test_fastmail_triage_defaults_to_bounded_unread_query_and_projection() -> None:
    now = datetime(2026, 9, 5, tzinfo=UTC)

    query = default_fastmail_triage_query(now)
    result = project_fastmail_triage_result(
        {
            "emails": [
                {
                    "id": "opaque-1",
                    "subject": "Review this",
                    "from": "sender@example.test",
                    "receivedAt": "2026-09-05T10:00:00Z",
                    "preview": "Untrusted message content",
                    "attachments": [{"name": "never-visible.pdf"}],
                }
            ]
        }
    )

    assert query.unread is True
    assert query.received_after == now - timedelta(hours=24)
    assert query.max_results == 5
    assert query.arguments == {"query": "is:unread newer_than:1d", "limit": 5}
    assert result == {
        "items": [
            {
                "message_reference": "opaque-1",
                "subject": "Review this",
                "sender": "sender@example.test",
                "received_at": "2026-09-05T10:00:00Z",
                "preview": "Untrusted message content",
            }
        ]
    }


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


def test_host_binding_allows_a_revalidated_same_identity_reconnect(
    tmp_path: Path,
) -> None:
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
    client.reconnect()

    result = registry.invoke_tool("mail_lookup", {"folder": "inbox"})

    assert result.success is True
    assert client.calls == [("list_unread", {"folder": "inbox"})]


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


def test_fastmail_triage_binding_owns_query_constraints_and_result_projection(
    tmp_path: Path,
) -> None:
    surfaces, binding_control, existing_binding, client = _setup(tmp_path)
    policy = WorkflowPolicy(
        **{
            **_policy().__dict__,
            "policy_digest": "d" * 64,
            "task_invocation": TaskInvocation(
                entrypoint="read_mail",
                max_total_tool_calls=1,
                allowed_structured_input_fields=(),
                allowed_artifact_roles=(),
                terminal_output_schema_ref="mail-v1",
                allowed_tool_ids=("search_email",),
            ),
            "declared_tools": (DeclaredTool("search_email", "list_unread"),),
        }
    )
    binding = binding_control.bind(
        policy=policy,
        snapshot_id=existing_binding.snapshot_id,
        client=client,
    )
    invocation_time = datetime(2026, 9, 5, tzinfo=UTC)

    def query_builder(now: datetime) -> FastmailTriageQuery:
        return FastmailTriageQuery(
            arguments={"host_owned": "query"},
            unread=True,
            received_after=now - timedelta(hours=24),
            max_results=5,
        )

    registry = create_host_tool_registry(
        (
            create_fastmail_triage_search_binding(
                policy=policy,
                binding_id=binding.binding_id,
                binding_control=binding_control,
                client=client,
                surfaces=surfaces,
                query_builder=query_builder,
                result_projector=lambda _result: {
                    "items": [{"message_reference": "opaque-1", "subject": "One"}]
                },
                now=lambda: invocation_time,
            ),
        )
    )

    result = registry.invoke_tool("search_email", {})

    assert result.success is True
    assert result.output == {
        "items": [{"message_reference": "opaque-1", "subject": "One"}]
    }
    assert client.calls == [("list_unread", {"host_owned": "query"})]


def test_fastmail_triage_binding_keeps_hostile_mail_content_out_of_authority(
    tmp_path: Path,
) -> None:
    surfaces, binding_control, existing_binding, client = _setup(tmp_path)
    policy = WorkflowPolicy(
        **{
            **_policy().__dict__,
            "policy_digest": "e" * 64,
            "task_invocation": TaskInvocation(
                entrypoint="read_mail",
                max_total_tool_calls=1,
                allowed_structured_input_fields=(),
                allowed_artifact_roles=(),
                terminal_output_schema_ref="mail-v1",
                allowed_tool_ids=("search_email",),
            ),
            "declared_tools": (DeclaredTool("search_email", "list_unread"),),
        }
    )
    binding = binding_control.bind(
        policy=policy,
        snapshot_id=existing_binding.snapshot_id,
        client=client,
    )
    invocation_time = datetime(2026, 9, 5, tzinfo=UTC)
    registry = create_host_tool_registry(
        (
            create_fastmail_triage_search_binding(
                policy=policy,
                binding_id=binding.binding_id,
                binding_control=binding_control,
                client=client,
                surfaces=surfaces,
                query_builder=lambda now: FastmailTriageQuery(
                    arguments={"host_owned": "query"},
                    unread=True,
                    received_after=now - timedelta(hours=24),
                    max_results=5,
                ),
                result_projector=lambda _result: json.loads(
                    (
                        Path(__file__).parent
                        / "fixtures"
                        / "fastmail-triage"
                        / "hostile-projection.json"
                    ).read_text(encoding="utf-8")
                ),
                now=lambda: invocation_time,
            ),
        )
    )

    result = registry.invoke_tool("search_email", {})
    unexpected = registry.invoke_tool("send_email", {})

    assert result.success is True
    assert unexpected.success is False
    assert client.calls == [("list_unread", {"host_owned": "query"})]
    rejected = registry.invoke_tool("search_email", {"injected": "argument"})
    exhausted = registry.invoke_tool("search_email", {})

    assert rejected.success is False
    assert "unknown input" in rejected.error
    assert exhausted.success is False
    assert "limit is exhausted" in exhausted.error
    assert client.calls == [("list_unread", {"host_owned": "query"})]
