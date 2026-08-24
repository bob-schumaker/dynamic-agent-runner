"""Tests for signed canonical release metadata for the DAR runtime launcher."""

from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


from dynamic_agent_runner.workflow_host.release_metadata import (  # noqa: E402
    ReleaseTrustRoot,
    ReleaseMetadataError,
    load_release_trust_root,
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
    ) == (
        (
            "dynamic-agent-runner",
            "0.1.15",
            hashlib.sha256(dar_wheel).hexdigest(),
        ),
    )
    with pytest.raises(ReleaseMetadataError, match="index"):
        verify_release_artifacts(
            metadata=metadata,
            index_url="https://wrong.example.test/simple",
            required_versions={"dynamic-agent-runner": "0.1.15"},
            wheel_bytes={"dynamic-agent-runner": dar_wheel},
        )


def test_release_metadata_requires_an_exact_nonrevoked_artifact_set() -> None:
    dar_wheel = b"dar wheel"
    helper_wheel = b"helper wheel"
    metadata = _metadata()
    metadata["artifacts"] = [
        {
            "name": "dynamic-agent-runner",
            "version": "0.1.15",
            "sha256": hashlib.sha256(dar_wheel).hexdigest(),
        },
        {
            "name": "helper",
            "version": "2.0.0",
            "sha256": hashlib.sha256(helper_wheel).hexdigest(),
        },
    ]

    with pytest.raises(ReleaseMetadataError, match="coverage"):
        verify_release_artifacts(
            metadata=metadata,
            index_url="https://artifactory.example.test/simple",
            required_versions={"dynamic-agent-runner": "0.1.15"},
            wheel_bytes={"dynamic-agent-runner": dar_wheel},
        )

    metadata["revoked_artifacts"] = [
        {"name": "dynamic-agent-runner", "version": "0.1.15"}
    ]
    with pytest.raises(ReleaseMetadataError, match="revoked"):
        verify_release_artifacts(
            metadata=metadata,
            index_url="https://artifactory.example.test/simple",
            required_versions={
                "dynamic-agent-runner": "0.1.15",
                "helper": "2.0.0",
            },
            wheel_bytes={
                "dynamic-agent-runner": dar_wheel,
                "helper": helper_wheel,
            },
        )


def test_release_metadata_rejects_malformed_artifact_digests_and_revocations() -> None:
    metadata = _metadata()
    metadata["artifacts"] = [
        {
            "name": "dynamic-agent-runner",
            "version": "0.1.15",
            "sha256": "g" * 64,
        },
    ]

    with pytest.raises(ReleaseMetadataError, match="artifacts"):
        verify_release_artifacts(
            metadata=metadata,
            index_url="https://artifactory.example.test/simple",
            required_versions={"dynamic-agent-runner": "0.1.15"},
            wheel_bytes={"dynamic-agent-runner": b"dar wheel"},
        )
    metadata["artifacts"][0]["sha256"] = hashlib.sha256(b"dar wheel").hexdigest()
    metadata["revoked_artifacts"] = [{"name": "dynamic-agent-runner"}]
    with pytest.raises(ReleaseMetadataError, match="revocations"):
        verify_release_artifacts(
            metadata=metadata,
            index_url="https://artifactory.example.test/simple",
            required_versions={"dynamic-agent-runner": "0.1.15"},
            wheel_bytes={"dynamic-agent-runner": b"dar wheel"},
        )


def test_release_trust_root_decodes_keys_and_enforces_version_floors() -> None:
    private_key = Ed25519PrivateKey.generate()
    root = load_release_trust_root(
        {
            "format_version": 1,
            "trusted_keys": {
                "release-root": base64.b64encode(
                    private_key.public_key().public_bytes_raw()
                ).decode("ascii"),
            },
            "minimum_versions": {"dynamic-agent-runner": "0.1.16rc1"},
        }
    )
    assert isinstance(root, ReleaseTrustRoot)
    assert root.trusted_keys == {
        "release-root": private_key.public_key().public_bytes_raw(),
    }

    dar_wheel = b"dar wheel"
    metadata = _metadata()
    metadata["artifacts"] = [
        {
            "name": "dynamic-agent-runner",
            "version": "0.1.16",
            "sha256": hashlib.sha256(dar_wheel).hexdigest(),
        },
    ]
    assert verify_release_artifacts(
        metadata=metadata,
        index_url="https://artifactory.example.test/simple",
        required_versions={"dynamic-agent-runner": "0.1.16"},
        wheel_bytes={"dynamic-agent-runner": dar_wheel},
        minimum_versions=root.minimum_versions,
    )

    metadata["artifacts"][0]["version"] = "0.1.16rc1"
    with pytest.raises(ReleaseMetadataError, match="below the security floor"):
        verify_release_artifacts(
            metadata=metadata,
            index_url="https://artifactory.example.test/simple",
            required_versions={"dynamic-agent-runner": "0.1.16rc1"},
            wheel_bytes={"dynamic-agent-runner": dar_wheel},
            minimum_versions={"dynamic-agent-runner": "0.1.16"},
        )


@pytest.mark.parametrize(
    "root",
    [
        {},
        {"format_version": 1, "trusted_keys": {}, "minimum_versions": {}},
        {
            "format_version": 1,
            "trusted_keys": {"release-root": "not base64"},
            "minimum_versions": {"dynamic-agent-runner": "not a version"},
        },
    ],
)
def test_release_trust_root_rejects_malformed_configuration(
    root: dict[str, object],
) -> None:
    with pytest.raises(ReleaseMetadataError, match="trust root"):
        load_release_trust_root(root)
