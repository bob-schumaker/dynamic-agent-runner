"""Tests for the skills-only DAR authoring plugin bundle."""

from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "dar-authoring"
PINNED_COMMAND = (
    "uv run --no-project --python 3.14 --index-url "
    "https://artifactory.oci.oraclecorp.com/api/pypi/global-release-pypi/simple "
    "--with dynamic-agent-runner==0.1.16 dar-package"
)
DISCOVERY_COMMAND = f"{PINNED_COMMAND} version --json"
AUTHORING_COMMANDS = (
    "project-authoring-materials --material-set-id <opaque-id>",
    "create-authored-package --package-name <user-requested-name>",
    "write-authored-package-file --authoring-output-id <opaque-id>",
    "finalize-authored-package --authoring-output-id <opaque-id>",
)


def test_plugin_is_skills_only() -> None:
    manifest = json.loads(
        (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )

    assert manifest["name"] == "dar-authoring"
    assert "mcpServers" not in manifest
    assert not (PLUGIN_ROOT / ".mcp.json").exists()
    assert not (PLUGIN_ROOT / "scripts" / "dar-mcp").exists()
    assert not (PLUGIN_ROOT / "scripts" / "dar-workflow").exists()


def test_bundled_skills_use_the_pinned_dar_package_control_plane() -> None:
    skills = sorted((PLUGIN_ROOT / "skills").glob("*/SKILL.md"))

    assert len(skills) == 3
    for skill in skills:
        text = skill.read_text(encoding="utf-8")
        assert DISCOVERY_COMMAND in text
        assert "dar-workflow" not in text
        assert "dar-mcp" not in text
        assert "run_dar_workflow" not in text


def test_agent_development_uses_only_the_role_scoped_authoring_commands() -> None:
    text = (PLUGIN_ROOT / "skills" / "agent-development" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert all(command in text for command in AUTHORING_COMMANDS)
    assert "M1 exposes only" not in text
    assert "select-package" not in text
    assert "register --" not in text
