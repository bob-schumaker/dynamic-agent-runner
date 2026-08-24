"""Human-configured trusted Ed25519 publisher keys for portable packages."""

from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


_KEY_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


class PublisherTrustError(ValueError):
    """Raised when a trusted publisher key cannot be managed safely."""


@dataclass(frozen=True)
class TrustedPublisher:
    """Redaction-safe configured publisher identity."""

    key_id: str
    public_key_sha256: str


class PublisherTrustStore:
    """Persist human-configured public keys under the local host state root."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._path = root / "trusted-publishers.json"
        self._lock_path = root / "trusted-publishers.lock"
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        mode = os.lstat(root).st_mode
        if not os.path.isdir(root) or os.path.islink(root) or mode & 0o077:
            raise PublisherTrustError("publisher trust root is not private")
        os.chmod(root, 0o700)

    def add(self, *, key_id: str, public_key: bytes) -> TrustedPublisher:
        """Add one human-confirmed publisher key without silent replacement."""

        _validate_key_id(key_id)
        _validate_public_key(public_key)
        encoded = base64.b64encode(public_key).decode("ascii")
        with self._mutation_lock():
            publishers = self._read()
            existing = publishers.get(key_id)
            if existing is not None:
                if existing != encoded:
                    raise PublisherTrustError("publisher key is already configured")
                return _publisher(key_id, public_key)
            publishers[key_id] = encoded
            self._write(publishers)
        return _publisher(key_id, public_key)

    def revoke(self, key_id: str) -> None:
        """Remove one human-configured publisher key."""

        _validate_key_id(key_id)
        with self._mutation_lock():
            publishers = self._read()
            if key_id not in publishers:
                raise PublisherTrustError("publisher key is not configured")
            del publishers[key_id]
            self._write(publishers)

    def publishers(self) -> tuple[TrustedPublisher, ...]:
        """Return configured identities without exposing their public key bytes."""

        return tuple(
            _publisher(key_id, public_key)
            for key_id, public_key in sorted(self.trusted_keys().items())
        )

    def trusted_keys(self) -> dict[str, bytes]:
        """Return the internal key map used only by package signature verification."""

        return {
            key_id: _decode_public_key(encoded)
            for key_id, encoded in self._read().items()
        }

    @contextmanager
    def _mutation_lock(self) -> Iterator[None]:
        descriptor = os.open(self._lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _read(self) -> dict[str, str]:
        try:
            value = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        if (
            not isinstance(value, dict)
            or value.get("format_version") != 1
            or not isinstance(value.get("publishers"), dict)
        ):
            raise PublisherTrustError("publisher trust store is invalid")
        publishers: dict[str, str] = {}
        for key_id, encoded in value["publishers"].items():
            _validate_key_id(key_id)
            if not isinstance(encoded, str):
                raise PublisherTrustError("publisher trust store is invalid")
            _decode_public_key(encoded)
            publishers[key_id] = encoded
        return publishers

    def _write(self, publishers: dict[str, str]) -> None:
        temporary = self._path.with_suffix(".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(
                descriptor,
                json.dumps(
                    {"format_version": 1, "publishers": publishers},
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8"),
            )
        finally:
            os.close(descriptor)
        os.replace(temporary, self._path)


def _validate_key_id(key_id: str) -> None:
    if not isinstance(key_id, str) or not _KEY_ID.fullmatch(key_id):
        raise PublisherTrustError("publisher key_id is invalid")


def _validate_public_key(public_key: bytes) -> None:
    if not isinstance(public_key, bytes):
        raise PublisherTrustError("publisher public key is invalid")
    try:
        Ed25519PublicKey.from_public_bytes(public_key)
    except ValueError as error:
        raise PublisherTrustError("publisher public key is invalid") from error


def _decode_public_key(encoded: str) -> bytes:
    try:
        public_key = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError) as error:
        raise PublisherTrustError("publisher trust store is invalid") from error
    _validate_public_key(public_key)
    return public_key


def _publisher(key_id: str, public_key: bytes) -> TrustedPublisher:
    return TrustedPublisher(
        key_id=key_id,
        public_key_sha256=hashlib.sha256(public_key).hexdigest(),
    )
