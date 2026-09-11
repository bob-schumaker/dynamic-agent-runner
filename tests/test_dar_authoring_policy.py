"""Tests for DAR authoring's immutable no-tool workflow policy."""

from __future__ import annotations

import shutil
import stat
import json
from hashlib import sha256
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml


from dynamic_agent_runner.workflow_host.catalog import PackageCatalog  # noqa: E402
from dynamic_agent_runner.workflow_host.capabilities import (  # noqa: E402
    BUILTIN_CAPABILITY_CONTRACTS,
    CapabilityCatalog,
    CapabilityContract,
    CapabilityProvider,
    CapabilityRequirement,
    CapabilityRequirements,
)
from dynamic_agent_runner.workflow_host.model_materials import (  # noqa: E402
    parse_model_dependency_lock,
)
from dynamic_agent_runner.workflow_host.execution_descriptors import (  # noqa: E402
    ExecutionDescriptorAbi,
    ExecutionDescriptorValidatorRegistry,
    parse_execution_descriptor,
)
import dynamic_agent_runner.workflow_host.policy as policy_module  # noqa: E402
from dynamic_agent_runner.workflow_host.package_sources import (
    PackageSourceSelectionPolicy,
)  # noqa: E402
from dynamic_agent_runner.workflow_host.policy import (  # noqa: E402
    PolicyCompilationError,
    compile_workflow_policy,
    resolve_capabilities,
)
from dynamic_agent_runner.workflow_host.staging import (  # noqa: E402
    PackageStagingError,
    PrivatePackageStager,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore  # noqa: E402


NOW = datetime(2026, 8, 23, tzinfo=UTC)
TEMPLATE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "specs"
    / "agent-engineering-plugin-migration"
    / "legacy-dar-authoring"
    / "templates"
)


def _catalog_revision(  # noqa: C901
    tmp_path: Path,
    *,
    package_id: str | None = None,
    with_read_only_mcp_tool: bool = False,
    with_side_effecting_mcp_tool: bool = False,
    with_local_tool: bool = False,
    package_skill_id: str | None = None,
    package_skill_bundled_path: str | None = None,
    enable_package_skill_source_resolution: bool = True,
    terminal_output_schema_ref: str | None = None,
    deferred_capability: str | None = None,
    input_converter_asset: bytes | None = None,
    input_converter_digest: str | None = None,
    capability_requirements: dict[str, object] | None = None,
    model_materials: dict[str, object] | None = None,
    execution_descriptor: dict[str, object] | None = None,
    model_material_sets: dict[str, object] | None = None,
    inference_roles: dict[str, object] | None = None,
    inference_role_assets: dict[str, bytes] | None = None,
):
    source = tmp_path / "packages" / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
    if model_materials is not None:
        (source / "model-materials.json").write_text(
            json.dumps(model_materials, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
    if execution_descriptor is not None:
        (source / "execution-descriptor.json").write_text(
            json.dumps(execution_descriptor, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
    if model_material_sets is not None:
        (source / "model-material-sets.json").write_text(
            json.dumps(model_material_sets, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
    if inference_roles is not None:
        descriptor = source / "workflow-descriptor.yaml"
        descriptor_value = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
        descriptor_value["inference_roles"] = inference_roles
        descriptor.write_text(yaml.safe_dump(descriptor_value), encoding="utf-8")
    if inference_role_assets is not None:
        for path, content in inference_role_assets.items():
            asset = source / path
            asset.parent.mkdir(parents=True, exist_ok=True)
            asset.write_bytes(content)
    if package_id is not None:
        descriptor = source / "workflow-descriptor.yaml"
        descriptor.write_text(
            descriptor.read_text(encoding="utf-8").replace(
                "dar-authoring-no-tool-template", package_id
            ),
            encoding="utf-8",
        )
    if terminal_output_schema_ref is not None:
        descriptor = source / "workflow-descriptor.yaml"
        descriptor_value = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
        descriptor_value["output"]["schema_ref"] = terminal_output_schema_ref
        descriptor_value["task_invocation"]["terminal_output_schema_ref"] = (
            terminal_output_schema_ref
        )
        descriptor.write_text(yaml.safe_dump(descriptor_value), encoding="utf-8")
    if with_read_only_mcp_tool:
        descriptor = source / "workflow-descriptor.yaml"
        descriptor_value = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
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
        descriptor.write_text(yaml.safe_dump(descriptor_value), encoding="utf-8")
        runtime = source / "agent-runtime.yaml"
        runtime_value = yaml.safe_load(runtime.read_text(encoding="utf-8"))
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
    if with_side_effecting_mcp_tool:
        descriptor = source / "workflow-descriptor.yaml"
        descriptor_value = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
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
                "max_total_tool_calls": 1,
                "allowed_structured_input_fields": ["recipient"],
                "allowed_artifact_roles": ["email_body"],
                "argument_sources": {
                    "mail_send": {
                        "recipient": {
                            "sources": ["sealed_structured_field:recipient"],
                            "authority": True,
                        },
                        "body": {
                            "sources": ["artifact_role:email_body"],
                            "authority": False,
                        },
                    }
                },
            }
        )
        descriptor.write_text(yaml.safe_dump(descriptor_value), encoding="utf-8")
        runtime = source / "agent-runtime.yaml"
        runtime_value = yaml.safe_load(runtime.read_text(encoding="utf-8"))
        runtime_value["tools"] = [
            {
                "id": "mail_send",
                "label": "Send mail",
                "tool_type": "external_api",
                "description_for_llm": "Send one reviewed email.",
                "adapter": "host.mcp",
                "input_schema": {
                    "type": "object",
                    "properties": {"envelope": {"type": "string"}},
                    "required": ["envelope"],
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
    if with_local_tool:
        descriptor = source / "workflow-descriptor.yaml"
        descriptor_value = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
        descriptor_value["tools"] = [
            {
                "id": "inspect_binary",
                "kind": "local",
                "asset_path": "tools/inspect_binary",
                "accepted_artifact_role": "source_binary",
                "max_input_bytes": 1024,
                "max_output_bytes": 1024,
                "timeout_seconds": 1,
            }
        ]
        descriptor_value["task_invocation"].update(
            {
                "allowed_tool_ids": ["inspect_binary"],
                "allowed_artifact_roles": ["source_binary"],
                "max_total_tool_calls": 1,
            }
        )
        descriptor.write_text(yaml.safe_dump(descriptor_value), encoding="utf-8")
        runtime = source / "agent-runtime.yaml"
        runtime_value = yaml.safe_load(runtime.read_text(encoding="utf-8"))
        runtime_value["tools"] = [
            {
                "id": "inspect_binary",
                "label": "Inspect binary",
                "tool_type": "external_api",
                "description_for_llm": "Inspect the sealed binary.",
                "adapter": "host.local",
                "input_schema": {"type": "object", "properties": {}},
                "side_effect": "read",
                "approval_required": False,
                "timeout": "runtime_default",
                "retry_policy": "none",
                "failure_behavior": "error",
            }
        ]
        runtime_value["nodes"][0]["available_tools"] = ["inspect_binary"]
        runtime.write_text(yaml.safe_dump(runtime_value), encoding="utf-8")
        asset = source / "tools" / "inspect_binary"
        asset.parent.mkdir()
        asset.write_text("placeholder", encoding="utf-8")
    if package_skill_id is not None:
        descriptor = source / "workflow-descriptor.yaml"
        descriptor_value = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
        descriptor_value["skills"] = [package_skill_id]
        descriptor.write_text(yaml.safe_dump(descriptor_value), encoding="utf-8")
        bundled_path = (
            package_skill_bundled_path or f"skills/{package_skill_id}/SKILL.md"
        )
        skill_path = source / "skill-bundle" / bundled_path
        skill_path.parent.mkdir(parents=True)
        skill_path.write_text("# Package guidance\nUse package-local guidance.\n")
        runtime = source / "agent-runtime.yaml"
        runtime_value = yaml.safe_load(runtime.read_text(encoding="utf-8"))
        runtime_value["packaging"]["skill_bundle_dir"] = "skill-bundle"
        if enable_package_skill_source_resolution:
            runtime_value["runtime"]["execution_policy"]["skill_source_resolution"] = {
                "enabled": True,
                "allowed_sources": ["package_bundle"],
                "max_skill_bytes": 65536,
                "max_node_skill_bytes": 262144,
                "load_support_files": False,
                "prompt_role": "developer",
            }
        runtime_value["skills"] = [
            {
                "id": package_skill_id,
                "bundled_path": bundled_path,
            }
        ]
        runtime_value["nodes"][0]["skill_refs"] = [package_skill_id]
        runtime.write_text(yaml.safe_dump(runtime_value), encoding="utf-8")
    if deferred_capability is not None:
        descriptor = source / "workflow-descriptor.yaml"
        descriptor_value = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
        runtime = source / "agent-runtime.yaml"
        runtime_value = yaml.safe_load(runtime.read_text(encoding="utf-8"))
        _declare_deferred_runtime_capability(
            deferred_capability, descriptor_value, runtime_value
        )
        descriptor.write_text(yaml.safe_dump(descriptor_value), encoding="utf-8")
        runtime.write_text(yaml.safe_dump(runtime_value), encoding="utf-8")
    if input_converter_asset is not None:
        converter = source / "converters" / "qwen_floorplan.py"
        converter.parent.mkdir()
        converter.write_bytes(input_converter_asset)
        descriptor = source / "workflow-descriptor.yaml"
        descriptor_value = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
        descriptor_value["input_converter"] = {
            "converter_id": "qwen-floorplan-input-v1",
            "converter_contract_version": "v1",
            "compatible_runner_contract_id": "transformers-generate-v1",
            "entrypoint": "converters/qwen_floorplan.py",
            "asset_digest": input_converter_digest
            or sha256(input_converter_asset).hexdigest(),
            "declared_resource_limits": {
                "max_input_bytes": 8 * 1024 * 1024,
                "max_output_bytes": 1024,
                "timeout_seconds": 30,
            },
        }
        descriptor.write_text(yaml.safe_dump(descriptor_value), encoding="utf-8")
    _set_capability_requirements(source, capability_requirements)
    store = PrivateStateStore(tmp_path / "state")
    source_handle = PackageSourceSelectionPolicy(
        allowed_root=source.parent, store=store
    ).select_directory(source, now=NOW)
    staged = PrivatePackageStager(store=store, private_root=tmp_path / "staging").stage(
        source_handle, now=NOW
    )
    return PackageCatalog(tmp_path / "catalog").import_staged(staged)


def _set_capability_requirements(
    source: Path, requirements: dict[str, object] | None
) -> None:
    if requirements is None:
        return
    descriptor = source / "workflow-descriptor.yaml"
    descriptor_value = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
    descriptor_value["dar_runtime"]["required_version"] = "0.1.17"
    descriptor_value["capability_requirements"] = requirements
    descriptor.write_text(yaml.safe_dump(descriptor_value), encoding="utf-8")


def _declare_deferred_runtime_capability(
    capability: str, descriptor: dict[str, object], runtime: dict[str, object]
) -> None:
    execution_policy = runtime["runtime"]["execution_policy"]
    if capability == "context-pruning-pipeline":
        execution_policy["prepare_model_input"] = {
            "context_compaction": {
                "auto": {
                    "enabled": True,
                    "implementation": "basic",
                    "trigger": "token_threshold",
                    "scope": "current_run",
                }
            }
        }
    elif capability == "scratch-workspace":
        descriptor["workspace"]["scratch_access"] = "ephemeral"
    elif capability == "durable-session-continuation":
        execution_policy["async_session"] = {
            "mode": "create_or_resume",
            "persist": "external_checkpoint",
            "history": "summary",
            "session_id_state_key": "session_id",
            "session_messages_state_key": "session_messages",
        }
    elif capability == "native-approval-resume":
        execution_policy["approval_interruption"] = {
            "mode": "pause_on_approval",
            "persist": "external_checkpoint",
            "resume_from": "approval_decision",
            "pending_tool_calls_state_key": "pending_tool_calls",
            "pending_approvals_state_key": "pending_approvals",
            "interruption_state_key": "interruption_state",
            "resume_token_state_key": "resume_token",
        }
    elif capability == "collaboration-subagents":
        runtime.setdefault("metadata", {})["participant_groups"] = [
            {"id": "review-council"}
        ]
    elif capability == "retrieval-embedding-rag":
        runtime.setdefault("metadata", {}).update(
            {
                "patterns_present": ["rag", "embedding_retrieval"],
                "rag_pipeline": {
                    "retrieval_mode": "embedding_semantic",
                    "embedding_capability": "required",
                    "graph_capability": "not_applicable",
                    "index_owner": "runtime",
                    "graph_store_owner": "unknown",
                    "corpus_boundary": "fixture documents",
                    "chunking_policy": "runtime default",
                },
            }
        )
        runtime["nodes"][0]["model_requirements"] = {
            "required_capabilities": ["embeddings"]
        }
    else:
        raise AssertionError(f"unknown deferred capability: {capability}")


def test_policy_compiles_a_cataloged_no_tool_package(tmp_path: Path) -> None:
    policy = compile_workflow_policy(_catalog_revision(tmp_path))

    assert policy.package_id == "dar-authoring-no-tool-template"
    assert len(policy.descriptor_digest) == 64
    assert len(policy.policy_digest) == 64
    assert policy.required_capabilities == frozenset({"text_generation"})
    assert policy.workspace.accepted_input_types == ("text/plain",)


def test_policy_binds_the_canonical_capability_requirements_digest(
    tmp_path: Path,
) -> None:
    requirements = CapabilityRequirements()
    policy = compile_workflow_policy(
        _catalog_revision(
            tmp_path,
            capability_requirements={
                "format_version": 1,
                "required_capabilities": [],
                "capability_requirements_digest": requirements.digest,
                "bindings": {},
            },
        )
    )

    assert policy.capability_requirements == requirements
    assert policy.capability_requirements_digest == requirements.digest
    assert policy.policy_digest


def test_policy_binds_the_canonical_model_materials_digest(tmp_path: Path) -> None:
    materials = {
        "format_version": 1,
        "logical_model_id": "local-model",
        "runner_contract": {"id": "llama-cpp-v1", "version": "1"},
        "loader_profile_contract": {"id": "llama-cpp-text-v1", "version": "1"},
        "sources": [
            {
                "role": "base_model",
                "group": "base",
                "source_type": "huggingface_file",
                "repository": "example-org/example-model",
                "revision": "a" * 40,
                "filename": "model.gguf",
                "sha256": "b" * 64,
            }
        ],
        "preparation": [],
    }
    lock = parse_model_dependency_lock(materials)
    contract = CapabilityContract("model.execution.test.v1", "1", "c" * 64, ())
    requirements = CapabilityRequirements(
        (CapabilityRequirement(contract.capability_id, "1", "c" * 64, ()),),
        {"runner": contract.capability_id},
    )

    policy = compile_workflow_policy(
        _catalog_revision(
            tmp_path,
            model_materials=materials,
            capability_requirements={
                "format_version": 1,
                "required_capabilities": [
                    requirements.required_capabilities[0].to_mapping()
                ],
                "capability_requirements_digest": requirements.digest,
                "bindings": {"runner": {"capability_id": contract.capability_id}},
            },
        ),
        capability_catalog=CapabilityCatalog(
            (contract,),
            (
                CapabilityProvider(
                    "private-test-provider", contract, conformance_passed=True
                ),
            ),
        ),
    )

    assert policy.model_materials == lock
    assert policy.model_materials_digest == lock.digest


def test_policy_binds_named_material_sets_to_locked_inference_roles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = {
        "format_version": 1,
        "logical_model_id": "local-model",
        "runner_contract": {"id": "llama-cpp-v1", "version": "1"},
        "loader_profile_contract": {"id": "llama-cpp-text-v1", "version": "1"},
        "sources": [
            {
                "role": "base_model",
                "group": "base",
                "source_type": "huggingface_file",
                "repository": "example/model",
                "revision": "a" * 40,
                "filename": "model.gguf",
                "sha256": "b" * 64,
            }
        ],
        "preparation": [],
    }
    runner = CapabilityContract("model.execution.test.v1", "1", "c" * 64, ())
    generate = CapabilityContract("model.generate.v1", "1", "d" * 64, ("structured",))
    requirements = CapabilityRequirements(
        (
            CapabilityRequirement(runner.capability_id, "1", "c" * 64, ()),
            CapabilityRequirement(
                generate.capability_id, "1", "d" * 64, ("structured",)
            ),
        ),
        {"runner": runner.capability_id},
    )
    instruction = b"sealed instruction"
    schema = b'{"max_depth":2,"max_items":1,"properties":{"value":{"max_string_bytes":16,"type":"string"}},"required":["value"],"type":"object"}'
    assets = {
        "assets/instruction.txt": instruction,
        "assets/request.json": schema,
        "assets/response.json": schema,
    }
    inference_roles = {
        "format_version": 1,
        "roles": [
            {
                "role": "suggest",
                "material_role": "suggest",
                "capability_id": "model.generate.v1",
                "instruction_asset": {
                    "path": "assets/instruction.txt",
                    "sha256": sha256(instruction).hexdigest(),
                },
                "request_schema_asset": {
                    "path": "assets/request.json",
                    "sha256": sha256(schema).hexdigest(),
                },
                "response_schema_asset": {
                    "path": "assets/response.json",
                    "sha256": sha256(schema).hexdigest(),
                },
                "authorized_asset_digests": ["d" * 64],
                "limits": {
                    "max_calls": 1,
                    "max_input_bytes": 1,
                    "max_output_bytes": 1,
                    "timeout_milliseconds": 1,
                    "max_concurrency": 1,
                },
            }
        ],
    }
    revision = _catalog_revision(
        tmp_path,
        model_material_sets={
            "format_version": 1,
            "material_sets": [{"role": "suggest", "model_materials": lock}],
        },
        inference_roles=inference_roles,
        inference_role_assets=assets,
        capability_requirements={
            "format_version": 1,
            "required_capabilities": [
                item.to_mapping() for item in requirements.required_capabilities
            ],
            "capability_requirements_digest": requirements.digest,
            "bindings": {"runner": {"capability_id": runner.capability_id}},
        },
    )
    catalog = CapabilityCatalog(
        (runner, generate),
        (
            CapabilityProvider("private-runner", runner, conformance_passed=True),
            CapabilityProvider(
                "private-generate",
                generate,
                conformance_passed=True,
                conformance_vector_ids=frozenset(
                    {
                        "bounded_io",
                        "deadline",
                        "structured_value",
                        "redacted_failure",
                    }
                ),
            ),
        ),
    )
    policy = compile_workflow_policy(revision, capability_catalog=catalog)

    assert policy.model_materials is None
    assert policy.model_material_sets is not None
    assert policy.inference_roles_digest == policy.inference_roles.digest
    assert policy.locked_inference_bindings[0].role == "suggest"

    revision.package_root.chmod(0o700)
    asset = revision.package_root / "assets" / "request.json"
    asset.chmod(0o600)
    asset.write_bytes(b"tampered")
    monkeypatch.setattr(
        policy_module,
        "load_agent_package_workflow",
        lambda _path: pytest.fail("runtime manifest was loaded"),
    )

    with pytest.raises(PolicyCompilationError, match="locked inference binding"):
        compile_workflow_policy(
            revision,
            capability_catalog=catalog,
        )

    asset.write_bytes(schema)
    material_sets_path = revision.package_root / "model-material-sets.json"
    material_sets_path.chmod(0o600)
    material_sets = json.loads(material_sets_path.read_text(encoding="utf-8"))
    material_sets["material_sets"][0]["role"] = "other"
    material_sets_path.write_text(
        json.dumps(material_sets, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )

    with pytest.raises(PolicyCompilationError, match="locked inference binding"):
        compile_workflow_policy(
            revision,
            capability_catalog=catalog,
        )


def test_policy_derives_embedding_binding_before_workflow_import(
    tmp_path: Path,
) -> None:
    materials = {
        "format_version": 1,
        "logical_model_id": "local-embedding-model",
        "runner_contract": {"id": "llama-cpp-v1", "version": "1"},
        "loader_profile_contract": {"id": "llama-cpp-embedding-v1", "version": "1"},
        "sources": [
            {
                "role": "base_model",
                "group": "base",
                "source_type": "huggingface_file",
                "repository": "example-org/example-model",
                "revision": "a" * 40,
                "filename": "model.gguf",
                "sha256": "b" * 64,
            }
        ],
        "preparation": [],
    }
    embedding = CapabilityContract(
        "embedding.execute.v1", "1", "a" * 64, ("deterministic",)
    )
    runner = CapabilityContract("model.execution.test.v1", "1", "c" * 64, ())
    requirements = CapabilityRequirements(
        (
            CapabilityRequirement(
                embedding.capability_id,
                embedding.contract_version,
                embedding.contract_digest,
                ("deterministic",),
            ),
            CapabilityRequirement(
                runner.capability_id,
                runner.contract_version,
                runner.contract_digest,
                (),
            ),
        ),
        {"runner": runner.capability_id},
    )

    policy = compile_workflow_policy(
        _catalog_revision(
            tmp_path,
            model_materials=materials,
            capability_requirements={
                "format_version": 1,
                "required_capabilities": [
                    item.to_mapping() for item in requirements.required_capabilities
                ],
                "capability_requirements_digest": requirements.digest,
                "bindings": {"runner": {"capability_id": runner.capability_id}},
            },
        ),
        capability_catalog=CapabilityCatalog(
            (embedding, runner),
            (
                CapabilityProvider(
                    "embedding-provider", embedding, conformance_passed=True
                ),
                CapabilityProvider("runner-provider", runner, conformance_passed=True),
            ),
        ),
    )

    assert policy.embedding_execution_binding is not None
    assert (
        policy.embedding_execution_binding.material_lock_digest
        == policy.model_materials_digest
    )
    assert policy.embedding_execution_binding_digest


def test_unavailable_embedding_fails_before_import_or_model_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    embedding = CapabilityContract(
        "embedding.execute.v1", "1", "a" * 64, ("deterministic",)
    )
    requirement = CapabilityRequirement(
        embedding.capability_id,
        embedding.contract_version,
        embedding.contract_digest,
        ("deterministic",),
    )
    requirements = CapabilityRequirements((requirement,))
    revision = _catalog_revision(
        tmp_path,
        capability_requirements={
            "format_version": 1,
            "required_capabilities": [requirement.to_mapping()],
            "capability_requirements_digest": requirements.digest,
            "bindings": {},
        },
    )
    monkeypatch.setattr(
        policy_module,
        "load_agent_package_workflow",
        lambda _path: pytest.fail("runtime manifest was loaded"),
    )
    monkeypatch.setattr(
        policy_module,
        "_load_model_materials",
        lambda _root: pytest.fail("model material admission was attempted"),
    )

    with pytest.raises(PolicyCompilationError, match="capability"):
        compile_workflow_policy(
            revision, capability_catalog=CapabilityCatalog((embedding,), ())
        )


def test_model_materials_require_a_declared_runner_capability_binding(
    tmp_path: Path,
) -> None:
    materials = {
        "format_version": 1,
        "logical_model_id": "local-model",
        "runner_contract": {"id": "llama-cpp-v1", "version": "1"},
        "loader_profile_contract": {"id": "llama-cpp-text-v1", "version": "1"},
        "sources": [
            {
                "role": "base_model",
                "group": "base",
                "source_type": "huggingface_file",
                "repository": "example-org/example-model",
                "revision": "a" * 40,
                "filename": "model.gguf",
                "sha256": "b" * 64,
            }
        ],
        "preparation": [],
    }

    with pytest.raises(PolicyCompilationError, match="runner capability"):
        compile_workflow_policy(_catalog_revision(tmp_path, model_materials=materials))


def test_model_material_lock_change_changes_the_policy_digest(tmp_path: Path) -> None:
    materials = {
        "format_version": 1,
        "logical_model_id": "local-model",
        "runner_contract": {"id": "llama-cpp-v1", "version": "1"},
        "loader_profile_contract": {"id": "llama-cpp-text-v1", "version": "1"},
        "sources": [
            {
                "role": "base_model",
                "group": "base",
                "source_type": "huggingface_file",
                "repository": "example-org/example-model",
                "revision": "a" * 40,
                "filename": "model.gguf",
                "sha256": "b" * 64,
            }
        ],
        "preparation": [],
    }
    contract = CapabilityContract("model.execution.test.v1", "1", "c" * 64, ())
    requirements = CapabilityRequirements(
        (CapabilityRequirement(contract.capability_id, "1", "c" * 64, ()),),
        {"runner": contract.capability_id},
    )
    declared_requirements = {
        "format_version": 1,
        "required_capabilities": [requirements.required_capabilities[0].to_mapping()],
        "capability_requirements_digest": requirements.digest,
        "bindings": {"runner": {"capability_id": contract.capability_id}},
    }
    catalog = CapabilityCatalog(
        (contract,),
        (
            CapabilityProvider(
                "private-test-provider", contract, conformance_passed=True
            ),
        ),
    )
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first = compile_workflow_policy(
        _catalog_revision(
            first_root,
            model_materials=materials,
            capability_requirements=declared_requirements,
        ),
        capability_catalog=catalog,
    )
    changed = {
        **materials,
        "sources": [{**materials["sources"][0], "sha256": "d" * 64}],
    }
    second = compile_workflow_policy(
        _catalog_revision(
            second_root,
            model_materials=changed,
            capability_requirements=declared_requirements,
        ),
        capability_catalog=catalog,
    )

    assert first.model_materials_digest != second.model_materials_digest
    assert first.policy_digest != second.policy_digest


def test_v2_material_lock_requires_its_exact_descriptor_before_runtime_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution_descriptor = {
        "format_version": 1,
        "architecture_abi": {
            "id": "bert-encoder-v1",
            "version": "1",
            "contract_digest": "d" * 64,
        },
        "material_roles": ["tokenizer", "weights"],
        "abi_fields": {},
    }
    descriptor = parse_execution_descriptor(execution_descriptor)
    materials = {
        "format_version": 2,
        "logical_model_id": "example-embedding",
        "runner_contract": {"id": "mlx-embedding-v1", "version": "1"},
        "execution_descriptor": {
            "filename": "execution-descriptor.json",
            "sha256": descriptor.digest,
        },
        "sources": [
            {
                "role": "tokenizer",
                "group": "base",
                "source_type": "huggingface_file",
                "repository": "example-org/example-model",
                "revision": "a" * 40,
                "filename": "tokenizer.json",
                "sha256": "b" * 64,
            },
            {
                "role": "weights",
                "group": "base",
                "source_type": "huggingface_file",
                "repository": "example-org/example-model",
                "revision": "a" * 40,
                "filename": "weights.safetensors",
                "sha256": "c" * 64,
            },
        ],
        "preparation": [],
    }
    contract = CapabilityContract("model.execution.test.v1", "1", "e" * 64, ())
    requirements = CapabilityRequirements(
        (CapabilityRequirement(contract.capability_id, "1", "e" * 64, ()),),
        {"runner": contract.capability_id},
    )
    declared_requirements = {
        "format_version": 1,
        "required_capabilities": [requirements.required_capabilities[0].to_mapping()],
        "capability_requirements_digest": requirements.digest,
        "bindings": {"runner": {"capability_id": contract.capability_id}},
    }
    catalog = CapabilityCatalog(
        (contract,),
        (CapabilityProvider("private-provider", contract, conformance_passed=True),),
    )

    class _Validator:
        identity = ExecutionDescriptorAbi("bert-encoder-v1", "1", "d" * 64)

        def validate(self, _descriptor) -> None:
            return None

    revision = _catalog_revision(
        tmp_path,
        model_materials=materials,
        execution_descriptor=execution_descriptor,
        capability_requirements=declared_requirements,
    )
    runtime_loads: list[object] = []
    with monkeypatch.context() as patched:
        patched.setattr(
            policy_module,
            "load_agent_package_workflow",
            lambda *args: runtime_loads.append(args),
        )
        with pytest.raises(PolicyCompilationError, match="model execution binding"):
            compile_workflow_policy(revision, capability_catalog=catalog)
    assert runtime_loads == []

    policy = compile_workflow_policy(
        revision,
        capability_catalog=catalog,
        descriptor_validators=ExecutionDescriptorValidatorRegistry((_Validator(),)),
    )

    assert policy.model_execution_binding is not None
    assert (
        policy.model_execution_binding.execution_descriptor_digest == descriptor.digest
    )

    with pytest.raises(PackageStagingError, match="model-material lock"):
        _catalog_revision(
            tmp_path / "missing",
            model_materials=materials,
            capability_requirements=declared_requirements,
        )


def test_unsatisfied_exact_requirement_fails_before_runtime_manifest_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = BUILTIN_CAPABILITY_CONTRACTS[0]
    requirements = CapabilityRequirements(
        required_capabilities=(
            CapabilityRequirement(
                contract.capability_id,
                contract.contract_version,
                contract.contract_digest,
                ("multimodal",),
            ),
        )
    )
    revision = _catalog_revision(
        tmp_path,
        capability_requirements={
            "format_version": 1,
            "required_capabilities": [
                {
                    "capability_id": contract.capability_id,
                    "contract_version": contract.contract_version,
                    "contract_digest": contract.contract_digest,
                    "required_features": ["multimodal"],
                }
            ],
            "capability_requirements_digest": requirements.digest,
            "bindings": {},
        },
    )
    monkeypatch.setattr(
        policy_module,
        "load_agent_package_workflow",
        lambda _path: pytest.fail("runtime manifest was loaded"),
    )

    with pytest.raises(PolicyCompilationError, match="capability"):
        compile_workflow_policy(
            revision, capability_catalog=CapabilityCatalog((contract,), ())
        )


def test_unsatisfied_exact_requirement_fails_before_converter_asset_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = BUILTIN_CAPABILITY_CONTRACTS[0]
    requirement = CapabilityRequirement(
        contract.capability_id,
        contract.contract_version,
        contract.contract_digest,
        ("multimodal",),
    )
    requirements = CapabilityRequirements((requirement,))
    revision = _catalog_revision(
        tmp_path,
        input_converter_asset=b"converter sentinel",
        capability_requirements={
            "format_version": 1,
            "required_capabilities": [requirement.to_mapping()],
            "capability_requirements_digest": requirements.digest,
            "bindings": {},
        },
    )
    monkeypatch.setattr(
        policy_module,
        "_validate_input_converter_asset",
        lambda **_kwargs: pytest.fail("converter asset was accessed"),
    )
    monkeypatch.setattr(
        policy_module,
        "load_agent_package_workflow",
        lambda _path: pytest.fail("runtime manifest was loaded"),
    )

    with pytest.raises(PolicyCompilationError, match="capability"):
        compile_workflow_policy(
            revision, capability_catalog=CapabilityCatalog((contract,), ())
        )


def test_unsatisfied_exact_requirement_fails_before_local_asset_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = BUILTIN_CAPABILITY_CONTRACTS[0]
    requirement = CapabilityRequirement(
        contract.capability_id,
        contract.contract_version,
        contract.contract_digest,
        ("multimodal",),
    )
    requirements = CapabilityRequirements((requirement,))
    revision = _catalog_revision(
        tmp_path,
        with_local_tool=True,
        capability_requirements={
            "format_version": 1,
            "required_capabilities": [requirement.to_mapping()],
            "capability_requirements_digest": requirements.digest,
            "bindings": {},
        },
    )
    monkeypatch.setattr(
        policy_module,
        "_validate_local_tool_assets",
        lambda **_kwargs: pytest.fail("local asset was accessed"),
    )
    monkeypatch.setattr(
        policy_module,
        "load_agent_package_workflow",
        lambda _path: pytest.fail("runtime manifest was loaded"),
    )

    with pytest.raises(PolicyCompilationError, match="capability"):
        compile_workflow_policy(
            revision, capability_catalog=CapabilityCatalog((contract,), ())
        )


@pytest.mark.parametrize("failure", ("malformed", "digest", "binding"))
def test_invalid_requirement_is_rejected_during_descriptor_only_staging(
    tmp_path: Path, failure: str
) -> None:
    contract = BUILTIN_CAPABILITY_CONTRACTS[0]
    requirement = CapabilityRequirement(
        contract.capability_id,
        contract.contract_version,
        contract.contract_digest,
        ("multimodal",),
    )
    requirements = CapabilityRequirements((requirement,))
    declared_requirement = requirement.to_mapping()
    declared_digest = requirements.digest
    bindings: dict[str, object] = {}
    if failure == "malformed":
        declared_requirement["unexpected"] = "value"
    elif failure == "digest":
        declared_digest = "0" * 64
    else:
        bindings = {"runner": {"capability_id": "unknown-capability"}}
    with pytest.raises(PackageStagingError, match="descriptor"):
        _catalog_revision(
            tmp_path,
            input_converter_asset=b"converter sentinel",
            capability_requirements={
                "format_version": 1,
                "required_capabilities": [declared_requirement],
                "capability_requirements_digest": declared_digest,
                "bindings": bindings,
            },
        )


def test_policy_stages_a_declared_local_tool_as_an_executable_asset(
    tmp_path: Path,
) -> None:
    revision = _catalog_revision(tmp_path, with_local_tool=True)

    policy = compile_workflow_policy(revision)

    asset = revision.package_root / "tools" / "inspect_binary"
    assert policy.declared_local_tools[0].tool_id == "inspect_binary"
    assert asset.stat().st_mode & stat.S_IXUSR


def test_policy_compiles_descriptor_declared_package_skill(tmp_path: Path) -> None:
    policy = compile_workflow_policy(
        _catalog_revision(tmp_path, package_skill_id="document-guidance")
    )

    assert policy.declared_skill_ids == ("document-guidance",)


def test_policy_rejects_package_skills_without_source_resolution(
    tmp_path: Path,
) -> None:
    revision = _catalog_revision(
        tmp_path,
        package_skill_id="document-guidance",
        enable_package_skill_source_resolution=False,
    )

    with pytest.raises(PolicyCompilationError, match="cataloged package policy"):
        compile_workflow_policy(revision)


def test_capability_resolution_is_eligible_or_nonexecuting(tmp_path: Path) -> None:
    policy = compile_workflow_policy(_catalog_revision(tmp_path))

    unavailable = resolve_capabilities(policy, available_capabilities=set())
    eligible = resolve_capabilities(policy, available_capabilities={"text_generation"})

    assert unavailable.status == "capability_unavailable"
    assert unavailable.missing_capabilities == ("text_generation",)
    assert eligible.status == "eligible"
    assert eligible.missing_capabilities == ()


@pytest.mark.parametrize(
    "capability",
    (
        "context-pruning-pipeline",
        "scratch-workspace",
        "durable-session-continuation",
        "native-approval-resume",
        "collaboration-subagents",
        "retrieval-embedding-rag",
    ),
)
def test_deferred_runtime_declarations_require_an_explicit_host_capability(
    tmp_path: Path, capability: str
) -> None:
    policy = compile_workflow_policy(
        _catalog_revision(tmp_path, deferred_capability=capability)
    )

    resolution = resolve_capabilities(
        policy, available_capabilities={"text_generation"}
    )

    assert capability in policy.required_capabilities
    assert resolution.status == "capability_unavailable"
    assert capability in resolution.missing_capabilities


def test_read_only_mcp_policy_requires_its_nonexecuting_capability(
    tmp_path: Path,
) -> None:
    policy = compile_workflow_policy(
        _catalog_revision(tmp_path, with_read_only_mcp_tool=True)
    )

    assert policy.task_invocation.allowed_tool_ids == ("mail_list_unread",)
    assert policy.required_capabilities == frozenset(
        {"text_generation", "mcp_read_only"}
    )
    unavailable = resolve_capabilities(
        policy, available_capabilities={"text_generation"}
    )
    eligible = resolve_capabilities(
        policy, available_capabilities={"text_generation", "mcp_read_only"}
    )
    assert unavailable.missing_capabilities == ("mcp_read_only",)
    assert eligible.status == "eligible"


def test_side_effecting_mcp_policy_requires_a_separate_unavailable_capability(
    tmp_path: Path,
) -> None:
    policy = compile_workflow_policy(
        _catalog_revision(tmp_path, with_side_effecting_mcp_tool=True)
    )

    assert policy.declared_tools[0].side_effect == "write"
    assert policy.required_capabilities == frozenset(
        {"text_generation", "mcp_side_effects"}
    )
    unavailable = resolve_capabilities(
        policy, available_capabilities={"text_generation", "mcp_read_only"}
    )
    assert unavailable.missing_capabilities == ("mcp_side_effects",)


def test_mixed_mcp_policy_requires_both_reviewed_surfaces(tmp_path: Path) -> None:
    source = tmp_path / "packages" / "mixed-mail"
    shutil.copytree(TEMPLATE_ROOT, source)
    descriptor = source / "workflow-descriptor.yaml"
    descriptor_value = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
    descriptor_value["tools"] = [
        {
            "id": "mail_lookup",
            "kind": "mcp",
            "remote_tool_name": "list_unread",
            "side_effect": "read",
        },
        {
            "id": "mail_delete",
            "kind": "mcp",
            "remote_tool_name": "delete_email",
            "side_effect": "delete",
            "approval_required": False,
        },
    ]
    descriptor_value["task_invocation"].update(
        {
            "allowed_tool_ids": ["mail_lookup", "mail_delete"],
            "max_total_tool_calls": 2,
            "argument_sources": {
                "mail_delete": {
                    "message_id": {
                        "sources": ["cited_original_prompt_span"],
                        "authority": True,
                    }
                }
            },
        }
    )
    descriptor.write_text(yaml.safe_dump(descriptor_value), encoding="utf-8")
    runtime = source / "agent-runtime.yaml"
    runtime_value = yaml.safe_load(runtime.read_text(encoding="utf-8"))
    runtime_value["tools"] = [
        {
            "id": "mail_lookup",
            "label": "List unread mail",
            "tool_type": "external_api",
            "description_for_llm": "List unread mail.",
            "adapter": "host.mcp",
            "input_schema": {"type": "object"},
            "side_effect": "read",
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
            "input_schema": {"type": "object"},
            "side_effect": "delete",
            "approval_required": False,
            "timeout": "runtime_default",
            "retry_policy": "none",
            "failure_behavior": "error",
        },
    ]
    runtime_value["nodes"][0]["available_tools"] = ["mail_lookup", "mail_delete"]
    runtime.write_text(yaml.safe_dump(runtime_value), encoding="utf-8")
    store = PrivateStateStore(tmp_path / "state")
    handle = PackageSourceSelectionPolicy(
        allowed_root=source.parent, store=store
    ).select_directory(source, now=NOW)
    revision = PackageCatalog(tmp_path / "catalog").import_staged(
        PrivatePackageStager(store=store, private_root=tmp_path / "staging").stage(
            handle, now=NOW
        )
    )

    policy = compile_workflow_policy(revision)

    assert policy.required_capabilities == frozenset(
        {"text_generation", "mcp_read_only", "mcp_side_effects"}
    )
    assert resolve_capabilities(
        policy,
        available_capabilities={"text_generation", "mcp_read_only"},
    ).missing_capabilities == ("mcp_side_effects",)


def test_staging_rejects_descriptor_package_identity_mismatch(tmp_path: Path) -> None:
    with pytest.raises(PackageStagingError, match="descriptor is incompatible"):
        _catalog_revision(tmp_path, package_id="other-package")


def test_policy_rejects_unknown_registered_terminal_output_contract(
    tmp_path: Path,
) -> None:
    revision = _catalog_revision(
        tmp_path, terminal_output_schema_ref="missing-contract"
    )

    with pytest.raises(PolicyCompilationError, match="terminal output contract"):
        compile_workflow_policy(revision)


def test_policy_binds_the_exact_staged_input_converter_asset(tmp_path: Path) -> None:
    revision = _catalog_revision(
        tmp_path, input_converter_asset=b"def pack():\n    return {}\n"
    )

    policy = compile_workflow_policy(revision)

    assert policy.input_converter is not None
    assert policy.input_converter.converter_id == "qwen-floorplan-input-v1"
    assert (
        policy.input_converter.compatible_runner_contract_id
        == "transformers-generate-v1"
    )


def test_policy_rejects_a_stale_input_converter_asset_digest(tmp_path: Path) -> None:
    revision = _catalog_revision(
        tmp_path,
        input_converter_asset=b"def pack():\n    return {}\n",
        input_converter_digest="a" * 64,
    )

    with pytest.raises(PolicyCompilationError, match="cataloged package policy"):
        compile_workflow_policy(revision)
