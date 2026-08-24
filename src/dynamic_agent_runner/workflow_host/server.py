"""Minimal stdio MCP server for the DAR authoring plugin launch spike."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any, TextIO

from dynamic_agent_runner.workflow_host.host import LocalWorkflowHost
from dynamic_agent_runner.workflow_host.runner import RunDarWorkflowRequest


SERVER_NAME = "Dynamic Agent Runner"
SERVER_VERSION = version("dynamic-agent-runner")
PROTOCOL_VERSION = "2025-06-18"


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Serve the launch-spike MCP lifecycle over newline-delimited stdio."""

    values = list(sys.argv[1:] if argv is None else argv)
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    if values != ["--stdio"]:
        print("Usage: dynamic-agent-runner-mcp --stdio", file=stderr)
        return 2

    session = _Session()
    for line in stdin:
        if not line.strip():
            continue
        response = session.handle(line)
        if response is not None:
            stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            stdout.flush()
    return 0


class _Session:
    def __init__(self, *, host_opener=LocalWorkflowHost.open) -> None:
        self._initialized = False
        self._ready = False
        self._host_opener = host_opener

    def handle(self, line: str) -> dict[str, Any] | None:
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            return _error(None, -32700, "Parse error")
        if not isinstance(message, Mapping) or message.get("jsonrpc") != "2.0":
            return _error(_request_id(message), -32600, "Invalid Request")

        method = message.get("method")
        if not isinstance(method, str):
            return _error(_request_id(message), -32600, "Invalid Request")
        request_id = _request_id(message)

        if method == "initialize":
            return self._initialize(request_id, message.get("params"))
        if method == "notifications/initialized":
            if self._initialized:
                self._ready = True
            return None
        if request_id is None:
            return None
        return self._ready_request(request_id, method, message.get("params"))

    def _ready_request(
        self, request_id: str | int, method: str, params: object
    ) -> dict[str, Any]:
        if not self._ready:
            return _error(request_id, -32002, "Server not initialized")
        if method == "tools/list":
            return _result(request_id, {"tools": self._available_tools()})
        if method == "tools/call":
            return self._call_tool(request_id, params)
        return _error(request_id, -32601, "Method not found")

    def _available_tools(self) -> list[dict[str, object]]:
        try:
            self._host_opener(_default_state_root())
        except (ValueError, OSError):
            return []
        return [_RUN_TOOL]

    def _initialize(
        self,
        request_id: str | int | None,
        params: object,
    ) -> dict[str, Any]:
        if request_id is None or not isinstance(params, Mapping):
            return _error(request_id, -32600, "Invalid Request")
        self._initialized = True
        return _result(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": "Prepare workflow input through the local dar-workflow CLI before calling run_dar_workflow.",
            },
        )

    def _call_tool(self, request_id: str | int, params: object) -> dict[str, Any]:
        if not isinstance(params, Mapping) or params.get("name") != "run_dar_workflow":
            return _error(request_id, -32602, "Invalid tool request")
        arguments = params.get("arguments")
        if not isinstance(arguments, Mapping):
            return _error(request_id, -32602, "Invalid tool request")
        try:
            request = RunDarWorkflowRequest.from_mapping(arguments)
            host = self._host_opener(_default_state_root())
            result = host.run(
                workflow_id=request.workflow_id,
                prepared_input_id=request.prepared_input_id,
                now=datetime.now(UTC),
            )
        except (ValueError, OSError):
            return _error(request_id, -32000, "Workflow run failed")
        payload = {"status": result.status, "run_id": result.run_id, **result.output}
        return _result(
            request_id,
            {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            payload, sort_keys=True, separators=(",", ":")
                        ),
                    }
                ],
                "structuredContent": payload,
            },
        )


_RUN_TOOL = {
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


def _default_state_root() -> Path:
    configured = os.environ.get("DAR_AUTHORING_STATE_ROOT")
    if configured:
        return Path(configured)
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "dar-authoring"
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / (
        "dar-authoring"
    )


def _request_id(message: object) -> str | int | None:
    if not isinstance(message, Mapping):
        return None
    value = message.get("id")
    if isinstance(value, (str, int)) and not isinstance(value, bool):
        return value
    return None


def _result(request_id: str | int, value: Mapping[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": dict(value)}


def _error(
    request_id: str | int | None,
    code: int,
    message: str,
) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def console_main() -> None:
    """Console-script entry point."""

    raise SystemExit(main())


if __name__ == "__main__":  # pragma: no cover - exercised through subprocess.
    console_main()
