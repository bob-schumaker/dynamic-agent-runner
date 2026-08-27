"""Focused fake-only tests for human-only discovered MCP OAuth setup."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import hashlib

import pytest

from dynamic_agent_runner.workflow_host.connections import MCPConnectionControlPlane
from dynamic_agent_runner.workflow_host.host import (
    DiscoveredOAuthAuthorizationResult,
    DiscoveredOAuthSetupPreview,
    DiscoveredOAuthSetupError,
    authorize_discovered_mcp_oauth,
    configure_local_host,
)
from dynamic_agent_runner.workflow_host.oauth_discovery import OAuthMetadataHTTPResponse
from dynamic_agent_runner.workflow_host.profiles import (
    InstallationIdentityProvider,
    LocalModelProfileControlPlane,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore


@dataclass
class FakeOAuthHTTPTransport:
    responses: dict[str, list[OAuthMetadataHTTPResponse]]
    registration_response: OAuthMetadataHTTPResponse

    def __post_init__(self) -> None:
        self.get_calls: list[str] = []
        self.registration_requests: list[dict[str, object]] = []

    def get(self, url: str, *, max_response_bytes: int) -> OAuthMetadataHTTPResponse:
        self.get_calls.append(url)
        return self.responses[url].pop(0)

    def post_json(
        self, url: str, *, payload: dict[str, object], max_response_bytes: int
    ) -> OAuthMetadataHTTPResponse:
        assert url == "https://auth.example.test/register"
        self.registration_requests.append(payload)
        return self.registration_response


class FakeAuthorizationService:
    calls = []

    def __init__(self, *, connections: object) -> None:
        self.connections = connections

    def authorize(self, connection_id: str, *, configuration: object) -> object:
        self.calls.append((connection_id, configuration))
        return type("Authentication", (), {"authentication_id": "v1.auth.signature"})()


def _response(*, status: int, body: bytes = b"", headers: dict[str, str] | None = None):
    return OAuthMetadataHTTPResponse(status=status, headers=headers or {}, body=body)


def _transport(*, changed_metadata: bool = False) -> FakeOAuthHTTPTransport:
    endpoint = "https://mcp.example.test/mcp"
    resource_metadata = (
        "https://mcp.example.test/.well-known/oauth-protected-resource/mcp"
    )
    authorization_metadata = (
        "https://auth.example.test/.well-known/oauth-authorization-server/tenant"
    )
    protected = (
        b'{"resource":"https://mcp.example.test/mcp",'
        b'"authorization_servers":["https://auth.example.test/tenant"],'
        b'"scopes_supported":["mail.read"]}'
    )
    changed_protected = (
        b'{"resource":"https://mcp.example.test/mcp",'
        b'"authorization_servers":["https://other.example.test/tenant"],'
        b'"scopes_supported":["mail.read"]}'
    )
    authorization = (
        b'{"issuer":"https://auth.example.test/tenant",'
        b'"authorization_endpoint":"https://auth.example.test/authorize",'
        b'"token_endpoint":"https://auth.example.test/token",'
        b'"registration_endpoint":"https://auth.example.test/register",'
        b'"token_endpoint_auth_methods_supported":["none"],'
        b'"code_challenge_methods_supported":["S256"],'
        b'"response_types_supported":["code"],'
        b'"grant_types_supported":["authorization_code","refresh_token"]}'
    )
    redirect = (
        "http://localhost/oauth/callback/"
        + hashlib.sha256(
            (
                f"{InstallationIdentityProvider().principal}\0"
                "https://auth.example.test/tenant"
            ).encode()
        ).hexdigest()[:24]
    )
    return FakeOAuthHTTPTransport(
        {
            endpoint: [
                _response(
                    status=401,
                    headers={
                        "WWW-Authenticate": f'Bearer resource_metadata="{resource_metadata}"'
                    },
                ),
                _response(
                    status=401,
                    headers={
                        "WWW-Authenticate": f'Bearer resource_metadata="{resource_metadata}"'
                    },
                ),
            ],
            resource_metadata: [
                _response(status=200, body=protected),
                _response(
                    status=200,
                    body=changed_protected if changed_metadata else protected,
                ),
            ],
            authorization_metadata: [
                _response(status=200, body=authorization),
                _response(status=200, body=authorization),
            ],
        },
        _response(
            status=201,
            body=(
                b'{"client_id":"registered-client",'
                b'"token_endpoint_auth_method":"none",'
                + f'"redirect_uris":["{redirect}"]}}'.encode()
            ),
        ),
    )


def _connection_id(tmp_path) -> str:
    root = tmp_path / "state"
    package_root = tmp_path / "packages"
    package_root.mkdir()
    configuration = configure_local_host(
        root=root,
        package_root=package_root,
        model_id="local-test-model",
        base_url="http://127.0.0.1:11434/v1",
    )
    store = PrivateStateStore(root)
    connections = MCPConnectionControlPlane(
        store=store, profiles=LocalModelProfileControlPlane(store=store)
    )
    return connections.create(
        profile_id=configuration.profile_id,
        endpoint="https://mcp.example.test/mcp",
        scopes={"mail.read"},
        authentication_method="oauth_authorization_code_pkce_loopback",
    ).connection_id


def test_discovered_setup_revalidates_before_browser_authorization(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = _transport()
    FakeAuthorizationService.calls = []
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.host.UrllibOAuthMetadataHTTPTransport",
        lambda: transport,
    )
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.host.OAuthAuthorizationService",
        FakeAuthorizationService,
    )

    connection_id = _connection_id(tmp_path)
    result = authorize_discovered_mcp_oauth(
        root=tmp_path / "state",
        connection_id=connection_id,
        persistent_reconnect=False,
    )

    assert result.authentication_id == "v1.auth.signature"
    assert result.registration_id.startswith("v1.")
    assert len(FakeAuthorizationService.calls) == 1
    configuration = FakeAuthorizationService.calls[0][1]
    assert configuration.resource == "https://mcp.example.test/mcp"
    assert configuration.issuer == "https://auth.example.test/tenant"
    records = PrivateStateStore(tmp_path / "state").active_records(
        kind="mcp_oauth_discovery",
        owner=InstallationIdentityProvider().principal,
        now=datetime.now(UTC),
    )
    assert len(records) == 1
    assert records[0][1].payload["connection_id"] == connection_id
    assert set(records[0][1].payload) == {
        "connection_id",
        "protected_resource_digest",
        "authorization_server_digest",
        "scope_digest",
    }


def test_discovered_setup_returns_no_metadata_or_registration_material(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = _transport()
    FakeAuthorizationService.calls = []
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.host.UrllibOAuthMetadataHTTPTransport",
        lambda: transport,
    )
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.host.OAuthAuthorizationService",
        FakeAuthorizationService,
    )

    result = authorize_discovered_mcp_oauth(
        root=tmp_path / "state",
        connection_id=_connection_id(tmp_path),
        persistent_reconnect=False,
    )

    public_result = json.dumps(result.__dict__, sort_keys=True)
    forbidden = {
        "https://mcp.example.test/mcp",
        "https://auth.example.test/authorize",
        "https://auth.example.test/token",
        "https://auth.example.test/register",
        "registered-client",
        "mail.read",
    }
    assert not any(value in public_result for value in forbidden)
    assert set(result.__dict__) == {"authentication_id", "registration_id"}


def test_discovered_setup_stops_before_browser_when_metadata_drifts(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = _transport(changed_metadata=True)
    FakeAuthorizationService.calls = []
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.host.UrllibOAuthMetadataHTTPTransport",
        lambda: transport,
    )
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.host.OAuthAuthorizationService",
        FakeAuthorizationService,
    )

    with pytest.raises(DiscoveredOAuthSetupError, match="metadata_drift"):
        authorize_discovered_mcp_oauth(
            root=tmp_path / "state",
            connection_id=_connection_id(tmp_path),
            persistent_reconnect=False,
        )

    assert FakeAuthorizationService.calls == []


def test_discovered_oauth_cli_returns_only_opaque_setup_receipts(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dynamic_agent_runner.workflow_host import cli

    captured: list[dict[str, object]] = []
    monkeypatch.setattr(
        cli,
        "authorize_discovered_mcp_oauth",
        lambda **kwargs: (
            captured.append(kwargs)
            or DiscoveredOAuthAuthorizationResult(
                authentication_id="v1.authentication.signature",
                registration_id="v1.registration.signature",
            )
        ),
    )
    output: list[str] = []

    assert (
        cli.main(
            [
                "--state-root",
                str(tmp_path / "state"),
                "authorize-discovered-mcp-oauth",
                "--connection-id",
                "v1.connection.signature",
                "--persistent-reconnect",
            ],
            write=output.append,
        )
        == 0
    )

    assert captured == [
        {
            "root": tmp_path / "state",
            "connection_id": "v1.connection.signature",
            "persistent_reconnect": True,
            "existing_registration_id": None,
        }
    ]
    assert output == [
        '{"authentication_id":"v1.authentication.signature",'
        '"registration_id":"v1.registration.signature","status":"authenticated"}'
    ]


def test_discovered_oauth_inspection_is_human_text_not_a_machine_receipt(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dynamic_agent_runner.workflow_host import cli

    monkeypatch.setattr(
        cli,
        "inspect_discovered_mcp_oauth",
        lambda **_kwargs: DiscoveredOAuthSetupPreview(
            endpoint="https://mcp.example.test/mcp",
            challenged_scopes=("mail.read",),
            advertised_scopes=("mail.read", "mail.send"),
        ),
    )
    output: list[str] = []

    assert (
        cli.main(
            [
                "--state-root",
                str(tmp_path / "state"),
                "inspect-discovered-mcp-oauth",
                "--connection-id",
                "v1.connection.signature",
            ],
            write=output.append,
        )
        == 0
    )

    assert output == [
        "MCP endpoint: https://mcp.example.test/mcp\n"
        "Challenged scopes: mail.read\n"
        "Advertised scopes: mail.read mail.send\n"
        "Choose scopes in a human-only connection setup; package and workflow inputs cannot set them."
    ]


@pytest.mark.parametrize(
    "status",
    [
        "metadata_unavailable",
        "metadata_invalid",
        "authorization_server_selection_required",
        "registration_unavailable",
        "authorization_required",
        "metadata_drift",
    ],
)
def test_discovered_oauth_cli_emits_only_a_stable_failure_status(
    tmp_path, monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    from dynamic_agent_runner.workflow_host import cli

    def fail(**_kwargs: object) -> object:
        raise DiscoveredOAuthSetupError(status)

    monkeypatch.setattr(cli, "authorize_discovered_mcp_oauth", fail)
    output: list[str] = []

    assert (
        cli.main(
            [
                "--state-root",
                str(tmp_path / "state"),
                "authorize-discovered-mcp-oauth",
                "--connection-id",
                "v1.connection.signature",
            ],
            write=output.append,
        )
        == 0
    )

    assert output == [f'{{"status":"{status}"}}']
