"""Tests for non-executing MCP workflow connection readiness."""

from __future__ import annotations

import sys
from pathlib import Path


PLUGIN_SERVER_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "server"
sys.path.insert(0, str(PLUGIN_SERVER_ROOT))

from dar_workflow_server.connections import MCPConnectionControlPlane  # noqa: E402
from dar_workflow_server.descriptor import (  # noqa: E402
    DeclaredTool,
    InputContract,
    TaskInvocation,
    WorkflowLimits,
)
from dar_workflow_server.mcp_readiness import MCPWorkflowReadinessService  # noqa: E402
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
            max_total_tool_calls=1,
            allowed_structured_input_fields=(),
            allowed_artifact_roles=(),
            terminal_output_schema_ref="mail-v1",
            allowed_tool_ids=("mail_lookup",),
        ),
        limits=WorkflowLimits(8),
        required_capabilities=frozenset({"local_model", "mcp_read_only"}),
        declared_tools=(DeclaredTool("mail_lookup", "list_unread"),),
    )


def test_workflow_readiness_reports_authentication_required_without_secrets(
    tmp_path: Path,
) -> None:
    store = PrivateStateStore(tmp_path / "state")
    profiles = LocalModelProfileControlPlane(store=store)
    profile = profiles.create(
        model_id="local-model-v1",
        adapter_id="strict-local-adapter-v1",
        base_url="http://127.0.0.1:11434/v1",
        capabilities={"text_generation"},
    )
    connections = MCPConnectionControlPlane(
        store=store, profiles=profiles, secret_store=MemorySecretStore()
    )
    connection = connections.create(
        profile_id=profile.profile_id,
        endpoint="https://mcp.example.test/v1",
        scopes={"mail.read"},
        authentication_method="api_token",
    )

    result = MCPWorkflowReadinessService(connections=connections).preflight(
        policy=_policy(), connection_id=connection.connection_id
    )

    assert result.status == "authentication_required"
    assert result.connection_id == connection.connection_id
    assert "token" not in repr(result)


def test_authenticated_workflow_readiness_requires_surface_review(
    tmp_path: Path,
) -> None:
    store = PrivateStateStore(tmp_path / "state")
    profiles = LocalModelProfileControlPlane(store=store)
    profile = profiles.create(
        model_id="local-model-v1",
        adapter_id="strict-local-adapter-v1",
        base_url="http://127.0.0.1:11434/v1",
        capabilities={"text_generation"},
    )
    connections = MCPConnectionControlPlane(
        store=store, profiles=profiles, secret_store=MemorySecretStore()
    )
    connection = connections.create(
        profile_id=profile.profile_id,
        endpoint="https://mcp.example.test/v1",
        scopes={"mail.read"},
        authentication_method="api_token",
    )
    authentication = connections.configure_api_token(connection.connection_id, "token")

    result = MCPWorkflowReadinessService(connections=connections).preflight(
        policy=_policy(),
        connection_id=connection.connection_id,
        authentication_id=authentication.authentication_id,
    )

    assert result.status == "surface_review_required"
