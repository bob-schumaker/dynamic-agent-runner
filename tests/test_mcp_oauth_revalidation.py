"""Focused fake-only tests for dynamic OAuth reconnect revalidation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib

import pytest

from dynamic_agent_runner.workflow_host.connections import (
    MCPAuthentication,
    MCPConnection,
)
from dynamic_agent_runner.workflow_host.oauth_discovery import (
    AuthorizationServerMetadata,
    OAuthMetadataHTTPResponse,
    ScopeSelection,
)
from dynamic_agent_runner.workflow_host.oauth_registration import (
    OAuthClientRegistrationService,
)
from dynamic_agent_runner.workflow_host.oauth_revalidation import (
    DiscoveredOAuthRevalidator,
)
from dynamic_agent_runner.workflow_host.profiles import InstallationIdentityProvider
from dynamic_agent_runner.workflow_host.state import PrivateStateStore


@dataclass
class FakeRevalidationTransport:
    protected_resource: str

    def __post_init__(self) -> None:
        self.redirect = (
            "http://localhost/oauth/callback/"
            + hashlib.sha256(
                (
                    f"{InstallationIdentityProvider().principal}\0"
                    "https://auth.example.test/tenant"
                ).encode()
            ).hexdigest()[:24]
        )

    def get(self, url: str, *, max_response_bytes: int) -> OAuthMetadataHTTPResponse:
        if url == "https://mcp.example.test/mcp":
            return OAuthMetadataHTTPResponse(
                status=401,
                headers={
                    "WWW-Authenticate": (
                        'Bearer resource_metadata="https://mcp.example.test/metadata"'
                    )
                },
                body=b"",
            )
        if url == "https://mcp.example.test/metadata":
            return OAuthMetadataHTTPResponse(
                status=200,
                headers={},
                body=(
                    b'{"resource":"'
                    + self.protected_resource.encode()
                    + b'","authorization_servers":["https://auth.example.test/tenant"],'
                    b'"scopes_supported":["mail.read"]}'
                ),
            )
        if (
            url
            == "https://auth.example.test/.well-known/oauth-authorization-server/tenant"
        ):
            return OAuthMetadataHTTPResponse(
                status=200,
                headers={},
                body=(
                    b'{"issuer":"https://auth.example.test/tenant",'
                    b'"authorization_endpoint":"https://auth.example.test/authorize",'
                    b'"token_endpoint":"https://auth.example.test/token",'
                    b'"registration_endpoint":"https://auth.example.test/register",'
                    b'"token_endpoint_auth_methods_supported":["none"],'
                    b'"code_challenge_methods_supported":["S256"],'
                    b'"response_types_supported":["code"],'
                    b'"grant_types_supported":["authorization_code","refresh_token"]}'
                ),
            )
        raise AssertionError(f"unexpected metadata URL {url}")

    def post_json(
        self, url: str, *, payload: dict[str, object], max_response_bytes: int
    ) -> OAuthMetadataHTTPResponse:
        assert url == "https://auth.example.test/register"
        return OAuthMetadataHTTPResponse(
            status=201,
            headers={},
            body=(
                b'{"client_id":"registered-client",'
                b'"token_endpoint_auth_method":"none",'
                + f'"redirect_uris":["{self.redirect}"]}}'.encode()
            ),
        )


def _metadata() -> AuthorizationServerMetadata:
    return AuthorizationServerMetadata(
        issuer="https://auth.example.test/tenant",
        authorization_endpoint="https://auth.example.test/authorize",
        token_endpoint="https://auth.example.test/token",
        registration_endpoint="https://auth.example.test/register",
        token_endpoint_auth_methods_supported=frozenset({"none"}),
        code_challenge_methods_supported=frozenset({"S256"}),
        response_types_supported=frozenset({"code"}),
        grant_types_supported=frozenset({"authorization_code", "refresh_token"}),
    )


def _binding(tmp_path, transport: FakeRevalidationTransport):
    store = PrivateStateStore(tmp_path / "state")
    owner = InstallationIdentityProvider().principal
    registration = OAuthClientRegistrationService(
        store=store,
        owner=owner,
        transport=transport,
        now=lambda: datetime(2026, 8, 26, tzinfo=UTC),
    ).register_or_reuse(
        metadata=_metadata(),
        scopes=ScopeSelection(scopes=frozenset({"mail.read"}), scope_is_omitted=False),
        resource="https://mcp.example.test/mcp",
        connection_id="v1.connection.signature",
    )
    return store, MCPAuthentication(
        authentication_id="v1.authentication.signature",
        connection_id="v1.connection.signature",
        authentication_method="oauth_authorization_code_pkce_loopback",
        credential_ref="secret-ref",
        authentication_status="authenticated",
        oauth_token_endpoint="https://auth.example.test/token",
        oauth_client_id=registration.client_id,
        oauth_resource="https://mcp.example.test/mcp",
        oauth_issuer="https://auth.example.test/tenant",
        oauth_authorization_endpoint="https://auth.example.test/authorize",
        oauth_registration_id=registration.registration_id,
    )


def _connection() -> MCPConnection:
    return MCPConnection(
        connection_id="v1.connection.signature",
        profile_id="v1.profile.signature",
        transport="https_jsonrpc",
        endpoint="https://mcp.example.test/mcp",
        scopes=frozenset({"mail.read"}),
        authentication_method="oauth_authorization_code_pkce_loopback",
        authentication_status="authenticated",
    )


def test_revalidator_accepts_the_exact_current_dynamic_binding(tmp_path) -> None:
    transport = FakeRevalidationTransport("https://mcp.example.test/mcp")
    store, authentication = _binding(tmp_path, transport)

    DiscoveredOAuthRevalidator(store=store, transport=transport).revalidate(
        connection=_connection(), authentication=authentication
    )


def test_revalidator_rejects_changed_protected_resource_before_reconnect(
    tmp_path,
) -> None:
    transport = FakeRevalidationTransport("https://mcp.example.test/mcp")
    store, authentication = _binding(tmp_path, transport)
    transport.protected_resource = "https://attacker.example.test/mcp"

    with pytest.raises(ValueError, match="metadata drift"):
        DiscoveredOAuthRevalidator(store=store, transport=transport).revalidate(
            connection=_connection(), authentication=authentication
        )
