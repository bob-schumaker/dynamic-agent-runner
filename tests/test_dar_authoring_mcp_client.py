"""Tests for the host-owned HTTPS MCP lifecycle client."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from pathlib import Path
from threading import Event

import pytest


from dynamic_agent_runner.workflow_host.connections import MCPConnectionControlPlane  # noqa: E402
from dynamic_agent_runner.workflow_host.mcp_client import (  # noqa: E402
    MCPClientConfiguration,
    MCPConnectionAuthenticationError,
    MCPConnectionClient,
    MCPConnectionClientError,
    MCPTransportResponse,
    HTTPSJSONRPCMCPTransportFactory,
)
from dynamic_agent_runner.workflow_host.mcp_surfaces import MCPDiscoveredTool  # noqa: E402
from dynamic_agent_runner.workflow_host.oauth import OAuthTokenBundle  # noqa: E402
from dynamic_agent_runner.workflow_host.profiles import LocalModelProfileControlPlane  # noqa: E402
from dynamic_agent_runner.workflow_host.state import PrivateStateStore  # noqa: E402


PIN = "a" * 64


class MemorySecretStore:
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

    def replace(self, reference: str, secret: str) -> None:
        self.values[reference] = secret


class FakeSession:
    def __init__(self, response: MCPTransportResponse | Exception) -> None:
        self._response = response
        self.initialize_calls: list[tuple[int, int]] = []
        self.list_tools_calls: list[tuple[int, int]] = []
        self.call_tool_calls: list[tuple[str, dict[str, object], int, int]] = []
        self.closed = False

    def initialize(
        self, *, timeout_seconds: int, max_response_bytes: int
    ) -> MCPTransportResponse:
        self.initialize_calls.append((timeout_seconds, max_response_bytes))
        if isinstance(self._response, Exception):
            raise self._response
        return self._response

    def close(self) -> None:
        self.closed = True

    def list_tools(
        self, *, timeout_seconds: int, max_response_bytes: int
    ) -> tuple[MCPDiscoveredTool, ...]:
        self.list_tools_calls.append((timeout_seconds, max_response_bytes))
        return (
            MCPDiscoveredTool(
                name="list_unread",
                input_schema={"type": "object", "properties": {}},
            ),
        )

    def call_tool(
        self,
        *,
        name: str,
        arguments: dict[str, object],
        timeout_seconds: int,
        max_response_bytes: int,
    ) -> dict[str, object]:
        self.call_tool_calls.append(
            (name, arguments, timeout_seconds, max_response_bytes)
        )
        return {"content": [{"type": "text", "text": "result"}]}


class FakeFactory:
    def __init__(self, responses: list[MCPTransportResponse | Exception]) -> None:
        self._responses = iter(responses)
        self.opens: list[tuple[str, str, int]] = []
        self.sessions: list[FakeSession] = []

    def open(
        self, *, endpoint: str, bearer_token: str, timeout_seconds: int
    ) -> FakeSession:
        self.opens.append((endpoint, bearer_token, timeout_seconds))
        session = FakeSession(next(self._responses))
        self.sessions.append(session)
        return session


class FakeOAuthRefresher:
    def __init__(self, result: OAuthTokenBundle | Exception) -> None:
        self._result = result
        self.calls: list[tuple[str, str, str]] = []

    def refresh(
        self, *, token_endpoint: str, client_id: str, refresh_token: str
    ) -> OAuthTokenBundle:
        self.calls.append((token_endpoint, client_id, refresh_token))
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def _client(
    tmp_path: Path, factory: FakeFactory
) -> tuple[MCPConnectionClient, str, str]:
    store = PrivateStateStore(tmp_path / "state")
    profiles = LocalModelProfileControlPlane(store=store)
    profile = profiles.create(
        model_id="local-model-v1",
        adapter_id="strict-local-adapter-v1",
        base_url="http://127.0.0.1:11434/v1",
        capabilities={"text_generation"},
    )
    connections = MCPConnectionControlPlane(
        store=store,
        profiles=profiles,
        secret_store=MemorySecretStore(),
    )
    connection = connections.create(
        profile_id=profile.profile_id,
        endpoint="https://mcp.example.test/v1",
        scopes={"mail.read"},
        authentication_method="api_token",
    )
    authentication = connections.configure_api_token(connection.connection_id, "token")
    client = MCPConnectionClient(
        connections=connections,
        configuration=MCPClientConfiguration(
            connection_id=connection.connection_id,
            authentication_id=authentication.authentication_id,
            peer_certificate_sha256=PIN,
            timeout_seconds=12,
            max_response_bytes=128,
        ),
        transport_factory=factory,
    )
    return client, connection.connection_id, authentication.authentication_id


def _oauth_client(
    tmp_path: Path,
    factory: FakeFactory,
    refresher: FakeOAuthRefresher,
    *,
    expires_at: datetime = datetime(2026, 8, 24, 12, 0, tzinfo=UTC),
) -> tuple[MCPConnectionClient, MemorySecretStore]:
    store = PrivateStateStore(tmp_path / "state")
    profiles = LocalModelProfileControlPlane(store=store)
    profile = profiles.create(
        model_id="local-model-v1",
        adapter_id="strict-local-adapter-v1",
        base_url="http://127.0.0.1:11434/v1",
        capabilities={"text_generation"},
    )
    secrets = MemorySecretStore()
    connections = MCPConnectionControlPlane(
        store=store,
        profiles=profiles,
        secret_store=secrets,
    )
    connection = connections.create(
        profile_id=profile.profile_id,
        endpoint="https://mcp.example.test/v1",
        scopes={"mail.read"},
        authentication_method="oauth_authorization_code_pkce_loopback",
    )
    authentication = connections.configure_oauth_token(
        connection.connection_id,
        OAuthTokenBundle(
            access_token="expired-access",
            refresh_token="refresh-token",
            expires_at=expires_at,
        ).secret_value(),
        token_endpoint="https://login.example.test/token",
        client_id="public-client-id",
    )
    client = MCPConnectionClient(
        connections=connections,
        configuration=MCPClientConfiguration(
            connection_id=connection.connection_id,
            authentication_id=authentication.authentication_id,
            peer_certificate_sha256=PIN,
            timeout_seconds=12,
            max_response_bytes=128,
        ),
        transport_factory=factory,
        oauth_refresher=refresher,
        now=lambda: datetime(2026, 8, 24, 12, 1, tzinfo=UTC),
    )
    return client, secrets


def _response(*, pin: str = PIN, body_bytes: int = 64) -> MCPTransportResponse:
    return MCPTransportResponse(
        peer_certificate_sha256=pin,
        body_bytes=body_bytes,
        protocol_version="2025-06-18",
        server_name="example-mcp",
    )


def test_client_initializes_only_after_matching_pin_and_bound_credential(
    tmp_path: Path,
) -> None:
    factory = FakeFactory([_response()])
    client, connection_id, authentication_id = _client(tmp_path, factory)

    initialized = client.initialize()

    assert initialized.connection_id == connection_id
    assert initialized.authentication_id == authentication_id
    assert initialized.generation == 1
    assert initialized.protocol_version == "2025-06-18"
    assert factory.opens == [("https://mcp.example.test/v1", "token", 12)]
    assert factory.sessions[0].initialize_calls == [(12, 128)]


def test_client_closes_and_fails_closed_on_peer_pin_or_response_bound_failure(
    tmp_path: Path,
) -> None:
    factory = FakeFactory([_response(pin="b" * 64), _response(body_bytes=129)])
    client, _, _ = _client(tmp_path, factory)

    with pytest.raises(MCPConnectionClientError, match="peer identity"):
        client.initialize()
    with pytest.raises(MCPConnectionClientError, match="response is too large"):
        client.initialize()

    assert [session.closed for session in factory.sessions] == [True, True]


def test_client_honors_cancellation_and_reconnects_with_a_new_generation(
    tmp_path: Path,
) -> None:
    factory = FakeFactory([_response(), _response()])
    client, _, _ = _client(tmp_path, factory)
    cancelled = Event()
    cancelled.set()

    with pytest.raises(MCPConnectionClientError, match="cancelled"):
        client.initialize(cancellation=cancelled)
    assert factory.opens == []

    first = client.initialize()
    second = client.reconnect()

    assert first.generation == 1
    assert second.generation == 2
    assert factory.sessions[0].closed is True
    client.close()
    assert factory.sessions[1].closed is True


def test_client_refreshes_expired_oauth_credential_before_transport_setup(
    tmp_path: Path,
) -> None:
    factory = FakeFactory([_response()])
    refresher = FakeOAuthRefresher(
        OAuthTokenBundle(
            access_token="refreshed-access",
            expires_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
        )
    )
    client, secrets = _oauth_client(tmp_path, factory, refresher)

    client.initialize()

    assert refresher.calls == [
        ("https://login.example.test/token", "public-client-id", "refresh-token")
    ]
    assert factory.opens == [("https://mcp.example.test/v1", "refreshed-access", 12)]
    assert json.loads(next(iter(secrets.values.values()))) == {
        "access_token": "refreshed-access",
        "expires_at": "2026-08-24T13:00:00+00:00",
        "refresh_token": "refresh-token",
    }


def test_client_refreshes_an_expired_oauth_credential_on_reconnect(
    tmp_path: Path,
) -> None:
    factory = FakeFactory([_response(), _response()])
    refresher = FakeOAuthRefresher(
        OAuthTokenBundle(
            access_token="refreshed-access",
            expires_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
        )
    )
    client, secrets = _oauth_client(
        tmp_path,
        factory,
        refresher,
        expires_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
    )
    client.initialize()
    credential_ref = next(iter(secrets.values))
    secrets.values[credential_ref] = OAuthTokenBundle(
        access_token="expired-access",
        refresh_token="refresh-token",
        expires_at=datetime(2026, 8, 24, 12, 0, tzinfo=UTC),
    ).secret_value()

    client.reconnect()

    assert factory.opens == [
        ("https://mcp.example.test/v1", "expired-access", 12),
        ("https://mcp.example.test/v1", "refreshed-access", 12),
    ]
    assert len(refresher.calls) == 1
    assert factory.sessions[0].closed is True


def test_client_refreshes_once_after_oauth_setup_is_rejected(
    tmp_path: Path,
) -> None:
    factory = FakeFactory([MCPConnectionAuthenticationError("rejected"), _response()])
    refresher = FakeOAuthRefresher(
        OAuthTokenBundle(
            access_token="refreshed-access",
            expires_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
        )
    )
    client, _ = _oauth_client(
        tmp_path,
        factory,
        refresher,
        expires_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
    )

    client.initialize()

    assert factory.opens == [
        ("https://mcp.example.test/v1", "expired-access", 12),
        ("https://mcp.example.test/v1", "refreshed-access", 12),
    ]
    assert refresher.calls == [
        ("https://login.example.test/token", "public-client-id", "refresh-token")
    ]
    assert factory.sessions[0].closed is True


def test_client_does_not_retry_oauth_setup_more_than_once(
    tmp_path: Path,
) -> None:
    factory = FakeFactory(
        [
            MCPConnectionAuthenticationError("rejected"),
            MCPConnectionAuthenticationError("rejected"),
        ]
    )
    refresher = FakeOAuthRefresher(
        OAuthTokenBundle(
            access_token="refreshed-access",
            expires_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
        )
    )
    client, _ = _oauth_client(
        tmp_path,
        factory,
        refresher,
        expires_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
    )

    with pytest.raises(MCPConnectionClientError, match="authentication is required"):
        client.initialize()

    assert len(factory.opens) == 2
    assert len(refresher.calls) == 1


def test_client_requires_human_authentication_when_oauth_refresh_fails(
    tmp_path: Path,
) -> None:
    factory = FakeFactory([_response()])
    refresher = FakeOAuthRefresher(ValueError("refresh rejected"))
    client, _ = _oauth_client(tmp_path, factory, refresher)

    with pytest.raises(MCPConnectionClientError, match="authentication is required"):
        client.initialize()

    assert factory.opens == []


def test_client_lists_only_bounded_schema_surface_after_initialization(
    tmp_path: Path,
) -> None:
    factory = FakeFactory([_response()])
    client, _, _ = _client(tmp_path, factory)

    with pytest.raises(MCPConnectionClientError, match="not initialized"):
        client.list_tools()
    client.initialize()

    assert client.list_tools() == (
        MCPDiscoveredTool(
            name="list_unread",
            input_schema={"type": "object", "properties": {}},
        ),
    )
    assert factory.sessions[0].list_tools_calls == [(12, 128)]


def test_client_calls_a_tool_only_through_an_initialized_bounded_session(
    tmp_path: Path,
) -> None:
    factory = FakeFactory([_response()])
    client, _, _ = _client(tmp_path, factory)

    with pytest.raises(MCPConnectionClientError, match="not initialized"):
        client.call_tool("list_unread", {"folder": "inbox"})
    client.initialize()

    assert client.call_tool("list_unread", {"folder": "inbox"}) == {
        "content": [{"type": "text", "text": "result"}]
    }
    assert factory.sessions[0].call_tool_calls == [
        ("list_unread", {"folder": "inbox"}, 12, 128)
    ]


def test_client_fails_closed_when_configured_https_startup_is_unavailable(
    tmp_path: Path,
) -> None:
    class FailingFactory:
        def open(self, **_kwargs: object) -> FakeSession:
            raise RuntimeError("unavailable")

    factory = FailingFactory()
    store = PrivateStateStore(tmp_path / "state")
    profiles = LocalModelProfileControlPlane(store=store)
    profile = profiles.create(
        model_id="local-model-v1",
        adapter_id="strict-local-adapter-v1",
        base_url="http://127.0.0.1:11434/v1",
        capabilities={"text_generation"},
    )
    connections = MCPConnectionControlPlane(
        store=store,
        profiles=profiles,
        secret_store=MemorySecretStore(),
    )
    connection = connections.create(
        profile_id=profile.profile_id,
        endpoint="https://mcp.example.test/v1",
        scopes={"mail.read"},
        authentication_method="api_token",
    )
    authentication = connections.configure_api_token(connection.connection_id, "token")
    client = MCPConnectionClient(
        connections=connections,
        configuration=MCPClientConfiguration(
            connection_id=connection.connection_id,
            authentication_id=authentication.authentication_id,
            peer_certificate_sha256=PIN,
            timeout_seconds=12,
            max_response_bytes=128,
        ),
        transport_factory=factory,
    )

    with pytest.raises(MCPConnectionClientError, match="initialization failed"):
        client.initialize()


class FakeHTTPResponse:
    def __init__(self, body: bytes, *, status: int = 200) -> None:
        self._body = body
        self.status = status

    def read(self, limit: int) -> bytes:
        return self._body[:limit]


class FakeHTTPSConnection:
    def __init__(self, body: bytes, certificate: bytes) -> None:
        self._response = FakeHTTPResponse(body)
        self.sock = SimpleNamespace(getpeercert=lambda *, binary_form: certificate)
        self.requests: list[tuple[str, str, bytes, dict[str, str]]] = []
        self.closed = False

    def request(
        self, method: str, path: str, body: bytes, headers: dict[str, str]
    ) -> None:
        self.requests.append((method, path, body, headers))

    def getresponse(self) -> FakeHTTPResponse:
        return self._response

    def close(self) -> None:
        self.closed = True


def test_https_json_rpc_transport_hashes_peer_certificate_and_bounds_body() -> None:
    certificate = b"peer-certificate"
    body = (
        b'{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-06-18",'
        b'"serverInfo":{"name":"example-mcp"}}}'
    )
    connection = FakeHTTPSConnection(body, certificate)
    factory = HTTPSJSONRPCMCPTransportFactory(
        connection_factory=lambda **_kwargs: connection
    )

    session = factory.open(
        endpoint="https://mcp.example.test/v1",
        bearer_token="token-not-in-result",
        timeout_seconds=12,
    )
    response = session.initialize(timeout_seconds=12, max_response_bytes=512)

    assert (
        response.peer_certificate_sha256
        == __import__("hashlib").sha256(certificate).hexdigest()
    )
    assert response.body_bytes == len(body)
    assert response.protocol_version == "2025-06-18"
    assert response.server_name == "example-mcp"
    assert connection.requests[0][0:2] == ("POST", "/v1")
    assert connection.requests[0][3]["Authorization"] == "Bearer token-not-in-result"
    assert b"initialize" in connection.requests[0][2]
    session.close()
    assert connection.closed is True


def test_https_json_rpc_transport_marks_setup_authentication_rejection() -> None:
    connection = FakeHTTPSConnection(b"unauthorized", b"peer-certificate")
    connection._response = FakeHTTPResponse(b"unauthorized", status=401)
    session = HTTPSJSONRPCMCPTransportFactory(
        connection_factory=lambda **_kwargs: connection
    ).open(
        endpoint="https://mcp.example.test/v1",
        bearer_token="token",
        timeout_seconds=12,
    )

    with pytest.raises(MCPConnectionAuthenticationError, match="authentication"):
        session.initialize(timeout_seconds=12, max_response_bytes=512)


def test_https_json_rpc_transport_retrieves_tools_list_only_after_initialize() -> None:
    certificate = b"peer-certificate"
    initialized = (
        b'{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-06-18",'
        b'"serverInfo":{"name":"example-mcp"}}}'
    )
    tools = (
        b'{"jsonrpc":"2.0","id":2,"result":{"tools":[{"name":"list_unread",'
        b'"inputSchema":{"type":"object","properties":{}}}]}}'
    )

    class SequentialConnection(FakeHTTPSConnection):
        def __init__(self) -> None:
            super().__init__(initialized, certificate)
            self._responses = [FakeHTTPResponse(initialized), FakeHTTPResponse(tools)]

        def getresponse(self) -> FakeHTTPResponse:
            return self._responses.pop(0)

    connection = SequentialConnection()
    session = HTTPSJSONRPCMCPTransportFactory(
        connection_factory=lambda **_kwargs: connection
    ).open(
        endpoint="https://mcp.example.test/v1",
        bearer_token="token",
        timeout_seconds=12,
    )

    session.initialize(timeout_seconds=12, max_response_bytes=512)

    assert session.list_tools(timeout_seconds=12, max_response_bytes=512) == (
        MCPDiscoveredTool(
            name="list_unread",
            input_schema={"type": "object", "properties": {}},
        ),
    )
    assert b"tools/list" in connection.requests[1][2]


def test_https_json_rpc_transport_calls_one_named_tool_after_initialize() -> None:
    certificate = b"peer-certificate"
    initialized = (
        b'{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-06-18",'
        b'"serverInfo":{"name":"example-mcp"}}}'
    )
    result = (
        b'{"jsonrpc":"2.0","id":3,"result":{"content":[{"type":"text","text":"ok"}]}}'
    )

    class SequentialConnection(FakeHTTPSConnection):
        def __init__(self) -> None:
            super().__init__(initialized, certificate)
            self._responses = [FakeHTTPResponse(initialized), FakeHTTPResponse(result)]

        def getresponse(self) -> FakeHTTPResponse:
            return self._responses.pop(0)

    connection = SequentialConnection()
    session = HTTPSJSONRPCMCPTransportFactory(
        connection_factory=lambda **_kwargs: connection
    ).open(
        endpoint="https://mcp.example.test/v1",
        bearer_token="token",
        timeout_seconds=12,
    )
    session.initialize(timeout_seconds=12, max_response_bytes=512)

    assert session.call_tool(
        name="list_unread",
        arguments={"folder": "inbox"},
        timeout_seconds=12,
        max_response_bytes=512,
    ) == {"content": [{"type": "text", "text": "ok"}]}
    assert b"tools/call" in connection.requests[1][2]
    assert b'"name":"list_unread"' in connection.requests[1][2]
