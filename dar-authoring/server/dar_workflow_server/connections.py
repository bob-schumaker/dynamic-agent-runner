"""Human-owned, credential-free definitions for generic HTTPS MCP connections."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterable
from urllib.parse import urlsplit

from dar_workflow_server.profiles import (
    InstallationIdentityProvider,
    LocalModelProfileControlPlane,
    LocalModelProfileError,
)
from dar_workflow_server.state import OpaqueRecordError, PrivateStateStore


SUPPORTED_TRANSPORT = "https_mcp_v1"
SUPPORTED_AUTHENTICATION_METHODS = frozenset(
    {"api_token", "oauth_authorization_code_pkce_loopback"}
)


class MCPConnectionError(ValueError):
    """Raised when a human-managed MCP connection record is unavailable."""


@dataclass(frozen=True)
class MCPConnection:
    """An immutable generic HTTPS MCP connection definition without secrets."""

    connection_id: str
    profile_id: str
    transport: str
    endpoint: str
    scopes: frozenset[str]
    authentication_method: str
    authentication_status: str


@dataclass(frozen=True)
class MCPConnectionPreflight:
    """A closed non-secret connection readiness state for capability resolution."""

    connection_id: str
    status: str


class MCPConnectionControlPlane:
    """Human-only creation and lookup boundary for generic MCP connections."""

    def __init__(
        self,
        *,
        store: PrivateStateStore,
        profiles: LocalModelProfileControlPlane,
    ) -> None:
        self._store = store
        self._profiles = profiles
        self._identity = InstallationIdentityProvider()

    def create(
        self,
        *,
        profile_id: str,
        endpoint: str,
        scopes: Iterable[str],
        authentication_method: str,
    ) -> MCPConnection:
        """Persist a credential-free definition pending human authentication."""

        _opaque_id(profile_id, "profile_id")
        try:
            self._profiles.load(profile_id)
        except LocalModelProfileError as error:
            raise MCPConnectionError("profile is unavailable") from error
        _https_endpoint(endpoint)
        scope_set = _scopes(scopes)
        if authentication_method not in SUPPORTED_AUTHENTICATION_METHODS:
            raise MCPConnectionError("authentication method is unsupported")
        try:
            connection_id = self._store.issue(
                kind="mcp_connection",
                owner=self._identity.principal,
                payload={
                    "profile_id": profile_id,
                    "transport": SUPPORTED_TRANSPORT,
                    "endpoint": endpoint,
                    "scopes": sorted(scope_set),
                    "authentication_method": authentication_method,
                },
                expires_at=datetime.max.replace(tzinfo=UTC),
                now=datetime.now(UTC),
            )
        except OpaqueRecordError as error:
            raise MCPConnectionError(
                "connection record could not be created"
            ) from error
        return MCPConnection(
            connection_id,
            profile_id,
            SUPPORTED_TRANSPORT,
            endpoint,
            scope_set,
            authentication_method,
            "authentication_required",
        )

    def load(self, connection_id: str) -> MCPConnection:
        """Load a connection owned by the current local principal."""

        try:
            record = self._store.load(
                connection_id,
                expected_kind="mcp_connection",
                owner=self._identity.principal,
                now=datetime.now(UTC),
            )
        except OpaqueRecordError as error:
            raise MCPConnectionError("connection record is unavailable") from error
        payload = record.payload
        try:
            profile_id = payload["profile_id"]
            transport = payload["transport"]
            endpoint = payload["endpoint"]
            scopes = _scopes(payload["scopes"])
            authentication_method = payload["authentication_method"]
        except (KeyError, TypeError, MCPConnectionError) as error:
            raise MCPConnectionError("connection record is invalid") from error
        _opaque_id(profile_id, "profile_id")
        _https_endpoint(endpoint)
        if (
            transport != SUPPORTED_TRANSPORT
            or authentication_method not in SUPPORTED_AUTHENTICATION_METHODS
        ):
            raise MCPConnectionError("connection record is invalid")
        return MCPConnection(
            connection_id,
            profile_id,
            transport,
            endpoint,
            scopes,
            authentication_method,
            "authentication_required",
        )

    def preflight(self, connection_id: str) -> MCPConnectionPreflight:
        """Return the non-executing state until a later credential setup succeeds."""

        connection = self.load(connection_id)
        return MCPConnectionPreflight(
            connection.connection_id, connection.authentication_status
        )


def _opaque_id(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.startswith("v1."):
        raise MCPConnectionError(f"{name} must be an opaque identifier")


def _https_endpoint(value: object) -> None:
    if not isinstance(value, str) or not value:
        raise MCPConnectionError("endpoint must be an HTTPS URL")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise MCPConnectionError("endpoint must be an HTTPS URL")


def _scopes(value: Iterable[object]) -> frozenset[str]:
    if isinstance(value, str):
        raise MCPConnectionError("scopes must contain non-empty strings")
    scopes = frozenset(value)
    if not scopes or any(not isinstance(scope, str) or not scope for scope in scopes):
        raise MCPConnectionError("scopes must contain non-empty strings")
    return scopes
