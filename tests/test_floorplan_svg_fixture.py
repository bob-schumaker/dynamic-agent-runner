"""Regression coverage for the workflow-owned floorplan SVG fixture."""

from __future__ import annotations

import base64
import shutil
import stat
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dynamic_agent_runner.local_model_preparation import (
    qwen25_vl_3b_floorplan_grpo_recipe,
)
from dynamic_agent_runner.workflow_host.catalog import PackageCatalog
from dynamic_agent_runner.workflow_host.host import (
    _dar_owned_transformers_generation_bindings,
    LocalWorkflowHost,
    configure_floorplan_transformers_peft_host,
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


NOW = datetime(2026, 9, 6, tzinfo=UTC)
FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "natural-language-workflow-authoring"
    / "floorplan-svg"
)
IMAGE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "m4-4-direct-plugin-baseline"
    / "assets"
    / "agent-engineering.png"
)


def test_floorplan_host_configures_workspace_ingress_for_its_image_contract(
    tmp_path: Path,
) -> None:
    root = tmp_path / "state"
    configure_floorplan_transformers_peft_host(
        root=root,
        package_root=FIXTURE.parent,
        workspace_input_root=IMAGE.parent,
    )
    host = LocalWorkflowHost.open(root)
    source = host.select_package(FIXTURE, now=NOW)
    registration = host.register(
        workflow_id="floorplan-from-image", package_source_handle=source, now=NOW
    )

    artifact = host.ingress_file(
        workflow_id=registration.workflow_id,
        path=IMAGE,
        role="source_image",
        media_type="image/png",
        now=NOW,
    )

    assert artifact.byte_count > 0


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
    assert tuple(
        (
            source.role,
            source.repository,
            source.revision,
            source.filename,
            source.sha256,
            source.group,
        )
        for source in policy.model_materials.sources
    ) == tuple(
        (
            artifact.role,
            artifact.repo_id,
            artifact.revision,
            artifact.filename,
            artifact.sha256,
            artifact.group,
        )
        for artifact in sorted(
            qwen25_vl_3b_floorplan_grpo_recipe().artifacts,
            key=lambda artifact: artifact.role,
        )
    )
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
