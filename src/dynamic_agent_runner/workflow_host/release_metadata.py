"""Canonical detached signatures for DAR-authoring release metadata."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


_KEY_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_SIGNATURE_FIELDS = frozenset({"algorithm", "format_version", "key_id", "signature"})
_METADATA_FIELDS = frozenset(
    {
        "format_version",
        "index_url",
        "expires_at",
        "artifacts",
        "revoked_key_ids",
        "revoked_artifacts",
    }
)


class ReleaseMetadataError(ValueError):
    """Raised when signed launcher release metadata cannot be trusted."""


def unsigned_release_metadata_bytes(metadata: Mapping[str, object]) -> bytes:
    """Return exact canonical bytes for the unsigned v1 release document."""

    if not isinstance(metadata, Mapping) or set(metadata) != _METADATA_FIELDS:
        raise ReleaseMetadataError("release metadata is invalid")
    if metadata.get("format_version") != 1:
        raise ReleaseMetadataError("release metadata is invalid")
    for field in ("index_url", "expires_at"):
        if not isinstance(metadata.get(field), str) or not metadata[field]:
            raise ReleaseMetadataError("release metadata is invalid")
    for field in ("artifacts", "revoked_key_ids", "revoked_artifacts"):
        if not isinstance(metadata.get(field), list):
            raise ReleaseMetadataError("release metadata is invalid")
    return json.dumps(dict(metadata), sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def sign_release_metadata(
    *, metadata: Mapping[str, object], key_id: str, private_key: bytes
) -> dict[str, object]:
    """Sign canonical release metadata with one Ed25519 private key."""

    _key_id(key_id)
    try:
        signer = Ed25519PrivateKey.from_private_bytes(private_key)
    except (TypeError, ValueError) as error:
        raise ReleaseMetadataError("release signing key is invalid") from error
    return {
        "algorithm": "ed25519",
        "format_version": 1,
        "key_id": key_id,
        "signature": base64.b64encode(
            signer.sign(unsigned_release_metadata_bytes(metadata))
        ).decode("ascii"),
    }


def verify_release_metadata(
    *,
    metadata: Mapping[str, object],
    signature: Mapping[str, object],
    trusted_keys: Mapping[str, bytes],
    now: datetime | None = None,
) -> str:
    """Verify exact release metadata bytes against a configured trusted key."""

    payload = unsigned_release_metadata_bytes(metadata)
    if (
        not isinstance(signature, Mapping)
        or set(signature) != _SIGNATURE_FIELDS
        or signature.get("format_version") != 1
        or signature.get("algorithm") != "ed25519"
    ):
        raise ReleaseMetadataError("release signature is invalid")
    key_id = signature.get("key_id")
    _key_id(key_id)
    _validate_freshness(metadata, key_id, now)
    key = trusted_keys.get(key_id)
    if not isinstance(key, bytes):
        raise ReleaseMetadataError("release signer is not trusted")
    try:
        encoded = signature["signature"]
        if not isinstance(encoded, str):
            raise ValueError
        signature_bytes = base64.b64decode(encoded.encode("ascii"), validate=True)
        Ed25519PublicKey.from_public_bytes(key).verify(signature_bytes, payload)
    except (InvalidSignature, TypeError, ValueError, UnicodeEncodeError) as error:
        raise ReleaseMetadataError("release signature is invalid") from error
    return key_id


def _validate_freshness(
    metadata: Mapping[str, object], key_id: str, now: datetime | None
) -> None:
    try:
        expiry = datetime.fromisoformat(str(metadata["expires_at"]))
    except ValueError as error:
        raise ReleaseMetadataError("release metadata is invalid") from error
    if expiry.tzinfo is None:
        raise ReleaseMetadataError("release metadata is invalid")
    current = datetime.now(UTC) if now is None else now
    if not isinstance(current, datetime) or current.tzinfo is None:
        raise ReleaseMetadataError("release verification time is invalid")
    if expiry <= current.astimezone(UTC):
        raise ReleaseMetadataError("release metadata is expired")
    if key_id in metadata["revoked_key_ids"]:
        raise ReleaseMetadataError("release signer is revoked")


def verify_release_artifacts(
    *,
    metadata: Mapping[str, object],
    index_url: str,
    required_versions: Mapping[str, str],
    wheel_bytes: Mapping[str, bytes],
) -> tuple[tuple[str, str], ...]:
    """Verify that selected wheel bytes exactly match signed release entries."""

    unsigned_release_metadata_bytes(metadata)
    if metadata["index_url"] != index_url:
        raise ReleaseMetadataError("release index is invalid")
    entries: dict[str, Mapping[str, object]] = {}
    for entry in metadata["artifacts"]:
        if not isinstance(entry, Mapping) or set(entry) != {
            "name",
            "version",
            "sha256",
        }:
            raise ReleaseMetadataError("release artifacts are invalid")
        name = entry.get("name")
        version = entry.get("version")
        digest = entry.get("sha256")
        if (
            not isinstance(name, str)
            or not isinstance(version, str)
            or not isinstance(digest, str)
            or len(digest) != 64
        ):
            raise ReleaseMetadataError("release artifacts are invalid")
        if name in entries:
            raise ReleaseMetadataError("release artifacts are invalid")
        entries[name] = entry
    resolved: list[tuple[str, str]] = []
    for name, version in sorted(required_versions.items()):
        entry = entries.get(name)
        data = wheel_bytes.get(name)
        if entry is None or entry["version"] != version or not isinstance(data, bytes):
            raise ReleaseMetadataError("release artifact is unavailable")
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ReleaseMetadataError("release artifact hash is invalid")
        resolved.append((name, version))
    return tuple(resolved)


def _key_id(value: object) -> None:
    if not isinstance(value, str) or not _KEY_ID.fullmatch(value):
        raise ReleaseMetadataError("release signature is invalid")
