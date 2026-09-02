"""Static contract checks for the migrated agent-engineering plugin."""

from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "agent-engineering"
MARKETPLACE_PATH = REPO_ROOT / "marketplace.json"


def test_agent_engineering_plugin_is_a_plain_single_visible_skill_plugin() -> None:
    manifest = json.loads(
        (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )

    assert manifest["name"] == "agent-engineering"
    assert manifest["skills"] == "./skills/"
    assert manifest["interface"]["composerIcon"] == "./assets/agent-engineering.png"
    assert manifest["interface"]["logo"] == "./assets/agent-engineering.png"
    assert "mcpServers" not in manifest
    assert "apps" not in manifest
    assert not (PLUGIN_ROOT / ".mcp.json").exists()
    assert not (PLUGIN_ROOT / ".app.json").exists()
    assert list((PLUGIN_ROOT / "skills").glob("*/SKILL.md")) == [
        PLUGIN_ROOT / "skills" / "agent-development" / "SKILL.md"
    ]


def test_plugin_contains_the_complete_cohort_and_dar_runtime_profile() -> None:
    root_skill = (PLUGIN_ROOT / "skills" / "agent-development" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    for module in (
        "agent-action-review",
        "agent-environment-health",
        "agent-evaluation",
        "agent-tool-contract-design",
    ):
        assert (
            PLUGIN_ROOT
            / "skills"
            / "agent-development"
            / "references"
            / "modules"
            / module
            / "instructions.md"
        ).is_file()
        assert module in root_skill

    profile = (PLUGIN_ROOT / "references" / "dar-runtime-profile.md").read_text(
        encoding="utf-8"
    )
    assert "source_selection_required" in profile
    assert "explicitly asks" in profile
    assert "command-limited `dar-package` on `PATH`" in profile
    assert "Do not search for a wheel" in profile
    assert "corpus/" not in root_skill


def test_marketplace_exposes_only_the_successor_plugin() -> None:
    marketplace = json.loads(MARKETPLACE_PATH.read_text(encoding="utf-8"))

    assert marketplace["name"] == "dynamic-agent-runner"
    assert marketplace["interface"]["displayName"] == "Dynamic Agent Runner"
    assert marketplace["plugins"] == [
        {
            "name": "agent-engineering",
            "source": {"source": "local", "path": "./plugins/agent-engineering"},
            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
            "category": "Productivity",
        }
    ]
