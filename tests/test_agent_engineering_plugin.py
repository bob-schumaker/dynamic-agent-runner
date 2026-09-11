"""Static contract checks for the migrated agent-engineering plugin."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "agent-engineering"
GENERATED_ROOT = REPO_ROOT / ".codex-plugin" / "generated" / "agent-engineering"
MARKETPLACE_PATH = REPO_ROOT / "marketplace.json"
DIRECT_BASELINE_ROOT = REPO_ROOT / "tests" / "fixtures" / "m4-4-direct-plugin-baseline"
DIRECT_BASELINE_MANIFEST = (
    REPO_ROOT / "tests" / "fixtures" / "m4-4-direct-baseline.json"
)
ROUTER_MEMBER_ROOT = PLUGIN_ROOT / "skills"
RUNTIME_RELEASE_DESCRIPTOR = PLUGIN_ROOT / ".codex-plugin" / "dar-runtime-release.json"
RUNTIME_RELEASE_VERIFIER = (
    REPO_ROOT / "scripts" / "validate_agent_engineering_runtime_release.py"
)
CLASSIFICATION_MANIFEST = PLUGIN_ROOT / ".codex-plugin" / "classification-manifest.json"
CLASSIFICATION_VERIFIER = (
    REPO_ROOT / "scripts" / "validate_agent_engineering_classification.py"
)


def _runtime_release_verifier() -> object:
    specification = importlib.util.spec_from_file_location(
        "agent_engineering_runtime_release", RUNTIME_RELEASE_VERIFIER
    )
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _classification_verifier() -> object:
    specification = importlib.util.spec_from_file_location(
        "agent_engineering_classification", CLASSIFICATION_VERIFIER
    )
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for source in sorted(path for path in root.rglob("*") if path.is_file()):
        digest.update(str(source.relative_to(root)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(source.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def test_router_source_is_an_internal_packaging_input() -> None:
    manifest = json.loads(
        (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )

    assert manifest["name"] == "agent-engineering-direct"
    assert manifest["skills"] == "./skills/"
    assert manifest["interface"]["composerIcon"] == "./assets/agent-engineering.png"
    assert manifest["interface"]["logo"] == "./assets/agent-engineering.png"
    assert "mcpServers" not in manifest
    assert "apps" not in manifest
    assert not (PLUGIN_ROOT / ".mcp.json").exists()
    assert not (PLUGIN_ROOT / ".app.json").exists()
    assert sorted(
        path.parent.name for path in (PLUGIN_ROOT / "skills").glob("*/SKILL.md")
    ) == [
        "agent-development",
        "dar-workflow-authoring",
        "general-agent-development",
    ]


def test_generated_router_preserves_the_public_plugin_interface_and_receipts() -> None:
    generated_manifest = json.loads(
        (GENERATED_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    direct_manifest = json.loads(
        (DIRECT_BASELINE_ROOT / ".codex-plugin" / "plugin.json").read_text(
            encoding="utf-8"
        )
    )

    assert generated_manifest == direct_manifest
    assert list((GENERATED_ROOT / "skills").glob("*/SKILL.md")) == [
        GENERATED_ROOT / "skills" / "agent-development" / "SKILL.md"
    ]
    assert not (GENERATED_ROOT / "skills" / "agent-development" / "schemas").exists()
    assert not (GENERATED_ROOT / "skills" / "agent-development" / "scripts").exists()
    assert not (GENERATED_ROOT / "skills" / "agent-development" / "templates").exists()
    for receipt in (
        ".router-plugin-packager-source-map.json",
        ".codex-plugin/payload-manifest.json",
        ".codex-plugin/release-metadata.json",
    ):
        assert (GENERATED_ROOT / receipt).is_file()
    invocation = json.loads(
        (REPO_ROOT / ".codex-plugin" / "agent-engineering-router.json").read_text(
            encoding="utf-8"
        )
    )
    source_map = json.loads(
        (GENERATED_ROOT / ".router-plugin-packager-source-map.json").read_text(
            encoding="utf-8"
        )
    )
    payload_manifest = json.loads(
        (GENERATED_ROOT / ".codex-plugin" / "payload-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    decision_record = json.loads(
        (
            GENERATED_ROOT / ".codex-plugin" / "native-routed-decision-record.json"
        ).read_text(encoding="utf-8")
    )

    assert (
        decision_record["decision_record"]["router_authority"]
        == invocation["router_authority"]
    )
    assert decision_record["surface_id"] == "agent-engineering"
    assert source_map["surface_id"] == "agent-engineering"
    assert any(
        entry["path"] == "skills/agent-development/SKILL.md"
        and entry["ownership_role"] == "router-skill"
        for entry in source_map["entries"]
    )
    generated_general_module = (
        GENERATED_ROOT
        / "skills"
        / "agent-development"
        / "references"
        / "modules"
        / "general-agent-development"
        / "instructions.md"
    ).read_text(encoding="utf-8")
    generated_dar_module = (
        GENERATED_ROOT
        / "skills"
        / "agent-development"
        / "references"
        / "modules"
        / "dar-workflow-authoring"
        / "instructions.md"
    ).read_text(encoding="utf-8")
    assert "../../../../../references/modules/general-agent-development/" in (
        generated_general_module
    )
    assert (
        "../../../../../references/modules/dar-workflow-authoring/references/"
        "dar-runtime-profile.md"
    ) in generated_dar_module
    assert {
        entry["source_reference"]
        for entry in payload_manifest["entries"]
        if entry["ownership_role"] == "private_module_support"
    } == {
        source.relative_to(REPO_ROOT).as_posix()
        for declaration in invocation["payload_assets"]
        for source in (
            PLUGIN_ROOT
            / declaration["source"].removeprefix("plugins/agent-engineering/")
        ).rglob("*")
        if source.is_file()
    }


def test_plugin_payload_pins_the_released_dar_runtime_version() -> None:
    expected = "0.1.17"
    source_payload = PLUGIN_ROOT / "payload" / "dar-workflow-authoring"
    generated_payload = (
        GENERATED_ROOT / "references" / "modules" / "dar-workflow-authoring"
    )

    for root in (source_payload, generated_payload):
        payload = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(root.rglob("*"))
            if path.is_file()
        )
        assert "dynamic-agent-runner==0.2.1" not in payload
        assert "required_version: 0.2.1" not in payload
        assert f"dynamic-agent-runner=={expected}" in payload
        assert f"required_version: {expected}" in payload


def test_runtime_release_contract_binds_only_the_dar_runtime_selector() -> None:
    verifier = _runtime_release_verifier()

    receipt = verifier.validate_runtime_release_contract(
        project_file=REPO_ROOT / "pyproject.toml",
        descriptor_file=RUNTIME_RELEASE_DESCRIPTOR,
        wheel_file=REPO_ROOT / "dist" / "dynamic_agent_runner-0.1.17-py3-none-any.whl",
        payload_roots=(
            PLUGIN_ROOT / "payload" / "dar-workflow-authoring",
            GENERATED_ROOT / "references" / "modules" / "dar-workflow-authoring",
        ),
        plugin_manifest_files=(
            PLUGIN_ROOT / ".codex-plugin" / "plugin.json",
            GENERATED_ROOT / ".codex-plugin" / "plugin.json",
        ),
    )

    assert receipt.runtime_version == "0.1.17"
    assert receipt.wheel_filename == "dynamic_agent_runner-0.1.17-py3-none-any.whl"
    assert len(receipt.wheel_metadata_sha256) == 64
    assert receipt.plugin_versions == ("0.1.3", "0.1.3")
    assert receipt.plugin_versions != (receipt.runtime_version,) * 2
    assert (
        receipt.descriptor_sha256
        == hashlib.sha256(RUNTIME_RELEASE_DESCRIPTOR.read_bytes()).hexdigest()
    )
    assert len(receipt.payload_sha256) == 64
    assert len(receipt.selector_list_sha256) == 64


def test_runtime_release_contract_rejects_a_descriptor_wheel_mismatch(
    tmp_path: Path,
) -> None:
    verifier = _runtime_release_verifier()
    descriptor = tmp_path / "dar-runtime-release.json"
    descriptor.write_text(
        json.dumps(
            {
                "distribution": "dynamic-agent-runner",
                "format_version": 1,
                "runtime_version": "0.1.18",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(verifier.RuntimeReleaseContractError, match="version mismatch"):
        verifier.validate_runtime_release_contract(
            project_file=REPO_ROOT / "pyproject.toml",
            descriptor_file=descriptor,
            wheel_file=REPO_ROOT
            / "dist"
            / "dynamic_agent_runner-0.1.17-py3-none-any.whl",
            payload_roots=(PLUGIN_ROOT / "payload" / "dar-workflow-authoring",),
            plugin_manifest_files=(PLUGIN_ROOT / ".codex-plugin" / "plugin.json",),
        )


def test_runtime_release_contract_allows_a_plugin_only_version_change(
    tmp_path: Path,
) -> None:
    verifier = _runtime_release_verifier()
    plugin_manifest = tmp_path / "plugin.json"
    plugin = json.loads(
        (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    plugin["version"] = "99.0.0"
    plugin_manifest.write_text(json.dumps(plugin), encoding="utf-8")

    receipt = verifier.validate_runtime_release_contract(
        project_file=REPO_ROOT / "pyproject.toml",
        descriptor_file=RUNTIME_RELEASE_DESCRIPTOR,
        wheel_file=REPO_ROOT / "dist" / "dynamic_agent_runner-0.1.17-py3-none-any.whl",
        payload_roots=(PLUGIN_ROOT / "payload" / "dar-workflow-authoring",),
        plugin_manifest_files=(plugin_manifest,),
    )

    assert receipt.runtime_version == "0.1.17"
    assert receipt.plugin_versions == ("99.0.0",)


def test_runtime_release_preparation_rewrites_only_payload_runtime_selectors(
    tmp_path: Path,
) -> None:
    verifier = _runtime_release_verifier()
    descriptor = tmp_path / "dar-runtime-release.json"
    descriptor.write_text(
        json.dumps(
            {
                "distribution": "dynamic-agent-runner",
                "format_version": 1,
                "runtime_version": "0.1.18",
            }
        ),
        encoding="utf-8",
    )
    payload_root = tmp_path / "dar-workflow-authoring"
    shutil.copytree(PLUGIN_ROOT / "payload" / "dar-workflow-authoring", payload_root)
    plugin_manifest = tmp_path / "plugin.json"
    plugin_manifest.write_text(
        (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    changed_files = verifier.prepare_runtime_release_payload(
        descriptor_file=descriptor,
        payload_roots=(payload_root,),
    )

    payload = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(
            candidate for candidate in payload_root.rglob("*") if candidate.is_file()
        )
    )
    assert changed_files
    assert "dynamic-agent-runner==0.1.17" not in payload
    assert "required_version: 0.1.17" not in payload
    assert "dynamic-agent-runner==0.1.18" in payload
    assert "required_version: 0.1.18" in payload
    assert json.loads(plugin_manifest.read_text(encoding="utf-8"))["version"] == "0.1.3"


def test_classification_manifest_covers_every_source_input_and_mapped_output() -> None:
    verifier = _classification_verifier()

    receipt = verifier.validate_classification_manifest(
        plugin_root=PLUGIN_ROOT,
        manifest_file=CLASSIFICATION_MANIFEST,
        source_map_file=GENERATED_ROOT / ".router-plugin-packager-source-map.json",
    )

    assert receipt.source_file_count > 0
    assert receipt.mapped_output_count > 0
    assert receipt.excluded_paths == (".codex-plugin/dar-runtime-release.json",)


def test_router_source_has_no_support_subtree_and_private_members_own_guidance() -> (
    None
):
    root_skill = (PLUGIN_ROOT / "skills" / "agent-development" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert [
        path.name for path in (PLUGIN_ROOT / "skills" / "agent-development").iterdir()
    ] == ["SKILL.md"]
    assert "private router modules" in root_skill

    general_support = PLUGIN_ROOT / "payload" / "general-agent-development"
    for module in (
        "agent-action-review",
        "agent-environment-health",
        "agent-evaluation",
        "agent-tool-contract-design",
    ):
        assert (
            general_support / "references" / "modules" / module / "instructions.md"
        ).is_file()

    profile = (
        PLUGIN_ROOT
        / "payload"
        / "dar-workflow-authoring"
        / "references"
        / "dar-runtime-profile.md"
    ).read_text(encoding="utf-8")
    assert "source_selection_required" in profile
    assert "explicitly asks" in profile
    assert "command-limited `dar-package` on `PATH`" in profile
    assert "Do not search for a wheel" in profile
    assert "corpus/" not in root_skill


def test_private_dar_write_template_preserves_the_reviewed_email_contract() -> None:
    support = PLUGIN_ROOT / "payload" / "dar-workflow-authoring" / "references"
    guidance = (support / "dar-runtime-profile" / "agent-development.md").read_text(
        encoding="utf-8"
    )
    descriptor = (
        support / "dar-authoring-write-mcp-template" / "workflow-descriptor.yaml"
    ).read_text(encoding="utf-8")
    runtime = (
        support / "dar-authoring-write-mcp-template" / "agent-runtime.yaml"
    ).read_text(encoding="utf-8")

    assert "dar-authoring-write-mcp-template" in guidance
    assert "remote_tool_name: send_email" in descriptor
    assert "side_effect: write" in descriptor
    assert "approval_required: true" in descriptor
    assert "id: mail_send" in runtime
    assert "available_tools:" in runtime


def test_private_dar_guidance_keeps_artifact_workflows_on_the_no_tool_template() -> (
    None
):
    guidance = (
        PLUGIN_ROOT
        / "payload"
        / "dar-workflow-authoring"
        / "references"
        / "dar-runtime-profile"
        / "agent-development.md"
    ).read_text(encoding="utf-8")

    assert "allowed_artifact_roles" in guidance
    assert "structured input schema" in guidance
    assert "custom artifact protocol" in guidance
    assert "Copy the canonical no-tool template files" in guidance
    assert "only YAML fields that may change" in guidance
    assert "Do not normalize artifact role names" in guidance
    assert "OAuth reconnect workflow" in guidance


def test_dar_guidance_uses_closed_design_first_registration() -> None:
    guidance = (
        PLUGIN_ROOT
        / "payload"
        / "dar-workflow-authoring"
        / "references"
        / "dar-runtime-profile"
        / "agent-development.md"
    ).read_text(encoding="utf-8")

    assert "dar-package register-authored-workflow --definition-stdin" in guidance
    assert "ask only the desired output format" in guidance
    assert "`SVG` requires no further question" in guidance
    assert "do not ask for a binary encoding" in guidance
    assert "material_set_id" not in guidance
    assert "project-authoring-materials" not in guidance
    assert "create-authored-package" not in guidance


def test_dar_guidance_requires_the_fixed_converter_package_contract() -> None:
    roots = (
        PLUGIN_ROOT / "payload" / "dar-workflow-authoring",
        GENERATED_ROOT / "references" / "modules" / "dar-workflow-authoring",
    )

    for root in roots:
        guidance = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(root.rglob("*"))
            if path.is_file()
        )
        normalized_guidance = " ".join(guidance.split())
        assert "workflow-sealed Python converter package" in guidance
        assert "transformers-generate-v1" in guidance
        assert 'converter_contract_version = "v1"' in guidance
        assert 'compatible_runner_contract_id = "transformers-generate-v1"' in guidance
        assert "converter =" in guidance
        assert "live callable" in guidance
        assert "dependency installation" in guidance
        assert "arbitrary path" in guidance
        assert "runtime package selection" in normalized_guidance
        assert "format registry" in guidance


def test_dar_guidance_requests_host_owned_local_model_preparation_only() -> None:
    guidance = (
        PLUGIN_ROOT
        / "payload"
        / "dar-workflow-authoring"
        / "references"
        / "dar-runtime-profile.md"
    ).read_text(encoding="utf-8")

    assert "dar-package prepare --model <logical-model-requirement>" in guidance
    assert "dar-package invoke --package-name <saved-workflow> --prompt-stdin" in (
        guidance
    )
    assert "--model-path" not in guidance
    assert "--projector-path" not in guidance
    assert "--lora-path" not in guidance
    assert "prepared-artifact identifier" not in guidance


def test_marketplace_exposes_only_the_successor_plugin() -> None:
    marketplace = json.loads(MARKETPLACE_PATH.read_text(encoding="utf-8"))

    assert marketplace["name"] == "dynamic-agent-runner"
    assert marketplace["interface"]["displayName"] == "Dynamic Agent Runner"
    assert marketplace["plugins"] == [
        {
            "name": "agent-engineering",
            "source": {
                "source": "local",
                "path": "./.codex-plugin/generated/agent-engineering",
            },
            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
            "category": "Productivity",
        }
    ]


def test_direct_skill_baseline_is_frozen_as_test_only_collateral() -> None:
    baseline = json.loads(DIRECT_BASELINE_MANIFEST.read_text(encoding="utf-8"))

    assert baseline["format_version"] == "m4.4-direct-baseline-v1"
    assert baseline["plugin_identity"] == "agent-engineering"
    assert baseline["skill_identity"] == "agent-development@agent-engineering"
    assert baseline["plugin_tree_digest"] == _tree_digest(DIRECT_BASELINE_ROOT)
    assert (DIRECT_BASELINE_ROOT / ".codex-plugin" / "plugin.json").is_file()
