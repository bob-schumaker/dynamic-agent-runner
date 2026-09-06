"""Private UNIX-socket bridge for controller-mediated package commands."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from io import StringIO
import json
from pathlib import Path
import socket
from threading import Event
from typing import Any


def serve_package_controller(
    *,
    socket_path: Path,
    host: object,
    allowed_commands: tuple[str, ...],
    stop_event: Event,
    approval_broker_factory: Callable[[], object] | None = None,
    guardrail_registry: object | None = None,
    workspace_artifact_ids: Sequence[str] = (),
) -> None:
    """Serve allowed package commands against one controller-owned host."""

    if (
        not socket_path.is_absolute()
        or socket_path.exists()
        or not allowed_commands
        or any(
            not isinstance(command, str) or not command for command in allowed_commands
        )
    ):
        raise ValueError("package controller inputs are invalid")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(str(socket_path))
        listener.listen(1)
        listener.settimeout(0.1)
        try:
            while not stop_event.is_set():
                try:
                    connection, _ = listener.accept()
                except TimeoutError:
                    continue
                with connection:
                    _serve_connection(
                        connection,
                        host=host,
                        allowed_commands=frozenset(allowed_commands),
                        approval_broker_factory=approval_broker_factory,
                        guardrail_registry=guardrail_registry,
                        workspace_artifact_ids=workspace_artifact_ids,
                    )
        finally:
            try:
                socket_path.unlink()
            except FileNotFoundError:
                pass


def proxy_package_command(
    *, socket_path: Path, arguments: Sequence[str], stdin: str
) -> tuple[int, str, str]:
    """Send one actor command to the controller without opening host state."""

    if not socket_path.is_absolute() or not arguments:
        raise ValueError("package controller request is invalid")
    request = json.dumps({"arguments": list(arguments), "stdin": stdin}) + "\n"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(str(socket_path))
        connection.sendall(request.encode("utf-8"))
        response = _read_line(connection)
    value = json.loads(response)
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("returncode"), int)
        or not isinstance(value.get("stdout"), str)
        or not isinstance(value.get("stderr"), str)
    ):
        raise ValueError("package controller response is invalid")
    return value["returncode"], value["stdout"], value["stderr"]


def _serve_connection(
    connection: socket.socket,
    *,
    host: object,
    allowed_commands: frozenset[str],
    approval_broker_factory: Callable[[], object] | None,
    guardrail_registry: object | None,
    workspace_artifact_ids: Sequence[str],
) -> None:
    try:
        request: Any = json.loads(_read_line(connection))
        arguments = request["arguments"]
        stdin = request["stdin"]
        if (
            not isinstance(arguments, list)
            or not arguments
            or any(not isinstance(argument, str) for argument in arguments)
            or not isinstance(stdin, str)
            or arguments[0] not in allowed_commands
        ):
            raise ValueError
        from dynamic_agent_runner.dar_package_cli import main

        stdout, stderr = StringIO(), StringIO()
        returncode = main(
            arguments,
            stdin=StringIO(stdin),
            stdout=stdout,
            stderr=stderr,
            host_opener=lambda _root: host,
            approval_broker_factory=approval_broker_factory,
            guardrail_registry=guardrail_registry,
            workspace_artifact_ids=workspace_artifact_ids,
        )
        response = {
            "returncode": returncode,
            "stdout": stdout.getvalue(),
            "stderr": stderr.getvalue(),
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        response = {"returncode": 2, "stdout": "", "stderr": ""}
    connection.sendall((json.dumps(response) + "\n").encode("utf-8"))


def _read_line(connection: socket.socket) -> str:
    chunks: list[bytes] = []
    while True:
        chunk = connection.recv(4096)
        if not chunk:
            break
        chunks.append(chunk)
        if b"\n" in chunk:
            break
    return b"".join(chunks).split(b"\n", 1)[0].decode("utf-8")
