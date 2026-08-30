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


def test_clean_codex_environment_exposes_cli_state_not_a_broker(tmp_path: Path) -> None:
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
        "DAR_AUTHORING_DAR_WHEEL": str(tmp_path / "dynamic_agent_runner.whl"),
        "DAR_AUTHORING_STATE_ROOT": str(tmp_path / "state"),
        "DAR_AUTHORING_TEMPLATE_ROOT": str(tmp_path / "templates"),
        "UV_CACHE_DIR": str(tmp_path / "workspace" / ".uv-cache"),
        "HOME": str(tmp_path / "workspace"),
        "LANG": "C.UTF-8",
        "PATH": "/usr/bin:/bin",
    }
    assert not {key for key in environment if "BROKER" in key or "MCP_MODE" in key}


def test_clean_codex_environment_rejects_non_absolute_state_root(
    tmp_path: Path,
) -> None:
    with pytest.raises(M44CleanCodexError):
        build_clean_codex_environment(
            codex_home=tmp_path / "codex-home",
            working_directory=tmp_path / "workspace",
            wheel=tmp_path / "dynamic_agent_runner.whl",
            state_root=Path("state"),
            template_root=tmp_path / "templates",
            inherited={"PATH": "/usr/bin:/bin"},
        )


def test_marketplace_contains_only_the_copied_plugin(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"
    (plugin / ".codex-plugin").mkdir(parents=True)
    (plugin / ".codex-plugin" / "plugin.json").write_text("{}", encoding="utf-8")

    marketplace = create_marketplace(
        plugin_root=plugin, destination=tmp_path / "marketplace"
    )

    assert marketplace.is_file()
    assert (tmp_path / "marketplace" / "plugins" / "dar-authoring").is_dir()


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


def test_author_prompt_requires_direct_cli_and_never_a_broker() -> None:
    module = _harness_module()

    prompt = module._author_request(
        "Design a summary workflow.",
        "material-id",
        "summary",
        Path("/tmp/dar.whl"),
        "openai/local-model",
        "pass",
    )

    assert "uv run --no-project --python 3.14 --with /tmp/dar.whl dar-package" in prompt
    assert "MCP" in prompt
    assert "broker" in prompt
    assert "material-id" in prompt
    assert "openai/local-model" in prompt
