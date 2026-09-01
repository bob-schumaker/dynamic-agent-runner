"""Tests for the private controller bridge behind clean actor launchers."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from threading import Event, Thread
from time import sleep
from uuid import uuid4

from dynamic_agent_runner import dar_package_cli
from dynamic_agent_runner.workflow_host.package_controller import (
    serve_package_controller,
)


def test_controller_proxy_runs_an_invoke_against_its_private_host(
    tmp_path: Path,
) -> None:
    socket_path = Path("/private/tmp") / f"dar-controller-{uuid4().hex}.sock"
    stopped = Event()
    observed: dict[str, object] = {}

    class Host:
        def invoke_saved(self, **kwargs: object) -> object:
            observed.update(kwargs)
            return type(
                "Result",
                (),
                {
                    "status": "completed",
                    "run_id": "run-1",
                    "output": {"message": "done"},
                },
            )()

    thread = Thread(
        target=serve_package_controller,
        kwargs={
            "socket_path": socket_path,
            "host": Host(),
            "allowed_commands": ("invoke",),
            "stop_event": stopped,
            "workspace_artifact_ids": ("v1.controller-artifact",),
        },
        daemon=True,
    )
    thread.start()
    for _ in range(20):
        if socket_path.exists():
            break
        sleep(0.01)

    assert (
        dar_package_cli.main(
            [
                "--controller-proxy",
                "--socket",
                str(socket_path),
                "invoke",
                "--package-name",
                "summary",
                "--prompt-stdin",
            ],
            stdin=StringIO("Summarize this document."),
        )
        == 0
    )
    assert observed["workspace_artifact_ids"] == ("v1.controller-artifact",)
    assert observed["workspace_files"] == ()
    assert (
        dar_package_cli.main(
            [
                "--controller-proxy",
                "--socket",
                str(socket_path),
                "create-authored-package",
                "--package-name",
                "summary",
            ],
            stdin=StringIO(),
        )
        == 2
    )
    stopped.set()
    thread.join(timeout=1)
    assert not thread.is_alive()
