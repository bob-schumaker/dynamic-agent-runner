"""Tests for the private host that composes DAR authoring runner services."""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import zipfile
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml


from dynamic_agent_runner.openai_client import (  # noqa: E402
    AsyncOpenAIClientAdapter,
    ModelResponse,
    ModelToolCall,
    OpenAIClientAdapter,
)

from dynamic_agent_runner.workflow_host.host import (  # noqa: E402
    LocalWorkflowHost,
    LocalWorkflowHostError,
    attach_mcp_client,
    configure_apple_local_host,
    configure_qwen25_vl_3b_floorplan_grpo_transformers_peft_host,
    configure_hosted_openai_host,
    configure_mcp_api_token,
    create_mcp_connection,
    configure_local_host,
)
from dynamic_agent_runner.workflow_host.connections import (  # noqa: E402
    MCPConnectionControlPlane,
)
from dynamic_agent_runner.workflow_host.capabilities import (  # noqa: E402
    BUILTIN_CAPABILITY_CONTRACTS,
    CapabilityCatalog,
    CapabilityProvider,
    CapabilityRequirement,
    CapabilityRequirements,
    ProviderAvailability,
)
from dynamic_agent_runner.workflow_host.authorized_tools import (  # noqa: E402
    create_authorized_mcp_tool_bindings,
)
from dynamic_agent_runner.workflow_host.mcp_client import MCPClientConfiguration  # noqa: E402
from dynamic_agent_runner.workflow_host.mcp_surfaces import MCPDiscoveredTool  # noqa: E402
from dynamic_agent_runner.workflow_host.profiles import (  # noqa: E402
    LocalModelProfileControlPlane,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore  # noqa: E402
from dynamic_agent_runner.workflow_host.reviewed_tool_packages import (  # noqa: E402
    ReviewedToolPackageBinding,
)


NOW = datetime(2026, 8, 23, tzinfo=UTC)
TEMPLATE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "specs"
    / "agent-engineering-plugin-migration"
    / "legacy-dar-authoring"
    / "templates"
)


def test_configure_qwen_transformers_peft_host_uses_the_builtin_profile(
    tmp_path: Path,
) -> None:
    root = tmp_path / "state"
    package_root = tmp_path / "packages"
    package_root.mkdir()

    configuration = configure_qwen25_vl_3b_floorplan_grpo_transformers_peft_host(
        root=root,
        package_root=package_root,
    )
    host = LocalWorkflowHost.open(root)

    assert configuration.profile_id == host._profile.profile_id
    assert host._profile.runner_id == "transformers-peft-v1"
    assert host._runner._model_adapter.models == ("qwen25-vl-3b-floorplan-grpo",)


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
                    "required_version": "0.2.1",
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


def test_local_host_open_uses_an_injected_controller_mcp_client(
    tmp_path: Path,
) -> None:
    configuration = MCPClientConfiguration(
        connection_id="v1.controller-connection",
        authentication_id="v1.controller-authentication",
        peer_certificate_sha256="a" * 64,
        timeout_seconds=1,
        max_response_bytes=1024,
    )
    configure_local_host(
        root=tmp_path / "state",
        package_root=tmp_path / "packages",
        model_id="local-model",
        base_url="http://127.0.0.1:11434/v1",
        mcp_client_configuration=configuration,
    )
    client = object()
    observed: list[object] = []

    def controller_client(supplied: object) -> object:
        observed.append(supplied)
        return client

    host = LocalWorkflowHost.open(
        tmp_path / "state", mcp_client_factory=controller_client
    )

    assert observed == [configuration]
    assert host._mcp_client is client


def test_local_host_open_supplies_the_trusted_local_tool_executor(
    tmp_path: Path,
) -> None:
    configure_local_host(
        root=tmp_path / "state",
        package_root=tmp_path / "packages",
        model_id="local-model",
        base_url="http://127.0.0.1:11434/v1",
    )

    host = LocalWorkflowHost.open(tmp_path / "state")

    assert host._runner.local_tool_execution_available


def test_local_host_configures_one_reviewed_tool_package(tmp_path: Path) -> None:
    configure_local_host(
        root=tmp_path / "state",
        package_root=tmp_path / "packages",
        model_id="local-model",
        base_url="http://127.0.0.1:11434/v1",
    )
    host = LocalWorkflowHost.open(tmp_path / "state")
    binding = ReviewedToolPackageBinding(
        binding_id="network-review-1",
        binding_digest="a" * 64,
        allowed_tool_ids=("packet_summary",),
        artifact_aware_tool_ids=("packet_summary",),
    )

    configured = host.configure_reviewed_tool_package(
        package_name="network-tools", binding=binding
    )

    assert configured.package_name == "network-tools"
    assert (
        host._reviewed_tool_packages.resolve(
            package_name="network-tools", current_binding=binding
        )
        == binding
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


class _AsyncResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.error: BaseException | None = None

    async def create(self, **kwargs: object) -> ModelResponse:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return ModelResponse(content="completed on device")


class _AsyncClient:
    def __init__(self) -> None:
        self.responses = _AsyncResponses()


class _AppleCallbackContent:
    def __init__(self, payload: str) -> None:
        self._payload = payload

    def to_json(self) -> str:
        return self._payload


class _AppleCallbackSession:
    def __init__(self, *, tools: list[object], callback_payload: str) -> None:
        self.tools = tuple(tools)
        self.callback_payload = callback_payload
        self.callback_results: list[object] = []
        self.callback_error: BaseException | None = None

    async def respond(self, _prompt: str, **_kwargs: object) -> str:
        try:
            self.callback_results.append(
                await self.tools[0].call(_AppleCallbackContent(self.callback_payload))
            )
        except BaseException as error:
            self.callback_error = error
            raise
        return "three unread messages"


class _AppleCallbackSDK:
    class Tool:
        pass

    def __init__(self, callback_payload: str = "{}") -> None:
        self.callback_payload = callback_payload
        self.sessions: list[_AppleCallbackSession] = []

    def SystemLanguageModel(self) -> object:
        return type("SystemModel", (), {"is_available": lambda _self: (True, None)})()

    def LanguageModelSession(
        self, *, instructions: str | None, tools: list[object]
    ) -> _AppleCallbackSession:
        del instructions
        session = _AppleCallbackSession(
            tools=tools, callback_payload=self.callback_payload
        )
        self.sessions.append(session)
        return session

    @staticmethod
    def generable(_description: str):
        def decorate(cls: type[object]) -> type[object]:
            cls.generation_schema = classmethod(lambda _cls: object())
            return cls

        return decorate


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
                input_schema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            ),
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

    def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        self.calls.append((name, arguments))
        return {"content": [{"type": "text", "text": "three unread messages"}]}


class _ToolClient:
    def __init__(self) -> None:
        self.responses = _ToolResponses()


class _ToolResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
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

    def create(self, **kwargs: object) -> ModelResponse:
        self.calls.append(kwargs)
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
            _Client(),
            models=[profile.execution_model_id],
            is_local=True,
            model_id_mapping={profile.execution_model_id: profile.model_id},
            execution_profile_adapter_id=profile.adapter_id,
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


def test_host_open_constructs_apple_adapter_with_only_configured_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_root = tmp_path / "packages"
    package_root.mkdir()
    source = package_root / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
    runtime_path = source / "agent-runtime.yaml"
    runtime = yaml.safe_load(runtime_path.read_text(encoding="utf-8"))
    runtime["runtime"]["execution_policy"]["model"] = "apple-system-language-model"
    runtime["nodes"][0]["model"] = "apple-system-language-model"
    runtime_path.write_text(yaml.safe_dump(runtime), encoding="utf-8")
    constructed_with: list[object] = []
    client = _AsyncClient()
    adapter = AsyncOpenAIClientAdapter(
        client,
        models=["apple-system-language-model"],
        is_local=True,
        execution_profile_adapter_id="apple-foundation-models-adapter-v1",
    )
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.profiles.preflight_apple_foundation_models",
        lambda: None,
    )
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.host.create_apple_foundation_model_async_adapter",
        lambda config: constructed_with.append(config) or adapter,
    )
    configured = configure_apple_local_host(
        root=tmp_path / "state",
        package_root=package_root,
        model_id="apple-system-language-model",
    )

    host = LocalWorkflowHost.open(tmp_path / "state")
    source_handle = host.select_package(source, now=NOW)
    registration = host.register(
        workflow_id="document-helper", package_source_handle=source_handle, now=NOW
    )
    prepared = host.prepare(
        workflow_id=registration.workflow_id, prompt="Answer me.", now=NOW
    )
    result = host.run(
        workflow_id=registration.workflow_id,
        prepared_input_id=prepared.prepared_input_id,
        now=NOW,
    )

    assert host._runner._model_adapter is adapter
    assert constructed_with[0].model_aliases == ("apple-system-language-model",)
    assert host._runner._configured_profile.profile_id == configured.profile_id
    assert result.output == {"message": "completed on device"}
    assert len(client.responses.calls) == 1
    assert "Answer me." not in repr(host._runner.traces()[-1])

    client.responses.error = RuntimeError("Apple async failure")
    failed = host.prepare(
        workflow_id=registration.workflow_id, prompt="Do not disclose me.", now=NOW
    )
    with pytest.raises(ValueError, match="DAR workflow execution failed"):
        host.run(
            workflow_id=registration.workflow_id,
            prepared_input_id=failed.prepared_input_id,
            now=NOW,
        )
    assert "Do not disclose me." not in repr(host._runner.traces()[-1])

    client.responses.error = asyncio.CancelledError()
    cancelled = host.prepare(
        workflow_id=registration.workflow_id, prompt="Cancel me.", now=NOW
    )
    with pytest.raises(asyncio.CancelledError):
        host.run(
            workflow_id=registration.workflow_id,
            prepared_input_id=cancelled.prepared_input_id,
            now=NOW,
        )


def test_host_open_constructs_configured_hosted_adapter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_root = tmp_path / "packages"
    package_root.mkdir()
    source = package_root / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
    descriptor_path = source / "workflow-descriptor.yaml"
    descriptor = yaml.safe_load(descriptor_path.read_text(encoding="utf-8"))
    descriptor["model"]["profile_requirement"] = "general-language-model-v1"
    descriptor_path.write_text(yaml.safe_dump(descriptor), encoding="utf-8")
    client = _Client()
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.host.create_hosted_openai_adapter",
        lambda profile: OpenAIClientAdapter(
            client,
            models=[profile.execution_model_id],
            is_local=False,
            model_id_mapping={profile.execution_model_id: profile.model_id},
            execution_profile_adapter_id=profile.adapter_id,
        ),
    )
    configured = configure_hosted_openai_host(
        root=tmp_path / "state",
        package_root=package_root,
        model_id="hosted-model-v1",
        base_url="https://models.example.test/v1",
    )

    host = LocalWorkflowHost.open(tmp_path / "state")
    source_handle = host.select_package(source, now=NOW)
    registration = host.register(
        workflow_id="document-helper", package_source_handle=source_handle, now=NOW
    )
    prepared = host.prepare(
        workflow_id=registration.workflow_id, prompt="Answer me.", now=NOW
    )
    result = host.run(
        workflow_id=registration.workflow_id,
        prepared_input_id=prepared.prepared_input_id,
        now=NOW,
    )

    assert host._runner._configured_profile.profile_id == configured.profile_id
    assert host._runner._model_adapter.is_local is False
    assert result.output == {"message": "completed locally"}
    assert len(client.responses.calls) == 1


def test_host_reopens_a_secret_free_configured_mcp_client(
    tmp_path: Path, monkeypatch
) -> None:
    package_root = tmp_path / "packages"
    package_root.mkdir()
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.host.create_local_adapter",
        lambda profile: OpenAIClientAdapter(
            _Client(),
            models=[profile.execution_model_id],
            is_local=True,
            model_id_mapping={profile.execution_model_id: profile.model_id},
            execution_profile_adapter_id=profile.adapter_id,
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
            _Client(),
            models=[profile.execution_model_id],
            is_local=True,
            model_id_mapping={profile.execution_model_id: profile.model_id},
            execution_profile_adapter_id=profile.adapter_id,
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
            _Client(),
            models=[profile.execution_model_id],
            is_local=True,
            model_id_mapping={profile.execution_model_id: profile.model_id},
            execution_profile_adapter_id=profile.adapter_id,
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
            models=[profile.execution_model_id],
            is_local=True,
            model_id_mapping={profile.execution_model_id: profile.model_id},
            execution_profile_adapter_id=profile.adapter_id,
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


def test_apple_host_runs_only_the_bound_read_only_mcp_callback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_root = tmp_path / "packages"
    source = package_root / "mail-reader"
    shutil.copytree(TEMPLATE_ROOT, source)
    _add_read_only_mcp_tool(source)
    runtime_path = source / "agent-runtime.yaml"
    runtime = yaml.safe_load(runtime_path.read_text(encoding="utf-8"))
    runtime["runtime"]["execution_policy"]["model"] = "apple-system-language-model"
    runtime["nodes"][0]["model"] = "apple-system-language-model"
    runtime_path.write_text(yaml.safe_dump(runtime), encoding="utf-8")
    sdk = _AppleCallbackSDK()
    _ReviewedMCPClient.calls.clear()
    monkeypatch.setattr(
        "dynamic_agent_runner.apple_foundation_models._load_sdk", lambda: sdk
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
    configure_apple_local_host(
        root=root,
        package_root=package_root,
        model_id="apple-system-language-model",
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

    session = sdk.sessions[0]
    assert result.output == {"message": "three unread messages"}
    assert _ReviewedMCPClient.calls == [("list_unread", {})]
    assert len(session.tools) == 1
    assert session.callback_error is None
    assert not hasattr(session.tools[0], "handler")
    assert not hasattr(session.tools[0], "registry")
    trace = host.run_traces()[-1]
    assert trace.status == "completed"
    assert "List unread email." not in repr(trace)


def test_apple_host_does_not_dispatch_an_unapproved_write_callback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_root = tmp_path / "packages"
    source = package_root / "mail-writer"
    shutil.copytree(TEMPLATE_ROOT, source)
    _add_approval_mcp_tool(source)
    runtime_path = source / "agent-runtime.yaml"
    runtime = yaml.safe_load(runtime_path.read_text(encoding="utf-8"))
    runtime["runtime"]["execution_policy"]["model"] = "apple-system-language-model"
    runtime["nodes"][0]["model"] = "apple-system-language-model"
    runtime_path.write_text(yaml.safe_dump(runtime), encoding="utf-8")
    sdk = _AppleCallbackSDK(
        json.dumps(
            {
                "provenance_envelope": json.dumps(
                    {
                        "arguments": {
                            "body": "Welcome!",
                            "recipient": "ada@example.test",
                        },
                        "format_version": 1,
                        "sources": {
                            "body": {
                                "end_byte": 25,
                                "kind": "prompt_span",
                                "normalization": "identity",
                                "start_byte": 17,
                            },
                            "recipient": {
                                "end_byte": 16,
                                "kind": "prompt_span",
                                "normalization": "identity",
                                "start_byte": 0,
                            },
                        },
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                )
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    _ReviewedMCPClient.calls.clear()
    monkeypatch.setattr(
        "dynamic_agent_runner.apple_foundation_models._load_sdk", lambda: sdk
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
    configure_apple_local_host(
        root=root,
        package_root=package_root,
        model_id="apple-system-language-model",
    )
    connection = create_mcp_connection(
        root=root,
        endpoint="https://mcp.example.test/v1",
        scopes={"mail.send"},
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
    snapshot = host.review_mcp_surface(
        approved_read_only_tool_names=(),
        approved_tool_side_effects={"send_email": "write"},
    )
    source_handle = host.select_package(source, now=NOW)
    binding = host.bind_mcp_package(
        package_source_handle=source_handle, snapshot_id=snapshot.snapshot_id, now=NOW
    )
    registration = host.register(
        workflow_id="mail-writer",
        package_source_handle=source_handle,
        mcp_binding_id=binding.binding_id,
        now=NOW,
    )
    prepared = host.prepare(
        workflow_id=registration.workflow_id,
        prompt="ada@example.test Welcome!",
        now=NOW,
    )
    handler_calls: list[dict[str, object]] = []

    def spy_bindings(**kwargs: object):
        bindings = create_authorized_mcp_tool_bindings(**kwargs)

        def handler(arguments: dict[str, object], *, binding=bindings[0]):
            handler_calls.append(dict(arguments))
            return binding.handler(arguments)

        return (replace(bindings[0], handler=handler),)

    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.runner.create_authorized_mcp_tool_bindings",
        spy_bindings,
    )

    with pytest.raises(ValueError, match="local approval is unavailable"):
        host.run(
            workflow_id=registration.workflow_id,
            prepared_input_id=prepared.prepared_input_id,
            now=NOW,
        )

    assert _ReviewedMCPClient.calls == []
    assert handler_calls == []
    assert sdk.sessions == []
    trace = host.run_traces()[-1]
    assert trace.status == "failed"
    assert "ada@example.test Welcome!" not in repr(trace)


def test_host_keeps_connection_setup_material_out_of_execution_surfaces(
    tmp_path: Path, monkeypatch
) -> None:
    package_root = tmp_path / "packages"
    source = package_root / "mail-reader"
    shutil.copytree(TEMPLATE_ROOT, source)
    _add_read_only_mcp_tool(source)
    root = tmp_path / "state"
    oauth_sentinels = {
        "oauth-access-token-sentinel",
        "oauth-authorization-endpoint-sentinel",
        "oauth-client-id-sentinel",
        "oauth-issuer-sentinel",
        "oauth-metadata-sentinel",
        "oauth-refresh-token-sentinel",
        "oauth-registration-id-sentinel",
        "oauth-resource-sentinel",
        "oauth-scope-sentinel",
        "oauth-token-endpoint-sentinel",
    }
    model_client = _ToolClient()
    _ReviewedMCPClient.calls.clear()
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.host.create_local_adapter",
        lambda profile: OpenAIClientAdapter(
            model_client,
            models=[profile.execution_model_id],
            is_local=True,
            model_id_mapping={profile.execution_model_id: profile.model_id},
            execution_profile_adapter_id=profile.adapter_id,
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
        endpoint="https://oauth-metadata-sentinel.example.test/mcp",
        scopes={"oauth-scope-sentinel"},
        authentication_method="oauth_authorization_code_pkce_loopback",
    )
    authentication = MCPConnectionControlPlane(
        store=PrivateStateStore(root),
        profiles=LocalModelProfileControlPlane(store=PrivateStateStore(root)),
    ).configure_oauth_token(
        connection.connection_id,
        '{"access_token":"oauth-access-token-sentinel",'
        '"refresh_token":"oauth-refresh-token-sentinel"}',
        token_endpoint="https://oauth-token-endpoint-sentinel.example.test/token",
        client_id="oauth-client-id-sentinel",
        resource="https://oauth-resource-sentinel.example.test/mcp",
        issuer="https://oauth-issuer-sentinel.example.test",
        authorization_endpoint=(
            "https://oauth-authorization-endpoint-sentinel.example.test/authorize"
        ),
        registration_id="v1.oauth-registration-id-sentinel",
        persistent_reconnect=True,
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

    package_text = "".join(
        path.read_text(encoding="utf-8") for path in source.iterdir() if path.is_file()
    )
    model_requests = json.dumps(model_client.responses.calls, sort_keys=True)
    traces = json.dumps([trace.__dict__ for trace in host.run_traces()], sort_keys=True)
    action_payloads = json.loads((root / "records.json").read_text(encoding="utf-8"))[
        "records"
    ]
    action_ledger = json.dumps(
        [
            record["payload"]
            for record in action_payloads.values()
            if str(record.get("kind", "")).startswith("workflow_action_")
        ],
        sort_keys=True,
    )
    public_values = "\n".join(
        (package_text, model_requests, traces, action_ledger, str(result))
    )

    assert _ReviewedMCPClient.calls == [("list_unread", {})]
    assert all(sentinel not in public_values for sentinel in oauth_sentinels)


def _configured_reviewable_mcp_host(
    *, root: Path, package_root: Path, monkeypatch
) -> Path:
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.host.create_local_adapter",
        lambda profile: OpenAIClientAdapter(
            _Client(),
            models=[profile.execution_model_id],
            is_local=True,
            model_id_mapping={profile.execution_model_id: profile.model_id},
            execution_profile_adapter_id=profile.adapter_id,
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
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
            "side_effect": "read",
            "approval_required": False,
            "timeout": "runtime_default",
            "retry_policy": "none",
            "failure_behavior": "error",
        }
    ]
    runtime_value["nodes"][0]["available_tools"] = ["mail_list_unread"]
    runtime.write_text(yaml.safe_dump(runtime_value), encoding="utf-8")


def _add_approval_mcp_tool(source: Path) -> None:
    descriptor = source / "workflow-descriptor.yaml"
    descriptor_value = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
    descriptor_value["package_id"] = "mail-writer"
    descriptor_value["tools"] = [
        {
            "id": "mail_send",
            "kind": "mcp",
            "remote_tool_name": "send_email",
            "side_effect": "write",
            "approval_required": True,
        }
    ]
    descriptor_value["task_invocation"].update(
        {
            "allowed_tool_ids": ["mail_send"],
            "argument_sources": {
                "mail_send": {
                    "recipient": {
                        "sources": ["cited_original_prompt_span"],
                        "authority": True,
                    },
                    "body": {
                        "sources": ["cited_original_prompt_span"],
                        "authority": False,
                    },
                }
            },
            "max_total_tool_calls": 1,
        }
    )
    descriptor.write_text(yaml.safe_dump(descriptor_value), encoding="utf-8")
    runtime = source / "agent-runtime.yaml"
    runtime_value = yaml.safe_load(runtime.read_text(encoding="utf-8"))
    runtime_value["package_id"] = "mail-writer"
    runtime_value["runtime"]["execution_policy"]["tool_use_completion"] = {
        "run_again": "required",
        "stop_on_tool": "disabled",
        "final_output": "default",
    }
    runtime_value["tools"] = [
        {
            "id": "mail_send",
            "label": "Send email",
            "tool_type": "external_api",
            "description_for_llm": "Send email.",
            "adapter": "host.mcp",
            "input_schema": {
                "type": "object",
                "properties": {
                    "recipient": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["recipient", "body"],
                "additionalProperties": False,
            },
            "side_effect": "write",
            "approval_required": True,
            "timeout": "runtime_default",
            "retry_policy": "none",
            "failure_behavior": "error",
        }
    ]
    runtime_value["nodes"][0]["available_tools"] = ["mail_send"]
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
            client,
            models=[profile.execution_model_id],
            is_local=True,
            model_id_mapping={profile.execution_model_id: profile.model_id},
            execution_profile_adapter_id=profile.adapter_id,
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
    result = host.invoke_saved(
        package_name=registration.workflow_id,
        prompt="Answer me.",
        workspace_files=(),
        dry_run=True,
        approval_broker=None,
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
            _Client(),
            models=[profile.execution_model_id],
            is_local=True,
            model_id_mapping={profile.execution_model_id: profile.model_id},
            execution_profile_adapter_id=profile.adapter_id,
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
    default_artifact = host.ingress_default_file(
        workflow_id=registration.workflow_id,
        path=document,
        now=NOW,
    )
    assert default_artifact.artifact_id.startswith("v1.")
    assert default_artifact.byte_count == len(b"document body")
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


def test_host_rejects_unsatisfied_requirement_before_file_ingress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_root = tmp_path / "packages"
    source = package_root / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
    descriptor = source / "workflow-descriptor.yaml"
    value = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
    value["workspace"]["accepted_input_types"] = ["text/plain"]
    value["task_invocation"]["allowed_artifact_roles"] = ["document"]
    contract = BUILTIN_CAPABILITY_CONTRACTS[0]
    requirement = CapabilityRequirement(
        contract.capability_id,
        contract.contract_version,
        contract.contract_digest,
        ("multimodal",),
    )
    requirements = CapabilityRequirements((requirement,))
    value["dar_runtime"]["required_version"] = "0.1.17"
    value["capability_requirements"] = {
        "format_version": 1,
        "required_capabilities": [requirement.to_mapping()],
        "capability_requirements_digest": requirements.digest,
        "bindings": {},
    }
    descriptor.write_text(yaml.safe_dump(value), encoding="utf-8")
    input_root = tmp_path / "input"
    input_root.mkdir()
    document = input_root / "document.txt"
    document.write_text("document body", encoding="utf-8")
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.host.create_local_adapter",
        lambda profile: OpenAIClientAdapter(
            _Client(),
            models=[profile.execution_model_id],
            is_local=True,
            model_id_mapping={profile.execution_model_id: profile.model_id},
            execution_profile_adapter_id=profile.adapter_id,
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
    provider_available = True
    available_catalog = CapabilityCatalog(
        (contract,),
        (
            CapabilityProvider(
                "private-test-provider",
                contract,
                conformance_passed=True,
                conformance_vector_ids=frozenset(
                    {
                        "requested_features",
                        "output_integrity",
                        "resource_limits",
                        "redacted_failure",
                    }
                ),
            ),
        ),
        availability_provider=lambda _provider: (
            ProviderAvailability.AVAILABLE
            if provider_available
            else ProviderAvailability.DISABLED
        ),
    )
    host._capability_catalog = available_catalog
    host._preparation._capability_catalog = available_catalog
    source_handle = host.select_package(source, now=NOW)
    registration = host.register(
        workflow_id="document-helper", package_source_handle=source_handle, now=NOW
    )
    provider_available = False
    assert host._workspace_ingress is not None
    monkeypatch.setattr(
        host._workspace_ingress,
        "ingress",
        lambda **_kwargs: pytest.fail("workspace file ingress was called"),
    )

    with pytest.raises(LocalWorkflowHostError, match="registration"):
        host.ingress_file(
            workflow_id=registration.workflow_id,
            path=document,
            role="document",
            media_type="text/plain",
            now=NOW,
        )

    host._profile = replace(
        host._profile,
        adapter_id="qwen25-vl-3b-floorplan-grpo-transformers-peft-adapter-v1",
    )
    monkeypatch.setattr(
        host._model_preparation,
        "prepare",
        lambda **_kwargs: pytest.fail("model preparation was called"),
    )
    with pytest.raises(LocalWorkflowHostError, match="saved package"):
        host.invoke_saved(
            package_name=registration.workflow_id,
            prompt="Answer the request.",
            workspace_files=(),
            dry_run=True,
            approval_broker=None,
            now=NOW,
        )
