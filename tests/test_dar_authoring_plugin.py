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
    assert project["project"]["dependencies"] == ["dynamic-agent-runner==0.1.0"]
    assert project["project"]["scripts"] == {
        "dar-authoring-mcp": "dar_workflow_server.server:console_main"
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
                "instructions": "Workflow execution is unavailable until G1 and G3 pass.",
            },
        },
        {"jsonrpc": "2.0", "id": 2, "result": {"tools": []}},
    ]
