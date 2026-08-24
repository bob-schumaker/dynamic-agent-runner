"""Ed25519 signatures over canonical portable package manifest bytes."""

from __future__ import annotations

import base64
import re
from collections.abc import Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


_KEY_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_SIGNATURE_KEYS = frozenset({"algorithm", "format_version", "key_id", "signature"})


class PackageSignatureError(ValueError):
    """Raised when a portable package signature cannot be trusted."""


def sign_manifest(
    *, manifest: bytes, key_id: str, private_key: bytes
) -> dict[str, object]:
    """Sign exact canonical manifest bytes with one Ed25519 private key."""

    _validate_manifest(manifest)
    _validate_key_id(key_id)
    try:
        signer = Ed25519PrivateKey.from_private_bytes(private_key)
    except (TypeError, ValueError) as error:
        raise PackageSignatureError("package signing key is invalid") from error
    return {
        "algorithm": "ed25519",
        "format_version": 1,
        "key_id": key_id,
        "signature": base64.b64encode(signer.sign(manifest)).decode("ascii"),
    }


def verify_manifest(
    *,
    manifest: bytes,
    signature: Mapping[str, object],
    trusted_keys: Mapping[str, bytes],
) -> str:
    """Verify exact manifest bytes against one configured publisher key."""

    _validate_manifest(manifest)
    key_id, signature_bytes = _parse_signature(signature)
    public_key_bytes = trusted_keys.get(key_id)
    if not isinstance(public_key_bytes, bytes):
        raise PackageSignatureError("package publisher is not trusted")
    try:
        verifier = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        verifier.verify(signature_bytes, manifest)
    except (InvalidSignature, TypeError, ValueError) as error:
        raise PackageSignatureError("package signature is invalid") from error
    return key_id


def _validate_manifest(manifest: bytes) -> None:
    if not isinstance(manifest, bytes) or not manifest:
        raise PackageSignatureError("package manifest bytes are invalid")


def _validate_key_id(key_id: str) -> None:
    if not isinstance(key_id, str) or not _KEY_ID.fullmatch(key_id):
        raise PackageSignatureError("package publisher key_id is invalid")


def _parse_signature(signature: Mapping[str, object]) -> tuple[str, bytes]:
    if not isinstance(signature, Mapping) or set(signature) != _SIGNATURE_KEYS:
        raise PackageSignatureError("package signature is invalid")
    if signature.get("format_version") != 1 or signature.get("algorithm") != "ed25519":
        raise PackageSignatureError("package signature is invalid")
    key_id = signature.get("key_id")
    _validate_key_id(key_id)
    encoded = signature.get("signature")
    if not isinstance(encoded, str):
        raise PackageSignatureError("package signature is invalid")
    try:
        decoded = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError) as error:
        raise PackageSignatureError("package signature is invalid") from error
    if len(decoded) != 64:
        raise PackageSignatureError("package signature is invalid")
    return key_id, decoded
