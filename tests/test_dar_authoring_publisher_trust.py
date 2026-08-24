"""Tests for human-configured portable package publisher trust."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


PLUGIN_SERVER_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "server"
sys.path.insert(0, str(PLUGIN_SERVER_ROOT))

from dar_workflow_server.publisher_trust import (  # noqa: E402
    PublisherTrustError,
    PublisherTrustStore,
)


def test_human_configured_publisher_key_survives_reopen_without_public_bytes(
    tmp_path: Path,
) -> None:
    key = Ed25519PrivateKey.generate().public_key().public_bytes_raw()
    store = PublisherTrustStore(tmp_path / "state")

    publisher = store.add(key_id="publisher.example.v1", public_key=key)
    reopened = PublisherTrustStore(tmp_path / "state")

    assert publisher.key_id == "publisher.example.v1"
    assert len(publisher.public_key_sha256) == 64
    assert not hasattr(publisher, "public_key")
    assert reopened.publishers() == (publisher,)
    assert reopened.trusted_keys() == {"publisher.example.v1": key}


def test_publisher_key_replacement_and_malformed_material_fail_closed(
    tmp_path: Path,
) -> None:
    store = PublisherTrustStore(tmp_path / "state")
    first = Ed25519PrivateKey.generate().public_key().public_bytes_raw()
    store.add(key_id="publisher.example.v1", public_key=first)

    with pytest.raises(PublisherTrustError, match="already configured"):
        store.add(
            key_id="publisher.example.v1",
            public_key=Ed25519PrivateKey.generate().public_key().public_bytes_raw(),
        )
    with pytest.raises(PublisherTrustError, match="invalid"):
        store.add(key_id="bad key id!", public_key=b"too short")


def test_human_can_revoke_a_configured_publisher_key(tmp_path: Path) -> None:
    store = PublisherTrustStore(tmp_path / "state")
    key = Ed25519PrivateKey.generate().public_key().public_bytes_raw()
    store.add(key_id="publisher.example.v1", public_key=key)

    store.revoke("publisher.example.v1")

    assert store.publishers() == ()
    assert store.trusted_keys() == {}
