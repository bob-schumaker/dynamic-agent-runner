"""Tests for the DAR authoring plugin's G0 stdio launch spike."""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "dar-authoring"
SERVER_PATH = PLUGIN_ROOT / "server" / "dar_workflow_server" / "server.py"
sys.path.insert(0, str(PLUGIN_ROOT / "server"))


def _read_json_lines(output: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in output.splitlines() if line]


def test_plugin_declares_a_fixed_uvx_stdio_launch_contract() -> None:
    manifest = json.loads(
        (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    mcp_config = json.loads((PLUGIN_ROOT / ".mcp.json").read_text(encoding="utf-8"))
    project = tomllib.loads(
        (PLUGIN_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    assert manifest["name"] == "dar-authoring"
    assert manifest["mcpServers"] == "./.mcp.json"
    assert project["project"]["name"] == "dar-authoring"
    assert project["project"]["dependencies"] == [
        "dynamic-agent-runner==0.1.15",
        "keyring>=25.7.0",
        "jsonschema>=4.26.0,<5.0.0",
        "PyYAML>=6.0.3",
    ]
    assert project["project"]["scripts"] == {
        "dar-authoring-mcp": "dar_workflow_server.server:console_main",
        "dar-workflow": "dar_workflow_server.cli:console_main",
        "dar-workflow-run": "dar_workflow_server.cli:run_console_main",
    }
    server = mcp_config["mcpServers"]["dar-authoring"]
    assert server["command"] == "uvx"
    assert server["args"] == [
        "--default-index",
        "https://artifactory.oci.oraclecorp.com/api/pypi/global-release-pypi/simple",
        "--from",
        "dar-authoring==0.1.0",
        "dar-authoring-mcp",
        "--stdio",
    ]
    assert all("{" not in value for value in server["args"])
    assert not any(value.startswith(("/", "./", "../")) for value in server["args"])


def test_stdio_server_initializes_and_exposes_no_tools(tmp_path: Path) -> None:
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]

    completed = subprocess.run(
        [sys.executable, str(SERVER_PATH), "--stdio"],
        input="".join(f"{json.dumps(request)}\n" for request in requests),
        capture_output=True,
        cwd=tmp_path,
        encoding="utf-8",
        check=False,
        timeout=5,
    )

    assert completed.returncode == 0, completed.stderr
    responses = _read_json_lines(completed.stdout)
    assert responses == [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "DAR Authoring",
                    "version": "0.1.0",
                },
                "instructions": "Prepare workflow input through the local dar-workflow CLI before calling run_dar_workflow.",
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {
                "tools": [
                    {
                        "name": "run_dar_workflow",
                        "description": "Run one registered sealed local DAR workflow.",
                        "inputSchema": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": [
                                "format_version",
                                "workflow_id",
                                "prepared_input_id",
                            ],
                            "properties": {
                                "format_version": {"const": 1},
                                "workflow_id": {"type": "string", "minLength": 1},
                                "prepared_input_id": {
                                    "type": "string",
                                    "minLength": 1,
                                },
                            },
                        },
                    }
                ]
            },
        },
    ]


def test_server_runs_only_closed_sealed_workflow_requests() -> None:
    from dar_workflow_server.runner import RunDarWorkflowResult
    from dar_workflow_server.server import _Session

    class Host:
        def __init__(self) -> None:
            self.calls: list[dict[str, str]] = []

        def run(self, *, workflow_id: str, prepared_input_id: str, now):
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
    session.handle(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            }
        )
    )
    session.handle(
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
    )

    response = session.handle(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "run_dar_workflow",
                    "arguments": {
                        "format_version": 1,
                        "workflow_id": "document-helper",
                        "prepared_input_id": "v1.sealed.signature",
                    },
                },
            }
        )
    )

    assert host.calls == [
        {"workflow_id": "document-helper", "prepared_input_id": "v1.sealed.signature"}
    ]
    assert response["result"]["structuredContent"] == {
        "status": "completed",
        "run_id": "run-1",
        "message": "done",
    }
