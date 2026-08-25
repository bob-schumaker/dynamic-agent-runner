"""Narrow skill-facing surface for the DAR package control plane."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import TextIO

from dynamic_agent_runner.workflow_host.cli import TerminalApprovalBroker
from dynamic_agent_runner.workflow_host.host import (
    LocalWorkflowHost,
    LocalWorkflowHostError,
)
from dynamic_agent_runner.workflow_host.runner import RunDarWorkflowError


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Run the narrow v1 DAR package discovery or saved-workflow command."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    if arguments == ["version", "--json"]:
        return _version(stdout=stdout, stderr=stderr)
    if not arguments or arguments[0] != "invoke":
        _write(stderr, _error("usage"))
        return 2
    try:
        invocation = _parse_invoke(arguments[1:])
        prompt = stdin.read()
        if not prompt.strip():
            raise ValueError("prompt is required")
        if invocation.dry_run and invocation.workspace_files:
            raise ValueError("dry run cannot accept workspace files")
    except ValueError:
        _write(stderr, _error("usage"))
        return 2
    try:
        result = LocalWorkflowHost.open(_default_state_root()).invoke_saved(
            package_name=invocation.package_name,
            prompt=prompt,
            workspace_files=invocation.workspace_files,
            dry_run=invocation.dry_run,
            approval_broker=TerminalApprovalBroker() if invocation.ask else None,
            now=datetime.now(UTC),
        )
    except RunDarWorkflowError:
        _write(stderr, _invoke_error("failed"))
        return 1
    except (LocalWorkflowHostError, ValueError):
        _write(stderr, _invoke_error("capability_unavailable"))
        return 1
    except Exception:  # noqa: BLE001 - receipt intentionally hides host details.
        _write(stderr, _error("internal"))
        return 1
    if invocation.dry_run:
        _write(
            stdout,
            {
                "configuration": {
                    "package_id": result.package_id,
                    "profile_id": result.profile_id,
                    "registration_digest": result.registration_digest,
                    "revision_digest": result.revision_digest,
                    "workflow_id": result.workflow_id,
                },
                "format_version": 1,
                "mode": "dry_run",
                "status": "completed",
            },
        )
        return 0
    _write(
        stdout,
        {
            "format_version": 1,
            "output": result.output,
            "run_id": result.run_id,
            "status": result.status,
            "workflow_id": invocation.package_name,
        },
    )
    return 0


def _version(*, stdout: TextIO, stderr: TextIO) -> int:
    try:
        distribution_version = _distribution_version()
    except Exception:  # noqa: BLE001 - receipt intentionally hides host details.
        _write(stderr, _error("internal"))
        return 1
    _write(
        stdout,
        {
            "format_version": 1,
            "status": "ok",
            "distribution": "dynamic-agent-runner",
            "version": distribution_version,
        },
    )
    return 0


@dataclass(frozen=True)
class _InvokeArguments:
    package_name: str
    workspace_files: tuple[Path, ...]
    dry_run: bool
    ask: bool


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(message)


def _parse_invoke(arguments: Sequence[str]) -> _InvokeArguments:
    parser = _ArgumentParser(add_help=False)
    parser.add_argument("--package-name", required=True)
    parser.add_argument("--prompt-stdin", action="store_true")
    parser.add_argument("--workspace-file", action="append", default=[], type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--ask", action="store_true")
    args = parser.parse_args(arguments)
    if not args.prompt_stdin or not args.package_name:
        raise ValueError("invoke requires a saved package and stdin prompt")
    return _InvokeArguments(
        package_name=args.package_name,
        workspace_files=tuple(args.workspace_file),
        dry_run=args.dry_run,
        ask=args.ask,
    )


def _default_state_root() -> Path:
    configured = os.environ.get("DAR_AUTHORING_STATE_ROOT")
    if configured:
        return Path(configured)
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "dar-authoring"
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / (
        "dar-authoring"
    )


def _distribution_version() -> str:
    return version("dynamic-agent-runner")


def _error(error_code: str) -> dict[str, object]:
    return {"format_version": 1, "status": "error", "error_code": error_code}


def _invoke_error(status: str) -> dict[str, object]:
    return {"format_version": 1, "status": status, "error_code": status}


def _write(stream: TextIO, value: dict[str, object]) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":")), file=stream)


def console_main() -> None:
    """Console-script entry point."""

    raise SystemExit(main())
