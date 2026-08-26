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
    if not arguments:
        _write(stderr, _error("usage"))
        return 2
    if arguments[0] == "select-package":
        return _select_package(arguments[1:], stdout=stdout, stderr=stderr)
    if arguments[0] in _AUTHORING_COMMANDS:
        return _authoring(arguments, stdin=stdin, stdout=stdout, stderr=stderr)
    if arguments[0] != "invoke":
        _write(stderr, _error("usage"))
        return 2
    return _invoke(arguments[1:], stdin=stdin, stdout=stdout, stderr=stderr)


def _select_package(arguments: Sequence[str], *, stdout: TextIO, stderr: TextIO) -> int:
    try:
        parser = _ArgumentParser(add_help=False)
        parser.add_argument("--path", required=True, type=Path)
        parser.add_argument("--json", action="store_true")
        args = parser.parse_args(arguments)
        if not args.json:
            raise ValueError("select-package requires --json")
        package_source_handle = LocalWorkflowHost.open(
            _default_state_root()
        ).select_package(args.path, now=datetime.now(UTC))
    except (LocalWorkflowHostError, ValueError):
        _write(stderr, _error("usage"))
        return 2
    except Exception:  # noqa: BLE001 - receipt intentionally hides host details.
        _write(stderr, _error("internal"))
        return 1
    _write(
        stdout,
        {
            "format_version": 1,
            "package_source_handle": package_source_handle,
            "status": "selected",
        },
    )
    return 0


def _invoke(
    arguments: Sequence[str], *, stdin: TextIO, stdout: TextIO, stderr: TextIO
) -> int:
    try:
        invocation = _parse_invoke(arguments)
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


_AUTHORING_COMMANDS = frozenset(
    {
        "project-authoring-materials",
        "create-authored-package",
        "write-authored-package-file",
        "finalize-authored-package",
    }
)


def _authoring(
    arguments: Sequence[str], *, stdin: TextIO, stdout: TextIO, stderr: TextIO
) -> int:
    try:
        args = _parse_authoring(arguments)
        host = LocalWorkflowHost.open(_default_state_root())
        result = _authoring_result(host, args, stdin=stdin)
    except (LocalWorkflowHostError, ValueError):
        _write(stderr, _error("usage"))
        return 2
    except Exception:  # noqa: BLE001 - receipt intentionally hides host details.
        _write(stderr, _error("internal"))
        return 1
    _write(stdout, result)
    return 0


def _parse_authoring(arguments: Sequence[str]) -> argparse.Namespace:
    parser = _ArgumentParser(add_help=False)
    subparsers = parser.add_subparsers(dest="command", required=True)
    project = subparsers.add_parser("project-authoring-materials", add_help=False)
    project.add_argument("--material-set-id", required=True)
    create = subparsers.add_parser("create-authored-package", add_help=False)
    create.add_argument("--package-name", required=True)
    write = subparsers.add_parser("write-authored-package-file", add_help=False)
    write.add_argument("--authoring-output-id", required=True)
    write.add_argument("--relative-path", required=True)
    write.add_argument("--content-stdin", action="store_true")
    finalize = subparsers.add_parser("finalize-authored-package", add_help=False)
    finalize.add_argument("--authoring-output-id", required=True)
    finalize.add_argument("--material-set-id", required=True)
    args = parser.parse_args(arguments)
    if args.command == "write-authored-package-file" and not args.content_stdin:
        raise ValueError("authored package file content must be supplied on stdin")
    return args


def _authoring_result(
    host: LocalWorkflowHost, args: argparse.Namespace, *, stdin: TextIO
) -> dict[str, object]:
    now = datetime.now(UTC)
    if args.command == "project-authoring-materials":
        projection = host.project_authoring_materials(args.material_set_id, now=now)
        return {
            "expires_at": projection.expires_at.isoformat(),
            "format_version": 1,
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
            "status": "projected",
        }
    if args.command == "create-authored-package":
        output = host.create_authored_package(package_name=args.package_name, now=now)
        return {
            "authoring_output_id": output.output_id,
            "expires_at": output.expires_at.isoformat(),
            "format_version": 1,
            "package_name": output.package_name,
            "status": "created",
        }
    if args.command == "write-authored-package-file":
        written = host.write_authored_package_file(
            output_id=args.authoring_output_id,
            relative_path=args.relative_path,
            content=stdin.read(),
            now=now,
        )
        return {
            "byte_count": written.byte_count,
            "content_hash": written.content_hash,
            "format_version": 1,
            "relative_path": written.relative_path,
            "status": "written",
        }
    finalized = host.finalize_authored_output(
        output_id=args.authoring_output_id,
        material_set_id=args.material_set_id,
        now=now,
    )
    return {
        "descriptor_digest": finalized.descriptor_digest,
        "file_count": finalized.file_count,
        "format_version": 1,
        "package_digest": finalized.package_digest,
        "package_id": finalized.package_id,
        "status": "finalized",
    }


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
