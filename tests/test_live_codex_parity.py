"""Opt-in live parity check for DAR and the installed Codex CLI."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from dynamic_agent_runner.openai_client import (
    OpenAIMessage,
    OpenAIProviderConfig,
    build_openai_request,
    create_async_openai_adapter,
    create_default_async_openai_provider,
)


LIVE_ENV = "DAR_RUN_LIVE_CODEX_PARITY"
PROMPT = "Reply with exactly: DAR_CODEX_PARITY_OK"


def _codex_cli() -> str:
    configured = os.environ.get("DAR_CODEX_CLI")
    if configured:
        return configured
    return shutil.which("codex") or pytest.fail("codex CLI is not installed")


def _trace_payloads(trace_root: Path) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for path in trace_root.glob("**/payloads/*.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            payloads.append(value)
    return payloads


@pytest.mark.skipif(
    os.environ.get(LIVE_ENV) != "1",
    reason=f"set {LIVE_ENV}=1 to run live ChatGPT/Codex parity coverage",
)
def test_live_dar_and_codex_cli_complete_same_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catch auth, model-catalog, request, and stream drift against Codex CLI."""

    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    source_codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    for filename in (
        "auth.json",
        "version.json",
        "config.toml",
        "cloud-config-bundle-cache.json",
        "cloud-requirements-cache.json",
    ):
        source = source_codex_home / filename
        if source.exists():
            shutil.copy2(source, codex_home / filename)

    trace_root = tmp_path / "codex-traces"
    cli_env = os.environ.copy()
    cli_env["CODEX_HOME"] = str(codex_home)
    cli_env["CODEX_ROLLOUT_TRACE_ROOT"] = str(trace_root)
    cli = subprocess.run(
        [
            _codex_cli(),
            "exec",
            "--json",
            "--skip-git-repo-check",
            PROMPT,
        ],
        check=False,
        capture_output=True,
        text=True,
        env=cli_env,
        timeout=180,
    )
    assert cli.returncode == 0, cli.stderr
    assert cli.stdout.strip(), cli.stderr
    assert any(
        payload.get("model") or payload.get("input")
        for payload in _trace_payloads(trace_root)
    ), "Codex CLI produced no captured inference request payload"

    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    async def run_dar() -> str:
        provider = create_default_async_openai_provider(
            OpenAIProviderConfig(codex_auth_preference="chatgpt_first")
        )
        adapter = create_async_openai_adapter(provider=provider)
        model = os.environ.get("DAR_LIVE_MODEL") or await adapter.default_model()
        request = build_openai_request(
            model=model,
            messages=(OpenAIMessage(role="user", content=PROMPT),),
        )
        response = await asyncio.wait_for(adapter.create_response(request), timeout=180)
        return response.content

    assert asyncio.run(run_dar()).strip()
