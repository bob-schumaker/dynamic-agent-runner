"""Regression coverage for the workflow-owned floorplan SVG fixture."""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import stat
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dynamic_agent_runner.workflow_host.catalog import PackageCatalog
from dynamic_agent_runner.workflow_host.host import (
    _dar_owned_transformers_generation_bindings,
)
from dynamic_agent_runner.workflow_host.local_tools import (
    LocalToolDefinition,
    LocalToolSandbox,
    execute_macos_sandbox_exec,
)
from dynamic_agent_runner.workflow_host.generation_resource_budgets import (
    validate_generation_budget_field,
)
from dynamic_agent_runner.workflow_host.package_sources import (
    PackageSourceSelectionPolicy,
)
from dynamic_agent_runner.workflow_host.policy import (
    PolicyCompilationError,
    compile_workflow_policy,
)
import dynamic_agent_runner.workflow_host.policy as policy_module
from dynamic_agent_runner.workflow_host.staging import PrivatePackageStager
from dynamic_agent_runner.workflow_host.state import PrivateStateStore
from dynamic_agent_runner.workflow_host.model_materials import (
    parse_model_dependency_lock,
)
from dynamic_agent_runner.workflow_host.execution_descriptors import (
    parse_execution_descriptor,
)
from dynamic_agent_runner.workflow_host.workflow_support_matrix import (
    MaterialIdentity,
    WorkflowSupportCandidate,
    WorkflowSupportProfile,
    WorkflowSupportReceipt,
    WorkflowSupportStatus,
    classify_workflow_support,
    validate_workflow_support_receipt,
)


NOW = datetime(2026, 9, 6, tzinfo=UTC)
FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "natural-language-workflow-authoring"
    / "floorplan-svg"
)


def _floorplan_matrix_profile(*, live: bool) -> WorkflowSupportProfile:
    lock = parse_model_dependency_lock(
        json.loads((FIXTURE / "model-materials.json").read_text(encoding="utf-8"))
    )
    descriptor = parse_execution_descriptor(
        json.loads((FIXTURE / "execution-descriptor.json").read_text(encoding="utf-8"))
    )
    material = MaterialIdentity(
        package_id=lock.logical_model_id,
        material_lock_digest=lock.digest,
        material_roles=descriptor.material_roles,
        artifact_digests={
            "execution_descriptor": descriptor.digest,
            "input_converter": hashlib.sha256(
                (FIXTURE / "assets" / "qwen25_vl_3b_grpo_converter.py").read_bytes()
            ).hexdigest(),
            "terminal_svg_validator": hashlib.sha256(
                (FIXTURE / "tools" / "validate_svg").read_bytes()
            ).hexdigest(),
        },
    )
    return WorkflowSupportProfile(
        profile_id=(
            "floorplan-svg-mps-completion-v1" if live else "floorplan-svg-synthetic-v1"
        ),
        workflow_family="floorplan-svg",
        required_adapter_capabilities=("structured_output",),
        required_abi_capabilities=(descriptor.architecture_abi.abi_id,),
        required_provider_capabilities=(lock.runner_contract.contract_id,),
        required_host_capabilities=("mps",) if live else (),
        material_identity=material,
        execution_mode="live" if live else "synthetic",
        authorization_required=live,
        implemented=True,
    )


def _floorplan_matrix_candidate(
    profile: WorkflowSupportProfile,
    *,
    material_identity: MaterialIdentity | None = None,
    missing_material: bool = False,
    host_capabilities: frozenset[str] = frozenset(),
    provider_capabilities: frozenset[str] = frozenset({"transformers-generate-v1"}),
    authorization_granted: bool = False,
) -> WorkflowSupportCandidate:
    return WorkflowSupportCandidate(
        adapter_id="floorplan-fixture-runner",
        adapter_capabilities=frozenset({"structured_output"}),
        available_abi_capabilities=frozenset({"transformers-peft-generation-v1"}),
        provider_capabilities=provider_capabilities,
        host_capabilities=host_capabilities,
        material_identity=(
            None if missing_material else material_identity or profile.material_identity
        ),
        authorization_granted=authorization_granted,
    )


def test_floorplan_matrix_profiles_bind_synthetic_and_mps_facts() -> None:
    synthetic = _floorplan_matrix_profile(live=False)
    synthetic_candidate = _floorplan_matrix_candidate(synthetic)
    synthetic_cell = classify_workflow_support(synthetic, synthetic_candidate)
    synthetic_receipt = WorkflowSupportReceipt(
        profile_digest=synthetic_cell.profile_digest,
        adapter_id=synthetic_cell.adapter_id,
        material_identity=synthetic_cell.material_identity,
        test_mode="synthetic",
        status=synthetic_cell.status,
        reason_codes=synthetic_cell.reason_codes,
        dispatch_count=1,
    )

    assert synthetic_cell.status is WorkflowSupportStatus.SUPPORTED
    validate_workflow_support_receipt(
        synthetic, synthetic_candidate, synthetic_cell, synthetic_receipt
    )

    live = _floorplan_matrix_profile(live=True)
    assert live.material_identity is not None

    def mismatched_material(role: str) -> MaterialIdentity:
        artifacts = dict(live.material_identity.artifact_digests)
        artifacts[role] = "f" * 64
        return MaterialIdentity(
            package_id=live.material_identity.package_id,
            material_lock_digest=live.material_identity.material_lock_digest,
            material_roles=live.material_identity.material_roles,
            artifact_digests=artifacts,
        )

    blocked_candidates = (
        _floorplan_matrix_candidate(live),
        _floorplan_matrix_candidate(live, missing_material=True),
        *(
            _floorplan_matrix_candidate(
                live, material_identity=mismatched_material(role)
            )
            for role in (
                "execution_descriptor",
                "input_converter",
                "terminal_svg_validator",
            )
        ),
        _floorplan_matrix_candidate(live, provider_capabilities=frozenset()),
        _floorplan_matrix_candidate(
            live, host_capabilities=frozenset({"mps"}), authorization_granted=False
        ),
    )
    for candidate in blocked_candidates:
        cell = classify_workflow_support(live, candidate)
        receipt = WorkflowSupportReceipt(
            profile_digest=cell.profile_digest,
            adapter_id=cell.adapter_id,
            material_identity=cell.material_identity,
            test_mode="live",
            status=cell.status,
            reason_codes=cell.reason_codes,
            dispatch_count=0,
        )

        assert cell.status is WorkflowSupportStatus.BLOCKED
        validate_workflow_support_receipt(live, candidate, cell, receipt)


def test_floorplan_fixture_stages_a_workflow_owned_svg_validator(
    tmp_path: Path,
) -> None:
    source = tmp_path / "packages" / "floorplan-from-image"
    shutil.copytree(FIXTURE, source)
    store = PrivateStateStore(tmp_path / "state")
    handle = PackageSourceSelectionPolicy(
        allowed_root=source.parent, store=store
    ).select_directory(source, now=NOW)
    staged = PrivatePackageStager(store=store, private_root=tmp_path / "staging").stage(
        handle, now=NOW
    )
    revision = PackageCatalog(tmp_path / "catalog").import_staged(staged)

    capability_catalog, descriptor_validators, _ = (
        _dar_owned_transformers_generation_bindings()
    )
    policy = compile_workflow_policy(
        revision,
        capability_catalog=capability_catalog,
        descriptor_validators=descriptor_validators,
    )

    assert policy.model_profile_requirement == "local-multimodal-model-v1"
    runtime = (revision.package_root / "agent-runtime.yaml").read_text(encoding="utf-8")
    assert "response_format: {type: json_object}" in runtime
    assert '"start":[x,y]' in runtime
    assert '"end":[x,y]' in runtime
    assert '"width":W' in runtime
    assert "Coordinates normalized so longer image edge = 1024." in runtime
    assert policy.workspace.accepted_input_types == ("image/jpeg", "image/png")
    assert policy.input_converter is not None
    assert policy.input_converter.converter_id == "qwen25-vl-3b-grpo-input-v1"
    assert (
        policy.input_converter.compatible_runner_contract_id
        == "transformers-generate-v1"
    )
    assert policy.terminal_output_validator is not None
    asset = revision.package_root / "tools" / "validate_svg"
    assert asset.stat().st_mode & stat.S_IXUSR

    sandbox = LocalToolSandbox(
        package_root=revision.package_root, execute=execute_macos_sandbox_exec
    )
    definition = LocalToolDefinition(
        tool_id="terminal-output-validator",
        asset_path=Path("tools/validate_svg"),
        accepted_artifact_role="terminal_output",
        max_input_bytes=32 * 1024,
        max_output_bytes=512,
        timeout_seconds=1,
    )
    assert sandbox.run(
        definition, artifact_role="terminal_output", artifact_bytes=b"<svg/>"
    ) == {"valid": True}
    assert sandbox.run(
        definition, artifact_role="terminal_output", artifact_bytes=b"not SVG"
    ) == {"valid": False}
    assert sandbox.run(
        definition, artifact_role="terminal_output", artifact_bytes=b"<svg>"
    ) == {"valid": False}

    renderer = LocalToolDefinition(
        tool_id="terminal-output-renderer",
        asset_path=Path("tools/render_floorplan_json"),
        accepted_artifact_role="terminal_output",
        max_input_bytes=32 * 1024,
        max_output_bytes=32 * 1024,
        timeout_seconds=1,
    )
    admission = LocalToolDefinition(
        tool_id="terminal-json-admission",
        asset_path=Path("tools/admit_floorplan_json"),
        accepted_artifact_role="terminal_output",
        max_input_bytes=32 * 1024,
        max_output_bytes=32 * 1024,
        timeout_seconds=1,
    )
    structured_output = (
        b'{"walls":[{"id":"wall_1","start":[10,20],"end":[90,20],'
        b'"thickness":4,"curvature":0,"openings":[{"type":"window",'
        b'"center":50,"width":20}]}],"rooms":[{"label":"outdoor",'
        b'"walls":["wall_1"]}]}'
    )
    admitted = sandbox.run(
        admission, artifact_role="terminal_output", artifact_bytes=structured_output
    )
    assert base64.b64decode(admitted["output_base64"]) == structured_output
    assert sandbox.run(
        admission,
        artifact_role="terminal_output",
        artifact_bytes=b'{"walls":[',
    ) == {"status": "rejected"}
    rendered = sandbox.run(
        renderer,
        artifact_role="terminal_output",
        artifact_bytes=base64.b64decode(admitted["output_base64"]),
    )
    assert rendered["status"] == "accepted"
    assert b"<svg " in base64.b64decode(rendered["output_base64"])
    assert sandbox.run(
        renderer,
        artifact_role="terminal_output",
        artifact_bytes=b'{"walls":[],"rooms":[],"extra":true}',
    ) == {"status": "rejected"}
    assert sandbox.run(
        renderer,
        artifact_role="terminal_output",
        artifact_bytes=(
            b'{"walls":[{"id":"wall_1","start":[10,20],"end":[90,20],'
            b'"thickness":4,"curvature":0,"openings":[{"type":"arch",'
            b'"center":50,"width":20}]}],"rooms":[]}'
        ),
    ) == {"status": "rejected"}


def test_floorplan_package_binds_a_sealed_generation_descriptor(tmp_path: Path) -> None:
    source = tmp_path / "packages" / "floorplan-from-image"
    shutil.copytree(FIXTURE, source)
    store = PrivateStateStore(tmp_path / "state")
    handle = PackageSourceSelectionPolicy(
        allowed_root=source.parent, store=store
    ).select_directory(source, now=NOW)
    staged = PrivatePackageStager(store=store, private_root=tmp_path / "staging").stage(
        handle, now=NOW
    )
    revision = PackageCatalog(tmp_path / "catalog").import_staged(staged)

    capability_catalog, descriptor_validators, model_runner_registry = (
        _dar_owned_transformers_generation_bindings()
    )
    policy = compile_workflow_policy(
        revision,
        capability_catalog=capability_catalog,
        descriptor_validators=descriptor_validators,
    )

    assert policy.model_materials is not None
    assert policy.execution_descriptor is not None
    assert policy.model_execution_binding is not None
    assert asdict(validate_generation_budget_field(policy.execution_descriptor)) == {
        "max_new_tokens_per_fragment": 1024,
        "max_continuations": 0,
        "max_total_generated_tokens": 1024,
        "max_total_output_bytes": 32768,
        "max_effective_context_tokens": 4096,
        "max_runtime_milliseconds": 360000,
        "max_memory_bytes": 30150672384,
    }
    assert {source.role for source in policy.model_materials.sources} == {
        "adapter_config",
        "adapter_weights",
        "base_chat_template",
        "base_config",
        "base_generation_config",
        "base_weight_1",
        "base_weight_2",
        "base_weight_index",
        "processor_config",
        "processor_merges",
        "processor_tokenizer",
        "processor_tokenizer_config",
        "processor_vocab",
    }
    assert (
        model_runner_registry.resolve(policy.model_execution_binding).provider_id
        == "dar-transformers-generate-runner-v1"
    )


def test_floorplan_package_without_materials_rejects_before_converter_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "packages" / "floorplan-from-image"
    shutil.copytree(FIXTURE, source)
    (source / "model-materials.json").unlink()
    (source / "execution-descriptor.json").unlink()
    store = PrivateStateStore(tmp_path / "state")
    handle = PackageSourceSelectionPolicy(
        allowed_root=source.parent, store=store
    ).select_directory(source, now=NOW)
    staged = PrivatePackageStager(store=store, private_root=tmp_path / "staging").stage(
        handle, now=NOW
    )
    revision = PackageCatalog(tmp_path / "catalog").import_staged(staged)
    capability_catalog, descriptor_validators, _ = (
        _dar_owned_transformers_generation_bindings()
    )
    monkeypatch.setattr(
        policy_module,
        "_validate_input_converter_asset",
        lambda **_kwargs: pytest.fail("converter validation must not run"),
    )

    with pytest.raises(PolicyCompilationError, match="model execution binding"):
        compile_workflow_policy(
            revision,
            capability_catalog=capability_catalog,
            descriptor_validators=descriptor_validators,
        )
