"""Tests for portable DAR authoring package signature primitives."""

from __future__ import annotations


import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


from dynamic_agent_runner.workflow_host.package_signatures import (  # noqa: E402
    PackageSignatureError,
    sign_manifest,
    verify_manifest,
)


def test_ed25519_signature_verifies_the_exact_canonical_manifest() -> None:
    private_key = Ed25519PrivateKey.generate()
    manifest = b'{"content_digest":"a"}'
    signature = sign_manifest(
        manifest=manifest,
        key_id="publisher.example.v1",
        private_key=private_key.private_bytes_raw(),
    )

    signer = verify_manifest(
        manifest=manifest,
        signature=signature,
        trusted_keys={
            "publisher.example.v1": private_key.public_key().public_bytes_raw()
        },
    )

    assert signer == "publisher.example.v1"
    assert signature["algorithm"] == "ed25519"


@pytest.mark.parametrize(
    "manifest, trusted_keys",
    [
        (b'{"content_digest":"changed"}', "trusted"),
        (b'{"content_digest":"a"}', "unknown"),
    ],
)
def test_signature_rejects_changed_manifest_or_unknown_publisher(
    manifest: bytes, trusted_keys: str
) -> None:
    private_key = Ed25519PrivateKey.generate()
    signature = sign_manifest(
        manifest=b'{"content_digest":"a"}',
        key_id="publisher.example.v1",
        private_key=private_key.private_bytes_raw(),
    )
    keys = (
        {"publisher.example.v1": private_key.public_key().public_bytes_raw()}
        if trusted_keys == "trusted"
        else {}
    )

    with pytest.raises(PackageSignatureError):
        verify_manifest(manifest=manifest, signature=signature, trusted_keys=keys)


def test_signature_rejects_malformed_keys_and_signatures() -> None:
    with pytest.raises(PackageSignatureError):
        sign_manifest(
            manifest=b"manifest",
            key_id="not a valid key id!",
            private_key=b"too short",
        )
    with pytest.raises(PackageSignatureError):
        verify_manifest(
            manifest=b"manifest",
            signature={"format_version": 1, "algorithm": "ed25519", "key_id": "x"},
            trusted_keys={"x": b"too short"},
        )
