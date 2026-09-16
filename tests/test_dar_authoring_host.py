"""Tests for the private host that composes DAR authoring runner services."""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import zipfile
from dataclasses import replace
from datetime import UTC, datetime, timedelta
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
    CapabilityContract,
    CapabilityProvider,
    CapabilityRequirement,
    CapabilityRequirements,
    ProviderAvailability,
    ReviewedCapabilityTemplate,
    ReviewedCapabilityTemplateOutput,
    reviewed_capability_template_digest,
)
from dynamic_agent_runner.workflow_host.authorized_tools import (  # noqa: E402
    create_authorized_mcp_tool_bindings,
)
from dynamic_agent_runner.workflow_host.mcp_client import MCPClientConfiguration  # noqa: E402
from dynamic_agent_runner.workflow_host.mcp_binding import (  # noqa: E402
    MCPWorkflowCapabilityBindingError,
)
from dynamic_agent_runner.workflow_host.mcp_surfaces import MCPDiscoveredTool  # noqa: E402
from dynamic_agent_runner.workflow_host.profiles import (  # noqa: E402
    InstallationIdentityProvider,
    LocalModelProfileControlPlane,
)
from dynamic_agent_runner.workflow_host.policy import (  # noqa: E402
    PolicyCompilationError,
    compile_workflow_policy,
)
from dynamic_agent_runner.workflow_host.package_export import (  # noqa: E402
    export_staged_package,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore  # noqa: E402
from dynamic_agent_runner.workflow_host.reviewed_tool_packages import (  # noqa: E402
    ReviewedToolPackageBinding,
)
from dynamic_agent_runner.workflow_host.reviewed_capability_host_extension import (  # noqa: E402
    ReviewedCapabilityHostExtension,
)
from dynamic_agent_runner.workflow_host.sealed_artifact_workflow_runner import (  # noqa: E402
    SealedArtifactInvocation,
)
from dynamic_agent_runner.workflow_host.locked_inference_execution import (  # noqa: E402
    LockedInferenceHostLimits,
)
from dynamic_agent_runner.workflow_host.locked_inference_provider_registry import (  # noqa: E402
    LockedInferenceProviderBinding,
    LockedInferenceProviderRegistry,
)
from dynamic_agent_runner.workflow_host.locked_inference_sealed_artifact_callback import (  # noqa: E402
    LockedInferenceSealedArtifactCallbackResolver,
)
from dynamic_agent_runner.workflow_host.embedding_execution import (  # noqa: E402
    EmbeddingBatchLimits,
    EmbeddingLimitProjectorBinding,
    EmbeddingLimitProjectorRegistry,
)
from dynamic_agent_runner.workflow_host.embedding_index_artifacts import (  # noqa: E402
    DocumentSnapshot,
    DocumentSnapshotPolicy,
    SnapshotDocument,
)
from dynamic_agent_runner.workflow_host.embedding_sealed_artifact_callback import (  # noqa: E402
    EmbeddingSealedArtifactCallbackResolver,
)
from dynamic_agent_runner.workflow_host.execution_descriptors import (  # noqa: E402
    ExecutionDescriptorAbi,
    ExecutionDescriptorValidatorRegistry,
)
from dynamic_agent_runner.workflow_host.model_materials import (  # noqa: E402
    parse_model_dependency_lock,
)


NOW = datetime(2026, 8, 23, tzinfo=UTC)
TEMPLATE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "specs"
    / "agent-engineering-plugin-migration"
    / "legacy-dar-authoring"
    / "templates"
)


def _observe_sealed_artifact_receiver(  # noqa: C901
    host: LocalWorkflowHost, resolver: object, monkeypatch: pytest.MonkeyPatch
) -> list[str]:
    import dynamic_agent_runner.workflow_host.sealed_artifact_workflow_runner as runner_module

    receiver = host._sealed_artifact_runner
    assert receiver is not None
    events: list[str] = []
    registration_resolve = host._registrations.resolve
    catalog_revision = host._catalog.revision
    policy_compile = runner_module.compile_workflow_policy
    descriptor_verify = runner_module.verify_sealed_artifact_runner_files
    collector_type = runner_module.SealedArtifactOutputCollector
    asset_read = runner_module._asset_bytes
    handle_reserve = receiver._handles.reserve
    handle_consume = receiver._handles.consume
    output_publish = receiver._outputs.publish
    resolver_resolve = resolver.resolve  # type: ignore[attr-defined]

    def observe_registration(*args, **kwargs):
        events.append("registration")
        return registration_resolve(*args, **kwargs)

    def observe_catalog(*args, **kwargs):
        events.append("catalog_revision")
        return catalog_revision(*args, **kwargs)

    def observe_policy(*args, **kwargs):
        events.append("policy_compile")
        return policy_compile(*args, **kwargs)

    def observe_descriptor(*args, **kwargs):
        events.append("descriptor_manifest_verify")
        return descriptor_verify(*args, **kwargs)

    def observe_collector(*args, **kwargs):
        events.append("collector_allocation")
        collector = collector_type(*args, **kwargs)
        collector_seal = collector.seal

        def observe_seal():
            events.append("collector_seal")
            return collector_seal()

        collector.seal = observe_seal
        return collector

    def observe_asset(*args, **kwargs):
        events.append("asset_read")
        return asset_read(*args, **kwargs)

    def observe_reserve(*args, **kwargs):
        events.append("handle_reservation")
        return handle_reserve(*args, **kwargs)

    def observe_consume(*args, **kwargs):
        events.append("input_byte_read")
        return handle_consume(*args, **kwargs)

    def observe_publish(*args, **kwargs):
        events.append("output_handle_publication")
        return output_publish(*args, **kwargs)

    def observe_callback_provider(*args, **kwargs):
        events.append("callback_provider_resolution")
        return resolver_resolve(*args, **kwargs)

    monkeypatch.setattr(host._registrations, "resolve", observe_registration)
    monkeypatch.setattr(host._catalog, "revision", observe_catalog)
    monkeypatch.setattr(runner_module, "compile_workflow_policy", observe_policy)
    monkeypatch.setattr(
        runner_module, "verify_sealed_artifact_runner_files", observe_descriptor
    )
    monkeypatch.setattr(
        runner_module, "SealedArtifactOutputCollector", observe_collector
    )
    monkeypatch.setattr(runner_module, "_asset_bytes", observe_asset)
    monkeypatch.setattr(receiver._handles, "reserve", observe_reserve)
    monkeypatch.setattr(receiver._handles, "consume", observe_consume)
    monkeypatch.setattr(receiver._outputs, "publish", observe_publish)
    monkeypatch.setattr(resolver, "resolve", observe_callback_provider)
    return events


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


def _write_locked_inference_sealed_package(
    source: Path,
    *,
    profile_digest: str,
    contract: CapabilityContract,
    runner_contract: CapabilityContract,
) -> bytes:
    runner_requirement = CapabilityRequirement(
        runner_contract.capability_id,
        runner_contract.contract_version,
        runner_contract.contract_digest,
        (),
    )
    requirement = CapabilityRequirement(
        contract.capability_id,
        contract.contract_version,
        contract.contract_digest,
        ("structured",),
    )
    requirements = CapabilityRequirements(
        (runner_requirement, requirement),
        {"runner": runner_requirement.capability_id},
    )
    schema = (
        b'{"max_depth":2,"max_items":1,"properties":{"value":'
        b'{"max_string_bytes":16,"type":"string"}},"required":["value"],'
        b'"type":"object"}'
    )
    instruction = b"sealed instruction"
    asset = (
        b"def run(context):\n"
        b"    request = context.read_input('request')\n"
        b"    response = context.invoke_callback('suggest', request)\n"
        b"    context.write_output('result', 'application/json', response)\n"
    )
    child = json.dumps(
        {
            "body": {},
            "callback_name": "suggest",
            "capability_requirement": "model.generate.v1",
            "format_version": 1,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    asset_digest = hashlib.sha256(asset).hexdigest()
    schema_digest = hashlib.sha256(schema).hexdigest()
    child_digest = hashlib.sha256(child).hexdigest()
    (source / "assets").mkdir()
    (source / "assets" / "runner.py").write_bytes(asset)
    (source / "assets" / "instruction.txt").write_bytes(instruction)
    (source / "schemas").mkdir()
    (source / "schemas" / "value.json").write_bytes(schema)
    (source / "contracts").mkdir()
    (source / "contracts" / "suggest.json").write_bytes(child)
    descriptor_path = source / "workflow-descriptor.yaml"
    descriptor = yaml.safe_load(descriptor_path.read_text(encoding="utf-8"))
    descriptor["dar_runtime"]["required_version"] = "0.1.18"
    descriptor["capability_requirements"] = {
        "format_version": 1,
        "required_capabilities": [
            runner_requirement.to_mapping(),
            requirement.to_mapping(),
        ],
        "capability_requirements_digest": requirements.digest,
        "bindings": {"runner": {"capability_id": runner_requirement.capability_id}},
    }
    descriptor["inference_roles"] = {
        "format_version": 1,
        "roles": [
            {
                "role": "suggest",
                "material_role": "suggest",
                "capability_id": "model.generate.v1",
                "instruction_asset": {
                    "path": "assets/instruction.txt",
                    "sha256": hashlib.sha256(instruction).hexdigest(),
                },
                "request_schema_asset": {
                    "path": "schemas/value.json",
                    "sha256": schema_digest,
                },
                "response_schema_asset": {
                    "path": "schemas/value.json",
                    "sha256": schema_digest,
                },
                "authorized_asset_digests": [asset_digest],
                "limits": {
                    "max_calls": 1,
                    "max_input_bytes": 100,
                    "max_output_bytes": 100,
                    "timeout_milliseconds": 100,
                    "max_concurrency": 1,
                },
            }
        ],
    }
    descriptor_path.write_text(yaml.safe_dump(descriptor), encoding="utf-8")
    (source / "model-material-sets.json").write_text(
        json.dumps(
            {
                "format_version": 1,
                "material_sets": [
                    {
                        "role": "suggest",
                        "model_materials": {
                            "format_version": 1,
                            "logical_model_id": "test-model",
                            "runner_contract": {"id": "test", "version": "1"},
                            "loader_profile_contract": {"id": "test", "version": "1"},
                            "sources": [
                                {
                                    "role": "base_model",
                                    "group": "base",
                                    "source_type": "huggingface_file",
                                    "repository": "example/test-model",
                                    "revision": "a" * 40,
                                    "filename": "model.gguf",
                                    "sha256": "b" * 64,
                                }
                            ],
                            "preparation": [],
                        },
                    }
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    runner = {
        "asset": {
            "abi_version": 1,
            "entrypoint": "run",
            "path": "assets/runner.py",
            "sha256": asset_digest,
        },
        "callbacks": [
            {
                "child_contract_digest": child_digest,
                "max_calls": 1,
                "max_concurrency": 1,
                "max_request_bytes": 100,
                "max_response_bytes": 100,
                "max_total_request_bytes": 100,
                "max_total_response_bytes": 100,
                "name": "suggest",
                "requirement": "model.generate.v1",
                "timeout_milliseconds": 100,
            }
        ],
        "capability_requirements_digest": requirements.digest,
        "child_contract_digests": [child_digest],
        "format_version": 1,
        "inputs": [
            {
                "max_bytes": 100,
                "media_type": "application/json",
                "required": True,
                "role": "request",
                "schema_digest": schema_digest,
            }
        ],
        "limits": {
            "max_concurrency": 1,
            "max_cpu_milliseconds": 1,
            "max_io_bytes": 1000,
            "max_memory_bytes": 1,
            "max_runtime_milliseconds": 100,
        },
        "outputs": [
            {
                "max_bytes": 100,
                "media_type": "application/json",
                "role": "result",
                "schema_digest": schema_digest,
            }
        ],
        "profile_digest": profile_digest,
        "schemas": [
            {
                "dialect": "json-schema-draft-2020-12",
                "path": "schemas/value.json",
                "sha256": schema_digest,
            }
        ],
    }
    runner["artifact_runner_digest"] = hashlib.sha256(
        json.dumps(runner, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    (source / "sealed-artifact-runner.json").write_text(
        json.dumps(runner, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    return b'{"value":"request"}'


def _write_portable_embedding_sealed_package(
    source: Path,
    *,
    profile_digest: str,
    embedding_contract: CapabilityContract,
    runner_contract: CapabilityContract,
    abi: ExecutionDescriptorAbi,
    snapshot: DocumentSnapshot,
) -> None:
    runner_requirement = CapabilityRequirement(
        runner_contract.capability_id,
        runner_contract.contract_version,
        runner_contract.contract_digest,
        (),
    )
    embedding_requirement = CapabilityRequirement(
        embedding_contract.capability_id,
        embedding_contract.contract_version,
        embedding_contract.contract_digest,
        ("deterministic",),
    )
    requirements = CapabilityRequirements(
        (embedding_requirement, runner_requirement),
        {"runner": runner_requirement.capability_id},
    )
    request_schema = b'{"additionalProperties":false,"properties":{"items":{"items":{"additionalProperties":false,"properties":{"id":{"type":"string"},"text":{"type":"string"}},"required":["id","text"],"type":"object"},"type":"array"}},"required":["items"],"type":"object"}'
    response_schema = b'{"additionalProperties":false,"properties":{"items":{"items":{"additionalProperties":false,"properties":{"id":{"type":"string"},"vector":{"items":{"type":"number"},"type":"array"}},"required":["id","vector"],"type":"object"},"type":"array"}},"required":["items"],"type":"object"}'
    child = json.dumps(
        {
            "body": {
                "embed_request_schema_digest": hashlib.sha256(
                    request_schema
                ).hexdigest(),
                "embed_response_schema_digest": hashlib.sha256(
                    response_schema
                ).hexdigest(),
            },
            "callback_name": "embed",
            "capability_requirement": "embedding.execute.v1",
            "format_version": 1,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    child_digest = hashlib.sha256(child).hexdigest()
    execution_descriptor = json.dumps(
        {
            "abi_fields": {},
            "architecture_abi": abi.to_mapping(),
            "format_version": 1,
            "material_roles": ["tokenizer", "weights"],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    materials = {
        "execution_descriptor": {
            "filename": "execution-descriptor.json",
            "sha256": hashlib.sha256(execution_descriptor).hexdigest(),
        },
        "format_version": 2,
        "logical_model_id": "test-embedding",
        "preparation": [],
        "runner_contract": {"id": "test-runner", "version": "1"},
        "sources": [
            {
                "filename": "tokenizer.json",
                "group": "embedding",
                "repository": "example/test-embedding",
                "revision": "a" * 40,
                "role": "tokenizer",
                "sha256": "b" * 64,
                "source_type": "huggingface_file",
            },
            {
                "filename": "weights.safetensors",
                "group": "embedding",
                "repository": "example/test-embedding",
                "revision": "a" * 40,
                "role": "weights",
                "sha256": "c" * 64,
                "source_type": "huggingface_file",
            },
        ],
    }
    material_bytes = json.dumps(
        materials, sort_keys=True, separators=(",", ":")
    ).encode()
    material_digest = parse_model_dependency_lock(material_bytes).digest
    bundle = b"index"
    bundle_digest = hashlib.sha256(bundle).hexdigest()
    manifest_prefix = (
        b'{"bundle_sha256":"'
        + bundle_digest.encode()
        + b'","chunk_count":1,"deleted_count":0,"document_count":1,'
        + b'"embedding_capability_contract_digest":"'
        + embedding_contract.contract_digest.encode()
        + b'","embedding_material_lock_digest":"'
        + material_digest.encode()
        + b'","error_count":0,"format_version":1,"index_builder_digest":"'
    )
    manifest_suffix = (
        b'","indexed_count":1,"skipped_count":0,"snapshot_digest":"'
        + snapshot.snapshot_digest.encode()
        + b'"}'
    )
    report_prefix = (
        b'{"chunk_count":1,"deleted_count":0,"document_count":1,'
        + b'"embedding_capability_contract_digest":"'
        + embedding_contract.contract_digest.encode()
        + b'","embedding_material_lock_digest":"'
        + material_digest.encode()
        + b'","error_classifications":[],"error_count":0,"format_version":1,'
        + b'"index_builder_digest":"'
    )
    report_suffix = (
        b'","indexed_count":1,"prior_bundle_digest":null,"skipped_count":0,'
        + b'"snapshot_digest":"'
        + snapshot.snapshot_digest.encode()
        + b'"}'
    )
    asset = (
        b"def run(context):\n"
        b"    context.read_input('snapshot')\n"
        b'    context.invoke_callback(\'embed\', b\'{"items":[{"id":"chunk","text":"body"}]}\')\n'
        b"    builder = context.callback_identity('embed')['digest'].encode()\n"
        b"    context.write_output('coverage_report', 'application/json', "
        + repr(report_prefix).encode()
        + b" + builder + "
        + repr(report_suffix).encode()
        + b")\n"
        b"    context.write_output('index_bundle', 'application/octet-stream', b'index')\n"
        b"    context.write_output('index_manifest', 'application/json', "
        + repr(manifest_prefix).encode()
        + b" + builder + "
        + repr(manifest_suffix).encode()
        + b")\n"
    )
    asset_digest = hashlib.sha256(asset).hexdigest()
    (source / "assets").mkdir()
    (source / "assets" / "runner.py").write_bytes(asset)
    (source / "schemas").mkdir()
    (source / "schemas" / "embed-request.json").write_bytes(request_schema)
    (source / "schemas" / "embed-response.json").write_bytes(response_schema)
    (source / "contracts").mkdir()
    (source / "contracts" / "embed.json").write_bytes(child)
    (source / "execution-descriptor.json").write_bytes(execution_descriptor)
    descriptor_path = source / "workflow-descriptor.yaml"
    descriptor = yaml.safe_load(descriptor_path.read_text(encoding="utf-8"))
    descriptor["capability_requirements"] = {
        "format_version": 1,
        "required_capabilities": [
            embedding_requirement.to_mapping(),
            runner_requirement.to_mapping(),
        ],
        "capability_requirements_digest": requirements.digest,
        "bindings": {"runner": {"capability_id": runner_requirement.capability_id}},
    }
    descriptor_path.write_text(yaml.safe_dump(descriptor), encoding="utf-8")
    (source / "model-materials.json").write_bytes(material_bytes)
    runner = {
        "asset": {
            "abi_version": 1,
            "entrypoint": "run",
            "path": "assets/runner.py",
            "sha256": asset_digest,
        },
        "callbacks": [
            {
                "child_contract_digest": child_digest,
                "max_calls": 1,
                "max_concurrency": 1,
                "max_request_bytes": 1024,
                "max_response_bytes": 1024,
                "max_total_request_bytes": 1024,
                "max_total_response_bytes": 1024,
                "name": "embed",
                "requirement": "embedding.execute.v1",
                "timeout_milliseconds": 100,
            }
        ],
        "capability_requirements_digest": requirements.digest,
        "child_contract_digests": [child_digest],
        "format_version": 1,
        "inputs": [
            {
                "max_bytes": 1024,
                "media_type": "application/octet-stream",
                "required": False,
                "role": "prior_bundle",
                "schema_digest": None,
            },
            {
                "max_bytes": 1024,
                "media_type": "application/json",
                "required": False,
                "role": "prior_index_manifest",
                "schema_digest": None,
            },
            {
                "max_bytes": 1024,
                "media_type": "application/json",
                "required": True,
                "role": "snapshot",
                "schema_digest": None,
            },
        ],
        "limits": {
            "max_concurrency": 1,
            "max_cpu_milliseconds": 1,
            "max_io_bytes": 4096,
            "max_memory_bytes": 1,
            "max_runtime_milliseconds": 100,
        },
        "outputs": [
            {
                "max_bytes": 1024,
                "media_type": "application/json",
                "role": "coverage_report",
                "schema_digest": None,
            },
            {
                "max_bytes": 1024,
                "media_type": "application/octet-stream",
                "role": "index_bundle",
                "schema_digest": None,
            },
            {
                "max_bytes": 1024,
                "media_type": "application/json",
                "role": "index_manifest",
                "schema_digest": None,
            },
        ],
        "profile_digest": profile_digest,
        "schemas": [
            {
                "dialect": "json-schema-draft-2020-12",
                "path": "schemas/embed-request.json",
                "sha256": hashlib.sha256(request_schema).hexdigest(),
            },
            {
                "dialect": "json-schema-draft-2020-12",
                "path": "schemas/embed-response.json",
                "sha256": hashlib.sha256(response_schema).hexdigest(),
            },
        ],
    }
    runner["artifact_runner_digest"] = hashlib.sha256(
        json.dumps(runner, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    (source / "sealed-artifact-runner.json").write_text(
        json.dumps(runner, sort_keys=True, separators=(",", ":")), encoding="utf-8"
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


def test_local_host_enables_sealed_artifact_runner_only_with_a_resolver(
    tmp_path: Path,
) -> None:
    configure_local_host(
        root=tmp_path / "state",
        package_root=tmp_path / "packages",
        model_id="local-model",
        base_url="http://127.0.0.1:11434/v1",
    )

    class Resolver:
        def resolve(self, _descriptor, _policy, _revision):
            return object()

    unavailable = LocalWorkflowHost.open(tmp_path / "state")
    enabled = LocalWorkflowHost.open(
        tmp_path / "state", sealed_artifact_callback_resolver=Resolver()
    )

    with pytest.raises(LocalWorkflowHostError, match="sealed artifact runner"):
        unavailable.run_sealed_artifact(
            SealedArtifactInvocation("workflow", "invocation", {}), now=NOW
        )
    assert enabled._sealed_artifact_preparation is not None
    assert enabled._sealed_artifact_runner is not None


def test_local_host_composes_locked_inference_callback_from_receiver_inputs(
    tmp_path: Path,
) -> None:
    configure_local_host(
        root=tmp_path / "state",
        package_root=tmp_path / "packages",
        model_id="local-model",
        base_url="http://127.0.0.1:11434/v1",
    )
    contract = next(
        item
        for item in BUILTIN_CAPABILITY_CONTRACTS
        if item.capability_id == "model.generate.v1"
    )

    class Provider:
        def generate(self, **_kwargs: object) -> bytes:
            return b"{}"

    host = LocalWorkflowHost.open(
        tmp_path / "state",
        capability_catalog=CapabilityCatalog(
            BUILTIN_CAPABILITY_CONTRACTS,
            (
                CapabilityProvider(
                    "receiver-generate",
                    contract,
                    conformance_passed=True,
                    conformance_vector_ids=frozenset(
                        {
                            "bounded_io",
                            "deadline",
                            "redacted_failure",
                            "structured_value",
                        }
                    ),
                ),
            ),
        ),
        locked_inference_provider_registry=LockedInferenceProviderRegistry(
            (LockedInferenceProviderBinding("receiver-generate", contract, Provider()),)
        ),
        locked_inference_host_limits=LockedInferenceHostLimits(1, 100, 100, 100, 1),
    )

    assert host._sealed_artifact_preparation is not None
    assert host._sealed_artifact_runner is not None
    assert isinstance(
        host._sealed_artifact_runner._callback_resolver,
        LockedInferenceSealedArtifactCallbackResolver,
    )


def test_local_host_composes_embedding_callback_from_receiver_inputs(
    tmp_path: Path,
) -> None:
    configure_local_host(
        root=tmp_path / "state",
        package_root=tmp_path / "packages",
        model_id="local-model",
        base_url="http://127.0.0.1:11434/v1",
    )

    class Execution:
        def execute(self, **_kwargs):  # type: ignore[no-untyped-def]
            return ()

    projects = EmbeddingLimitProjectorRegistry(
        (
            EmbeddingLimitProjectorBinding(
                ExecutionDescriptorAbi("test-embedding", "1", "a" * 64),
                lambda _descriptor: EmbeddingBatchLimits(1, 1, 1, 1, 1),
            ),
        )
    )
    host = LocalWorkflowHost.open(
        tmp_path / "state",
        capability_catalog=CapabilityCatalog((), ()),
        embedding_execution=Execution(),
        embedding_limit_projectors=projects,
    )

    assert host._sealed_artifact_preparation is not None
    assert host._sealed_artifact_runner is not None
    assert isinstance(
        host._sealed_artifact_runner._callback_resolver,
        EmbeddingSealedArtifactCallbackResolver,
    )


def test_portable_embedding_zip_rejects_tampering_before_receiver_ingress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_root = tmp_path / "packages"
    source = package_root / "portable-embedding"
    shutil.copytree(TEMPLATE_ROOT, source)
    configuration = configure_local_host(
        root=tmp_path / "state",
        package_root=package_root,
        model_id="local-model",
        base_url="http://127.0.0.1:11434/v1",
    )
    profile = LocalModelProfileControlPlane(
        store=PrivateStateStore(tmp_path / "state")
    ).load(configuration.profile_id)
    snapshot = DocumentSnapshot.create(
        (SnapshotDocument("note", "text/plain", b"body"),),
        policy=DocumentSnapshotPolicy(1, 16, 64, ("text/plain",)),
    )
    embedding = CapabilityContract(
        "embedding.execute.v1", "1", "a" * 64, ("deterministic",)
    )
    runner_contract = CapabilityContract("model.execution.test.v1", "1", "b" * 64, ())
    abi = ExecutionDescriptorAbi("test-embedding-abi", "1", "c" * 64)
    _write_portable_embedding_sealed_package(
        source,
        profile_digest=profile.profile_digest,
        embedding_contract=embedding,
        runner_contract=runner_contract,
        abi=abi,
        snapshot=snapshot,
    )

    class Validator:
        identity = abi

        def validate(self, _descriptor: object) -> None:
            return None

    class Execution:
        calls = 0

        def execute(self, **_kwargs: object) -> tuple[object, ...]:
            self.calls += 1
            return ()

    execution = Execution()
    catalog = CapabilityCatalog(
        (embedding, runner_contract),
        (
            CapabilityProvider(
                "receiver-embedding", embedding, conformance_passed=True
            ),
            CapabilityProvider(
                "receiver-runner", runner_contract, conformance_passed=True
            ),
        ),
    )
    host = LocalWorkflowHost.open(
        tmp_path / "state",
        capability_catalog=catalog,
        descriptor_validators=ExecutionDescriptorValidatorRegistry((Validator(),)),
        embedding_execution=execution,
        embedding_limit_projectors=EmbeddingLimitProjectorRegistry(
            (
                EmbeddingLimitProjectorBinding(
                    abi, lambda _descriptor: EmbeddingBatchLimits(1, 32, 32, 2, 1)
                ),
            )
        ),
    )
    staged = host.preview_package(
        package_source_handle=host.select_package(source, now=NOW), now=NOW
    )
    archive = package_root / "portable-embedding.zip"
    export_staged_package(staged=staged, destination=archive)
    registration = host.register(
        workflow_id="portable-embedding",
        package_source_handle=host.select_package(archive, now=NOW),
        now=NOW,
    )
    revision = host._catalog.revision(
        registration.package_id, registration.revision_digest
    )
    asset = revision.package_root / "assets" / "runner.py"
    original_asset = asset.read_bytes()
    asset.chmod(0o600)
    asset.write_bytes(b"tampered")
    resolver = host._sealed_artifact_runner._callback_resolver
    events = _observe_sealed_artifact_receiver(host, resolver, monkeypatch)

    with pytest.raises(LocalWorkflowHostError, match="sealed artifact runner"):
        host.run_sealed_artifact(
            SealedArtifactInvocation(
                workflow_id=registration.workflow_id,
                invocation_id="run-1",
                input_handles={"snapshot": "unreadable"},
            ),
            now=NOW,
        )

    assert execution.calls == 0
    assert events == [
        "registration",
        "catalog_revision",
        "policy_compile",
        "descriptor_manifest_verify",
    ]
    asset.write_bytes(original_asset)
    prepared = host.prepare_sealed_artifact_input(
        workflow_id=registration.workflow_id,
        invocation_id="run-2",
        role="snapshot",
        media_type="application/json",
        schema_digest=None,
        content=snapshot.wire_bytes,
        expires_at=NOW + timedelta(minutes=1),
        now=NOW,
    )
    events.clear()

    result = host.run_sealed_artifact(
        SealedArtifactInvocation(
            workflow_id=registration.workflow_id,
            invocation_id="run-2",
            input_handles={"snapshot": prepared.handle_id},
        ),
        now=NOW,
    )

    assert execution.calls == 1
    assert [output.role for output in result.outputs] == [
        "coverage_report",
        "index_bundle",
        "index_manifest",
    ]
    assert result.receipt["status"] == "completed"
    assert b"body" not in repr((result.outputs, result.receipt)).encode()
    repeat = host.prepare_sealed_artifact_input(
        workflow_id=registration.workflow_id,
        invocation_id="run-3",
        role="snapshot",
        media_type="application/json",
        schema_digest=None,
        content=snapshot.wire_bytes,
        expires_at=NOW + timedelta(minutes=1),
        now=NOW,
    )
    repeated_result = host.run_sealed_artifact(
        SealedArtifactInvocation(
            workflow_id=registration.workflow_id,
            invocation_id="run-3",
            input_handles={"snapshot": repeat.handle_id},
        ),
        now=NOW,
    )

    assert execution.calls == 2
    assert repeated_result.receipt == result.receipt


def test_portable_snapshot_wire_digest_is_not_its_semantic_snapshot_digest() -> None:
    snapshot = DocumentSnapshot.create(
        (SnapshotDocument("note", "text/plain", b"body"),),
        policy=DocumentSnapshotPolicy(1, 16, 64, ("text/plain",)),
    )

    decoded = DocumentSnapshot.from_wire_bytes(snapshot.wire_bytes)

    assert decoded.snapshot_digest == snapshot.snapshot_digest
    assert hashlib.sha256(snapshot.wire_bytes).hexdigest() != snapshot.snapshot_digest


def test_local_host_rejects_partial_embedding_callback_configuration(
    tmp_path: Path,
) -> None:
    configure_local_host(
        root=tmp_path / "state",
        package_root=tmp_path / "packages",
        model_id="local-model",
        base_url="http://127.0.0.1:11434/v1",
    )

    class Execution:
        def execute(self, **_kwargs):  # type: ignore[no-untyped-def]
            return ()

    with pytest.raises(
        LocalWorkflowHostError, match="embedding execution configuration"
    ):
        LocalWorkflowHost.open(
            tmp_path / "state",
            capability_catalog=CapabilityCatalog((), ()),
            embedding_execution=Execution(),
        )


def test_local_host_runs_locked_inference_from_a_staged_zip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_root = tmp_path / "packages"
    source = package_root / "locked-inference"
    shutil.copytree(TEMPLATE_ROOT, source)
    configuration = configure_local_host(
        root=tmp_path / "state",
        package_root=package_root,
        model_id="local-model",
        base_url="http://127.0.0.1:11434/v1",
    )
    profile = LocalModelProfileControlPlane(
        store=PrivateStateStore(tmp_path / "state")
    ).load(configuration.profile_id)
    contract = next(
        item
        for item in BUILTIN_CAPABILITY_CONTRACTS
        if item.capability_id == "model.generate.v1"
    )
    runner_contract = CapabilityContract("model.execution.test.v1", "1", "c" * 64, ())
    request = _write_locked_inference_sealed_package(
        source,
        profile_digest=profile.profile_digest,
        contract=contract,
        runner_contract=runner_contract,
    )

    class Provider:
        calls = 0
        fail = False

        def generate(self, **_kwargs: object) -> bytes:
            self.calls += 1
            events.append("provider_entry")
            if self.fail:
                raise RuntimeError("provider failure")
            return b'{"value":"ok"}'

    provider = Provider()
    catalog = CapabilityCatalog(
        (*BUILTIN_CAPABILITY_CONTRACTS, runner_contract),
        (
            CapabilityProvider(
                "receiver-generate",
                contract,
                conformance_passed=True,
                conformance_vector_ids=frozenset(
                    {"bounded_io", "deadline", "redacted_failure", "structured_value"}
                ),
            ),
            CapabilityProvider(
                "receiver-runner", runner_contract, conformance_passed=True
            ),
        ),
    )
    host = LocalWorkflowHost.open(
        tmp_path / "state",
        capability_catalog=catalog,
        locked_inference_provider_registry=LockedInferenceProviderRegistry(
            (LockedInferenceProviderBinding("receiver-generate", contract, provider),)
        ),
        locked_inference_host_limits=LockedInferenceHostLimits(1, 100, 100, 100, 1),
    )
    staged = host.preview_package(
        package_source_handle=host.select_package(source, now=NOW), now=NOW
    )
    archive = package_root / "locked-inference.zip"
    export_staged_package(staged=staged, destination=archive)
    registration = host.register(
        workflow_id="locked-inference",
        package_source_handle=host.select_package(archive, now=NOW),
        now=NOW,
    )
    prepared = host.prepare_sealed_artifact_input(
        workflow_id=registration.workflow_id,
        invocation_id="run-1",
        role="request",
        media_type="application/json",
        schema_digest=hashlib.sha256(
            b'{"max_depth":2,"max_items":1,"properties":{"value":'
            b'{"max_string_bytes":16,"type":"string"}},"required":["value"],'
            b'"type":"object"}'
        ).hexdigest(),
        content=request,
        expires_at=NOW + timedelta(minutes=1),
        now=NOW,
    )
    revision = host._catalog.revision(
        registration.package_id, registration.revision_digest
    )
    revision.package_root.chmod(0o700)
    instruction_asset = revision.package_root / "assets" / "instruction.txt"
    instruction_asset.chmod(0o600)
    instruction_asset.write_bytes(b"tampered")
    events = _observe_sealed_artifact_receiver(
        host, host._sealed_artifact_runner._callback_resolver, monkeypatch
    )
    import dynamic_agent_runner.workflow_host.locked_inference_sealed_artifact_callback as callback_module

    verify_role_assets = callback_module.read_verified_inference_role_assets

    def observe_role_assets(*args, **kwargs):
        events.append("locked_role_asset_verify")
        return verify_role_assets(*args, **kwargs)

    catalog_revalidate = catalog.revalidate

    def observe_provider_revalidation(*args, **kwargs):
        events.append("provider_revalidation")
        return catalog_revalidate(*args, **kwargs)

    monkeypatch.setattr(
        callback_module, "read_verified_inference_role_assets", observe_role_assets
    )
    monkeypatch.setattr(catalog, "revalidate", observe_provider_revalidation)

    with pytest.raises(LocalWorkflowHostError, match="sealed artifact runner"):
        host.run_sealed_artifact(
            SealedArtifactInvocation(
                workflow_id=registration.workflow_id,
                invocation_id="run-1",
                input_handles={"request": prepared.handle_id},
            ),
            now=NOW,
        )

    assert provider.calls == 0
    assert events == ["registration", "catalog_revision", "policy_compile"]
    instruction_asset.write_bytes(b"sealed instruction")
    events.clear()

    result = host.run_sealed_artifact(
        SealedArtifactInvocation(
            workflow_id=registration.workflow_id,
            invocation_id="run-1",
            input_handles={"request": prepared.handle_id},
        ),
        now=NOW,
    )

    assert provider.calls == 1
    assert [output.role for output in result.outputs] == ["result"]
    assert result.receipt == {
        "callback_count": 1,
        "descriptor_digest": result.receipt["descriptor_digest"],
        "output_bytes": len(b'{"value":"ok"}'),
        "output_count": 1,
        "status": "completed",
    }
    assert b'{"value":"ok"}' not in repr((result.outputs, result.receipt)).encode()
    assert events == [
        "registration",
        "catalog_revision",
        "policy_compile",
        "descriptor_manifest_verify",
        "callback_provider_resolution",
        "provider_revalidation",
        "locked_role_asset_verify",
        "handle_reservation",
        "collector_allocation",
        "asset_read",
        "input_byte_read",
        "provider_revalidation",
        "provider_entry",
        "collector_seal",
        "output_handle_publication",
    ]
    output_store = PrivateStateStore(tmp_path / "state")
    published_before = output_store.active_records(
        kind="sealed_artifact_output_set",
        owner=InstallationIdentityProvider().principal,
        now=NOW,
    )
    failed = host.prepare_sealed_artifact_input(
        workflow_id=registration.workflow_id,
        invocation_id="run-2",
        role="request",
        media_type="application/json",
        schema_digest=hashlib.sha256(
            b'{"max_depth":2,"max_items":1,"properties":{"value":'
            b'{"max_string_bytes":16,"type":"string"}},"required":["value"],'
            b'"type":"object"}'
        ).hexdigest(),
        content=request,
        expires_at=NOW + timedelta(minutes=1),
        now=NOW,
    )
    provider.fail = True
    events.clear()

    with pytest.raises(LocalWorkflowHostError, match="sealed artifact runner"):
        host.run_sealed_artifact(
            SealedArtifactInvocation(
                workflow_id=registration.workflow_id,
                invocation_id="run-2",
                input_handles={"request": failed.handle_id},
            ),
            now=NOW,
        )

    assert provider.calls == 2
    assert (
        output_store.active_records(
            kind="sealed_artifact_output_set",
            owner=InstallationIdentityProvider().principal,
            now=NOW,
        )
        == published_before
    )
    assert events[-2:] == ["provider_revalidation", "provider_entry"]
    assert "collector_seal" not in events
    assert "output_handle_publication" not in events


def test_local_host_rejects_partial_locked_inference_configuration(
    tmp_path: Path,
) -> None:
    configure_local_host(
        root=tmp_path / "state",
        package_root=tmp_path / "packages",
        model_id="local-model",
        base_url="http://127.0.0.1:11434/v1",
    )

    with pytest.raises(
        LocalWorkflowHostError,
        match="locked inference configuration is unavailable",
    ):
        LocalWorkflowHost.open(
            tmp_path / "state",
            locked_inference_host_limits=LockedInferenceHostLimits(1, 100, 100, 100, 1),
        )


def test_locked_inference_registration_rejects_tampered_role_before_preparation(
    tmp_path: Path,
) -> None:
    package_root = tmp_path / "packages"
    source = package_root / "locked-inference"
    shutil.copytree(TEMPLATE_ROOT, source)
    configuration = configure_local_host(
        root=tmp_path / "state",
        package_root=package_root,
        model_id="local-model",
        base_url="http://127.0.0.1:11434/v1",
    )
    profile = LocalModelProfileControlPlane(
        store=PrivateStateStore(tmp_path / "state")
    ).load(configuration.profile_id)
    contract = next(
        item
        for item in BUILTIN_CAPABILITY_CONTRACTS
        if item.capability_id == "model.generate.v1"
    )
    runner_contract = CapabilityContract("model.execution.test.v1", "1", "c" * 64, ())
    _write_locked_inference_sealed_package(
        source,
        profile_digest=profile.profile_digest,
        contract=contract,
        runner_contract=runner_contract,
    )
    descriptor_path = source / "workflow-descriptor.yaml"
    descriptor = yaml.safe_load(descriptor_path.read_text(encoding="utf-8"))
    descriptor["inference_roles"]["roles"][0]["capability_id"] = "other.generate.v1"
    descriptor_path.write_text(yaml.safe_dump(descriptor), encoding="utf-8")
    catalog = CapabilityCatalog(
        (*BUILTIN_CAPABILITY_CONTRACTS, runner_contract),
        (
            CapabilityProvider("receiver-generate", contract, conformance_passed=True),
            CapabilityProvider(
                "receiver-runner", runner_contract, conformance_passed=True
            ),
        ),
    )
    host = LocalWorkflowHost.open(
        tmp_path / "state",
        capability_catalog=catalog,
        locked_inference_provider_registry=LockedInferenceProviderRegistry(
            (LockedInferenceProviderBinding("receiver-generate", contract, object()),)  # type: ignore[arg-type]
        ),
        locked_inference_host_limits=LockedInferenceHostLimits(1, 100, 100, 100, 1),
    )
    with pytest.raises(ValueError, match="package descriptor"):
        host.register(
            workflow_id="locked-inference",
            package_source_handle=host.select_package(source, now=NOW),
            now=NOW,
        )


def test_local_host_rejects_tampered_asset_and_missing_handle_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_root = tmp_path / "packages"
    source = package_root / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
    configuration = configure_local_host(
        root=tmp_path / "state",
        package_root=package_root,
        model_id="local-model",
        base_url="http://127.0.0.1:11434/v1",
    )
    profile = LocalModelProfileControlPlane(
        store=PrivateStateStore(tmp_path / "state")
    ).load(configuration.profile_id)
    requirements = CapabilityRequirements()
    workflow_descriptor = source / "workflow-descriptor.yaml"
    workflow = yaml.safe_load(workflow_descriptor.read_text(encoding="utf-8"))
    workflow["dar_runtime"]["required_version"] = "0.1.18"
    workflow["capability_requirements"] = {
        "format_version": 1,
        "required_capabilities": [],
        "capability_requirements_digest": requirements.digest,
        "bindings": {},
    }
    workflow_descriptor.write_text(yaml.safe_dump(workflow), encoding="utf-8")
    asset = (
        b"def run(context):\n"
        b"    context.write_output('result', 'application/octet-stream', context.read_input('snapshot'))\n"
    )
    (source / "assets").mkdir()
    (source / "assets" / "runner.py").write_bytes(asset)
    runner_descriptor = {
        "asset": {
            "abi_version": 1,
            "entrypoint": "run",
            "path": "assets/runner.py",
            "sha256": hashlib.sha256(asset).hexdigest(),
        },
        "callbacks": [],
        "capability_requirements_digest": requirements.digest,
        "child_contract_digests": [],
        "format_version": 1,
        "inputs": [
            {
                "max_bytes": 12,
                "media_type": "application/octet-stream",
                "required": True,
                "role": "snapshot",
                "schema_digest": None,
            }
        ],
        "limits": {
            "max_concurrency": 1,
            "max_cpu_milliseconds": 1,
            "max_io_bytes": 100,
            "max_memory_bytes": 1,
            "max_runtime_milliseconds": 100,
        },
        "outputs": [
            {
                "max_bytes": 12,
                "media_type": "application/octet-stream",
                "role": "result",
                "schema_digest": None,
            }
        ],
        "profile_digest": profile.profile_digest,
        "schemas": [],
    }
    runner_descriptor["artifact_runner_digest"] = hashlib.sha256(
        json.dumps(runner_descriptor, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    (source / "sealed-artifact-runner.json").write_text(
        json.dumps(runner_descriptor, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )

    class Callbacks:
        def revalidate(self, _callback) -> None:
            return None

        def invoke(self, _name: str, _request: bytes) -> bytes:
            raise AssertionError("no callback is declared")

    class Resolver:
        calls = 0

        def resolve(self, _descriptor, _policy, _revision) -> Callbacks:
            self.calls += 1
            return Callbacks()

    resolver = Resolver()
    host = LocalWorkflowHost.open(
        tmp_path / "state", sealed_artifact_callback_resolver=resolver
    )
    staged = host.preview_package(
        package_source_handle=host.select_package(source, now=NOW), now=NOW
    )
    archive = package_root / "document-helper.zip"
    export_staged_package(staged=staged, destination=archive)
    registration = host.register(
        workflow_id="document-helper",
        package_source_handle=host.select_package(archive, now=NOW),
        now=NOW,
    )
    prepared = host.prepare_sealed_artifact_input(
        workflow_id=registration.workflow_id,
        invocation_id="run-1",
        role="snapshot",
        media_type="application/octet-stream",
        schema_digest=None,
        content=b"snapshot",
        expires_at=NOW + timedelta(minutes=1),
        now=NOW,
    )
    resolver.calls = 0

    revision = host._catalog.revision(
        registration.package_id, registration.revision_digest
    )
    revision.package_root.chmod(0o700)
    staged_asset = revision.package_root / "assets" / "runner.py"
    staged_asset.chmod(0o600)
    staged_asset.write_bytes(b"tampered")
    output_store = PrivateStateStore(tmp_path / "state")
    events = _observe_sealed_artifact_receiver(host, resolver, monkeypatch)

    with pytest.raises(LocalWorkflowHostError, match="sealed artifact runner"):
        host.run_sealed_artifact(
            SealedArtifactInvocation(
                workflow_id=registration.workflow_id,
                invocation_id="run-1",
                input_handles={"snapshot": prepared.handle_id},
            ),
            now=NOW,
        )

    assert resolver.calls == 0
    assert events == [
        "registration",
        "catalog_revision",
        "policy_compile",
        "descriptor_manifest_verify",
    ]
    assert not output_store.active_records(
        kind="sealed_artifact_output_set",
        owner=InstallationIdentityProvider().principal,
        now=NOW,
    )
    staged_asset.write_bytes(asset)
    events.clear()

    with pytest.raises(LocalWorkflowHostError, match="sealed artifact runner"):
        host.run_sealed_artifact(
            SealedArtifactInvocation(
                workflow_id=registration.workflow_id,
                invocation_id="run-1",
                input_handles={"snapshot": "missing-handle"},
            ),
            now=NOW,
        )

    assert resolver.calls == 1
    assert events == [
        "registration",
        "catalog_revision",
        "policy_compile",
        "descriptor_manifest_verify",
        "callback_provider_resolution",
        "handle_reservation",
    ]
    assert not output_store.active_records(
        kind="sealed_artifact_output_set",
        owner=InstallationIdentityProvider().principal,
        now=NOW,
    )
    events.clear()

    result = host.run_sealed_artifact(
        SealedArtifactInvocation(
            workflow_id=registration.workflow_id,
            invocation_id="run-1",
            input_handles={"snapshot": prepared.handle_id},
        ),
        now=NOW,
    )

    assert [handle.role for handle in result.outputs] == ["result"]
    assert result.receipt["status"] == "completed"
    assert resolver.calls == 2
    assert events == [
        "registration",
        "catalog_revision",
        "policy_compile",
        "descriptor_manifest_verify",
        "callback_provider_resolution",
        "handle_reservation",
        "collector_allocation",
        "asset_read",
        "input_byte_read",
        "collector_seal",
        "output_handle_publication",
    ]


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


def _reviewed_template(
    *, extension_binding: str = "host-vector-index-v1"
) -> ReviewedCapabilityTemplate:
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
        "extension_binding": extension_binding,
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
    return ReviewedCapabilityTemplate(
        template_digest=reviewed_capability_template_digest(**values), **values
    )


class _FakeReviewedCapabilityHost:
    def resolve(self, **_kwargs: object) -> object:
        return object()

    def revalidate(self, **_kwargs: object) -> object:
        return object()

    def dispatch(self, **_kwargs: object) -> None:
        return None

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


def _reviewed_extension(
    extension_binding: str = "host-vector-index-v1",
) -> ReviewedCapabilityHostExtension:
    return ReviewedCapabilityHostExtension(
        template=_reviewed_template(extension_binding=extension_binding),
        host=_FakeReviewedCapabilityHost(),
    )


def test_local_host_discovers_only_explicitly_registered_reviewed_templates(
    tmp_path: Path,
) -> None:
    configure_local_host(
        root=tmp_path / "state",
        package_root=tmp_path / "packages",
        model_id="local-model",
        base_url="http://127.0.0.1:11434/v1",
    )
    configure_local_host(
        root=tmp_path / "enabled-state",
        package_root=tmp_path / "enabled-packages",
        model_id="local-model",
        base_url="http://127.0.0.1:11434/v1",
    )

    unavailable = LocalWorkflowHost.open(tmp_path / "state")
    with pytest.raises(LocalWorkflowHostError, match="reviewed capability"):
        LocalWorkflowHost.open(
            tmp_path / "enabled-state",
            reviewed_capability_templates=(_reviewed_template(),),
        )
    enabled = LocalWorkflowHost.open(
        tmp_path / "enabled-state",
        reviewed_capability_extensions=(_reviewed_extension(),),
    )

    assert (
        unavailable.discover_reviewed_capability_template(
            capability_id="vector_index.build.v1"
        ).status
        == "authoring_runtime_unavailable"
    )
    discovered = enabled.discover_reviewed_capability_template(
        capability_id="vector_index.build.v1"
    )
    assert discovered.status == "available"
    assert discovered.capability_id == "vector_index.build.v1"
    assert discovered.input_fields == ("job_handle",)
    restarted = LocalWorkflowHost.open(
        tmp_path / "enabled-state",
        reviewed_capability_extensions=(_reviewed_extension(),),
    )
    assert (
        restarted.discover_reviewed_capability_template(
            capability_id="vector_index.build.v1"
        )
        == discovered
    )
    removed = LocalWorkflowHost.open(tmp_path / "enabled-state")
    assert (
        removed.discover_reviewed_capability_template(
            capability_id="vector_index.build.v1"
        ).status
        == "authoring_runtime_unavailable"
    )
    with pytest.raises(LocalWorkflowHostError, match="reviewed capability"):
        LocalWorkflowHost.open(
            tmp_path / "enabled-state",
            reviewed_capability_extensions=(
                _reviewed_extension(extension_binding="changed-host-extension"),
            ),
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


def test_host_refreshes_a_saved_registration_without_a_package_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_root = tmp_path / "packages"
    source = package_root / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
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
    source_handle = host.select_package(source, now=NOW)
    registration = host.register(
        workflow_id="document-helper", package_source_handle=source_handle, now=NOW
    )

    refreshed = host.refresh_saved_registration(workflow_id="document-helper")

    assert refreshed.workflow_id == registration.workflow_id
    assert refreshed.package_id == registration.package_id
    assert refreshed.revision_digest == registration.revision_digest


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


def test_host_refresh_rebinds_a_changed_policy_to_its_current_reviewed_surface(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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
        package_source_handle=source_handle, snapshot_id=snapshot.snapshot_id, now=NOW
    )
    registration = host.register(
        workflow_id="mail-reader",
        package_source_handle=source_handle,
        mcp_binding_id=binding.binding_id,
        now=NOW,
    )
    revision = host._catalog.revision(
        registration.package_id, registration.revision_digest
    )
    refreshed_policy = replace(
        compile_workflow_policy(
            revision,
            capability_catalog=host._capability_catalog,
            descriptor_validators=host._descriptor_validators,
        ),
        policy_digest="f" * 64,
    )
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.host.compile_workflow_policy",
        lambda *_args, **_kwargs: refreshed_policy,
    )

    refreshed = host.refresh_saved_registration(workflow_id="mail-reader")

    assert refreshed.policy_digest == refreshed_policy.policy_digest
    assert refreshed.mcp_binding_id is not None
    assert refreshed.mcp_binding_id != binding.binding_id
    assert host._mcp_bindings is not None
    original_load = host._mcp_bindings.load

    def unavailable_binding(binding_id: str):
        if binding_id == refreshed.mcp_binding_id:
            raise MCPWorkflowCapabilityBindingError("unavailable")
        return original_load(binding_id)

    monkeypatch.setattr(
        host._mcp_bindings,
        "load",
        unavailable_binding,
    )

    with pytest.raises(LocalWorkflowHostError, match="MCP package binding"):
        host.refresh_saved_registration(workflow_id="mail-reader")

    assert host._registrations.resolve("mail-reader") == refreshed

    refreshed_with_current_snapshot = host.refresh_saved_registration(
        workflow_id="mail-reader", mcp_snapshot_id=snapshot.snapshot_id
    )

    assert (
        refreshed_with_current_snapshot.policy_digest == refreshed_policy.policy_digest
    )
    assert refreshed_with_current_snapshot.mcp_binding_id is not None
    assert refreshed_with_current_snapshot.mcp_binding_id != refreshed.mcp_binding_id

    assert host._registrations.resolve("mail-reader") == refreshed_with_current_snapshot


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
    value["dar_runtime"]["required_version"] = "0.1.18"
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
    configure_local_host(
        root=tmp_path / "state",
        package_root=package_root,
        workspace_input_root=input_root,
        model_id="local-model-v1",
        base_url="http://127.0.0.1:11434/v1",
    )
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
    no_catalog_host = LocalWorkflowHost.open(tmp_path / "state")
    no_catalog_source = no_catalog_host.select_package(source, now=NOW)

    with pytest.raises(PolicyCompilationError, match="capability"):
        no_catalog_host.register(
            workflow_id="without-catalog",
            package_source_handle=no_catalog_source,
            now=NOW,
        )

    host = LocalWorkflowHost.open(
        tmp_path / "state", capability_catalog=available_catalog
    )
    assert host._capability_catalog is available_catalog
    assert host._preparation._capability_catalog is available_catalog
    assert host._runner._capability_catalog is available_catalog
    source_handle = host.select_package(source, now=NOW)
    registration = host.register(
        workflow_id="document-helper", package_source_handle=source_handle, now=NOW
    )
    prepared = host.prepare(
        workflow_id=registration.workflow_id, prompt="Answer the request.", now=NOW
    )
    result = host.run(
        workflow_id=registration.workflow_id,
        prepared_input_id=prepared.prepared_input_id,
        now=NOW,
    )

    assert result.output == {"message": "completed locally"}
    assert len(client.responses.calls) == 1

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
    with pytest.raises(LocalWorkflowHostError, match="saved package"):
        host.invoke_saved(
            package_name=registration.workflow_id,
            prompt="Answer the request.",
            workspace_files=(),
            dry_run=True,
            approval_broker=None,
            now=NOW,
        )
