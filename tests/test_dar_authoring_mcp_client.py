"""Tests for the host-owned HTTPS MCP lifecycle client."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from pathlib import Path
from threading import Event

import pytest


PLUGIN_SERVER_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "server"
sys.path.insert(0, str(PLUGIN_SERVER_ROOT))

from dar_workflow_server.connections import MCPConnectionControlPlane  # noqa: E402
from dar_workflow_server.mcp_client import (  # noqa: E402
    MCPClientConfiguration,
    MCPConnectionClient,
    MCPConnectionClientError,
    MCPTransportResponse,
    HTTPSJSONRPCMCPTransportFactory,
)
from dar_workflow_server.mcp_surfaces import MCPDiscoveredTool  # noqa: E402
from dar_workflow_server.profiles import LocalModelProfileControlPlane  # noqa: E402
from dar_workflow_server.state import PrivateStateStore  # noqa: E402


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


class FakeSession:
    def __init__(self, response: MCPTransportResponse) -> None:
        self._response = response
        self.initialize_calls: list[tuple[int, int]] = []
        self.list_tools_calls: list[tuple[int, int]] = []
        self.closed = False

    def initialize(
        self, *, timeout_seconds: int, max_response_bytes: int
    ) -> MCPTransportResponse:
        self.initialize_calls.append((timeout_seconds, max_response_bytes))
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


class FakeFactory:
    def __init__(self, responses: list[MCPTransportResponse]) -> None:
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
    status = 200

    def __init__(self, body: bytes) -> None:
        self._body = body

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
