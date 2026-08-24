"""Tests for the DAR authoring plugin's G0 stdio launch spike."""

from __future__ import annotations

import json
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "dar-authoring"


def _read_json_lines(output: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in output.splitlines() if line]


def test_plugin_declares_a_fixed_uvx_stdio_launch_contract() -> None:
    manifest = json.loads(
        (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    mcp_config = json.loads((PLUGIN_ROOT / ".mcp.json").read_text(encoding="utf-8"))

    assert manifest["name"] == "dar-authoring"
    assert manifest["mcpServers"] == "./.mcp.json"
    server = mcp_config["mcpServers"]["dar-authoring"]
    assert server["command"] == "uvx"
    assert server["args"] == [
        "--default-index",
        "https://artifactory.oci.oraclecorp.com/api/pypi/global-release-pypi/simple",
        "--from",
        "dynamic-agent-runner==0.1.16",
        "dynamic-agent-runner-mcp",
        "--stdio",
    ]
    assert all("{" not in value for value in server["args"])
    assert not any(value.startswith(("/", "./", "../")) for value in server["args"])


def test_plugin_bundle_contains_only_local_authoring_assets() -> None:
    assert {
        ".codex-plugin/plugin.json",
        ".mcp.json",
        "skills/agent-development/SKILL.md",
        "skills/agent-tool-contract-design/SKILL.md",
        "skills/agent-evaluation/SKILL.md",
        "templates/workflow-descriptor.yaml",
        "read-only-mcp-template/workflow-descriptor.yaml",
    } <= {
        path.relative_to(PLUGIN_ROOT).as_posix()
        for path in PLUGIN_ROOT.rglob("*")
        if path.is_file()
    }
    assert not any((PLUGIN_ROOT / "server").rglob("*.py"))


def test_dar_stdio_server_initializes_without_execution_tools_before_configuration(
    tmp_path: Path,
) -> None:
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
        [sys.executable, "-m", "dynamic_agent_runner.mcp_server", "--stdio"],
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
                    "name": "Dynamic Agent Runner",
                    "version": version("dynamic-agent-runner"),
                },
                "instructions": "Run registered workflows through the local DAR host.",
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {"tools": []},
        },
    ]


def test_server_seals_input_before_running_a_registered_workflow() -> None:
    from datetime import UTC, datetime, timedelta

    from dynamic_agent_runner.workflow_host.preparation import PreparedWorkflowInput
    from dynamic_agent_runner.workflow_host.runner import RunDarWorkflowResult
    from dynamic_agent_runner.workflow_host.server import _Session

    class Host:
        def __init__(self) -> None:
            self.calls: list[dict[str, str]] = []

        def prepare(self, *, workflow_id: str, prompt: str, now):
            assert workflow_id == "document-helper"
            assert prompt == "Answer this document question."
            return PreparedWorkflowInput(
                prepared_input_id="v1.sealed.signature",
                workflow_id=workflow_id,
                registration_digest="registration-digest",
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )

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
                        "prompt": "Answer this document question.",
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
        "workflow_id": "document-helper",
        "run_id": "run-1",
        "message": "done",
    }
