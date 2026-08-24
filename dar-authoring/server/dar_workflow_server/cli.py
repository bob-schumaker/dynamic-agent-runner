"""Local control-plane and sealed-run CLI façades for DAR authoring."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dar_workflow_server.host import (
    LocalWorkflowHost,
    LocalWorkflowHostError,
    configure_local_host,
)


def main(
    argv: Sequence[str] | None = None,
    *,
    write: Callable[[str], None] = print,
) -> int:
    """Run local setup, package selection, preparation, or sealed execution."""

    parser = _parser()
    args = parser.parse_args(argv)
    root = Path(args.state_root)
    try:
        if args.command == "configure-local-model":
            configured = configure_local_host(
                root=root,
                package_root=Path(args.package_root),
                workspace_input_root=(
                    Path(args.workspace_input_root)
                    if args.workspace_input_root is not None
                    else None
                ),
                workspace_input_max_bytes=args.workspace_input_max_bytes,
                model_id=args.model_id,
                base_url=args.base_url,
            )
            _write(
                write,
                {"status": "configured", "profile_id": configured.profile_id},
            )
            return 0
        host = LocalWorkflowHost.open(root)
        now = datetime.now(UTC)
        if args.command == "select-package":
            _write(
                write,
                {
                    "package_source_handle": host.select_package(
                        Path(args.path), now=now
                    )
                },
            )
            return 0
        if args.command == "register":
            registration = host.register(
                workflow_id=args.workflow_id,
                package_source_handle=args.package_source_handle,
                now=now,
            )
            _write(
                write,
                {
                    "workflow_id": registration.workflow_id,
                    "registration_digest": registration.registration_digest,
                    "profile_id": registration.profile_id,
                },
            )
            return 0
        if args.command == "ingress-file":
            artifact = host.ingress_file(
                workflow_id=args.workflow_id,
                path=Path(args.path),
                role=args.role,
                media_type=args.media_type,
                now=now,
            )
            _write(
                write,
                {
                    "artifact_id": artifact.artifact_id,
                    "content_hash": artifact.content_hash,
                    "byte_count": artifact.byte_count,
                    "expires_at": artifact.expires_at.isoformat(),
                },
            )
            return 0
        if args.command == "prepare":
            prepared = host.prepare(
                workflow_id=args.workflow_id,
                prompt=args.prompt,
                workspace_artifact_ids=args.artifact_id,
                now=now,
            )
            _write(
                write,
                {
                    "prepared_input_id": prepared.prepared_input_id,
                    "workflow_id": prepared.workflow_id,
                    "expires_at": prepared.expires_at.isoformat(),
                },
            )
            return 0
        return _run(host, args, now=now, write=write)
    except (LocalWorkflowHostError, ValueError) as error:
        print(f"dar-workflow: {error}", file=sys.stderr)
        return 2


def run_main(
    argv: Sequence[str] | None = None,
    *,
    write: Callable[[str], None] = print,
) -> int:
    """Run the dedicated sealed-workflow execution command."""

    parser = argparse.ArgumentParser(prog="dar-workflow-run")
    _state_root_argument(parser)
    _run_arguments(parser)
    args = parser.parse_args(argv)
    try:
        return _run(
            LocalWorkflowHost.open(Path(args.state_root)),
            args,
            now=datetime.now(UTC),
            write=write,
        )
    except (LocalWorkflowHostError, ValueError) as error:
        print(f"dar-workflow-run: {error}", file=sys.stderr)
        return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dar-workflow")
    _state_root_argument(parser)
    commands = parser.add_subparsers(dest="command", required=True)
    configure = commands.add_parser("configure-local-model")
    configure.add_argument("--package-root", required=True)
    configure.add_argument("--workspace-input-root")
    configure.add_argument(
        "--workspace-input-max-bytes", type=int, default=8 * 1024 * 1024
    )
    configure.add_argument("--model-id", required=True)
    configure.add_argument("--base-url", required=True)
    select = commands.add_parser("select-package")
    select.add_argument("--path", required=True)
    register = commands.add_parser("register")
    register.add_argument("--workflow-id", required=True)
    register.add_argument("--package-source-handle", required=True)
    ingress = commands.add_parser("ingress-file")
    ingress.add_argument("--workflow-id", required=True)
    ingress.add_argument("--path", required=True)
    ingress.add_argument("--role", required=True)
    ingress.add_argument("--media-type", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--workflow-id", required=True)
    prepare.add_argument("--prompt", required=True)
    prepare.add_argument("--artifact-id", action="append", default=[])
    run = commands.add_parser("run")
    _run_arguments(run)
    return parser


def _state_root_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state-root", default=str(_default_state_root()))


def _run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workflow-id", required=True)
    parser.add_argument("--prepared-input-id", required=True)
    parser.add_argument("--dry-run", action="store_true")


def _run(
    host: LocalWorkflowHost,
    args: Any,
    *,
    now: datetime,
    write: Callable[[str], None],
) -> int:
    if args.dry_run:
        result = host.dry_run(
            workflow_id=args.workflow_id,
            prepared_input_id=args.prepared_input_id,
            now=now,
        )
        _write(write, {"status": result.status, "workflow_id": result.workflow_id})
        return 0
    result = host.run(
        workflow_id=args.workflow_id,
        prepared_input_id=args.prepared_input_id,
        now=now,
    )
    _write(write, {"status": result.status, "run_id": result.run_id, **result.output})
    return 0


def _default_state_root() -> Path:
    configured = os.environ.get("DAR_AUTHORING_STATE_ROOT")
    if configured:
        return Path(configured)
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "dar-authoring"
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / (
        "dar-authoring"
    )


def _write(write: Callable[[str], None], value: dict[str, object]) -> None:
    write(json.dumps(value, sort_keys=True, separators=(",", ":")))


def console_main() -> None:
    """Console script for the local workflow control plane."""

    raise SystemExit(main())


def run_console_main() -> None:
    """Console script for sealed workflow execution only."""

    raise SystemExit(run_main())
