"""Host-owned HTTPS MCP initialization lifecycle with strict transport binding."""

from __future__ import annotations

import hmac
import http.client
import json
import hashlib
import ssl
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Event
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import urlsplit

from dar_workflow_server.connections import (
    MCPAuthentication,
    MCPConnection,
    MCPConnectionControlPlane,
    MCPConnectionError,
)
from dar_workflow_server.mcp_surfaces import MCPDiscoveredTool
from dar_workflow_server.oauth import OAuthError, OAuthTokenBundle, OAuthTokenRefresher


class MCPConnectionClientError(ValueError):
    """Raised when a configured MCP transport cannot remain safely bound."""


class MCPConnectionAuthenticationError(MCPConnectionClientError):
    """Raised only when MCP setup rejects the presented credential."""


@dataclass(frozen=True)
class MCPClientConfiguration:
    """Human-configured transport limits and immutable identity bindings."""

    connection_id: str
    authentication_id: str
    peer_certificate_sha256: str
    timeout_seconds: int
    max_response_bytes: int

    def __post_init__(self) -> None:
        _opaque_id(self.connection_id, "connection_id")
        _opaque_id(self.authentication_id, "authentication_id")
        if (
            not isinstance(self.peer_certificate_sha256, str)
            or len(self.peer_certificate_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.peer_certificate_sha256
            )
        ):
            raise MCPConnectionClientError("peer certificate pin is invalid")
        if (
            not isinstance(self.timeout_seconds, int)
            or not 0 < self.timeout_seconds <= 60
        ):
            raise MCPConnectionClientError("timeout is out of range")
        if (
            not isinstance(self.max_response_bytes, int)
            or not 0 < self.max_response_bytes <= 1_048_576
        ):
            raise MCPConnectionClientError("response limit is out of range")


@dataclass(frozen=True)
class MCPTransportResponse:
    """Bounded non-secret result of a transport initialization request."""

    peer_certificate_sha256: str
    body_bytes: int
    protocol_version: str
    server_name: str


@dataclass(frozen=True)
class MCPInitializedConnection:
    """A current initialized transport identity without remote tool information."""

    connection_id: str
    authentication_id: str
    generation: int
    protocol_version: str
    server_name: str


class HTTPSMCPTransportSession(Protocol):
    """A connected HTTPS session; only lifecycle initialization is available here."""

    def initialize(
        self, *, timeout_seconds: int, max_response_bytes: int
    ) -> MCPTransportResponse:
        """Initialize the remote MCP session with bounded I/O."""

    def close(self) -> None:
        """Release all transport resources."""

    def list_tools(
        self, *, timeout_seconds: int, max_response_bytes: int
    ) -> tuple[MCPDiscoveredTool, ...]:
        """Return the bounded remote `tools/list` identity/schema surface."""

    def call_tool(
        self,
        *,
        name: str,
        arguments: Mapping[str, object],
        timeout_seconds: int,
        max_response_bytes: int,
    ) -> Mapping[str, object]:
        """Call one reviewed remote tool with bounded transport I/O."""


class HTTPSMCPTransportFactory(Protocol):
    """Construct a session only from host-owned connection data."""

    def open(
        self, *, endpoint: str, bearer_token: str, timeout_seconds: int
    ) -> HTTPSMCPTransportSession:
        """Connect to one configured HTTPS endpoint."""


class HTTPSJSONRPCMCPTransportFactory:
    """Create HTTPS JSON-RPC initialization sessions for configured MCP servers."""

    def __init__(
        self,
        *,
        connection_factory: Callable[..., http.client.HTTPSConnection] | None = None,
    ) -> None:
        self._connection_factory = connection_factory or _https_connection

    def open(
        self, *, endpoint: str, bearer_token: str, timeout_seconds: int
    ) -> HTTPSJSONRPCMCPTransportSession:
        return HTTPSJSONRPCMCPTransportSession(
            endpoint=endpoint,
            bearer_token=bearer_token,
            timeout_seconds=timeout_seconds,
            connection_factory=self._connection_factory,
        )


class HTTPSJSONRPCMCPTransportSession:
    """One HTTPS connection that supports the MCP `initialize` lifecycle step."""

    def __init__(
        self,
        *,
        endpoint: str,
        bearer_token: str,
        timeout_seconds: int,
        connection_factory: Callable[..., http.client.HTTPSConnection],
    ) -> None:
        parsed = urlsplit(endpoint)
        if parsed.scheme != "https" or not parsed.hostname or parsed.query:
            raise MCPConnectionClientError("HTTPS MCP endpoint is invalid")
        self._host = parsed.hostname
        self._port = parsed.port or 443
        self._path = parsed.path or "/"
        self._bearer_token = bearer_token
        self._timeout_seconds = timeout_seconds
        self._connection_factory = connection_factory
        self._connection: http.client.HTTPSConnection | None = None
        self._initialized = False

    def initialize(
        self, *, timeout_seconds: int, max_response_bytes: int
    ) -> MCPTransportResponse:
        if timeout_seconds != self._timeout_seconds:
            raise MCPConnectionClientError("HTTPS MCP timeout changed after connection")
        if self._connection is not None:
            raise MCPConnectionClientError("HTTPS MCP session is already initialized")
        connection = self._connection_factory(
            host=self._host,
            port=self._port,
            timeout=timeout_seconds,
        )
        self._connection = connection
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "dar-authoring", "version": "1"},
                },
            },
            separators=(",", ":"),
        ).encode("utf-8")
        try:
            connection.request(
                "POST",
                self._path,
                body=payload,
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Authorization": f"Bearer {self._bearer_token}",
                    "Content-Type": "application/json",
                },
            )
            response = connection.getresponse()
            if response.status in {401, 403}:
                raise MCPConnectionAuthenticationError(
                    "HTTPS MCP initialization authentication was rejected"
                )
            if response.status != 200:
                raise MCPConnectionClientError("HTTPS MCP initialization was rejected")
            body = response.read(max_response_bytes + 1)
            if len(body) > max_response_bytes:
                raise MCPConnectionClientError("HTTPS MCP response is too large")
            certificate = _peer_certificate(connection)
            result = _initialization_result(body)
        except MCPConnectionClientError:
            raise
        except Exception as error:
            raise MCPConnectionClientError("HTTPS MCP initialization failed") from error
        self._initialized = True
        return MCPTransportResponse(
            peer_certificate_sha256=hashlib.sha256(certificate).hexdigest(),
            body_bytes=len(body),
            protocol_version=result["protocol_version"],
            server_name=result["server_name"],
        )

    def list_tools(
        self, *, timeout_seconds: int, max_response_bytes: int
    ) -> tuple[MCPDiscoveredTool, ...]:
        if not self._initialized:
            raise MCPConnectionClientError("HTTPS MCP session is not initialized")
        body = self._json_rpc_request(
            method="tools/list",
            request_id=2,
            params={},
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
        )
        return _discovered_tools(body)

    def call_tool(
        self,
        *,
        name: str,
        arguments: Mapping[str, object],
        timeout_seconds: int,
        max_response_bytes: int,
    ) -> Mapping[str, object]:
        if not isinstance(name, str) or not name:
            raise MCPConnectionClientError("MCP tool name is invalid")
        if not isinstance(arguments, Mapping):
            raise MCPConnectionClientError("MCP tool arguments are invalid")
        body = self._json_rpc_request(
            method="tools/call",
            request_id=3,
            params={"name": name, "arguments": dict(arguments)},
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
        )
        return _tool_call_result(body)

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None
        self._initialized = False

    def _json_rpc_request(
        self,
        *,
        method: str,
        request_id: int,
        params: dict[str, object],
        timeout_seconds: int,
        max_response_bytes: int,
    ) -> bytes:
        if timeout_seconds != self._timeout_seconds:
            raise MCPConnectionClientError("HTTPS MCP timeout changed after connection")
        if self._connection is None:
            raise MCPConnectionClientError("HTTPS MCP session is unavailable")
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        try:
            self._connection.request(
                "POST",
                self._path,
                body=payload,
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Authorization": f"Bearer {self._bearer_token}",
                    "Content-Type": "application/json",
                },
            )
            response = self._connection.getresponse()
            if response.status != 200:
                raise MCPConnectionClientError("HTTPS MCP request was rejected")
            body = response.read(max_response_bytes + 1)
        except MCPConnectionClientError:
            raise
        except Exception as error:
            raise MCPConnectionClientError("HTTPS MCP request failed") from error
        if len(body) > max_response_bytes:
            raise MCPConnectionClientError("HTTPS MCP response is too large")
        return body


@dataclass
class MCPConnectionClient:
    """Lifecycle owner for one authentication-bound configured HTTPS MCP server."""

    connections: MCPConnectionControlPlane
    configuration: MCPClientConfiguration
    transport_factory: HTTPSMCPTransportFactory
    oauth_refresher: OAuthTokenRefresher | None = None
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    _session: HTTPSMCPTransportSession | None = field(
        default=None, init=False, repr=False
    )
    _generation: int = field(default=0, init=False)

    @property
    def connection_id(self) -> str:
        """Return the immutable connection identity for this client."""

        return self.configuration.connection_id

    @property
    def authentication_id(self) -> str:
        """Return the immutable credential identity for this client."""

        return self.configuration.authentication_id

    @property
    def current_generation(self) -> int:
        """Return the initialized generation, failing closed after close."""

        if self._session is None:
            raise MCPConnectionClientError("HTTPS MCP connection is not initialized")
        return self._generation

    def initialize(
        self, *, cancellation: Event | None = None
    ) -> MCPInitializedConnection:
        """Initialize one session after credential and certificate-pin verification."""

        _raise_if_cancelled(cancellation)
        if self._session is not None:
            raise MCPConnectionClientError("MCP connection is already initialized")
        connection, authentication, secret = self._configured_connection()
        session: HTTPSMCPTransportSession | None = None
        try:
            session, response = self._initialize_bound_session(
                connection=connection,
                authentication=authentication,
                secret=secret,
                cancellation=cancellation,
            )
        except MCPConnectionClientError:
            if session is not None:
                session.close()
            raise
        except Exception as error:
            if session is not None:
                session.close()
            raise MCPConnectionClientError("HTTPS MCP initialization failed") from error
        self._session = session
        self._generation += 1
        return MCPInitializedConnection(
            connection_id=connection.connection_id,
            authentication_id=authentication.authentication_id,
            generation=self._generation,
            protocol_version=response.protocol_version,
            server_name=response.server_name,
        )

    def _configured_connection(
        self,
    ) -> tuple[MCPConnection, MCPAuthentication, str]:
        try:
            connection = self.connections.load(self.configuration.connection_id)
            authentication, secret = self.connections.credential_for_authentication(
                self.configuration.authentication_id
            )
        except MCPConnectionError as error:
            raise MCPConnectionClientError(
                "configured connection is unavailable"
            ) from error
        if authentication.connection_id != connection.connection_id:
            raise MCPConnectionClientError(
                "authentication is bound to another connection"
            )
        return (
            connection,
            authentication,
            self._refresh_expired_oauth_credential(authentication, secret),
        )

    def _initialize_bound_session(
        self,
        *,
        connection: MCPConnection,
        authentication: MCPAuthentication,
        secret: str,
        cancellation: Event | None,
    ) -> tuple[HTTPSMCPTransportSession, MCPTransportResponse]:
        for setup_attempt in range(2):
            try:
                return self._open_initialized_session(
                    endpoint=connection.endpoint,
                    authentication=authentication,
                    secret=secret,
                    cancellation=cancellation,
                )
            except MCPConnectionAuthenticationError as error:
                if (
                    authentication.authentication_method
                    != "oauth_authorization_code_pkce_loopback"
                ):
                    raise
                if setup_attempt != 0:
                    raise MCPConnectionClientError(
                        "OAuth authentication is required"
                    ) from error
                secret = self._refresh_expired_oauth_credential(
                    authentication, secret, force=True
                )
        raise MCPConnectionClientError("OAuth authentication is required")

    def _open_initialized_session(
        self,
        *,
        endpoint: str,
        authentication: MCPAuthentication,
        secret: str,
        cancellation: Event | None,
    ) -> tuple[HTTPSMCPTransportSession, MCPTransportResponse]:
        _raise_if_cancelled(cancellation)
        session = self.transport_factory.open(
            endpoint=endpoint,
            bearer_token=_bearer_token(authentication, secret),
            timeout_seconds=self.configuration.timeout_seconds,
        )
        try:
            _raise_if_cancelled(cancellation)
            response = session.initialize(
                timeout_seconds=self.configuration.timeout_seconds,
                max_response_bytes=self.configuration.max_response_bytes,
            )
            _raise_if_cancelled(cancellation)
            _validate_response(response, self.configuration)
            return session, response
        except Exception:
            session.close()
            raise

    def _refresh_expired_oauth_credential(
        self, authentication: MCPAuthentication, secret: str, *, force: bool = False
    ) -> str:
        if (
            authentication.authentication_method
            != "oauth_authorization_code_pkce_loopback"
        ):
            return secret
        try:
            bundle = OAuthTokenBundle.from_secret_value(secret)
            if not force and (
                bundle.expires_at is None or bundle.expires_at > self.now()
            ):
                return secret
            if (
                bundle.refresh_token is None
                or authentication.oauth_token_endpoint is None
                or authentication.oauth_client_id is None
            ):
                raise OAuthError("OAuth credential cannot be refreshed")
            refresher = self.oauth_refresher or _default_oauth_refresher()
            refreshed = refresher.refresh(
                token_endpoint=authentication.oauth_token_endpoint,
                client_id=authentication.oauth_client_id,
                refresh_token=bundle.refresh_token,
            )
            if refreshed.refresh_token is None:
                refreshed = OAuthTokenBundle(
                    access_token=refreshed.access_token,
                    refresh_token=bundle.refresh_token,
                    expires_at=refreshed.expires_at,
                )
            replacement = refreshed.secret_value()
            self.connections.replace_oauth_credential(
                authentication.authentication_id, replacement
            )
            return replacement
        except (MCPConnectionError, OAuthError, ValueError) as error:
            raise MCPConnectionClientError(
                "OAuth authentication is required"
            ) from error

    def reconnect(
        self, *, cancellation: Event | None = None
    ) -> MCPInitializedConnection:
        """Close the previous session before constructing a new generation."""

        self.close()
        return self.initialize(cancellation=cancellation)

    def list_tools(self) -> tuple[MCPDiscoveredTool, ...]:
        """Return only the current bounded remote identity/schema surface."""

        if self._session is None:
            raise MCPConnectionClientError("HTTPS MCP connection is not initialized")
        try:
            return self._session.list_tools(
                timeout_seconds=self.configuration.timeout_seconds,
                max_response_bytes=self.configuration.max_response_bytes,
            )
        except MCPConnectionClientError:
            self.close()
            raise
        except Exception as error:
            self.close()
            raise MCPConnectionClientError("HTTPS MCP tools/list failed") from error

    def call_tool(
        self, name: str, arguments: Mapping[str, object]
    ) -> Mapping[str, object]:
        """Call one reviewed tool through the current bounded HTTPS session."""

        if self._session is None:
            raise MCPConnectionClientError("HTTPS MCP connection is not initialized")
        if not isinstance(name, str) or not name:
            raise MCPConnectionClientError("MCP tool name is invalid")
        if not isinstance(arguments, Mapping):
            raise MCPConnectionClientError("MCP tool arguments are invalid")
        try:
            return self._session.call_tool(
                name=name,
                arguments=arguments,
                timeout_seconds=self.configuration.timeout_seconds,
                max_response_bytes=self.configuration.max_response_bytes,
            )
        except MCPConnectionClientError:
            self.close()
            raise
        except Exception as error:
            self.close()
            raise MCPConnectionClientError("HTTPS MCP tools/call failed") from error

    def close(self) -> None:
        """Release the current session without retaining a usable remote handle."""

        if self._session is not None:
            self._session.close()
            self._session = None


def _validate_response(
    response: MCPTransportResponse, configuration: MCPClientConfiguration
) -> None:
    if not isinstance(response, MCPTransportResponse):
        raise MCPConnectionClientError("HTTPS MCP response is invalid")
    if response.body_bytes > configuration.max_response_bytes:
        raise MCPConnectionClientError("HTTPS MCP response is too large")
    if not hmac.compare_digest(
        response.peer_certificate_sha256, configuration.peer_certificate_sha256
    ):
        raise MCPConnectionClientError("HTTPS MCP peer identity does not match")
    if not isinstance(response.protocol_version, str) or not response.protocol_version:
        raise MCPConnectionClientError("HTTPS MCP response is invalid")
    if not isinstance(response.server_name, str) or not response.server_name:
        raise MCPConnectionClientError("HTTPS MCP response is invalid")


def _bearer_token(authentication: MCPAuthentication, secret: str) -> str:
    if authentication.authentication_method == "api_token":
        return secret
    if authentication.authentication_method != "oauth_authorization_code_pkce_loopback":
        raise MCPConnectionClientError("authentication method is unsupported")
    try:
        access_token = json.loads(secret)["access_token"]
    except (TypeError, ValueError, KeyError) as error:
        raise MCPConnectionClientError("OAuth credential is invalid") from error
    if not isinstance(access_token, str) or not access_token:
        raise MCPConnectionClientError("OAuth credential is invalid")
    return access_token


def _default_oauth_refresher() -> OAuthTokenRefresher:
    from dar_workflow_server.oauth import HttpOAuthTokenExchanger

    return HttpOAuthTokenExchanger()


def _raise_if_cancelled(cancellation: Event | None) -> None:
    if cancellation is not None and cancellation.is_set():
        raise MCPConnectionClientError("HTTPS MCP initialization was cancelled")


def _opaque_id(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.startswith("v1."):
        raise MCPConnectionClientError(f"{name} must be an opaque identifier")


def _https_connection(
    *, host: str, port: int, timeout: int
) -> http.client.HTTPSConnection:
    return http.client.HTTPSConnection(
        host,
        port=port,
        timeout=timeout,
        context=ssl.create_default_context(),
    )


def _peer_certificate(connection: Any) -> bytes:
    socket = getattr(connection, "sock", None)
    if socket is None:
        raise MCPConnectionClientError("HTTPS MCP peer certificate is unavailable")
    certificate = socket.getpeercert(binary_form=True)
    if not isinstance(certificate, bytes) or not certificate:
        raise MCPConnectionClientError("HTTPS MCP peer certificate is unavailable")
    return certificate


def _initialization_result(body: bytes) -> dict[str, str]:
    try:
        value = json.loads(body.decode("utf-8"))
        result = value["result"]
        protocol_version = result["protocolVersion"]
        server_name = result["serverInfo"]["name"]
    except (KeyError, TypeError, UnicodeDecodeError, ValueError) as error:
        raise MCPConnectionClientError(
            "HTTPS MCP initialization response is invalid"
        ) from error
    if not isinstance(protocol_version, str) or not protocol_version:
        raise MCPConnectionClientError("HTTPS MCP initialization response is invalid")
    if not isinstance(server_name, str) or not server_name:
        raise MCPConnectionClientError("HTTPS MCP initialization response is invalid")
    return {"protocol_version": protocol_version, "server_name": server_name}


def _discovered_tools(body: bytes) -> tuple[MCPDiscoveredTool, ...]:
    try:
        raw_tools = json.loads(body.decode("utf-8"))["result"]["tools"]
    except (KeyError, TypeError, UnicodeDecodeError, ValueError) as error:
        raise MCPConnectionClientError(
            "HTTPS MCP tools/list response is invalid"
        ) from error
    if not isinstance(raw_tools, list):
        raise MCPConnectionClientError("HTTPS MCP tools/list response is invalid")
    tools: list[MCPDiscoveredTool] = []
    for raw_tool in raw_tools:
        if not isinstance(raw_tool, dict):
            raise MCPConnectionClientError("HTTPS MCP tools/list response is invalid")
        name = raw_tool.get("name")
        input_schema = raw_tool.get("inputSchema")
        if not isinstance(name, str) or not isinstance(input_schema, dict):
            raise MCPConnectionClientError("HTTPS MCP tools/list response is invalid")
        tools.append(MCPDiscoveredTool(name=name, input_schema=input_schema))
    return tuple(tools)


def _tool_call_result(body: bytes) -> Mapping[str, object]:
    try:
        result = json.loads(body.decode("utf-8"))["result"]
    except (KeyError, TypeError, UnicodeDecodeError, ValueError) as error:
        raise MCPConnectionClientError(
            "HTTPS MCP tools/call response is invalid"
        ) from error
    if not isinstance(result, dict):
        raise MCPConnectionClientError("HTTPS MCP tools/call response is invalid")
    return result
