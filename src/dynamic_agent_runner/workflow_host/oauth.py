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
from urllib.request import Request, urlopen

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

    def __post_init__(self) -> None:
        _https_url(self.authorization_endpoint, "authorization_endpoint")
        _https_url(self.token_endpoint, "token_endpoint")
        if not isinstance(self.client_id, str) or not self.client_id:
            raise OAuthError("client_id must be a non-empty string")


@dataclass(frozen=True)
class OAuthCallback:
    """Transient authorization-code callback, never persisted or returned."""

    code: str = field(repr=False)
    state: str = field(repr=False)


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
    def open(self) -> OAuthCallbackReceiver:
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

    def __init__(self) -> None:
        callbacks: queue.Queue[OAuthCallback] = queue.Queue(maxsize=1)
        callback_path = self._CALLBACK_PATH

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
                self.send_response(200)
                self.end_headers()

            def log_message(self, format: str, *args: object) -> None:
                return

        self._callbacks = callbacks
        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        port = self._server.server_address[1]
        self._redirect_uri = f"http://127.0.0.1:{port}{self._CALLBACK_PATH}"

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
    def open(self) -> LoopbackOAuthCallbackReceiver:
        return LoopbackOAuthCallbackReceiver()


class HttpOAuthTokenExchanger:
    """Exchange a public-client authorization code over HTTPS."""

    def exchange(
        self,
        *,
        token_endpoint: str,
        client_id: str,
        code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> OAuthTokenBundle:
        request = Request(
            token_endpoint,
            data=urlencode(
                {
                    "grant_type": "authorization_code",
                    "client_id": client_id,
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "code_verifier": code_verifier,
                }
            ).encode("ascii"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
            return _token_bundle_from_response(payload)
        except Exception as error:
            raise OAuthError("OAuth code exchange failed") from error

    def refresh(
        self,
        *,
        token_endpoint: str,
        client_id: str,
        refresh_token: str,
    ) -> OAuthTokenBundle:
        """Refresh a public-client OAuth credential over HTTPS."""

        request = Request(
            token_endpoint,
            data=urlencode(
                {
                    "grant_type": "refresh_token",
                    "client_id": client_id,
                    "refresh_token": refresh_token,
                }
            ).encode("ascii"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
            return _token_bundle_from_response(payload)
        except Exception as error:
            raise OAuthError("OAuth token refresh failed") from error


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
        receiver = self._receiver_factory.open()
        try:
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
            bundle = self._exchanger.exchange(
                token_endpoint=configuration.token_endpoint,
                client_id=configuration.client_id,
                code=callback.code,
                redirect_uri=receiver.redirect_uri,
                code_verifier=verifier,
            )
            return self._connections.configure_oauth_token(
                connection.connection_id,
                bundle.secret_value(),
                token_endpoint=configuration.token_endpoint,
                client_id=configuration.client_id,
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
    query = urlencode(
        {
            "response_type": "code",
            "client_id": configuration.client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(sorted(scopes)),
            "state": state,
            "code_challenge": _code_challenge(verifier),
            "code_challenge_method": "S256",
        }
    )
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))


def _callback_from_query(
    path: str, query: str, expected_path: str
) -> OAuthCallback | None:
    if path != expected_path:
        return None
    values = parse_qs(query, keep_blank_values=True)
    if set(values) != {"code", "state"}:
        return None
    code = values.get("code")
    state = values.get("state")
    if code is None or state is None or len(code) != 1 or len(state) != 1:
        return None
    if not code[0] or not state[0]:
        return None
    return OAuthCallback(code=code[0], state=state[0])


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
