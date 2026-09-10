"""Contract tests for receiver-only prepared artifact handles."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactHandleError,
    SealedArtifactHandleService,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore


NOW = datetime(2026, 9, 10, tzinfo=UTC)


def _service(tmp_path) -> SealedArtifactHandleService:
    return SealedArtifactHandleService(
        store=PrivateStateStore(tmp_path / "state"), owner="test-owner"
    )


def _prepare(service: SealedArtifactHandleService):
    return service.prepare(
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


def test_handle_is_opaque_bound_and_single_use(tmp_path) -> None:
    service = _service(tmp_path)
    handle = _prepare(service)

    assert handle.handle_id
    assert (
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
        == b"sealed bytes"
    )
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
        service.consume(handle.handle_id, now=NOW, **expected)

    assert (
        service.consume(
            handle.handle_id,
            now=NOW,
            **{
                "receiver_id": "receiver",
                "revision_digest": "a" * 64,
                "invocation_id": "invocation",
                "role": "snapshot",
                "media_type": "application/octet-stream",
                "schema_digest": None,
            },
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
