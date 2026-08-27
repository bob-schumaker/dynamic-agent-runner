"""Human-only OAuth authorization-code PKCE loopback handling."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import queue
import secrets
import time
import webbrowser
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable, Protocol
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from dynamic_agent_runner.workflow_host.connections import (
    MCPAuthentication,
    MCPConnectionControlPlane,
    MCPConnectionError,
)


class OAuthError(ValueError):
    """Raised when a human OAuth authorization flow cannot complete safely."""


@dataclass(frozen=True)
class OAuthClientConfiguration:
    """Public-client endpoints supplied only to the local control plane."""

    authorization_endpoint: str
    token_endpoint: str
    client_id: str
    resource: str | None = None
    issuer: str | None = None
    registered_redirect_template: str | None = None
    registration_id: str | None = None
    persistent_reconnect: bool = False
    scope_is_omitted: bool = False
    require_issuer_callback: bool = False

    def __post_init__(self) -> None:
        _https_url(self.authorization_endpoint, "authorization_endpoint")
        _https_url(self.token_endpoint, "token_endpoint")
        if not isinstance(self.client_id, str) or not self.client_id:
            raise OAuthError("client_id must be a non-empty string")
        discovered_values = (
            self.resource,
            self.issuer,
            self.registered_redirect_template,
            self.registration_id,
        )
        if any(value is not None for value in discovered_values) and any(
            value is None for value in discovered_values
        ):
            raise OAuthError("discovered OAuth configuration is incomplete")
        if self.resource is not None:
            _https_url(self.resource, "resource")
            _https_url(self.issuer, "issuer")
            _registered_redirect_template(self.registered_redirect_template)
            if not isinstance(
                self.registration_id, str
            ) or not self.registration_id.startswith("v1."):
                raise OAuthError("registration_id is invalid")
            if not isinstance(self.persistent_reconnect, bool):
                raise OAuthError("persistent_reconnect is invalid")
            if not isinstance(self.scope_is_omitted, bool):
                raise OAuthError("scope_is_omitted is invalid")
            if not isinstance(self.require_issuer_callback, bool):
                raise OAuthError("require_issuer_callback is invalid")
        elif (
            self.persistent_reconnect
            or self.scope_is_omitted
            or self.require_issuer_callback
        ):
            raise OAuthError("discovered OAuth configuration is invalid")


@dataclass(frozen=True)
class OAuthCallback:
    """Transient authorization-code callback, never persisted or returned."""

    code: str = field(repr=False)
    state: str = field(repr=False)
    issuer: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class OAuthTokenBundle:
    """Transient OAuth tokens that are serialized directly into secret storage."""

    access_token: str = field(repr=False)
    refresh_token: str | None = field(default=None, repr=False)
    expires_at: datetime | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.access_token, str) or not self.access_token:
            raise OAuthError("token exchange did not return an access token")
        if self.refresh_token is not None and (
            not isinstance(self.refresh_token, str) or not self.refresh_token
        ):
            raise OAuthError("token exchange returned an invalid refresh token")
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise OAuthError("token exchange returned an invalid expiry")

    def secret_value(self) -> str:
        value: dict[str, str] = {"access_token": self.access_token}
        if self.refresh_token is not None:
            value["refresh_token"] = self.refresh_token
        if self.expires_at is not None:
            value["expires_at"] = self.expires_at.astimezone(UTC).isoformat()
        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_secret_value(cls, value: str) -> OAuthTokenBundle:
        """Parse a token bundle retrieved only from host-owned secret storage."""

        try:
            payload = json.loads(value)
            expires_at = _stored_expiry(payload.get("expires_at"))
            return cls(
                access_token=payload["access_token"],
                refresh_token=payload.get("refresh_token"),
                expires_at=expires_at,
            )
        except (AttributeError, KeyError, TypeError, ValueError, OAuthError) as error:
            raise OAuthError("OAuth credential is invalid") from error


class OAuthCallbackReceiver(Protocol):
    """A listener that is already bound before the external browser opens."""

    @property
    def redirect_uri(self) -> str:
        """Return the exact bound loopback callback URI."""

    def wait_for_callback(self, timeout_seconds: int) -> OAuthCallback:
        """Return one valid-shape callback or raise after a bounded wait."""

    def close(self) -> None:
        """Release the listener regardless of OAuth outcome."""


class OAuthCallbackReceiverFactory(Protocol):
    def open(self, *, callback_path: str = "/oauth/callback") -> OAuthCallbackReceiver:
        """Bind and return one loopback callback receiver."""


class OAuthBrowser(Protocol):
    def open(self, url: str) -> None:
        """Open the authorization request in the user's external browser."""


class OAuthTokenExchanger(Protocol):
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
        """Exchange one code without exposing token material to callers."""


class OAuthTokenRefresher(Protocol):
    """Refresh an OAuth credential without user interaction."""

    def refresh(
        self,
        *,
        token_endpoint: str,
        client_id: str,
        refresh_token: str,
        resource: str | None = None,
    ) -> OAuthTokenBundle:
        """Refresh one token bundle without exposing token material to callers."""


class ExternalOAuthBrowser:
    """Open an authorization URL through the system external browser."""

    def open(self, url: str) -> None:
        try:
            opened = webbrowser.open(url, new=1)
        except Exception as error:
            raise OAuthError("external browser could not be opened") from error
        if not opened:
            raise OAuthError("external browser could not be opened")


class LoopbackOAuthCallbackReceiver:
    """A single-use `127.0.0.1` callback receiver with an exact path."""

    _CALLBACK_PATH = "/oauth/callback"

    def __init__(self, *, callback_path: str = _CALLBACK_PATH) -> None:
        if not isinstance(callback_path, str) or not callback_path.startswith(
            "/oauth/callback"
        ):
            raise OAuthError("OAuth callback path is invalid")
        callbacks: queue.Queue[OAuthCallback] = queue.Queue(maxsize=1)

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                parsed = urlsplit(self.path)
                callback = _callback_from_query(
                    parsed.path, parsed.query, callback_path
                )
                if callback is None:
                    self.send_response(400)
                    self.end_headers()
                    return
                try:
                    callbacks.put_nowait(callback)
                except queue.Full:
                    self.send_response(409)
                    self.end_headers()
                    return
                body, headers = _callback_success_response()
                self.send_response(200)
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return

        self._callbacks = callbacks
        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        port = self._server.server_address[1]
        self._redirect_uri = f"http://127.0.0.1:{port}{callback_path}"

    @property
    def redirect_uri(self) -> str:
        return self._redirect_uri

    def wait_for_callback(self, timeout_seconds: int) -> OAuthCallback:
        if not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
            raise OAuthError("OAuth callback timeout must be positive")
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            self._server.timeout = max(0.01, deadline - time.monotonic())
            self._server.handle_request()
            try:
                return self._callbacks.get_nowait()
            except queue.Empty:
                continue
        raise OAuthError("OAuth callback timed out")

    def close(self) -> None:
        self._server.server_close()


class LoopbackOAuthCallbackReceiverFactory:
    def open(
        self, *, callback_path: str = "/oauth/callback"
    ) -> LoopbackOAuthCallbackReceiver:
        return LoopbackOAuthCallbackReceiver(callback_path=callback_path)


def _callback_success_response() -> tuple[bytes, dict[str, str]]:
    """Return the static, non-cacheable browser acknowledgement for a callback."""

    body = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        "<title>OAuth authorization complete</title></head><body>"
        "<p>The OAuth token has been received. You may now close this window "
        "and return to the terminal.</p></body></html>"
    ).encode("utf-8")
    return body, {
        "Cache-Control": "no-store",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
        "Content-Type": "text/html; charset=utf-8",
        "X-Content-Type-Options": "nosniff",
    }


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


class HttpOAuthTokenExchanger:
    """Exchange a public-client authorization code over HTTPS."""

    def __init__(
        self, *, opener: object | None = None, max_response_bytes: int = 32_768
    ):
        if (
            not isinstance(max_response_bytes, int)
            or not 0 < max_response_bytes <= 65_536
        ):
            raise OAuthError("OAuth token response limit is invalid")
        self._opener = opener or build_opener(_NoRedirectHandler())
        self._max_response_bytes = max_response_bytes

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
        form = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        }
        if resource is not None:
            form["resource"] = resource
        try:
            payload = self._post_form(token_endpoint, form)
            return _token_bundle_from_response(payload)
        except Exception as error:
            raise OAuthError("OAuth code exchange failed") from error

    def refresh(
        self,
        *,
        token_endpoint: str,
        client_id: str,
        refresh_token: str,
        resource: str | None = None,
    ) -> OAuthTokenBundle:
        """Refresh a public-client OAuth credential over HTTPS."""

        form = {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": refresh_token,
        }
        if resource is not None:
            form["resource"] = resource
        try:
            payload = self._post_form(token_endpoint, form)
            return _token_bundle_from_response(payload)
        except Exception as error:
            raise OAuthError("OAuth token refresh failed") from error

    def _post_form(self, endpoint: str, form: dict[str, str]) -> object:
        request = Request(
            endpoint,
            data=urlencode(form).encode("ascii"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with self._opener.open(request, timeout=30) as response:  # type: ignore[union-attr]
            if response.geturl() != endpoint:
                raise OAuthError("OAuth token response was redirected")
            body = response.read(self._max_response_bytes + 1)
        if len(body) > self._max_response_bytes:
            raise OAuthError("OAuth token response is too large")
        return json.loads(body.decode("utf-8"))


class OAuthAuthorizationService:
    """Run a human-only OAuth PKCE flow and persist only the resulting secret ref."""

    def __init__(
        self,
        *,
        connections: MCPConnectionControlPlane,
        receiver_factory: OAuthCallbackReceiverFactory | None = None,
        browser: OAuthBrowser | None = None,
        exchanger: OAuthTokenExchanger | None = None,
        state_factory: Callable[[], str] = lambda: secrets.token_urlsafe(32),
        verifier_factory: Callable[[], str] = lambda: secrets.token_urlsafe(64),
        timeout_seconds: int = 300,
    ) -> None:
        if not isinstance(timeout_seconds, int) or not 0 < timeout_seconds <= 600:
            raise OAuthError("OAuth callback timeout is out of range")
        self._connections = connections
        self._receiver_factory = (
            receiver_factory or LoopbackOAuthCallbackReceiverFactory()
        )
        self._browser = browser or ExternalOAuthBrowser()
        self._exchanger = exchanger or HttpOAuthTokenExchanger()
        self._state_factory = state_factory
        self._verifier_factory = verifier_factory
        self._timeout_seconds = timeout_seconds

    def authorize(
        self,
        connection_id: str,
        *,
        configuration: OAuthClientConfiguration,
    ) -> MCPAuthentication:
        """Authorize one preconfigured connection through an external browser."""

        connection = self._connections.load(connection_id)
        if connection.authentication_method != "oauth_authorization_code_pkce_loopback":
            raise MCPConnectionError("connection does not use OAuth authentication")
        state = _secret_text(self._state_factory(), "OAuth state")
        verifier = _secret_text(self._verifier_factory(), "PKCE verifier")
        receiver = self._receiver_factory.open(
            callback_path=_callback_path(configuration.registered_redirect_template)
        )
        try:
            if (
                configuration.registered_redirect_template is not None
                and not _matches_registered_redirect_uri(
                    receiver.redirect_uri, configuration.registered_redirect_template
                )
            ):
                raise MCPConnectionError("OAuth callback is invalid")
            authorization_url = _authorization_url(
                configuration=configuration,
                redirect_uri=receiver.redirect_uri,
                scopes=connection.scopes,
                state=state,
                verifier=verifier,
            )
            self._browser.open(authorization_url)
            callback = receiver.wait_for_callback(self._timeout_seconds)
            if not hmac.compare_digest(callback.state, state):
                raise MCPConnectionError("OAuth callback is invalid")
            if configuration.require_issuer_callback and callback.issuer is None:
                raise MCPConnectionError("OAuth callback is invalid")
            if (
                callback.issuer is not None
                and configuration.issuer is not None
                and not hmac.compare_digest(callback.issuer, configuration.issuer)
            ):
                raise MCPConnectionError("OAuth callback is invalid")
            exchange_arguments = {
                "token_endpoint": configuration.token_endpoint,
                "client_id": configuration.client_id,
                "code": callback.code,
                "redirect_uri": receiver.redirect_uri,
                "code_verifier": verifier,
            }
            if configuration.resource is not None:
                exchange_arguments["resource"] = configuration.resource
            bundle = self._exchanger.exchange(**exchange_arguments)
            return self._connections.configure_oauth_token(
                connection.connection_id,
                bundle.secret_value(),
                token_endpoint=configuration.token_endpoint,
                client_id=configuration.client_id,
                resource=configuration.resource,
                issuer=configuration.issuer,
                authorization_endpoint=configuration.authorization_endpoint
                if configuration.resource is not None
                else None,
                registration_id=configuration.registration_id,
                persistent_reconnect=configuration.persistent_reconnect,
            )
        except MCPConnectionError:
            raise
        except OAuthError as error:
            raise MCPConnectionError("OAuth authorization failed") from error
        finally:
            receiver.close()


def _authorization_url(
    *,
    configuration: OAuthClientConfiguration,
    redirect_uri: str,
    scopes: frozenset[str],
    state: str,
    verifier: str,
) -> str:
    parsed = urlsplit(configuration.authorization_endpoint)
    parameters = {
        "response_type": "code",
        "client_id": configuration.client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": _code_challenge(verifier),
        "code_challenge_method": "S256",
    }
    if not configuration.scope_is_omitted:
        parameters["scope"] = " ".join(sorted(scopes))
    if configuration.resource is not None:
        parameters["resource"] = configuration.resource
    query = urlencode(parameters)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))


def _callback_from_query(
    path: str, query: str, expected_path: str
) -> OAuthCallback | None:
    if path != expected_path:
        return None
    values = parse_qs(query, keep_blank_values=True)
    if set(values) not in ({"code", "state"}, {"code", "state", "iss"}):
        return None
    code = values.get("code")
    state = values.get("state")
    if code is None or state is None or len(code) != 1 or len(state) != 1:
        return None
    if not code[0] or not state[0]:
        return None
    issuer = values.get("iss")
    if issuer is not None and (len(issuer) != 1 or not issuer[0]):
        return None
    return OAuthCallback(
        code=code[0], state=state[0], issuer=None if issuer is None else issuer[0]
    )


def _code_challenge(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .decode("ascii")
        .rstrip("=")
    )


def _https_url(value: object, name: str) -> None:
    if not isinstance(value, str) or not value:
        raise OAuthError(f"{name} must be an HTTPS URL")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise OAuthError(f"{name} must be an HTTPS URL")


def _registered_redirect_template(value: object) -> None:
    if not isinstance(value, str) or not value:
        raise OAuthError("registered_redirect_template is invalid")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "localhost"
        or parsed.port is not None
        or not parsed.path.startswith("/oauth/callback/")
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise OAuthError("registered_redirect_template is invalid")


def _callback_path(registered_redirect_template: str | None) -> str:
    if registered_redirect_template is None:
        return LoopbackOAuthCallbackReceiver._CALLBACK_PATH
    return urlsplit(registered_redirect_template).path


def _matches_registered_redirect_uri(uri: str, template: str) -> bool:
    parsed = urlsplit(uri)
    expected = urlsplit(template)
    return (
        parsed.scheme == "http"
        and parsed.hostname == "127.0.0.1"
        and expected.hostname == "localhost"
        and parsed.port is not None
        and 0 < parsed.port <= 65_535
        and parsed.path == expected.path
        and not parsed.query
        and not parsed.fragment
        and parsed.username is None
        and parsed.password is None
    )


def _secret_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise OAuthError(f"{name} is unavailable")
    return value


def _expiry_from_response(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise OAuthError("OAuth code exchange failed")
    return datetime.now(UTC) + timedelta(seconds=value)


def _stored_expiry(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise OAuthError("OAuth credential is invalid")
    try:
        expiry = datetime.fromisoformat(value)
    except ValueError as error:
        raise OAuthError("OAuth credential is invalid") from error
    if expiry.tzinfo is None:
        raise OAuthError("OAuth credential is invalid")
    return expiry


def _token_bundle_from_response(payload: object) -> OAuthTokenBundle:
    if not isinstance(payload, dict):
        raise OAuthError("OAuth token response is invalid")
    return OAuthTokenBundle(
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token"),
        expires_at=_expiry_from_response(payload.get("expires_in")),
    )
