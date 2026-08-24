"""Tests for the generic Dynamic Agent Runner stdio MCP entry point."""

from __future__ import annotations

from io import StringIO
from importlib.metadata import version
from pathlib import Path
import tomllib

from dynamic_agent_runner.mcp_server import main


def test_project_declares_the_generic_stdio_mcp_entry_point() -> None:
    project = tomllib.loads(
        (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(
            encoding="utf-8"
        )
    )

    assert project["project"]["scripts"]["dynamic-agent-runner-mcp"] == (
        "dynamic_agent_runner.mcp_server:console_main"
    )


def test_stdio_server_initializes_and_advertises_no_tools_before_host_setup() -> None:
    stdin = StringIO(
        "\n".join(
            (
                '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}',
                '{"jsonrpc":"2.0","method":"notifications/initialized"}',
                '{"jsonrpc":"2.0","id":2,"method":"tools/list"}',
            )
        )
        + "\n"
    )
    stdout = StringIO()

    assert main(["--stdio"], stdin=stdin, stdout=stdout, stderr=StringIO()) == 0

    assert stdout.getvalue().splitlines() == [
        '{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-06-18","capabilities":{"tools":{}},"serverInfo":{"name":"Dynamic Agent Runner","version":"'
        + version("dynamic-agent-runner")
        + '"}}}',
        '{"jsonrpc":"2.0","id":2,"result":{"tools":[]}}',
    ]
