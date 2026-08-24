"""Tests for the DAR authoring local workflow CLI façade."""

from __future__ import annotations

import json
import shutil
import sys
import base64
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


PLUGIN_SERVER_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "server"
sys.path.insert(0, str(PLUGIN_SERVER_ROOT))

from dar_workflow_server import cli  # noqa: E402
from dar_workflow_server.cli import main, run_main  # noqa: E402


TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "templates"


def _invoke(args: list[str]) -> tuple[int, dict[str, object]]:
    output: list[str] = []
    result = main(args, write=output.append)
    return result, json.loads(output[0])


def test_cli_manages_human_trusted_publisher_keys(tmp_path: Path) -> None:
    state_args = ["--state-root", str(tmp_path / "state")]
    key_id = "publisher.example.v1"
    public_key = base64.b64encode(
        Ed25519PrivateKey.generate().public_key().public_bytes_raw()
    ).decode("ascii")

    status, added = _invoke(
        [
            *state_args,
            "trust-publisher",
            "--key-id",
            key_id,
            "--public-key-base64",
            public_key,
        ]
    )
    assert status == 0
    assert added["key_id"] == key_id
    status, listed = _invoke([*state_args, "list-trusted-publishers"])
    assert status == 0
    assert listed["publishers"][0]["key_id"] == key_id
    status, revoked = _invoke(
        [*state_args, "revoke-trusted-publisher", "--key-id", key_id]
    )
    assert status == 0
    assert revoked == {"key_id": key_id, "status": "revoked"}


def test_cli_configures_selects_registers_prepares_and_dry_runs(tmp_path: Path) -> None:
    root = tmp_path / "state"
    package_root = tmp_path / "packages"
    source = package_root / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
    state_args = ["--state-root", str(root)]

    status, configured = _invoke(
        [
            *state_args,
            "configure-local-model",
            "--package-root",
            str(package_root),
            "--model-id",
            "local-model-v1",
            "--base-url",
            "http://127.0.0.1:11434/v1",
        ]
    )
    assert status == 0
    assert configured["status"] == "configured"

    status, selected = _invoke([*state_args, "select-package", "--path", str(source)])
    assert status == 0
    status, registration = _invoke(
        [
            *state_args,
            "register",
            "--workflow-id",
            "document-helper",
            "--package-source-handle",
            selected["package_source_handle"],
        ]
    )
    assert status == 0
    assert registration["workflow_id"] == "document-helper"

    status, prepared = _invoke(
        [
            *state_args,
            "prepare",
            "--workflow-id",
            "document-helper",
            "--prompt",
            "Answer me.",
        ]
    )
    assert status == 0
    status, result = _invoke(
        [
            *state_args,
            "run",
            "--workflow-id",
            "document-helper",
            "--prepared-input-id",
            prepared["prepared_input_id"],
            "--dry-run",
        ]
    )
    assert status == 0
    assert result == {"status": "ready", "workflow_id": "document-helper"}

    output: list[str] = []
    assert (
        run_main(
            [
                *state_args,
                "--workflow-id",
                "document-helper",
                "--prepared-input-id",
                prepared["prepared_input_id"],
                "--dry-run",
                "--ask",
            ],
            write=output.append,
        )
        == 0
    )


def test_cli_ingresses_a_registered_workspace_file_without_returning_its_path(
    tmp_path: Path,
) -> None:
    root = tmp_path / "state"
    package_root = tmp_path / "packages"
    source = package_root / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
    descriptor = source / "workflow-descriptor.yaml"
    descriptor.write_text(
        descriptor.read_text(encoding="utf-8").replace(
            "allowed_artifact_roles: []", "allowed_artifact_roles: [document]"
        ),
        encoding="utf-8",
    )
    input_root = tmp_path / "input"
    input_root.mkdir()
    document = input_root / "document.txt"
    document.write_text("document body", encoding="utf-8")
    state_args = ["--state-root", str(root)]

    status, _ = _invoke(
        [
            *state_args,
            "configure-local-model",
            "--package-root",
            str(package_root),
            "--workspace-input-root",
            str(input_root),
            "--model-id",
            "local-model-v1",
            "--base-url",
            "http://127.0.0.1:11434/v1",
        ]
    )
    assert status == 0
    status, selected = _invoke([*state_args, "select-package", "--path", str(source)])
    assert status == 0
    status, registration = _invoke(
        [
            *state_args,
            "register",
            "--workflow-id",
            "document-helper",
            "--package-source-handle",
            selected["package_source_handle"],
        ]
    )
    assert status == 0

    status, artifact = _invoke(
        [
            *state_args,
            "ingress-file",
            "--workflow-id",
            registration["workflow_id"],
            "--path",
            str(document),
            "--role",
            "document",
            "--media-type",
            "text/plain",
        ]
    )

    assert status == 0
    assert set(artifact) == {
        "artifact_id",
        "byte_count",
        "content_hash",
        "expires_at",
    }
    assert str(document) not in json.dumps(artifact)
    assert "document body" not in json.dumps(artifact)

    status, prepared = _invoke(
        [
            *state_args,
            "prepare",
            "--workflow-id",
            registration["workflow_id"],
            "--prompt",
            "Answer the request.",
            "--artifact-id",
            artifact["artifact_id"],
        ]
    )

    assert status == 0
    assert str(document) not in json.dumps(prepared)
    assert "document body" not in json.dumps(prepared)


def test_run_cli_passes_ask_as_a_host_only_broker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    class Host:
        def run(self, **kwargs: object) -> SimpleNamespace:
            calls.append(kwargs)
            return SimpleNamespace(
                status="completed", run_id="run-1", output={"message": "done"}
            )

    monkeypatch.setattr(cli.LocalWorkflowHost, "open", lambda root: Host())
    output: list[str] = []

    assert (
        run_main(
            [
                "--state-root",
                "/tmp/dar-authoring-test",
                "--workflow-id",
                "mail-reader",
                "--prepared-input-id",
                "v1.input.signature",
                "--ask",
            ],
            write=output.append,
        )
        == 0
    )

    assert len(calls) == 1
    assert calls[0]["workflow_id"] == "mail-reader"
    assert calls[0]["prepared_input_id"] == "v1.input.signature"
    assert calls[0]["approval_broker"] is not None
    assert output == ['{"message":"done","run_id":"run-1","status":"completed"}']


def test_cli_configures_generic_mcp_connection_without_exposing_api_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def create(**kwargs: object) -> SimpleNamespace:
        calls.append(("create", kwargs))
        return SimpleNamespace(connection_id="v1.connection")

    def configure_token(**kwargs: object) -> SimpleNamespace:
        calls.append(("token", kwargs))
        return SimpleNamespace(authentication_id="v1.authentication")

    def attach(**kwargs: object) -> SimpleNamespace:
        calls.append(("attach", kwargs))
        return SimpleNamespace()

    monkeypatch.setattr(cli, "create_mcp_connection", create)
    monkeypatch.setattr(cli, "configure_mcp_api_token", configure_token)
    monkeypatch.setattr(cli, "attach_mcp_client", attach)
    state_args = ["--state-root", "/tmp/dar-authoring-test"]

    status, connection = _invoke(
        [
            *state_args,
            "create-mcp-connection",
            "--endpoint",
            "https://mcp.example.test/v1",
            "--scope",
            "mail.read",
            "--authentication-method",
            "api_token",
        ]
    )
    assert status == 0
    assert connection == {"connection_id": "v1.connection", "status": "created"}

    output: list[str] = []
    status = main(
        [
            *state_args,
            "configure-mcp-api-token",
            "--connection-id",
            "v1.connection",
            "--token-stdin",
        ],
        write=output.append,
        read_stdin=lambda: "secret-token\n",
    )
    assert status == 0
    assert json.loads(output[0]) == {
        "authentication_id": "v1.authentication",
        "status": "authenticated",
    }
    assert "secret-token" not in output[0]

    status, attached = _invoke(
        [
            *state_args,
            "attach-mcp-client",
            "--connection-id",
            "v1.connection",
            "--authentication-id",
            "v1.authentication",
            "--peer-certificate-sha256",
            "a" * 64,
        ]
    )
    assert status == 0
    assert attached == {"status": "attached"}
    assert calls == [
        (
            "create",
            {
                "root": Path("/tmp/dar-authoring-test"),
                "endpoint": "https://mcp.example.test/v1",
                "scopes": ["mail.read"],
                "authentication_method": "api_token",
            },
        ),
        (
            "token",
            {
                "root": Path("/tmp/dar-authoring-test"),
                "connection_id": "v1.connection",
                "token": "secret-token",
            },
        ),
        (
            "attach",
            {
                "root": Path("/tmp/dar-authoring-test"),
                "connection_id": "v1.connection",
                "authentication_id": "v1.authentication",
                "peer_certificate_sha256": "a" * 64,
                "timeout_seconds": 10,
                "max_response_bytes": 32_768,
            },
        ),
    ]


def test_cli_authorizes_generic_mcp_oauth_through_human_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def authorize(**kwargs: object) -> SimpleNamespace:
        calls.append(kwargs)
        return SimpleNamespace(authentication_id="v1.authentication")

    monkeypatch.setattr(cli, "authorize_mcp_oauth", authorize)
    output: list[str] = []

    assert (
        main(
            [
                "--state-root",
                "/tmp/dar-authoring-test",
                "authorize-mcp-oauth",
                "--connection-id",
                "v1.connection",
                "--authorization-endpoint",
                "https://login.example.test/authorize",
                "--token-endpoint",
                "https://login.example.test/token",
                "--client-id",
                "public-client",
            ],
            write=output.append,
        )
        == 0
    )
    assert json.loads(output[0]) == {
        "authentication_id": "v1.authentication",
        "status": "authenticated",
    }
    assert calls == [
        {
            "root": Path("/tmp/dar-authoring-test"),
            "connection_id": "v1.connection",
            "authorization_endpoint": "https://login.example.test/authorize",
            "token_endpoint": "https://login.example.test/token",
            "client_id": "public-client",
        }
    ]


def test_cli_inspects_reviews_binds_and_registers_mcp_workflows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class Host:
        def discover_mcp_tools(self) -> tuple[SimpleNamespace, ...]:
            return (
                SimpleNamespace(name="list_unread", input_schema={"type": "object"}),
            )

        def review_mcp_surface(self, **kwargs: object) -> SimpleNamespace:
            calls.append(("review", kwargs))
            return SimpleNamespace(snapshot_id="v1.snapshot")

        def bind_mcp_package(self, **kwargs: object) -> SimpleNamespace:
            calls.append(("bind", kwargs))
            return SimpleNamespace(binding_id="v1.binding")

        def register(self, **kwargs: object) -> SimpleNamespace:
            calls.append(("register", kwargs))
            return SimpleNamespace(
                workflow_id="mail-reader",
                registration_digest="a" * 64,
                profile_id="v1.profile",
            )

    monkeypatch.setattr(cli.LocalWorkflowHost, "open", lambda root: Host())
    state_args = ["--state-root", "/tmp/dar-authoring-test"]

    status, tools = _invoke([*state_args, "inspect-mcp-tools"])
    assert status == 0
    assert tools == {
        "tools": [{"input_schema": {"type": "object"}, "name": "list_unread"}]
    }

    status, snapshot = _invoke(
        [
            *state_args,
            "review-mcp-surface",
            "--approve-read-tool",
            "list_unread",
        ]
    )
    assert status == 0
    assert snapshot == {"snapshot_id": "v1.snapshot", "status": "reviewed"}

    status, binding = _invoke(
        [
            *state_args,
            "bind-mcp-package",
            "--package-source-handle",
            "v1.source",
            "--snapshot-id",
            "v1.snapshot",
        ]
    )
    assert status == 0
    assert binding == {"binding_id": "v1.binding", "status": "bound"}

    status, registration = _invoke(
        [
            *state_args,
            "register",
            "--workflow-id",
            "mail-reader",
            "--package-source-handle",
            "v1.source",
            "--mcp-binding-id",
            "v1.binding",
        ]
    )
    assert status == 0
    assert registration["workflow_id"] == "mail-reader"
    assert calls[0] == (
        "review",
        {
            "approved_read_only_tool_names": ["list_unread"],
            "approved_tool_side_effects": {},
        },
    )
    assert calls[1][0] == "bind"
    assert calls[1][1]["package_source_handle"] == "v1.source"
    assert calls[1][1]["snapshot_id"] == "v1.snapshot"
    assert calls[2][0] == "register"
    assert calls[2][1]["mcp_binding_id"] == "v1.binding"
