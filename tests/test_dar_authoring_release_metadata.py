"""Tests for signed canonical release metadata for the DAR runtime launcher."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


from dynamic_agent_runner.workflow_host.release_metadata import (  # noqa: E402
    ReleaseMetadataError,
    sign_release_metadata,
    unsigned_release_metadata_bytes,
    verify_release_metadata,
    verify_release_artifacts,
)


def _metadata() -> dict[str, object]:
    return {
        "format_version": 1,
        "index_url": "https://artifactory.example.test/simple",
        "expires_at": "2026-08-25T00:00:00+00:00",
        "artifacts": [],
        "revoked_key_ids": [],
        "revoked_artifacts": [],
    }


def test_release_metadata_uses_canonical_unsigned_bytes_and_ed25519_envelope() -> None:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes_raw()
    metadata = _metadata()

    signature = sign_release_metadata(
        metadata=metadata,
        key_id="release-root",
        private_key=private_key.private_bytes_raw(),
    )

    assert unsigned_release_metadata_bytes(metadata) == (
        b'{"artifacts":[],"expires_at":"2026-08-25T00:00:00+00:00",'
        b'"format_version":1,"index_url":"https://artifactory.example.test/simple",'
        b'"revoked_artifacts":[],"revoked_key_ids":[]}'
    )
    assert (
        verify_release_metadata(
            metadata=metadata,
            signature=signature,
            trusted_keys={"release-root": public_key},
        )
        == "release-root"
    )


def test_release_metadata_rejects_tampering_or_an_untrusted_signer() -> None:
    private_key = Ed25519PrivateKey.generate()
    metadata = _metadata()
    signature = sign_release_metadata(
        metadata=metadata,
        key_id="release-root",
        private_key=private_key.private_bytes_raw(),
    )

    with pytest.raises(ReleaseMetadataError, match="not trusted"):
        verify_release_metadata(
            metadata=metadata,
            signature=signature,
            trusted_keys={},
        )


def test_release_metadata_rejects_expired_or_signer_revocation() -> None:
    private_key = Ed25519PrivateKey.generate()
    metadata = _metadata()
    signature = sign_release_metadata(
        metadata=metadata,
        key_id="release-root",
        private_key=private_key.private_bytes_raw(),
    )
    trusted_keys = {"release-root": private_key.public_key().public_bytes_raw()}

    with pytest.raises(ReleaseMetadataError, match="expired"):
        verify_release_metadata(
            metadata=metadata,
            signature=signature,
            trusted_keys=trusted_keys,
            now=datetime(2026, 8, 25, tzinfo=UTC),
        )
    revoked = {**metadata, "revoked_key_ids": ["release-root"]}
    revoked_signature = sign_release_metadata(
        metadata=revoked,
        key_id="release-root",
        private_key=private_key.private_bytes_raw(),
    )
    with pytest.raises(ReleaseMetadataError, match="revoked"):
        verify_release_metadata(
            metadata=revoked,
            signature=revoked_signature,
            trusted_keys=trusted_keys,
            now=datetime(2026, 8, 24, tzinfo=UTC),
        )


def test_release_metadata_binds_exact_index_and_wheel_bytes() -> None:
    dar_wheel = b"dar wheel"
    metadata = _metadata()
    metadata["artifacts"] = [
        {
            "name": "dynamic-agent-runner",
            "version": "0.1.15",
            "sha256": hashlib.sha256(dar_wheel).hexdigest(),
        },
    ]

    assert verify_release_artifacts(
        metadata=metadata,
        index_url="https://artifactory.example.test/simple",
        required_versions={"dynamic-agent-runner": "0.1.15"},
        wheel_bytes={"dynamic-agent-runner": dar_wheel},
    ) == (("dynamic-agent-runner", "0.1.15"),)
    with pytest.raises(ReleaseMetadataError, match="index"):
        verify_release_artifacts(
            metadata=metadata,
            index_url="https://wrong.example.test/simple",
            required_versions={"dynamic-agent-runner": "0.1.15"},
            wheel_bytes={"dynamic-agent-runner": dar_wheel},
        )
