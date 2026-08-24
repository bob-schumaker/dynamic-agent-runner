"""Tests for host-owned, model-directed side-effecting MCP handlers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
import sys

import pytest

PLUGIN_SERVER_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "server"
sys.path.insert(0, str(PLUGIN_SERVER_ROOT))

from dynamic_agent_runner import create_host_tool_registry  # noqa: E402

from dar_workflow_server.action_ledger import WorkflowActionLedger  # noqa: E402
from dar_workflow_server.approvals import WorkflowApprovalStore  # noqa: E402
from dar_workflow_server.argument_provenance import (  # noqa: E402
    ArgumentVerificationContext,
)
from dar_workflow_server.authorized_tools import (  # noqa: E402
    LocalActionApprovalBroker,
    LocalApprovalDecision,
    create_authorized_mcp_tool_bindings,
)
from dar_workflow_server.connections import MCPConnectionControlPlane  # noqa: E402
from dar_workflow_server.descriptor import (  # noqa: E402
    ArgumentSourceRule,
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
from dar_workflow_server.policy import WorkflowPolicy  # noqa: E402
from dar_workflow_server.profiles import LocalModelProfileControlPlane  # noqa: E402
from dar_workflow_server.registration import WorkflowRegistration  # noqa: E402
from dar_workflow_server.state import PrivateStateStore  # noqa: E402


NOW = datetime(2026, 8, 24, tzinfo=UTC)


class FakeApprovalBroker:
    def __init__(self, decision: LocalApprovalDecision) -> None:
        self._decision = decision
        self.actions: list[object] = []
        self.approvals: list[object] = []

    def decide(self, *, action: object, approval: object) -> LocalApprovalDecision:
        self.actions.append(action)
        self.approvals.append(approval)
        return self._decision


class BrokenApprovalBroker:
    def decide(self, *, action: object, approval: object) -> LocalApprovalDecision:
        raise RuntimeError("terminal is unavailable")


class MemorySecretStore:
    def store(self, secret: str) -> str:
        return "secret-v1"

    def load(self, reference: str) -> str:
        return "secret"

    def delete(self, reference: str) -> None:
        return None


class CurrentClient:
    def __init__(self, connection_id: str, authentication_id: str) -> None:
        self.connection_id = connection_id
        self.authentication_id = authentication_id
        self.current_generation = 1
        self.calls: list[tuple[str, dict[str, object]]] = []
        self._tools = (
            MCPDiscoveredTool(
                name="send_email",
                input_schema={
                    "type": "object",
                    "properties": {
                        "recipient": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["recipient", "body"],
                    "additionalProperties": False,
                },
            ),
        )

    def list_tools(self) -> tuple[MCPDiscoveredTool, ...]:
        return self._tools

    def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        self.calls.append((name, arguments))
        return {"sent": True}


def _policy() -> WorkflowPolicy:
    return WorkflowPolicy(
        package_id="mail-sender",
        revision_digest="a" * 64,
        descriptor_digest="b" * 64,
        policy_digest="c" * 64,
        model_profile_requirement="local-general-model",
        input_contract=InputContract("hybrid", 8192, "original_prompt"),
        task_invocation=TaskInvocation(
            entrypoint="send_mail",
            max_total_tool_calls=1,
            allowed_structured_input_fields=(),
            allowed_artifact_roles=(),
            terminal_output_schema_ref="mail-v1",
            allowed_tool_ids=("send_mail",),
            argument_sources={
                "send_mail": {
                    "recipient": ArgumentSourceRule(
                        ("cited_original_prompt_span",), True
                    ),
                    "body": ArgumentSourceRule(("package_constant:body",), False),
                }
            },
        ),
        limits=WorkflowLimits(8),
        required_capabilities=frozenset({"local_model", "mcp_side_effects"}),
        declared_tools=(
            DeclaredTool(
                "send_mail", "send_email", side_effect="write", approval_required=True
            ),
        ),
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
        store=store, profiles=profiles, secret_store=MemorySecretStore()
    )
    connection = connections.create(
        profile_id=profile.profile_id,
        endpoint="https://mcp.example.test/v1",
        scopes={"mail.send"},
        authentication_method="api_token",
    )
    authentication = connections.configure_api_token(connection.connection_id, "token")
    client = CurrentClient(connection.connection_id, authentication.authentication_id)
    surfaces = MCPSurfaceSnapshotControlPlane(store=store, connections=connections)
    snapshot = surfaces.create(
        connection_id=connection.connection_id,
        authentication_id=authentication.authentication_id,
        connection_generation=1,
        tools=client.list_tools(),
        approved_read_only_tool_names=(),
        approved_tool_side_effects={"send_email": "write"},
    )
    bindings = MCPWorkflowCapabilityBindingControlPlane(store=store, surfaces=surfaces)
    binding = bindings.bind(
        policy=_policy(), snapshot_id=snapshot.snapshot_id, client=client
    )
    registration = WorkflowRegistration(
        workflow_id="mail-sender",
        registration_digest="d" * 64,
        package_id="mail-sender",
        revision_digest="a" * 64,
        policy_digest="c" * 64,
        profile_id=profile.profile_id,
        model_id="local-model-v1",
        mcp_binding_id=binding.binding_id,
    )
    return store, surfaces, bindings, binding, registration, client


def _envelope() -> str:
    return json.dumps(
        {
            "format_version": 1,
            "arguments": {"recipient": "ada@example.test", "body": "Welcome!"},
            "sources": {
                "recipient": {
                    "kind": "prompt_span",
                    "start_byte": 0,
                    "end_byte": 16,
                    "normalization": "identity",
                },
                "body": {"kind": "constant", "ref": "body"},
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _registry(
    tmp_path: Path,
    *,
    approval_broker: LocalActionApprovalBroker | None = None,
):
    store, surfaces, bindings, binding, registration, client = _setup(tmp_path)
    tools = create_authorized_mcp_tool_bindings(
        policy=_policy(),
        registration=registration,
        binding_id=binding.binding_id,
        binding_control=bindings,
        client=client,
        surfaces=surfaces,
        provenance=ArgumentVerificationContext(
            original_prompt="ada@example.test",
            sealed_fields={},
            artifact_values={},
            constants={"body": "Welcome!", "other_body": "Welcome!"},
            argument_policies={},
        ),
        workspace_artifact_hashes={},
        trace_correlation="run-1",
        ledger=WorkflowActionLedger(store=store, owner="local-os-user-v1:501:ada"),
        approval_store=(
            WorkflowApprovalStore(store=store, owner="local-os-user-v1:501:ada")
            if approval_broker is not None
            else None
        ),
        approval_broker=approval_broker,
        now=NOW,
    )
    return create_host_tool_registry(tools), client, tmp_path / "state" / "records.json"


def test_authorized_binding_verifies_provenance_then_dispatches_once(
    tmp_path: Path,
) -> None:
    registry, client, state_path = _registry(tmp_path)

    result = registry.invoke_tool("send_mail", {"provenance_envelope": _envelope()})

    assert result.success is True
    assert result.output == {"sent": True}
    assert client.calls == [
        ("send_email", {"recipient": "ada@example.test", "body": "Welcome!"})
    ]
    state = state_path.read_text(encoding="utf-8")
    assert "ada@example.test" not in state
    assert "Welcome!" not in state


def test_authorized_binding_rejects_invalid_provenance_before_dispatch(
    tmp_path: Path,
) -> None:
    registry, client, _ = _registry(tmp_path)

    result = registry.invoke_tool("send_mail", {"provenance_envelope": "{}"})

    assert result.success is False
    assert client.calls == []


def test_authorized_binding_rejects_an_undeclared_constant_reference(
    tmp_path: Path,
) -> None:
    registry, client, _ = _registry(tmp_path)
    envelope = json.loads(_envelope())
    envelope["sources"]["body"]["ref"] = "other_body"

    result = registry.invoke_tool(
        "send_mail",
        {
            "provenance_envelope": json.dumps(
                envelope, sort_keys=True, separators=(",", ":")
            )
        },
    )

    assert result.success is False
    assert client.calls == []


def test_authorized_binding_rejects_a_second_call_over_its_budget(
    tmp_path: Path,
) -> None:
    registry, client, _ = _registry(tmp_path)

    registry.invoke_tool("send_mail", {"provenance_envelope": _envelope()})
    result = registry.invoke_tool("send_mail", {"provenance_envelope": _envelope()})

    assert result.success is False
    assert client.calls == [
        ("send_email", {"recipient": "ada@example.test", "body": "Welcome!"})
    ]


def test_authorized_binding_allows_a_revalidated_same_identity_reconnect(
    tmp_path: Path,
) -> None:
    registry, client, _ = _registry(tmp_path)
    client.current_generation = 2

    result = registry.invoke_tool("send_mail", {"provenance_envelope": _envelope()})

    assert result.success is True
    assert client.calls == [
        ("send_email", {"recipient": "ada@example.test", "body": "Welcome!"})
    ]


def test_authorized_binding_dispatches_only_after_local_approval(
    tmp_path: Path,
) -> None:
    broker = FakeApprovalBroker(LocalApprovalDecision.APPROVED)
    registry, client, _ = _registry(tmp_path, approval_broker=broker)

    result = registry.invoke_tool("send_mail", {"provenance_envelope": _envelope()})

    assert result.success is True
    assert len(broker.actions) == 1
    assert len(broker.approvals) == 1
    assert client.calls == [
        ("send_email", {"recipient": "ada@example.test", "body": "Welcome!"})
    ]


@pytest.mark.parametrize(
    ("decision", "terminal_status"),
    [
        (LocalApprovalDecision.DENIED, "denied"),
        (LocalApprovalDecision.CANCELLED, "cancelled"),
    ],
)
def test_authorized_binding_does_not_dispatch_a_rejected_local_approval(
    tmp_path: Path,
    decision: LocalApprovalDecision,
    terminal_status: str,
) -> None:
    broker = FakeApprovalBroker(decision)
    registry, client, state_path = _registry(tmp_path, approval_broker=broker)

    result = registry.invoke_tool("send_mail", {"provenance_envelope": _envelope()})

    assert result.success is False
    assert len(broker.actions) == 1
    assert client.calls == []
    assert f'"status":"{terminal_status}"' in state_path.read_text(encoding="utf-8")


def test_authorized_binding_fails_closed_when_local_approval_fails(
    tmp_path: Path,
) -> None:
    registry, client, state_path = _registry(
        tmp_path,
        approval_broker=BrokenApprovalBroker(),
    )

    result = registry.invoke_tool("send_mail", {"provenance_envelope": _envelope()})

    assert result.success is False
    assert client.calls == []
    assert '"status":"failed"' in state_path.read_text(encoding="utf-8")
