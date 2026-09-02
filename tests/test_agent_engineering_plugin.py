"""Static contract checks for the migrated agent-engineering plugin."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "agent-engineering"
GENERATED_ROOT = REPO_ROOT / ".codex-plugin" / "generated" / "agent-engineering-routed"
MARKETPLACE_PATH = REPO_ROOT / "marketplace.json"
DIRECT_BASELINE_ROOT = REPO_ROOT / "tests" / "fixtures" / "m4-4-direct-plugin-baseline"
DIRECT_BASELINE_MANIFEST = (
    REPO_ROOT / "tests" / "fixtures" / "m4-4-direct-baseline.json"
)
ROUTER_MEMBER_ROOT = PLUGIN_ROOT / "skills"


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


def test_marketplace_exposes_only_the_successor_plugin() -> None:
    marketplace = json.loads(MARKETPLACE_PATH.read_text(encoding="utf-8"))

    assert marketplace["name"] == "dynamic-agent-runner"
    assert marketplace["interface"]["displayName"] == "Dynamic Agent Runner"
    assert marketplace["plugins"] == [
        {
            "name": "agent-engineering",
            "source": {
                "source": "local",
                "path": "./.codex-plugin/generated/agent-engineering-routed",
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
