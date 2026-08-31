"""Host-owned dynamic public-client registration for discovered MCP OAuth."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from typing import Callable, Mapping, Protocol

from dynamic_agent_runner.workflow_host.oauth_discovery import (
    AuthorizationServerMetadata,
    OAuthMetadataHTTPResponse,
    ScopeSelection,
)
from dynamic_agent_runner.workflow_host.state import (
    OpaqueRecordError,
    PrivateStateStore,
)


class OAuthClientRegistrationError(ValueError):
    """Raised when public-client registration is unsupported or unsafe."""


class OAuthRegistrationHTTPTransport(Protocol):
    """Send one bounded JSON registration request without redirects or credentials."""

    def post_json(
        self,
        url: str,
        *,
        payload: Mapping[str, object],
        max_response_bytes: int,
    ) -> OAuthMetadataHTTPResponse:
        """Return the bounded response for exactly ``url``."""


@dataclass(frozen=True)
class OAuthClientRegistration:
    """Host-only non-secret public-client record for one issuer and scope set."""

    registration_id: str
    issuer: str
    client_id: str
    redirect_template: str
    resource_digest: str
    scope_digest: str


class OAuthClientRegistrationService:
    """Register or reuse the one v1 loopback public client for a host context."""

    def __init__(
        self,
        *,
        store: PrivateStateStore,
        owner: str,
        transport: OAuthRegistrationHTTPTransport,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        max_response_bytes: int = 32_768,
    ) -> None:
        if not isinstance(owner, str) or not owner:
            raise OAuthClientRegistrationError("registration owner is invalid")
        if (
            not isinstance(max_response_bytes, int)
            or not 0 < max_response_bytes <= 65_536
        ):
            raise OAuthClientRegistrationError("registration response limit is invalid")
        self._store = store
        self._owner = owner
        self._transport = transport
        self._now = now
        self._max_response_bytes = max_response_bytes

    def register_or_reuse(
        self,
        *,
        metadata: AuthorizationServerMetadata,
        scopes: ScopeSelection,
        resource: str,
        connection_id: str | None = None,
        existing_registration_id: str | None = None,
    ) -> OAuthClientRegistration:
        """Reuse an exact matching record or register one non-confidential client."""

        _require_dynamic_registration_capabilities(metadata)
        redirect_template = _redirect_template(metadata.issuer, self._owner)
        resource_digest = _resource_digest(resource)
        scope_digest = _scope_digest(scopes)
        if connection_id is not None:
            _opaque_id(connection_id, "connection_id")
        if existing_registration_id is not None:
            return self._load_matching(
                existing_registration_id,
                issuer=metadata.issuer,
                redirect_template=redirect_template,
                resource_digest=resource_digest,
                scope_digest=scope_digest,
                connection_id=connection_id,
            )
        if connection_id is not None:
            existing = self._matching_connection_registration(
                connection_id=connection_id,
                issuer=metadata.issuer,
                redirect_template=redirect_template,
                resource_digest=resource_digest,
                scope_digest=scope_digest,
            )
            if existing is not None:
                return existing
        response = self._transport.post_json(
            metadata.registration_endpoint,
            payload=_registration_request(redirect_template, scopes),
            max_response_bytes=self._max_response_bytes,
        )
        if response.url is not None and response.url != metadata.registration_endpoint:
            raise OAuthClientRegistrationError("registration response is invalid")
        if response.status not in {200, 201}:
            raise OAuthClientRegistrationError("registration is unavailable")
        if (
            not isinstance(response.body, bytes)
            or len(response.body) > self._max_response_bytes
        ):
            raise OAuthClientRegistrationError("registration response is invalid")
        client_id = _registered_client_id(response.body, redirect_template)
        try:
            registration_id = self._store.issue(
                kind="mcp_oauth_dynamic_client_registration",
                owner=self._owner,
                payload={
                    "issuer": metadata.issuer,
                    "client_id": client_id,
                    "redirect_template": redirect_template,
                    "resource_digest": resource_digest,
                    "scope_digest": scope_digest,
                    "connection_id": connection_id,
                },
                expires_at=datetime.max.replace(tzinfo=UTC),
                now=self._now(),
            )
        except OpaqueRecordError as error:
            raise OAuthClientRegistrationError(
                "registration record is unavailable"
            ) from error
        return OAuthClientRegistration(
            registration_id=registration_id,
            issuer=metadata.issuer,
            client_id=client_id,
            redirect_template=redirect_template,
            resource_digest=resource_digest,
            scope_digest=scope_digest,
        )

    def _load_matching(
        self,
        registration_id: str,
        *,
        issuer: str,
        redirect_template: str,
        resource_digest: str,
        scope_digest: str,
        connection_id: str | None,
    ) -> OAuthClientRegistration:
        try:
            record = self._store.load(
                registration_id,
                expected_kind="mcp_oauth_dynamic_client_registration",
                owner=self._owner,
                now=self._now(),
            )
            payload = record.payload
            stored_issuer = payload["issuer"]
            client_id = payload["client_id"]
            stored_redirect = payload["redirect_template"]
            stored_resource_digest = payload["resource_digest"]
            stored_scope_digest = payload["scope_digest"]
            stored_connection_id = payload.get("connection_id")
        except (KeyError, OpaqueRecordError, TypeError) as error:
            raise OAuthClientRegistrationError(
                "registration record is unavailable"
            ) from error
        if (
            stored_issuer != issuer
            or stored_redirect != redirect_template
            or stored_resource_digest != resource_digest
            or stored_scope_digest != scope_digest
            or stored_connection_id != connection_id
            or not isinstance(client_id, str)
            or not client_id
        ):
            raise OAuthClientRegistrationError(
                "registration record does not match setup"
            )
        return OAuthClientRegistration(
            registration_id=registration_id,
            issuer=issuer,
            client_id=client_id,
            redirect_template=redirect_template,
            resource_digest=resource_digest,
            scope_digest=scope_digest,
        )

    def _matching_connection_registration(
        self,
        *,
        connection_id: str,
        issuer: str,
        redirect_template: str,
        resource_digest: str,
        scope_digest: str,
    ) -> OAuthClientRegistration | None:
        try:
            records = self._store.active_records(
                kind="mcp_oauth_dynamic_client_registration",
                owner=self._owner,
                now=self._now(),
            )
        except OpaqueRecordError as error:
            raise OAuthClientRegistrationError(
                "registration record is unavailable"
            ) from error
        for registration_id, record in records:
            payload = record.payload
            if (
                payload.get("connection_id") == connection_id
                and payload.get("issuer") == issuer
                and payload.get("redirect_template") == redirect_template
                and payload.get("resource_digest") == resource_digest
                and payload.get("scope_digest") == scope_digest
            ):
                return self._load_matching(
                    registration_id,
                    issuer=issuer,
                    redirect_template=redirect_template,
                    resource_digest=resource_digest,
                    scope_digest=scope_digest,
                    connection_id=connection_id,
                )
        return None


def _require_dynamic_registration_capabilities(
    metadata: AuthorizationServerMetadata,
) -> None:
    if (
        metadata.registration_endpoint is None
        or "none" not in metadata.token_endpoint_auth_methods_supported
        or "S256" not in metadata.code_challenge_methods_supported
        or (
            metadata.response_types_supported is not None
            and "code" not in metadata.response_types_supported
        )
        or not {"authorization_code", "refresh_token"} <= metadata.grant_types_supported
    ):
        raise OAuthClientRegistrationError("registration is unavailable")


def _registration_request(
    redirect_template: str, scopes: ScopeSelection
) -> dict[str, object]:
    request: dict[str, object] = {
        "client_name": "Dynamic Agent Runner",
        "redirect_uris": [redirect_template],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }
    if not scopes.scope_is_omitted:
        request["scope"] = " ".join(sorted(scopes.scopes))
    return request


def _registered_client_id(body: bytes, redirect_template: str) -> str:
    try:
        payload = json.loads(body)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OAuthClientRegistrationError(
            "registration response is invalid"
        ) from error
    if not isinstance(payload, dict):
        raise OAuthClientRegistrationError("registration response is invalid")
    if "client_secret" in payload or "registration_access_token" in payload:
        raise OAuthClientRegistrationError("registration response is invalid")
    client_id = payload.get("client_id")
    if not isinstance(client_id, str) or not client_id:
        raise OAuthClientRegistrationError("registration response is invalid")
    if payload.get("token_endpoint_auth_method") != "none":
        raise OAuthClientRegistrationError("registration response is invalid")
    if payload.get("redirect_uris") != [redirect_template]:
        raise OAuthClientRegistrationError("registration response is invalid")
    return client_id


def _redirect_template(issuer: str, owner: str) -> str:
    path_token = hashlib.sha256(f"{owner}\0{issuer}".encode("utf-8")).hexdigest()[:24]
    return f"http://localhost/oauth/callback/{path_token}"


def _scope_digest(scopes: ScopeSelection) -> str:
    canonical = json.dumps(
        {"scope_is_omitted": scopes.scope_is_omitted, "scopes": sorted(scopes.scopes)},
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _resource_digest(resource: object) -> str:
    if not isinstance(resource, str) or not resource.startswith("https://"):
        raise OAuthClientRegistrationError("protected resource is invalid")
    return hashlib.sha256(resource.encode("utf-8")).hexdigest()


def _opaque_id(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.startswith("v1."):
        raise OAuthClientRegistrationError(f"{label} is invalid")
