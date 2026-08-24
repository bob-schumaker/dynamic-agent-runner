"""Tests for DAR authoring's closed no-tool workflow runner."""

from __future__ import annotations

import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml


PLUGIN_SERVER_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "server"
sys.path.insert(0, str(PLUGIN_SERVER_ROOT))

from dynamic_agent_runner.openai_client import (  # noqa: E402
    ModelToolCall,
    ModelResponse,
    OpenAIClientAdapter,
)

from dar_workflow_server.catalog import PackageCatalog  # noqa: E402
from dar_workflow_server.connections import MCPConnectionControlPlane  # noqa: E402
from dar_workflow_server.mcp_binding import (  # noqa: E402
    MCPWorkflowCapabilityBindingControlPlane,
)
from dar_workflow_server.mcp_surfaces import (  # noqa: E402
    MCPDiscoveredTool,
    MCPSurfaceSnapshotControlPlane,
)
from dar_workflow_server.package_sources import PackageSourceSelectionPolicy  # noqa: E402
from dar_workflow_server.policy import compile_workflow_policy, resolve_capabilities  # noqa: E402
from dar_workflow_server.preparation import WorkflowInvocationPreparationService  # noqa: E402
from dar_workflow_server.profiles import LocalModelProfileControlPlane  # noqa: E402
from dar_workflow_server.registration import WorkflowRegistrationService  # noqa: E402
from dar_workflow_server.runner import (  # noqa: E402
    RunDarWorkflowError,
    RunDarWorkflowRequest,
    WorkflowRunner,
)
from dar_workflow_server.staging import PrivatePackageStager  # noqa: E402
from dar_workflow_server.state import PrivateStateStore  # noqa: E402


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


def _runner(tmp_path: Path, *, local: bool = True):
    source = tmp_path / "packages" / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
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
        registrations=registrations, catalog=catalog, store=store
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


def _tool_runner(tmp_path: Path):
    source = tmp_path / "packages" / "mail-reader"
    shutil.copytree(TEMPLATE_ROOT, source)
    descriptor_path = source / "workflow-descriptor.yaml"
    descriptor = yaml.safe_load(descriptor_path.read_text(encoding="utf-8"))
    descriptor["package_id"] = "mail-reader"
    descriptor["tools"] = [
        {
            "id": "mail_lookup",
            "kind": "mcp",
            "remote_tool_name": "list_unread",
            "side_effect": "read",
        }
    ]
    descriptor["task_invocation"].update(
        {"allowed_tool_ids": ["mail_lookup"], "max_total_tool_calls": 1}
    )
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
            "id": "mail_lookup",
            "label": "List unread mail",
            "tool_type": "external_api",
            "description_for_llm": "List unread mail.",
            "adapter": "host.mcp",
            "input_schema": {
                "type": "object",
                "properties": {"folder": {"type": "string"}},
                "required": ["folder"],
                "additionalProperties": False,
            },
            "side_effect": "read",
            "approval_required": False,
            "timeout": "runtime_default",
            "retry_policy": "none",
            "failure_behavior": "error",
        }
    ]
    runtime["nodes"][0]["available_tools"] = ["mail_lookup"]
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
    surfaces = MCPSurfaceSnapshotControlPlane(store=store, connections=connections)
    snapshot = surfaces.create(
        connection_id=connection.connection_id,
        authentication_id=authentication.authentication_id,
        connection_generation=1,
        tools=mcp_client.list_tools(),
        approved_read_only_tool_names={"list_unread"},
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
            policy, available_capabilities={"local_model", "mcp_read_only"}
        ),
        mcp_binding_id=mcp_binding.binding_id,
    )
    preparation = WorkflowInvocationPreparationService(
        registrations=registrations, catalog=catalog, store=store
    )
    model_client = QueuedClient(
        [
            ModelResponse(
                content=None,
                tool_calls=(
                    ModelToolCall(
                        id="call_1",
                        name="mail_lookup",
                        arguments='{"folder":"inbox"}',
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
    assert len(model_client.responses.calls) == 2


def test_runner_rejects_mcp_generation_drift_before_consuming_input(
    tmp_path: Path,
) -> None:
    runner, preparation, mcp_client, model_client = _tool_runner(tmp_path)
    prepared = preparation.prepare(
        workflow_id="mail-reader", prompt="List unread email.", now=NOW
    )
    mcp_client.current_generation = 2

    with pytest.raises(RunDarWorkflowError, match="MCP capability is unavailable"):
        runner.run(
            RunDarWorkflowRequest.from_mapping(
                {
                    "format_version": 1,
                    "workflow_id": "mail-reader",
                    "prepared_input_id": prepared.prepared_input_id,
                }
            ),
            now=NOW,
        )

    assert mcp_client.calls == []
    assert model_client.responses.calls == []


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
