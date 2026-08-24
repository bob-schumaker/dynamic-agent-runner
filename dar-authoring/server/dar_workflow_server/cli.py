"""Local control-plane and sealed-run CLI façades for DAR authoring."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dar_workflow_server.action_ledger import ExternalAction
from dar_workflow_server.approvals import WorkflowApproval
from dar_workflow_server.authorized_tools import LocalApprovalDecision
from dar_workflow_server.host import (
    LocalWorkflowHost,
    LocalWorkflowHostError,
    attach_mcp_client,
    authorize_mcp_oauth,
    configure_mcp_api_token,
    configure_local_host,
    create_mcp_connection,
    revoke_package_publisher,
    trust_package_publisher,
    trusted_package_publishers,
)


def main(
    argv: Sequence[str] | None = None,
    *,
    write: Callable[[str], None] = print,
    read_stdin: Callable[[], str] | None = None,
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
        publisher_result = _publisher_control_result(args, root=root)
        if publisher_result is not None:
            _write(write, publisher_result)
            return 0
        control_result = _mcp_control_result(args, root=root, read_stdin=read_stdin)
        if control_result is not None:
            _write(write, control_result)
            return 0
        host = LocalWorkflowHost.open(root)
        now = datetime.now(UTC)
        mcp_result = _mcp_workflow_result(host, args, now=now)
        if mcp_result is not None:
            _write(write, mcp_result)
            return 0
        package_result = _package_control_result(
            host, args, now=now, read_stdin=read_stdin
        )
        if package_result is not None:
            _write(write, package_result)
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
    connection = commands.add_parser("create-mcp-connection")
    connection.add_argument("--endpoint", required=True)
    connection.add_argument("--scope", action="append", required=True)
    connection.add_argument(
        "--authentication-method",
        required=True,
        choices=("api_token", "oauth_authorization_code_pkce_loopback"),
    )
    token = commands.add_parser("configure-mcp-api-token")
    token.add_argument("--connection-id", required=True)
    token.add_argument("--token-stdin", action="store_true")
    oauth = commands.add_parser("authorize-mcp-oauth")
    oauth.add_argument("--connection-id", required=True)
    oauth.add_argument("--authorization-endpoint", required=True)
    oauth.add_argument("--token-endpoint", required=True)
    oauth.add_argument("--client-id", required=True)
    attach = commands.add_parser("attach-mcp-client")
    attach.add_argument("--connection-id", required=True)
    attach.add_argument("--authentication-id", required=True)
    attach.add_argument("--peer-certificate-sha256", required=True)
    attach.add_argument("--timeout-seconds", type=int, default=10)
    attach.add_argument("--max-response-bytes", type=int, default=32_768)
    trust_publisher = commands.add_parser("trust-publisher")
    trust_publisher.add_argument("--key-id", required=True)
    trust_publisher.add_argument("--public-key-base64", required=True)
    commands.add_parser("list-trusted-publishers")
    revoke_publisher = commands.add_parser("revoke-trusted-publisher")
    revoke_publisher.add_argument("--key-id", required=True)
    commands.add_parser("inspect-mcp-tools")
    review = commands.add_parser("review-mcp-surface")
    review.add_argument("--approve-read-tool", action="append", default=[])
    review.add_argument("--approve-tool", action="append", default=[])
    bind = commands.add_parser("bind-mcp-package")
    bind.add_argument("--package-source-handle", required=True)
    bind.add_argument("--snapshot-id", required=True)
    select = commands.add_parser("select-package")
    select.add_argument("--path", required=True)
    select.add_argument("--publisher-signed", action="store_true")
    export = commands.add_parser("export-signed-package")
    export.add_argument("--package-source-handle", required=True)
    export.add_argument("--destination", required=True)
    export.add_argument("--key-id", required=True)
    export.add_argument("--expected-content-digest", required=True)
    export.add_argument("--private-key-stdin", action="store_true")
    preview = commands.add_parser("preview-package")
    preview.add_argument("--package-source-handle", required=True)
    register = commands.add_parser("register")
    register.add_argument("--workflow-id", required=True)
    register.add_argument("--package-source-handle", required=True)
    register.add_argument("--mcp-binding-id")
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


def _mcp_control_result(
    args: Any,
    *,
    root: Path,
    read_stdin: Callable[[], str] | None,
) -> dict[str, object] | None:
    if args.command == "create-mcp-connection":
        connection = create_mcp_connection(
            root=root,
            endpoint=args.endpoint,
            scopes=args.scope,
            authentication_method=args.authentication_method,
        )
        return {"status": "created", "connection_id": connection.connection_id}
    if args.command == "configure-mcp-api-token":
        if not args.token_stdin:
            raise LocalWorkflowHostError("API token must be supplied on stdin")
        authentication = configure_mcp_api_token(
            root=root,
            connection_id=args.connection_id,
            token=(read_stdin or sys.stdin.read)().strip(),
        )
        return {
            "status": "authenticated",
            "authentication_id": authentication.authentication_id,
        }
    if args.command == "authorize-mcp-oauth":
        authentication = authorize_mcp_oauth(
            root=root,
            connection_id=args.connection_id,
            authorization_endpoint=args.authorization_endpoint,
            token_endpoint=args.token_endpoint,
            client_id=args.client_id,
        )
        return {
            "status": "authenticated",
            "authentication_id": authentication.authentication_id,
        }
    if args.command == "attach-mcp-client":
        attach_mcp_client(
            root=root,
            connection_id=args.connection_id,
            authentication_id=args.authentication_id,
            peer_certificate_sha256=args.peer_certificate_sha256,
            timeout_seconds=args.timeout_seconds,
            max_response_bytes=args.max_response_bytes,
        )
        return {"status": "attached"}
    return None


def _publisher_control_result(args: Any, *, root: Path) -> dict[str, object] | None:
    if args.command == "trust-publisher":
        try:
            public_key = base64.b64decode(
                args.public_key_base64.encode("ascii"), validate=True
            )
        except (UnicodeEncodeError, ValueError) as error:
            raise LocalWorkflowHostError("publisher public key is invalid") from error
        publisher = trust_package_publisher(
            root=root, key_id=args.key_id, public_key=public_key
        )
        return {
            "key_id": publisher.key_id,
            "public_key_sha256": publisher.public_key_sha256,
            "status": "trusted",
        }
    if args.command == "list-trusted-publishers":
        return {
            "publishers": [
                {
                    "key_id": publisher.key_id,
                    "public_key_sha256": publisher.public_key_sha256,
                }
                for publisher in trusted_package_publishers(root=root)
            ]
        }
    if args.command == "revoke-trusted-publisher":
        revoke_package_publisher(root=root, key_id=args.key_id)
        return {"key_id": args.key_id, "status": "revoked"}
    return None


def _mcp_workflow_result(
    host: LocalWorkflowHost, args: Any, *, now: datetime
) -> dict[str, object] | None:
    if args.command == "inspect-mcp-tools":
        return {
            "tools": [
                {"name": tool.name, "input_schema": dict(tool.input_schema)}
                for tool in host.discover_mcp_tools()
            ]
        }
    if args.command == "review-mcp-surface":
        snapshot = host.review_mcp_surface(
            approved_read_only_tool_names=args.approve_read_tool,
            approved_tool_side_effects=_approved_tool_effects(args.approve_tool),
        )
        return {"status": "reviewed", "snapshot_id": snapshot.snapshot_id}
    if args.command == "bind-mcp-package":
        binding = host.bind_mcp_package(
            package_source_handle=args.package_source_handle,
            snapshot_id=args.snapshot_id,
            now=now,
        )
        return {"status": "bound", "binding_id": binding.binding_id}
    return None


def _package_control_result(
    host: LocalWorkflowHost,
    args: Any,
    *,
    now: datetime,
    read_stdin: Callable[[], str] | None,
) -> dict[str, object] | None:
    if args.command == "select-package":
        select = (
            host.select_publisher_package
            if args.publisher_signed
            else host.select_package
        )
        return {"package_source_handle": select(Path(args.path), now=now)}
    if args.command == "export-signed-package":
        previewed = host.preview_package(
            package_source_handle=args.package_source_handle, now=now
        )
        if args.expected_content_digest != previewed.digest:
            raise LocalWorkflowHostError("package content digest was not confirmed")
        if not args.private_key_stdin:
            raise LocalWorkflowHostError(
                "package signing key must be supplied on stdin"
            )
        try:
            private_key = base64.b64decode(
                (read_stdin or sys.stdin.read)().strip().encode("ascii"),
                validate=True,
            )
        except (UnicodeEncodeError, ValueError) as error:
            raise LocalWorkflowHostError("package signing key is invalid") from error
        exported = host.export_signed_package(
            package_source_handle=args.package_source_handle,
            destination=Path(args.destination),
            key_id=args.key_id,
            private_key=private_key,
            expected_content_digest=args.expected_content_digest,
            now=now,
        )
        return {
            "byte_count": exported.byte_count,
            "content_digest": exported.content_digest,
            "publisher_key_id": exported.publisher_key_id,
            "status": "exported",
        }
    if args.command == "preview-package":
        staged = host.preview_package(
            package_source_handle=args.package_source_handle, now=now
        )
        return {
            "byte_count": staged.byte_count,
            "content_digest": staged.digest,
            "file_count": staged.file_count,
            "status": "previewed",
        }
    if args.command == "register":
        registration = host.register(
            workflow_id=args.workflow_id,
            package_source_handle=args.package_source_handle,
            now=now,
            mcp_binding_id=args.mcp_binding_id,
        )
        return {
            "workflow_id": registration.workflow_id,
            "registration_digest": registration.registration_digest,
            "profile_id": registration.profile_id,
        }
    if args.command == "ingress-file":
        artifact = host.ingress_file(
            workflow_id=args.workflow_id,
            path=Path(args.path),
            role=args.role,
            media_type=args.media_type,
            now=now,
        )
        return {
            "artifact_id": artifact.artifact_id,
            "content_hash": artifact.content_hash,
            "byte_count": artifact.byte_count,
            "expires_at": artifact.expires_at.isoformat(),
        }
    if args.command == "prepare":
        prepared = host.prepare(
            workflow_id=args.workflow_id,
            prompt=args.prompt,
            workspace_artifact_ids=args.artifact_id,
            now=now,
        )
        return {
            "prepared_input_id": prepared.prepared_input_id,
            "workflow_id": prepared.workflow_id,
            "expires_at": prepared.expires_at.isoformat(),
        }
    return None


def _approved_tool_effects(values: Sequence[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        name, separator, effect = value.partition("=")
        if (
            not separator
            or not name
            or effect not in {"read", "write", "delete"}
            or name in result
        ):
            raise LocalWorkflowHostError(
                "approved MCP tool must use name=read|write|delete"
            )
        result[name] = effect
    return result


def _run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workflow-id", required=True)
    parser.add_argument("--prepared-input-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--ask", action="store_true")


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
        approval_broker=_TerminalApprovalBroker() if args.ask else None,
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


class _TerminalApprovalBroker:
    """Prompt the local terminal user for one normalized external action."""

    def decide(
        self, *, action: ExternalAction, approval: WorkflowApproval
    ) -> LocalApprovalDecision:
        del approval
        prompt = json.dumps(
            {
                "arguments": action.normalized_arguments,
                "side_effect": action.side_effect,
                "tool": action.remote_tool_name,
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        try:
            answer = input(f"Approve external action {prompt}? [y/N] ")
        except (EOFError, KeyboardInterrupt):
            return LocalApprovalDecision.CANCELLED
        return (
            LocalApprovalDecision.APPROVED
            if answer.strip().lower() in {"y", "yes"}
            else LocalApprovalDecision.DENIED
        )


def console_main() -> None:
    """Console script for the local workflow control plane."""

    raise SystemExit(main())


def run_console_main() -> None:
    """Console script for sealed workflow execution only."""

    raise SystemExit(run_main())
