"""Human-owned, credential-free definitions for generic HTTPS MCP connections."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import secrets
from typing import Iterable, Protocol
from urllib.parse import urlsplit

from dynamic_agent_runner.workflow_host.profiles import (
    InstallationIdentityProvider,
    LocalModelProfileControlPlane,
    LocalModelProfileError,
)
from dynamic_agent_runner.workflow_host.state import (
    OpaqueRecordError,
    PrivateStateStore,
)


SUPPORTED_TRANSPORT = "https_mcp_v1"
SUPPORTED_AUTHENTICATION_METHODS = frozenset(
    {"api_token", "oauth_authorization_code_pkce_loopback"}
)


class MCPConnectionError(ValueError):
    """Raised when a human-managed MCP connection record is unavailable."""


class SecretStoreError(ValueError):
    """Raised when a credential cannot be kept outside the state store."""


class SecretStore(Protocol):
    """Private OS-secret storage used only by human control-plane operations."""

    def store(self, secret: str) -> str:
        """Store a secret and return an opaque reference."""

    def load(self, reference: str) -> str:
        """Load a secret by opaque reference for host-owned use only."""

    def delete(self, reference: str) -> None:
        """Delete a previously stored secret after a failed setup."""

    def replace(self, reference: str, secret: str) -> None:
        """Atomically replace one existing secret without changing its reference."""


class KeyringSecretStore:
    """Use the platform credential manager without putting secrets in state."""

    _SERVICE_NAME = "dynamic-agent-runner.dar-authoring.mcp-v1"

    def __init__(self, *, principal: str) -> None:
        self._principal = principal

    def store(self, secret: str) -> str:
        reference = f"mcp-secret-v1-{secrets.token_urlsafe(32)}"
        self._set(reference, secret)
        return reference

    def load(self, reference: str) -> str:
        try:
            import keyring

            secret = keyring.get_password(
                self._SERVICE_NAME, self._account_name(reference)
            )
        except Exception as error:
            raise SecretStoreError("credential store is unavailable") from error
        if not isinstance(secret, str) or not secret:
            raise SecretStoreError("credential is unavailable")
        return secret

    def delete(self, reference: str) -> None:
        try:
            import keyring

            keyring.delete_password(self._SERVICE_NAME, self._account_name(reference))
        except Exception as error:
            raise SecretStoreError("credential store is unavailable") from error

    def replace(self, reference: str, secret: str) -> None:
        self._set(reference, secret)

    def _set(self, reference: str, secret: str) -> None:
        try:
            import keyring

            keyring.set_password(
                self._SERVICE_NAME, self._account_name(reference), secret
            )
        except Exception as error:
            raise SecretStoreError("credential store is unavailable") from error

    def _account_name(self, reference: str) -> str:
        return f"{self._principal}:{reference}"


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


@dataclass(frozen=True)
class MCPAuthentication:
    """An immutable connection-to-secret reference without secret material."""

    authentication_id: str
    connection_id: str
    authentication_method: str
    credential_ref: str
    authentication_status: str
    oauth_token_endpoint: str | None = None
    oauth_client_id: str | None = None


class MCPConnectionControlPlane:
    """Human-only creation and lookup boundary for generic MCP connections."""

    def __init__(
        self,
        *,
        store: PrivateStateStore,
        profiles: LocalModelProfileControlPlane,
        secret_store: SecretStore | None = None,
    ) -> None:
        self._store = store
        self._profiles = profiles
        self._identity = InstallationIdentityProvider()
        self._secret_store = secret_store or KeyringSecretStore(
            principal=self._identity.principal
        )

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

    def configure_api_token(self, connection_id: str, token: str) -> MCPAuthentication:
        """Store a human-provided API token outside records and bind its reference."""

        connection = self.load(connection_id)
        if connection.authentication_method != "api_token":
            raise MCPConnectionError("connection does not use API-token authentication")
        if not isinstance(token, str) or not token:
            raise MCPConnectionError("API token must be a non-empty string")
        return self._store_authentication(connection, token)

    def configure_oauth_token(
        self,
        connection_id: str,
        token_bundle: str,
        *,
        token_endpoint: str,
        client_id: str,
    ) -> MCPAuthentication:
        """Store an OAuth token bundle after the human-only PKCE exchange."""

        connection = self.load(connection_id)
        if connection.authentication_method != "oauth_authorization_code_pkce_loopback":
            raise MCPConnectionError("connection does not use OAuth authentication")
        if not isinstance(token_bundle, str) or not token_bundle:
            raise MCPConnectionError("OAuth token bundle is unavailable")
        _https_endpoint(token_endpoint)
        if not isinstance(client_id, str) or not client_id:
            raise MCPConnectionError("OAuth client_id is invalid")
        return self._store_authentication(
            connection,
            token_bundle,
            oauth_token_endpoint=token_endpoint,
            oauth_client_id=client_id,
        )

    def _store_authentication(
        self,
        connection: MCPConnection,
        secret: str,
        *,
        oauth_token_endpoint: str | None = None,
        oauth_client_id: str | None = None,
    ) -> MCPAuthentication:
        """Persist only an opaque secret-store reference for one connection."""

        try:
            credential_ref = self._secret_store.store(secret)
        except SecretStoreError as error:
            raise MCPConnectionError("credential store is unavailable") from error
        try:
            authentication_id = self._store.issue(
                kind="mcp_authentication",
                owner=self._identity.principal,
                payload={
                    "connection_id": connection.connection_id,
                    "authentication_method": connection.authentication_method,
                    "credential_ref": credential_ref,
                    "oauth_token_endpoint": oauth_token_endpoint,
                    "oauth_client_id": oauth_client_id,
                },
                expires_at=datetime.max.replace(tzinfo=UTC),
                now=datetime.now(UTC),
            )
        except OpaqueRecordError as error:
            try:
                self._secret_store.delete(credential_ref)
            except SecretStoreError:
                pass
            raise MCPConnectionError(
                "authentication record could not be created"
            ) from error
        return MCPAuthentication(
            authentication_id=authentication_id,
            connection_id=connection.connection_id,
            authentication_method=connection.authentication_method,
            credential_ref=credential_ref,
            authentication_status="authenticated",
            oauth_token_endpoint=oauth_token_endpoint,
            oauth_client_id=oauth_client_id,
        )

    def load_authentication(self, authentication_id: str) -> MCPAuthentication:
        """Load an authenticated connection binding owned by this OS user."""

        try:
            record = self._store.load(
                authentication_id,
                expected_kind="mcp_authentication",
                owner=self._identity.principal,
                now=datetime.now(UTC),
            )
            connection_id = record.payload["connection_id"]
            authentication_method = record.payload["authentication_method"]
            credential_ref = record.payload["credential_ref"]
            oauth_token_endpoint = record.payload.get("oauth_token_endpoint")
            oauth_client_id = record.payload.get("oauth_client_id")
        except (OpaqueRecordError, KeyError, TypeError) as error:
            raise MCPConnectionError("authentication record is unavailable") from error
        _opaque_id(connection_id, "connection_id")
        if (
            authentication_method not in SUPPORTED_AUTHENTICATION_METHODS
            or not isinstance(credential_ref, str)
            or not credential_ref
        ):
            raise MCPConnectionError("authentication record is invalid")
        connection = self.load(connection_id)
        if connection.authentication_method != authentication_method:
            raise MCPConnectionError("authentication record is invalid")
        if authentication_method == "oauth_authorization_code_pkce_loopback":
            _https_endpoint(oauth_token_endpoint)
            if not isinstance(oauth_client_id, str) or not oauth_client_id:
                raise MCPConnectionError("authentication record is invalid")
        elif oauth_token_endpoint is not None or oauth_client_id is not None:
            raise MCPConnectionError("authentication record is invalid")
        return MCPAuthentication(
            authentication_id=authentication_id,
            connection_id=connection_id,
            authentication_method=authentication_method,
            credential_ref=credential_ref,
            authentication_status="authenticated",
            oauth_token_endpoint=oauth_token_endpoint,
            oauth_client_id=oauth_client_id,
        )

    def replace_oauth_credential(
        self, authentication_id: str, token_bundle: str
    ) -> None:
        """Replace an OAuth secret in place without changing its authentication ID."""

        authentication = self.load_authentication(authentication_id)
        if (
            authentication.authentication_method
            != "oauth_authorization_code_pkce_loopback"
        ):
            raise MCPConnectionError("connection does not use OAuth authentication")
        if not isinstance(token_bundle, str) or not token_bundle:
            raise MCPConnectionError("OAuth token bundle is unavailable")
        try:
            self._secret_store.replace(authentication.credential_ref, token_bundle)
        except SecretStoreError as error:
            raise MCPConnectionError("credential store is unavailable") from error

    def credential_for_authentication(
        self, authentication_id: str
    ) -> tuple[MCPAuthentication, str]:
        """Return one credential only to a host-owned transport constructor."""

        authentication = self.load_authentication(authentication_id)
        try:
            secret = self._secret_store.load(authentication.credential_ref)
        except SecretStoreError as error:
            raise MCPConnectionError("credential is unavailable") from error
        return authentication, secret

    def preflight(
        self, connection_id: str, *, authentication_id: str | None = None
    ) -> MCPConnectionPreflight:
        """Return readiness only for a matching usable authentication binding."""

        connection = self.load(connection_id)
        if authentication_id is None:
            return MCPConnectionPreflight(
                connection.connection_id, connection.authentication_status
            )
        authentication, _ = self.credential_for_authentication(authentication_id)
        if authentication.connection_id != connection.connection_id:
            raise MCPConnectionError("authentication record is for another connection")
        return MCPConnectionPreflight(
            connection.connection_id, authentication.authentication_status
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
