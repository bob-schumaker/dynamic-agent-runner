"""Tests for the human-only OAuth PKCE loopback control plane."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest


from dynamic_agent_runner.workflow_host.connections import (  # noqa: E402
    MCPConnectionControlPlane,
    MCPConnectionError,
)
from dynamic_agent_runner.workflow_host.oauth import (  # noqa: E402
    HttpOAuthTokenExchanger,
    OAuthError,
    OAuthAuthorizationService,
    OAuthCallback,
    OAuthClientConfiguration,
    OAuthTokenBundle,
    _callback_from_query,
    _callback_success_response,
)
from dynamic_agent_runner.workflow_host.profiles import LocalModelProfileControlPlane  # noqa: E402
from dynamic_agent_runner.workflow_host.state import PrivateStateStore  # noqa: E402


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


class FakeReceiver:
    def __init__(self, callback: OAuthCallback, events: list[str]) -> None:
        self.redirect_uri = "http://127.0.0.1:49612/oauth/callback"
        self._callback = callback
        self._events = events

    def wait_for_callback(self, timeout_seconds: int) -> OAuthCallback:
        self._events.append("callback")
        return self._callback

    def close(self) -> None:
        self._events.append("closed")


class FakeReceiverFactory:
    def __init__(self, callback: OAuthCallback, events: list[str]) -> None:
        self._callback = callback
        self._events = events
        self.receiver: FakeReceiver | None = None
        self.callback_paths: list[str] = []

    def open(self, *, callback_path: str = "/oauth/callback") -> FakeReceiver:
        self.callback_paths.append(callback_path)
        self._events.append("listener-open")
        self.receiver = FakeReceiver(self._callback, self._events)
        self.receiver.redirect_uri = f"http://127.0.0.1:49612{callback_path}"
        return self.receiver


class FakeResourceReceiverFactory(FakeReceiverFactory):
    def __init__(
        self, callback: OAuthCallback, events: list[str], redirect_uri: str
    ) -> None:
        super().__init__(callback, events)
        self._redirect_uri = redirect_uri

    def open(self, *, callback_path: str = "/oauth/callback") -> FakeReceiver:
        receiver = super().open(callback_path=callback_path)
        receiver.redirect_uri = self._redirect_uri
        return receiver


class FakeBrowser:
    def __init__(self, events: list[str]) -> None:
        self._events = events
        self.urls: list[str] = []

    def open(self, url: str) -> None:
        self._events.append("browser-open")
        self.urls.append(url)


class FakeExchanger:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, str, str]] = []

    def exchange(
        self,
        *,
        token_endpoint: str,
        client_id: str,
        code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> OAuthTokenBundle:
        self.calls.append(
            (token_endpoint, client_id, code, redirect_uri, code_verifier)
        )
        return OAuthTokenBundle(access_token="access-token", refresh_token="refresh")


class ResourceFakeExchanger:
    def __init__(self) -> None:
        self.resources: list[str | None] = []

    def exchange(
        self,
        *,
        token_endpoint: str,
        client_id: str,
        code: str,
        redirect_uri: str,
        code_verifier: str,
        resource: str | None = None,
    ) -> OAuthTokenBundle:
        self.resources.append(resource)
        return OAuthTokenBundle(access_token="access-token", refresh_token="refresh")


def _control(
    tmp_path: Path,
) -> tuple[MCPConnectionControlPlane, str, MemorySecretStore]:
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
        authentication_method="oauth_authorization_code_pkce_loopback",
    )
    return control, connection.connection_id, secrets


def test_oauth_binds_listener_before_browser_and_stores_only_token_reference(
    tmp_path: Path,
) -> None:
    control, connection_id, secrets = _control(tmp_path)
    events: list[str] = []
    callback = OAuthCallback(code="one-time-code", state="expected-state")
    receivers = FakeReceiverFactory(callback, events)
    browser = FakeBrowser(events)
    exchanger = FakeExchanger()
    service = OAuthAuthorizationService(
        connections=control,
        receiver_factory=receivers,
        browser=browser,
        exchanger=exchanger,
        state_factory=lambda: "expected-state",
        verifier_factory=lambda: "code-verifier",
    )

    authentication = service.authorize(
        connection_id,
        configuration=OAuthClientConfiguration(
            authorization_endpoint="https://login.example.test/authorize",
            token_endpoint="https://login.example.test/token",
            client_id="public-client-id",
        ),
    )

    assert events == ["listener-open", "browser-open", "callback", "closed"]
    query = parse_qs(urlsplit(browser.urls[0]).query)
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["public-client-id"]
    assert query["redirect_uri"] == ["http://127.0.0.1:49612/oauth/callback"]
    assert query["scope"] == ["mail.read"]
    assert query["state"] == ["expected-state"]
    assert query["code_challenge_method"] == ["S256"]
    assert exchanger.calls == [
        (
            "https://login.example.test/token",
            "public-client-id",
            "one-time-code",
            "http://127.0.0.1:49612/oauth/callback",
            "code-verifier",
        )
    ]
    assert authentication.authentication_status == "authenticated"
    assert authentication.oauth_token_endpoint == "https://login.example.test/token"
    assert authentication.oauth_client_id == "public-client-id"
    assert secrets.values == {
        "mcp-secret-v1-1": '{"access_token":"access-token","refresh_token":"refresh"}'
    }
    state_text = (tmp_path / "state" / "records.json").read_text(encoding="utf-8")
    assert "one-time-code" not in state_text
    assert "access-token" not in state_text
    assert "code-verifier" not in state_text


def test_loopback_callback_shows_a_redacted_completion_page() -> None:
    body, headers = _callback_success_response()
    text = body.decode("utf-8")

    assert "OAuth token has been received" in text
    assert "close this window" in text
    assert "return to the terminal" in text
    assert "one-time-code" not in text
    assert "expected-state" not in text
    assert headers == {
        "Cache-Control": "no-store",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
        "Content-Type": "text/html; charset=utf-8",
        "X-Content-Type-Options": "nosniff",
    }


def test_oauth_credential_replacement_preserves_its_connection_binding(
    tmp_path: Path,
) -> None:
    control, connection_id, secrets = _control(tmp_path)
    authentication = control.configure_oauth_token(
        connection_id,
        '{"access_token":"old","refresh_token":"refresh"}',
        token_endpoint="https://login.example.test/token",
        client_id="public-client-id",
    )

    control.replace_oauth_credential(
        authentication.authentication_id,
        '{"access_token":"new","refresh_token":"refresh"}',
    )
    reloaded, secret = control.credential_for_authentication(
        authentication.authentication_id
    )

    assert reloaded == authentication
    assert secret == '{"access_token":"new","refresh_token":"refresh"}'
    assert len(secrets.values) == 1


def test_oauth_token_bundle_serializes_an_optional_utc_expiry() -> None:
    expiry = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)

    bundle = OAuthTokenBundle(access_token="access", expires_at=expiry)

    assert json.loads(bundle.secret_value()) == {
        "access_token": "access",
        "expires_at": "2026-08-24T12:00:00+00:00",
    }


def test_http_oauth_exchanger_uses_refresh_token_grant() -> None:
    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def geturl(self) -> str:
            return "https://login.example.test/token"

        def read(self, _limit: int) -> bytes:
            return b'{"access_token":"refreshed","expires_in":60}'

    requests = []

    class FakeOpener:
        def open(self, request: object, *, timeout: int) -> FakeResponse:
            requests.append((request, timeout))
            return FakeResponse()

    bundle = HttpOAuthTokenExchanger(opener=FakeOpener()).refresh(
        token_endpoint="https://login.example.test/token",
        client_id="public-client-id",
        refresh_token="refresh-token",
        resource="https://mcp.example.test/v1",
    )

    request, timeout = requests[0]
    assert timeout == 30
    assert request.full_url == "https://login.example.test/token"
    assert parse_qs(request.data.decode("ascii")) == {
        "grant_type": ["refresh_token"],
        "client_id": ["public-client-id"],
        "refresh_token": ["refresh-token"],
        "resource": ["https://mcp.example.test/v1"],
    }
    assert bundle.access_token == "refreshed"
    assert bundle.refresh_token is None
    assert bundle.expires_at is not None


def test_http_oauth_exchanger_binds_resource_to_the_code_exchange() -> None:
    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def geturl(self) -> str:
            return "https://login.example.test/token"

        def read(self, _limit: int) -> bytes:
            return b'{"access_token":"access"}'

    requests = []

    class FakeOpener:
        def open(self, request: object, *, timeout: int) -> FakeResponse:
            requests.append((request, timeout))
            return FakeResponse()

    HttpOAuthTokenExchanger(opener=FakeOpener()).exchange(
        token_endpoint="https://login.example.test/token",
        client_id="public-client-id",
        code="one-time-code",
        redirect_uri="http://127.0.0.1:49612/oauth/callback/issuer-bound",
        code_verifier="verifier",
        resource="https://mcp.example.test/v1",
    )

    request, timeout = requests[0]
    assert timeout == 30
    assert parse_qs(request.data.decode("ascii")) == {
        "grant_type": ["authorization_code"],
        "client_id": ["public-client-id"],
        "code": ["one-time-code"],
        "redirect_uri": ["http://127.0.0.1:49612/oauth/callback/issuer-bound"],
        "code_verifier": ["verifier"],
        "resource": ["https://mcp.example.test/v1"],
    }


@pytest.mark.parametrize("limit", [0, 65_537])
def test_http_oauth_exchanger_rejects_an_unbounded_response_limit(limit: int) -> None:
    with pytest.raises(OAuthError, match="response limit is invalid"):
        HttpOAuthTokenExchanger(max_response_bytes=limit)


@pytest.mark.parametrize("grant", ["exchange", "refresh"])
@pytest.mark.parametrize(
    ("response_url", "body"),
    [
        ("https://redirect.example.test/token", b'{"access_token":"access"}'),
        ("https://login.example.test/token", b"x" * 32_769),
    ],
)
def test_http_oauth_exchanger_rejects_redirected_or_oversized_responses(
    grant: str, response_url: str, body: bytes
) -> None:
    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def geturl(self) -> str:
            return response_url

        def read(self, _limit: int) -> bytes:
            return body

    class FakeOpener:
        def open(self, _request: object, *, timeout: int) -> FakeResponse:
            assert timeout == 30
            return FakeResponse()

    exchanger = HttpOAuthTokenExchanger(opener=FakeOpener())
    arguments = {
        "token_endpoint": "https://login.example.test/token",
        "client_id": "public-client-id",
        "resource": "https://mcp.example.test/v1",
    }

    with pytest.raises(OAuthError):
        if grant == "exchange":
            exchanger.exchange(
                **arguments,
                code="one-time-code",
                redirect_uri="http://127.0.0.1:49612/oauth/callback",
                code_verifier="verifier",
            )
        else:
            exchanger.refresh(**arguments, refresh_token="refresh-token")


def test_oauth_rejects_bad_callback_state_without_exchanging_the_code(
    tmp_path: Path,
) -> None:
    control, connection_id, secrets = _control(tmp_path)
    receivers = FakeReceiverFactory(
        OAuthCallback(code="one-time-code", state="wrong-state"), []
    )
    exchanger = FakeExchanger()
    service = OAuthAuthorizationService(
        connections=control,
        receiver_factory=receivers,
        browser=FakeBrowser([]),
        exchanger=exchanger,
        state_factory=lambda: "expected-state",
        verifier_factory=lambda: "code-verifier",
    )

    with pytest.raises(MCPConnectionError, match="OAuth callback is invalid"):
        service.authorize(
            connection_id,
            configuration=OAuthClientConfiguration(
                authorization_endpoint="https://login.example.test/authorize",
                token_endpoint="https://login.example.test/token",
                client_id="public-client-id",
            ),
        )

    assert exchanger.calls == []
    assert secrets.values == {}


def test_discovered_oauth_binds_resource_issuer_and_registered_loopback_path(
    tmp_path: Path,
) -> None:
    control, connection_id, _ = _control(tmp_path)
    events: list[str] = []
    redirect_template = "http://localhost/oauth/callback/issuer-bound"
    receivers = FakeResourceReceiverFactory(
        OAuthCallback(
            code="one-time-code",
            state="expected-state",
        ),
        events,
        "http://127.0.0.1:49612/oauth/callback/issuer-bound",
    )
    browser = FakeBrowser(events)
    exchanger = ResourceFakeExchanger()
    service = OAuthAuthorizationService(
        connections=control,
        receiver_factory=receivers,
        browser=browser,
        exchanger=exchanger,
        state_factory=lambda: "expected-state",
        verifier_factory=lambda: "code-verifier",
    )

    authentication = service.authorize(
        connection_id,
        configuration=OAuthClientConfiguration(
            authorization_endpoint="https://login.example.test/authorize",
            token_endpoint="https://login.example.test/token",
            client_id="public-client-id",
            resource="https://mcp.example.test/v1",
            issuer="https://login.example.test/tenant",
            registered_redirect_template=redirect_template,
            registration_id="v1.registration.signature",
            scope_is_omitted=True,
        ),
    )

    assert parse_qs(urlsplit(browser.urls[0]).query)["resource"] == [
        "https://mcp.example.test/v1"
    ]
    assert "scope" not in parse_qs(urlsplit(browser.urls[0]).query)
    assert exchanger.resources == ["https://mcp.example.test/v1"]
    assert authentication.oauth_resource == "https://mcp.example.test/v1"
    assert authentication.oauth_issuer == "https://login.example.test/tenant"
    assert authentication.oauth_registration_id == "v1.registration.signature"
    assert receivers.callback_paths == ["/oauth/callback/issuer-bound"]


def test_discovered_oauth_rejects_a_callback_without_its_expected_issuer(
    tmp_path: Path,
) -> None:
    control, connection_id, _ = _control(tmp_path)
    receivers = FakeResourceReceiverFactory(
        OAuthCallback(code="one-time-code", state="expected-state"),
        [],
        "http://127.0.0.1:49612/oauth/callback/issuer-bound",
    )
    exchanger = ResourceFakeExchanger()
    service = OAuthAuthorizationService(
        connections=control,
        receiver_factory=receivers,
        browser=FakeBrowser([]),
        exchanger=exchanger,
        state_factory=lambda: "expected-state",
        verifier_factory=lambda: "code-verifier",
    )

    with pytest.raises(MCPConnectionError, match="OAuth callback is invalid"):
        service.authorize(
            connection_id,
            configuration=OAuthClientConfiguration(
                authorization_endpoint="https://login.example.test/authorize",
                token_endpoint="https://login.example.test/token",
                client_id="public-client-id",
                resource="https://mcp.example.test/v1",
                issuer="https://login.example.test/tenant",
                registered_redirect_template="http://localhost/oauth/callback/issuer-bound",
                registration_id="v1.registration.signature",
                require_issuer_callback=True,
            ),
        )

    assert exchanger.resources == []


@pytest.mark.parametrize(
    ("path", "query"),
    [
        ("/wrong", "code=one&state=expected"),
        ("/oauth/callback", "code=one&state=expected&extra=value"),
        ("/oauth/callback", "code=one&code=two&state=expected"),
        ("/oauth/callback", "code=&state=expected"),
    ],
)
def test_loopback_callback_requires_the_exact_path_and_one_code_and_state(
    path: str, query: str
) -> None:
    assert _callback_from_query(path, query, "/oauth/callback") is None


def test_loopback_callback_retains_an_optional_single_issuer() -> None:
    assert _callback_from_query(
        "/oauth/callback",
        "code=one&state=expected&iss=https%3A%2F%2Flogin.example.test%2Ftenant",
        "/oauth/callback",
    ) == OAuthCallback(
        code="one", state="expected", issuer="https://login.example.test/tenant"
    )
