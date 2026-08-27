"""Bounded, fake-testable OAuth metadata discovery for configured HTTPS MCP."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from typing import Callable, Mapping, Protocol
from urllib.parse import urlsplit, urlunsplit
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from dynamic_agent_runner.workflow_host.state import (
    OpaqueRecordError,
    PrivateStateStore,
)


class OAuthDiscoveryError(ValueError):
    """Raised when configured MCP OAuth metadata cannot be safely bound."""


@dataclass(frozen=True)
class OAuthMetadataHTTPResponse:
    """One bounded response returned by an injected no-redirect HTTP client."""

    status: int
    headers: Mapping[str, str]
    body: bytes
    url: str | None = None


class OAuthMetadataHTTPTransport(Protocol):
    """Fetch one HTTPS URL without redirect following or ambient credentials."""

    def get(self, url: str, *, max_response_bytes: int) -> OAuthMetadataHTTPResponse:
        """Return one bounded response for exactly ``url``."""


class UrllibOAuthMetadataHTTPTransport:
    """Perform bounded unauthenticated metadata requests without redirects."""

    def get(self, url: str, *, max_response_bytes: int) -> OAuthMetadataHTTPResponse:
        request = Request(url, method="GET")
        return self._request(request, max_response_bytes=max_response_bytes)

    def post_json(
        self,
        url: str,
        *,
        payload: Mapping[str, object],
        max_response_bytes: int,
    ) -> OAuthMetadataHTTPResponse:
        request = Request(
            url,
            data=json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            ),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        return self._request(request, max_response_bytes=max_response_bytes)

    def _request(
        self, request: Request, *, max_response_bytes: int
    ) -> OAuthMetadataHTTPResponse:
        if not isinstance(max_response_bytes, int) or max_response_bytes <= 0:
            raise OAuthDiscoveryError("metadata response limit is out of range")
        opener = build_opener(_NoRedirectHandler())
        try:
            response = opener.open(request, timeout=30)
        except HTTPError as response:
            return _http_response(response, max_response_bytes=max_response_bytes)
        except Exception as error:
            raise OAuthDiscoveryError("metadata is unavailable") from error
        try:
            return _http_response(response, max_response_bytes=max_response_bytes)
        finally:
            response.close()


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


@dataclass(frozen=True)
class ProtectedResourceMetadata:
    """Validated fields needed to discover one MCP authorization server."""

    resource: str
    authorization_servers: tuple[str, ...]
    scopes_supported: frozenset[str]
    challenged_scopes: frozenset[str]


@dataclass(frozen=True)
class AuthorizationServerMetadata:
    """Validated non-secret metadata for one selected authorization server."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str | None
    token_endpoint_auth_methods_supported: frozenset[str]
    code_challenge_methods_supported: frozenset[str]
    response_types_supported: frozenset[str] | None
    grant_types_supported: frozenset[str]
    authorization_response_iss_parameter_supported: bool = False


@dataclass(frozen=True)
class ScopeSelection:
    """Immutable human-confirmed effective scope choice for later persistence."""

    scopes: frozenset[str]
    scope_is_omitted: bool


class OAuthDiscoveryRecordStore:
    """Persist redaction-safe discovery bindings outside package surfaces."""

    def __init__(
        self,
        *,
        store: PrivateStateStore,
        owner: str,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(owner, str) or not owner:
            raise OAuthDiscoveryError("discovery record owner is invalid")
        self._store = store
        self._owner = owner
        self._now = now or (lambda: datetime.now(UTC))

    def record(
        self,
        *,
        connection_id: str,
        protected_resource: ProtectedResourceMetadata,
        authorization_server: AuthorizationServerMetadata,
        scopes: ScopeSelection,
    ) -> None:
        """Record validated discovery state without preserving raw metadata."""

        if not isinstance(connection_id, str) or not connection_id.startswith("v1."):
            raise OAuthDiscoveryError("discovery record connection is invalid")
        payload = {
            "connection_id": connection_id,
            "protected_resource_digest": _metadata_digest(protected_resource),
            "authorization_server_digest": _metadata_digest(authorization_server),
            "scope_digest": _metadata_digest(scopes),
        }
        try:
            self._store.issue(
                kind="mcp_oauth_discovery",
                owner=self._owner,
                payload=payload,
                expires_at=datetime.max.replace(tzinfo=UTC),
                now=self._now(),
            )
        except OpaqueRecordError as error:
            raise OAuthDiscoveryError("discovery record is unavailable") from error


class OAuthMetadataDiscovery:
    """Discover protected-resource metadata from a human-configured endpoint."""

    def __init__(
        self, *, transport: OAuthMetadataHTTPTransport, max_response_bytes: int = 32_768
    ) -> None:
        if (
            not isinstance(max_response_bytes, int)
            or not 0 < max_response_bytes <= 65_536
        ):
            raise OAuthDiscoveryError("metadata response limit is out of range")
        self._transport = transport
        self._max_response_bytes = max_response_bytes

    def discover_protected_resource(self, endpoint: str) -> ProtectedResourceMetadata:
        """Discover one resource document and bind it to exactly ``endpoint``."""

        canonical_endpoint = _https_url(endpoint, "configured endpoint")
        challenge_response = self._get(canonical_endpoint)
        challenge = _bearer_challenge(challenge_response.headers)
        metadata_url = challenge.get("resource_metadata")
        challenged_scopes = frozenset(_scope_values(challenge.get("scope")))
        candidates = (
            (metadata_url,)
            if metadata_url is not None
            else _protected_resource_metadata_urls(canonical_endpoint)
        )
        for candidate in candidates:
            if candidate is None:
                continue
            response = self._get(candidate)
            if response.status == 404 and metadata_url is None:
                continue
            if response.status != 200:
                raise OAuthDiscoveryError("metadata is unavailable")
            return _protected_resource_metadata(
                response.body,
                endpoint=canonical_endpoint,
                challenged_scopes=challenged_scopes,
            )
        raise OAuthDiscoveryError("metadata is unavailable")

    def discover_authorization_server(
        self, protected_resource: ProtectedResourceMetadata
    ) -> AuthorizationServerMetadata:
        """Discover metadata for exactly one server from protected-resource metadata."""

        if len(protected_resource.authorization_servers) != 1:
            raise OAuthDiscoveryError("authorization server selection required")
        issuer = _issuer_url(
            protected_resource.authorization_servers[0], "authorization server"
        )
        for candidate in _authorization_server_metadata_urls(issuer):
            response = self._get(candidate)
            if response.status == 404:
                continue
            if response.status != 200:
                raise OAuthDiscoveryError(
                    "authorization server metadata is unavailable"
                )
            return _authorization_server_metadata(response.body, issuer=issuer)
        raise OAuthDiscoveryError("authorization server metadata is unavailable")

    @staticmethod
    def confirm_scope_selection(
        protected_resource: ProtectedResourceMetadata,
        *,
        selected_scopes: set[str],
        persistent_reconnect: bool,
    ) -> ScopeSelection:
        """Validate the exact scope set a human confirms during setup."""

        selected = frozenset(_scope_values_from_set(selected_scopes))
        challenged = protected_resource.challenged_scopes
        if challenged:
            if selected != challenged:
                raise OAuthDiscoveryError(
                    "challenged scopes require exact confirmation"
                )
            return ScopeSelection(scopes=selected, scope_is_omitted=False)
        advertised = protected_resource.scopes_supported
        if not advertised:
            if selected:
                raise OAuthDiscoveryError("scopes were not advertised")
            return ScopeSelection(scopes=frozenset(), scope_is_omitted=True)
        if not selected or not selected <= advertised:
            raise OAuthDiscoveryError("selected scopes are not advertised")
        if "offline_access" in selected and not persistent_reconnect:
            raise OAuthDiscoveryError("offline_access requires persistent reconnect")
        return ScopeSelection(scopes=selected, scope_is_omitted=False)

    def _get(self, url: str) -> OAuthMetadataHTTPResponse:
        expected = _https_url(url, "metadata URL")
        response = self._transport.get(
            expected, max_response_bytes=self._max_response_bytes
        )
        if response.url is not None and response.url != expected:
            raise OAuthDiscoveryError("metadata was redirected")
        if not isinstance(response.body, bytes):
            raise OAuthDiscoveryError("metadata is invalid")
        if len(response.body) > self._max_response_bytes:
            raise OAuthDiscoveryError("metadata is too large")
        return response


def _protected_resource_metadata_urls(endpoint: str) -> tuple[str, str]:
    parsed = urlsplit(endpoint)
    path_metadata = urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            f"/.well-known/oauth-protected-resource{parsed.path}",
            "",
            "",
        )
    )
    root_metadata = urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            "/.well-known/oauth-protected-resource",
            "",
            "",
        )
    )
    return path_metadata, root_metadata


def _http_response(
    response: object, *, max_response_bytes: int
) -> OAuthMetadataHTTPResponse:
    try:
        status = response.status
        headers = dict(response.headers.items())
        body = response.read(max_response_bytes + 1)
        url = response.geturl()
    except Exception as error:
        raise OAuthDiscoveryError("metadata is unavailable") from error
    if not isinstance(status, int) or not isinstance(body, bytes):
        raise OAuthDiscoveryError("metadata is unavailable")
    return OAuthMetadataHTTPResponse(status=status, headers=headers, body=body, url=url)


def _authorization_server_metadata_urls(issuer: str) -> tuple[str, str, str]:
    parsed = urlsplit(issuer)
    path = parsed.path.rstrip("/")
    rfc8414 = urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            f"/.well-known/oauth-authorization-server{path}",
            "",
            "",
        )
    )
    oidc_inserted = urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            f"/.well-known/openid-configuration{path}",
            "",
            "",
        )
    )
    oidc_appended = urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            f"{path}/.well-known/openid-configuration",
            "",
            "",
        )
    )
    return rfc8414, oidc_inserted, oidc_appended


def _protected_resource_metadata(
    body: bytes,
    *,
    endpoint: str,
    challenged_scopes: frozenset[str],
) -> ProtectedResourceMetadata:
    try:
        payload = json.loads(body)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OAuthDiscoveryError("metadata is invalid") from error
    if not isinstance(payload, dict):
        raise OAuthDiscoveryError("metadata is invalid")
    resource = payload.get("resource")
    if resource != endpoint:
        raise OAuthDiscoveryError("metadata resource does not match endpoint")
    authorization_servers = _https_values(
        payload.get("authorization_servers"), "authorization_servers"
    )
    if not authorization_servers:
        raise OAuthDiscoveryError("metadata is invalid")
    scopes = _string_values(payload.get("scopes_supported"), "scopes_supported")
    return ProtectedResourceMetadata(
        resource=resource,
        authorization_servers=authorization_servers,
        scopes_supported=frozenset(scopes),
        challenged_scopes=challenged_scopes,
    )


def _authorization_server_metadata(
    body: bytes, *, issuer: str
) -> AuthorizationServerMetadata:
    try:
        payload = json.loads(body)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OAuthDiscoveryError("authorization server metadata is invalid") from error
    if not isinstance(payload, dict):
        raise OAuthDiscoveryError("authorization server metadata is invalid")
    if payload.get("issuer") != issuer:
        raise OAuthDiscoveryError("authorization server metadata issuer does not match")
    authorization_endpoint = _https_url(
        payload.get("authorization_endpoint"), "authorization endpoint"
    )
    token_endpoint = _https_url(payload.get("token_endpoint"), "token endpoint")
    registration_value = payload.get("registration_endpoint")
    registration_endpoint = (
        None
        if registration_value is None
        else _https_url(registration_value, "registration endpoint")
    )
    return AuthorizationServerMetadata(
        issuer=issuer,
        authorization_endpoint=authorization_endpoint,
        token_endpoint=token_endpoint,
        registration_endpoint=registration_endpoint,
        token_endpoint_auth_methods_supported=frozenset(
            _string_values(
                payload.get("token_endpoint_auth_methods_supported"),
                "token_endpoint_auth_methods_supported",
            )
        ),
        code_challenge_methods_supported=frozenset(
            _string_values(
                payload.get("code_challenge_methods_supported"),
                "code_challenge_methods_supported",
            )
        ),
        response_types_supported=(
            None
            if "response_types_supported" not in payload
            else frozenset(
                _string_values(
                    payload["response_types_supported"], "response_types_supported"
                )
            )
        ),
        grant_types_supported=frozenset(
            _string_values(
                payload.get("grant_types_supported"), "grant_types_supported"
            )
        ),
        authorization_response_iss_parameter_supported=_boolean_metadata_value(
            payload.get("authorization_response_iss_parameter_supported", False),
            "authorization_response_iss_parameter_supported",
        ),
    )


def _bearer_challenge(headers: Mapping[str, str]) -> dict[str, str]:
    header = next(
        (
            value
            for name, value in headers.items()
            if isinstance(name, str) and name.lower() == "www-authenticate"
        ),
        "",
    )
    if not isinstance(header, str) or not header.lower().startswith("bearer"):
        return {}
    fields: dict[str, str] = {}
    for part in header[6:].split(","):
        name, separator, value = part.strip().partition("=")
        if not separator or not name:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] == '"':
            value = value[1:-1]
        fields[name.lower()] = value
    return fields


def _scope_values(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    values = tuple(item for item in value.split() if item)
    if len(values) != len(set(values)):
        raise OAuthDiscoveryError("metadata challenge is invalid")
    return values


def _scope_values_from_set(value: set[str]) -> tuple[str, ...]:
    if not isinstance(value, set) or any(
        not isinstance(item, str)
        or not item
        or any(character.isspace() for character in item)
        for item in value
    ):
        raise OAuthDiscoveryError("selected scopes are invalid")
    return tuple(value)


def _string_values(value: object, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise OAuthDiscoveryError("metadata is invalid")
    if len(value) != len(set(value)):
        raise OAuthDiscoveryError(f"{name} contains duplicates")
    return tuple(value)


def _boolean_metadata_value(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise OAuthDiscoveryError(f"{name} is invalid")
    return value


def _metadata_digest(
    value: ProtectedResourceMetadata | AuthorizationServerMetadata | ScopeSelection,
) -> str:
    if isinstance(value, ProtectedResourceMetadata):
        canonical: Mapping[str, object] = {
            "resource": value.resource,
            "authorization_servers": value.authorization_servers,
            "scopes_supported": sorted(value.scopes_supported),
            "challenged_scopes": sorted(value.challenged_scopes),
        }
    elif isinstance(value, AuthorizationServerMetadata):
        canonical = {
            "issuer": value.issuer,
            "authorization_endpoint": value.authorization_endpoint,
            "token_endpoint": value.token_endpoint,
            "registration_endpoint": value.registration_endpoint,
            "token_endpoint_auth_methods_supported": sorted(
                value.token_endpoint_auth_methods_supported
            ),
            "code_challenge_methods_supported": sorted(
                value.code_challenge_methods_supported
            ),
            "response_types_supported": (
                None
                if value.response_types_supported is None
                else sorted(value.response_types_supported)
            ),
            "grant_types_supported": sorted(value.grant_types_supported),
            "authorization_response_iss_parameter_supported": (
                value.authorization_response_iss_parameter_supported
            ),
        }
    else:
        canonical = {
            "scopes": sorted(value.scopes),
            "scope_is_omitted": value.scope_is_omitted,
        }
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _https_values(value: object, name: str) -> tuple[str, ...]:
    values = _string_values(value, name)
    return tuple(_https_url(item, name) for item in values)


def _https_url(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise OAuthDiscoveryError(f"{name} must be an HTTPS URL")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise OAuthDiscoveryError(f"{name} must be an HTTPS URL")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))


def _issuer_url(value: object, name: str) -> str:
    issuer = _https_url(value, name)
    if urlsplit(issuer).query:
        raise OAuthDiscoveryError(f"{name} must not contain a query")
    return issuer
