"""Tests for the private host that composes DAR authoring runner services."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml


from dynamic_agent_runner.openai_client import (  # noqa: E402
    ModelResponse,
    ModelToolCall,
    OpenAIClientAdapter,
)

from dynamic_agent_runner.workflow_host.host import (  # noqa: E402
    LocalWorkflowHost,
    attach_mcp_client,
    configure_mcp_api_token,
    create_mcp_connection,
    configure_local_host,
)
from dynamic_agent_runner.workflow_host.mcp_client import MCPClientConfiguration  # noqa: E402
from dynamic_agent_runner.workflow_host.mcp_surfaces import MCPDiscoveredTool  # noqa: E402


NOW = datetime(2026, 8, 23, tzinfo=UTC)
TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "templates"


def _write_portable_manifest(source: Path) -> None:
    digest = hashlib.sha256()
    files = []
    for path in sorted(source.iterdir()):
        body = path.read_bytes()
        file_digest = hashlib.sha256(body).hexdigest()
        digest.update(f"{path.name}\0{file_digest}\0{len(body)}\n".encode("utf-8"))
        files.append(
            {"byte_count": len(body), "path": path.name, "sha256": file_digest}
        )
    (source / "package-manifest.json").write_text(
        json.dumps(
            {
                "content_digest": digest.hexdigest(),
                "dar_runtime": {
                    "distribution": "dynamic-agent-runner",
                    "required_version": "0.1.16",
                },
                "descriptor_format_version": 1,
                "files": files,
                "format_version": 2,
                "package_id": "dar-authoring-no-tool-template",
                "runtime_format_version": 1,
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )


class _Responses:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> ModelResponse:
        self.calls.append(kwargs)
        return ModelResponse(content="completed locally")


class _Client:
    def __init__(self) -> None:
        self.responses = _Responses()


class _MemorySecretStore:
    values: dict[str, str] = {}

    def __init__(self, **_: object) -> None:
        return None

    def store(self, secret: str) -> str:
        reference = f"secret-{len(self.values) + 1}"
        self.values[reference] = secret
        return reference

    def load(self, reference: str) -> str:
        return self.values[reference]

    def delete(self, reference: str) -> None:
        self.values.pop(reference, None)


class _ReviewedMCPClient:
    calls: list[tuple[str, dict[str, object]]] = []

    def __init__(self, *, configuration: MCPClientConfiguration, **_: object) -> None:
        self.connection_id = configuration.connection_id
        self.authentication_id = configuration.authentication_id
        self.current_generation = 1

    def initialize(self) -> None:
        return None

    def list_tools(self) -> tuple[MCPDiscoveredTool, ...]:
        return (
            MCPDiscoveredTool(
                name="list_unread",
                input_schema={"type": "object", "properties": {}},
            ),
            MCPDiscoveredTool(
                name="send_email",
                input_schema={"type": "object", "properties": {}},
            ),
        )

    def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        self.calls.append((name, arguments))
        return {"content": [{"type": "text", "text": "three unread messages"}]}


class _ToolClient:
    def __init__(self) -> None:
        self.responses = _ToolResponses()


class _ToolResponses:
    def __init__(self) -> None:
        self._responses = iter(
            [
                ModelResponse(
                    content=None,
                    tool_calls=(
                        ModelToolCall(
                            id="call-1", name="mail_list_unread", arguments="{}"
                        ),
                    ),
                ),
                ModelResponse(content="three unread messages"),
            ]
        )

    def create(self, **_: object) -> ModelResponse:
        return next(self._responses)


def test_host_selects_and_registers_a_local_zip_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_root = tmp_path / "packages"
    source = package_root / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
    _write_portable_manifest(source)
    archive = package_root / "document-helper.zip"
    with zipfile.ZipFile(archive, "w") as package:
        for path in sorted(source.iterdir()):
            package.write(path, path.name)
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.host.create_local_adapter",
        lambda profile: OpenAIClientAdapter(
            _Client(), models=[profile.model_id], is_local=True
        ),
    )
    root = tmp_path / "state"
    configure_local_host(
        root=root,
        package_root=package_root,
        model_id="local-model-v1",
        base_url="http://127.0.0.1:11434/v1",
    )

    host = LocalWorkflowHost.open(root)
    source_handle = host.select_package(archive, now=NOW)
    registration = host.register(
        workflow_id="document-helper", package_source_handle=source_handle, now=NOW
    )

    assert source_handle.startswith("v1.")
    assert registration.workflow_id == "document-helper"


def test_host_reopens_a_secret_free_configured_mcp_client(
    tmp_path: Path, monkeypatch
) -> None:
    package_root = tmp_path / "packages"
    package_root.mkdir()
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.host.create_local_adapter",
        lambda profile: OpenAIClientAdapter(
            _Client(), models=[profile.model_id], is_local=True
        ),
    )
    mcp_configuration = MCPClientConfiguration(
        connection_id="v1.connection",
        authentication_id="v1.authentication",
        peer_certificate_sha256="a" * 64,
        timeout_seconds=10,
        max_response_bytes=32_768,
    )

    configure_local_host(
        root=tmp_path / "state",
        package_root=package_root,
        model_id="local-model-v1",
        base_url="http://127.0.0.1:11434/v1",
        mcp_client_configuration=mcp_configuration,
    )

    host = LocalWorkflowHost.open(tmp_path / "state")

    assert host._mcp_client is not None
    assert host._mcp_client.configuration == mcp_configuration
    host_json = (tmp_path / "state" / "host.json").read_text(encoding="utf-8")
    assert "connection" in host_json
    assert "authentication" in host_json
    assert "token" not in host_json


def test_host_control_plane_binds_an_authenticated_generic_mcp_connection(
    tmp_path: Path, monkeypatch
) -> None:
    package_root = tmp_path / "packages"
    package_root.mkdir()
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.host.create_local_adapter",
        lambda profile: OpenAIClientAdapter(
            _Client(), models=[profile.model_id], is_local=True
        ),
    )
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.connections.KeyringSecretStore",
        _MemorySecretStore,
    )
    configure_local_host(
        root=tmp_path / "state",
        package_root=package_root,
        model_id="local-model-v1",
        base_url="http://127.0.0.1:11434/v1",
    )

    connection = create_mcp_connection(
        root=tmp_path / "state",
        endpoint="https://mcp.example.test/v1",
        scopes={"mail.read"},
        authentication_method="api_token",
    )
    authentication = configure_mcp_api_token(
        root=tmp_path / "state",
        connection_id=connection.connection_id,
        token="secret-token",
    )
    configured = attach_mcp_client(
        root=tmp_path / "state",
        connection_id=connection.connection_id,
        authentication_id=authentication.authentication_id,
        peer_certificate_sha256="b" * 64,
        timeout_seconds=10,
        max_response_bytes=32_768,
    )

    assert configured.mcp_client_configuration is not None
    assert configured.mcp_client_configuration.connection_id == connection.connection_id
    assert "secret-token" not in (tmp_path / "state" / "records.json").read_text(
        encoding="utf-8"
    )


def test_host_reviews_only_the_human_approved_generic_mcp_surface(
    tmp_path: Path, monkeypatch
) -> None:
    package_root = tmp_path / "packages"
    package_root.mkdir()
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.host.create_local_adapter",
        lambda profile: OpenAIClientAdapter(
            _Client(), models=[profile.model_id], is_local=True
        ),
    )
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.connections.KeyringSecretStore",
        _MemorySecretStore,
    )
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.host.MCPConnectionClient",
        _ReviewedMCPClient,
    )
    root = tmp_path / "state"
    configure_local_host(
        root=root,
        package_root=package_root,
        model_id="local-model-v1",
        base_url="http://127.0.0.1:11434/v1",
    )
    connection = create_mcp_connection(
        root=root,
        endpoint="https://mcp.example.test/v1",
        scopes={"mail.read"},
        authentication_method="api_token",
    )
    authentication = configure_mcp_api_token(
        root=root, connection_id=connection.connection_id, token="secret-token"
    )
    attach_mcp_client(
        root=root,
        connection_id=connection.connection_id,
        authentication_id=authentication.authentication_id,
        peer_certificate_sha256="a" * 64,
        timeout_seconds=10,
        max_response_bytes=32_768,
    )

    host = LocalWorkflowHost.open(root)
    assert {tool.name for tool in host.discover_mcp_tools()} == {
        "list_unread",
        "send_email",
    }
    snapshot = host.review_mcp_surface(
        approved_read_only_tool_names={"list_unread"},
        approved_tool_side_effects={"send_email": "write"},
    )

    assert snapshot.snapshot_id.startswith("v1.")
    assert dict(snapshot.tool_side_effects) == {
        "list_unread": "read",
        "send_email": "write",
    }


def test_host_binds_a_staged_mcp_package_only_to_a_reviewed_surface(
    tmp_path: Path, monkeypatch
) -> None:
    package_root = tmp_path / "packages"
    source = package_root / "mail-reader"
    shutil.copytree(TEMPLATE_ROOT, source)
    _add_read_only_mcp_tool(source)
    root = _configured_reviewable_mcp_host(
        root=tmp_path / "state", package_root=package_root, monkeypatch=monkeypatch
    )
    host = LocalWorkflowHost.open(root)
    snapshot = host.review_mcp_surface(approved_read_only_tool_names={"list_unread"})
    source_handle = host.select_package(source, now=NOW)

    binding = host.bind_mcp_package(
        package_source_handle=source_handle,
        snapshot_id=snapshot.snapshot_id,
        now=NOW,
    )

    assert binding.snapshot_id == snapshot.snapshot_id
    assert dict(binding.tool_id_to_remote_name) == {"mail_list_unread": "list_unread"}


def test_host_runs_a_registered_reviewed_mcp_workflow(
    tmp_path: Path, monkeypatch
) -> None:
    package_root = tmp_path / "packages"
    source = package_root / "mail-reader"
    shutil.copytree(TEMPLATE_ROOT, source)
    _add_read_only_mcp_tool(source)
    root = _configured_reviewable_mcp_host(
        root=tmp_path / "state", package_root=package_root, monkeypatch=monkeypatch
    )
    model_client = _ToolClient()
    _ReviewedMCPClient.calls.clear()
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.host.create_local_adapter",
        lambda profile: OpenAIClientAdapter(
            model_client,
            models=[profile.model_id, "local-model"],
            is_local=True,
        ),
    )
    host = LocalWorkflowHost.open(root)
    snapshot = host.review_mcp_surface(approved_read_only_tool_names={"list_unread"})
    source_handle = host.select_package(source, now=NOW)
    binding = host.bind_mcp_package(
        package_source_handle=source_handle, snapshot_id=snapshot.snapshot_id, now=NOW
    )
    registration = host.register(
        workflow_id="mail-reader",
        package_source_handle=source_handle,
        mcp_binding_id=binding.binding_id,
        now=NOW,
    )
    prepared = host.prepare(
        workflow_id=registration.workflow_id, prompt="List unread email.", now=NOW
    )

    result = host.run(
        workflow_id=registration.workflow_id,
        prepared_input_id=prepared.prepared_input_id,
        now=NOW,
    )

    assert result.output == {"message": "three unread messages"}
    assert _ReviewedMCPClient.calls == [("list_unread", {})]


def _configured_reviewable_mcp_host(
    *, root: Path, package_root: Path, monkeypatch
) -> Path:
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.host.create_local_adapter",
        lambda profile: OpenAIClientAdapter(
            _Client(), models=[profile.model_id], is_local=True
        ),
    )
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.connections.KeyringSecretStore",
        _MemorySecretStore,
    )
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.host.MCPConnectionClient",
        _ReviewedMCPClient,
    )
    configure_local_host(
        root=root,
        package_root=package_root,
        model_id="local-model-v1",
        base_url="http://127.0.0.1:11434/v1",
    )
    connection = create_mcp_connection(
        root=root,
        endpoint="https://mcp.example.test/v1",
        scopes={"mail.read"},
        authentication_method="api_token",
    )
    authentication = configure_mcp_api_token(
        root=root, connection_id=connection.connection_id, token="secret-token"
    )
    attach_mcp_client(
        root=root,
        connection_id=connection.connection_id,
        authentication_id=authentication.authentication_id,
        peer_certificate_sha256="a" * 64,
        timeout_seconds=10,
        max_response_bytes=32_768,
    )
    return root


def _add_read_only_mcp_tool(source: Path) -> None:
    descriptor = source / "workflow-descriptor.yaml"
    descriptor_value = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
    descriptor_value["package_id"] = "mail-reader"
    descriptor_value["tools"] = [
        {
            "id": "mail_list_unread",
            "kind": "mcp",
            "remote_tool_name": "list_unread",
            "side_effect": "read",
        }
    ]
    descriptor_value["task_invocation"].update(
        {"allowed_tool_ids": ["mail_list_unread"], "max_total_tool_calls": 3}
    )
    descriptor_value["limits"]["max_steps"] = 3
    descriptor.write_text(yaml.safe_dump(descriptor_value), encoding="utf-8")
    runtime = source / "agent-runtime.yaml"
    runtime_value = yaml.safe_load(runtime.read_text(encoding="utf-8"))
    runtime_value["package_id"] = "mail-reader"
    runtime_value["runtime"]["execution_policy"]["max_steps"] = 3
    runtime_value["runtime"]["execution_policy"]["tool_use_completion"] = {
        "run_again": "required",
        "stop_on_tool": "disabled",
        "final_output": "default",
    }
    runtime_value["tools"] = [
        {
            "id": "mail_list_unread",
            "label": "List unread mail",
            "tool_type": "external_api",
            "description_for_llm": "List unread mail.",
            "adapter": "host.mcp",
            "input_schema": {"type": "object", "properties": {}},
            "side_effect": "read",
            "approval_required": False,
            "timeout": "runtime_default",
            "retry_policy": "none",
            "failure_behavior": "error",
        }
    ]
    runtime_value["nodes"][0]["available_tools"] = ["mail_list_unread"]
    runtime.write_text(yaml.safe_dump(runtime_value), encoding="utf-8")


def test_host_composes_human_setup_with_sealed_dry_run(
    tmp_path: Path, monkeypatch
) -> None:
    package_root = tmp_path / "packages"
    source = package_root / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
    client = _Client()
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.host.create_local_adapter",
        lambda profile: OpenAIClientAdapter(
            client, models=[profile.model_id], is_local=True
        ),
    )

    configured = configure_local_host(
        root=tmp_path / "state",
        package_root=package_root,
        model_id="local-model-v1",
        base_url="http://127.0.0.1:11434/v1",
    )
    host = LocalWorkflowHost.open(tmp_path / "state")
    source_handle = host.select_package(source, now=NOW)
    registration = host.register(
        workflow_id="document-helper", package_source_handle=source_handle, now=NOW
    )
    prepared = host.prepare(
        workflow_id=registration.workflow_id, prompt="Answer me.", now=NOW
    )

    result = host.dry_run(
        workflow_id=registration.workflow_id,
        prepared_input_id=prepared.prepared_input_id,
        now=NOW,
    )

    assert configured.profile_id == registration.profile_id
    assert result.status == "ready"
    assert client.responses.calls == []


def test_host_ingresses_a_file_only_under_the_registered_workspace_contract(
    tmp_path: Path, monkeypatch
) -> None:
    package_root = tmp_path / "packages"
    source = package_root / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
    descriptor = source / "workflow-descriptor.yaml"
    descriptor.write_text(
        descriptor.read_text(encoding="utf-8").replace(
            "allowed_artifact_roles: []", "allowed_artifact_roles: [document]"
        ),
        encoding="utf-8",
    )
    input_root = tmp_path / "input"
    input_root.mkdir()
    document = input_root / "document.txt"
    document.write_text("document body", encoding="utf-8")
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.host.create_local_adapter",
        lambda profile: OpenAIClientAdapter(
            _Client(), models=[profile.model_id], is_local=True
        ),
    )

    configure_local_host(
        root=tmp_path / "state",
        package_root=package_root,
        workspace_input_root=input_root,
        model_id="local-model-v1",
        base_url="http://127.0.0.1:11434/v1",
    )
    host = LocalWorkflowHost.open(tmp_path / "state")
    source_handle = host.select_package(source, now=NOW)
    registration = host.register(
        workflow_id="document-helper", package_source_handle=source_handle, now=NOW
    )

    artifact = host.ingress_file(
        workflow_id=registration.workflow_id,
        path=document,
        role="document",
        media_type="text/plain",
        now=NOW,
    )

    assert artifact.artifact_id.startswith("v1.")
    assert artifact.byte_count == len(b"document body")
    prepared = host.prepare(
        workflow_id=registration.workflow_id,
        prompt="Answer the request.",
        workspace_artifact_ids=(artifact.artifact_id,),
        now=NOW,
    )
    result = host.dry_run(
        workflow_id=registration.workflow_id,
        prepared_input_id=prepared.prepared_input_id,
        now=NOW,
    )
    assert result.status == "ready"
    assert str(document) not in str(result)
    with pytest.raises(ValueError, match="not configured"):
        configure_local_host(
            root=tmp_path / "no-ingress-state",
            package_root=package_root,
            model_id="local-model-v1",
            base_url="http://127.0.0.1:11434/v1",
        )
        LocalWorkflowHost.open(tmp_path / "no-ingress-state").ingress_file(
            workflow_id=registration.workflow_id,
            path=document,
            role="document",
            media_type="text/plain",
            now=NOW,
        )
