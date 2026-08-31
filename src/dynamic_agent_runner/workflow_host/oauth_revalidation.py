"""Revalidate dynamic MCP OAuth metadata before reconnecting a client."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from dynamic_agent_runner.workflow_host.connections import (
    MCPAuthentication,
    MCPConnection,
)
from dynamic_agent_runner.workflow_host.oauth_discovery import (
    OAuthDiscoveryError,
    OAuthMetadataDiscovery,
    OAuthMetadataHTTPResponse,
)
from dynamic_agent_runner.workflow_host.oauth_registration import (
    OAuthClientRegistrationError,
    OAuthClientRegistrationService,
)
from dynamic_agent_runner.workflow_host.profiles import InstallationIdentityProvider
from dynamic_agent_runner.workflow_host.state import PrivateStateStore


class OAuthRevalidationHTTPTransport(Protocol):
    """Bounded no-redirect transport required by discovery and registration reuse."""

    def get(self, url: str, *, max_response_bytes: int) -> OAuthMetadataHTTPResponse:
        """Return a bounded response for exactly one URL."""

    def post_json(
        self,
        url: str,
        *,
        payload: dict[str, object],
        max_response_bytes: int,
    ) -> OAuthMetadataHTTPResponse:
        """Present only for the registration-service transport contract."""


@dataclass(frozen=True)
class DiscoveredOAuthRevalidator:
    """Fail closed when a saved dynamic OAuth binding no longer matches discovery."""

    store: PrivateStateStore
    transport: OAuthRevalidationHTTPTransport

    def revalidate(
        self, *, connection: MCPConnection, authentication: MCPAuthentication
    ) -> None:
        """Verify current resource, issuer, scopes, endpoints, and registration binding."""

        try:
            self._revalidate(connection=connection, authentication=authentication)
        except (OAuthDiscoveryError, OAuthClientRegistrationError) as error:
            raise ValueError("OAuth metadata drift") from error

    def _revalidate(
        self, *, connection: MCPConnection, authentication: MCPAuthentication
    ) -> None:
        """Perform the metadata and registration comparisons for one connection."""

        if (
            authentication.oauth_resource is None
            or authentication.oauth_issuer is None
            or authentication.oauth_authorization_endpoint is None
            or authentication.oauth_registration_id is None
            or authentication.oauth_token_endpoint is None
            or authentication.oauth_client_id is None
        ):
            raise ValueError("OAuth discovery binding is unavailable")
        discovery = OAuthMetadataDiscovery(transport=self.transport)
        protected_resource = discovery.discover_protected_resource(connection.endpoint)
        if protected_resource.resource != authentication.oauth_resource:
            raise ValueError("OAuth metadata drift")
        authorization_server = discovery.discover_authorization_server(
            protected_resource
        )
        if (
            authorization_server.issuer != authentication.oauth_issuer
            or authorization_server.authorization_endpoint
            != authentication.oauth_authorization_endpoint
            or authorization_server.token_endpoint
            != authentication.oauth_token_endpoint
        ):
            raise ValueError("OAuth metadata drift")
        scopes = discovery.confirm_scope_selection(
            protected_resource,
            selected_scopes=set(connection.scopes),
            persistent_reconnect=authentication.oauth_persistent_reconnect,
        )
        registration = OAuthClientRegistrationService(
            store=self.store,
            owner=InstallationIdentityProvider().principal,
            transport=self.transport,
            now=lambda: datetime.now(UTC),
        ).register_or_reuse(
            metadata=authorization_server,
            scopes=scopes,
            resource=protected_resource.resource,
            connection_id=connection.connection_id,
            existing_registration_id=authentication.oauth_registration_id,
        )
        if registration.client_id != authentication.oauth_client_id:
            raise ValueError("OAuth metadata drift")
