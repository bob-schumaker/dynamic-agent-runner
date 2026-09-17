"""Tests for DAR authoring's closed no-tool workflow runner."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
import shutil
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
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
from dynamic_agent_runner.workflow_host.capabilities import (  # noqa: E402
    BUILTIN_CAPABILITY_CONTRACTS,
    CapabilityCatalog,
    CapabilityContract,
    CapabilityProvider,
    CapabilityRequirement,
    CapabilityRequirements,
    ProviderAvailability,
    ReviewedCapabilityTemplate,
    ReviewedCapabilityTemplateOutput,
    reviewed_capability_template_digest,
)
from dynamic_agent_runner.workflow_host.action_ledger import (  # noqa: E402
    ExternalAction,
    WorkflowActionLedger,
)
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
from dynamic_agent_runner.workflow_host.model_execution_binding import (  # noqa: E402
    ModelExecutionBinding,
    ModelRunnerProvider,
    ModelRunnerRegistry,
)
from dynamic_agent_runner.workflow_host.descriptor import (  # noqa: E402
    DeclaredArtifactTool,
    DeclaredLocalTool,
    DeclaredReviewedCapabilityTool,
    DeclaredTerminalOutputProcessor,
    DeclaredTerminalOutputValidator,
)
from dynamic_agent_runner.workflow_host.execution_descriptors import (  # noqa: E402
    ExecutionDescriptor,
    ExecutionDescriptorAbi,
    ExecutionDescriptorValidatorRegistry,
)
from dynamic_agent_runner.workflow_host.generation_resource_budgets import (  # noqa: E402
    GenerationBudgetDescriptorValidator,
    GenerationExecutionHostPolicy,
    GenerationResourceBudget,
)
from dynamic_agent_runner.workflow_host.host import LocalWorkflowHost  # noqa: E402
from dynamic_agent_runner.workflow_host.reviewed_tool_packages import (  # noqa: E402
    ReviewedCapabilityTemplateControlPlane,
    ReviewedToolPackageBinding,
    ReviewedToolPackageControlPlane,
)
from dynamic_agent_runner.workflow_host.reviewed_capability_host_extension import (  # noqa: E402
    ReviewedCapabilityHostExtension,
)
from dynamic_agent_runner.workflow_host.reviewed_capability_execution import (  # noqa: E402
    ReviewedCapabilityHostResult,
)
from dynamic_agent_runner.workflow_host.reviewed_capability_jobs import (  # noqa: E402
    SealedReviewedCapabilityJob,
)
from dynamic_agent_runner.workflow_host.reviewed_capability_outputs import (  # noqa: E402
    ReviewedCapabilityCandidateOutput,
    ReviewedCapabilityHostContribution,
)
from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (  # noqa: E402
    SealedArtifactOutputHandleService,
)
from dynamic_agent_runner.workflow_host.registration import WorkflowRegistrationService  # noqa: E402
from dynamic_agent_runner.workflow_host.runner import (  # noqa: E402
    RunDarWorkflowError,
    RunDarWorkflowRequest,
    TerminalProcessorDiagnostic,
    WorkflowRunner,
)
from dynamic_agent_runner.workflow_host.staging import PrivatePackageStager  # noqa: E402
from dynamic_agent_runner.workflow_host.state import PrivateStateStore  # noqa: E402
from dynamic_agent_runner.workflow_host.workspace_ingress import (  # noqa: E402
    MaterializedWorkspaceBinaryArtifact,
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


class ConverterArtifactVerifier(VisionArtifactVerifier):
    def materialize_binary(
        self,
        artifact_id: str,
        *,
        workflow_id: str,
        registration_digest: str,
        now: datetime,
    ) -> MaterializedWorkspaceBinaryArtifact:
        self.load(
            artifact_id,
            workflow_id=workflow_id,
            registration_digest=registration_digest,
            now=now,
        )
        return MaterializedWorkspaceBinaryArtifact(
            artifact_id,
            "sha256:" + "f" * 64,
            "source_image",
            "image/png",
            b"sealed-image-bytes",
        )


class BinaryArtifactVerifier(ArtifactVerifier):
    def materialize_binary(
        self,
        artifact_id: str,
        *,
        workflow_id: str,
        registration_digest: str,
        now: datetime,
    ) -> MaterializedWorkspaceBinaryArtifact:
        self.load(
            artifact_id,
            workflow_id=workflow_id,
            registration_digest=registration_digest,
            now=now,
        )
        return MaterializedWorkspaceBinaryArtifact(
            artifact_id,
            "sha256:" + "d" * 64,
            "source_binary",
            "application/octet-stream",
            b"sealed binary",
        )


class OpaqueBinaryArtifactVerifier(ArtifactVerifier):
    def materialize_binary(
        self,
        artifact_id: str,
        *,
        workflow_id: str,
        registration_digest: str,
        now: datetime,
    ) -> MaterializedWorkspaceBinaryArtifact:
        self.load(
            artifact_id,
            workflow_id=workflow_id,
            registration_digest=registration_digest,
            now=now,
        )
        return MaterializedWorkspaceBinaryArtifact(
            artifact_id,
            "sha256:" + "e" * 64,
            "opaque_binary_artifact",
            "application/octet-stream",
            b"sealed network capture",
        )


class ReviewedPacketExecutor:
    def __init__(self, binding: ReviewedToolPackageBinding) -> None:
        self.binding = binding
        self.references: list[object] = []

    def execute(self, *, tool_id: str, artifact: object, reader: object) -> object:
        assert tool_id == "packet_summary"
        self.references.append(artifact)
        return {"packet_count": len(reader.read(artifact))}  # type: ignore[attr-defined]


class VisionFakeAdapter(OpenAIClientAdapter):
    """Test-local adapter that records only DAR's sealed image handoff."""

    def __init__(
        self,
        client: FakeClient,
        *,
        model: str,
        adapter_id: str,
        json_mode: bool = False,
    ) -> None:
        super().__init__(
            client,
            models=(model,),
            is_local=True,
            execution_profile_adapter_id=adapter_id,
            model_id_mapping={model: model},
        )
        self._json_mode = json_mode
        self.bound_images: list[tuple[bytes, str]] = []
        self.cleared = 0
        self._debug_fragment_recorder: object | None = None
        self.debug_error: BaseException | None = None

    @property
    def capabilities(self) -> dict[str, bool]:
        return {
            "text_generation": True,
            "multimodal_input": True,
            "json_mode": self._json_mode,
        }

    def bind_sealed_image(self, *, content: bytes, media_type: str) -> None:
        self.bound_images.append((content, media_type))

    def clear_sealed_image(self) -> None:
        self.cleared += 1

    def set_debug_fragment_recorder(self, recorder: object | None) -> None:
        self._debug_fragment_recorder = recorder

    def create_response(self, request: object) -> ModelResponse:
        response = super().create_response(request)  # type: ignore[arg-type]
        recorder = self._debug_fragment_recorder
        if callable(recorder) and isinstance(response.content, str):
            recorder(
                type(
                    "GeneratedFragment",
                    (),
                    {
                        "content": response.content,
                        "exhausted": False,
                        "generated_tokens": len(response.content),
                    },
                )()
            )
        if self.debug_error is not None:
            raise self.debug_error
        return response


class ConverterFakeAdapter(VisionFakeAdapter):
    """Test-local adapter that records only the converter payload handoff."""

    def __init__(
        self,
        client: FakeClient,
        *,
        model: str,
        adapter_id: str,
        json_mode: bool = False,
    ) -> None:
        super().__init__(
            client, model=model, adapter_id=adapter_id, json_mode=json_mode
        )
        self.bound_payloads: list[bytes] = []
        self.bound_converters: list[tuple[Path, object]] = []
        self.converter_error: Exception | None = None
        self.payload_cleared = 0
        self.bound_generation_budgets: list[tuple[object, str, object]] = []
        self.input_converter_contract_id = "transformers-generate-v1"

    def bind_generation_budget(
        self, *, descriptor: object, material_lock_digest: str, host_policy: object
    ) -> None:
        self.bound_generation_budgets.append(
            (descriptor, material_lock_digest, host_policy)
        )

    def bind_input_converter(self, *, package_root: Path, converter: object) -> None:
        if self.converter_error is not None:
            raise self.converter_error
        self.bound_converters.append((package_root, converter))

    def bind_sealed_payload(self, *, content: bytes) -> None:
        self.bound_payloads.append(content)

    def clear_sealed_payload(self) -> None:
        self.payload_cleared += 1


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
    input_converter: bool = False,
    local_asset: bool = False,
    local_tool_executor: object | None = None,
    terminal_validator: bool = False,
    response_format: dict[str, object] | None = None,
    json_mode: bool = False,
    response_content: str = "completed locally",
    reviewed_tool_packages: ReviewedToolPackageControlPlane | None = None,
    reviewed_artifact_tool_executors: object | None = None,
    capability_catalog: CapabilityCatalog | None = None,
    with_capability_requirements: bool = False,
    v2_converter_budget: bool = True,
):
    source = tmp_path / "packages" / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
    runtime_path = source / "agent-runtime.yaml"
    runtime = yaml.safe_load(runtime_path.read_text(encoding="utf-8"))
    runtime["runtime"]["execution_policy"]["model"] = package_model
    runtime["nodes"][0]["model"] = package_model
    if response_format is not None:
        runtime["nodes"][0]["response_format"] = response_format
    runtime["output_contracts"][0]["required_fields"] = [terminal_required_field]
    runtime_path.write_text(yaml.safe_dump(runtime), encoding="utf-8")
    if local_asset or terminal_validator:
        asset = source / "tools" / "inspect"
        asset.parent.mkdir()
        asset.write_text("placeholder", encoding="utf-8")
    if hosted or vision or input_converter or with_capability_requirements:
        descriptor_path = source / "workflow-descriptor.yaml"
        descriptor = yaml.safe_load(descriptor_path.read_text(encoding="utf-8"))
        if hosted:
            descriptor["model"]["profile_requirement"] = "general-language-model-v1"
        if vision:
            descriptor["model"]["profile_requirement"] = "local-multimodal-model-v1"
            descriptor["workspace"]["accepted_input_types"] = ["image/png"]
            descriptor["task_invocation"]["allowed_artifact_roles"] = ["source_image"]
        if input_converter:
            converter = source / "assets" / "qwen_converter.py"
            converter.parent.mkdir()
            converter.write_text("trusted fixture", encoding="utf-8")
            descriptor["input_converter"] = {
                "converter_id": "qwen25-vl-3b-grpo-input-v1",
                "converter_contract_version": "v1",
                "compatible_runner_contract_id": "transformers-generate-v1",
                "entrypoint": "assets/qwen_converter.py",
                "asset_digest": sha256(converter.read_bytes()).hexdigest(),
                "declared_resource_limits": {
                    "max_input_bytes": 8 * 1024 * 1024,
                    "max_output_bytes": 32 * 1024 * 1024,
                    "timeout_seconds": 1,
                },
            }
        if with_capability_requirements:
            contract = BUILTIN_CAPABILITY_CONTRACTS[0]
            requirement = CapabilityRequirement(
                contract.capability_id,
                contract.contract_version,
                contract.contract_digest,
                ("multimodal",),
            )
            requirements = CapabilityRequirements((requirement,))
            descriptor["dar_runtime"]["required_version"] = "0.1.18"
            descriptor["capability_requirements"] = {
                "format_version": 1,
                "required_capabilities": [requirement.to_mapping()],
                "capability_requirements_digest": requirements.digest,
                "bindings": {},
            }
        descriptor_path.write_text(yaml.safe_dump(descriptor), encoding="utf-8")
    v2_fixture = _v2_converter_budget_fixture(
        source, enabled=input_converter and v2_converter_budget
    )
    if terminal_validator:
        descriptor_path = source / "workflow-descriptor.yaml"
        descriptor = yaml.safe_load(descriptor_path.read_text(encoding="utf-8"))
        descriptor["output"]["validator"] = {
            "asset_path": "tools/inspect",
            "max_output_bytes": 512,
            "timeout_seconds": 1,
        }
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
    (
        effective_capability_catalog,
        descriptor_validators,
        model_runner_registry,
        generation_execution_host_policy,
    ) = _v2_runtime_dependencies(
        v2_fixture, fallback_capability_catalog=capability_catalog
    )
    policy = compile_workflow_policy(
        revision,
        capability_catalog=effective_capability_catalog,
        descriptor_validators=descriptor_validators,
    )
    profiles = LocalModelProfileControlPlane(store=store)
    profile = (
        profiles.create_hosted_openai(
            model_id="local-model-v1",
            base_url="https://models.example.test/v1",
            capabilities={"text_generation"},
        )
        if hosted
        else profiles.create(
            model_id=package_model if vision else "local-model-v1",
            adapter_id="strict-local-adapter-v1",
            base_url="http://127.0.0.1:11434/v1",
            execution_model_id=package_model if vision else "local-model",
            profile_requirement=(
                "local-multimodal-model-v1" if vision else "local-general-model"
            ),
            capabilities=(
                {"text_generation", "multimodal_input"}
                if vision
                else {"text_generation"}
            ),
        )
    )
    registrations = WorkflowRegistrationService(
        profiles=profiles,
        configured_profile_id=profile.profile_id,
        root=tmp_path / "registrations",
        model_recipe_digest_provider=lambda _profile: "a" * 64,
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
        capability_catalog=effective_capability_catalog,
        descriptor_validators=descriptor_validators,
    )
    client = (
        AsyncFakeClient(response_content)
        if async_adapter
        else FakeClient(response_content)
    )
    adapter = (
        (
            ConverterFakeAdapter(
                client,
                model=profile.execution_model_id,
                adapter_id=profile.adapter_id,
                json_mode=json_mode,
            )
            if input_converter
            else VisionFakeAdapter(
                client,
                model=profile.execution_model_id,
                adapter_id=profile.adapter_id,
                json_mode=json_mode,
            )
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
    runner = WorkflowRunner(
        registrations=registrations,
        catalog=catalog,
        preparation=preparation,
        model_adapter=adapter,
        configured_profile=profiles.load(active_profile_id or profile.profile_id),
        local_tool_executor=local_tool_executor,  # type: ignore[arg-type]
        reviewed_tool_packages=reviewed_tool_packages,
        reviewed_artifact_tool_executors=reviewed_artifact_tool_executors,  # type: ignore[arg-type]
        terminal_diagnostic_store=store,
        terminal_diagnostic_owner="test-local-user",
        capability_catalog=effective_capability_catalog,
        model_runner_registry=model_runner_registry,
        descriptor_validators=descriptor_validators,
        generation_execution_host_policy=generation_execution_host_policy,
    )
    _configure_legacy_generation_budget_fixture(runner, v2_fixture)
    return (
        runner,
        preparation,
        registration,
        revision,
        client,
    )


@dataclass(frozen=True)
class _V2ConverterBudgetFixture:
    capability_catalog: CapabilityCatalog
    descriptor_validators: ExecutionDescriptorValidatorRegistry
    model_runner_registry: ModelRunnerRegistry
    host_policy: GenerationExecutionHostPolicy


def _v2_runtime_dependencies(
    fixture: _V2ConverterBudgetFixture | None,
    *,
    fallback_capability_catalog: CapabilityCatalog | None,
) -> tuple[
    CapabilityCatalog | None,
    ExecutionDescriptorValidatorRegistry | None,
    ModelRunnerRegistry | None,
    GenerationExecutionHostPolicy | None,
]:
    if fixture is None:
        return fallback_capability_catalog, None, None, None
    return (
        fixture.capability_catalog,
        fixture.descriptor_validators,
        fixture.model_runner_registry,
        fixture.host_policy,
    )


def _v2_converter_budget_fixture(
    source: Path, *, enabled: bool
) -> _V2ConverterBudgetFixture | None:
    if not enabled:
        return None
    return _install_v2_converter_budget_fixture(source)


def _install_v2_converter_budget_fixture(source: Path) -> _V2ConverterBudgetFixture:
    budget = GenerationResourceBudget(
        max_new_tokens_per_fragment=4,
        max_continuations=1,
        max_total_generated_tokens=8,
        max_total_output_bytes=64,
        max_effective_context_tokens=8,
        max_runtime_milliseconds=1_000,
        max_memory_bytes=1_024,
    )
    abi = ExecutionDescriptorAbi("test-generation-v1", "1", "a" * 64)
    execution_descriptor = ExecutionDescriptor(
        abi,
        ("weights",),
        {"generation_budget": asdict(budget)},
    )
    runner_contract = CapabilityContract("model.execution.test.v1", "1", "b" * 64, ())
    converter_contract = CapabilityContract(
        "model.converter.test.v1", "1", "c" * 64, ()
    )
    requirements = CapabilityRequirements(
        (
            CapabilityRequirement(
                converter_contract.capability_id,
                converter_contract.contract_version,
                converter_contract.contract_digest,
                (),
            ),
            CapabilityRequirement(
                runner_contract.capability_id,
                runner_contract.contract_version,
                runner_contract.contract_digest,
                (),
            ),
        ),
        {
            "converter": converter_contract.capability_id,
            "runner": runner_contract.capability_id,
        },
    )
    descriptor_path = source / "workflow-descriptor.yaml"
    descriptor = yaml.safe_load(descriptor_path.read_text(encoding="utf-8"))
    descriptor["dar_runtime"]["required_version"] = "0.1.18"
    descriptor["capability_requirements"] = {
        "format_version": 1,
        "required_capabilities": [
            requirement.to_mapping()
            for requirement in requirements.required_capabilities
        ],
        "capability_requirements_digest": requirements.digest,
        "bindings": {
            name: {"capability_id": capability_id}
            for name, capability_id in requirements.bindings.items()
        },
    }
    descriptor_path.write_text(yaml.safe_dump(descriptor), encoding="utf-8")
    (source / "execution-descriptor.json").write_bytes(
        execution_descriptor.canonical_bytes
    )
    (source / "model-materials.json").write_text(
        json.dumps(
            {
                "format_version": 2,
                "logical_model_id": "qwen25-vl-3b-floorplan-grpo",
                "runner_contract": {"id": "transformers-generate-v1", "version": "1"},
                "execution_descriptor": {
                    "filename": "execution-descriptor.json",
                    "sha256": execution_descriptor.digest,
                },
                "sources": [
                    {
                        "role": "weights",
                        "group": "base",
                        "source_type": "huggingface_file",
                        "repository": "example/qwen",
                        "revision": "a" * 40,
                        "filename": "weights.safetensors",
                        "sha256": "d" * 64,
                    }
                ],
                "preparation": [],
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    capability_catalog = CapabilityCatalog(
        (converter_contract, runner_contract),
        (
            CapabilityProvider(
                "test-converter-provider", converter_contract, conformance_passed=True
            ),
            CapabilityProvider(
                "test-runner-provider", runner_contract, conformance_passed=True
            ),
        ),
    )

    class ReservationProvider:
        def reserve(self, _request: object) -> object:
            return object()

    return _V2ConverterBudgetFixture(
        capability_catalog,
        ExecutionDescriptorValidatorRegistry(
            (GenerationBudgetDescriptorValidator(abi),)
        ),
        ModelRunnerRegistry(
            (
                ModelRunnerProvider(
                    "test-runner-provider",
                    runner_contract,
                    (),
                    ((abi.abi_id, abi.version, abi.contract_digest),),
                ),
            )
        ),
        GenerationExecutionHostPolicy(budget, "cpu", ReservationProvider()),
    )


def _configure_legacy_generation_budget_fixture(
    runner: WorkflowRunner, v2_fixture: _V2ConverterBudgetFixture | None
) -> None:
    if v2_fixture is None:
        _configure_generation_budget_fixture(runner)


def _configure_generation_budget_fixture(runner: WorkflowRunner) -> None:
    adapter = runner._model_adapter
    if not isinstance(adapter, ConverterFakeAdapter):
        return
    budget = GenerationResourceBudget(
        max_new_tokens_per_fragment=4,
        max_continuations=1,
        max_total_generated_tokens=8,
        max_total_output_bytes=64,
        max_effective_context_tokens=8,
        max_runtime_milliseconds=1_000,
        max_memory_bytes=1_024,
    )

    class Provider:
        def reserve(self, _request: object) -> object:
            return object()

    descriptor = ExecutionDescriptor(
        ExecutionDescriptorAbi("test-generation-v1", "1", "a" * 64),
        ("weights",),
        {"generation_budget": budget.__dict__},
    )
    binding = ModelExecutionBinding(
        "test-model",
        "test-runner-v1",
        "1",
        None,
        None,
        "b" * 64,
        "c" * 64,
        "test-runner-v1",
        "1",
        "d" * 64,
    )
    original_preflight = runner._preflight

    def preflight(workflow_id: str):
        registration, package_root, policy, terminal_output_contract = (
            original_preflight(workflow_id)
        )
        return (
            registration,
            package_root,
            replace(
                policy,
                execution_descriptor=descriptor,
                model_execution_binding=binding,
            ),
            terminal_output_contract,
        )

    runner._preflight = preflight  # type: ignore[method-assign]
    runner._validate_model_execution_binding = lambda _policy: None  # type: ignore[method-assign]
    runner._generation_execution_host_policy = GenerationExecutionHostPolicy(
        budget, "cpu", Provider()
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


def test_runner_rejects_a_locked_runner_before_sealed_input_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner, preparation, registration, revision, _ = _runner(tmp_path)
    binding = ModelExecutionBinding(
        "example",
        "llama-cpp-v1",
        "1",
        "llama-cpp-text-v1",
        "1",
        "a" * 64,
        "b" * 64,
        "model.execution.test.v1",
        "1",
        "c" * 64,
    )
    policy = replace(
        compile_workflow_policy(revision),
        model_execution_binding=binding,
    )
    monkeypatch.setattr(
        runner,
        "_preflight",
        lambda _workflow_id: (registration, revision.package_root, policy, {}),
    )
    monkeypatch.setattr(
        preparation,
        "load",
        lambda *_args, **_kwargs: pytest.fail("sealed input was loaded"),
    )

    with pytest.raises(RunDarWorkflowError, match="model runner"):
        runner.run(
            RunDarWorkflowRequest(registration.workflow_id, "prepared-input"), now=NOW
        )


def test_runner_rejects_unsatisfied_requirement_before_artifact_materialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class CountingVerifier(ArtifactVerifier):
        def __init__(self) -> None:
            self.loads = 0

        def load(self, *args: object, **kwargs: object) -> object:
            self.loads += 1
            return super().load(*args, **kwargs)  # type: ignore[arg-type]

    verifier = CountingVerifier()
    runner, preparation, registration, revision, client = _runner(
        tmp_path, artifact_verifier=verifier
    )
    prepared = preparation.prepare(
        workflow_id=registration.workflow_id,
        prompt="Answer me.",
        workspace_artifact_ids=("v1.workspace-artifact",),
        now=NOW,
    )
    loads_before_run = verifier.loads
    contract = BUILTIN_CAPABILITY_CONTRACTS[0]
    requirement = CapabilityRequirement(
        contract.capability_id,
        contract.contract_version,
        contract.contract_digest,
        ("multimodal",),
    )
    requirements = CapabilityRequirements((requirement,))
    descriptor_path = revision.package_root / "workflow-descriptor.yaml"
    revision.package_root.chmod(0o700)
    descriptor_path.chmod(0o600)
    descriptor = yaml.safe_load(descriptor_path.read_text(encoding="utf-8"))
    descriptor["dar_runtime"]["required_version"] = "0.1.18"
    descriptor["capability_requirements"] = {
        "format_version": 1,
        "required_capabilities": [requirement.to_mapping()],
        "capability_requirements_digest": requirements.digest,
        "bindings": {},
    }
    descriptor_path.write_text(yaml.safe_dump(descriptor), encoding="utf-8")
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda *_args, **_kwargs: pytest.fail("subprocess creation was called"),
    )
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *_args, **_kwargs: pytest.fail("network access was called"),
    )

    with pytest.raises(RunDarWorkflowError, match="registered workflow run failed"):
        runner.run(
            RunDarWorkflowRequest.from_mapping(
                {
                    "format_version": 1,
                    "workflow_id": registration.workflow_id,
                    "prepared_input_id": prepared.prepared_input_id,
                }
            ),
            now=NOW,
        )

    assert verifier.loads == loads_before_run
    assert client.responses.calls == []


def test_runner_rejects_provider_reselection_before_model_execution(
    tmp_path: Path,
) -> None:
    contract = BUILTIN_CAPABILITY_CONTRACTS[0]

    def provider(provider_id: str) -> CapabilityProvider:
        return CapabilityProvider(
            provider_id,
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
        )

    first = provider("private-provider-a")
    second = provider("private-provider-b")
    original_catalog = CapabilityCatalog((contract,), (first, second))
    runner, preparation, registration, _, client = _runner(
        tmp_path,
        capability_catalog=original_catalog,
        with_capability_requirements=True,
    )
    prepared = preparation.prepare(
        workflow_id=registration.workflow_id,
        prompt="Answer me.",
        now=NOW,
    )
    runner._capability_catalog = CapabilityCatalog((contract,), (second, first))

    with pytest.raises(RunDarWorkflowError, match="capability requirements"):
        runner.run(
            RunDarWorkflowRequest.from_mapping(
                {
                    "format_version": 1,
                    "workflow_id": registration.workflow_id,
                    "prepared_input_id": prepared.prepared_input_id,
                }
            ),
            now=NOW,
        )

    assert client.responses.calls == []


def test_runner_rejects_provider_becoming_unavailable_before_model_execution(
    tmp_path: Path,
) -> None:
    contract = BUILTIN_CAPABILITY_CONTRACTS[0]
    provider = CapabilityProvider(
        "private-provider-a",
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
    )
    available = True
    catalog = CapabilityCatalog(
        (contract,),
        (provider,),
        availability_provider=lambda _provider: (
            ProviderAvailability.AVAILABLE
            if available
            else ProviderAvailability.DISABLED
        ),
    )
    runner, preparation, registration, _, client = _runner(
        tmp_path,
        capability_catalog=catalog,
        with_capability_requirements=True,
    )
    prepared = preparation.prepare(
        workflow_id=registration.workflow_id,
        prompt="Answer me.",
        now=NOW,
    )
    available = False

    with pytest.raises(RunDarWorkflowError, match="registered workflow run failed"):
        runner.run(
            RunDarWorkflowRequest.from_mapping(
                {
                    "format_version": 1,
                    "workflow_id": registration.workflow_id,
                    "prepared_input_id": prepared.prepared_input_id,
                }
            ),
            now=NOW,
        )

    assert client.responses.calls == []


def test_runner_rejects_provider_becoming_unavailable_before_converter_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = BUILTIN_CAPABILITY_CONTRACTS[0]
    provider = CapabilityProvider(
        "private-provider-a",
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
    )
    available = True
    catalog = CapabilityCatalog(
        (contract,),
        (provider,),
        availability_provider=lambda _provider: (
            ProviderAvailability.AVAILABLE
            if available
            else ProviderAvailability.DISABLED
        ),
    )
    runner, preparation, registration, _, client = _runner(
        tmp_path,
        vision=True,
        input_converter=True,
        package_model="qwen25-vl-3b-floorplan-grpo",
        artifact_verifier=ConverterArtifactVerifier(),
        v2_converter_budget=False,
        capability_catalog=catalog,
        with_capability_requirements=True,
    )
    adapter = runner._model_adapter
    assert isinstance(adapter, ConverterFakeAdapter)
    monkeypatch.setattr(
        adapter,
        "bind_input_converter",
        lambda **_kwargs: pytest.fail("converter load was called"),
    )
    prepared = preparation.prepare(
        workflow_id=registration.workflow_id,
        prompt="Create a floorplan.",
        workspace_artifact_ids=("v1.source-image",),
        now=NOW,
    )
    available = False

    with pytest.raises(RunDarWorkflowError, match="registered workflow run failed"):
        runner.run(
            RunDarWorkflowRequest.from_mapping(
                {
                    "format_version": 1,
                    "workflow_id": registration.workflow_id,
                    "prepared_input_id": prepared.prepared_input_id,
                }
            ),
            now=NOW,
        )

    assert client.responses.calls == []


def test_legacy_package_does_not_invoke_capability_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = CapabilityCatalog((), ())
    monkeypatch.setattr(
        catalog,
        "resolve",
        lambda _requirements: pytest.fail("capability catalog was used"),
    )
    runner, preparation, registration, _, client = _runner(
        tmp_path, capability_catalog=catalog
    )
    prepared = preparation.prepare(
        workflow_id=registration.workflow_id,
        prompt="Answer me.",
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

    assert result.status == "completed"
    assert len(client.responses.calls) == 1


def test_runner_binds_a_declared_local_tool_to_sealed_binary_input(
    tmp_path: Path,
) -> None:
    runner, preparation, registration, revision, _ = _runner(
        tmp_path,
        artifact_verifier=BinaryArtifactVerifier(),
        local_asset=True,
        local_tool_executor=lambda _command, input_bytes, _timeout: (
            b'{"byte_count":' + str(len(input_bytes)).encode() + b"}"
        ),
    )
    policy = compile_workflow_policy(revision)
    policy = replace(
        policy,
        declared_local_tools=(
            DeclaredLocalTool(
                tool_id="inspect",
                asset_path="tools/inspect",
                accepted_artifact_role="source_binary",
                max_input_bytes=1024,
                max_output_bytes=1024,
                timeout_seconds=1,
            ),
        ),
    )
    prepared = preparation.prepare(
        workflow_id=registration.workflow_id,
        prompt="Inspect it.",
        workspace_artifact_ids=("v1.workspace-artifact",),
        now=NOW,
    )
    sealed = preparation.load(
        prepared.prepared_input_id, registration=registration, now=NOW
    )
    registry = runner._tool_registry(  # type: ignore[attr-defined]
        policy,
        registration,
        package_root=revision.package_root,
        sealed=sealed,
        run_id="test-run",
        now=NOW,
    )

    result = registry.invoke_tool("inspect", {})

    assert result.success is True
    assert result.output == {"byte_count": len(b"sealed binary")}


def test_runner_postprocesses_terminal_output_with_declared_validator(
    tmp_path: Path,
) -> None:
    observed: list[bytes] = []
    runner, _, _, revision, _ = _runner(
        tmp_path,
        local_asset=True,
        local_tool_executor=lambda _command, content, _timeout: (
            observed.append(content) or b'{"valid":true}'
        ),
    )
    policy = replace(
        compile_workflow_policy(revision),
        terminal_output_validator=DeclaredTerminalOutputValidator(
            asset_path="tools/inspect",
            max_output_bytes=512,
            timeout_seconds=1,
        ),
    )

    runner._validate_terminal_output(  # type: ignore[attr-defined]
        policy=policy,
        package_root=revision.package_root,
        output={"message": "<svg/>"},
    )

    assert observed == [b"<svg/>"]


def test_runner_passes_terminal_bytes_only_between_declared_processors(
    tmp_path: Path,
) -> None:
    observed: list[bytes] = []
    responses = iter(
        (
            b'{"status":"accepted","output_base64":"eyJyb29tcyI6W119",'
            b'"repair_report":{"category":"none"}}',
            b'{"status":"accepted","output_base64":"PHN2Zy8+",'
            b'"repair_report":{"category":"none"}}',
        )
    )
    runner, _, _, revision, _ = _runner(
        tmp_path,
        local_asset=True,
        local_tool_executor=lambda _command, content, _timeout: (
            observed.append(content) or next(responses)
        ),
    )
    policy = replace(
        compile_workflow_policy(revision),
        terminal_output_processors=(
            DeclaredTerminalOutputProcessor("tools/inspect", 512, 1),
            DeclaredTerminalOutputProcessor("tools/inspect", 512, 1),
        ),
    )

    result = runner._process_terminal_output(  # type: ignore[attr-defined]
        policy=policy,
        package_root=revision.package_root,
        value='{"rooms":[]}',
        run_id="processor-run",
        now=NOW,
    )

    assert result == "<svg/>"
    assert observed == [b'{"rooms":[]}', b'{"rooms":[]}']
    diagnostic = runner.terminal_processor_diagnostic("processor-run", now=NOW)
    assert diagnostic.original == b'{"rooms":[]}'
    assert diagnostic.admitted == b"<svg/>"
    assert diagnostic.repair_categories == ("none", "none")
    assert diagnostic.original_digest != diagnostic.admitted_digest


def test_runner_rejects_a_terminal_processor_envelope_without_bounded_output(
    tmp_path: Path,
) -> None:
    runner, _, _, revision, _ = _runner(
        tmp_path,
        local_asset=True,
        local_tool_executor=lambda _command, _content, _timeout: (
            b'{"status":"accepted"}'
        ),
    )
    policy = replace(
        compile_workflow_policy(revision),
        terminal_output_processors=(
            DeclaredTerminalOutputProcessor("tools/inspect", 512, 1),
        ),
    )

    with pytest.raises(RunDarWorkflowError, match="terminal output processing failed"):
        runner._process_terminal_output(  # type: ignore[attr-defined]
            policy=policy,
            package_root=revision.package_root,
            value='{"rooms":[]}',
            run_id="rejected-processor-run",
            now=NOW,
        )

    diagnostic = runner.terminal_processor_diagnostic("rejected-processor-run", now=NOW)
    assert diagnostic.original == b'{"rooms":[]}'
    assert diagnostic.admitted is None
    assert diagnostic.repair_categories == ()


def test_runner_retains_and_loads_debug_fragments_for_the_local_owner(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.runner import _DebugDiagnosticCollector

    runner, _, _, _, _ = _runner(tmp_path)
    collector = _DebugDiagnosticCollector("debug-run-1")
    collector.set_run_id("workflow-run-1")

    class Generated:
        content = '{"walls":['
        exhausted = True
        generated_tokens = 3
        packed_context_tokens = 3
        elapsed_milliseconds = 42
        stop_classification = "completed"
        runner_max_new_tokens = 65_536
        backend_max_new_tokens = 65_536

    collector.record_fragment(Generated())
    runner._retain_debug_diagnostic(  # type: ignore[attr-defined]
        collector, outcome="failed", now=NOW
    )

    diagnostic = runner.debug_diagnostic("debug-run-1", now=NOW)

    assert diagnostic.diagnostic_id == "debug-run-1"
    assert diagnostic.run_id == "workflow-run-1"
    assert diagnostic.outcome == "failed"
    assert not hasattr(diagnostic.fragments[0], "content")
    assert diagnostic.fragments[0].fragment_index == 0
    assert diagnostic.fragments[0].exhausted is True
    assert diagnostic.fragments[0].generated_tokens == 3
    assert diagnostic.fragments[0].output_bytes == len(b'{"walls":[')
    assert diagnostic.fragments[0].packed_context_tokens == 3
    assert diagnostic.fragments[0].elapsed_milliseconds == 42
    assert diagnostic.fragments[0].stop_classification == "completed"
    assert diagnostic.terminal is None
    assert diagnostic.retention_limited is False


def test_debug_run_retains_fragments_without_exposing_them_normally(
    tmp_path: Path,
) -> None:
    runner, preparation, registration, _, client = _runner(
        tmp_path,
        vision=True,
        input_converter=True,
        package_model="qwen25-vl-3b-floorplan-grpo",
        artifact_verifier=ConverterArtifactVerifier(),
        response_format={"type": "json_object"},
        json_mode=True,
        response_content='{"message":"debug-only completion"}',
    )
    prepared = preparation.prepare(
        workflow_id=registration.workflow_id,
        prompt="Create a floorplan.",
        workspace_artifact_ids=("v1.source-image",),
        now=NOW,
    )

    debug = runner.run_debug(
        RunDarWorkflowRequest.from_mapping(
            {
                "format_version": 1,
                "workflow_id": registration.workflow_id,
                "prepared_input_id": prepared.prepared_input_id,
            }
        ),
        now=NOW,
    )

    diagnostic = runner.debug_diagnostic(debug.diagnostic_id, now=NOW)
    assert debug.status == "completed"
    assert debug.result is not None
    assert diagnostic.outcome == "completed"
    assert [
        (
            fragment.fragment_index,
            fragment.exhausted,
            fragment.generated_tokens,
            fragment.output_bytes,
        )
        for fragment in diagnostic.fragments
    ] == [(0, False, 35, len(b'{"message":"debug-only completion"}'))]
    assert "debug-only completion" not in repr(diagnostic)
    records = runner._terminal_diagnostic_store.active_records(  # type: ignore[attr-defined]
        kind="debug_workflow_diagnostic", owner="test-local-user", now=NOW
    )
    assert "debug-only completion" not in repr(records[0][1].payload)
    assert debug.diagnostic_id not in repr(debug.result)
    assert "debug-only completion" not in repr(runner.traces())
    assert "debug-only completion" not in repr(client.responses.calls)
    adapter = runner._model_adapter
    assert isinstance(adapter, ConverterFakeAdapter)
    assert adapter._debug_fragment_recorder is None


def test_debug_run_retains_post_generation_failure_without_trace_leakage(
    tmp_path: Path,
) -> None:
    runner, preparation, registration, _, _ = _runner(
        tmp_path,
        vision=True,
        input_converter=True,
        package_model="qwen25-vl-3b-floorplan-grpo",
        artifact_verifier=ConverterArtifactVerifier(),
        response_content='{"malformed":',
    )
    adapter = runner._model_adapter
    assert isinstance(adapter, ConverterFakeAdapter)
    adapter.debug_error = TimeoutError("debug-only completion")
    prepared = preparation.prepare(
        workflow_id=registration.workflow_id,
        prompt="Create a floorplan.",
        workspace_artifact_ids=("v1.source-image",),
        now=NOW,
    )

    debug = runner.run_debug(
        RunDarWorkflowRequest.from_mapping(
            {
                "format_version": 1,
                "workflow_id": registration.workflow_id,
                "prepared_input_id": prepared.prepared_input_id,
            }
        ),
        now=NOW,
    )

    diagnostic = runner.debug_diagnostic(debug.diagnostic_id, now=NOW)
    assert debug.status == diagnostic.outcome == "failed"
    assert not hasattr(diagnostic.fragments[0], "content")
    assert diagnostic.fragments[0].output_bytes == len(b'{"malformed":')
    assert "malformed" not in repr(runner.traces())
    assert debug.diagnostic_id not in repr(runner.traces())


def test_debug_run_retains_post_generation_cancellation(tmp_path: Path) -> None:
    runner, preparation, registration, _, _ = _runner(
        tmp_path,
        vision=True,
        input_converter=True,
        package_model="qwen25-vl-3b-floorplan-grpo",
        artifact_verifier=ConverterArtifactVerifier(),
        response_content='{"cancelled":true}',
    )
    adapter = runner._model_adapter
    assert isinstance(adapter, ConverterFakeAdapter)
    adapter.debug_error = asyncio.CancelledError()
    prepared = preparation.prepare(
        workflow_id=registration.workflow_id,
        prompt="Create a floorplan.",
        workspace_artifact_ids=("v1.source-image",),
        now=NOW,
    )

    with pytest.raises(asyncio.CancelledError):
        runner.run_debug(
            RunDarWorkflowRequest.from_mapping(
                {
                    "format_version": 1,
                    "workflow_id": registration.workflow_id,
                    "prepared_input_id": prepared.prepared_input_id,
                }
            ),
            now=NOW,
        )

    records = runner._terminal_diagnostic_store.active_records(  # type: ignore[attr-defined]
        kind="debug_workflow_diagnostic", owner="test-local-user", now=NOW
    )
    diagnostic_id = records[0][1].payload["diagnostic_id"]
    diagnostic = runner.debug_diagnostic(diagnostic_id, now=NOW)
    assert diagnostic.outcome == "cancelled"
    assert not hasattr(diagnostic.fragments[0], "content")
    assert diagnostic.fragments[0].output_bytes == len(b'{"cancelled":true}')


def test_debug_diagnostic_is_revoked_for_its_local_owner(tmp_path: Path) -> None:
    from dynamic_agent_runner.workflow_host.runner import _DebugDiagnosticCollector

    runner, _, _, _, _ = _runner(tmp_path)
    collector = _DebugDiagnosticCollector("debug-run-1")
    runner._retain_debug_diagnostic(  # type: ignore[attr-defined]
        collector, outcome="failed", now=NOW
    )

    runner.delete_debug_diagnostic("debug-run-1", now=NOW)

    with pytest.raises(RunDarWorkflowError, match="debug diagnostic is unavailable"):
        runner.debug_diagnostic("debug-run-1", now=NOW)


def test_debug_diagnostic_expires_after_its_retention_window(tmp_path: Path) -> None:
    from dynamic_agent_runner.workflow_host.runner import _DebugDiagnosticCollector

    runner, _, _, _, _ = _runner(tmp_path)
    runner._retain_debug_diagnostic(  # type: ignore[attr-defined]
        _DebugDiagnosticCollector("debug-run-1"), outcome="failed", now=NOW
    )

    with pytest.raises(RunDarWorkflowError, match="debug diagnostic is unavailable"):
        runner.debug_diagnostic("debug-run-1", now=NOW + timedelta(days=8))


def test_debug_diagnostic_marks_aggregate_retention_limit(tmp_path: Path) -> None:
    from dynamic_agent_runner.workflow_host.runner import (
        _DebugDiagnosticCollector,
        _MAX_DEBUG_DIAGNOSTIC_BYTES,
    )

    collector = _DebugDiagnosticCollector("debug-run-1")

    class Generated:
        content = "x" * _MAX_DEBUG_DIAGNOSTIC_BYTES
        exhausted = False
        generated_tokens = None

    collector.record_fragment(Generated())
    collector.record_terminal(
        TerminalProcessorDiagnostic(
            original=b"terminal",
            original_digest="a" * 64,
            admitted=None,
            admitted_digest=None,
            repair_categories=(),
        )
    )

    assert len(collector.fragments) == 1
    assert collector.terminal is not None
    assert collector.retention_limited is False


def test_local_host_exposes_only_the_debug_diagnostic_surface() -> None:
    class FakeRunner:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        def run_debug(self, request: object, **_kwargs: object) -> str:
            self.calls.append(("run", request))
            return "debug-result"

        def debug_diagnostic(self, diagnostic_id: str, **_kwargs: object) -> str:
            self.calls.append(("load", diagnostic_id))
            return "diagnostic"

        def delete_debug_diagnostic(
            self, diagnostic_id: str, **_kwargs: object
        ) -> None:
            self.calls.append(("delete", diagnostic_id))

    host = object.__new__(LocalWorkflowHost)
    runner = FakeRunner()
    host._runner = runner  # type: ignore[attr-defined]
    host._ensure_mcp_client_for_workflow = lambda _workflow_id: None  # type: ignore[method-assign]

    assert (
        host.run_debug(  # type: ignore[arg-type]
            workflow_id="workflow-1", prepared_input_id="prepared-1", now=NOW
        )
        == "debug-result"
    )
    assert host.debug_diagnostic("diagnostic-1", now=NOW) == "diagnostic"
    host.delete_debug_diagnostic("diagnostic-1", now=NOW)

    assert [kind for kind, _ in runner.calls] == ["run", "load", "delete"]


def test_runner_binds_reviewed_tool_to_an_opaque_binary_artifact(
    tmp_path: Path,
) -> None:
    binding = ReviewedToolPackageBinding(
        binding_id="network-review-1",
        binding_digest="a" * 64,
        allowed_tool_ids=("packet_summary",),
        artifact_aware_tool_ids=("packet_summary",),
    )
    packages = ReviewedToolPackageControlPlane(
        store=PrivateStateStore(tmp_path / "reviewed"), owner="local-user"
    )
    packages.create(package_name="network-tools", binding=binding)
    executor = ReviewedPacketExecutor(binding)
    runner, preparation, registration, revision, _ = _runner(
        tmp_path,
        artifact_verifier=OpaqueBinaryArtifactVerifier(),
        reviewed_tool_packages=packages,
        reviewed_artifact_tool_executors={"network-tools": executor},
    )
    policy = replace(
        compile_workflow_policy(revision),
        declared_artifact_tools=(
            DeclaredArtifactTool(
                tool_id="packet_summary",
                reviewed_package_name="network-tools",
                accepted_artifact_role="opaque_binary_artifact",
                max_result_bytes=1024,
            ),
        ),
    )
    prepared = preparation.prepare(
        workflow_id=registration.workflow_id,
        prompt="Inspect it.",
        workspace_artifact_ids=("v1.workspace-artifact",),
        now=NOW,
    )
    sealed = preparation.load(
        prepared.prepared_input_id, registration=registration, now=NOW
    )

    registry = runner._tool_registry(  # type: ignore[attr-defined]
        policy,
        registration,
        package_root=revision.package_root,
        sealed=sealed,
        run_id="test-run",
        now=NOW,
    )

    result = registry.invoke_tool("packet_summary", {})

    assert result.success is True
    assert result.output == {"packet_count": len(b"sealed network capture")}
    assert len(executor.references) == 1


@pytest.mark.parametrize(
    "outcome",
    (
        LocalApprovalDecision.APPROVED,
        LocalApprovalDecision.DENIED,
        LocalApprovalDecision.CANCELLED,
        None,
        RuntimeError("terminal unavailable"),
    ),
)
def test_runner_exposes_one_declared_reviewed_capability_tool(  # noqa: C901 - full binding path.
    tmp_path: Path, outcome: LocalApprovalDecision | None | RuntimeError
) -> None:
    class Host:
        def resolve(self, **_kwargs: object) -> object:
            return job

        def revalidate(self, **_kwargs: object) -> object:
            return job

        def dispatch(self, **_kwargs: object) -> ReviewedCapabilityHostResult:
            self.calls += 1
            return ReviewedCapabilityHostResult(
                candidates=(
                    ReviewedCapabilityCandidateOutput(
                        "index_generation", "application/octet-stream", b"index"
                    ),
                    ReviewedCapabilityCandidateOutput(
                        "index_manifest", "application/json", b'{"index_digest":"a"}'
                    ),
                    ReviewedCapabilityCandidateOutput(
                        "coverage_report", "application/json", b'{"indexed":1}'
                    ),
                ),
                contribution=ReviewedCapabilityHostContribution(
                    "generation-1",
                    {
                        "source_records": 1,
                        "embedding_units": 1,
                        "indexed": 1,
                        "skipped": 0,
                        "deleted": 0,
                        "errored": 0,
                    },
                ),
            )

        def begin_pending_publication(self, **_kwargs: object) -> None:
            return None

        def query_current_outcome(self, **_kwargs: object) -> str:
            return "pending"

        def acknowledge_visibility(self, **_kwargs: object) -> None:
            return None

        def compensate(self, **_kwargs: object) -> None:
            return None

        def assert_generation_current(self, **_kwargs: object) -> bool:
            return True

        def unpublish_generation_atomically(self, **_kwargs: object) -> None:
            return None

        def __init__(self) -> None:
            self.calls = 0

    outputs = (
        ReviewedCapabilityTemplateOutput(
            "index_generation", "application/octet-stream", 1024, 60
        ),
        ReviewedCapabilityTemplateOutput(
            "index_manifest", "application/json", 1024, 60
        ),
        ReviewedCapabilityTemplateOutput(
            "coverage_report", "application/json", 1024, 60
        ),
    )
    values = {
        "capability_id": "vector_index.build.v1",
        "contract_version": "1",
        "input_fields": ("job_handle",),
        "required_dependency": "embedding.execute.v1",
        "outputs": outputs,
        "max_receipt_bytes": 1024,
        "approval_class": "human_write",
        "extension_binding": "host-vector-index-v1",
        "recovery_operations": (
            "acknowledge_visibility",
            "begin_pending_publication",
            "compensate",
            "query_current_outcome",
        ),
        "success_receipt_schema_digest": "d" * 64,
        "generation_id_max_bytes": 128,
        "artifact_handle_max_bytes": 128,
        "count_ceiling": 1024,
        "failure_classifications": ("host_failure",),
        "enabled": True,
    }
    template = ReviewedCapabilityTemplate(
        template_digest=reviewed_capability_template_digest(**values), **values
    )
    host = Host()
    extension = ReviewedCapabilityHostExtension(
        template=template,
        host=host,
        dependency_binding_digest="c" * 64,
        nonce_factory=lambda: "v1.approval.nonce",
    )
    runner, preparation, registration, revision, _ = _runner(tmp_path)
    store = PrivateStateStore(tmp_path / "reviewed")
    templates = ReviewedCapabilityTemplateControlPlane(
        store=store, owner="test-local-user"
    )
    templates.create(template=template)
    runner._action_ledger = WorkflowActionLedger(store=store, owner="test-local-user")  # type: ignore[attr-defined]
    runner._approval_store = WorkflowApprovalStore(store=store, owner="test-local-user")  # type: ignore[attr-defined]
    runner._reviewed_capability_extensions = {template.capability_id: extension}  # type: ignore[attr-defined]
    runner._reviewed_capability_templates = templates  # type: ignore[attr-defined]
    runner._reviewed_capability_artifacts = SealedArtifactOutputHandleService(  # type: ignore[attr-defined]
        store=store, owner="test-local-user"
    )
    job = SealedReviewedCapabilityJob(
        job_handle="sealed:vector-index-job:job-1",
        issuer_id="host-local",
        opaque_id="job-1",
        revision="1",
        digest="a" * 64,
        principal="test-local-user",
        expires_at=NOW + timedelta(minutes=5),
        template_capability_id=template.capability_id,
        template_contract_version=template.contract_version,
        template_digest=template.template_digest,
        extension_binding=template.extension_binding,
        dependency_capability_id="embedding.execute.v1",
        dependency_binding_digest="c" * 64,
        member_binding_digest="d" * 64,
    )
    policy = replace(
        compile_workflow_policy(revision),
        declared_reviewed_capability_tools=(
            DeclaredReviewedCapabilityTool(
                tool_id="build_vector_index",
                capability_id=template.capability_id,
                contract_version=template.contract_version,
                template_digest=template.template_digest,
                input_fields=("job_handle",),
                side_effect="write",
                approval_required=True,
            ),
        ),
    )
    prepared = preparation.prepare(
        workflow_id=registration.workflow_id, prompt="Build it.", now=NOW
    )
    sealed = preparation.load(
        prepared.prepared_input_id, registration=registration, now=NOW
    )

    class Broker:
        def __init__(self) -> None:
            self.actions: list[object] = []
            self.approvals: list[object] = []

        def decide(self, *, action: object, approval: object) -> LocalApprovalDecision:
            self.actions.append(action)
            self.approvals.append(approval)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome  # type: ignore[return-value]

    broker = Broker()

    registry = runner._tool_registry(  # type: ignore[attr-defined]
        policy,
        registration,
        package_root=revision.package_root,
        sealed=sealed,
        run_id="test-run",
        approval_broker=broker,
        now=NOW,
    )

    assert registry.get_tool("build_vector_index").definition.raw["input_schema"] == {
        "type": "object",
        "properties": {"job_handle": {"type": "string"}},
        "required": ["job_handle"],
        "additionalProperties": False,
    }
    assert (
        registry.get_tool("build_vector_index").definition.approval_required
        == "human_approval"
    )
    result = registry.invoke_tool("build_vector_index", {"job_handle": job.job_handle})

    assert len(broker.actions) == len(broker.approvals) == 1
    action = broker.actions[0]
    assert isinstance(action, ExternalAction)
    assert action.remote_tool_name == "vector_index.build.v1"
    assert action.side_effect == "write"
    assert action.normalized_arguments == {}
    if outcome is LocalApprovalDecision.APPROVED:
        assert result.success is True
        assert result.output["status"] == "published"
        assert host.calls == 1
    else:
        assert result.success is False
        assert host.calls == 0
    assert "index_digest" not in json.dumps(result.output)
    assert job.member_binding_digest not in json.dumps(result.output)


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


def test_runner_delivers_converter_payload_without_media_type_routing(
    tmp_path: Path,
) -> None:
    runner, preparation, registration, _, client = _runner(
        tmp_path,
        vision=True,
        input_converter=True,
        package_model="qwen25-vl-3b-floorplan-grpo",
        artifact_verifier=ConverterArtifactVerifier(),
        v2_converter_budget=True,
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
    assert isinstance(adapter, ConverterFakeAdapter)
    assert result.output == {"message": "completed locally"}
    assert len(adapter.bound_converters) == 1
    assert len(adapter.bound_generation_budgets) == 1
    assert adapter.bound_converters[0][1].converter_id == "qwen25-vl-3b-grpo-input-v1"
    assert adapter.bound_payloads == [b"sealed-image-bytes"]
    assert adapter.bound_images == []
    assert adapter.payload_cleared == 1
    assert "sealed-image-bytes" not in repr(client.responses.calls)
    assert "v1.source-image" not in repr(runner.traces())


def test_runner_rejects_converter_without_budget_before_sealed_input_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner, preparation, registration, _, _ = _runner(
        tmp_path,
        vision=True,
        input_converter=True,
        package_model="qwen25-vl-3b-floorplan-grpo",
        artifact_verifier=ConverterArtifactVerifier(),
        v2_converter_budget=True,
    )
    preflight = runner._preflight

    def without_generation_budget(workflow_id: str):
        registration, package_root, policy, terminal_output_contract = preflight(
            workflow_id
        )
        return (
            registration,
            package_root,
            replace(policy, execution_descriptor=None),
            terminal_output_contract,
        )

    runner._preflight = without_generation_budget  # type: ignore[method-assign]
    load_calls: list[object] = []

    def load(**_kwargs: object) -> object:
        load_calls.append(object())
        raise AssertionError("sealed input must not be loaded")

    monkeypatch.setattr(
        preparation,
        "load",
        load,
    )

    with pytest.raises(RunDarWorkflowError, match="generation budget"):
        runner.run(
            RunDarWorkflowRequest.from_mapping(
                {
                    "format_version": 1,
                    "workflow_id": registration.workflow_id,
                    "prepared_input_id": "unloaded-input",
                }
            ),
            now=NOW,
        )

    assert load_calls == []


def test_runner_rejects_declared_json_before_binding_sealed_payload(
    tmp_path: Path,
) -> None:
    runner, preparation, registration, _, _ = _runner(
        tmp_path,
        vision=True,
        input_converter=True,
        package_model="qwen25-vl-3b-floorplan-grpo",
        artifact_verifier=ConverterArtifactVerifier(),
        response_format={"type": "json_object"},
    )
    prepared = preparation.prepare(
        workflow_id=registration.workflow_id,
        prompt="Create a floorplan.",
        workspace_artifact_ids=("v1.source-image",),
        now=NOW,
    )

    with pytest.raises(RunDarWorkflowError, match="lacks json_mode"):
        runner.run(
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
    assert isinstance(adapter, ConverterFakeAdapter)
    assert adapter.bound_converters == []
    assert adapter.bound_payloads == []
    assert adapter.payload_cleared == 0
    assert "Create a floorplan." not in repr(runner.traces())
    assert "sealed-image-bytes" not in repr(runner.traces())


def test_runner_defers_worker_converter_loading_to_the_adapter(
    tmp_path: Path,
) -> None:
    runner, preparation, registration, _, _ = _runner(
        tmp_path,
        vision=True,
        input_converter=True,
        package_model="qwen25-vl-3b-floorplan-grpo",
        artifact_verifier=ConverterArtifactVerifier(),
    )
    adapter = runner._model_adapter
    assert isinstance(adapter, ConverterFakeAdapter)
    worker_payloads: list[tuple[Path, object, bytes]] = []

    def bind_worker_converter_payload(
        *, package_root: Path, converter: object, content: bytes
    ) -> None:
        worker_payloads.append((package_root, converter, content))

    adapter.bind_worker_converter_payload = bind_worker_converter_payload  # type: ignore[attr-defined]
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

    assert result.output == {"message": "completed locally"}
    assert len(worker_payloads) == 1
    assert worker_payloads[0][1].converter_id == "qwen25-vl-3b-grpo-input-v1"
    assert worker_payloads[0][2] == b"sealed-image-bytes"
    assert adapter.bound_converters == []
    assert adapter.bound_payloads == []


def test_runner_redacts_converter_package_load_failure(tmp_path: Path) -> None:
    runner, preparation, registration, _, _ = _runner(
        tmp_path,
        vision=True,
        input_converter=True,
        package_model="qwen25-vl-3b-floorplan-grpo",
        artifact_verifier=ConverterArtifactVerifier(),
    )
    adapter = runner._model_adapter
    assert isinstance(adapter, ConverterFakeAdapter)
    adapter.converter_error = ValueError("package path leaked")
    prepared = preparation.prepare(
        workflow_id=registration.workflow_id,
        prompt="Create a floorplan.",
        workspace_artifact_ids=("v1.source-image",),
        now=NOW,
    )

    with pytest.raises(RunDarWorkflowError, match="sealed converter package"):
        runner.run(
            RunDarWorkflowRequest.from_mapping(
                {
                    "format_version": 1,
                    "workflow_id": registration.workflow_id,
                    "prepared_input_id": prepared.prepared_input_id,
                }
            ),
            now=NOW,
        )

    assert adapter.bound_payloads == []
    assert adapter.payload_cleared == 0
    assert "package path leaked" not in repr(runner.traces())
    assert runner.traces()[-1].status == "failed"


@pytest.mark.parametrize("failure", [RuntimeError("worker failed"), TimeoutError()])
def test_runner_clears_converter_payload_and_redacts_worker_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: Exception
) -> None:
    runner, preparation, registration, _, _ = _runner(
        tmp_path,
        vision=True,
        input_converter=True,
        package_model="qwen25-vl-3b-floorplan-grpo",
        artifact_verifier=ConverterArtifactVerifier(),
    )
    monkeypatch.setattr(
        workflow_runner_module,
        "run_agent_workflow",
        lambda **_kwargs: (_ for _ in ()).throw(failure),
    )
    prepared = preparation.prepare(
        workflow_id=registration.workflow_id,
        prompt="Create a floorplan.",
        workspace_artifact_ids=("v1.source-image",),
        now=NOW,
    )

    with pytest.raises(RunDarWorkflowError, match="DAR workflow execution failed"):
        runner.run(
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
    assert isinstance(adapter, ConverterFakeAdapter)
    assert adapter.payload_cleared == 1
    assert "sealed-image-bytes" not in repr(runner.traces())
    assert runner.traces()[-1].status == "failed"


def test_runner_clears_converter_payload_and_records_cancellation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runner, preparation, registration, _, _ = _runner(
        tmp_path,
        vision=True,
        input_converter=True,
        package_model="qwen25-vl-3b-floorplan-grpo",
        artifact_verifier=ConverterArtifactVerifier(),
    )
    monkeypatch.setattr(
        workflow_runner_module,
        "run_agent_workflow",
        lambda **_kwargs: (_ for _ in ()).throw(asyncio.CancelledError()),
    )
    prepared = preparation.prepare(
        workflow_id=registration.workflow_id,
        prompt="Create a floorplan.",
        workspace_artifact_ids=("v1.source-image",),
        now=NOW,
    )

    with pytest.raises(asyncio.CancelledError):
        runner.run(
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
    assert isinstance(adapter, ConverterFakeAdapter)
    assert adapter.payload_cleared == 1
    assert runner.traces()[-1].status == "failed"


def test_floorplan_run_validates_shaped_terminal_output_after_image_delivery(
    tmp_path: Path,
) -> None:
    validated: list[bytes] = []
    runner, preparation, registration, _, _ = _runner(
        tmp_path,
        vision=True,
        terminal_validator=True,
        package_model="qwen25-vl-3b-floorplan-grpo",
        artifact_verifier=VisionArtifactVerifier(),
        response_content='<svg xmlns="http://www.w3.org/2000/svg"/>',
        local_tool_executor=lambda _command, content, _timeout: (
            validated.append(content)
            or (
                b'{"valid":true}' if content.startswith(b"<svg") else b'{"valid":false}'
            )
        ),
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

    assert result.output == {"message": '<svg xmlns="http://www.w3.org/2000/svg"/>'}
    assert validated == [b'<svg xmlns="http://www.w3.org/2000/svg"/>']


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
