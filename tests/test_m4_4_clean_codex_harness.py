"""Tests for the CLI-first M4.4 clean-Codex harness boundary."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

from m4_4_clean_codex import (
    M44CleanCodexError,
    build_clean_codex_environment,
    create_marketplace,
    stage_dar_package,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESS = REPO_ROOT / "scripts" / "run_m4_4_clean_codex.py"


def _harness_module() -> object:
    spec = importlib.util.spec_from_file_location("m44_harness", HARNESS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_clean_codex_environment_exposes_successor_path_not_legacy_state(
    tmp_path: Path,
) -> None:
    environment = build_clean_codex_environment(
        codex_home=tmp_path / "codex-home",
        working_directory=tmp_path / "workspace",
        wheel=tmp_path / "dynamic_agent_runner.whl",
        state_root=tmp_path / "state",
        template_root=tmp_path / "templates",
        inherited={"PATH": "/usr/bin:/bin", "OPENAI_API_KEY": "secret"},
    )

    assert environment == {
        "CODEX_HOME": str(tmp_path / "codex-home"),
        "UV_CACHE_DIR": str(tmp_path / "workspace" / ".uv-cache"),
        "HOME": str(tmp_path / "workspace"),
        "LANG": "C.UTF-8",
        "PATH": "/usr/bin:/bin",
    }
    assert not {
        key
        for key in environment
        if "DAR_AUTHORING" in key or "BROKER" in key or "MCP_MODE" in key
    }


def test_stage_dar_package_rejects_non_absolute_state_root(
    tmp_path: Path,
) -> None:
    with pytest.raises(M44CleanCodexError):
        stage_dar_package(
            wheel=tmp_path / "dynamic_agent_runner.whl",
            state_root=Path("state"),
            destination=tmp_path / "dar-bin",
        )


def test_marketplace_contains_only_the_copied_plugin(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"
    (plugin / ".codex-plugin").mkdir(parents=True)
    (plugin / "skills" / "agent-development").mkdir(parents=True)
    (plugin / "references").mkdir(parents=True)
    (plugin / ".codex-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    (plugin / "skills" / "agent-development" / "SKILL.md").write_text(
        "# Agent development\n", encoding="utf-8"
    )
    (plugin / "references" / "dar-runtime-profile.md").write_text(
        "# DAR runtime profile\n", encoding="utf-8"
    )

    marketplace = create_marketplace(
        plugin_root=plugin, destination=tmp_path / "marketplace"
    )

    assert marketplace.is_file()
    copied_plugin = tmp_path / "marketplace" / "plugins" / "agent-engineering"
    assert copied_plugin.is_dir()
    assert (copied_plugin / "skills" / "agent-development" / "SKILL.md").is_file()
    assert (copied_plugin / "references" / "dar-runtime-profile.md").is_file()
    manifest_value = json.loads(marketplace.read_text(encoding="utf-8"))
    assert manifest_value["plugins"][0]["name"] == "agent-engineering"
    assert "dar-authoring" not in marketplace.read_text(encoding="utf-8")


def test_receipt_reader_finds_nested_redacted_cli_receipts() -> None:
    module = _harness_module()
    transcript = "\n".join(
        (
            json.dumps(
                {
                    "item": {
                        "aggregated_output": 'command output\n{"format_version":1,"status":"created","authoring_output_id":"output-id"}'
                    }
                }
            ),
            json.dumps(
                {
                    "item": {
                        "aggregated_output": '{"format_version":1,"status":"finalized","package_digest":"'
                        + "a" * 64
                        + '"}'
                    }
                }
            ),
        )
    )

    assert module._receipt(transcript, "created") == {
        "format_version": 1,
        "status": "created",
        "authoring_output_id": "output-id",
    }
    assert module._receipt(transcript, "finalized")["package_digest"] == "a" * 64


def test_successor_author_prompt_uses_no_legacy_identity_or_cli_recipe() -> None:
    module = _harness_module()

    prompt = module._author_request(
        "Design a summary workflow.",
        "material-id",
        "summary",
        "pass",
    )

    assert "agent-engineering" in prompt
    assert "DAR" in prompt
    assert "material-id" in prompt
    assert "dar-authoring" not in prompt
    assert "dar-package" not in prompt
    assert "/tmp" not in prompt
    assert "broker" not in prompt
    assert "MCP" not in prompt


def test_successor_run_prompt_names_only_the_saved_package_and_request() -> None:
    module = _harness_module()

    prompt = module._run_request("summary", "Summarize this text.")

    assert "dar-package invoke" in prompt
    assert "summary" in prompt
    assert "Summarize this text." in prompt
    assert "uv run" not in prompt
    assert "/" not in prompt
