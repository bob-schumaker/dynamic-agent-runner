"""Opt-in live parity check for DAR and the installed Codex CLI."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest

from dynamic_agent_runner.openai_client import (
    OpenAIMessage,
    OpenAIProviderConfig,
    build_openai_request,
    create_async_openai_adapter,
    create_default_async_openai_provider,
)


LIVE_ENV = "DAR_RUN_LIVE_CODEX_PARITY"
MODEL_ENV = "DAR_LIVE_MODEL"
PROMPT = (
    "Return exactly one JSON object with string field `status` equal to `ok` "
    "and string field `value` equal to `DAR_STRUCTURED_PARITY_OK`. Do not add "
    "markdown or an envelope."
)
StructuredValidator = Callable[[str], Mapping[str, Any]]


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


def _validate_structured_probe(content: str) -> Mapping[str, Any]:
    value = json.loads(content)
    if not isinstance(value, Mapping):
        raise AssertionError("structured response must be a JSON object")
    if value.get("status") != "ok" or value.get("value") != "DAR_STRUCTURED_PARITY_OK":
        raise AssertionError(f"unexpected structured response: {value!r}")
    return value


def _codex_message(output: str) -> str:
    messages: list[str] = []
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = event.get("item")
        if isinstance(item, Mapping) and item.get("type") == "agent_message":
            text = item.get("text")
            if isinstance(text, str):
                messages.append(text)
    if not messages:
        raise AssertionError("Codex CLI emitted no agent message")
    return messages[-1]


def test_structured_probe_validator_requires_expected_contract() -> None:
    assert (
        _validate_structured_probe(
            '{"status":"ok","value":"DAR_STRUCTURED_PARITY_OK"}'
        )["status"]
        == "ok"
    )
    with pytest.raises(AssertionError, match="unexpected structured response"):
        _validate_structured_probe('{"status":"ok"}')


def test_codex_message_reads_agent_message_from_jsonl() -> None:
    output = json.dumps(
        {"type": "item.completed", "item": {"type": "agent_message", "text": "{}"}}
    )
    assert _codex_message(output) == "{}"


@pytest.mark.skipif(
    os.environ.get(LIVE_ENV) != "1",
    reason=f"set {LIVE_ENV}=1 to run live ChatGPT/Codex parity coverage",
)
def test_live_dar_and_codex_cli_complete_same_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Compare two authenticated client paths against one structured contract."""

    model = os.environ.get(MODEL_ENV) or "gpt-5.4-mini"

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
            "--model",
            model,
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
    _validate_structured_probe(_codex_message(cli.stdout))
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
        request = build_openai_request(
            model=model,
            messages=(OpenAIMessage(role="user", content=PROMPT),),
        )
        response = await asyncio.wait_for(adapter.create_response(request), timeout=180)
        if response.content is None:
            raise AssertionError("DAR returned no response content")
        return response.content

    _validate_structured_probe(asyncio.run(run_dar()))
