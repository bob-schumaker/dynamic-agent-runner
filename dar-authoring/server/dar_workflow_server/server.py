"""Minimal stdio MCP server for the DAR authoring plugin launch spike."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from typing import Any, TextIO


SERVER_NAME = "DAR Authoring"
SERVER_VERSION = "0.1.0"
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
        print("Usage: dar-authoring-mcp --stdio", file=stderr)
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
    def __init__(self) -> None:
        self._initialized = False
        self._ready = False

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
        if not self._ready:
            return _error(request_id, -32002, "Server not initialized")
        if method == "tools/list":
            return _result(request_id, {"tools": []})
        return _error(request_id, -32601, "Method not found")

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
                "instructions": "Workflow execution is unavailable until G1 and G3 pass.",
            },
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
