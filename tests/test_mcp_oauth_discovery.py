"""Focused fake-only tests for MCP OAuth protected-resource discovery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from dynamic_agent_runner.workflow_host.oauth_discovery import (
    AuthorizationServerMetadata,
    OAuthDiscoveryError,
    OAuthDiscoveryRecordStore,
    OAuthMetadataDiscovery,
    OAuthMetadataHTTPResponse,
    ProtectedResourceMetadata,
    ScopeSelection,
    UrllibOAuthMetadataHTTPTransport,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore


@dataclass
class FakeMetadataTransport:
    responses: dict[str, OAuthMetadataHTTPResponse]

    def __post_init__(self) -> None:
        self.requests: list[tuple[str, int]] = []

    def get(self, url: str, *, max_response_bytes: int) -> OAuthMetadataHTTPResponse:
        self.requests.append((url, max_response_bytes))
        return self.responses[url]


def _response(
    *,
    status: int,
    body: bytes = b"",
    headers: dict[str, str] | None = None,
    url: str | None = None,
) -> OAuthMetadataHTTPResponse:
    return OAuthMetadataHTTPResponse(
        status=status,
        headers=headers or {},
        body=body,
        url=url,
    )


def test_discovery_uses_bearer_metadata_and_challenged_scope() -> None:
    endpoint = "https://mcp.example.test/private/mcp"
    metadata_url = (
        "https://mcp.example.test/.well-known/oauth-protected-resource/private/mcp"
    )
    transport = FakeMetadataTransport(
        {
            endpoint: _response(
                status=401,
                headers={
                    "WWW-Authenticate": (
                        f'Bearer resource_metadata="{metadata_url}", '
                        'scope="mail.read offline_access"'
                    )
                },
            ),
            metadata_url: _response(
                status=200,
                body=(
                    b'{"resource":"https://mcp.example.test/private/mcp",'
                    b'"authorization_servers":["https://auth.example.test"],'
                    b'"scopes_supported":["mail.read","mail.send"]}'
                ),
            ),
        }
    )

    result = OAuthMetadataDiscovery(transport=transport).discover_protected_resource(
        endpoint
    )

    assert result.resource == endpoint
    assert result.authorization_servers == ("https://auth.example.test",)
    assert result.scopes_supported == frozenset({"mail.read", "mail.send"})
    assert result.challenged_scopes == frozenset({"mail.read", "offline_access"})
    assert transport.requests == [(endpoint, 32_768), (metadata_url, 32_768)]


def test_discovery_record_retains_only_opaque_identity_and_digests(tmp_path) -> None:
    store = PrivateStateStore(tmp_path / "state")
    OAuthDiscoveryRecordStore(
        store=store,
        owner="test-local-principal",
        now=lambda: datetime(2026, 8, 26, tzinfo=UTC),
    ).record(
        connection_id="v1.connection.signature",
        protected_resource=ProtectedResourceMetadata(
            resource="https://mcp.example.test/mcp",
            authorization_servers=("https://auth.example.test/tenant",),
            scopes_supported=frozenset({"mail.read"}),
            challenged_scopes=frozenset({"mail.read"}),
        ),
        authorization_server=AuthorizationServerMetadata(
            issuer="https://auth.example.test/tenant",
            authorization_endpoint="https://auth.example.test/authorize",
            token_endpoint="https://auth.example.test/token",
            registration_endpoint="https://auth.example.test/register",
            token_endpoint_auth_methods_supported=frozenset({"none"}),
            code_challenge_methods_supported=frozenset({"S256"}),
            response_types_supported=frozenset({"code"}),
            grant_types_supported=frozenset({"authorization_code", "refresh_token"}),
        ),
        scopes=ScopeSelection(scopes=frozenset({"mail.read"}), scope_is_omitted=False),
    )

    records = store.active_records(
        kind="mcp_oauth_discovery",
        owner="test-local-principal",
        now=datetime(2026, 8, 26, tzinfo=UTC),
    )
    assert len(records) == 1
    payload = records[0][1].payload
    assert set(payload) == {
        "connection_id",
        "protected_resource_digest",
        "authorization_server_digest",
        "scope_digest",
    }
    assert all(
        isinstance(value, str) and len(value) == 64
        for key, value in payload.items()
        if key != "connection_id"
    )


def test_discovery_falls_back_from_endpoint_path_to_root_well_known_location() -> None:
    endpoint = "https://mcp.example.test/private/mcp"
    path_metadata = (
        "https://mcp.example.test/.well-known/oauth-protected-resource/private/mcp"
    )
    root_metadata = "https://mcp.example.test/.well-known/oauth-protected-resource"
    transport = FakeMetadataTransport(
        {
            endpoint: _response(status=401),
            path_metadata: _response(status=404),
            root_metadata: _response(
                status=200,
                body=(
                    b'{"resource":"https://mcp.example.test/private/mcp",'
                    b'"authorization_servers":["https://auth.example.test"]}'
                ),
            ),
        }
    )

    result = OAuthMetadataDiscovery(transport=transport).discover_protected_resource(
        endpoint
    )

    assert result.resource == endpoint
    assert transport.requests == [
        (endpoint, 32_768),
        (path_metadata, 32_768),
        (root_metadata, 32_768),
    ]


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (b"not-json", "metadata is invalid"),
        (
            b'{"resource":"https://other.example.test/mcp",'
            b'"authorization_servers":["https://auth.example.test"]}',
            "resource does not match",
        ),
    ],
)
def test_discovery_rejects_invalid_or_unbound_metadata(
    body: bytes, message: str
) -> None:
    endpoint = "https://mcp.example.test/mcp"
    metadata_url = "https://mcp.example.test/.well-known/oauth-protected-resource/mcp"
    transport = FakeMetadataTransport(
        {
            endpoint: _response(
                status=401,
                headers={
                    "WWW-Authenticate": f'Bearer resource_metadata="{metadata_url}"'
                },
            ),
            metadata_url: _response(status=200, body=body),
        }
    )

    with pytest.raises(OAuthDiscoveryError, match=message):
        OAuthMetadataDiscovery(transport=transport).discover_protected_resource(
            endpoint
        )


def test_discovery_rejects_redirected_or_oversized_metadata() -> None:
    endpoint = "https://mcp.example.test/mcp"
    metadata_url = "https://mcp.example.test/.well-known/oauth-protected-resource/mcp"
    transport = FakeMetadataTransport(
        {
            endpoint: _response(
                status=401,
                headers={
                    "WWW-Authenticate": f'Bearer resource_metadata="{metadata_url}"'
                },
            ),
            metadata_url: _response(
                status=200,
                url="https://attacker.example.test/metadata",
                body=b"{}",
            ),
        }
    )

    with pytest.raises(OAuthDiscoveryError, match="redirected"):
        OAuthMetadataDiscovery(transport=transport).discover_protected_resource(
            endpoint
        )
    transport.responses[metadata_url] = _response(
        status=200,
        body=b"x" * 32_769,
    )
    with pytest.raises(OAuthDiscoveryError, match="too large"):
        OAuthMetadataDiscovery(transport=transport).discover_protected_resource(
            endpoint
        )


def test_urllib_metadata_transport_reads_only_the_configured_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        status = 200
        headers = {"Content-Type": "application/json"}

        def __init__(self) -> None:
            self.read_limits: list[int] = []
            self.closed = False

        def read(self, limit: int) -> bytes:
            self.read_limits.append(limit)
            return b"abcd"

        def geturl(self) -> str:
            return "https://mcp.example.test/metadata"

        def close(self) -> None:
            self.closed = True

    class Opener:
        def __init__(self, response: Response) -> None:
            self.response = response
            self.requests: list[object] = []

        def open(self, request: object, *, timeout: int) -> Response:
            assert timeout == 30
            self.requests.append(request)
            return self.response

    response = Response()
    opener = Opener(response)
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.oauth_discovery.build_opener",
        lambda handler: opener,
    )

    result = UrllibOAuthMetadataHTTPTransport().get(
        "https://mcp.example.test/metadata", max_response_bytes=3
    )

    assert result.body == b"abcd"
    assert response.read_limits == [4]
    assert response.closed is True


def test_authorization_server_discovery_uses_ordered_metadata_locations() -> None:
    issuer = "https://auth.example.test/tenant"
    rfc8414 = "https://auth.example.test/.well-known/oauth-authorization-server/tenant"
    oidc_inserted = "https://auth.example.test/.well-known/openid-configuration/tenant"
    oidc_appended = "https://auth.example.test/tenant/.well-known/openid-configuration"
    transport = FakeMetadataTransport(
        {
            rfc8414: _response(status=404),
            oidc_inserted: _response(status=404),
            oidc_appended: _response(
                status=200,
                body=(
                    b'{"issuer":"https://auth.example.test/tenant",'
                    b'"authorization_endpoint":"https://auth.example.test/authorize",'
                    b'"token_endpoint":"https://auth.example.test/token",'
                    b'"registration_endpoint":"https://auth.example.test/register",'
                    b'"token_endpoint_auth_methods_supported":["none"],'
                    b'"code_challenge_methods_supported":["S256"]}'
                ),
            ),
        }
    )

    result = OAuthMetadataDiscovery(transport=transport).discover_authorization_server(
        _resource_metadata(issuer)
    )

    assert result == AuthorizationServerMetadata(
        issuer=issuer,
        authorization_endpoint="https://auth.example.test/authorize",
        token_endpoint="https://auth.example.test/token",
        registration_endpoint="https://auth.example.test/register",
        token_endpoint_auth_methods_supported=frozenset({"none"}),
        code_challenge_methods_supported=frozenset({"S256"}),
        response_types_supported=None,
        grant_types_supported=frozenset(),
    )
    assert transport.requests == [
        (rfc8414, 32_768),
        (oidc_inserted, 32_768),
        (oidc_appended, 32_768),
    ]


def test_authorization_server_discovery_requires_one_issuer_and_exact_metadata_issuer() -> (
    None
):
    transport = FakeMetadataTransport({})
    discovery = OAuthMetadataDiscovery(transport=transport)

    with pytest.raises(OAuthDiscoveryError, match="selection required"):
        discovery.discover_authorization_server(
            _resource_metadata(
                "https://auth-one.example.test", "https://auth-two.example.test"
            )
        )

    issuer = "https://auth.example.test"
    metadata_url = "https://auth.example.test/.well-known/oauth-authorization-server"
    transport.responses[metadata_url] = _response(
        status=200,
        body=(
            b'{"issuer":"https://substitute.example.test",'
            b'"authorization_endpoint":"https://auth.example.test/authorize",'
            b'"token_endpoint":"https://auth.example.test/token"}'
        ),
    )
    with pytest.raises(OAuthDiscoveryError, match="issuer does not match"):
        discovery.discover_authorization_server(_resource_metadata(issuer))


def test_scope_selection_requires_exact_challenge_or_least_privilege_offered_scope() -> (
    None
):
    challenged = _resource_metadata(
        "https://auth.example.test", challenged={"mail.read"}
    )

    assert OAuthMetadataDiscovery.confirm_scope_selection(
        challenged, selected_scopes={"mail.read"}, persistent_reconnect=False
    ) == ScopeSelection(scopes=frozenset({"mail.read"}), scope_is_omitted=False)
    with pytest.raises(OAuthDiscoveryError, match="challenged scopes"):
        OAuthMetadataDiscovery.confirm_scope_selection(
            challenged, selected_scopes={"mail.send"}, persistent_reconnect=False
        )

    offered = _resource_metadata(
        "https://auth.example.test", scopes={"mail.read", "mail.send", "offline_access"}
    )
    assert OAuthMetadataDiscovery.confirm_scope_selection(
        offered, selected_scopes={"mail.read"}, persistent_reconnect=False
    ) == ScopeSelection(scopes=frozenset({"mail.read"}), scope_is_omitted=False)
    with pytest.raises(OAuthDiscoveryError, match="offline_access"):
        OAuthMetadataDiscovery.confirm_scope_selection(
            offered, selected_scopes={"offline_access"}, persistent_reconnect=False
        )

    no_scope_advertised = _resource_metadata("https://auth.example.test")
    assert OAuthMetadataDiscovery.confirm_scope_selection(
        no_scope_advertised, selected_scopes=set(), persistent_reconnect=False
    ) == ScopeSelection(scopes=frozenset(), scope_is_omitted=True)


def _resource_metadata(
    *issuers: str,
    scopes: set[str] | None = None,
    challenged: set[str] | None = None,
) -> ProtectedResourceMetadata:
    return ProtectedResourceMetadata(
        resource="https://mcp.example.test/mcp",
        authorization_servers=issuers,
        scopes_supported=frozenset(scopes or set()),
        challenged_scopes=frozenset(challenged or set()),
    )
