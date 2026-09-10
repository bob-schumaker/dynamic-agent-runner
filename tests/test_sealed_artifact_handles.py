"""Contract tests for receiver-only prepared artifact handles."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactHandleError,
    SealedArtifactHandleService,
    SealedArtifactInput,
    SealedArtifactRunnerDescriptor,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore


NOW = datetime(2026, 9, 10, tzinfo=UTC)


def _service(tmp_path) -> SealedArtifactHandleService:
    return SealedArtifactHandleService(
        store=PrivateStateStore(tmp_path / "state"), owner="test-owner"
    )


def _descriptor() -> SealedArtifactRunnerDescriptor:
    return SealedArtifactRunnerDescriptor(
        digest="b" * 64,
        asset_path="assets/runner.py",
        asset_digest="c" * 64,
        capability_requirements_digest="d" * 64,
        inputs=(
            SealedArtifactInput(
                role="snapshot",
                media_type="application/octet-stream",
                max_bytes=12,
                required=True,
                schema_digest=None,
            ),
        ),
        schema_assets=(),
        child_contract_digests=(),
        callbacks=(),
        output_roles=("result",),
    )


def _prepare(service: SealedArtifactHandleService):
    return service.prepare(
        descriptor=_descriptor(),
        receiver_id="receiver",
        revision_digest="a" * 64,
        invocation_id="invocation",
        role="snapshot",
        media_type="application/octet-stream",
        schema_digest=None,
        content=b"sealed bytes",
        expires_at=NOW + timedelta(minutes=1),
        now=NOW,
    )


def test_handle_preparation_requires_declared_input_contract(tmp_path) -> None:
    service = _service(tmp_path)

    with pytest.raises(SealedArtifactHandleError, match="invalid"):
        service.prepare(
            descriptor=_descriptor(),
            receiver_id="receiver",
            revision_digest="a" * 64,
            invocation_id="invocation",
            role="other",
            media_type="application/octet-stream",
            schema_digest=None,
            content=b"sealed bytes",
            expires_at=NOW + timedelta(minutes=1),
            now=NOW,
        )


@pytest.mark.parametrize(
    ("media_type", "content"),
    [
        ("application/json", b"sealed bytes"),
        ("application/octet-stream", b"x" * 13),
    ],
)
def test_handle_preparation_enforces_declared_media_and_byte_ceiling(
    tmp_path, media_type: str, content: bytes
) -> None:
    service = _service(tmp_path)

    with pytest.raises(SealedArtifactHandleError, match="invalid"):
        service.prepare(
            descriptor=_descriptor(),
            receiver_id="receiver",
            revision_digest="a" * 64,
            invocation_id="invocation",
            role="snapshot",
            media_type=media_type,
            schema_digest=None,
            content=content,
            expires_at=NOW + timedelta(minutes=1),
            now=NOW,
        )


def _binding() -> dict[str, str | None]:
    return {
        "receiver_id": "receiver",
        "revision_digest": "a" * 64,
        "invocation_id": "invocation",
        "role": "snapshot",
        "media_type": "application/octet-stream",
        "schema_digest": None,
    }


def test_handle_is_opaque_bound_and_single_use(tmp_path) -> None:
    service = _service(tmp_path)
    handle = _prepare(service)

    assert handle.handle_id
    service.reserve(handle.handle_id, now=NOW, **_binding())
    assert (
        service.consume(
            handle.handle_id,
            now=NOW,
            **_binding(),
        )
        == b"sealed bytes"
    )
    with pytest.raises(SealedArtifactHandleError, match="unavailable"):
        service.consume(
            handle.handle_id,
            now=NOW,
            **_binding(),
        )


def test_handle_cannot_be_consumed_before_reservation(tmp_path) -> None:
    service = _service(tmp_path)
    handle = _prepare(service)

    with pytest.raises(SealedArtifactHandleError, match="unavailable"):
        service.consume(handle.handle_id, now=NOW, **_binding())

    service.reserve(handle.handle_id, now=NOW, **_binding())
    assert service.consume(handle.handle_id, now=NOW, **_binding()) == b"sealed bytes"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("receiver_id", "other-receiver"),
        ("revision_digest", "b" * 64),
        ("invocation_id", "other-invocation"),
        ("role", "other_role"),
        ("media_type", "application/json"),
        ("schema_digest", "b" * 64),
    ],
)
def test_mismatched_handle_metadata_never_consumes_bytes(
    tmp_path, field: str, value: str
) -> None:
    service = _service(tmp_path)
    handle = _prepare(service)
    expected = {
        "receiver_id": "receiver",
        "revision_digest": "a" * 64,
        "invocation_id": "invocation",
        "role": "snapshot",
        "media_type": "application/octet-stream",
        "schema_digest": None,
    }
    expected[field] = value

    with pytest.raises(SealedArtifactHandleError, match="does not match"):
        service.reserve(handle.handle_id, now=NOW, **expected)

    service.reserve(handle.handle_id, now=NOW, **_binding())
    assert (
        service.consume(
            handle.handle_id,
            now=NOW,
            **_binding(),
        )
        == b"sealed bytes"
    )


def test_revoked_handle_cannot_be_consumed(tmp_path) -> None:
    service = _service(tmp_path)
    handle = _prepare(service)
    service.revoke(handle.handle_id, now=NOW)

    with pytest.raises(SealedArtifactHandleError, match="unavailable"):
        service.consume(
            handle.handle_id,
            receiver_id="receiver",
            revision_digest="a" * 64,
            invocation_id="invocation",
            role="snapshot",
            media_type="application/octet-stream",
            schema_digest=None,
            now=NOW,
        )


def test_reserved_handle_can_be_revoked(tmp_path) -> None:
    service = _service(tmp_path)
    handle = _prepare(service)
    service.reserve(handle.handle_id, now=NOW, **_binding())

    service.revoke(handle.handle_id, now=NOW)

    with pytest.raises(SealedArtifactHandleError, match="unavailable"):
        service.consume(handle.handle_id, now=NOW, **_binding())


def test_expired_handle_cannot_be_consumed(tmp_path) -> None:
    service = _service(tmp_path)
    handle = _prepare(service)

    with pytest.raises(SealedArtifactHandleError, match="unavailable"):
        service.consume(
            handle.handle_id,
            receiver_id="receiver",
            revision_digest="a" * 64,
            invocation_id="invocation",
            role="snapshot",
            media_type="application/octet-stream",
            schema_digest=None,
            now=NOW + timedelta(minutes=2),
        )
