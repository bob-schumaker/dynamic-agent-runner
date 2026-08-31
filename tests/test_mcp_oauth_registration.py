"""Focused fake-only tests for dynamic OAuth public-client registration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib

import pytest

from dynamic_agent_runner.workflow_host.oauth_discovery import (
    AuthorizationServerMetadata,
    OAuthMetadataHTTPResponse,
    ScopeSelection,
)
from dynamic_agent_runner.workflow_host.oauth_registration import (
    OAuthClientRegistrationError,
    OAuthClientRegistrationService,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore


@dataclass
class FakeRegistrationTransport:
    response: OAuthMetadataHTTPResponse

    def __post_init__(self) -> None:
        self.requests: list[tuple[str, dict[str, object], int]] = []

    def post_json(
        self, url: str, *, payload: dict[str, object], max_response_bytes: int
    ) -> OAuthMetadataHTTPResponse:
        self.requests.append((url, payload, max_response_bytes))
        return self.response


def _metadata(**changes: object) -> AuthorizationServerMetadata:
    values: dict[str, object] = {
        "issuer": "https://auth.example.test/tenant",
        "authorization_endpoint": "https://auth.example.test/authorize",
        "token_endpoint": "https://auth.example.test/token",
        "registration_endpoint": "https://auth.example.test/register",
        "token_endpoint_auth_methods_supported": frozenset({"none"}),
        "code_challenge_methods_supported": frozenset({"S256"}),
        "response_types_supported": frozenset({"code"}),
        "grant_types_supported": frozenset({"authorization_code", "refresh_token"}),
    }
    values.update(changes)
    return AuthorizationServerMetadata(**values)  # type: ignore[arg-type]


def _response(payload: bytes, *, status: int = 201) -> OAuthMetadataHTTPResponse:
    return OAuthMetadataHTTPResponse(status=status, headers={}, body=payload)


def _service(
    tmp_path, transport: FakeRegistrationTransport
) -> OAuthClientRegistrationService:
    return OAuthClientRegistrationService(
        store=PrivateStateStore(tmp_path / "state"),
        owner="test-local-principal",
        transport=transport,
        now=lambda: datetime(2026, 8, 26, tzinfo=UTC),
    )


def test_registers_one_public_client_and_reuses_exact_host_record(tmp_path) -> None:
    redirect_template = (
        "http://localhost/oauth/callback/"
        + hashlib.sha256(
            b"test-local-principal\0https://auth.example.test/tenant"
        ).hexdigest()[:24]
    )
    transport = FakeRegistrationTransport(
        _response(
            b'{"client_id":"registered-client",'
            b'"token_endpoint_auth_method":"none",'
            + f'"redirect_uris":["{redirect_template}"]}}'.encode()
        )
    )
    service = _service(tmp_path, transport)
    metadata = _metadata()
    scopes = ScopeSelection(scopes=frozenset({"mail.read"}), scope_is_omitted=False)

    registration = service.register_or_reuse(
        metadata=metadata,
        scopes=scopes,
        resource="https://mcp.example.test/mcp",
    )
    reused = service.register_or_reuse(
        metadata=metadata,
        scopes=scopes,
        resource="https://mcp.example.test/mcp",
        existing_registration_id=registration.registration_id,
    )

    assert reused == registration
    assert registration.client_id == "registered-client"
    assert registration.redirect_template == redirect_template
    assert (
        registration.resource_digest
        == hashlib.sha256(b"https://mcp.example.test/mcp").hexdigest()
    )
    assert transport.requests == [
        (
            "https://auth.example.test/register",
            {
                "client_name": "Dynamic Agent Runner",
                "redirect_uris": [registration.redirect_template],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
                "scope": "mail.read",
            },
            32_768,
        )
    ]


def test_registration_accepts_an_omitted_response_type_advertisement(tmp_path) -> None:
    redirect_template = (
        "http://localhost/oauth/callback/"
        + hashlib.sha256(
            b"test-local-principal\0https://auth.example.test/tenant"
        ).hexdigest()[:24]
    )
    transport = FakeRegistrationTransport(
        _response(
            b'{"client_id":"registered-client",'
            b'"token_endpoint_auth_method":"none",'
            + f'"redirect_uris":["{redirect_template}"]}}'.encode()
        )
    )

    registration = _service(tmp_path, transport).register_or_reuse(
        metadata=_metadata(response_types_supported=None),
        scopes=ScopeSelection(scopes=frozenset(), scope_is_omitted=True),
        resource="https://mcp.example.test/mcp",
    )

    assert registration.client_id == "registered-client"


def test_registration_reuses_a_matching_connection_record_without_a_handle(
    tmp_path,
) -> None:
    redirect_template = (
        "http://localhost/oauth/callback/"
        + hashlib.sha256(
            b"test-local-principal\0https://auth.example.test/tenant"
        ).hexdigest()[:24]
    )
    transport = FakeRegistrationTransport(
        _response(
            b'{"client_id":"registered-client",'
            b'"token_endpoint_auth_method":"none",'
            + f'"redirect_uris":["{redirect_template}"]}}'.encode()
        )
    )
    service = _service(tmp_path, transport)
    arguments = {
        "metadata": _metadata(),
        "scopes": ScopeSelection(scopes=frozenset(), scope_is_omitted=True),
        "resource": "https://mcp.example.test/mcp",
        "connection_id": "v1.connection.signature",
    }

    registered = service.register_or_reuse(**arguments)
    reused = service.register_or_reuse(**arguments)

    assert reused == registered
    assert len(transport.requests) == 1


@pytest.mark.parametrize(
    ("metadata", "message"),
    [
        (_metadata(registration_endpoint=None), "registration is unavailable"),
        (
            _metadata(code_challenge_methods_supported=frozenset()),
            "registration is unavailable",
        ),
        (
            _metadata(response_types_supported=frozenset()),
            "registration is unavailable",
        ),
    ],
)
def test_registration_requires_explicit_advertised_public_client_capabilities(
    tmp_path, metadata: AuthorizationServerMetadata, message: str
) -> None:
    service = _service(tmp_path, FakeRegistrationTransport(_response(b"{}")))

    with pytest.raises(OAuthClientRegistrationError, match=message):
        service.register_or_reuse(
            metadata=metadata,
            scopes=ScopeSelection(scopes=frozenset(), scope_is_omitted=True),
            resource="https://mcp.example.test/mcp",
        )


def test_registration_rejects_secret_or_mismatched_response(tmp_path) -> None:
    redirect_template = (
        "http://localhost/oauth/callback/"
        + hashlib.sha256(
            b"test-local-principal\0https://auth.example.test/tenant"
        ).hexdigest()[:24]
    )
    transport = FakeRegistrationTransport(
        _response(
            b'{"client_id":"registered-client","client_secret":"not-allowed",'
            b'"token_endpoint_auth_method":"none",'
            + f'"redirect_uris":["{redirect_template}"]}}'.encode()
        )
    )
    service = _service(tmp_path, transport)

    with pytest.raises(OAuthClientRegistrationError, match="response is invalid"):
        service.register_or_reuse(
            metadata=_metadata(),
            scopes=ScopeSelection(scopes=frozenset(), scope_is_omitted=True),
            resource="https://mcp.example.test/mcp",
        )
