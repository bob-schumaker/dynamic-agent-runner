"""Tests for DAR authoring's closed no-tool workflow runner."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml


from dynamic_agent_runner.openai_client import (  # noqa: E402
    ModelToolCall,
    ModelResponse,
    OpenAIClientAdapter,
)

from dynamic_agent_runner.workflow_host.catalog import PackageCatalog  # noqa: E402
from dynamic_agent_runner.workflow_host.action_ledger import WorkflowActionLedger  # noqa: E402
from dynamic_agent_runner.workflow_host.approvals import WorkflowApprovalStore  # noqa: E402
from dynamic_agent_runner.workflow_host.authorized_tools import (  # noqa: E402
    LocalActionApprovalBroker,
    LocalApprovalDecision,
)
from dynamic_agent_runner.workflow_host.connections import MCPConnectionControlPlane  # noqa: E402
from dynamic_agent_runner.workflow_host.mcp_binding import (  # noqa: E402
    MCPWorkflowCapabilityBindingControlPlane,
)
from dynamic_agent_runner.workflow_host.mcp_surfaces import (  # noqa: E402
    MCPDiscoveredTool,
    MCPSurfaceSnapshotControlPlane,
)
from dynamic_agent_runner.workflow_host.package_sources import (
    PackageSourceSelectionPolicy,
)  # noqa: E402
from dynamic_agent_runner.workflow_host.policy import (
    compile_workflow_policy,
    resolve_capabilities,
)  # noqa: E402
from dynamic_agent_runner.workflow_host.preparation import (
    WorkflowInvocationPreparationService,
)  # noqa: E402
from dynamic_agent_runner.workflow_host.profiles import LocalModelProfileControlPlane  # noqa: E402
from dynamic_agent_runner.workflow_host.registration import WorkflowRegistrationService  # noqa: E402
from dynamic_agent_runner.workflow_host.runner import (  # noqa: E402
    RunDarWorkflowError,
    RunDarWorkflowRequest,
    WorkflowRunner,
)
from dynamic_agent_runner.workflow_host.staging import PrivatePackageStager  # noqa: E402
from dynamic_agent_runner.workflow_host.state import PrivateStateStore  # noqa: E402
from dynamic_agent_runner.workflow_host.workspace_ingress import (  # noqa: E402
    MaterializedWorkspaceInputArtifact,
)


NOW = datetime(2026, 8, 23, tzinfo=UTC)
TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "templates"


class FakeResponses:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> ModelResponse:
        self.calls.append(kwargs)
        return ModelResponse(content=self.content)


class FakeClient:
    def __init__(self, content: str) -> None:
        self.responses = FakeResponses(content)


class ArtifactVerifier:
    def load(
        self,
        artifact_id: str,
        *,
        workflow_id: str,
        registration_digest: str,
        now: datetime,
    ) -> object:
        if (
            artifact_id != "v1.workspace-artifact"
            or workflow_id != "document-helper"
            or not registration_digest
        ):
            raise ValueError("unexpected artifact")
        return object()


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


class FakeMCPClient:
    def __init__(self, connection_id: str, authentication_id: str) -> None:
        self.connection_id = connection_id
        self.authentication_id = authentication_id
        self.current_generation = 1
        self.calls: list[tuple[str, dict[str, object]]] = []
        self._tools = (
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

    def list_tools(self) -> tuple[MCPDiscoveredTool, ...]:
        return self._tools

    def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        self.calls.append((name, arguments))
        return {"content": [{"type": "text", "text": "three unread messages"}]}


class QueuedResponses:
    def __init__(self, responses: list[ModelResponse]) -> None:
        self._responses = iter(responses)
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> ModelResponse:
        self.calls.append(kwargs)
        return next(self._responses)


class QueuedClient:
    def __init__(self, responses: list[ModelResponse]) -> None:
        self.responses = QueuedResponses(responses)


class FakeApprovalBroker:
    def __init__(self, decision: LocalApprovalDecision) -> None:
        self.decision = decision
        self.actions: list[object] = []

    def decide(self, *, action: object, approval: object) -> LocalApprovalDecision:
        self.actions.append(action)
        return self.decision


class BodyArtifactVerifier:
    def load(
        self,
        artifact_id: str,
        *,
        workflow_id: str,
        registration_digest: str,
        now: datetime,
    ) -> object:
        if artifact_id != "v1.body" or workflow_id != "mail-reader":
            raise ValueError("unexpected artifact")
        return object()

    def materialize(
        self,
        artifact_id: str,
        *,
        workflow_id: str,
        registration_digest: str,
        now: datetime,
    ) -> MaterializedWorkspaceInputArtifact:
        self.load(
            artifact_id,
            workflow_id=workflow_id,
            registration_digest=registration_digest,
            now=now,
        )
        return MaterializedWorkspaceInputArtifact(
            "v1.body", "sha256:" + "b" * 64, "body", "Body from artifact"
        )


def _runner(
    tmp_path: Path,
    *,
    local: bool = True,
    terminal_required_field: str = "message",
    artifact_verifier: object | None = None,
):
    source = tmp_path / "packages" / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
    runtime_path = source / "agent-runtime.yaml"
    runtime = yaml.safe_load(runtime_path.read_text(encoding="utf-8"))
    runtime["output_contracts"][0]["required_fields"] = [terminal_required_field]
    runtime_path.write_text(yaml.safe_dump(runtime), encoding="utf-8")
    store = PrivateStateStore(tmp_path / "state")
    source_handle = PackageSourceSelectionPolicy(
        allowed_root=source.parent, store=store
    ).select_directory(source, now=NOW)
    catalog = PackageCatalog(tmp_path / "catalog")
    revision = catalog.import_staged(
        PrivatePackageStager(store=store, private_root=tmp_path / "staging").stage(
            source_handle, now=NOW
        )
    )
    policy = compile_workflow_policy(revision)
    profiles = LocalModelProfileControlPlane(store=store)
    profile = profiles.create(
        model_id="local-model-v1",
        adapter_id="strict-local-adapter-v1",
        base_url="http://127.0.0.1:11434/v1",
        capabilities={"text_generation"},
    )
    registrations = WorkflowRegistrationService(
        profiles=profiles,
        configured_profile_id=profile.profile_id,
        root=tmp_path / "registrations",
    )
    registration = registrations.register(
        workflow_id="document-helper",
        policy=policy,
        capability_resolution=resolve_capabilities(
            policy, available_capabilities={"local_model"}
        ),
    )
    preparation = WorkflowInvocationPreparationService(
        registrations=registrations,
        catalog=catalog,
        store=store,
        artifact_verifier=artifact_verifier,  # type: ignore[arg-type]
    )
    client = FakeClient("completed locally")
    adapter = OpenAIClientAdapter(
        client,
        models=["local-model", "local-model-v1"],
        is_local=local,
    )
    return (
        WorkflowRunner(
            registrations=registrations,
            catalog=catalog,
            preparation=preparation,
            model_adapter=adapter,
        ),
        preparation,
        registration,
        revision,
        client,
    )


def _tool_runner(
    tmp_path: Path,
    *,
    side_effect: bool = False,
    approval_broker: LocalActionApprovalBroker | None = None,
    body_from_artifact: bool = False,
    artifact_verifier: object | None = None,
):
    source = tmp_path / "packages" / "mail-reader"
    shutil.copytree(TEMPLATE_ROOT, source)
    descriptor_path = source / "workflow-descriptor.yaml"
    descriptor = yaml.safe_load(descriptor_path.read_text(encoding="utf-8"))
    descriptor["package_id"] = "mail-reader"
    remote_tool_name = "send_email" if side_effect else "list_unread"
    tool_id = "mail_send" if side_effect else "mail_lookup"
    descriptor["tools"] = [
        {
            "id": tool_id,
            "kind": "mcp",
            "remote_tool_name": remote_tool_name,
            "side_effect": "write" if side_effect else "read",
            **({"approval_required": True} if side_effect else {}),
        }
    ]
    descriptor["task_invocation"].update(
        {
            "allowed_tool_ids": [tool_id],
            "max_total_tool_calls": 1,
            **(
                {
                    "argument_sources": {
                        tool_id: {
                            "recipient": {
                                "sources": ["cited_original_prompt_span"],
                                "authority": True,
                            },
                            "body": {
                                "sources": (
                                    ["artifact_role:body"]
                                    if body_from_artifact
                                    else ["cited_original_prompt_span"]
                                ),
                                "authority": False,
                            },
                        }
                    }
                }
                if side_effect
                else {}
            ),
        }
    )
    if body_from_artifact:
        descriptor["task_invocation"]["allowed_artifact_roles"] = ["body"]
    descriptor_path.write_text(yaml.safe_dump(descriptor), encoding="utf-8")
    runtime_path = source / "agent-runtime.yaml"
    runtime = yaml.safe_load(runtime_path.read_text(encoding="utf-8"))
    runtime["package_id"] = "mail-reader"
    runtime["runtime"]["execution_policy"]["tool_use_completion"] = {
        "run_again": "required",
        "stop_on_tool": "disabled",
        "final_output": "default",
    }
    runtime["tools"] = [
        {
            "id": tool_id,
            "label": "List unread mail",
            "tool_type": "external_api",
            "description_for_llm": "List unread mail.",
            "adapter": "host.mcp",
            "input_schema": (
                {
                    "type": "object",
                    "properties": {
                        "recipient": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["recipient", "body"],
                    "additionalProperties": False,
                }
                if side_effect
                else {
                    "type": "object",
                    "properties": {"folder": {"type": "string"}},
                    "required": ["folder"],
                    "additionalProperties": False,
                }
            ),
            "side_effect": "write" if side_effect else "read",
            "approval_required": side_effect,
            "timeout": "runtime_default",
            "retry_policy": "none",
            "failure_behavior": "error",
        }
    ]
    runtime["nodes"][0]["available_tools"] = [tool_id]
    runtime_path.write_text(yaml.safe_dump(runtime), encoding="utf-8")
    store = PrivateStateStore(tmp_path / "state")
    source_handle = PackageSourceSelectionPolicy(
        allowed_root=source.parent, store=store
    ).select_directory(source, now=NOW)
    catalog = PackageCatalog(tmp_path / "catalog")
    revision = catalog.import_staged(
        PrivatePackageStager(store=store, private_root=tmp_path / "staging").stage(
            source_handle, now=NOW
        )
    )
    policy = compile_workflow_policy(revision)
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
    mcp_client = FakeMCPClient(
        connection.connection_id, authentication.authentication_id
    )
    if side_effect:
        mcp_client._tools = (
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
    surfaces = MCPSurfaceSnapshotControlPlane(store=store, connections=connections)
    snapshot = surfaces.create(
        connection_id=connection.connection_id,
        authentication_id=authentication.authentication_id,
        connection_generation=1,
        tools=mcp_client.list_tools(),
        approved_read_only_tool_names={"list_unread"} if not side_effect else (),
        approved_tool_side_effects={"send_email": "write"} if side_effect else None,
    )
    mcp_bindings = MCPWorkflowCapabilityBindingControlPlane(
        store=store, surfaces=surfaces
    )
    mcp_binding = mcp_bindings.bind(
        policy=policy, snapshot_id=snapshot.snapshot_id, client=mcp_client
    )
    registrations = WorkflowRegistrationService(
        profiles=profiles,
        configured_profile_id=profile.profile_id,
        root=tmp_path / "registrations",
        mcp_bindings=mcp_bindings,
        mcp_client=mcp_client,
        mcp_surfaces=surfaces,
    )
    registrations.register(
        workflow_id="mail-reader",
        policy=policy,
        capability_resolution=resolve_capabilities(
            policy,
            available_capabilities=(
                {"local_model", "mcp_side_effects"}
                if side_effect
                else {"local_model", "mcp_read_only"}
            ),
        ),
        mcp_binding_id=mcp_binding.binding_id,
    )
    preparation = WorkflowInvocationPreparationService(
        registrations=registrations,
        catalog=catalog,
        store=store,
        artifact_verifier=artifact_verifier,  # type: ignore[arg-type]
    )
    tool_arguments = (
        '{"provenance_envelope":"{\\"arguments\\":{\\"body\\":\\"Body from artifact\\",\\"recipient\\":\\"ada@example.test\\"},\\"format_version\\":1,\\"sources\\":{\\"body\\":{\\"kind\\":\\"artifact\\",\\"ref\\":\\"body\\"},\\"recipient\\":{\\"end_byte\\":16,\\"kind\\":\\"prompt_span\\",\\"normalization\\":\\"identity\\",\\"start_byte\\":0}}}"}'
        if body_from_artifact
        else '{"provenance_envelope":"{\\"arguments\\":{\\"body\\":\\"Welcome!\\",\\"recipient\\":\\"ada@example.test\\"},\\"format_version\\":1,\\"sources\\":{\\"body\\":{\\"end_byte\\":25,\\"kind\\":\\"prompt_span\\",\\"normalization\\":\\"identity\\",\\"start_byte\\":17},\\"recipient\\":{\\"end_byte\\":16,\\"kind\\":\\"prompt_span\\",\\"normalization\\":\\"identity\\",\\"start_byte\\":0}}}"}'
        if side_effect
        else '{"folder":"inbox"}'
    )
    model_client = QueuedClient(
        [
            ModelResponse(
                content=None,
                tool_calls=(
                    ModelToolCall(
                        id="call_1",
                        name=tool_id,
                        arguments=tool_arguments,
                    ),
                ),
            ),
            ModelResponse(content="three unread messages"),
        ]
    )
    adapter = OpenAIClientAdapter(
        model_client, models=["local-model", "local-model-v1"], is_local=True
    )
    return (
        WorkflowRunner(
            registrations=registrations,
            catalog=catalog,
            preparation=preparation,
            model_adapter=adapter,
            mcp_bindings=mcp_bindings,
            mcp_client=mcp_client,
            mcp_surfaces=surfaces,
            action_ledger=(
                WorkflowActionLedger(store=store, owner="local-os-user-v1:501:ada")
                if side_effect
                else None
            ),
            approval_store=(
                WorkflowApprovalStore(store=store, owner="local-os-user-v1:501:ada")
                if side_effect
                else None
            ),
        ),
        preparation,
        mcp_client,
        model_client,
    )


def test_runner_executes_one_sealed_no_tool_workflow(tmp_path: Path) -> None:
    runner, preparation, _, _, client = _runner(tmp_path)
    prepared = preparation.prepare(
        workflow_id="document-helper", prompt="Answer me.", now=NOW
    )

    result = runner.run(
        RunDarWorkflowRequest.from_mapping(
            {
                "format_version": 1,
                "workflow_id": "document-helper",
                "prepared_input_id": prepared.prepared_input_id,
            }
        ),
        now=NOW,
    )

    assert result.status == "completed"
    assert result.output == {"message": "completed locally"}
    assert len(client.responses.calls) == 1
    assert runner.traces()[-1].workflow_id == "document-helper"
    assert "Answer me." not in repr(runner.traces()[-1])


def test_runner_never_sends_a_sealed_workspace_artifact_to_the_model_or_trace(
    tmp_path: Path,
) -> None:
    runner, preparation, _, _, client = _runner(
        tmp_path, artifact_verifier=ArtifactVerifier()
    )
    prepared = preparation.prepare(
        workflow_id="document-helper",
        prompt="Answer me.",
        workspace_artifact_ids=("v1.workspace-artifact",),
        now=NOW,
    )

    result = runner.run(
        RunDarWorkflowRequest.from_mapping(
            {
                "format_version": 1,
                "workflow_id": "document-helper",
                "prepared_input_id": prepared.prepared_input_id,
            }
        ),
        now=NOW,
    )

    assert result.output == {"message": "completed locally"}
    model_request = repr(client.responses.calls)
    trace = repr(runner.traces()[-1])
    assert "v1.workspace-artifact" not in model_request
    assert "private document body" not in model_request
    assert "v1.workspace-artifact" not in trace
    assert "private document body" not in trace


def test_runner_rejects_terminal_output_that_misses_registered_contract_field(
    tmp_path: Path,
) -> None:
    runner, preparation, _, _, client = _runner(
        tmp_path, terminal_required_field="answer"
    )
    prepared = preparation.prepare(
        workflow_id="document-helper", prompt="Answer me.", now=NOW
    )

    with pytest.raises(RunDarWorkflowError, match="terminal output"):
        runner.run(
            RunDarWorkflowRequest.from_mapping(
                {
                    "format_version": 1,
                    "workflow_id": "document-helper",
                    "prepared_input_id": prepared.prepared_input_id,
                }
            ),
            now=NOW,
        )

    assert len(client.responses.calls) == 1
    assert runner.traces()[-1].status == "failed"


def test_runner_executes_one_registered_reviewed_read_only_mcp_workflow(
    tmp_path: Path,
) -> None:
    runner, preparation, mcp_client, model_client = _tool_runner(tmp_path)
    prepared = preparation.prepare(
        workflow_id="mail-reader", prompt="List unread email.", now=NOW
    )

    result = runner.run(
        RunDarWorkflowRequest.from_mapping(
            {
                "format_version": 1,
                "workflow_id": "mail-reader",
                "prepared_input_id": prepared.prepared_input_id,
            }
        ),
        now=NOW,
    )

    assert result.output == {"message": "three unread messages"}
    assert mcp_client.calls == [("list_unread", {"folder": "inbox"})]


def test_runner_executes_one_registered_reviewed_side_effecting_mcp_workflow(
    tmp_path: Path,
) -> None:
    runner, preparation, mcp_client, model_client = _tool_runner(
        tmp_path, side_effect=True
    )
    prepared = preparation.prepare(
        workflow_id="mail-reader", prompt="ada@example.test\nWelcome!", now=NOW
    )

    result = runner.run(
        RunDarWorkflowRequest.from_mapping(
            {
                "format_version": 1,
                "workflow_id": "mail-reader",
                "prepared_input_id": prepared.prepared_input_id,
            }
        ),
        now=NOW,
    )

    assert result.status == "completed"
    assert mcp_client.calls == [
        ("send_email", {"recipient": "ada@example.test", "body": "Welcome!"})
    ]
    assert len(model_client.responses.calls) == 2


def test_runner_uses_a_local_broker_only_when_ask_is_selected(
    tmp_path: Path,
) -> None:
    broker = FakeApprovalBroker(LocalApprovalDecision.APPROVED)
    runner, preparation, mcp_client, _ = _tool_runner(
        tmp_path, side_effect=True, approval_broker=broker
    )
    prepared = preparation.prepare(
        workflow_id="mail-reader", prompt="ada@example.test\nWelcome!", now=NOW
    )

    result = runner.run(
        RunDarWorkflowRequest.from_mapping(
            {
                "format_version": 1,
                "workflow_id": "mail-reader",
                "prepared_input_id": prepared.prepared_input_id,
            }
        ),
        now=NOW,
        approval_broker=broker,
    )

    assert result.status == "completed"
    assert len(broker.actions) == 1
    assert mcp_client.calls == [
        ("send_email", {"recipient": "ada@example.test", "body": "Welcome!"})
    ]


def test_runner_materializes_a_hash_bound_artifact_only_for_the_handler(
    tmp_path: Path,
) -> None:
    runner, preparation, mcp_client, model_client = _tool_runner(
        tmp_path,
        side_effect=True,
        body_from_artifact=True,
        artifact_verifier=BodyArtifactVerifier(),
    )
    prepared = preparation.prepare(
        workflow_id="mail-reader",
        prompt="ada@example.test\nUntrusted body",
        workspace_artifact_ids=("v1.body",),
        now=NOW,
    )

    result = runner.run(
        RunDarWorkflowRequest.from_mapping(
            {
                "format_version": 1,
                "workflow_id": "mail-reader",
                "prepared_input_id": prepared.prepared_input_id,
            }
        ),
        now=NOW,
    )

    assert result.status == "completed"
    assert mcp_client.calls == [
        (
            "send_email",
            {"recipient": "ada@example.test", "body": "Body from artifact"},
        )
    ]
    assert "Body from artifact" not in repr(model_client.responses.calls)


def test_side_effecting_prepared_input_cannot_be_replayed(tmp_path: Path) -> None:
    runner, preparation, mcp_client, _ = _tool_runner(tmp_path, side_effect=True)
    prepared = preparation.prepare(
        workflow_id="mail-reader", prompt="ada@example.test\nWelcome!", now=NOW
    )
    request = RunDarWorkflowRequest.from_mapping(
        {
            "format_version": 1,
            "workflow_id": "mail-reader",
            "prepared_input_id": prepared.prepared_input_id,
        }
    )

    runner.run(request, now=NOW)

    with pytest.raises(RunDarWorkflowError, match="registered workflow run failed"):
        runner.run(request, now=NOW)

    assert mcp_client.calls == [
        ("send_email", {"recipient": "ada@example.test", "body": "Welcome!"})
    ]


def test_side_effecting_workflow_dry_run_constructs_no_action(
    tmp_path: Path,
) -> None:
    runner, preparation, mcp_client, model_client = _tool_runner(
        tmp_path, side_effect=True
    )
    prepared = preparation.prepare(
        workflow_id="mail-reader", prompt="ada@example.test\nWelcome!", now=NOW
    )

    result = runner.dry_run(
        RunDarWorkflowRequest.from_mapping(
            {
                "format_version": 1,
                "workflow_id": "mail-reader",
                "prepared_input_id": prepared.prepared_input_id,
            }
        ),
        now=NOW,
    )

    assert result.status == "ready"
    assert mcp_client.calls == []
    assert model_client.responses.calls == []


def test_runner_allows_a_revalidated_same_identity_reconnect(
    tmp_path: Path,
) -> None:
    runner, preparation, mcp_client, model_client = _tool_runner(tmp_path)
    prepared = preparation.prepare(
        workflow_id="mail-reader", prompt="List unread email.", now=NOW
    )
    mcp_client.current_generation = 2

    result = runner.run(
        RunDarWorkflowRequest.from_mapping(
            {
                "format_version": 1,
                "workflow_id": "mail-reader",
                "prepared_input_id": prepared.prepared_input_id,
            }
        ),
        now=NOW,
    )

    assert result.status == "completed"
    assert mcp_client.calls == [("list_unread", {"folder": "inbox"})]
    assert len(model_client.responses.calls) == 2


def test_request_rejects_raw_prompt_and_unknown_fields() -> None:
    with pytest.raises(RunDarWorkflowError, match="exactly"):
        RunDarWorkflowRequest.from_mapping(
            {
                "format_version": 1,
                "workflow_id": "document-helper",
                "prepared_input_id": "v1.opaque.signature",
                "prompt": "raw input is forbidden",
            }
        )


def test_runner_rejects_hosted_adapter_before_consuming_input(tmp_path: Path) -> None:
    runner, preparation, registration, _, client = _runner(tmp_path, local=False)
    prepared = preparation.prepare(
        workflow_id="document-helper", prompt="Answer me.", now=NOW
    )
    request = RunDarWorkflowRequest.from_mapping(
        {
            "format_version": 1,
            "workflow_id": "document-helper",
            "prepared_input_id": prepared.prepared_input_id,
        }
    )

    with pytest.raises(RunDarWorkflowError, match="strict local"):
        runner.run(request, now=NOW)

    assert (
        preparation.load(
            prepared.prepared_input_id, registration=registration, now=NOW
        ).prompt
        == "Answer me."
    )
    assert client.responses.calls == []


def test_runner_dry_run_preflights_without_consuming_or_calling_model(
    tmp_path: Path,
) -> None:
    runner, preparation, registration, _, client = _runner(tmp_path)
    prepared = preparation.prepare(
        workflow_id="document-helper", prompt="Answer me.", now=NOW
    )
    request = RunDarWorkflowRequest.from_mapping(
        {
            "format_version": 1,
            "workflow_id": "document-helper",
            "prepared_input_id": prepared.prepared_input_id,
        }
    )

    result = runner.dry_run(request, now=NOW)

    assert result.status == "ready"
    assert result.workflow_id == "document-helper"
    assert (
        preparation.load(
            prepared.prepared_input_id, registration=registration, now=NOW
        ).prompt
        == "Answer me."
    )
    assert client.responses.calls == []


def test_runner_fails_dar_preflight_before_model_entry(tmp_path: Path) -> None:
    runner, preparation, _, revision, client = _runner(tmp_path)
    prepared = preparation.prepare(
        workflow_id="document-helper", prompt="Answer me.", now=NOW
    )
    runtime = revision.package_root / "agent-runtime.yaml"
    runtime.chmod(0o600)
    runtime.write_text("not: a DAR package", encoding="utf-8")
    request = RunDarWorkflowRequest.from_mapping(
        {
            "format_version": 1,
            "workflow_id": "document-helper",
            "prepared_input_id": prepared.prepared_input_id,
        }
    )

    with pytest.raises(RunDarWorkflowError, match="registered workflow run failed"):
        runner.run(request, now=NOW)

    assert client.responses.calls == []
