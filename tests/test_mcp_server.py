"""Tests for the generic Dynamic Agent Runner stdio MCP entry point."""

from __future__ import annotations

import json
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


def test_stdio_server_hides_execution_tools_without_a_configured_host() -> None:
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

    responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert responses[0]["result"]["serverInfo"] == {
        "name": "Dynamic Agent Runner",
        "version": version("dynamic-agent-runner"),
    }
    assert responses[1]["result"]["tools"] == []


def test_stdio_server_advertises_the_closed_tool_when_a_host_is_configured() -> None:
    from dynamic_agent_runner.workflow_host.server import _Session

    session = _Session(host_opener=lambda _root: object())
    session.handle('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}')
    session.handle('{"jsonrpc":"2.0","method":"notifications/initialized"}')

    response = session.handle('{"jsonrpc":"2.0","id":2,"method":"tools/list"}')

    assert response is not None
    assert response["result"]["tools"] == [
        {
            "name": "run_dar_workflow",
            "description": "Run one registered sealed local DAR workflow.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["format_version", "workflow_id", "prepared_input_id"],
                "properties": {
                    "format_version": {"const": 1},
                    "workflow_id": {"type": "string", "minLength": 1},
                    "prepared_input_id": {"type": "string", "minLength": 1},
                },
            },
        }
    ]


def test_stdio_server_runs_only_closed_sealed_workflow_requests() -> None:
    from dynamic_agent_runner.workflow_host.runner import RunDarWorkflowResult
    from dynamic_agent_runner.workflow_host.server import _Session

    class Host:
        def __init__(self) -> None:
            self.calls: list[dict[str, str]] = []

        def run(self, *, workflow_id: str, prepared_input_id: str, now: object):
            self.calls.append(
                {
                    "workflow_id": workflow_id,
                    "prepared_input_id": prepared_input_id,
                }
            )
            return RunDarWorkflowResult(
                status="completed", run_id="run-1", output={"message": "done"}
            )

    host = Host()
    session = _Session(host_opener=lambda _root: host)
    session.handle('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}')
    session.handle('{"jsonrpc":"2.0","method":"notifications/initialized"}')

    response = session.handle(
        """{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"run_dar_workflow","arguments":{"format_version":1,"workflow_id":"document-helper","prepared_input_id":"v1.sealed.signature"}}}"""
    )

    assert host.calls == [
        {"workflow_id": "document-helper", "prepared_input_id": "v1.sealed.signature"}
    ]
    assert response is not None
    assert response["result"]["structuredContent"] == {
        "status": "completed",
        "run_id": "run-1",
        "message": "done",
    }
