"""Tests for human-owned generic HTTPS MCP connection records."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


PLUGIN_SERVER_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "server"
sys.path.insert(0, str(PLUGIN_SERVER_ROOT))

from dar_workflow_server.connections import (  # noqa: E402
    MCPConnectionControlPlane,
    MCPConnectionError,
)
from dar_workflow_server.profiles import LocalModelProfileControlPlane  # noqa: E402
from dar_workflow_server.state import PrivateStateStore  # noqa: E402


def test_human_connection_record_is_immutable_and_has_no_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("dar_workflow_server.profiles.getpass.getuser", lambda: "ada")
    monkeypatch.setattr("dar_workflow_server.profiles.os.getuid", lambda: 501)
    store = PrivateStateStore(tmp_path / "state")
    profiles = LocalModelProfileControlPlane(store=store)
    profile = profiles.create(
        model_id="local-model-v1",
        adapter_id="strict-local-adapter-v1",
        base_url="http://127.0.0.1:11434/v1",
        capabilities={"text_generation"},
    )
    control = MCPConnectionControlPlane(store=store, profiles=profiles)

    created = control.create(
        profile_id=profile.profile_id,
        endpoint="https://mcp.example.test/v1",
        scopes={"mail.read"},
        authentication_method="oauth_authorization_code_pkce_loopback",
    )
    loaded = control.load(created.connection_id)

    assert loaded == created
    assert loaded.transport == "https_mcp_v1"
    assert loaded.authentication_status == "authentication_required"
    assert "credential" not in repr(loaded).lower()
    assert control.preflight(created.connection_id).status == "authentication_required"


@pytest.mark.parametrize(
    ("endpoint", "authentication_method"),
    [
        ("http://mcp.example.test/v1", "api_token"),
        ("https://mcp.example.test/v1?token=secret", "api_token"),
        ("https://mcp.example.test/v1", "unsupported"),
    ],
)
def test_connection_rejects_non_https_or_unsupported_auth(
    tmp_path: Path,
    endpoint: str,
    authentication_method: str,
) -> None:
    store = PrivateStateStore(tmp_path / "state")
    profiles = LocalModelProfileControlPlane(store=store)
    profile = profiles.create(
        model_id="local-model-v1",
        adapter_id="strict-local-adapter-v1",
        base_url="http://127.0.0.1:11434/v1",
        capabilities={"text_generation"},
    )
    control = MCPConnectionControlPlane(store=store, profiles=profiles)

    with pytest.raises(MCPConnectionError):
        control.create(
            profile_id=profile.profile_id,
            endpoint=endpoint,
            scopes={"mail.read"},
            authentication_method=authentication_method,
        )


def test_connection_rejects_scalar_scope_string(tmp_path: Path) -> None:
    store = PrivateStateStore(tmp_path / "state")
    profiles = LocalModelProfileControlPlane(store=store)
    profile = profiles.create(
        model_id="local-model-v1",
        adapter_id="strict-local-adapter-v1",
        base_url="http://127.0.0.1:11434/v1",
        capabilities={"text_generation"},
    )
    control = MCPConnectionControlPlane(store=store, profiles=profiles)

    with pytest.raises(MCPConnectionError, match="scopes"):
        control.create(
            profile_id=profile.profile_id,
            endpoint="https://mcp.example.test/v1",
            scopes="mail.read",  # type: ignore[arg-type]
            authentication_method="api_token",
        )
