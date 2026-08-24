"""Canonical detached signatures for DAR-authoring release metadata."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from packaging.version import InvalidVersion, Version


_KEY_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_DISTRIBUTION_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
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


@dataclass(frozen=True)
class ReleaseTrustRoot:
    """Human-configured release signing keys and per-distribution version floors."""

    trusted_keys: Mapping[str, bytes]
    minimum_versions: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "trusted_keys", dict(self.trusted_keys))
        object.__setattr__(self, "minimum_versions", dict(self.minimum_versions))


def load_release_trust_root(value: Mapping[str, object]) -> ReleaseTrustRoot:
    """Decode and validate the local JSON-compatible v1 launcher trust root."""

    required_fields = frozenset({"format_version", "trusted_keys", "minimum_versions"})
    if not isinstance(value, Mapping) or set(value) != required_fields:
        raise ReleaseMetadataError("release trust root is invalid")
    if value.get("format_version") != 1:
        raise ReleaseMetadataError("release trust root is invalid")
    return ReleaseTrustRoot(
        trusted_keys=_decode_trusted_keys(value.get("trusted_keys")),
        minimum_versions=_minimum_versions(value.get("minimum_versions")),
    )


def _decode_trusted_keys(value: object) -> dict[str, bytes]:
    if not isinstance(value, Mapping) or not value:
        raise ReleaseMetadataError("release trust root is invalid")
    trusted_keys: dict[str, bytes] = {}
    for key_id, encoded_key in value.items():
        _key_id(key_id)
        if not isinstance(encoded_key, str):
            raise ReleaseMetadataError("release trust root is invalid")
        try:
            public_key = base64.b64decode(encoded_key.encode("ascii"), validate=True)
            Ed25519PublicKey.from_public_bytes(public_key)
        except (TypeError, ValueError, UnicodeEncodeError) as error:
            raise ReleaseMetadataError("release trust root is invalid") from error
        trusted_keys[key_id] = public_key
    return trusted_keys


def _minimum_versions(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ReleaseMetadataError("release trust root is invalid")
    floors: dict[str, str] = {}
    for name, version in value.items():
        if not isinstance(name, str) or not name or not isinstance(version, str):
            raise ReleaseMetadataError("release trust root is invalid")
        try:
            Version(version)
        except InvalidVersion as error:
            raise ReleaseMetadataError("release trust root is invalid") from error
        floors[name] = version
    return floors


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
    minimum_versions: Mapping[str, str] | None = None,
) -> tuple[tuple[str, str, str], ...]:
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
            or not name
            or not isinstance(version, str)
            or not version
            or not isinstance(digest, str)
            or _SHA256.fullmatch(digest) is None
        ):
            raise ReleaseMetadataError("release artifacts are invalid")
        if name in entries:
            raise ReleaseMetadataError("release artifacts are invalid")
        entries[name] = entry
    _validate_required_artifact_coverage(
        entries=entries,
        required_versions=required_versions,
        wheel_bytes=wheel_bytes,
    )
    _validate_version_floors(required_versions, minimum_versions)
    revoked = _revoked_artifacts(metadata["revoked_artifacts"])
    resolved: list[tuple[str, str, str]] = []
    for name, version in sorted(required_versions.items()):
        entry = entries.get(name)
        data = wheel_bytes.get(name)
        if entry is None or entry["version"] != version or not isinstance(data, bytes):
            raise ReleaseMetadataError("release artifact is unavailable")
        if (name, version) in revoked:
            raise ReleaseMetadataError("release artifact is revoked")
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ReleaseMetadataError("release artifact hash is invalid")
        resolved.append((name, version, str(entry["sha256"])))
    return tuple(resolved)


def render_uv_requirements_lock(
    artifacts: tuple[tuple[str, str, str], ...],
) -> str:
    """Render verified release identities as a hash-enforced uv requirements lock.

    The caller must obtain ``artifacts`` from :func:`verify_release_artifacts`.
    This function defensively validates the output again because the rendered
    text crosses into a command-line package installer.
    """

    if not artifacts:
        raise ReleaseMetadataError("release lock artifacts are invalid")
    rendered: list[tuple[str, str, str]] = []
    names: set[str] = set()
    for artifact in artifacts:
        if not isinstance(artifact, tuple) or len(artifact) != 3:
            raise ReleaseMetadataError("release lock artifacts are invalid")
        name, version, digest = artifact
        if (
            not isinstance(name, str)
            or _DISTRIBUTION_NAME.fullmatch(name) is None
            or name in names
            or not isinstance(version, str)
            or not version
            or not isinstance(digest, str)
            or _SHA256.fullmatch(digest) is None
        ):
            raise ReleaseMetadataError("release lock artifacts are invalid")
        try:
            Version(version)
        except InvalidVersion as error:
            raise ReleaseMetadataError("release lock artifacts are invalid") from error
        names.add(name)
        rendered.append((name, version, digest))
    return "".join(
        f"{name}=={version} \\\n    --hash=sha256:{digest}\n"
        for name, version, digest in sorted(rendered)
    )


def _validate_required_artifact_coverage(
    *,
    entries: Mapping[str, Mapping[str, object]],
    required_versions: Mapping[str, str],
    wheel_bytes: Mapping[str, bytes],
) -> None:
    if set(required_versions) != set(entries) or set(wheel_bytes) != set(entries):
        raise ReleaseMetadataError("release artifact coverage is invalid")
    for name, version in required_versions.items():
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(version, str)
            or not version
        ):
            raise ReleaseMetadataError("release artifact coverage is invalid")


def _revoked_artifacts(value: object) -> frozenset[tuple[str, str]]:
    revoked: set[tuple[str, str]] = set()
    if not isinstance(value, list):
        raise ReleaseMetadataError("release artifact revocations are invalid")
    for entry in value:
        if not isinstance(entry, Mapping) or set(entry) != {"name", "version"}:
            raise ReleaseMetadataError("release artifact revocations are invalid")
        name = entry.get("name")
        version = entry.get("version")
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(version, str)
            or not version
        ):
            raise ReleaseMetadataError("release artifact revocations are invalid")
        pair = (name, version)
        if pair in revoked:
            raise ReleaseMetadataError("release artifact revocations are invalid")
        revoked.add(pair)
    return frozenset(revoked)


def _validate_version_floors(
    required_versions: Mapping[str, str], minimum_versions: Mapping[str, str] | None
) -> None:
    if minimum_versions is None:
        return
    for name, version in required_versions.items():
        floor = minimum_versions.get(name)
        if not isinstance(floor, str):
            raise ReleaseMetadataError("release security floor is unavailable")
        try:
            if Version(version) < Version(floor):
                raise ReleaseMetadataError(
                    "release artifact is below the security floor"
                )
        except InvalidVersion as error:
            raise ReleaseMetadataError("release security floor is invalid") from error


def _key_id(value: object) -> None:
    if not isinstance(value, str) or not _KEY_ID.fullmatch(value):
        raise ReleaseMetadataError("release signature is invalid")
