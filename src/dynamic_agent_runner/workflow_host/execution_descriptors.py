"""Canonical sealed execution descriptors and pure ABI validation."""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol


class ExecutionDescriptorError(ValueError):
    """Raised when a sealed execution descriptor or ABI is invalid."""


@dataclass(frozen=True)
class ExecutionDescriptorAbi:
    """Exact receiver-supported declarative execution ABI identity."""

    abi_id: str
    version: str
    contract_digest: str

    def __post_init__(self) -> None:
        _text(self.abi_id, "execution ABI id")
        _text(self.version, "execution ABI version")
        _hex(self.contract_digest, 64, "execution ABI contract digest")

    def to_mapping(self) -> dict[str, str]:
        return {
            "id": self.abi_id,
            "version": self.version,
            "contract_digest": self.contract_digest,
        }


@dataclass(frozen=True)
class ExecutionDescriptor:
    """One canonical descriptor envelope validated by its exact ABI."""

    architecture_abi: ExecutionDescriptorAbi
    material_roles: tuple[str, ...]
    abi_fields: Mapping[str, object]
    format_version: int = 1

    def __post_init__(self) -> None:
        if self.format_version != 1:
            raise ExecutionDescriptorError(
                "execution descriptor format version is invalid"
            )
        if (
            not self.material_roles
            or self.material_roles != tuple(sorted(self.material_roles))
            or len(set(self.material_roles)) != len(self.material_roles)
        ):
            raise ExecutionDescriptorError(
                "execution descriptor material roles are invalid"
            )
        if any(not isinstance(role, str) for role in self.material_roles):
            raise ExecutionDescriptorError(
                "execution descriptor material roles are invalid"
            )
        for role in self.material_roles:
            _text(role, "execution descriptor material role")
        if not isinstance(self.abi_fields, Mapping):
            raise ExecutionDescriptorError(
                "execution descriptor ABI fields are invalid"
            )
        object.__setattr__(self, "material_roles", tuple(self.material_roles))
        object.__setattr__(self, "abi_fields", dict(self.abi_fields))
        _canonical_json(self.to_mapping())

    def to_mapping(self) -> dict[str, object]:
        return {
            "format_version": self.format_version,
            "architecture_abi": self.architecture_abi.to_mapping(),
            "material_roles": list(self.material_roles),
            "abi_fields": dict(self.abi_fields),
        }

    @property
    def canonical_bytes(self) -> bytes:
        return _canonical_json(self.to_mapping())

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


class ExecutionDescriptorValidator(Protocol):
    """A receiver-installed, pure validator for one exact ABI identity."""

    identity: ExecutionDescriptorAbi

    def validate(self, descriptor: ExecutionDescriptor) -> None:
        """Reject ABI-schema-invalid data without material or framework work."""


class ExecutionDescriptorValidatorRegistry:
    """Resolve a descriptor only through one exact receiver-installed ABI."""

    def __init__(self, validators: Sequence[ExecutionDescriptorValidator]) -> None:
        resolved: dict[ExecutionDescriptorAbi, ExecutionDescriptorValidator] = {}
        for validator in validators:
            identity = validator.identity
            if not isinstance(identity, ExecutionDescriptorAbi) or identity in resolved:
                raise ExecutionDescriptorError(
                    "execution descriptor ABI is unavailable"
                )
            resolved[identity] = validator
        self._validators = resolved

    def validate(self, descriptor: ExecutionDescriptor) -> None:
        validator = self._validators.get(descriptor.architecture_abi)
        if validator is None:
            raise ExecutionDescriptorError("execution descriptor ABI is unavailable")
        try:
            validator.validate(descriptor)
        except ExecutionDescriptorError:
            raise
        except Exception as error:  # noqa: BLE001 - receiver validator boundary.
            raise ExecutionDescriptorError("execution descriptor is invalid") from error


def parse_execution_descriptor(value: object) -> ExecutionDescriptor:
    """Parse a strict canonical descriptor envelope without invoking an ABI."""

    mapping = _mapping(value)
    if set(mapping) != {
        "format_version",
        "architecture_abi",
        "material_roles",
        "abi_fields",
    }:
        raise ExecutionDescriptorError("execution descriptor fields are invalid")
    roles = mapping["material_roles"]
    if not isinstance(roles, list):
        raise ExecutionDescriptorError(
            "execution descriptor material roles are invalid"
        )
    return ExecutionDescriptor(
        architecture_abi=_abi(mapping["architecture_abi"]),
        material_roles=tuple(
            _required_text(role, "execution descriptor material role") for role in roles
        ),
        abi_fields=_fields(mapping["abi_fields"]),
        format_version=_format_version(mapping["format_version"]),
    )


def parse_verified_execution_descriptor(
    value: object, *, expected_digest: str
) -> ExecutionDescriptor:
    """Parse one descriptor and bind it to the hash from a v2 material lock."""

    _hex(expected_digest, 64, "execution descriptor digest")
    descriptor = parse_execution_descriptor(value)
    if descriptor.digest != expected_digest:
        raise ExecutionDescriptorError("execution descriptor does not match lock")
    return descriptor


def _abi(value: object) -> ExecutionDescriptorAbi:
    if not isinstance(value, Mapping) or set(value) != {
        "id",
        "version",
        "contract_digest",
    }:
        raise ExecutionDescriptorError("execution descriptor ABI is invalid")
    return ExecutionDescriptorAbi(
        _required_text(value["id"], "execution ABI id"),
        _required_text(value["version"], "execution ABI version"),
        _required_text(value["contract_digest"], "execution ABI contract digest"),
    )


def _fields(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ExecutionDescriptorError("execution descriptor ABI fields are invalid")
    return dict(value)


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, bytes):
        if value.startswith(b"\xef\xbb\xbf"):
            raise ExecutionDescriptorError(
                "execution descriptor JSON must not contain a byte-order mark"
            )
        try:
            value = json.loads(value.decode("utf-8"), object_pairs_hook=_unique_object)
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            ExecutionDescriptorError,
        ) as error:
            raise ExecutionDescriptorError(
                "execution descriptor JSON is invalid"
            ) from error
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ExecutionDescriptorError("execution descriptor is invalid")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, item in pairs:
        if key in result:
            raise ExecutionDescriptorError(
                "execution descriptor JSON contains duplicate keys"
            )
        result[key] = item
    return result


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        _normalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _normalize(value: object) -> object:
    if isinstance(value, str):
        _text(value, "execution descriptor value")
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ExecutionDescriptorError(
                "execution descriptor canonical JSON value is invalid"
            )
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_normalize(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ExecutionDescriptorError(
            "execution descriptor canonical JSON value is invalid"
        )
    if isinstance(value, bool | int | float) or value is None:
        return value
    raise ExecutionDescriptorError(
        "execution descriptor canonical JSON value is invalid"
    )


def _format_version(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ExecutionDescriptorError("execution descriptor format version is invalid")
    return value


def _required_text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ExecutionDescriptorError(f"{name} is invalid")
    _text(value, name)
    return value


def _text(value: str, name: str) -> None:
    if not value or unicodedata.normalize("NFC", value) != value:
        raise ExecutionDescriptorError(f"{name} is invalid")


def _hex(value: str, length: int, name: str) -> None:
    if len(value) != length or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ExecutionDescriptorError(f"{name} is invalid")
