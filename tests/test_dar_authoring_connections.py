"""Tests for human-owned generic HTTPS MCP connection records."""

from __future__ import annotations

from pathlib import Path

import pytest


from dynamic_agent_runner.workflow_host.connections import (  # noqa: E402
    MCPConnectionControlPlane,
    MCPConnectionError,
)
from dynamic_agent_runner.workflow_host.profiles import LocalModelProfileControlPlane  # noqa: E402
from dynamic_agent_runner.workflow_host.state import PrivateStateStore  # noqa: E402


class MemorySecretStore:
    """Test double that keeps secret bytes outside the opaque state store."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def store(self, secret: str) -> str:
        reference = f"mcp-secret-v1-{len(self.values) + 1}"
        self.values[reference] = secret
        return reference

    def load(self, reference: str) -> str:
        return self.values[reference]

    def delete(self, reference: str) -> None:
        self.values.pop(reference, None)


def test_human_connection_record_is_immutable_and_has_no_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.profiles.getpass.getuser", lambda: "ada"
    )
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.profiles.os.getuid", lambda: 501
    )
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


def test_human_api_token_setup_uses_only_an_opaque_secret_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.profiles.getpass.getuser", lambda: "ada"
    )
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.profiles.os.getuid", lambda: 501
    )
    store = PrivateStateStore(tmp_path / "state")
    profiles = LocalModelProfileControlPlane(store=store)
    profile = profiles.create(
        model_id="local-model-v1",
        adapter_id="strict-local-adapter-v1",
        base_url="http://127.0.0.1:11434/v1",
        capabilities={"text_generation"},
    )
    secrets = MemorySecretStore()
    control = MCPConnectionControlPlane(
        store=store,
        profiles=profiles,
        secret_store=secrets,
    )
    connection = control.create(
        profile_id=profile.profile_id,
        endpoint="https://mcp.example.test/v1",
        scopes={"mail.read"},
        authentication_method="api_token",
    )

    authentication = control.configure_api_token(
        connection.connection_id, "token-not-in-state"
    )

    assert authentication.connection_id == connection.connection_id
    assert authentication.authentication_status == "authenticated"
    assert authentication.credential_ref == "mcp-secret-v1-1"
    assert secrets.values == {"mcp-secret-v1-1": "token-not-in-state"}
    assert (
        control.preflight(
            connection.connection_id,
            authentication_id=authentication.authentication_id,
        ).status
        == "authenticated"
    )
    assert "token-not-in-state" not in (tmp_path / "state" / "records.json").read_text()
    assert "token-not-in-state" not in repr(authentication)


def test_api_token_authentication_cannot_bind_a_different_connection(
    tmp_path: Path,
) -> None:
    store = PrivateStateStore(tmp_path / "state")
    profiles = LocalModelProfileControlPlane(store=store)
    profile = profiles.create(
        model_id="local-model-v1",
        adapter_id="strict-local-adapter-v1",
        base_url="http://127.0.0.1:11434/v1",
        capabilities={"text_generation"},
    )
    control = MCPConnectionControlPlane(
        store=store,
        profiles=profiles,
        secret_store=MemorySecretStore(),
    )
    first = control.create(
        profile_id=profile.profile_id,
        endpoint="https://first.example.test/v1",
        scopes={"mail.read"},
        authentication_method="api_token",
    )
    second = control.create(
        profile_id=profile.profile_id,
        endpoint="https://second.example.test/v1",
        scopes={"mail.read"},
        authentication_method="api_token",
    )
    authentication = control.configure_api_token(first.connection_id, "token")

    with pytest.raises(MCPConnectionError, match="authentication record"):
        control.preflight(
            second.connection_id,
            authentication_id=authentication.authentication_id,
        )


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
