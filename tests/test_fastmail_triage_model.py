"""Tests for the pinned local Qwen binding used by Fastmail triage."""

from __future__ import annotations

from pathlib import Path


def test_fastmail_triage_qwen_binding_is_pinned_and_offline(tmp_path: Path) -> None:
    from dynamic_agent_runner.workflow_host.fastmail_triage_model import (
        FASTMAIL_TRIAGE_MODEL_ALIAS,
        create_fastmail_triage_qwen_config,
    )

    config = create_fastmail_triage_qwen_config(
        model_path=tmp_path / "qwen.gguf",
        model_kwargs={"chat_format": "chatml-function-calling", "n_ctx": 8192},
    )

    assert config.model_aliases == (FASTMAIL_TRIAGE_MODEL_ALIAS,)
    assert config.allow_network is False
    assert config.expected_model_sha256 == (
        "626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d"
    )
    assert config.huggingface_file is not None
    assert config.huggingface_file.repo_id == "Qwen/Qwen2.5-3B-Instruct-GGUF"
    assert (
        config.huggingface_file.revision == "7dabda4d13d513e3e842b20f0d435c732f172cbe"
    )
