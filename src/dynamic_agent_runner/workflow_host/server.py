"""Minimal stdio MCP server for the DAR authoring plugin launch spike."""

from __future__ import annotations

import json
import os
import socket
import stat
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any, TextIO

from dynamic_agent_runner.workflow_host.host import LocalWorkflowHost

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
    if len(values) == 3 and values[:2] == ["--stdio-proxy", "--socket"] and values[2]:
        try:
            return proxy_stdio_unix(
                socket_path=Path(values[2]), stdin=stdin, stdout=stdout
            )
        except ValueError:
            print("Broker proxy is unavailable", file=stderr)
            return 2
    if values == ["--stdio"]:
        session: _Session = _Session()
    elif (
        len(values) == 7
        and values[:2] == ["--authoring-stdio", "--material-set-id"]
        and values[2]
        and values[3] == "--package-name"
        and values[4]
        and values[5] == "--authoring-output-id"
        and values[6]
    ):
        session = _AuthoringSession(
            material_set_id=values[2],
            package_name=values[4],
            authoring_output_id=values[6],
        )
    else:
        print(
            "Usage: dynamic-agent-runner-mcp --stdio | "
            "--stdio-proxy --socket PATH | "
            "--authoring-stdio --material-set-id ID --package-name NAME "
            "--authoring-output-id ID",
            file=stderr,
        )
        return 2
    for line in stdin:
        if not line.strip():
            continue
        response = session.handle(line)
        if response is not None:
            stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            stdout.flush()
    return 0


class _Session:
    def __init__(
        self,
        *,
        host: Any | None = None,
        allowed_workflow_id: str | None = None,
        prepared_input_sink: Callable[[object], None] | None = None,
        host_opener=LocalWorkflowHost.open,
    ) -> None:
        self._initialized = False
        self._ready = False
        self._host = host
        self._allowed_workflow_id = allowed_workflow_id
        self._prepared_input_sink = prepared_input_sink
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
            self._open_host()
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
                "instructions": "Run registered workflows through the local DAR host.",
            },
        )

    def _call_tool(self, request_id: str | int, params: object) -> dict[str, Any]:
        if not isinstance(params, Mapping):
            return _error(request_id, -32602, "Invalid tool request")
        arguments = params.get("arguments")
        if not isinstance(arguments, Mapping):
            return _error(request_id, -32602, "Invalid tool request")
        if params.get("name") != "run_dar_workflow":
            return _error(request_id, -32602, "Invalid tool request")
        if (
            self._allowed_workflow_id is not None
            and arguments.get("workflow_id") != self._allowed_workflow_id
        ):
            return _error(request_id, -32000, "Workflow run failed")
        try:
            host = self._open_host()
            prepared = _prepare_request(host, arguments)
            if self._prepared_input_sink is not None:
                self._prepared_input_sink(prepared[1])
            result = host.run(
                workflow_id=prepared[0],
                prepared_input_id=prepared[1].prepared_input_id,
                now=datetime.now(UTC),
            )
        except (ValueError, OSError):
            return _error(request_id, -32000, "Workflow run failed")
        payload = {
            "status": result.status,
            "workflow_id": prepared[0],
            "run_id": result.run_id,
            **result.output,
        }
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

    def _open_host(self) -> Any:
        return self._host or self._host_opener(_default_state_root())


class _AuthoringSession(_Session):
    """One capability-reduced authoring session for a pre-issued material set."""

    def __init__(
        self,
        *,
        material_set_id: str,
        package_name: str,
        authoring_output_id: str,
        host: Any | None = None,
        finalized_sink: Callable[[object, str], None] | None = None,
        host_opener=LocalWorkflowHost.open,
    ) -> None:
        super().__init__(host=host, host_opener=host_opener)
        if not isinstance(material_set_id, str) or not material_set_id:
            raise ValueError("authoring material set is invalid")
        if not isinstance(package_name, str) or not package_name:
            raise ValueError("authoring package name is invalid")
        if not isinstance(authoring_output_id, str) or not authoring_output_id:
            raise ValueError("authoring output is invalid")
        self._material_set_id = material_set_id
        self._package_name = package_name
        self._authoring_output_id = authoring_output_id
        self._finalized_sink = finalized_sink
        self._created = False

    def _available_tools(self) -> list[dict[str, object]]:
        try:
            self._open_host()
        except (ValueError, OSError):
            return []
        return list(_AUTHORING_TOOLS)

    def _call_tool(self, request_id: str | int, params: object) -> dict[str, Any]:
        if not isinstance(params, Mapping) or not isinstance(
            params.get("arguments"), Mapping
        ):
            return _error(request_id, -32602, "Invalid tool request")
        try:
            name = params.get("name")
            arguments = params["arguments"]
            handler = {
                "project_authoring_materials": self._project_materials,
                "create_authored_package": self._create_package,
                "write_authored_package_file": self._write_package_file,
                "finalize_authored_package": self._finalize_package,
            }.get(name)
            if handler is None:
                return _error(request_id, -32602, "Invalid tool request")
            return _authoring_result(request_id, handler(self._open_host(), arguments))
        except (ValueError, OSError):
            return _error(request_id, -32000, "Authoring request failed")

    def _project_materials(
        self, host: Any, arguments: Mapping[str, object]
    ) -> dict[str, object]:
        _require_arguments(arguments, {"format_version"})
        projection = host.project_authoring_materials(
            self._material_set_id, now=datetime.now(UTC)
        )
        return {
            "material_set_id": projection.material_set_id,
            "members": [
                {
                    "artifact_id": member.artifact_id,
                    "content": member.content,
                    "digest": member.digest,
                    "disposition": member.disposition,
                    "role": member.role,
                }
                for member in projection.members
            ],
        }

    def _create_package(
        self, host: Any, arguments: Mapping[str, object]
    ) -> dict[str, object]:
        del host
        _require_arguments(arguments, {"format_version"})
        if self._created:
            raise ValueError("authoring output already exists")
        self._created = True
        return {
            "authoring_output_id": self._authoring_output_id,
            "package_name": self._package_name,
        }

    def _write_package_file(
        self, host: Any, arguments: Mapping[str, object]
    ) -> dict[str, object]:
        _require_arguments(
            arguments,
            {"format_version", "authoring_output_id", "relative_path", "content"},
        )
        if not self._created:
            raise ValueError("authoring output was not created")
        output_id = _authoring_output_id(arguments, self._authoring_output_id)
        relative_path = arguments.get("relative_path")
        content = arguments.get("content")
        if not isinstance(relative_path, str) or not isinstance(content, str):
            raise ValueError("authoring file is invalid")
        receipt = host.write_authored_package_file(
            output_id=output_id,
            relative_path=relative_path,
            content=content,
            now=datetime.now(UTC),
        )
        return {
            "relative_path": receipt.relative_path,
            "content_hash": receipt.content_hash,
            "byte_count": receipt.byte_count,
        }

    def _finalize_package(
        self, host: Any, arguments: Mapping[str, object]
    ) -> dict[str, object]:
        _require_arguments(arguments, {"format_version", "authoring_output_id"})
        if not self._created:
            raise ValueError("authoring output was not created")
        output_id = _authoring_output_id(arguments, self._authoring_output_id)
        validation, source_handle = host.finalize_and_select_authored_output(
            output_id=output_id,
            material_set_id=self._material_set_id,
            now=datetime.now(UTC),
        )
        if self._finalized_sink is not None:
            self._finalized_sink(validation, source_handle)
        return {
            "package_id": validation.package_id,
            "package_digest": validation.package_digest,
            "descriptor_digest": validation.descriptor_digest,
            "file_count": validation.file_count,
        }


def serve_authoring_broker(
    *,
    socket_path: Path,
    host: LocalWorkflowHost,
    material_set_id: str,
    package_name: str,
    authoring_output_id: str,
    finalized_sink: Callable[[object, str], None] | None = None,
    stop_event: threading.Event | None = None,
) -> None:
    """Serve one controller-owned authoring session without ambient host state."""

    if not isinstance(host, LocalWorkflowHost):
        raise ValueError("broker host is invalid")
    serve_session_unix(
        socket_path=socket_path,
        session=_AuthoringSession(
            material_set_id=material_set_id,
            package_name=package_name,
            authoring_output_id=authoring_output_id,
            host=host,
            finalized_sink=finalized_sink,
        ),
        stop_event=stop_event,
    )


def serve_workflow_broker(
    *,
    socket_path: Path,
    host: LocalWorkflowHost,
    workflow_id: str,
    prepared_input_sink: Callable[[object], None] | None = None,
    stop_event: threading.Event | None = None,
) -> None:
    """Serve one controller-owned generic workflow session without host paths."""

    if not isinstance(host, LocalWorkflowHost):
        raise ValueError("broker host is invalid")
    if not isinstance(workflow_id, str) or not workflow_id:
        raise ValueError("broker workflow is invalid")
    serve_session_unix(
        socket_path=socket_path,
        session=_Session(
            host=host,
            allowed_workflow_id=workflow_id,
            prepared_input_sink=prepared_input_sink,
        ),
        stop_event=stop_event,
    )


def serve_session_unix(
    *, socket_path: Path, session: _Session, stop_event: threading.Event | None = None
) -> None:
    """Serve one already-bound host session over a controller-owned UNIX socket."""

    _validate_broker_socket(socket_path)
    if not isinstance(session, _Session):
        raise ValueError("broker session is invalid")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            previous_umask = os.umask(0o177)
            try:
                listener.bind(str(socket_path))
            finally:
                os.umask(previous_umask)
            listener.listen(1)
            listener.settimeout(0.1)
            while stop_event is None or not stop_event.is_set():
                try:
                    connection, _ = listener.accept()
                except TimeoutError:
                    continue
                with connection:
                    _serve_connection(connection, session)
                return
    finally:
        try:
            socket_path.unlink()
        except FileNotFoundError:
            pass


def proxy_stdio_unix(*, socket_path: Path, stdin: TextIO, stdout: TextIO) -> int:
    """Bridge a clean actor's stdio to a controller-owned broker socket."""

    _validate_broker_socket(socket_path, must_exist=True)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        try:
            connection.connect(str(socket_path))
        except OSError as error:
            raise ValueError("broker socket is unavailable") from error
        reader = connection.makefile("r", encoding="utf-8")
        writer = connection.makefile("w", encoding="utf-8")
        relay = threading.Thread(
            target=_relay_responses,
            args=(reader, stdout),
            daemon=True,
        )
        relay.start()
        try:
            for line in stdin:
                writer.write(line)
                writer.flush()
        finally:
            writer.close()
            connection.shutdown(socket.SHUT_WR)
        relay.join()
    return 0


def _serve_connection(connection: socket.socket, session: _Session) -> None:
    reader = connection.makefile("r", encoding="utf-8")
    writer = connection.makefile("w", encoding="utf-8")
    try:
        _serve_reader_writer(reader, writer, session)
    finally:
        reader.close()
        writer.close()


def _serve_reader_writer(reader: TextIO, writer: TextIO, session: _Session) -> None:
    for line in reader:
        response = session.handle(line)
        if response is not None:
            writer.write(json.dumps(response, separators=(",", ":")) + "\n")
            writer.flush()


def _relay_responses(reader: TextIO, stdout: TextIO) -> None:
    try:
        for line in reader:
            stdout.write(line)
            stdout.flush()
    finally:
        reader.close()


def _validate_broker_socket(socket_path: object, *, must_exist: bool = False) -> None:
    if not isinstance(socket_path, Path) or not socket_path.is_absolute():
        raise ValueError("broker socket is invalid")
    if len(os.fsencode(socket_path)) >= 104:
        raise ValueError("broker socket is invalid")
    parent = socket_path.parent
    if parent.is_symlink():
        raise ValueError("broker socket is invalid")
    try:
        mode = os.lstat(parent).st_mode
    except OSError as error:
        raise ValueError("broker socket is unavailable") from error
    if not stat.S_ISDIR(mode) or mode & 0o077:
        raise ValueError("broker socket is unavailable")
    if not must_exist:
        if socket_path.exists() or socket_path.is_symlink():
            raise ValueError("broker socket already exists")
        return
    try:
        mode = os.lstat(socket_path).st_mode
    except OSError as error:
        raise ValueError("broker socket is unavailable") from error
    if not stat.S_ISSOCK(mode) or socket_path.is_symlink():
        raise ValueError("broker socket is unavailable")


_RUN_TOOL = {
    "name": "run_dar_workflow",
    "description": "Run one registered local DAR workflow.",
    "inputSchema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["format_version", "workflow_id", "prompt"],
        "properties": {
            "format_version": {"const": 1},
            "workflow_id": {"type": "string", "minLength": 1},
            "prompt": {"type": "string", "minLength": 1},
        },
    },
}

_FORMAT_VERSION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["format_version"],
    "properties": {"format_version": {"const": 1}},
}

_AUTHORING_TOOLS = (
    {
        "name": "project_authoring_materials",
        "description": "Read the host-approved material projection for this session.",
        "inputSchema": _FORMAT_VERSION_SCHEMA,
    },
    {
        "name": "create_authored_package",
        "description": "Create this session's one host-owned workflow package.",
        "inputSchema": _FORMAT_VERSION_SCHEMA,
    },
    {
        "name": "write_authored_package_file",
        "description": "Atomically write one declared file in this session's package.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "format_version",
                "authoring_output_id",
                "relative_path",
                "content",
            ],
            "properties": {
                "format_version": {"const": 1},
                "authoring_output_id": {"type": "string", "minLength": 1},
                "relative_path": {"type": "string", "minLength": 1},
                "content": {"type": "string"},
            },
        },
    },
    {
        "name": "finalize_authored_package",
        "description": "Validate and finalize this session's one workflow package.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["format_version", "authoring_output_id"],
            "properties": {
                "format_version": {"const": 1},
                "authoring_output_id": {"type": "string", "minLength": 1},
            },
        },
    },
)


def _require_arguments(arguments: Mapping[str, object], expected: set[str]) -> None:
    if set(arguments) != expected or arguments.get("format_version") != 1:
        raise ValueError("authoring tool arguments are invalid")


def _authoring_output_id(
    arguments: Mapping[str, object], expected_output_id: str | None
) -> str:
    value = arguments.get("authoring_output_id")
    if (
        expected_output_id is None
        or not isinstance(value, str)
        or value != expected_output_id
    ):
        raise ValueError("authoring output is invalid")
    return value


def _authoring_result(
    request_id: str | int, payload: Mapping[str, object]
) -> dict[str, Any]:
    value = dict(payload)
    return _result(
        request_id,
        {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(value, sort_keys=True, separators=(",", ":")),
                }
            ],
            "structuredContent": value,
        },
    )


def _prepare_request(
    host: LocalWorkflowHost, arguments: Mapping[str, object]
) -> tuple[str, Any]:
    if set(arguments) != {"format_version", "workflow_id", "prompt"}:
        raise ValueError("workflow run request is invalid")
    if arguments.get("format_version") != 1:
        raise ValueError("workflow run request is invalid")
    workflow_id = arguments.get("workflow_id")
    prompt = arguments.get("prompt")
    if (
        not isinstance(workflow_id, str)
        or not workflow_id
        or not isinstance(prompt, str)
        or not prompt
    ):
        raise ValueError("workflow run request is invalid")
    prepared = host.prepare(
        workflow_id=workflow_id,
        prompt=prompt,
        now=datetime.now(UTC),
    )
    return workflow_id, prepared


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
