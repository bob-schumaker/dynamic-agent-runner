"""Tests for DAR authoring's closed no-tool workflow runner."""

from __future__ import annotations

from dataclasses import replace
import json
import shutil
import socket
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier

import pytest
import yaml

from parity_support import install_parity_io_blocker

from dynamic_agent_runner.openai_client import (  # noqa: E402
    AsyncOpenAIClientAdapter,
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
from dynamic_agent_runner.workflow_host.profiles import (  # noqa: E402
    FASTMAIL_TRIAGE_LLAMA_CPP_ADAPTER_ID,
)
from dynamic_agent_runner.workflow_host.registration import WorkflowRegistrationService  # noqa: E402
from dynamic_agent_runner.workflow_host.runner import (  # noqa: E402
    RunDarWorkflowError,
    RunDarWorkflowRequest,
    WorkflowRunner,
)
from dynamic_agent_runner.workflow_host.staging import PrivatePackageStager  # noqa: E402
from dynamic_agent_runner.workflow_host.state import PrivateStateStore  # noqa: E402
from dynamic_agent_runner.workflow_host.workspace_ingress import (  # noqa: E402
    MaterializedWorkspaceImageArtifact,
    MaterializedWorkspaceInputArtifact,
)
import dynamic_agent_runner.workflow_host.runner as workflow_runner_module  # noqa: E402


NOW = datetime(2026, 8, 23, tzinfo=UTC)
TEMPLATE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "specs"
    / "agent-engineering-plugin-migration"
    / "legacy-dar-authoring"
    / "templates"
)


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


class AsyncFakeResponses:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> ModelResponse:
        self.calls.append(kwargs)
        return ModelResponse(content=self.content)


class AsyncFakeClient:
    def __init__(self, content: str) -> None:
        self.responses = AsyncFakeResponses(content)


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


class VisionArtifactVerifier:
    def load(
        self,
        artifact_id: str,
        *,
        workflow_id: str,
        registration_digest: str,
        now: datetime,
    ) -> object:
        if (
            artifact_id != "v1.source-image"
            or workflow_id != "document-helper"
            or not registration_digest
        ):
            raise ValueError("unexpected artifact")
        return object()

    def materialize_image(
        self,
        artifact_id: str,
        *,
        workflow_id: str,
        registration_digest: str,
        now: datetime,
    ) -> MaterializedWorkspaceImageArtifact:
        self.load(
            artifact_id,
            workflow_id=workflow_id,
            registration_digest=registration_digest,
            now=now,
        )
        return MaterializedWorkspaceImageArtifact(
            artifact_id,
            "sha256:" + "c" * 64,
            "source_image",
            "image/png",
            b"sealed-image-bytes",
        )


class VisionFakeAdapter(OpenAIClientAdapter):
    """Test-local adapter that records only DAR's sealed image handoff."""

    def __init__(self, client: FakeClient, *, model: str, adapter_id: str) -> None:
        super().__init__(
            client,
            models=(model,),
            is_local=True,
            execution_profile_adapter_id=adapter_id,
            model_id_mapping={model: model},
        )
        self.bound_images: list[tuple[bytes, str]] = []
        self.cleared = 0

    @property
    def capabilities(self) -> dict[str, bool]:
        return {"text_generation": True, "multimodal_input": True}

    def bind_sealed_image(self, *, content: bytes, media_type: str) -> None:
        self.bound_images.append((content, media_type))

    def clear_sealed_image(self) -> None:
        self.cleared += 1


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
        self.echo_arguments = False
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
        if self.echo_arguments:
            return {"content": [{"type": "text", "text": str(arguments["body"])}]}
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


class BrokenApprovalBroker:
    def __init__(self) -> None:
        self.actions: list[object] = []

    def decide(self, *, action: object, approval: object) -> LocalApprovalDecision:
        self.actions.append(action)
        raise RuntimeError("terminal is unavailable")


class InvalidApprovalBroker:
    def __init__(self) -> None:
        self.actions: list[object] = []

    def decide(self, *, action: object, approval: object) -> LocalApprovalDecision:
        self.actions.append(action)
        return "invalid"  # type: ignore[return-value]


class SequencedApprovalBroker:
    def __init__(self, *decisions: LocalApprovalDecision) -> None:
        self._decisions = iter(decisions)
        self.actions: list[object] = []

    def decide(self, *, action: object, approval: object) -> LocalApprovalDecision:
        self.actions.append(action)
        return next(self._decisions)


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
    hosted: bool = False,
    configured_adapter_id: str | None = None,
    async_adapter: bool = False,
    active_profile_id: str | None = None,
    active_apple_profile: bool = False,
    package_model: str = "local-model",
    terminal_required_field: str = "message",
    artifact_verifier: object | None = None,
    vision: bool = False,
):
    source = tmp_path / "packages" / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
    runtime_path = source / "agent-runtime.yaml"
    runtime = yaml.safe_load(runtime_path.read_text(encoding="utf-8"))
    runtime["runtime"]["execution_policy"]["model"] = package_model
    runtime["nodes"][0]["model"] = package_model
    runtime["output_contracts"][0]["required_fields"] = [terminal_required_field]
    runtime_path.write_text(yaml.safe_dump(runtime), encoding="utf-8")
    if hosted or vision:
        descriptor_path = source / "workflow-descriptor.yaml"
        descriptor = yaml.safe_load(descriptor_path.read_text(encoding="utf-8"))
        if hosted:
            descriptor["model"]["profile_requirement"] = "general-language-model-v1"
        if vision:
            descriptor["model"]["profile_requirement"] = "local-multimodal-model-v1"
            descriptor["workspace"]["accepted_input_types"] = ["image/png"]
            descriptor["task_invocation"]["allowed_artifact_roles"] = ["source_image"]
        descriptor_path.write_text(yaml.safe_dump(descriptor), encoding="utf-8")
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
    profile = (
        profiles.create_floorplan_vision_llama_cpp()
        if vision
        else (
            profiles.create_hosted_openai(
                model_id="local-model-v1",
                base_url="https://models.example.test/v1",
                capabilities={"text_generation"},
            )
            if hosted
            else profiles.create(
                model_id="local-model-v1",
                adapter_id="strict-local-adapter-v1",
                base_url="http://127.0.0.1:11434/v1",
                capabilities={"text_generation"},
            )
        )
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
            policy, available_capabilities=profile.capabilities
        ),
    )
    if active_apple_profile:
        active_profile_id = profiles.create_apple(model_id=profile.model_id).profile_id
    preparation = WorkflowInvocationPreparationService(
        registrations=registrations,
        catalog=catalog,
        store=store,
        artifact_verifier=artifact_verifier,  # type: ignore[arg-type]
    )
    client = (
        AsyncFakeClient("completed locally")
        if async_adapter
        else FakeClient("completed locally")
    )
    adapter = (
        VisionFakeAdapter(
            client, model=profile.execution_model_id, adapter_id=profile.adapter_id
        )
        if vision
        else (
            AsyncOpenAIClientAdapter(
                client,
                models=["local-model", "local-model-v1"],
                is_local=local,
                model_id_mapping={"local-model": "local-model-v1"},
                execution_profile_adapter_id=(
                    configured_adapter_id
                    or (
                        "apple-foundation-models-adapter-v1"
                        if active_apple_profile
                        else profile.adapter_id
                    )
                ),
            )
            if async_adapter
            else OpenAIClientAdapter(
                client,
                models=["local-model", "local-model-v1"],
                is_local=local,
                model_id_mapping={"local-model": "local-model-v1"},
                execution_profile_adapter_id=(
                    configured_adapter_id
                    or (
                        "apple-foundation-models-adapter-v1"
                        if active_apple_profile
                        else profile.adapter_id
                    )
                ),
            )
        )
    )
    return (
        WorkflowRunner(
            registrations=registrations,
            catalog=catalog,
            preparation=preparation,
            model_adapter=adapter,
            configured_profile=profiles.load(active_profile_id or profile.profile_id),
        ),
        preparation,
        registration,
        revision,
        client,
    )


def test_runner_rejects_an_image_workflow_for_a_text_only_profile(
    tmp_path: Path,
) -> None:
    runner, _, registration, _, _ = _runner(tmp_path)

    with pytest.raises(RunDarWorkflowError, match="multimodal"):
        runner.validate_artifact_capability(
            workflow_id=registration.workflow_id,
            input_kind="image_artifact",
        )


def _approval_runner(
    tmp_path: Path,
    *,
    responses: list[ModelResponse] | None = None,
    tool_loop: bool = False,
    max_total_tool_calls: int = 2,
    max_steps: int = 2,
):
    source = tmp_path / "packages" / "approval-runner"
    shutil.copytree(TEMPLATE_ROOT, source)
    descriptor_path = source / "workflow-descriptor.yaml"
    descriptor = yaml.safe_load(descriptor_path.read_text(encoding="utf-8"))
    descriptor["package_id"] = "approval-runner"
    descriptor["tools"] = [
        {
            "id": "create_record",
            "kind": "mcp",
            "remote_tool_name": "create_record",
            "side_effect": "write",
            "approval_required": True,
        },
        {
            "id": "delete_record",
            "kind": "mcp",
            "remote_tool_name": "delete_record",
            "side_effect": "delete",
            "approval_required": True,
        },
    ]
    descriptor["task_invocation"].update(
        {
            "allowed_tool_ids": ["create_record", "delete_record"],
            "max_total_tool_calls": max_total_tool_calls,
            "argument_sources": {
                "create_record": {
                    "title": {
                        "sources": ["cited_original_prompt_span"],
                        "authority": False,
                    },
                    "body": {
                        "sources": ["cited_original_prompt_span"],
                        "authority": False,
                    },
                },
                "delete_record": {
                    "record_id": {
                        "sources": ["cited_original_prompt_span"],
                        "authority": True,
                    }
                },
            },
        }
    )
    descriptor["limits"]["max_steps"] = max_steps

    descriptor_path.write_text(yaml.safe_dump(descriptor), encoding="utf-8")

    runtime_path = source / "agent-runtime.yaml"
    runtime = yaml.safe_load(runtime_path.read_text(encoding="utf-8"))
    runtime["package_id"] = "approval-runner"
    runtime["runtime"]["execution_policy"]["max_steps"] = max_steps
    if tool_loop:
        runtime["runtime"]["execution_policy"]["tool_use_completion"] = {
            "run_again": "required",
            "stop_on_tool": "disabled",
            "final_output": "default",
        }
    runtime["tools"] = [
        {
            "id": tool_id,
            "label": tool_id,
            "tool_type": "external_api",
            "description_for_llm": tool_id,
            "adapter": "host.mcp",
            "input_schema": {
                "type": "object",
                "properties": {"provenance_envelope": {"type": "string"}},
                "required": ["provenance_envelope"],
                "additionalProperties": False,
            },
            "side_effect": side_effect,
            "approval_required": False,
            "timeout": "runtime_default",
            "retry_policy": "none",
            "failure_behavior": "error",
        }
        for tool_id, side_effect in (
            ("create_record", "write"),
            ("delete_record", "delete"),
        )
    ]
    runtime["nodes"][0]["available_tools"] = ["create_record", "delete_record"]
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
        scopes={"records.write"},
        authentication_method="api_token",
    )
    authentication = connections.configure_api_token(connection.connection_id, "token")
    mcp_client = FakeMCPClient(
        connection.connection_id, authentication.authentication_id
    )
    mcp_client._tools = (
        MCPDiscoveredTool(
            name="create_record",
            input_schema={
                "type": "object",
                "properties": {"title": {"type": "string"}, "body": {"type": "string"}},
                "required": ["title", "body"],
                "additionalProperties": False,
            },
        ),
        MCPDiscoveredTool(
            name="delete_record",
            input_schema={
                "type": "object",
                "properties": {"record_id": {"type": "string"}},
                "required": ["record_id"],
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
        approved_read_only_tool_names=(),
        approved_tool_side_effects={
            "create_record": "write",
            "delete_record": "delete",
        },
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
        workflow_id="approval-runner",
        policy=policy,
        capability_resolution=resolve_capabilities(
            policy,
            available_capabilities={"text_generation", "mcp_side_effects"},
        ),
        mcp_binding_id=mcp_binding.binding_id,
    )
    preparation = WorkflowInvocationPreparationService(
        registrations=registrations, catalog=catalog, store=store
    )
    model_client = QueuedClient(responses or [ModelResponse(content="record ready")])
    adapter = OpenAIClientAdapter(
        model_client,
        models=["local-model", "local-model-v1"],
        is_local=True,
        model_id_mapping={"local-model": "local-model-v1"},
        execution_profile_adapter_id=profile.adapter_id,
    )
    ledger = WorkflowActionLedger(store=store, owner="local-os-user-v1:501:ada")
    return (
        WorkflowRunner(
            registrations=registrations,
            catalog=catalog,
            preparation=preparation,
            model_adapter=adapter,
            configured_profile=profile,
            mcp_bindings=mcp_bindings,
            mcp_client=mcp_client,
            mcp_surfaces=surfaces,
            action_ledger=ledger,
            approval_store=WorkflowApprovalStore(
                store=store, owner="local-os-user-v1:501:ada"
            ),
        ),
        preparation,
        mcp_client,
        model_client,
        policy,
        tmp_path / "state" / "records.json",
    )


def _approval_request(
    preparation: WorkflowInvocationPreparationService,
    prompt: str = "Create DAR record.",
):
    prepared = preparation.prepare(
        workflow_id="approval-runner", prompt=prompt, now=NOW
    )
    return RunDarWorkflowRequest.from_mapping(
        {
            "format_version": 1,
            "workflow_id": "approval-runner",
            "prepared_input_id": prepared.prepared_input_id,
        }
    )


def _create_record_response(
    *,
    title: str = "Create",
    body: str = "DAR",
    title_span: tuple[int, int] = (0, 6),
    body_span: tuple[int, int] = (7, 10),
) -> ModelResponse:
    envelope = {
        "format_version": 1,
        "arguments": {"title": title, "body": body},
        "sources": {
            "title": {
                "kind": "prompt_span",
                "start_byte": title_span[0],
                "end_byte": title_span[1],
                "normalization": "identity",
            },
            "body": {
                "kind": "prompt_span",
                "start_byte": body_span[0],
                "end_byte": body_span[1],
                "normalization": "identity",
            },
        },
    }
    return ModelResponse(
        content=None,
        tool_calls=(
            ModelToolCall(
                id="call_create",
                name="create_record",
                arguments=json.dumps(
                    {
                        "provenance_envelope": json.dumps(
                            envelope, sort_keys=True, separators=(",", ":")
                        )
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            ),
        ),
    )


def _delete_record_response() -> ModelResponse:
    envelope = {
        "format_version": 1,
        "arguments": {"record_id": "Delete"},
        "sources": {
            "record_id": {
                "kind": "prompt_span",
                "start_byte": 22,
                "end_byte": 28,
                "normalization": "identity",
            }
        },
    }
    return ModelResponse(
        content=None,
        tool_calls=(
            ModelToolCall(
                id="call_delete",
                name="delete_record",
                arguments=json.dumps(
                    {
                        "provenance_envelope": json.dumps(
                            envelope, sort_keys=True, separators=(",", ":")
                        )
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            ),
        ),
    )


def _tool_runner(
    tmp_path: Path,
    *,
    side_effect: bool = False,
    approval_required: bool = False,
    mixed: bool = False,
    approval_broker: LocalActionApprovalBroker | None = None,
    body_from_artifact: bool = False,
    body_composed_from_artifact: bool = False,
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
            **({"approval_required": approval_required} if side_effect else {}),
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
                                    else ["model_generated_transform"]
                                    if body_composed_from_artifact
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
    if mixed:
        descriptor["tools"] = [
            {
                "id": "mail_lookup",
                "kind": "mcp",
                "remote_tool_name": "list_unread",
                "side_effect": "read",
            },
            {
                "id": "mail_send",
                "kind": "mcp",
                "remote_tool_name": "send_email",
                "side_effect": "write",
                "approval_required": False,
            },
            {
                "id": "mail_delete",
                "kind": "mcp",
                "remote_tool_name": "delete_email",
                "side_effect": "delete",
                "approval_required": True,
            },
        ]
        descriptor["task_invocation"].update(
            {
                "allowed_tool_ids": ["mail_lookup", "mail_send", "mail_delete"],
                "max_total_tool_calls": 3,
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
                    },
                    "mail_delete": {
                        "message_id": {
                            "sources": ["cited_original_prompt_span"],
                            "authority": True,
                        }
                    },
                },
            }
        )
    if body_from_artifact or body_composed_from_artifact:
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
    if mixed:
        runtime["runtime"]["execution_policy"]["max_steps"] = 4
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
            "approval_required": approval_required if side_effect else False,
            "timeout": "runtime_default",
            "retry_policy": "none",
            "failure_behavior": "error",
        }
    ]
    runtime["nodes"][0]["available_tools"] = [tool_id]
    if mixed:
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
            },
            {
                "id": "mail_send",
                "label": "Send mail",
                "tool_type": "external_api",
                "description_for_llm": "Send mail.",
                "adapter": "host.mcp",
                "input_schema": {
                    "type": "object",
                    "properties": {"provenance_envelope": {"type": "string"}},
                    "required": ["provenance_envelope"],
                    "additionalProperties": False,
                },
                "side_effect": "write",
                "approval_required": False,
                "timeout": "runtime_default",
                "retry_policy": "none",
                "failure_behavior": "error",
            },
            {
                "id": "mail_delete",
                "label": "Delete mail",
                "tool_type": "external_api",
                "description_for_llm": "Delete mail.",
                "adapter": "host.mcp",
                "input_schema": {
                    "type": "object",
                    "properties": {"provenance_envelope": {"type": "string"}},
                    "required": ["provenance_envelope"],
                    "additionalProperties": False,
                },
                "side_effect": "delete",
                "approval_required": False,
                "timeout": "runtime_default",
                "retry_policy": "none",
                "failure_behavior": "error",
            },
        ]
        runtime["nodes"][0]["available_tools"] = [
            "mail_lookup",
            "mail_send",
            "mail_delete",
        ]
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
    if mixed:
        mcp_client._tools = (
            mcp_client._tools[0],
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
            MCPDiscoveredTool(
                name="delete_email",
                input_schema={
                    "type": "object",
                    "properties": {"message_id": {"type": "string"}},
                    "required": ["message_id"],
                    "additionalProperties": False,
                },
            ),
        )
    elif side_effect:
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
        approved_read_only_tool_names={"list_unread"}
        if not side_effect or mixed
        else (),
        approved_tool_side_effects=(
            {"send_email": "write", "delete_email": "delete"}
            if mixed
            else {"send_email": "write"}
            if side_effect
            else None
        ),
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
                {"text_generation", "mcp_read_only", "mcp_side_effects"}
                if mixed
                else {"text_generation", "mcp_side_effects"}
                if side_effect
                else {"text_generation", "mcp_read_only"}
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
        if side_effect or mixed
        else '{"folder":"inbox"}'
    )
    if body_composed_from_artifact:
        tool_arguments = json.dumps(
            {
                "provenance_envelope": json.dumps(
                    {
                        "arguments": {
                            "body": "Body from artifact",
                            "recipient": "ada@example.test",
                        },
                        "format_version": 1,
                        "sources": {
                            "body": {
                                "kind": "compose_content_v1",
                                "inputs": [{"kind": "artifact", "ref": "body"}],
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
    model_responses = [
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
    if mixed:
        model_responses = [
            ModelResponse(
                content=None,
                tool_calls=(
                    ModelToolCall(
                        id="call_1", name="mail_lookup", arguments='{"folder":"inbox"}'
                    ),
                ),
            ),
            ModelResponse(
                content=None,
                tool_calls=(
                    ModelToolCall(
                        id="call_2",
                        name="mail_send",
                        arguments=tool_arguments,
                    ),
                ),
            ),
            ModelResponse(
                content=None,
                tool_calls=(
                    ModelToolCall(
                        id="call_3",
                        name="mail_delete",
                        arguments=(
                            '{"provenance_envelope":"{\\"arguments\\":{\\"message_id\\":\\"first\\"},\\"format_version\\":1,\\"sources\\":{\\"message_id\\":{\\"end_byte\\":31,\\"kind\\":\\"prompt_span\\",\\"normalization\\":\\"identity\\",\\"start_byte\\":26}}}"}'
                        ),
                    ),
                ),
            ),
            ModelResponse(content="three mail actions completed"),
        ]
    model_client = QueuedClient(model_responses)
    adapter = OpenAIClientAdapter(
        model_client,
        models=["local-model", "local-model-v1"],
        is_local=True,
        model_id_mapping={"local-model": "local-model-v1"},
        execution_profile_adapter_id=profile.adapter_id,
    )
    return (
        WorkflowRunner(
            registrations=registrations,
            catalog=catalog,
            preparation=preparation,
            model_adapter=adapter,
            configured_profile=profile,
            mcp_bindings=mcp_bindings,
            mcp_client=mcp_client,
            mcp_surfaces=surfaces,
            action_ledger=(
                WorkflowActionLedger(store=store, owner="local-os-user-v1:501:ada")
                if side_effect or mixed
                else None
            ),
            approval_store=(
                WorkflowApprovalStore(store=store, owner="local-os-user-v1:501:ada")
                if side_effect or mixed
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


def test_runner_sync_wrapper_executes_an_injected_async_adapter(tmp_path: Path) -> None:
    runner, preparation, _, _, client = _runner(tmp_path, async_adapter=True)
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

    assert result.output == {"message": "completed locally"}
    assert len(client.responses.calls) == 1


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


def test_runner_delivers_one_declared_sealed_image_only_to_the_vision_adapter(
    tmp_path: Path,
) -> None:
    runner, preparation, registration, _, client = _runner(
        tmp_path,
        vision=True,
        package_model="qwen25-vl-3b-floorplan-grpo",
        artifact_verifier=VisionArtifactVerifier(),
    )
    prepared = preparation.prepare(
        workflow_id=registration.workflow_id,
        prompt="Create a floorplan.",
        workspace_artifact_ids=("v1.source-image",),
        now=NOW,
    )

    result = runner.run(
        RunDarWorkflowRequest.from_mapping(
            {
                "format_version": 1,
                "workflow_id": registration.workflow_id,
                "prepared_input_id": prepared.prepared_input_id,
            }
        ),
        now=NOW,
    )

    adapter = runner._model_adapter
    assert isinstance(adapter, VisionFakeAdapter)
    assert result.output == {"message": "completed locally"}
    assert adapter.bound_images == [(b"sealed-image-bytes", "image/png")]
    assert adapter.cleared == 1
    assert "sealed-image-bytes" not in repr(client.responses.calls)
    assert "v1.source-image" not in repr(runner.traces())


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


def test_fastmail_terminal_output_rejects_raw_projected_messages() -> None:
    raw_projection = json.dumps(
        {
            "status": "complete",
            "window": "previous_24_hours",
            "matched_count": 1,
            "truncated": False,
            "items": [
                {
                    "message_reference": "opaque-1",
                    "subject": "Synthetic message",
                    "sender": "synthetic@example.invalid",
                    "received_at": "2026-09-05T00:00:00Z",
                    "preview": "Synthetic preview",
                }
            ],
            "warnings": [],
        }
    )

    with pytest.raises(RunDarWorkflowError, match="terminal output"):
        workflow_runner_module._terminal_output(
            raw_projection,
            {"required_fields": ["message"]},
            adapter_id=FASTMAIL_TRIAGE_LLAMA_CPP_ADAPTER_ID,
        )


def test_fastmail_terminal_output_normalizes_a_classified_report() -> None:
    report = json.dumps(
        {
            "status": "complete",
            "window": "previous_24_hours",
            "matched_count": 1,
            "truncated": False,
            "items": [
                {
                    "message_reference": "opaque-1",
                    "subject": "Synthetic message",
                    "classification": "needs_reply",
                    "rationale": "A response is requested.",
                    "sender": "synthetic@example.invalid",
                    "received_at": "2026-09-05T00:00:00Z",
                    "preview": "Synthetic preview",
                }
            ],
            "warnings": [],
        }
    )

    output = workflow_runner_module._terminal_output(
        report,
        {"required_fields": ["message"]},
        adapter_id=FASTMAIL_TRIAGE_LLAMA_CPP_ADAPTER_ID,
    )

    assert json.loads(output["message"])["items"] == [
        {
            "message_reference": "opaque-1",
            "subject": "Synthetic message",
            "classification": "needs_reply",
            "rationale": "A response is requested.",
        }
    ]


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


def test_runner_ignores_a_broker_for_declared_auto_policy(
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
    assert broker.actions == []
    assert mcp_client.calls == [
        ("send_email", {"recipient": "ada@example.test", "body": "Welcome!"})
    ]


def test_runner_dispatches_declared_approval_policy_through_its_broker(
    tmp_path: Path,
) -> None:
    broker = FakeApprovalBroker(LocalApprovalDecision.APPROVED)
    runner, preparation, mcp_client, _ = _tool_runner(
        tmp_path, side_effect=True, approval_required=True
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


def test_runner_materializes_wrapper_approval_binding_without_external_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_parity_io_blocker(monkeypatch)
    with pytest.raises(AssertionError, match="external I/O"):
        socket.create_connection(("example.invalid", 443))

    captured_bindings: list[object] = []
    create_registry = workflow_runner_module.create_host_tool_registry

    def capture_bindings(bindings: object):
        captured_bindings.extend(bindings)  # type: ignore[arg-type]
        return create_registry(bindings)  # type: ignore[arg-type]

    monkeypatch.setattr(
        workflow_runner_module, "create_host_tool_registry", capture_bindings
    )
    broker = FakeApprovalBroker(LocalApprovalDecision.APPROVED)
    runner, preparation, mcp_client, model_client, policy, _ = _approval_runner(
        tmp_path
    )
    prepared = preparation.prepare(
        workflow_id="approval-runner", prompt="Create DAR record.", now=NOW
    )

    result = runner.run(
        RunDarWorkflowRequest.from_mapping(
            {
                "format_version": 1,
                "workflow_id": "approval-runner",
                "prepared_input_id": prepared.prepared_input_id,
            }
        ),
        now=NOW,
        approval_broker=broker,
    )

    approval_bindings = [
        binding
        for binding in captured_bindings
        if getattr(binding, "model_id", None) == "create_record"
    ]
    assert result.status == "completed"
    assert [tool.approval_required for tool in policy.declared_tools] == [True, True]
    assert len(approval_bindings) == 1
    assert approval_bindings[0].canonical_id.startswith("authorized-mcp:")
    assert approval_bindings[0].approval_required == "no"
    assert {binding.model_id for binding in captured_bindings} == {
        "create_record",
        "delete_record",
    }
    assert broker.actions == []
    assert mcp_client.calls == []
    assert len(model_client.responses.calls) == 1


def test_runner_requires_an_approval_broker_before_consuming_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_parity_io_blocker(monkeypatch)
    runner, preparation, mcp_client, model_client, _, records_path = _approval_runner(
        tmp_path
    )

    request = _approval_request(preparation)
    with pytest.raises(RunDarWorkflowError, match="local approval is unavailable"):
        runner.run(request, now=NOW)

    assert mcp_client.calls == []
    assert model_client.responses.calls == []
    assert "workflow_action_intent" not in records_path.read_text(encoding="utf-8")
    assert (
        runner.run(
            request,
            now=NOW,
            approval_broker=FakeApprovalBroker(LocalApprovalDecision.APPROVED),
        ).status
        == "completed"
    )


def test_runner_dispatches_create_record_once_after_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_parity_io_blocker(monkeypatch)
    broker = FakeApprovalBroker(LocalApprovalDecision.APPROVED)
    runner, preparation, mcp_client, model_client, _, records_path = _approval_runner(
        tmp_path,
        responses=[_create_record_response(), ModelResponse(content="record ready")],
        tool_loop=True,
    )

    result = runner.run(_approval_request(preparation), now=NOW, approval_broker=broker)

    assert result.status == "completed"
    assert len(model_client.responses.calls) == 2
    assert len(broker.actions) == 1
    assert mcp_client.calls == [("create_record", {"title": "Create", "body": "DAR"})]
    assert '"status":"completed"' in records_path.read_text(encoding="utf-8")


def test_runner_grants_rest_of_run_only_to_the_same_declared_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_parity_io_blocker(monkeypatch)
    broker = SequencedApprovalBroker(
        LocalApprovalDecision.APPROVED_FOR_REST_OF_RUN,
        LocalApprovalDecision.DENIED,
        LocalApprovalDecision.DENIED,
    )
    runner, preparation, mcp_client, _, _, records_path = _approval_runner(
        tmp_path,
        responses=[
            _create_record_response(),
            _create_record_response(
                title="Again", body="More", title_span=(11, 16), body_span=(17, 21)
            ),
            _delete_record_response(),
            _create_record_response(),
        ],
        tool_loop=True,
        max_total_tool_calls=3,
        max_steps=4,
    )

    with pytest.raises(RunDarWorkflowError, match="DAR workflow execution failed"):
        runner.run(
            _approval_request(preparation, "Create DAR Again More Delete"),
            now=NOW,
            approval_broker=broker,
        )

    assert len(broker.actions) == 2
    assert [action.remote_tool_name for action in broker.actions] == [
        "create_record",
        "delete_record",
    ]
    assert mcp_client.calls == [
        ("create_record", {"title": "Create", "body": "DAR"}),
        ("create_record", {"title": "Again", "body": "More"}),
    ]
    assert '"status":"denied"' in records_path.read_text(encoding="utf-8")

    with pytest.raises(RunDarWorkflowError, match="DAR workflow execution failed"):
        runner.run(_approval_request(preparation), now=NOW, approval_broker=broker)

    assert len(broker.actions) == 3
    assert broker.actions[-1].remote_tool_name == "create_record"
    assert len(mcp_client.calls) == 2


@pytest.mark.parametrize(
    ("broker", "terminal_status"),
    [
        (FakeApprovalBroker(LocalApprovalDecision.DENIED), "denied"),
        (FakeApprovalBroker(LocalApprovalDecision.CANCELLED), "cancelled"),
        (InvalidApprovalBroker(), "failed"),
        (BrokenApprovalBroker(), "failed"),
    ],
)
def test_runner_records_terminal_receipt_without_dispatch_when_approval_fails(
    tmp_path: Path,
    broker: LocalActionApprovalBroker,
    terminal_status: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_parity_io_blocker(monkeypatch)
    runner, preparation, mcp_client, model_client, _, records_path = _approval_runner(
        tmp_path, responses=[_create_record_response()], tool_loop=True
    )

    with pytest.raises(RunDarWorkflowError, match="DAR workflow execution failed"):
        runner.run(_approval_request(preparation), now=NOW, approval_broker=broker)

    assert len(model_client.responses.calls) == 1
    assert len(getattr(broker, "actions", ())) == 1
    assert mcp_client.calls == []
    records = records_path.read_text(encoding="utf-8")
    assert '"kind":"workflow_action_intent"' in records
    assert '"kind":"workflow_action_terminal"' in records
    assert f'"status":"{terminal_status}"' in records


def test_runner_keeps_mixed_read_write_delete_policies_separate(
    tmp_path: Path,
) -> None:
    broker = FakeApprovalBroker(LocalApprovalDecision.APPROVED)
    runner, preparation, mcp_client, _ = _tool_runner(tmp_path, mixed=True)
    prepared = preparation.prepare(
        workflow_id="mail-reader", prompt="ada@example.test\nWelcome!\nfirst", now=NOW
    )
    request = RunDarWorkflowRequest.from_mapping(
        {
            "format_version": 1,
            "workflow_id": "mail-reader",
            "prepared_input_id": prepared.prepared_input_id,
        }
    )

    assert runner.dry_run(request, now=NOW).status == "ready"
    result = runner.run(request, now=NOW, approval_broker=broker)

    assert result.status == "completed"
    assert len(broker.actions) == 1
    assert mcp_client.calls == [
        ("list_unread", {"folder": "inbox"}),
        ("send_email", {"recipient": "ada@example.test", "body": "Welcome!"}),
        ("delete_email", {"message_id": "first"}),
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
    mcp_client.echo_arguments = True
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
    assert (
        model_client.responses.calls[1]["input"][-1]["content"]
        == '{"status": "artifact_result_redacted"}'
    )


def test_runner_redacts_composed_artifact_provenance_from_the_model(
    tmp_path: Path,
) -> None:
    runner, preparation, mcp_client, model_client = _tool_runner(
        tmp_path,
        side_effect=True,
        body_composed_from_artifact=True,
        artifact_verifier=BodyArtifactVerifier(),
    )
    mcp_client.echo_arguments = True
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
    follow_up_input = model_client.responses.calls[1]["input"]
    assert follow_up_input[-2]["tool_calls"][0]["function"]["arguments"] == "{}"
    assert follow_up_input[-1]["content"] == '{"status": "artifact_result_redacted"}'


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


def test_side_effecting_prepared_input_has_one_concurrent_consumer(
    tmp_path: Path,
) -> None:
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
    barrier = Barrier(2)

    def consume_once() -> str:
        barrier.wait()
        try:
            return runner.run(request, now=NOW).status
        except RunDarWorkflowError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _index: consume_once(), range(2)))

    assert sorted(outcomes) == ["completed", "rejected"]
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


def test_runner_rejects_adapter_profile_mismatch_before_consuming_input(
    tmp_path: Path,
) -> None:
    runner, preparation, registration, _, client = _runner(
        tmp_path, configured_adapter_id="hosted-openai-adapter-v1"
    )
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

    with pytest.raises(RunDarWorkflowError, match="does not match profile"):
        runner.run(request, now=NOW)

    assert (
        preparation.load(
            prepared.prepared_input_id, registration=registration, now=NOW
        ).prompt
        == "Answer me."
    )
    assert client.responses.calls == []


def test_runner_admits_matching_hosted_adapter_before_consuming_input(
    tmp_path: Path,
) -> None:
    runner, preparation, _, _, client = _runner(tmp_path, local=False, hosted=True)
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

    result = runner.run(request, now=NOW)

    assert result.status == "completed"
    assert client.responses.calls
    assert client.responses.calls[0]["model"] == "local-model-v1"


def test_runner_rejects_execution_alias_resolution_drift_before_consuming_input(
    tmp_path: Path,
) -> None:
    runner, preparation, registration, _, client = _runner(tmp_path, hosted=True)
    runner._model_adapter._model_id_mapping["local-model"] = "other-model-v1"  # noqa: SLF001
    prepared = preparation.prepare(
        workflow_id="document-helper", prompt="Answer me.", now=NOW
    )

    with pytest.raises(RunDarWorkflowError, match="does not resolve registered model"):
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

    assert (
        preparation.load(
            prepared.prepared_input_id, registration=registration, now=NOW
        ).prompt
        == "Answer me."
    )
    assert client.responses.calls == []


def test_runner_rejects_profile_digest_drift_before_consuming_input(
    tmp_path: Path,
) -> None:
    runner, preparation, registration, _, client = _runner(tmp_path)
    runner._configured_profile = replace(  # noqa: SLF001 - admission boundary seam.
        runner._configured_profile, profile_digest="d" * 64
    )
    prepared = preparation.prepare(
        workflow_id="document-helper", prompt="Answer me.", now=NOW
    )

    with pytest.raises(RunDarWorkflowError, match="does not match registration"):
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

    assert (
        preparation.load(
            prepared.prepared_input_id, registration=registration, now=NOW
        ).prompt
        == "Answer me."
    )
    assert client.responses.calls == []


def test_runner_rejects_adapter_capability_drift_before_consuming_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        OpenAIClientAdapter,
        "capabilities",
        property(lambda _adapter: {}),
    )
    runner, preparation, registration, _, client = _runner(tmp_path)
    prepared = preparation.prepare(
        workflow_id="document-helper", prompt="Answer me.", now=NOW
    )

    with pytest.raises(RunDarWorkflowError, match="adapter lacks text_generation"):
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

    assert (
        preparation.load(
            prepared.prepared_input_id, registration=registration, now=NOW
        ).prompt
        == "Answer me."
    )
    assert client.responses.calls == []


def test_runner_rejects_same_alias_cross_profile_before_consuming_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.profiles.preflight_apple_foundation_models",
        lambda: None,
    )
    runner, preparation, registration, _, client = _runner(
        tmp_path, active_apple_profile=True
    )
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

    with pytest.raises(RunDarWorkflowError, match="configured profile"):
        runner.run(request, now=NOW)

    assert (
        preparation.load(
            prepared.prepared_input_id, registration=registration, now=NOW
        ).prompt
        == "Answer me."
    )
    assert client.responses.calls == []


def test_runner_uses_strict_coverage_before_model_fallback(tmp_path: Path) -> None:
    runner, preparation, _, _, client = _runner(
        tmp_path, package_model="unadvertised-local-model"
    )
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

    with pytest.raises(RunDarWorkflowError, match="DAR workflow execution failed"):
        runner.run(request, now=NOW)

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
